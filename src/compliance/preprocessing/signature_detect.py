from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

SignatureDetectFn = Callable[[Path], float | None]

# Floor for Ultralytics ``conf`` so weak boxes (below accept threshold) still score.
_SIGNATURE_SCORE_FLOOR = 0.01

_HF_AUTH_HINT = (
    "HuggingFace gated model requires authentication. "
    "Accept access on the model page, then set HF_TOKEN (or HUGGING_FACE_HUB_TOKEN) "
    "or run `huggingface-cli login`. "
    "Alternatively set ocr_retry.signature_model to a local .pt path."
)


class SignatureDetectionError(RuntimeError):
    """YOLO signature detection failed; preprocessing must not continue silently."""


class SignatureDependencyError(SignatureDetectionError):
    """A required signature-detection package is not installed."""

    _REMEDIES: ClassVar[dict[str, str]] = {
        "huggingface_hub": "set ocr_retry.signature_model to a local .pt path",
        "ultralytics": "disable ocr_retry.on_missing_signature",
    }

    def __init__(self, package: str) -> None:
        """Build the missing-dependency message from the package name.

        :param package: Name of the missing package (``huggingface_hub`` or
            ``ultralytics``); selects the remedy suggestion.
        """
        remedy = self._REMEDIES[package]
        super().__init__(
            f"{package} is required for YOLO signature detection. Install project deps (`uv sync`) or {remedy}."
        )


class SignatureWeightsDownloadError(SignatureDetectionError):
    """YOLO weights could not be downloaded from HuggingFace Hub."""

    def __init__(self, weights_ref: str, reason: str, *, auth_hint: bool = True) -> None:
        """Build the download-failure message, optionally appending the HF auth hint.

        :param weights_ref: ``model/weights`` identifier being downloaded.
        :param reason: Human-readable cause (gated repo, missing token, HTTP status, etc.).
        :param auth_hint: When True, append ``_HF_AUTH_HINT`` (omit for non-auth HTTP errors).
        """
        message = f"Cannot download YOLO weights '{weights_ref}': {reason}."
        if auth_hint:
            message += f" {_HF_AUTH_HINT}"
        super().__init__(message)


class SignatureInferenceError(SignatureDetectionError):
    """YOLO inference itself raised while scoring a document image."""

    def __init__(self, image_path: Path, cause: Exception) -> None:
        """Build the inference-failure message from the image and underlying cause.

        :param image_path: Raster document path YOLO was scoring.
        :param cause: Exception raised by Ultralytics during predict.
        """
        super().__init__(f"YOLO signature detection failed for {image_path.name}: {cause}")


class SignatureModelNotConfiguredError(SignatureDetectionError):
    """Signature verify is enabled but no signature model is configured."""

    def __init__(self) -> None:
        """Build the fixed not-configured message (no parameters vary)."""
        super().__init__("ocr_retry.on_missing_signature is enabled but ocr_retry.signature_model is empty.")


def resolve_signature_weights(*, model: str, weights: str) -> str:
    """Resolve YOLO weights from a local ``.pt`` path or HuggingFace repo.

    :param model: Local ``.pt`` path or HuggingFace repo id.
    :param weights: Filename inside the HF repo when ``model`` is a repo id.
    :return: Filesystem path string usable by Ultralytics ``YOLO``.
    :raises SignatureDetectionError: When download/auth fails (e.g. missing HF_TOKEN).
    """
    local = Path(model)
    if local.suffix.lower() == ".pt" and local.is_file():
        return str(local)
    weights_ref = f"{model}/{weights}"
    try:
        from huggingface_hub import hf_hub_download
        from huggingface_hub.errors import (
            GatedRepoError,
            HfHubHTTPError,
            LocalTokenNotFoundError,
        )
    except ImportError as exc:
        raise SignatureDependencyError("huggingface_hub") from exc

    try:
        return hf_hub_download(repo_id=model, filename=weights)
    except GatedRepoError as exc:
        raise SignatureWeightsDownloadError(weights_ref, "gated repository requires accepted access") from exc
    except LocalTokenNotFoundError as exc:
        raise SignatureWeightsDownloadError(weights_ref, "no HuggingFace token available") from exc
    except HfHubHTTPError as exc:
        status = getattr(exc.response, "status_code", None) if hasattr(exc, "response") else None
        if status in {401, 403}:
            raise SignatureWeightsDownloadError(weights_ref, f"HTTP {status} access denied") from exc
        raise SignatureWeightsDownloadError(weights_ref, str(exc), auth_hint=False) from exc
    except OSError as exc:
        raise SignatureWeightsDownloadError(weights_ref, str(exc)) from exc


def detect_signature_with_yolo(
    image_path: Path,
    *,
    model: str,
    weights: str,
    confidence: float,
) -> float | None:
    """Run Ultralytics YOLO signature detection on a document image.

    Predicts with a low score floor so boxes below ``confidence`` still return a
    probability; the caller applies ``confidence`` as the accept / HITL threshold.

    :param image_path: Raster document path (PNG preferred).
    :param model: HuggingFace repo id or local ``.pt`` path from config.
    :param weights: Filename inside the HF repo (ignored for local ``.pt``).
    :param confidence: Accept threshold from config (also caps the score floor).
    :return: Max box confidence in ``[0, 1]``, or ``None`` when no boxes fire.
    :raises SignatureDetectionError: When Ultralytics/YOLO is missing or inference fails.
    """
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise SignatureDependencyError("ultralytics") from exc

    weights_path = resolve_signature_weights(model=model, weights=weights)
    score_floor = min(_SIGNATURE_SCORE_FLOOR, float(confidence))
    try:
        results = YOLO(weights_path).predict(
            source=str(image_path),
            conf=score_floor,
            verbose=False,
        )
    except SignatureDetectionError:
        raise
    except Exception as exc:
        raise SignatureInferenceError(image_path, exc) from exc
    scores: list[float] = []
    for result in results:
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            continue
        scores.extend(float(value) for value in boxes.conf.tolist())
    if not scores:
        return None
    return max(scores)
