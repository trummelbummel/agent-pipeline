from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal, NamedTuple

import ollama
from langgraph.graph import END, START, StateGraph

from compliance.branch_log import log_branch_decision
from compliance.config.settings import AnalysisConfig, AppConfig
from compliance.llm.chat import ChatFn
from compliance.llm.checks import CheckContext, CheckSuite
from compliance.llm.classifier import CaseClassifier
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
from compliance.policy.gates import gates_from_config
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
from compliance.workflows.claim_artifacts import ClaimArtifactReader
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
    """Soft-fail analysis batch: published paths plus per-claim outcomes."""

    paths: list[Path]
    outcomes: tuple[ClaimRunOutcome, ...]


class _StageClassifiers(NamedTuple):
    """Analysis-stage classifiers built once from ``AnalysisConfig``."""

    coverage: CaseClassifier
    cancellation_reason: CaseClassifier
    cancellation_document: CaseClassifier
    personal_effects_document: CaseClassifier
    missed_departure_document: CaseClassifier


def _stage_classifiers(analysis: AnalysisConfig, chat_fn: ChatFn | None) -> _StageClassifiers:
    return _StageClassifiers(
        coverage=CaseClassifier.from_config(analysis.coverage, chat_fn),
        cancellation_reason=CaseClassifier.from_config(analysis.cancellation_reason, chat_fn),
        cancellation_document=CaseClassifier.from_config(analysis.cancellation_document, chat_fn),
        personal_effects_document=CaseClassifier.from_config(analysis.personal_effects_document, chat_fn),
        missed_departure_document=CaseClassifier.from_config(analysis.missed_departure_document, chat_fn),
    )


