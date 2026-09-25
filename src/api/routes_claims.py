"""Claims API routes — multipart intake under config data_dir."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.deps import get_config
from api.schemas import ClaimCreated
from compliance.config.settings import AppConfig
from compliance.preprocessing.claim_batch import _claim_sort_key
from compliance.workflows.pipeline import _validate_claim_dir_name

logger = logging.getLogger(__name__)

router = APIRouter()

_CLAIM_NUM = re.compile(r"(\d+)")


def _next_claim_id(data_dir: Path) -> str:
    """Return the next ``claim {n}`` folder name under ``data_dir``.

    :param data_dir: Configured raw claims root.
    :return: Single-segment claim folder name starting with ``claim``.
    """
    if not data_dir.is_dir():
        return "claim 1"
    folders = [
        path
        for path in data_dir.iterdir()
        if path.is_dir() and path.name.lower().startswith("claim")
    ]
    if not folders:
        return "claim 1"
    last = max(folders, key=_claim_sort_key)
    match = _CLAIM_NUM.search(last.name)
    number = int(match.group(1)) if match else 0
    return f"claim {number + 1}"


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
    (claim_dir / artifacts_supporting_documents).write_bytes(
        supporting_documents.file.read()
    )
    (claim_dir / image_basename).write_bytes(image.file.read())


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
