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
from compliance.workflows.pipeline import _validate_claim_dir_name

logger = logging.getLogger(__name__)


class ClaimAnalysisState(TypedDict, total=False):
    """LangGraph state for one-shot claim analysis.

    :param claim_id: Safe claim folder segment (validated at analyze_claim boundary).
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
        """Compile the cancellation-path StateGraph without a checkpointer.

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
        builder.add_edge("run_checker", "persist")
        builder.add_edge("persist", END)
        return builder.compile()

    def analyze_claim(self, claim_dir: Path) -> Path:
        """Run cancellation-path analysis for one claim and write analysis_result.json.

        :param claim_dir: Claim folder whose ``name`` is the safe path segment.
        :return: Path to the written analysis_result.json under results_dir.
        :raises ValueError: When ``claim_dir.name`` is not a safe single path segment.
        """
        _validate_claim_dir_name(claim_dir.name)
        log_branch_decision(
            logger,
            branch="claim_analysis",
            outcome="START",
            reason="analyze_claim",
            claim=claim_dir.name,
        )
        graph = self.build_graph()
        graph.invoke({"claim_id": claim_dir.name})
        return self._analysis_result_path(claim_dir.name)

    def _route_after_coverage(
        self, state: ClaimAnalysisState
    ) -> Literal["classify_reason"] | object:
        """Route by exact config.analysis.coverage label strings (not ROADMAP Title Case).

        PE/missed coverage labels stub to END until 04-03 fills those branches.
        """
        labels = state.get("coverage_labels") or []
        primary = labels[0] if labels else None
        coverage = self._config.analysis.coverage
        cancellation_label = coverage.labels[0]
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
        log_branch_decision(
            logger,
            branch="coverage_route",
            outcome="END",
            reason="non_cancellation_stub",
            claim=state.get("claim_id"),
            next_step=str(END),
        )
        return END

    def _load_artifacts_node(self, state: ClaimAnalysisState) -> dict[str, object]:
        claim_id = state["claim_id"]
        _validate_claim_dir_name(claim_id)
        texts = self._loaded_claim_texts(claim_id)
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
        log_branch_decision(
            logger,
            branch="persist",
            outcome="WROTE",
            reason="analysis_result",
            claim=state.get("claim_id"),
            path=str(path),
        )
        return {}

    def _loaded_claim_texts(self, claim_id: str) -> dict[str, str]:
        """Read description and supporting markdown from preprocessed_dir.

        :param claim_id: Validated claim folder segment.
        :return: Dict with description_text, supporting_document_text,
            supporting_documents_text.
        """
        artifacts = self._config.preprocessing.artifacts
        claim_in = self.preprocessed_root / claim_id
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

        :param state: Final ClaimAnalysisState after checker.
        :return: JSON-serializable analysis payload.
        """
        return {
            "claim_id": state["claim_id"],
            "coverage_labels": list(state.get("coverage_labels") or []),
            "reason_labels": list(state.get("reason_labels") or []),
            "document_labels": list(state.get("document_labels") or []),
            "checker_containment": bool(state.get("checker_containment", False)),
            "checker_contradicts": bool(state.get("checker_contradicts", False)),
        }

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
