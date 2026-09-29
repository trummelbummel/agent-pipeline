from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal, NamedTuple

from langgraph.graph import END, START, StateGraph

from compliance.branch_log import log_branch_decision
from compliance.config.settings import AppConfig, ClassificationConfig
from compliance.llm.chat import ChatFn
from compliance.llm.classifier import CaseClassifier, ClassificationResult
from compliance.policy import (
    ClaimAnalysisState,
    CoverageBranch,
    analysis_result_payload,
    checker_state_updates,
    classified_document_codes,
    human_in_the_loop_provenance,
    predicted_answer_decision,
    resolved_human_in_the_loop,
    route_coverage,
    rule_set_for_claim,
    run_checks,
)
from compliance.preprocessing.claim_batch import (
    _discover_claim_folders,
    _is_claim_folder,
    _validate_claim_dir_name,
    _validate_claim_root,
)
from compliance.workflows.artifact_publication import (
    ClaimRunOutcome,
    PublishedGeneration,
    new_run_id,
    publish_claim_generation,
    write_failed_run_manifest,
)
from compliance.workflows.predicted_answer_io import analysis_predicted_answer_text

logger = logging.getLogger(__name__)

CoverageNextNode = Literal["classify_reason", "classify_pe_document", "classify_missed_document", "persist"]

_COVERAGE_BRANCH_NEXT_NODE: dict[CoverageBranch, CoverageNextNode] = {
    "cancellation": "classify_reason",
    "personal_effects": "classify_pe_document",
    "missed_departure": "classify_missed_document",
    "abstention": "persist",
}


class BatchAnalysisResult(NamedTuple):
    """Structured result of a soft-fail analysis batch.

    :param paths: Successfully published analysis_result.json paths.
    :param outcomes: Per-claim status for the run (ok or failed).
    """

    paths: list[Path]
    outcomes: tuple[ClaimRunOutcome, ...]


