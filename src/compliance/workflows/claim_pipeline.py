from __future__ import annotations

import json
import logging
import re
from datetime import date
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
from compliance.preprocessing.markdown import MarkdownPreprocessor
from compliance.workflows.pipeline import _is_claim_folder, _validate_claim_dir_name
from compliance.workflows.predicted_answer_io import write_analysis_predicted_answer

logger = logging.getLogger(__name__)

_DECISION_APPROVE = "APPROVE"
_DECISION_DENY = "DENY"
_DECISION_UNCERTAIN = "UNCERTAIN"

# Calendar-date token patterns (order: ISO first, then day-first numerics, then English).
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DATE_DMY = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")
_DATE_DMONTH_Y = re.compile(
    r"\b(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+(\d{4})\b",
    re.IGNORECASE,
)
_DATE_MONTH_D_Y = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+(\d{1,2}),?\s+(\d{4})\b",
    re.IGNORECASE,
)
_MONTH_NUM: dict[str, int] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


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
    :param departure_within_days: True when departure is within the configured
        day window of reference today (deterministic UNCERTAIN).
    :param multiple_document_dates: True when OCR supporting_document text has
        two or more distinct calendar days (deterministic UNCERTAIN).
    :param human_in_the_loop: True when OCR metadata already flagged review, or any
        classifier returned ``False`` (confident none-of-the-above).
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
    departure_within_days: bool
    multiple_document_dates: bool
    human_in_the_loop: bool


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_calendar_date(raw: str) -> date | None:
    """Parse the first calendar date from a booking/OCR string.

    Supports ISO ``YYYY-MM-DD``, day-first ``DD/MM/YYYY`` (also ``-`` / ``.``),
    and English month names. Trailing time suffixes are ignored (ISO match first).

    :param raw: Free-text value that may contain a date.
    :return: Parsed ``date``, or None when unparseable.
    """
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    match = _DATE_ISO.search(text)
    if match:
        return _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    match = _DATE_DMONTH_Y.search(text)
    if match:
        return _safe_date(
            int(match.group(3)),
            _MONTH_NUM[match.group(2).lower()],
            int(match.group(1)),
        )
    match = _DATE_MONTH_D_Y.search(text)
    if match:
        return _safe_date(
            int(match.group(3)),
            _MONTH_NUM[match.group(1).lower()],
            int(match.group(2)),
        )
    match = _DATE_DMY.search(text)
    if match:
        return _safe_date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    return None


def _unique_calendar_dates(text: str) -> set[date]:
    """Collect distinct calendar days mentioned in free text.

    :param text: OCR or narrative text that may contain multiple date tokens.
    :return: Set of successfully parsed calendar dates.
    """
    if not text:
        return set()
    found: set[date] = set()
    for match in _DATE_ISO.finditer(text):
        parsed = _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if parsed is not None:
            found.add(parsed)
    for match in _DATE_DMONTH_Y.finditer(text):
        parsed = _safe_date(
            int(match.group(3)),
            _MONTH_NUM[match.group(2).lower()],
            int(match.group(1)),
        )
        if parsed is not None:
            found.add(parsed)
    for match in _DATE_MONTH_D_Y.finditer(text):
        parsed = _safe_date(
            int(match.group(3)),
            _MONTH_NUM[match.group(1).lower()],
            int(match.group(2)),
        )
        if parsed is not None:
            found.add(parsed)
    for match in _DATE_DMY.finditer(text):
        parsed = _safe_date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        if parsed is not None:
            found.add(parsed)
    return found


def _booking_fields(supporting_documents_text: str) -> dict[str, str]:
    """Extract canonical BookingData fields from booking markdown.

    :param supporting_documents_text: ``supporting_documents.md`` contents.
    :return: Dict of BookingData field name → string value.
    """
    if not supporting_documents_text:
        return {}
    return MarkdownPreprocessor().preprocess(supporting_documents_text)


