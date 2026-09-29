"""Claims API routes — multipart intake and claim decision endpoints."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, NamedTuple

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.deps import get_claims, get_config, get_preprocessing
from api.schemas import ClaimCreated, ClaimDecision, ClaimListItem
from api.uploads import UploadTooLargeError, write_upload_stream
from compliance.branch_log import log_branch_decision
from compliance.config.settings import AppConfig
from compliance.preprocessing.claim_batch import (
    _claim_number,
    _claim_sort_key,
    _validate_claim_dir_name,
    _validate_claim_root,
)
from compliance.workflows.artifact_publication import (
    ClaimAnalysisBusyError,
    generation_mismatch,
)
from compliance.workflows.claim_pipeline import ClaimPipeline
from compliance.workflows.orchestration import analyze_claim_exclusively
from compliance.workflows.pipeline import PreprocessingPipeline

logger = logging.getLogger(__name__)

router = APIRouter()


class ArtifactRead(NamedTuple):
    """Structured result of reading one published claim artifact.

    :param payload: Parsed JSON object when the artifact is readable, else None.
    :param error: Stable reason code when unreadable, else None.
    """

    payload: dict[str, Any] | None
    error: str | None


def _next_claim_id(data_dir: Path) -> str:
    """Return the next ``claim {n}`` folder name under ``data_dir``.

    :param data_dir: Configured raw claims root.
    :return: Single-segment claim folder name starting with ``claim``.
    """
    if not data_dir.is_dir():
        return "claim 1"
    folders = [path for path in data_dir.iterdir() if path.is_dir() and path.name.lower().startswith("claim")]
    if not folders:
        return "claim 1"
    last = max(folders, key=_claim_sort_key)
    return f"claim {_claim_number(last.name) + 1}"


def _allowed_image_suffix(filename: str | None, document_formats: list[str]) -> str:
    """Validate upload filename suffix against config document_formats.

    :param filename: Client-provided image filename (may be empty).
    :param document_formats: Allowed extensions from config (with or without dots).
    :return: Normalized suffix without a leading dot.
    :raises HTTPException: 422 when filename missing or suffix not allowlisted.
    """
    if not filename or not filename.strip():
        raise HTTPException(status_code=422, detail="image filename required")
    suffix = Path(filename).suffix.lower().lstrip(".")
    allowed = {fmt.lower().lstrip(".") for fmt in document_formats}
    if suffix not in allowed:
        raise HTTPException(
            status_code=422,
            detail="image extension not in document_formats",
        )
    return suffix


def _write_claim_upload(
    *,
    claim_dir: Path,
    artifacts_description: str,
    artifacts_supporting_documents: str,
    description: UploadFile,
    supporting_documents: UploadFile,
    image: UploadFile,
    image_basename: str,
    max_file_bytes: int,
    max_request_bytes: int,
) -> None:
    """Write the multipart trio into an existing claim directory under byte caps.

    :param claim_dir: Destination claim folder (already created).
    :param artifacts_description: Configured description artifact filename.
    :param artifacts_supporting_documents: Configured supporting_documents filename.
    :param description: Uploaded claim narrative file.
    :param supporting_documents: Uploaded supporting markdown file.
    :param image: Uploaded document image.
    :param image_basename: Path-safe basename for the image file.
    :param max_file_bytes: Per-part cap from ``api.upload``.
    :param max_request_bytes: Per-request total cap from ``api.upload``.
    """
    remaining = max_request_bytes
    remaining -= write_upload_stream(
        description,
        claim_dir / artifacts_description,
        max_file_bytes=max_file_bytes,
        remaining_bytes=remaining,
    )
    remaining -= write_upload_stream(
        supporting_documents,
        claim_dir / artifacts_supporting_documents,
        max_file_bytes=max_file_bytes,
        remaining_bytes=remaining,
    )
    write_upload_stream(
        image,
        claim_dir / image_basename,
        max_file_bytes=max_file_bytes,
        remaining_bytes=remaining,
    )


def _artifact_read(
    claim_results_dir: Path,
    artifact_name: str,
    manifest_name: str,
) -> ArtifactRead:
    """Read one published artifact, enforcing the SR-005 generation contract.

    :param claim_results_dir: ``results_dir/{claim_id}/``.
    :param artifact_name: Configured artifact filename.
    :param manifest_name: Configured run_manifest filename.
    :return: Payload and/or a stable reason code.
    """
    mismatch = generation_mismatch(claim_results_dir, artifact_name, manifest_name)
    if mismatch is not None:
        return ArtifactRead(payload=None, error=mismatch)
    path = claim_results_dir / artifact_name
    if not path.is_file():
        return ArtifactRead(payload=None, error=None)
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ArtifactRead(payload=None, error="invalid_json")
    if not isinstance(raw, dict):
        return ArtifactRead(payload=None, error="invalid_json")
    return ArtifactRead(payload=raw, error=None)


def _claim_decision_from_results(
    claim_id: str,
    claim_results_dir: Path,
    *,
    analysis_name: str,
    predicted_name: str,
    manifest_name: str,
) -> ClaimDecision:
    """Assemble a ClaimDecision from published artifacts, mapping read errors to HTTP.

    :param claim_id: Claim folder segment.
    :param claim_results_dir: ``results_dir/{claim_id}/``.
    :param analysis_name: Configured analysis_result filename.
    :param predicted_name: Configured predicted_answer filename.
    :param manifest_name: Configured run_manifest filename.
    :return: ClaimDecision for a readable published generation.
    :raises HTTPException: 404 when analysis is absent; 409 on unreadable artifacts.
    """
    analysis = _artifact_read(claim_results_dir, analysis_name, manifest_name)
    if analysis.error is not None:
        raise HTTPException(status_code=409, detail=analysis.error)
    if analysis.payload is None:
        raise HTTPException(status_code=404, detail="analysis_not_found")
    predicted = _artifact_read(claim_results_dir, predicted_name, manifest_name)
    if predicted.error is not None:
        raise HTTPException(status_code=409, detail=predicted.error)
    return ClaimDecision(
        claim_id=claim_id,
        analysis_result=analysis.payload,
        predicted_answer=predicted.payload,
    )


def _claim_list_item(
    folder: Path,
    *,
    analysis_name: str,
    predicted_name: str,
    manifest_name: str,
) -> ClaimListItem:
    """Build one ClaimListItem from a results folder, collecting read errors.

    :param folder: Claim results directory under results_dir.
    :param analysis_name: Configured analysis_result filename.
    :param predicted_name: Configured predicted_answer filename.
    :param manifest_name: Configured run_manifest filename.
    :return: List item with null artifacts and reason codes when unreadable.
    """
    analysis = _artifact_read(folder, analysis_name, manifest_name)
    predicted = _artifact_read(folder, predicted_name, manifest_name)
    errors: dict[str, str] = {}
    if analysis.error is not None:
        errors[analysis_name] = analysis.error
        log_branch_decision(
            logger,
            branch="claim_list_artifact",
            outcome="UNREADABLE",
            reason=analysis.error,
            level=logging.WARNING,
            claim=folder.name,
        )
    if predicted.error is not None:
        errors[predicted_name] = predicted.error
        log_branch_decision(
            logger,
            branch="claim_list_artifact",
            outcome="UNREADABLE",
            reason=predicted.error,
            level=logging.WARNING,
            claim=folder.name,
        )
    return ClaimListItem(
        claim_id=folder.name,
        analysis_result=analysis.payload if analysis.error is None else None,
        predicted_answer=predicted.payload if predicted.error is None else None,
        errors=errors or None,
    )


@router.post("/claims", response_model=ClaimCreated, status_code=201)
def create_claim(
    description: UploadFile = File(...),
    supporting_documents: UploadFile = File(...),
    image: UploadFile = File(...),
    config: AppConfig = Depends(get_config),
) -> ClaimCreated:
    """Accept multipart claim intake and write files under config data_dir.

    Oversized parts or requests return 413 with ``file_too_large`` /
    ``request_too_large`` and leave no claim folder behind.

    :param description: Claim narrative text upload.
    :param supporting_documents: Supporting markdown upload.
    :param image: Document image whose suffix must be in document_formats.
    :param config: Injected application configuration.
    :return: Created claim identifier.
    """
    data_dir = Path(config.preprocessing.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    claim_id = _next_claim_id(data_dir)
    try:
        _validate_claim_dir_name(claim_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    _allowed_image_suffix(image.filename, config.preprocessing.document_formats)
    image_basename = Path(image.filename or "").name
    if not image_basename or image_basename in {".", ".."}:
        raise HTTPException(status_code=422, detail="image filename required")

    claim_dir = data_dir / claim_id
    try:
        claim_dir.mkdir(parents=False)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail="claim folder already exists") from exc

    try:
        _validate_claim_root(claim_dir, root=data_dir)
    except ValueError as exc:
        shutil.rmtree(claim_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    artifacts = config.preprocessing.artifacts
    image_path = claim_dir / image_basename
    claim_root = claim_dir.resolve()
    if not image_path.resolve().is_relative_to(claim_root):
        raise HTTPException(status_code=422, detail="unsafe image filename")

    try:
        _write_claim_upload(
            claim_dir=claim_dir,
            artifacts_description=artifacts.description,
            artifacts_supporting_documents=artifacts.supporting_documents,
            description=description,
            supporting_documents=supporting_documents,
            image=image,
            image_basename=image_basename,
            max_file_bytes=config.api.upload.max_file_bytes,
            max_request_bytes=config.api.upload.max_request_bytes,
        )
    except UploadTooLargeError as exc:
        # Safe: claim_dir was created moments earlier with mkdir(parents=False),
        # which fails when the path already exists, so this request owns it.
        shutil.rmtree(claim_dir, ignore_errors=True)
        raise HTTPException(status_code=413, detail=exc.reason) from exc
    logger.info("Created claim_id=%s", claim_id)
    return ClaimCreated(claim_id=claim_id)


@router.get("/claims", response_model=list[ClaimListItem])
def list_claims(
    config: AppConfig = Depends(get_config),
) -> list[ClaimListItem]:
    """List claim folders under results_dir with optional artifact payloads.

    :param config: Injected application configuration.
    :return: Claim list items ordered by numeric claim_id sort key; [] when empty.
    """
    results_root = Path(config.preprocessing.results_dir)
    if not results_root.is_dir():
        return []

    folders = [path for path in results_root.iterdir() if path.is_dir() and path.name.lower().startswith("claim")]
    folders = sorted(folders, key=_claim_sort_key)
    artifacts = config.preprocessing.artifacts
    return [
        _claim_list_item(
            folder,
            analysis_name=artifacts.analysis_result,
            predicted_name=artifacts.predicted_answer,
            manifest_name=artifacts.run_manifest,
        )
        for folder in folders
    ]


@router.get("/claims/{claim_id}", response_model=ClaimDecision)
def get_claim(
    claim_id: str,
    config: AppConfig = Depends(get_config),
) -> ClaimDecision:
    """Serve the published claim generation; never triggers analysis.

    :param claim_id: Claim folder name under results_dir.
    :param config: Injected application configuration.
    :return: Claim decision from the published generation.
    """
    try:
        _validate_claim_dir_name(claim_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    artifacts = config.preprocessing.artifacts
    claim_results = Path(config.preprocessing.results_dir) / claim_id
    return _claim_decision_from_results(
        claim_id,
        claim_results,
        analysis_name=artifacts.analysis_result,
        predicted_name=artifacts.predicted_answer,
        manifest_name=artifacts.run_manifest,
    )


@router.post("/claims/{claim_id}/analysis", response_model=ClaimDecision)
def analyze_claim(
    claim_id: str,
    config: AppConfig = Depends(get_config),
    preprocessing: PreprocessingPipeline = Depends(get_preprocessing),
    claims: ClaimPipeline = Depends(get_claims),
) -> ClaimDecision:
    """Run preprocess-then-analyse under a per-claim lock and return the decision.

    Idempotency is keyed on ``claim_id`` alone: a concurrent second request for
    the same claim is refused with 409. A repeat call after completion re-runs
    the analysis.

    :param claim_id: Raw claim folder name under config data_dir.
    :param config: Injected application configuration.
    :param preprocessing: Shared PreprocessingPipeline from lifespan.
    :param claims: Shared ClaimPipeline from lifespan.
    :return: Claim decision from the generation just published.
    """
    try:
        # Validate the raw segment before Path join — Path.name drops separators.
        _validate_claim_dir_name(claim_id)
        _validate_claim_root(
            Path(config.preprocessing.data_dir) / claim_id,
            root=Path(config.preprocessing.data_dir),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    claim_dir = Path(config.preprocessing.data_dir) / claim_id
    if not claim_dir.is_dir():
        raise HTTPException(status_code=404, detail="claim_not_found")

    try:
        analyze_claim_exclusively(claim_dir, preprocessing, claims)
    except ClaimAnalysisBusyError as exc:
        raise HTTPException(status_code=409, detail="analysis_in_progress") from exc
    except Exception as exc:
        logger.exception(
            "analyze_claim_exclusively failed claim_id=%s error=%s",
            claim_id,
            type(exc).__name__,
        )
        raise

    artifacts = config.preprocessing.artifacts
    claim_results = Path(config.preprocessing.results_dir) / claim_id
    return _claim_decision_from_results(
        claim_id,
        claim_results,
        analysis_name=artifacts.analysis_result,
        predicted_name=artifacts.predicted_answer,
        manifest_name=artifacts.run_manifest,
    )
