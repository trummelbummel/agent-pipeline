from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal, NamedTuple

from langgraph.graph import END, START, StateGraph

from compliance.branch_log import log_branch_decision
from compliance.config.settings import AppConfig, ClassificationConfig
from compliance.llm.chat import ChatFn
from compliance.llm.checker import CheckerMode, CheckOutcome
from compliance.llm.classifier import CaseClassifier, ClassificationResult
from compliance.models.claim import GroundTruth
from compliance.models.decisions import (
    DECISION_APPROVE,
    DECISION_DENY,
    DECISION_UNCERTAIN,
)
from compliance.policy import (
    ClaimAnalysisState,
    CoverageBranch,
    RoutedCoverage,
    checker_state_updates,
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

# Checker and gate booleans copied into analysis_result.json, in payload key order.
_STATE_BOOLEAN_KEYS: tuple[str, ...] = (
    "checker_containment",
    "checker_contradicts",
    "identity_check",
    "identity_unclear",
    "document_has_signature",
    "signature_check",
    "healthy_check",
    "checker_document_not_authentic",
    "checker_incomplete_document",
    "departure_within_days",
    "checker_suspicious_dating",
)

# Checker VIOLATION → legacy DENY explanation key (order matches _violated_checkers).
_VIOLATION_LEGACY_KEYS: tuple[tuple[CheckerMode, str], ...] = (
    ("identity", "identity_check"),
    ("healthy", "healthy_check"),
    ("not_authentic", "checker_document_not_authentic"),
    ("incomplete", "checker_incomplete_document"),
    ("contradicts", "checker_contradicts"),
)

# Modes whose ABSTAIN drives UNCERTAIN (identity only; containment ABSTAIN is record-only).
_ABSTAIN_UNCERTAIN_MODES: frozenset[CheckerMode] = frozenset({"identity"})

# Modes whose ERROR drives UNCERTAIN. Containment ERROR is record-only (checker docstring).
_ERROR_DECISION_MODES: frozenset[CheckerMode] = frozenset({
    "contradicts",
    "healthy",
    "not_authentic",
    "incomplete",
    "identity",
})


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
            classified_codes=self._classified_document_codes(state),
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
        hitl = self._resolved_human_in_the_loop(state)
        hitl_source = self._human_in_the_loop_provenance(state)
        published = self._published_generation(state)
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

    @staticmethod
    def _classifier_returned_false(state: ClaimAnalysisState) -> bool:
        """True when the routed coverage label is ``False``, or a raw reason/document label is.

        Coverage follows the routed winner (P-01): a losing ``False`` in the
        coverage selection has no HITL side effect. Reason and document stages
        keep raw membership (SR-010/SR-004 out-of-scope precedence unchanged).

        :param state: Graph state with routed_coverage and reason/document label codes.
        :return: Whether the routed coverage label, or a raw reason/document
            label, is the confident-negative ``False``.
        """
        if state["routed_coverage"].label == "False":
            return True
        return any(
            "False" in labels for labels in (state.get("reason_labels") or [], state.get("document_labels") or [])
        )

    def _resolved_human_in_the_loop(self, state: ClaimAnalysisState) -> bool:
        """HITL from preprocess, classifier ``False``, or any UNCERTAIN decision.

        Checker gates that emit UNCERTAIN (suspicious dating, far departure,
        identity unclear, coverage abstention, OCR failure) always require
        operator review — same as classifier abstention.

        :param state: Final (or mid-pipeline) graph state.
        :return: Whether a human should review the claim.
        """
        if bool(state.get("human_in_the_loop")):
            return True
        if self._classifier_returned_false(state):
            return True
        return self._decision_from_state(state).decision == DECISION_UNCERTAIN

    def _human_in_the_loop_provenance(self, state: ClaimAnalysisState) -> str:
        """Return the stable source code that drove HITL for this run.

        Check order (first match wins): ``classifier_false`` when the routed
        coverage or a raw reason/document label is the confident-negative;
        ``preprocess_metadata`` when the flag came in from the metadata read;
        ``uncertain_decision`` when the decision resolves to UNCERTAIN; else
        ``none``.

        :param state: Final graph state after checker (or coverage-only).
        :return: One of ``classifier_false``, ``preprocess_metadata``,
            ``uncertain_decision``, or ``none``.
        """
        if self._classifier_returned_false(state):
            return "classifier_false"
        if bool(state.get("human_in_the_loop")):
            return "preprocess_metadata"
        if self._decision_from_state(state).decision == DECISION_UNCERTAIN:
            return "uncertain_decision"
        return "none"

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

    @staticmethod
    def _state_boolean_flags(state: ClaimAnalysisState) -> dict[str, bool]:
        """Checker and gate booleans present in state, in analysis_result.json key order.

        :param state: Graph state to read boolean flags from.
        :return: Dict of ``_STATE_BOOLEAN_KEYS`` present in ``state``, cast to bool.
        """
        return {key: bool(state.get(key)) for key in _STATE_BOOLEAN_KEYS if key in state}

    def _analysis_result_payload(self, state: ClaimAnalysisState) -> dict[str, object]:
        """Build the structured analysis_result.json body from graph state.

        ``*_labels`` hold semantic names from ``config.analysis.*.label_names``;
        numeric classifier codes are written alongside as ``*_label_codes``.
        Also records the evaluator-facing ``decision`` derived from checker flags.

        :param state: Final ClaimAnalysisState after checker (or coverage-only).
        :return: JSON-serializable analysis payload. Checker keys are omitted when
            the Checker node did not run (coverage other_label path).
        """
        analysis = self._config.analysis
        coverage_codes = list(state.get("coverage_labels") or [])
        reason_codes = list(state.get("reason_labels") or [])
        document_codes = list(state.get("document_labels") or [])
        routed = state["routed_coverage"]
        document_stage = self._document_stage_for_coverage(routed)
        payload: dict[str, object] = {
            "claim_id": state["claim_id"],
            "coverage_labels": analysis.coverage.resolve_label_names(coverage_codes),
            "coverage_label_codes": coverage_codes,
            "routed_coverage_label": analysis.coverage.resolve_label_names([routed.label])[0],
            "routed_coverage_label_code": routed.label,
            "coverage_probabilities": dict(state.get("coverage_probabilities") or {}),
            "reason_labels": analysis.cancellation_reason.resolve_label_names(reason_codes),
            "reason_label_codes": reason_codes,
            "document_labels": document_stage.resolve_label_names(document_codes),
            "document_label_codes": document_codes,
        }
        payload.update(self._state_boolean_flags(state))
        if state.get("checker_outcomes"):
            payload["checker_outcomes"] = {mode: outcome.value for mode, outcome in state["checker_outcomes"].items()}
        if "checker_rule_set" in state:
            payload["checker_rule_set"] = state["checker_rule_set"]
        if "checker_skipped" in state:
            payload["checker_skipped"] = list(state["checker_skipped"])
        if "document_labels" in state:
            payload["checker_missing_documentation"] = self._is_missing_documentation(state)
        hitl = self._resolved_human_in_the_loop(state)
        payload["human_in_the_loop"] = hitl
        payload["human_in_the_loop_source"] = self._human_in_the_loop_provenance(state)
        metadata_run_id = self._document_metadata_run_id(
            state["claim_id"],
            input_root=self._claim_input_root(state),
        )
        if metadata_run_id is not None:
            payload["document_metadata_run_id"] = metadata_run_id
        decision = self._decision_from_state(state)
        payload["decision"] = decision.decision
        payload["decision_explanation"] = decision.explanation if isinstance(decision.explanation, str) else None
        payload["run_id"] = state["run_id"]
        return payload

    def _document_stage_for_coverage(self, routed: RoutedCoverage) -> ClassificationConfig:
        """Pick the document-stage config for the routed coverage branch.

        :param routed: Single authoritative coverage routing decision.
        :return: Document ClassificationConfig for semantic name resolution
            (abstention has no document labels; it keeps today's cancellation
            fallback for label-name resolution only).
        """
        analysis = self._config.analysis
        if routed.branch == "personal_effects":
            return analysis.personal_effects_document
        if routed.branch == "missed_departure":
            return analysis.missed_departure_document
        return analysis.cancellation_document

    def _acceptable_document_codes(self, state: ClaimAnalysisState) -> set[str]:
        """Return document codes allowed for this claim's routed coverage path.

        :param state: Graph state with routed coverage and reason label codes.
        :return: Acceptable document-type codes from ``required_documents`` config
            (falls back to the document-stage label list when a mapping is empty).
        """
        analysis = self._config.analysis
        required = analysis.required_documents
        routed = state["routed_coverage"]
        stage = self._document_stage_for_coverage(routed)
        stage_positive = set(stage.positive_labels())

        if routed.branch == "personal_effects":
            return set(required.personal_effects) or stage_positive
        if routed.branch == "missed_departure":
            return set(required.missed_departure) or stage_positive
        return self._cancellation_acceptable_codes(state, stage_positive)

    def _cancellation_acceptable_codes(self, state: ClaimAnalysisState, stage_positive: set[str]) -> set[str]:
        """Acceptable cancellation-document codes from the reason stage (or fallback).

        :param state: Graph state with reason label codes.
        :param stage_positive: Fallback codes when no reason-based mapping applies.
        :return: Union of ``cancellation_by_reason`` codes for classified reasons;
            else the union of every configured reason mapping; else stage positives.
        """
        analysis = self._config.analysis
        required = analysis.required_documents
        reason_abstention = analysis.cancellation_reason.abstention_labels()
        reason_codes = [code for code in (state.get("reason_labels") or []) if code not in reason_abstention]
        by_reason = required.cancellation_by_reason
        if reason_codes and by_reason:
            acceptable: set[str] = set()
            for reason in reason_codes:
                acceptable.update(by_reason.get(reason, []))
            if acceptable:
                return acceptable
        if by_reason:
            return {code for codes in by_reason.values() for code in codes}
        return stage_positive

    def _classified_document_codes(self, state: ClaimAnalysisState) -> set[str]:
        """Return non-abstention document codes from the document classifier stage.

        :param state: Graph state with routed coverage and document_labels.
        :return: Classified document codes excluding ``False`` / ``other_label``.
        """
        stage = self._document_stage_for_coverage(state["routed_coverage"])
        abstention = stage.abstention_labels()
        return {code for code in (state.get("document_labels") or []) if code not in abstention}

    def _is_missing_documentation(self, state: ClaimAnalysisState) -> bool:
        """True when no classified document type is acceptable for this claim.

        :param state: Final graph state after document classification.
        :return: Whether the supporting document type fails the required-doc check.
        """
        classified = self._classified_document_codes(state)
        if not classified:
            return True
        acceptable = self._acceptable_document_codes(state)
        return classified.isdisjoint(acceptable)

    def _violated_checkers(self, state: ClaimAnalysisState) -> list[str]:
        """Return checker / rule keys that failed for the claim.

        Missing documentation is document-type acceptability for the claim path —
        not failed containment (certs rarely contain the claim letter).
        Checker VIOLATIONs are read from ``checker_outcomes`` when present
        (SR-008); otherwise legacy boolean keys are used (date early-exit path).
        ``signature_check`` False means a medical certificate / hospital admission
        lacks ``has_signature`` in ``document_metadata.json`` → DENY.

        :param state: Final graph state after Checker (or coverage-only).
        :return: Ordered list of violated keys that drive DENY.
        """
        violated: list[str] = []
        if self._is_missing_documentation(state):
            violated.append("checker_missing_documentation")
        violated.extend(self._checker_violation_keys(state))
        if "signature_check" in state and not bool(state["signature_check"]):
            violated.append("signature_check")
        return self._ordered_violated_keys(violated)

    def _checker_violation_keys(self, state: ClaimAnalysisState) -> list[str]:
        """Legacy DENY keys for checker VIOLATIONs (or legacy bool fallback).

        :param state: Graph state with optional ``checker_outcomes``.
        :return: Unordered DENY explanation keys from checker modes.
        """
        outcomes = state.get("checker_outcomes") or {}
        if outcomes:
            return [key for mode, key in _VIOLATION_LEGACY_KEYS if outcomes.get(mode) is CheckOutcome.VIOLATION]
        keys: list[str] = []
        if "identity_check" in state and not bool(state["identity_check"]) and not bool(state.get("identity_unclear")):
            keys.append("identity_check")
        if "healthy_check" in state and bool(state["healthy_check"]):
            keys.append("healthy_check")
        if "checker_document_not_authentic" in state and bool(state["checker_document_not_authentic"]):
            keys.append("checker_document_not_authentic")
        if "checker_incomplete_document" in state and bool(state["checker_incomplete_document"]):
            keys.append("checker_incomplete_document")
        if "checker_contradicts" in state and bool(state["checker_contradicts"]):
            keys.append("checker_contradicts")
        return keys

    @staticmethod
    def _ordered_violated_keys(violated: list[str]) -> list[str]:
        """Stable DENY explanation key order (matches historical fold).

        :param violated: Unordered or partially ordered violated keys.
        :return: Keys filtered to the canonical order, preserving only those present.
        """
        order = (
            "checker_missing_documentation",
            "identity_check",
            "signature_check",
            "healthy_check",
            "checker_document_not_authentic",
            "checker_incomplete_document",
            "checker_contradicts",
        )
        present = set(violated)
        return [key for key in order if key in present]

    def _errored_checkers(self, state: ClaimAnalysisState) -> list[str]:
        """Modes whose ERROR should drive UNCERTAIN (excludes containment).

        :param state: Graph state with optional ``checker_outcomes``.
        :return: Errored mode names in recorded (insertion) order.
        """
        outcomes = state.get("checker_outcomes") or {}
        return [
            mode
            for mode, outcome in outcomes.items()
            if outcome is CheckOutcome.ERROR and mode in _ERROR_DECISION_MODES
        ]

    def _identity_abstain_unclear(self, state: ClaimAnalysisState) -> bool:
        """Whether identity ABSTAIN should yield UNCERTAIN ``identity_unclear``.

        :param state: Graph state with optional ``checker_outcomes`` / legacy flags.
        :return: True when identity abstained (or legacy identity_unclear is set).
        """
        outcomes = state.get("checker_outcomes") or {}
        if outcomes:
            return any(
                mode in _ABSTAIN_UNCERTAIN_MODES and outcome is CheckOutcome.ABSTAIN
                for mode, outcome in outcomes.items()
            )
        return "identity_unclear" in state and bool(state["identity_unclear"])

    def _decision_from_state(self, state: ClaimAnalysisState) -> GroundTruth:
        """Derive APPROVE/DENY/UNCERTAIN for evaluator-facing predicted_answer.

        Precedence (locked, SR-008):
        1. Preprocess OCR failure → UNCERTAIN
        2. Routed coverage abstention → UNCERTAIN ``coverage_false_label``
        3. ``departure_within_days`` → UNCERTAIN
        4. ``checker_suspicious_dating`` → UNCERTAIN
        5. Any VIOLATION (checker or missing-doc / signature) → DENY
        6. Any ERROR (except containment) → UNCERTAIN ``checker_error:<modes>``
        7. Identity ABSTAIN → UNCERTAIN ``identity_unclear``
        8. APPROVE ``checker_consistent``

        :param state: Final graph state.
        :return: GroundTruth decision written beside analysis_result.
        """
        claim_id = state.get("claim_id") or ""
        ocr_failure_reason = self._document_ocr_failure(claim_id) if claim_id else None
        if ocr_failure_reason is not None:
            return GroundTruth(
                decision=DECISION_UNCERTAIN,
                explanation=ocr_failure_reason,
            )
        if state["routed_coverage"].branch == "abstention":
            return GroundTruth(
                decision=DECISION_UNCERTAIN,
                explanation="coverage_false_label",
            )
        if bool(state.get("departure_within_days")):
            return GroundTruth(
                decision=DECISION_UNCERTAIN,
                explanation="departure_within_days",
            )
        if bool(state.get("checker_suspicious_dating")):
            return GroundTruth(
                decision=DECISION_UNCERTAIN,
                explanation="checker_suspicious_dating",
            )
        violated = self._violated_checkers(state)
        if violated:
            return GroundTruth(
                decision=DECISION_DENY,
                explanation=",".join(violated),
            )
        errored = self._errored_checkers(state)
        if errored:
            return GroundTruth(
                decision=DECISION_UNCERTAIN,
                explanation="checker_error:" + ",".join(errored),
            )
        if self._identity_abstain_unclear(state):
            return GroundTruth(
                decision=DECISION_UNCERTAIN,
                explanation="identity_unclear",
            )
        return GroundTruth(
            decision=DECISION_APPROVE,
            explanation="checker_consistent",
        )

    def _published_generation(self, state: ClaimAnalysisState) -> PublishedGeneration:
        """Publish analysis_result + predicted_answer as one run-scoped generation.

        :param state: Final ClaimAnalysisState with ``run_id``.
        :return: Paths of the promoted artifacts and the committed manifest.
        """
        artifacts = self._config.preprocessing.artifacts
        run_id = state["run_id"]
        bodies = {
            artifacts.analysis_result: json.dumps(self._analysis_result_payload(state), indent=2) + "\n",
            artifacts.predicted_answer: analysis_predicted_answer_text(
                self._predicted_answer_decision(state),
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

    def _predicted_answer_decision(self, state: ClaimAnalysisState) -> GroundTruth:
        """Build evaluator GroundTruth from analysis decision + resolved HITL.

        :param state: Final ClaimAnalysisState after checker (or coverage-only).
        :return: Decision with ``human_in_the_loop`` set (``source`` stamped on write).
        """
        return self._decision_from_state(state).model_copy(
            update={"human_in_the_loop": self._resolved_human_in_the_loop(state)}
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