def _reference_today(supporting_documents_text: str, *, fallback: date) -> date:
    """Resolve reference today from booking ``current_date``, else ``fallback``.

    :param supporting_documents_text: Booking markdown text.
    :param fallback: Clock date when booking has no parseable current_date.
    :return: Calendar date used as the proximity reference.
    """
    fields = _booking_fields(supporting_documents_text)
    current_raw = fields.get("current_date")
    if current_raw:
        parsed = _parse_calendar_date(str(current_raw))
        if parsed is not None:
            return parsed
    return fallback


def _departure_within_days(
    *,
    supporting_documents_text: str,
    description_text: str,
    today: date,
    within_days: int,
) -> bool:
    """True when departure is within ``within_days`` of ``today`` (inclusive).

    Departure source priority: booking markdown ``departure`` via
    ``MarkdownPreprocessor``; else first parseable date in ``description_text``.
    Unparseable departure → False.

    :param supporting_documents_text: Booking/internal markdown.
    :param description_text: Claim narrative fallback for departure date.
    :param today: Reference today (injected; pipeline resolves from booking).
    :param within_days: Inclusive absolute day threshold from config.
    :return: Whether proximity UNCERTAIN should fire.
    """
    fields = _booking_fields(supporting_documents_text)
    departure: date | None = None
    raw_dep = fields.get("departure")
    if raw_dep:
        departure = _parse_calendar_date(str(raw_dep))
    if departure is None:
        departure = _parse_calendar_date(description_text)
    if departure is None:
        return False
    return abs((departure - today).days) <= within_days


