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
from compliance.preprocessing.document import vision_ocr_text
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
    :param identity_check: True when booking name matches patient/subject name,
        or identity was skipped (non-medical document).
    :param identity_unclear: True when OCR has no clear patient/subject name field.
    :param document_has_signature: True when document_metadata reports has_signature.
    :param signature_check: True when signature requirement passes (or N/A).
    :param healthy_check: True when supporting_document asserts patient is healthy.
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
    identity_check: bool
    identity_unclear: bool
    document_has_signature: bool
    signature_check: bool
    healthy_check: bool


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
        has_signature = self._document_has_signature(claim_id, input_root=input_root)
        log_branch_decision(
            logger,
            branch="load_artifacts",
            outcome="LOADED",
            reason="preprocessed_texts",
            claim=claim_id,
            document_has_signature=has_signature,
        )
        return {
            "description_text": texts["description_text"],
            "supporting_document_text": texts["supporting_document_text"],
            "supporting_documents_text": texts["supporting_documents_text"],
            "document_has_signature": has_signature,
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
        run_identity = self._identity_required_applies(state)
        results = self._checker_results(
            state["description_text"],
            state["supporting_document_text"],
            state.get("supporting_documents_text") or "",
            run_identity=run_identity,
        )
        updates: dict[str, object] = {}
        if run_identity and results["identity_unclear"]:
            refreshed = self._identity_after_ocr_retry(state)
            if refreshed is not None:
                supporting_text, identity_check, identity_unclear = refreshed
                results = {
                    **results,
                    "identity_check": identity_check,
                    "identity_unclear": identity_unclear,
                }
                updates["supporting_document_text"] = supporting_text
        signature_check = self._signature_check_result(state)
        log_branch_decision(
            logger,
            branch="run_checker",
            outcome="CHECKED",
            reason="containment_contradicts_identity_signature_healthy",
            claim=state.get("claim_id"),
            identity_check=results["identity_check"],
            identity_unclear=results["identity_unclear"],
            signature_check=signature_check,
            healthy_check=results["healthy_check"],
        )
        return {
            **updates,
            "checker_containment": results["checker_containment"],
            "checker_contradicts": results["checker_contradicts"],
            "identity_check": results["identity_check"],
            "identity_unclear": results["identity_unclear"],
            "signature_check": signature_check,
            "healthy_check": results["healthy_check"],
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

    def _document_has_signature(
        self, claim_id: str, *, input_root: Path | None = None
    ) -> bool:
        """Read has_signature from document_metadata.json (any document True).

        :param claim_id: Validated claim folder segment.
        :param input_root: Directory holding artifacts; defaults to preprocessed claim.
        :return: True when any metadata entry has ``has_signature`` true.
        """
        documents = self._document_metadata_entries(claim_id, input_root=input_root)
        return any(bool(entry.get("has_signature")) for entry in documents)

    def _document_metadata_entries(
        self, claim_id: str, *, input_root: Path | None = None
    ) -> list[dict[str, object]]:
        """Load document metadata entries for a claim folder.

        :param claim_id: Validated claim folder segment.
        :param input_root: Directory holding artifacts; defaults to preprocessed claim.
        :return: List of metadata dicts (empty when missing/invalid).
        """
        artifacts = self._config.preprocessing.artifacts
        claim_in = input_root if input_root is not None else self.preprocessed_root / claim_id
        path = claim_in / artifacts.document_metadata
        if not path.is_file():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        documents = raw.get("documents") if isinstance(raw, dict) else None
        if not isinstance(documents, list):
            return []
        return [entry for entry in documents if isinstance(entry, dict)]

    def _claim_input_root(self, state: ClaimAnalysisState) -> Path:
        """Resolve the preprocessed claim folder for the current state.

        :param state: Graph state with claim_id and optional input_root.
        :return: Absolute claim folder path.
        """
        claim_id = state["claim_id"]
        if state.get("input_root"):
            return Path(state["input_root"])
        return self.preprocessed_root / claim_id

    def _claim_document_image(self, claim_in: Path, source_file: str | None) -> Path | None:
        """Find a preprocessed document image for vision OCR retry.

        :param claim_in: Preprocessed claim folder.
        :param source_file: Preferred basename from document_metadata (may be raster).
        :return: Path to an existing image, or None.
        """
        suffixes = (".png", ".jpg", ".jpeg", ".webp")
        if source_file:
            stem = Path(source_file).stem
            for suffix in suffixes:
                candidate = claim_in / f"{stem}{suffix}"
                if candidate.is_file():
                    return candidate
            direct = claim_in / source_file
            if direct.is_file() and direct.suffix.lower() in suffixes:
                return direct
        for path in sorted(claim_in.iterdir()):
            if path.is_file() and path.suffix.lower() in suffixes:
                return path
        return None

    def _identity_after_ocr_retry(
        self, state: ClaimAnalysisState
    ) -> tuple[str, bool, bool] | None:
        """Vision-OCR once when identity is unclear and preprocess did not retry.

        :param state: Graph state after the first identity check returned unclear.
        :return: ``(new_supporting_text, identity_check, identity_unclear)`` when a
            retry ran; otherwise ``None``.
        """
        ocr_retry = self._config.ocr_retry
        if not ocr_retry.enabled or not ocr_retry.on_identity_unclear:
            return None
        if not ocr_retry.model or not ocr_retry.prompt.strip():
            return None

        claim_in = self._claim_input_root(state)
        entries = self._document_metadata_entries(
            state["claim_id"], input_root=claim_in
        )
        if any(bool(entry.get("retry_used")) for entry in entries):
            log_branch_decision(
                logger,
                branch="ocr_retry",
                outcome="SKIP",
                reason="already_retried",
                claim=state.get("claim_id"),
            )
            return None

        source_file = None
        if entries:
            raw_source = entries[0].get("source_file")
            source_file = str(raw_source) if raw_source else None
        image_path = self._claim_document_image(claim_in, source_file)
        if image_path is None:
            log_branch_decision(
                logger,
                branch="ocr_retry",
                outcome="SKIP",
                reason="no_document_image",
                claim=state.get("claim_id"),
            )
            return None

        chat_fn = self._chat_fn
        if chat_fn is None:
            import ollama

            chat_fn = ollama.chat

        log_branch_decision(
            logger,
            branch="ocr_retry",
            outcome="START",
            reason="identity_unclear",
            claim=state.get("claim_id"),
            file=image_path.name,
            model=ocr_retry.model,
        )
        try:
            retry_text = vision_ocr_text(
                image_path,
                model=ocr_retry.model,
                prompt=ocr_retry.prompt,
                chat_fn=chat_fn,
            )
        except Exception as exc:
            log_branch_decision(
                logger,
                branch="ocr_retry",
                outcome="ERROR",
                reason=type(exc).__name__,
                level=logging.WARNING,
                claim=state.get("claim_id"),
                file=image_path.name,
            )
            return None

        supporting_text = (
            f"# Supporting document\n\n## Document: 1\n{retry_text.strip()}\n"
        )
        self._persist_ocr_retry_artifacts(
            claim_in,
            supporting_text=supporting_text,
            entries=entries,
            retry_model=ocr_retry.model,
        )
        checking = self._config.checking
        checker = Checker(
            model_name=checking.model,
            containment_prompt=checking.containment_prompt,
            contradicts_prompt=checking.contradicts_prompt,
            identity_prompt=checking.identity_prompt,
            healthy_prompt=checking.healthy_prompt,
            chat_fn=self._chat_fn,
        )
        status = checker.check_identity(
            state.get("supporting_documents_text") or "",
            supporting_text,
        )
        log_branch_decision(
            logger,
            branch="ocr_retry",
            outcome="SUCCESS",
            reason="identity_recheck",
            claim=state.get("claim_id"),
            identity_status=status,
        )
        return supporting_text, status == "match", status == "unclear"

    def _persist_ocr_retry_artifacts(
        self,
        claim_in: Path,
        *,
        supporting_text: str,
        entries: list[dict[str, object]],
        retry_model: str,
    ) -> None:
        """Write refreshed OCR text and retry flags under the claim folder.

        :param claim_in: Preprocessed claim folder.
        :param supporting_text: New supporting_document.md body.
        :param entries: Existing document_metadata entries (may be empty).
        :param retry_model: Vision model name used for the retry.
        """
        artifacts = self._config.preprocessing.artifacts
        (claim_in / artifacts.supporting_document).write_text(
            supporting_text, encoding="utf-8"
        )
        if not entries:
            entries = [{"source_file": "", "has_signature": False}]
        updated = []
        for entry in entries:
            updated.append(
                {
                    **entry,
                    "retry_used": True,
                    "retry_model": retry_model,
                }
            )
        (claim_in / artifacts.document_metadata).write_text(
            json.dumps({"documents": updated}, indent=2) + "\n",
            encoding="utf-8",
        )

    def _signature_required_applies(self, state: ClaimAnalysisState) -> bool:
        """True when a cancellation medical/hospital document requires a signature.

        Codes are stage-local (cancellation_document ``"1"``/``"4"``), so this
        only applies on the trip-cancellation coverage path.

        :param state: Graph state with coverage and document_labels.
        :return: Whether medical certificate / hospital admission codes apply.
        """
        if not self._is_cancellation_coverage(state):
            return False
        required = set(
            self._config.analysis.required_documents.signature_required_codes
        )
        if not required:
            return False
        return bool(self._classified_document_codes(state) & required)

    def _identity_required_applies(self, state: ClaimAnalysisState) -> bool:
        """True when a cancellation medical/hospital document requires identity.

        Codes are stage-local (cancellation_document ``"1"``/``"4"``), so this
        only applies on the trip-cancellation coverage path — not PE/missed
        docs that reuse numeric codes.

        :param state: Graph state with coverage and document_labels.
        :return: Whether medical certificate / hospital admission codes apply.
        """
        if not self._is_cancellation_coverage(state):
            return False
        required = set(
            self._config.analysis.required_documents.identity_required_codes
        )
        if not required:
            return False
        return bool(self._classified_document_codes(state) & required)

    def _is_cancellation_coverage(self, state: ClaimAnalysisState) -> bool:
        """True when coverage primary label is trip cancellation / rescheduling.

        :param state: Graph state with coverage_labels.
        :return: Whether the cancellation document taxonomy applies.
        """
        coverage_labels = self._config.analysis.coverage.labels
        if not coverage_labels:
            return False
        coverage_codes = set(state.get("coverage_labels") or [])
        return coverage_labels[0] in coverage_codes

    def _signature_check_result(self, state: ClaimAnalysisState) -> bool:
        """Pass when signature is not required, or document_has_signature is True.

        :param state: Graph state after load + document classification.
        :return: True when the signature gate passes.
        """
        if not self._signature_required_applies(state):
            return True
        return bool(state.get("document_has_signature"))

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
        self,
        description_text: str,
        supporting_document_text: str,
        supporting_documents_text: str,
        *,
        run_identity: bool,
    ) -> dict[str, bool]:
        """Run Checker containment, contradicts, identity, and healthy modes.

        Identity compares the passenger ``name`` in ``supporting_documents.md``
        (booking / internal record) against the patient/subject name in
        ``supporting_document.md`` (Docling OCR). Skipped when the classified
        document is not medical certificate / hospital admission.

        :param description_text: Claim narrative for containment / contradicts.
        :param supporting_document_text: Medical/supporting OCR markdown.
        :param supporting_documents_text: Booking/internal markdown with ``name``.
        :param run_identity: When False, identity passes without an LLM call.
        :return: Dict with checker_containment, checker_contradicts, identity_check,
            identity_unclear, healthy_check.
        """
        checking = self._config.checking
        checker = Checker(
            model_name=checking.model,
            containment_prompt=checking.containment_prompt,
            contradicts_prompt=checking.contradicts_prompt,
            identity_prompt=checking.identity_prompt,
            healthy_prompt=checking.healthy_prompt,
            chat_fn=self._chat_fn,
        )
        containment = checker.check(
            description_text, supporting_document_text, mode="containment"
        )
        contradicts = checker.check(
            description_text, supporting_document_text, mode="contradicts"
        )
        if run_identity:
            identity_status = checker.check_identity(
                supporting_documents_text, supporting_document_text
            )
            identity_check = identity_status == "match"
            identity_unclear = identity_status == "unclear"
        else:
            identity_check = True
            identity_unclear = False
        healthy = checker.check(
            description_text,
            supporting_document_text,
            mode="healthy",
        )
        return {
            "checker_containment": containment,
            "checker_contradicts": contradicts,
            "identity_check": identity_check,
            "identity_unclear": identity_unclear,
            "healthy_check": healthy,
        }

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
        document_stage = self._document_stage_for_coverage(coverage_codes)
        payload: dict[str, object] = {
            "claim_id": state["claim_id"],
            "coverage_labels": analysis.coverage.resolve_label_names(coverage_codes),
            "coverage_label_codes": coverage_codes,
            "reason_labels": analysis.cancellation_reason.resolve_label_names(
                reason_codes
            ),
            "reason_label_codes": reason_codes,
            "document_labels": document_stage.resolve_label_names(document_codes),
            "document_label_codes": document_codes,
        }
        if "checker_containment" in state:
            payload["checker_containment"] = bool(state["checker_containment"])
        if "checker_contradicts" in state:
            payload["checker_contradicts"] = bool(state["checker_contradicts"])
        if "identity_check" in state:
            payload["identity_check"] = bool(state["identity_check"])
        if "identity_unclear" in state:
            payload["identity_unclear"] = bool(state["identity_unclear"])
        if "document_has_signature" in state:
            payload["document_has_signature"] = bool(state["document_has_signature"])
        if "signature_check" in state:
            payload["signature_check"] = bool(state["signature_check"])
        if "healthy_check" in state:
            payload["healthy_check"] = bool(state["healthy_check"])
        if "document_labels" in state:
            payload["checker_missing_documentation"] = self._is_missing_documentation(
                state
            )
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
        coverage_labels = analysis.coverage.labels
        if len(coverage_labels) > 1 and coverage_labels[1] in coverage_codes:
            return analysis.personal_effects_document
        if len(coverage_labels) > 2 and coverage_labels[2] in coverage_codes:
            return analysis.missed_departure_document
        return analysis.cancellation_document

    def _acceptable_document_codes(self, state: ClaimAnalysisState) -> set[str]:
        """Return document codes allowed for this claim's coverage / reason path.

        :param state: Graph state with coverage and reason label codes.
        :return: Acceptable document-type codes from ``required_documents`` config
            (falls back to the document-stage label list when a mapping is empty).
        """
        analysis = self._config.analysis
        required = analysis.required_documents
        coverage_codes = list(state.get("coverage_labels") or [])
        coverage_labels = analysis.coverage.labels
        stage = self._document_stage_for_coverage(coverage_codes)

        if len(coverage_labels) > 1 and coverage_labels[1] in coverage_codes:
            acceptable = list(required.personal_effects) or list(stage.labels)
            return set(acceptable)
        if len(coverage_labels) > 2 and coverage_labels[2] in coverage_codes:
            acceptable = list(required.missed_departure) or list(stage.labels)
            return set(acceptable)

        reason_codes = [
            code
            for code in (state.get("reason_labels") or [])
            if code != analysis.cancellation_reason.other_label
        ]
        by_reason = required.cancellation_by_reason
        if reason_codes and by_reason:
            acceptable: set[str] = set()
            for reason in reason_codes:
                acceptable.update(by_reason.get(reason, []))
            if acceptable:
                return acceptable
        if by_reason:
            return {code for codes in by_reason.values() for code in codes}
        return set(stage.labels)

    def _classified_document_codes(self, state: ClaimAnalysisState) -> set[str]:
        """Return non-other document codes from the document classifier stage.

        :param state: Graph state with document_labels.
        :return: Classified document codes excluding the stage other_label.
        """
        coverage_codes = list(state.get("coverage_labels") or [])
        stage = self._document_stage_for_coverage(coverage_codes)
        return {
            code
            for code in (state.get("document_labels") or [])
            if code != stage.other_label
        }

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
        ``identity_check`` False means a clear mismatch / redaction on a medical
        document → DENY. ``identity_unclear`` is handled separately as UNCERTAIN.
        ``signature_check`` False means a medical certificate / hospital admission
        lacks ``has_signature`` in ``document_metadata.json`` → DENY.
        ``healthy_check`` True means ``supporting_document.md`` asserts the patient
        is healthy / fit → DENY.

        :param state: Final graph state after Checker (or coverage-only).
        :return: Ordered list of violated keys that drive DENY.
        """
        violated: list[str] = []
        if self._is_missing_documentation(state):
            violated.append("checker_missing_documentation")
        if (
            "identity_check" in state
            and not bool(state["identity_check"])
            and not bool(state.get("identity_unclear"))
        ):
            violated.append("identity_check")
        if "signature_check" in state and not bool(state["signature_check"]):
            violated.append("signature_check")
        if "healthy_check" in state and bool(state["healthy_check"]):
            violated.append("healthy_check")
        if "checker_contradicts" in state and bool(state["checker_contradicts"]):
            violated.append("checker_contradicts")
        return violated

    def _decision_from_state(self, state: ClaimAnalysisState) -> GroundTruth:
        """Derive APPROVE/DENY/UNCERTAIN for evaluator-facing predicted_answer.

        Missing documentation uses required document types for the coverage/reason
        path. Containment is recorded but does not drive DENY. Coverage-only
        (other) paths → UNCERTAIN. Identity with no clear patient field → UNCERTAIN
        when no hard deny rules fired. On DENY, ``explanation`` lists violated keys.

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
        violated = self._violated_checkers(state)
        if violated:
            return GroundTruth(
                decision=_DECISION_DENY,
                explanation=",".join(violated),
            )
        if "identity_unclear" in state and bool(state["identity_unclear"]):
            return GroundTruth(
                decision=_DECISION_UNCERTAIN,
                explanation="identity_unclear",
            )
        return GroundTruth(
            decision=_DECISION_APPROVE,
            explanation="checker_consistent",
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