class ClaimPipeline:
    """Thin LangGraph orchestration over preprocessed claim artifacts."""

    def __init__(self, config: AppConfig, chat_fn: ChatFn | None = None) -> None:
        self._config = config
        self._classifiers = _stage_classifiers(config.analysis, chat_fn)
        self._check_suite = CheckSuite.from_config(config.checking, chat_fn or ollama.chat)
        self._date_gates = gates_from_config(config.checking)

    @property
    def preprocessed_root(self) -> Path:
        """Root directory for mirrored preprocessed claim inputs."""
        return Path(self._config.preprocessing.preprocessed_dir)

    @property
    def results_root(self) -> Path:
        """Root directory for analysis_result.json outputs."""
        return Path(self._config.preprocessing.results_dir)

    def build_graph(self) -> Any:
        """Compile the claim-analysis StateGraph without a checkpointer."""
        builder: StateGraph[ClaimAnalysisState, None, ClaimAnalysisState, ClaimAnalysisState] = StateGraph(
            ClaimAnalysisState
        )
        for name, node in (
            ("load_artifacts", self._load_artifacts_node),
            ("classify_coverage", self._classify_coverage_node),
            ("classify_reason", self._classify_reason_node),
            ("classify_cancel_document", self._classify_cancel_document_node),
            ("classify_pe_document", self._classify_pe_document_node),
            ("classify_missed_document", self._classify_missed_document_node),
            ("run_checker", self._run_checker_node),
            ("persist", self._persist_node),
        ):
            builder.add_node(name, node)
        builder.add_edge(START, "load_artifacts")
        builder.add_edge("load_artifacts", "classify_coverage")
        builder.add_conditional_edges("classify_coverage", self._route_after_coverage)
        builder.add_edge("classify_reason", "classify_cancel_document")
        builder.add_edge("classify_cancel_document", "run_checker")
        builder.add_edge("classify_pe_document", "run_checker")
        builder.add_edge("classify_missed_document", "run_checker")
        builder.add_edge("run_checker", "persist")
        builder.add_edge("persist", END)
        return builder.compile()

    def analyze_claim(self, claim_dir: Path, *, run_id: str | None = None) -> Path:
        """Run claim analysis for one claim and write analysis_result.json.

        :param claim_dir: Claim folder; loads local artifacts or ``preprocessed_dir``.
        :param run_id: Generation id; minted when the caller passes none.
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

        :param source: Claim folder, claims directory, or ``None`` for preprocessed_dir.
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
        """Resolve the preprocessed artifact directory for ``claim_dir``."""
        artifacts = self._config.preprocessing.artifacts
        if (claim_dir / artifacts.supporting_document).is_file():
            return claim_dir
        return self.preprocessed_root / claim_dir.name

    def _batch_analysis_outcomes(self, folders: list[Path], *, run_id: str) -> BatchAnalysisResult:
        """Analyze each claim folder; soft-fail and continue on errors."""
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
        """Route to the next node from the routed coverage decision (SR-004)."""
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
        reader = ClaimArtifactReader(
            claim_dir=self._claim_input_root(state),
            artifacts=self._config.preprocessing.artifacts,
        )
        texts = reader.texts()
        has_signature = reader.has_signature()
        human_in_the_loop = reader.human_in_the_loop()
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
        result = self._classifiers.coverage.classify(state["description_text"])
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
        return self._stage_label_update(
            state,
            branch="classify_reason",
            reason="cancellation_reason_stage",
            classifier=self._classifiers.cancellation_reason,
            text=state["description_text"],
            state_key="reason_labels",
        )

    def _classify_cancel_document_node(self, state: ClaimAnalysisState) -> dict[str, object]:
        return self._stage_label_update(
            state,
            branch="classify_cancel_document",
            reason="cancellation_document_stage",
            classifier=self._classifiers.cancellation_document,
            text=state["supporting_document_text"],
            state_key="document_labels",
        )

    def _classify_pe_document_node(self, state: ClaimAnalysisState) -> dict[str, object]:
        return self._stage_label_update(
            state,
            branch="classify_pe_document",
            reason="personal_effects_document_stage",
            classifier=self._classifiers.personal_effects_document,
            text=state["supporting_document_text"],
            state_key="document_labels",
        )

    def _classify_missed_document_node(self, state: ClaimAnalysisState) -> dict[str, object]:
        return self._stage_label_update(
            state,
            branch="classify_missed_document",
            reason="missed_departure_document_stage",
            classifier=self._classifiers.missed_departure_document,
            text=state["supporting_document_text"],
            state_key="document_labels",
        )

    def _stage_label_update(
        self,
        state: ClaimAnalysisState,
        *,
        branch: str,
        reason: str,
        classifier: CaseClassifier,
        text: str,
        state_key: str,
    ) -> dict[str, object]:
        """Classify text and return one label-list state update.

        :param state: Current graph state (claim_id for branch log).
        :param branch: Branch-log name for this node.
        :param reason: Branch-log reason key.
        :param classifier: Prebuilt classifier for the stage.
        :param text: Input text for the classifier.
        :param state_key: ``reason_labels`` or ``document_labels``.
        :return: State update with the selected label codes.
        """
        result = classifier.classify(text)
        log_branch_decision(logger, branch=branch, outcome="CLASSIFIED", reason=reason, claim=state.get("claim_id"))
        return {state_key: list(result.labels)}

    def _run_checker_node(self, state: ClaimAnalysisState) -> dict[str, object]:
        rule_set = rule_set_for_claim(
            branch=state["routed_coverage"].branch,
            classified_codes=classified_document_codes(state, analysis=self._config.analysis),
            required_documents=self._config.analysis.required_documents,
        )
        results = run_checks(
            context=CheckContext(
                description=state["description_text"],
                document=state["supporting_document_text"],
                booking=state.get("supporting_documents_text") or "",
            ),
            rule_set=rule_set,
            gates=self._date_gates,
            suite=self._check_suite,
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
        artifacts = self._config.preprocessing.artifacts
        # Two roots deliberately (P-04): OCR failure under preprocessed_dir;
        # metadata run_id under claim input root — reconciling would change decisions.
        ocr_reader = ClaimArtifactReader(
            claim_dir=self.preprocessed_root / claim_id,
            artifacts=artifacts,
        )
        input_reader = ClaimArtifactReader(
            claim_dir=self._claim_input_root(state),
            artifacts=artifacts,
        )
        ocr_failure_reason = ocr_reader.ocr_failure_reason()
        analysis = self._config.analysis
        hitl = resolved_human_in_the_loop(state, analysis=analysis, ocr_failure_reason=ocr_failure_reason)
        hitl_source = human_in_the_loop_provenance(state, analysis=analysis, ocr_failure_reason=ocr_failure_reason)
        published = self._published_generation(
            state,
            ocr_failure_reason=ocr_failure_reason,
            metadata_run_id=input_reader.metadata_run_id(),
        )
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

    def _published_generation(
        self,
        state: ClaimAnalysisState,
        *,
        ocr_failure_reason: str | None,
        metadata_run_id: str | None,
    ) -> PublishedGeneration:
        """Publish analysis_result + predicted_answer as one run-scoped generation."""
        artifacts = self._config.preprocessing.artifacts
        analysis = self._config.analysis
        run_id = state["run_id"]
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

    def _claim_input_root(self, state: ClaimAnalysisState) -> Path:
        """Resolve the artifact directory for ``state`` (input_root or preprocessed)."""
        if state.get("input_root"):
            return Path(state["input_root"])
        return self.preprocessed_root / state["claim_id"]

    def _analysis_result_path(self, claim_id: str) -> Path:
        return self.results_root / claim_id / self._config.preprocessing.artifacts.analysis_result