def _has_multiple_document_dates(supporting_document_text: str) -> bool:
    """True when medical OCR text contains two or more distinct calendar days.

    :param supporting_document_text: ``supporting_document.md`` OCR markdown only.
    :return: Whether multiple-document-dates UNCERTAIN should fire.
    """
    return len(_unique_calendar_dates(supporting_document_text)) >= 2


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

        ``other_label`` / ``False`` (and unknown labels after CaseClassifier allow-list)
        go to persist without reason, document classifiers, or Checker.
        """
        labels = state.get("coverage_labels") or []
        primary = labels[0] if labels else None
        coverage = self._config.analysis.coverage
        positive = coverage.positive_labels()
        cancellation_label = positive[0]
        pe_label = positive[1]
        missed_label = positive[2]
        abstention = coverage.abstention_labels()
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
        # abstention (None / False) or unknown → persist-only (T-04-03 / A7)
        log_branch_decision(
            logger,
            branch="coverage_route",
            outcome="ROUTE",
            reason="other_label" if primary in abstention else "unknown_as_other",
            claim=state.get("claim_id"),
            next_step="persist",
        )
        return "persist"

    def _load_artifacts_node(self, state: ClaimAnalysisState) -> dict[str, object]:
        claim_id = state["claim_id"]
        _validate_claim_dir_name(claim_id)
        input_root = self._claim_input_root(state)
        texts = self._loaded_claim_texts(claim_id, input_root=input_root)
        has_signature = self._document_has_signature(claim_id, input_root=input_root)
        human_in_the_loop = self._document_human_in_the_loop(
            claim_id, input_root=input_root
        )
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
        signature_check = self._signature_check_result(state)
        early_uncertain = bool(results.get("departure_within_days")) or bool(
            results.get("multiple_document_dates")
        )
        reason = (
            "date_uncertain_skip_llm"
            if early_uncertain
            else "containment_contradicts_identity_signature_healthy"
        )
        log_branch_decision(
            logger,
            branch="run_checker",
            outcome="CHECKED",
            reason=reason,
            claim=state.get("claim_id"),
            identity_check=results.get("identity_check"),
            identity_unclear=results.get("identity_unclear"),
            signature_check=signature_check,
            healthy_check=results.get("healthy_check"),
            departure_within_days=results.get("departure_within_days"),
            multiple_document_dates=results.get("multiple_document_dates"),
        )
        payload: dict[str, object] = {
            "departure_within_days": results["departure_within_days"],
            "multiple_document_dates": results["multiple_document_dates"],
            "signature_check": signature_check,
        }
        if not early_uncertain:
            payload["checker_containment"] = results["checker_containment"]
            payload["checker_contradicts"] = results["checker_contradicts"]
            payload["identity_check"] = results["identity_check"]
            payload["identity_unclear"] = results["identity_unclear"]
            payload["healthy_check"] = results["healthy_check"]
        return payload

    def _persist_node(self, state: ClaimAnalysisState) -> dict[str, object]:
        hitl = self._resolved_human_in_the_loop(state)
        if hitl and self._classifier_returned_false(state):
            self._persist_human_in_the_loop_metadata(state)
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
            human_in_the_loop=hitl,
        )
        return {"human_in_the_loop": hitl}

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

    def _document_human_in_the_loop(
        self, claim_id: str, *, input_root: Path | None = None
    ) -> bool:
        """Read human_in_the_loop from document_metadata.json (any document True).

        :param claim_id: Validated claim folder segment.
        :param input_root: Directory holding artifacts; defaults to preprocessed claim.
        :return: True when any metadata entry already requires human review.
        """
        documents = self._document_metadata_entries(claim_id, input_root=input_root)
        return any(bool(entry.get("human_in_the_loop")) for entry in documents)

    @staticmethod
    def _classifier_returned_false(state: ClaimAnalysisState) -> bool:
        """True when any stage classifier selected the confident-negative ``False`` label.

        :param state: Graph state with coverage / reason / document label codes.
        :return: Whether ``False`` appears in any classifier output.
        """
        for key in ("coverage_labels", "reason_labels", "document_labels"):
            if "False" in (state.get(key) or []):
                return True
        return False

    def _resolved_human_in_the_loop(self, state: ClaimAnalysisState) -> bool:
        """HITL from preprocess metadata or any classifier ``False`` label.

        :param state: Final (or mid-pipeline) graph state.
        :return: Whether a human should review the claim.
        """
        if bool(state.get("human_in_the_loop")):
            return True
        return self._classifier_returned_false(state)

    def _persist_human_in_the_loop_metadata(self, state: ClaimAnalysisState) -> None:
        """Set ``human_in_the_loop: true`` on every document_metadata entry.

        :param state: Graph state with claim_id and optional input_root.
        """
        claim_id = state["claim_id"]
        claim_in = self._claim_input_root(state)
        artifacts = self._config.preprocessing.artifacts
        path = claim_in / artifacts.document_metadata
        entries = self._document_metadata_entries(claim_id, input_root=claim_in)
        if not entries:
            entries = [{"source_file": "", "has_signature": False}]
        updated = [{**entry, "human_in_the_loop": True} for entry in entries]
        path.write_text(
            json.dumps({"documents": updated}, indent=2) + "\n",
            encoding="utf-8",
        )
        log_branch_decision(
            logger,
            branch="human_in_the_loop",
            outcome="FLAGGED",
            reason="classifier_false",
            claim=claim_id,
            path=str(path),
        )

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
        coverage_labels = self._config.analysis.coverage.positive_labels()
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
        """Run deterministic date checks, then Checker LLM modes when needed.

        Always computes ``departure_within_days`` and ``multiple_document_dates``.
        When either is True, returns early without constructing ``Checker`` /
        calling chat — LLM keys are omitted from the result dict.

        Identity compares the passenger ``name`` in ``supporting_documents.md``
        (booking / internal record) against the patient/subject name in
        ``supporting_document.md`` (Docling OCR). Skipped when the classified
        document is not medical certificate / hospital admission.

        :param description_text: Claim narrative for containment / contradicts.
        :param supporting_document_text: Medical/supporting OCR markdown.
        :param supporting_documents_text: Booking/internal markdown with ``name``.
        :param run_identity: When False, identity passes without an LLM call.
        :return: Dict with date flags and optionally checker LLM results.
        """
        checking = self._config.checking
        today = _reference_today(supporting_documents_text, fallback=date.today())
        departure_flag = _departure_within_days(
            supporting_documents_text=supporting_documents_text,
            description_text=description_text,
            today=today,
            within_days=checking.departure_uncertain_within_days,
        )
        multiple_dates_flag = _has_multiple_document_dates(supporting_document_text)
        date_flags = {
            "departure_within_days": departure_flag,
            "multiple_document_dates": multiple_dates_flag,
        }
        if departure_flag or multiple_dates_flag:
            return date_flags

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
            **date_flags,
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
        if "departure_within_days" in state:
            payload["departure_within_days"] = bool(state["departure_within_days"])
        if "multiple_document_dates" in state:
            payload["multiple_document_dates"] = bool(state["multiple_document_dates"])
        if "document_labels" in state:
            payload["checker_missing_documentation"] = self._is_missing_documentation(
                state
            )
        hitl = self._resolved_human_in_the_loop(state)
        payload["human_in_the_loop"] = hitl
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
        coverage_labels = analysis.coverage.positive_labels()
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
        coverage_labels = analysis.coverage.positive_labels()
        stage = self._document_stage_for_coverage(coverage_codes)
        stage_positive = set(stage.positive_labels())

        if len(coverage_labels) > 1 and coverage_labels[1] in coverage_codes:
            acceptable = list(required.personal_effects) or list(stage_positive)
            return set(acceptable)
        if len(coverage_labels) > 2 and coverage_labels[2] in coverage_codes:
            acceptable = list(required.missed_departure) or list(stage_positive)
            return set(acceptable)

        reason_abstention = analysis.cancellation_reason.abstention_labels()
        reason_codes = [
            code
            for code in (state.get("reason_labels") or [])
            if code not in reason_abstention
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
        return stage_positive

    def _classified_document_codes(self, state: ClaimAnalysisState) -> set[str]:
        """Return non-abstention document codes from the document classifier stage.

        :param state: Graph state with document_labels.
        :return: Classified document codes excluding ``False`` / ``other_label``.
        """
        coverage_codes = list(state.get("coverage_labels") or [])
        stage = self._document_stage_for_coverage(coverage_codes)
        abstention = stage.abstention_labels()
        return {
            code
            for code in (state.get("document_labels") or [])
            if code not in abstention
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

        Precedence (locked):
        1. Coverage abstention → UNCERTAIN ``coverage_false_label``
        2. ``departure_within_days`` → UNCERTAIN (before DENY)
        3. ``multiple_document_dates`` → UNCERTAIN (before DENY)
        4. ``_violated_checkers`` non-empty → DENY
        5. ``identity_unclear`` → UNCERTAIN
        6. APPROVE ``checker_consistent``

        Date UNCERTAIN flags sit before DENY so an early-exit path cannot fall
        through to signature/identity deny when proximity/dating fired.
        Missing documentation uses required document types for the coverage/reason
        path. Containment is recorded but does not drive DENY.

        :param state: Final graph state.
        :return: GroundTruth decision written beside analysis_result.
        """
        coverage = list(state.get("coverage_labels") or [])
        abstention = self._config.analysis.coverage.abstention_labels()
        if coverage and set(coverage) <= abstention:
            return GroundTruth(
                decision=_DECISION_UNCERTAIN,
                explanation="coverage_false_label",
            )
        if bool(state.get("departure_within_days")):
            return GroundTruth(
                decision=_DECISION_UNCERTAIN,
                explanation="departure_within_days",
            )
        if bool(state.get("multiple_document_dates")):
            return GroundTruth(
                decision=_DECISION_UNCERTAIN,
                explanation="multiple_document_dates",
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

        Includes ``human_in_the_loop`` from preprocess metadata and/or analysis
        classifier ``False`` abstention so operators see the flag on the prediction.

        :param state: Final ClaimAnalysisState.
        :return: Path to the written predicted_answer.json file.
        """
        claim_id = state["claim_id"]
        _validate_claim_dir_name(claim_id)
        path = self._predicted_answer_path(claim_id)
        return write_analysis_predicted_answer(
            path, self._predicted_answer_decision(state)
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
        return (
            self.results_root
            / claim_id
            / self._config.preprocessing.artifacts.predicted_answer
        )

    def _claim_input_root(self, state: ClaimAnalysisState) -> Path:
        """Resolve the artifact directory for ``state`` (input_root or preprocessed).

        :param state: Graph state with claim_id and optional input_root string.
        :return: Directory holding description / supporting_document artifacts.
        """
        if state.get("input_root"):
            return Path(state["input_root"])
        return self.preprocessed_root / state["claim_id"]

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
