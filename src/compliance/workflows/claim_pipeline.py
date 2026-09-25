from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from compliance.branch_log import log_branch_decision
from compliance.config.settings import AppConfig, ClassificationConfig
from compliance.llm.chat import ChatFn
from compliance.llm.checker import Checker
from compliance.llm.classifier import CaseClassifier, ClassificationResult
from compliance.models.claim import GroundTruth
from compliance.preprocessing.claim_batch import _discover_claim_folders
from compliance.workflows.pipeline import _is_claim_folder, _validate_claim_dir_name

logger = logging.getLogger(__name__)

_DECISION_APPROVE = "APPROVE"
_DECISION_DENY = "DENY"
_DECISION_UNCERTAIN = "UNCERTAIN"


class ClaimAnalysisState(TypedDict, total=False):
    """LangGraph state for one-shot claim analysis.

    :param claim_id: Safe claim folder segment (validated at analyze_claim boundary).
    :param input_root: Absolute path to the preprocessed claim folder to load from.
    :param description_text: Contents of the configured description artifact.
    :param supporting_document_text: Docling markdown for the primary supporting document.
    :param supporting_documents_text: Booking/internal markdown artifact text.
    :param coverage_labels: Labels from the coverage classifier stage.
    :param reason_labels: Labels from the cancellation-reason stage.
    :param document_labels: Labels from the cancellation-document stage.
    :param checker_containment: Checker containment mode result.
    :param checker_contradicts: Checker contradicts mode result.
    """

    claim_id: str
    input_root: str
    description_text: str
    supporting_document_text: str
    supporting_documents_text: str
    coverage_labels: list[str]
    reason_labels: list[str]
    document_labels: list[str]
    checker_containment: bool
    checker_contradicts: bool


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
        builder: StateGraph[ClaimAnalysisState, None, ClaimAnalysisState, ClaimAnalysisState] = (
            StateGraph(ClaimAnalysisState)
        )
        builder.add_node("load_artifacts", self._load_artifacts_node)
        builder.add_node("classify_coverage", self._classify_coverage_node)
        builder.add_node("classify_reason", self._classify_reason_node)
        builder.add_node(
            "classify_cancel_document", self._classify_cancel_document_node
        )
        builder.add_node("classify_pe_document", self._classify_pe_document_node)
        builder.add_node(
            "classify_missed_document", self._classify_missed_document_node
        )
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

    def analyze_claim(self, claim_dir: Path) -> Path:
        """Run claim analysis for one claim and write analysis_result.json.

        :param claim_dir: Claim folder whose ``name`` is the safe path segment.
            When the folder already contains preprocessed artifacts, those are
            loaded directly; otherwise artifacts are read from config
            ``preprocessed_dir`` / ``claim_dir.name`` (process_then_analyze path).
        :return: Path to the written analysis_result.json under results_dir.
        :raises ValueError: When ``claim_dir.name`` is not a safe single path segment.
        """
        _validate_claim_dir_name(claim_dir.name)
        input_root = self._input_root_for_claim(claim_dir)
        log_branch_decision(
            logger,
            branch="claim_analysis",
            outcome="START",
            reason="analyze_claim",
            claim=claim_dir.name,
        )
        graph = self.build_graph()
        graph.invoke({"claim_id": claim_dir.name, "input_root": str(input_root)})
        return self._analysis_result_path(claim_dir.name)

    def run(self, source: Path | None = None) -> list[Path]:
        """Analyze one claim folder or soft-fail batch under a claims directory.

        Per-claim failures are logged and skipped so the full run continues.
        Logs claim names, counts, and exception types only — never description
        or OCR payloads (T-04-02).

        :param source: Caller-supplied path — one claim folder, a directory of
            claims, or ``None`` to use config ``preprocessed_dir``.
        :return: Paths to successfully written analysis_result.json files.
        """
        self.results_root.mkdir(parents=True, exist_ok=True)

        if source is not None and _is_claim_folder(source):
            log_branch_decision(
                logger,
                branch="analysis_batch",
                outcome="SINGLE",
                reason="caller_claim_folder",
                claim=source.name,
            )
            return [self.analyze_claim(source)]

        root = self.preprocessed_root if source is None else source
        folders = _discover_claim_folders(root)
        logger.info("Discovered %d claim folders under %s", len(folders), root)
        written = self._written_analysis_outputs(folders)
        log_branch_decision(
            logger,
            branch="analysis_batch",
            outcome="COMPLETE",
            reason="soft_fail_batch",
            written=len(written),
            total=len(folders),
        )
        return written

    def _input_root_for_claim(self, claim_dir: Path) -> Path:
        """Resolve which directory holds preprocessed artifacts for ``claim_dir``.

        :param claim_dir: Caller path (raw folder or preprocessed claim folder).
        :return: Directory to read description/supporting_document artifacts from.
        """
        artifacts = self._config.preprocessing.artifacts
        if (claim_dir / artifacts.supporting_document).is_file():
            return claim_dir
        return self.preprocessed_root / claim_dir.name

    def _written_analysis_outputs(self, folders: list[Path]) -> list[Path]:
        """Analyze each claim folder; soft-fail and continue on errors.

        :param folders: Claim directories under preprocessed_dir.
        :return: Paths of analysis_result.json files written successfully.
        """
        written: list[Path] = []
        for claim_dir in folders:
            logger.info("Analyzing %s", claim_dir.name)
            try:
                _validate_claim_dir_name(claim_dir.name)
                written.append(self.analyze_claim(claim_dir))
            except Exception as exc:
                log_branch_decision(
                    logger,
                    branch="analysis_write",
                    outcome="SKIP",
                    reason="claim_failed",
                    level=logging.ERROR,
                    claim=claim_dir.name,
                    error=type(exc).__name__,
                )
                logger.exception(
                    "Failed to analyze %s: %s", claim_dir.name, type(exc).__name__
                )
        return written

    def _route_after_coverage(
        self, state: ClaimAnalysisState
    ) -> Literal[
        "classify_reason",
        "classify_pe_document",
        "classify_missed_document",
        "persist",
    ]:
        """Route by exact config.analysis.coverage label strings (not ROADMAP Title Case).

        other_label (and unknown labels after CaseClassifier allow-list) go to persist
        without reason, document classifiers, or Checker.
        """
        labels = state.get("coverage_labels") or []
        primary = labels[0] if labels else None
        coverage = self._config.analysis.coverage
        cancellation_label = coverage.labels[0]
        pe_label = coverage.labels[1]
        missed_label = coverage.labels[2]
        other_label = coverage.other_label
        if primary == cancellation_label:
            log_branch_decision(
                logger,
                branch="coverage_route",
                outcome="ROUTE",
                reason="cancellation",
                claim=state.get("claim_id"),
                next_step="classify_reason",
            )
            return "classify_reason"
        if primary == pe_label:
            log_branch_decision(
                logger,
                branch="coverage_route",
                outcome="ROUTE",
                reason="personal_effects",
                claim=state.get("claim_id"),
                next_step="classify_pe_document",
            )
            return "classify_pe_document"
        if primary == missed_label:
            log_branch_decision(
                logger,
                branch="coverage_route",
                outcome="ROUTE",
                reason="missed_departure",
                claim=state.get("claim_id"),
                next_step="classify_missed_document",
            )
            return "classify_missed_document"
        # other_label or unknown → persist-only (T-04-03 / A7)
        log_branch_decision(
            logger,
            branch="coverage_route",
            outcome="ROUTE",
            reason="other_label" if primary == other_label else "unknown_as_other",
            claim=state.get("claim_id"),
            next_step="persist",
        )
        return "persist"

    def _load_artifacts_node(self, state: ClaimAnalysisState) -> dict[str, object]:
        claim_id = state["claim_id"]
        _validate_claim_dir_name(claim_id)
        input_root = (
            Path(state["input_root"])
            if state.get("input_root")
            else self.preprocessed_root / claim_id
        )
        texts = self._loaded_claim_texts(claim_id, input_root=input_root)
        log_branch_decision(
            logger,
            branch="load_artifacts",
            outcome="LOADED",
            reason="preprocessed_texts",
            claim=claim_id,
        )
        return {
            "description_text": texts["description_text"],
            "supporting_document_text": texts["supporting_document_text"],
            "supporting_documents_text": texts["supporting_documents_text"],
        }

    def _classify_coverage_node(self, state: ClaimAnalysisState) -> dict[str, object]:
        result = self._coverage_classification(state["description_text"])
        log_branch_decision(
            logger,
            branch="classify_coverage",
            outcome="CLASSIFIED",
            reason="coverage_stage",
            claim=state.get("claim_id"),
        )
        return {"coverage_labels": list(result.labels)}

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

    def _classify_cancel_document_node(
        self, state: ClaimAnalysisState
    ) -> dict[str, object]:
        result = self._cancellation_document_classification(
            state["supporting_document_text"]
        )
        log_branch_decision(
            logger,
            branch="classify_cancel_document",
            outcome="CLASSIFIED",
            reason="cancellation_document_stage",
            claim=state.get("claim_id"),
        )
        return {"document_labels": list(result.labels)}

    def _classify_pe_document_node(
        self, state: ClaimAnalysisState
    ) -> dict[str, object]:
        result = self._personal_effects_document_classification(
            state["supporting_document_text"]
        )
        log_branch_decision(
            logger,
            branch="classify_pe_document",
            outcome="CLASSIFIED",
            reason="personal_effects_document_stage",
            claim=state.get("claim_id"),
        )
        return {"document_labels": list(result.labels)}

    def _classify_missed_document_node(
        self, state: ClaimAnalysisState
    ) -> dict[str, object]:
        result = self._missed_departure_document_classification(
            state["supporting_document_text"]
        )
        log_branch_decision(
            logger,
            branch="classify_missed_document",
            outcome="CLASSIFIED",
            reason="missed_departure_document_stage",
            claim=state.get("claim_id"),
        )
        return {"document_labels": list(result.labels)}

    def _run_checker_node(self, state: ClaimAnalysisState) -> dict[str, object]:
        results = self._checker_results(
            state["description_text"],
            state["supporting_document_text"],
        )
        log_branch_decision(
            logger,
            branch="run_checker",
            outcome="CHECKED",
            reason="containment_and_contradicts",
            claim=state.get("claim_id"),
        )
        return {
            "checker_containment": results["checker_containment"],
            "checker_contradicts": results["checker_contradicts"],
        }

    def _persist_node(self, state: ClaimAnalysisState) -> dict[str, object]:
        path = self._written_analysis_result(state)
        predicted_path = self._written_predicted_answer(state)
        log_branch_decision(
            logger,
            branch="persist",
            outcome="WROTE",
            reason="analysis_result",
            claim=state.get("claim_id"),
            path=str(path),
            predicted_answer=str(predicted_path),
        )
        return {}

    def _loaded_claim_texts(
        self, claim_id: str, *, input_root: Path | None = None
    ) -> dict[str, str]:
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
            supporting_documents_path.read_text(encoding="utf-8")
            if supporting_documents_path.is_file()
            else ""
        )
        return {
            "description_text": (claim_in / artifacts.description).read_text(
                encoding="utf-8"
            ),
            "supporting_document_text": (
                claim_in / artifacts.supporting_document
            ).read_text(encoding="utf-8"),
            "supporting_documents_text": supporting_documents_text,
        }

    def _coverage_classification(
        self, description_text: str
    ) -> ClassificationResult:
        return self._stage_classifier(self._config.analysis.coverage).classify(
            description_text
        )

    def _reason_classification(self, description_text: str) -> ClassificationResult:
        return self._stage_classifier(
            self._config.analysis.cancellation_reason
        ).classify(description_text)

    def _cancellation_document_classification(
        self, supporting_document_text: str
    ) -> ClassificationResult:
        return self._stage_classifier(
            self._config.analysis.cancellation_document
        ).classify(supporting_document_text)

    def _personal_effects_document_classification(
        self, supporting_document_text: str
    ) -> ClassificationResult:
        return self._stage_classifier(
            self._config.analysis.personal_effects_document
        ).classify(supporting_document_text)

    def _missed_departure_document_classification(
        self, supporting_document_text: str
    ) -> ClassificationResult:
        return self._stage_classifier(
            self._config.analysis.missed_departure_document
        ).classify(supporting_document_text)

    def _checker_results(
        self, description_text: str, supporting_document_text: str
    ) -> dict[str, bool]:
        """Run Checker containment and contradicts modes.

        :param description_text: Claim narrative used as the checker claim.
        :param supporting_document_text: Reference text for both modes.
        :return: Dict with checker_containment and checker_contradicts bools.
        """
        checking = self._config.checking
        checker = Checker(
            model_name=checking.model,
            containment_prompt=checking.containment_prompt,
            contradicts_prompt=checking.contradicts_prompt,
            chat_fn=self._chat_fn,
        )
        return {
            "checker_containment": checker.check(
                description_text, supporting_document_text, mode="containment"
            ),
            "checker_contradicts": checker.check(
                description_text, supporting_document_text, mode="contradicts"
            ),
        }

    def _analysis_result_payload(self, state: ClaimAnalysisState) -> dict[str, object]:
        """Build the structured analysis_result.json body from graph state.

        Numeric classifier codes stay in ``*_labels``; semantic names from
        ``config.analysis.*.label_names`` are written alongside as ``*_label_names``.
        Also records the evaluator-facing ``decision`` derived from checker flags.

        :param state: Final ClaimAnalysisState after checker (or coverage-only).
        :return: JSON-serializable analysis payload. Checker keys are omitted when
            the Checker node did not run (coverage other_label path).
        """
        analysis = self._config.analysis
        coverage_codes = list(state.get("coverage_labels") or [])
        reason_codes = list(state.get("reason_labels") or [])
        document_codes = list(state.get("document_labels") or [])
        document_stage = self._document_stage_for_coverage(coverage_codes)
        payload: dict[str, object] = {
            "claim_id": state["claim_id"],
            "coverage_labels": coverage_codes,
            "coverage_label_names": analysis.coverage.resolve_label_names(
                coverage_codes
            ),
            "reason_labels": reason_codes,
            "reason_label_names": analysis.cancellation_reason.resolve_label_names(
                reason_codes
            ),
            "document_labels": document_codes,
            "document_label_names": document_stage.resolve_label_names(document_codes),
        }
        if "checker_containment" in state:
            payload["checker_containment"] = bool(state["checker_containment"])
        if "checker_contradicts" in state:
            payload["checker_contradicts"] = bool(state["checker_contradicts"])
        decision = self._decision_from_state(state)
        payload["decision"] = decision.decision
        payload["decision_explanation"] = (
            decision.explanation
            if isinstance(decision.explanation, str)
            else None
        )
        return payload

    def _document_stage_for_coverage(
        self, coverage_codes: list[str]
    ) -> ClassificationConfig:
        """Pick the document-stage config whose label_names match the coverage path.

        :param coverage_codes: Coverage codes from the coverage classifier.
        :return: Document ClassificationConfig for semantic name resolution.
        """
        analysis = self._config.analysis
        if "2" in coverage_codes:
            return analysis.personal_effects_document
        if "3" in coverage_codes:
            return analysis.missed_departure_document
        return analysis.cancellation_document

    def _decision_from_state(self, state: ClaimAnalysisState) -> GroundTruth:
        """Derive APPROVE/DENY/UNCERTAIN for evaluator-facing predicted_answer.

        Uses checker flags when present; coverage-only (other) paths → UNCERTAIN.

        :param state: Final graph state.
        :return: GroundTruth decision written beside analysis_result.
        """
        coverage = list(state.get("coverage_labels") or [])
        other = self._config.analysis.coverage.other_label
        if coverage and set(coverage) <= {other}:
            return GroundTruth(
                decision=_DECISION_UNCERTAIN,
                explanation="coverage_other_label",
            )
        if "checker_contradicts" in state and bool(state["checker_contradicts"]):
            return GroundTruth(
                decision=_DECISION_DENY,
                explanation="checker_contradicts",
            )
        if "checker_containment" in state and not bool(state["checker_containment"]):
            return GroundTruth(
                decision=_DECISION_DENY,
                explanation="checker_missing_documentation",
            )
        if "checker_containment" in state:
            return GroundTruth(
                decision=_DECISION_APPROVE,
                explanation="checker_consistent",
            )
        return GroundTruth(
            decision=_DECISION_UNCERTAIN,
            explanation="no_checker_result",
        )

    def _written_analysis_result(self, state: ClaimAnalysisState) -> Path:
        """Persist analysis_result.json under results_dir/{claim_id}/.

        :param state: Final ClaimAnalysisState.
        :return: Path to the written analysis_result.json file.
        """
        claim_id = state["claim_id"]
        _validate_claim_dir_name(claim_id)
        path = self._analysis_result_path(claim_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._analysis_result_payload(state)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    def _written_predicted_answer(self, state: ClaimAnalysisState) -> Path:
        """Persist predicted_answer.json for the evaluator from analysis decision.

        :param state: Final ClaimAnalysisState.
        :return: Path to the written predicted_answer.json file.
        """
        claim_id = state["claim_id"]
        _validate_claim_dir_name(claim_id)
        artifacts = self._config.preprocessing.artifacts
        path = self.results_root / claim_id / artifacts.predicted_answer
        path.parent.mkdir(parents=True, exist_ok=True)
        decision = self._decision_from_state(state)
        path.write_text(decision.model_dump_json(indent=2) + "\n", encoding="utf-8")
        log_branch_decision(
            logger,
            branch="predicted_answer",
            outcome="WROTE",
            reason="analysis_decision",
            claim=claim_id,
            decision=decision.decision,
            path=str(path),
        )
        return path

    def _analysis_result_path(self, claim_id: str) -> Path:
        return (
            self.results_root
            / claim_id
            / self._config.preprocessing.artifacts.analysis_result
        )

    def _stage_classifier(self, stage: ClassificationConfig) -> CaseClassifier:
        return CaseClassifier(
            labels=list(stage.labels),
            model_name=stage.model,
            prompt=stage.prompt,
            other_label=stage.other_label,
            chat_fn=self._chat_fn,
        )
