"""Claims API routes — multipart intake and claim decision endpoints."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.deps import get_claims, get_config, get_preprocessing
from api.schemas import ClaimCreated, ClaimDecision, ClaimListItem
from compliance.config.settings import AppConfig
from compliance.preprocessing.claim_batch import (
    _claim_number,
    _claim_sort_key,
    _validate_claim_dir_name,
)
from compliance.workflows.claim_pipeline import ClaimPipeline
from compliance.workflows.orchestration import process_then_analyze
from compliance.workflows.pipeline import PreprocessingPipeline

logger = logging.getLogger(__name__)

router = APIRouter()


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
) -> None:
    """Write the multipart trio into an existing claim directory.

    :param claim_dir: Destination claim folder (already created).
    :param artifacts_description: Configured description artifact filename.
    :param artifacts_supporting_documents: Configured supporting_documents filename.
    :param description: Uploaded claim narrative file.
    :param supporting_documents: Uploaded supporting markdown file.
    :param image: Uploaded document image.
    :param image_basename: Path-safe basename for the image file.
    """
    (claim_dir / artifacts_description).write_bytes(description.file.read())
    (claim_dir / artifacts_supporting_documents).write_bytes(supporting_documents.file.read())
    (claim_dir / image_basename).write_bytes(image.file.read())


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    """Load a JSON object from disk when the file exists.

    :param path: Candidate JSON file path under results_dir.
    :return: Parsed object, or None when the file is absent.
    """
    if not path.is_file():
        return None
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return payload


@router.post("/claims", response_model=ClaimCreated, status_code=201)
def create_claim(
    description: UploadFile = File(...),
    supporting_documents: UploadFile = File(...),
    image: UploadFile = File(...),
    config: AppConfig = Depends(get_config),
) -> ClaimCreated:
    """Accept multipart claim intake and write files under config data_dir.

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

    artifacts = config.preprocessing.artifacts
    image_path = claim_dir / image_basename
    claim_root = claim_dir.resolve()
    if not image_path.resolve().is_relative_to(claim_root):
        raise HTTPException(status_code=422, detail="unsafe image filename")

    _write_claim_upload(
        claim_dir=claim_dir,
        artifacts_description=artifacts.description,
        artifacts_supporting_documents=artifacts.supporting_documents,
        description=description,
        supporting_documents=supporting_documents,
        image=image,
        image_basename=image_basename,
    )
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
    items: list[ClaimListItem] = []
    for folder in folders:
        items.append(
            ClaimListItem(
                claim_id=folder.name,
                analysis_result=_load_optional_json(folder / artifacts.analysis_result),
                predicted_answer=_load_optional_json(folder / artifacts.predicted_answer),
            )
        )
    return items


@router.get("/claims/{claim_id}", response_model=ClaimDecision)
def get_claim(
    claim_id: str,
    config: AppConfig = Depends(get_config),
    preprocessing: PreprocessingPipeline = Depends(get_preprocessing),
    claims: ClaimPipeline = Depends(get_claims),
) -> ClaimDecision:
    """Run process_then_analyze for one claim and return the decision JSON.

    :param claim_id: Raw claim folder name under config data_dir.
    :param config: Injected application configuration.
    :param preprocessing: Shared PreprocessingPipeline from lifespan.
    :param claims: Shared ClaimPipeline from lifespan.
    :return: Claim decision including analysis_result payload.
    """
    try:
        _validate_claim_dir_name(claim_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    claim_dir = Path(config.preprocessing.data_dir) / claim_id
    if not claim_dir.is_dir():
        raise HTTPException(status_code=404, detail="claim not found")

    try:
        analysis_path = process_then_analyze(claim_dir, preprocessing, claims)
    except Exception as exc:
        logger.exception(
            "process_then_analyze failed claim_id=%s error=%s",
            claim_id,
            type(exc).__name__,
        )
        raise

    analysis_result = json.loads(analysis_path.read_text(encoding="utf-8"))
    artifacts = config.preprocessing.artifacts
    predicted_path = Path(config.preprocessing.results_dir) / claim_id / artifacts.predicted_answer
    predicted_answer = _load_optional_json(predicted_path)
    return ClaimDecision(
        claim_id=claim_id,
        analysis_result=analysis_result,
        predicted_answer=predicted_answer,
    )