class ClaimPipeline:
    """LangGraph claim-analysis pipeline over Phase 03 preprocessed artifacts.

    :param config: Loaded application configuration (paths, analysis stages, checking).
    :param chat_fn: Optional shared chat seam for CaseClassifier and Checker (tests).
    """

    def __init__(self, config: AppConfig, chat_fn: ChatFn | None = None) -> None:
        self._config = config
        self._chat_fn = chat_fn

    @property
    def preprocessed_root(self) -> Path:
        """Root directory for mirrored preprocessed claim inputs."""
        return Path(self._config.preprocessing.preprocessed_dir)

    @property
    def results_root(self) -> Path:
        """Root directory for analysis_result.json outputs."""
        return Path(self._config.preprocessing.results_dir)

    def build_graph(self) -> Any:
        """Compile the claim-analysis StateGraph without a checkpointer.

        :return: Compiled LangGraph ready for one-shot ``invoke``.
        """
        builder: StateGraph[ClaimAnalysisState, None, ClaimAnalysisState, ClaimAnalysisState] = StateGraph(
            ClaimAnalysisState
        )
        builder.add_node("load_artifacts", self._load_artifacts_node)
        builder.add_node("classify_coverage", self._classify_coverage_node)
        builder.add_node("classify_reason", self._classify_reason_node)
        builder.add_node("classify_cancel_document", self._classify_cancel_document_node)
        builder.add_node("classify_pe_document", self._classify_pe_document_node)
        builder.add_node("classify_missed_document", self._classify_missed_document_node)
        builder.add_node("run_checker", self._run_checker_node)
        builder.add_node("persist", self._persist_node)

        builder.add_edge(START, "load_artifacts")
        builder.add_edge("load_artifacts", "classify_coverage")
        builder.add_conditional_edges(
            "classify_coverage",
            self._route_after_coverage,
        )
        builder.add_edge("classify_reason", "classify_cancel_document")
        builder.add_edge("classify_cancel_document", "run_checker")
        builder.add_edge("classify_pe_document", "run_checker")
        builder.add_edge("classify_missed_document", "run_checker")
        builder.add_edge("run_checker", "persist")
        builder.add_edge("persist", END)
        return builder.compile()

    def analyze_claim(self, claim_dir: Path, *, run_id: str | None = None) -> Path:
        """Run claim analysis for one claim and write analysis_result.json.

        :param claim_dir: Claim folder whose ``name`` is the safe path segment.
            When the folder already contains preprocessed artifacts, those are
            loaded directly; otherwise artifacts are read from config
            ``preprocessed_dir`` / ``claim_dir.name`` (process_then_analyze path).
        :param run_id: Generation id for this claim; minted when the caller
            passes none so single-claim and API entry points still publish under
            a run-scoped identity.
        :return: Path to the written analysis_result.json under results_dir.
        :raises ValueError: When the claim root is unsafe or a symlink.
        """
        _validate_claim_root(claim_dir)
        input_root = self._input_root_for_claim(claim_dir)
        resolved_run_id = run_id if run_id is not None else new_run_id()
        log_branch_decision(
            logger,
            branch="claim_analysis",
            outcome="START",
            reason="analyze_claim",
            claim=claim_dir.name,
            run_id=resolved_run_id,
        )
        graph = self.build_graph()
        graph.invoke({
            "claim_id": claim_dir.name,
            "input_root": str(input_root),
            "run_id": resolved_run_id,
        })
        return self._analysis_result_path(claim_dir.name)

    def run(self, source: Path | None = None) -> list[Path]:
        """Analyze one claim folder or soft-fail batch under a claims directory.

        Per-claim failures (classifier / I/O) are logged and skipped so the full
        run continues. Checker chat transport failures are retried then recorded
        as ERROR → UNCERTAIN on the claim (not skipped). Logs claim names,
        counts, and exception types only — never description or OCR payloads
        (T-04-02).

        :param source: Caller-supplied path — one claim folder, a directory of
            claims, or ``None`` to use config ``preprocessed_dir``.
        :return: Paths to successfully written analysis_result.json files.
        """
        self.results_root.mkdir(parents=True, exist_ok=True)
        run_id = new_run_id()

        if source is not None and _is_claim_folder(source):
            log_branch_decision(
                logger,
                branch="analysis_batch",
                outcome="SINGLE",
                reason="caller_claim_folder",
                claim=source.name,
                run_id=run_id,
            )
            return [self.analyze_claim(source, run_id=run_id)]

        root = self.preprocessed_root if source is None else source
        folders = _discover_claim_folders(root)
        logger.info("Discovered %d claim folders under %s", len(folders), root)
        batch = self._batch_analysis_outcomes(folders, run_id=run_id)
        failed_manifest = write_failed_run_manifest(self.results_root, run_id, batch.outcomes)
        if failed_manifest is not None:
            log_branch_decision(
                logger,
                branch="analysis_batch",
                outcome="FAILED_RUN_MANIFEST",
                reason="claim_failures",
                run_id=run_id,
                path=str(failed_manifest),
            )
        log_branch_decision(
            logger,
            branch="analysis_batch",
            outcome="COMPLETE",
            reason="soft_fail_batch",
            written=len(batch.paths),
            total=len(folders),
            run_id=run_id,
        )
        return batch.paths

    def _input_root_for_claim(self, claim_dir: Path) -> Path:
        """Resolve which directory holds preprocessed artifacts for ``claim_dir``.

        :param claim_dir: Caller path (raw folder or preprocessed claim folder).
        :return: Directory to read description/supporting_document artifacts from.
        """
        artifacts = self._config.preprocessing.artifacts
        if (claim_dir / artifacts.supporting_document).is_file():
            return claim_dir
        return self.preprocessed_root / claim_dir.name

    def _batch_analysis_outcomes(self, folders: list[Path], *, run_id: str) -> BatchAnalysisResult:
        """Analyze each claim folder; soft-fail and continue on errors.

        :param folders: Claim directories under preprocessed_dir.
        :param run_id: Shared generation id for every claim in this run.
        :return: Successful analysis_result paths plus per-claim outcomes.
        """
        written: list[Path] = []
        outcomes: list[ClaimRunOutcome] = []
        for claim_dir in folders:
            logger.info("Analyzing %s", claim_dir.name)
            try:
                _validate_claim_dir_name(claim_dir.name)
                written.append(self.analyze_claim(claim_dir, run_id=run_id))
                outcomes.append(ClaimRunOutcome(claim_id=claim_dir.name, status="ok", error=None))
            except Exception as exc:
                outcomes.append(ClaimRunOutcome(claim_id=claim_dir.name, status="failed", error=type(exc).__name__))
                log_branch_decision(
                    logger,
                    branch="analysis_write",
                    outcome="SKIP",
                    reason="claim_failed",
                    level=logging.ERROR,
                    claim=claim_dir.name,
                    error=type(exc).__name__,
                )
                logger.exception("Failed to analyze %s: %s", claim_dir.name, type(exc).__name__)
        return BatchAnalysisResult(paths=written, outcomes=tuple(outcomes))

    def _route_after_coverage(self, state: ClaimAnalysisState) -> CoverageNextNode:
        """Route to the next node from the single routed coverage decision (SR-004).

        :param state: Graph state after ``classify_coverage`` (``routed_coverage``
            is always set by that node before this router runs).
        :return: Next node name for the routed branch.
        """
        routed = state["routed_coverage"]
        next_node = _COVERAGE_BRANCH_NEXT_NODE[routed.branch]
        log_branch_decision(
            logger,
            branch="coverage_route",
            outcome="ROUTE",
            reason=routed.branch,
            claim=state.get("claim_id"),
            next_step=next_node,
            label=routed.label,
        )
        return next_node

    def _load_artifacts_node(self, state: ClaimAnalysisState) -> dict[str, object]:
        claim_id = state["claim_id"]
        _validate_claim_dir_name(claim_id)
        input_root = self._claim_input_root(state)
        texts = self._loaded_claim_texts(claim_id, input_root=input_root)
        has_signature = self._document_has_signature(claim_id, input_root=input_root)
        human_in_the_loop = self._document_human_in_the_loop(claim_id, input_root=input_root)
        log_branch_decision(
            logger,
            branch="load_artifacts",
            outcome="LOADED",
            reason="preprocessed_texts",
            claim=claim_id,
            document_has_signature=has_signature,
            human_in_the_loop=human_in_the_loop,
        )
        return {
            "description_text": texts["description_text"],
            "supporting_document_text": texts["supporting_document_text"],
            "supporting_documents_text": texts["supporting_documents_text"],
            "document_has_signature": has_signature,
            "human_in_the_loop": human_in_the_loop,
        }

    def _classify_coverage_node(self, state: ClaimAnalysisState) -> dict[str, object]:
        result = self._coverage_classification(state["description_text"])
        routed = route_coverage(result, self._config.analysis.coverage)
        log_branch_decision(
            logger,
            branch="classify_coverage",
            outcome="CLASSIFIED",
            reason="coverage_stage",
            claim=state.get("claim_id"),
            routed_label=routed.label,
            routed_branch=routed.branch,
        )
        return {
            "coverage_labels": list(result.labels),
            "coverage_probabilities": dict(result.probabilities),
            "routed_coverage": routed,
        }

    def _classify_reason_node(self, state: ClaimAnalysisState) -> dict[str, object]:
        result = self._reason_classification(state["description_text"])
        log_branch_decision(
            logger,
            branch="classify_reason",
            outcome="CLASSIFIED",
            reason="cancellation_reason_stage",
            claim=state.get("claim_id"),
        )
        return {"reason_labels": list(result.labels)}

    def _classify_cancel_document_node(self, state: ClaimAnalysisState) -> dict[str, object]:
        result = self._cancellation_document_classification(state["supporting_document_text"])
        log_branch_decision(
            logger,
            branch="classify_cancel_document",
            outcome="CLASSIFIED",
            reason="cancellation_document_stage",
            claim=state.get("claim_id"),
        )
        return {"document_labels": list(result.labels)}

    def _classify_pe_document_node(self, state: ClaimAnalysisState) -> dict[str, object]:
        result = self._personal_effects_document_classification(state["supporting_document_text"])
        log_branch_decision(
            logger,
            branch="classify_pe_document",
            outcome="CLASSIFIED",
            reason="personal_effects_document_stage",
            claim=state.get("claim_id"),
        )
        return {"document_labels": list(result.labels)}

    def _classify_missed_document_node(self, state: ClaimAnalysisState) -> dict[str, object]:
        result = self._missed_departure_document_classification(state["supporting_document_text"])
        log_branch_decision(
            logger,
            branch="classify_missed_document",
            outcome="CLASSIFIED",
            reason="missed_departure_document_stage",
            claim=state.get("claim_id"),
        )
        return {"document_labels": list(result.labels)}

    def _run_checker_node(self, state: ClaimAnalysisState) -> dict[str, object]:
        rule_set = rule_set_for_claim(
            branch=state["routed_coverage"].branch,
            classified_codes=classified_document_codes(state, analysis=self._config.analysis),
            required_documents=self._config.analysis.required_documents,
        )
        results = run_checks(
            description_text=state["description_text"],
            supporting_document_text=state["supporting_document_text"],
            supporting_documents_text=state.get("supporting_documents_text") or "",
            rule_set=rule_set,
            checking=self._config.checking,
            chat_fn=self._chat_fn,
        )
        early_uncertain = results.departure_within_days or results.suspicious_dating
        skipped = ",".join(rule_set.skipped)
        log_branch_decision(
            logger,
            branch="run_checker",
            outcome="CHECKED",
            reason="date_uncertain_skip_llm" if early_uncertain else rule_set.name,
            claim=state.get("claim_id"),
            rule_set=rule_set.name,
            skipped=skipped,
            identity_check=results.legacy_booleans.get("identity_check"),
            identity_unclear=results.legacy_booleans.get("identity_unclear"),
            signature_check=(bool(state.get("document_has_signature")) if "signature" in rule_set.applicable else None),
            healthy_check=results.legacy_booleans.get("healthy_check"),
            checker_document_not_authentic=results.legacy_booleans.get("checker_document_not_authentic"),
            checker_incomplete_document=results.legacy_booleans.get("checker_incomplete_document"),
            departure_within_days=results.departure_within_days,
            checker_suspicious_dating=results.suspicious_dating,
        )
        return checker_state_updates(
            rule_set,
            results,
            document_has_signature=bool(state.get("document_has_signature")),
        )

    def _persist_node(self, state: ClaimAnalysisState) -> dict[str, object]:
        claim_id = state["claim_id"]
        # Until ClaimArtifactReader (Commit C), OCR reason still uses the
        # preprocessed-root reader (no input_root); metadata run id uses claim input root.
        ocr_failure_reason = self._document_ocr_failure(claim_id)
        analysis = self._config.analysis
        hitl = resolved_human_in_the_loop(state, analysis=analysis, ocr_failure_reason=ocr_failure_reason)
        hitl_source = human_in_the_loop_provenance(state, analysis=analysis, ocr_failure_reason=ocr_failure_reason)
        published = self._published_generation(state, ocr_failure_reason=ocr_failure_reason)
        log_branch_decision(
            logger,
            branch="persist",
            outcome="WROTE",
            reason="analysis_result",
            claim=state.get("claim_id"),
            path=str(published.artifacts[0]) if published.artifacts else None,
            predicted_answer=str(published.artifacts[1]) if len(published.artifacts) > 1 else None,
            manifest=str(published.manifest),
            run_id=published.run_id,
            human_in_the_loop=hitl,
            hitl_source=hitl_source,
        )
        return {"human_in_the_loop": hitl}

    def _loaded_claim_texts(self, claim_id: str, *, input_root: Path | None = None) -> dict[str, str]:
        """Read description and supporting markdown from a claim artifact folder.

        :param claim_id: Validated claim folder segment.
        :param input_root: Directory holding artifacts; defaults to
            ``preprocessed_dir`` / ``claim_id``.
        :return: Dict with description_text, supporting_document_text,
            supporting_documents_text.
        """
        artifacts = self._config.preprocessing.artifacts
        claim_in = input_root if input_root is not None else self.preprocessed_root / claim_id
        supporting_documents_path = claim_in / artifacts.supporting_documents
        supporting_documents_text = (
            supporting_documents_path.read_text(encoding="utf-8") if supporting_documents_path.is_file() else ""
        )
        return {
            "description_text": (claim_in / artifacts.description).read_text(encoding="utf-8"),
            "supporting_document_text": (claim_in / artifacts.supporting_document).read_text(encoding="utf-8"),
            "supporting_documents_text": supporting_documents_text,
        }

    def _document_has_signature(self, claim_id: str, *, input_root: Path | None = None) -> bool:
        """Read has_signature from document_metadata.json (any document True).

        :param claim_id: Validated claim folder segment.
        :param input_root: Directory holding artifacts; defaults to preprocessed claim.
        :return: True when any metadata entry has ``has_signature`` true.
        """
        documents = self._document_metadata_entries(claim_id, input_root=input_root)
        return any(bool(entry.get("has_signature")) for entry in documents)

    def _document_human_in_the_loop(self, claim_id: str, *, input_root: Path | None = None) -> bool:
        """Read human_in_the_loop from document_metadata.json (any document True).

        :param claim_id: Validated claim folder segment.
        :param input_root: Directory holding artifacts; defaults to preprocessed claim.
        :return: True when any metadata entry already requires human review.
        """
        documents = self._document_metadata_entries(claim_id, input_root=input_root)
        return any(bool(entry.get("human_in_the_loop")) for entry in documents)

    def _document_ocr_failure(self, claim_id: str, *, input_root: Path | None = None) -> str | None:
        """Return preprocess OCR-failure reason if any document was tagged.

        :param claim_id: Validated claim folder segment.
        :param input_root: Directory holding artifacts; defaults to preprocessed claim.
        :return: ``ocr_read_failure`` or ``ocr_failure`` when present; else None.
        """
        documents = self._document_metadata_entries(claim_id, input_root=input_root)
        found: set[str] = set()
        for entry in documents:
            reasons = entry.get("failure_reasons")
            if not isinstance(reasons, list):
                continue
            for code in ("ocr_read_failure", "ocr_failure"):
                if code in reasons:
                    found.add(code)
        return next((code for code in ("ocr_read_failure", "ocr_failure") if code in found), None)

    def _document_metadata_entries(self, claim_id: str, *, input_root: Path | None = None) -> list[dict[str, object]]:
        """Load document metadata entries for a claim folder.

        :param claim_id: Validated claim folder segment.
        :param input_root: Directory holding artifacts; defaults to preprocessed claim.
        :return: List of metadata dicts (empty when missing/invalid).
        """
        raw = self._document_metadata_raw(claim_id, input_root=input_root)
        documents = raw.get("documents") if raw else None
        if not isinstance(documents, list):
            return []
        return [entry for entry in documents if isinstance(entry, dict)]

    def _document_metadata_run_id(self, claim_id: str, *, input_root: Path | None = None) -> str | None:
        """Return the preprocess ``run_id`` stamped on document_metadata.json, if any.

        :param claim_id: Validated claim folder segment.
        :param input_root: Directory holding artifacts; defaults to preprocessed claim.
        :return: Run id string, or None when absent (pre-SR-005 trees).
        """
        raw = self._document_metadata_raw(claim_id, input_root=input_root)
        if raw is None:
            return None
        value = raw.get("run_id")
        return value if isinstance(value, str) else None

    def _document_metadata_raw(self, claim_id: str, *, input_root: Path | None = None) -> dict[str, object] | None:
        """Parse document_metadata.json once for entries and provenance readers.

        :param claim_id: Validated claim folder segment.
        :param input_root: Directory holding artifacts; defaults to preprocessed claim.
        :return: Parsed object, or None when missing/invalid.
        """
        artifacts = self._config.preprocessing.artifacts
        claim_in = input_root if input_root is not None else self.preprocessed_root / claim_id
        path = claim_in / artifacts.document_metadata
        if not path.is_file():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None

    def _coverage_classification(self, description_text: str) -> ClassificationResult:
        return self._stage_classifier(self._config.analysis.coverage).classify(description_text)

    def _reason_classification(self, description_text: str) -> ClassificationResult:
        return self._stage_classifier(self._config.analysis.cancellation_reason).classify(description_text)

    def _cancellation_document_classification(self, supporting_document_text: str) -> ClassificationResult:
        return self._stage_classifier(self._config.analysis.cancellation_document).classify(supporting_document_text)

    def _personal_effects_document_classification(self, supporting_document_text: str) -> ClassificationResult:
        return self._stage_classifier(self._config.analysis.personal_effects_document).classify(
            supporting_document_text
        )

    def _missed_departure_document_classification(self, supporting_document_text: str) -> ClassificationResult:
        return self._stage_classifier(self._config.analysis.missed_departure_document).classify(
            supporting_document_text
        )

    def _published_generation(
        self,
        state: ClaimAnalysisState,
        *,
        ocr_failure_reason: str | None,
    ) -> PublishedGeneration:
        """Publish analysis_result + predicted_answer as one run-scoped generation.

        :param state: Final ClaimAnalysisState with ``run_id``.
        :param ocr_failure_reason: OCR-failure code read once in persist.
        :return: Paths of the promoted artifacts and the committed manifest.
        """
        artifacts = self._config.preprocessing.artifacts
        analysis = self._config.analysis
        run_id = state["run_id"]
        metadata_run_id = self._document_metadata_run_id(
            state["claim_id"],
            input_root=self._claim_input_root(state),
        )
        bodies = {
            artifacts.analysis_result: json.dumps(
                analysis_result_payload(
                    state,
                    analysis=analysis,
                    ocr_failure_reason=ocr_failure_reason,
                    metadata_run_id=metadata_run_id,
                ),
                indent=2,
            )
            + "\n",
            artifacts.predicted_answer: analysis_predicted_answer_text(
                predicted_answer_decision(
                    state,
                    analysis=analysis,
                    ocr_failure_reason=ocr_failure_reason,
                ),
                run_id=run_id,
            ),
        }
        return publish_claim_generation(
            results_root=self.results_root,
            claim_id=state["claim_id"],
            run_id=run_id,
            bodies=bodies,
            manifest_name=artifacts.run_manifest,
            source="analysis",
        )

    def _predicted_answer_path(self, claim_id: str) -> Path:
        return self.results_root / claim_id / self._config.preprocessing.artifacts.predicted_answer

    def _claim_input_root(self, state: ClaimAnalysisState) -> Path:
        """Resolve the artifact directory for ``state`` (input_root or preprocessed).

        :param state: Graph state with claim_id and optional input_root string.
        :return: Directory holding description / supporting_document artifacts.
        """
        if state.get("input_root"):
            return Path(state["input_root"])
        return self.preprocessed_root / state["claim_id"]

    def _analysis_result_path(self, claim_id: str) -> Path:
        return self.results_root / claim_id / self._config.preprocessing.artifacts.analysis_result

    def _stage_classifier(self, stage: ClassificationConfig) -> CaseClassifier:
        return CaseClassifier(
            labels=list(stage.labels),
            model_name=stage.model,
            prompt=stage.prompt,
            other_label=stage.other_label,
            chat_fn=self._chat_fn,
        )
