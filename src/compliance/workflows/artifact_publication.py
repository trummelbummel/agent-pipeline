from __future__ import annotations

import json
import os
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple


class PublishedGeneration(NamedTuple):
    """Filesystem paths produced by one successful claim publication.

    :param run_id: Generation id stamped into every published artifact.
    :param claim_id: Claim folder segment under results_dir.
    :param artifacts: Promoted artifact paths (not including the manifest).
    :param manifest: Path to the commit-marker run_manifest.json.
    """

    run_id: str
    claim_id: str
    artifacts: tuple[Path, ...]
    manifest: Path


class ClaimGeneration(NamedTuple):
    """Parsed run_manifest.json commit marker for a published claim.

    :param run_id: Generation id this manifest commits.
    :param published_at: ISO-8601 UTC timestamp when the generation was committed.
    :param source: Origin of the publication (``analysis`` or ``preprocess``).
    :param artifacts: Artifact filenames this generation published.
    """

    run_id: str
    published_at: str
    source: str
    artifacts: tuple[str, ...]


class ClaimRunOutcome(NamedTuple):
    """Per-claim status recorded in a failed-run manifest.

    :param claim_id: Claim folder segment.
    :param status: ``ok`` or ``failed``.
    :param error: Exception type name when failed, else None.
    """

    claim_id: str
    status: str
    error: str | None


class MixedGenerationError(RuntimeError):
    """Raised when a published artifact disagrees with its claim's run manifest.

    :param claim_id: Claim folder segment.
    :param artifact: Artifact filename that mismatched.
    :param reason: ``artifact_missing``, ``run_id_missing``, or ``run_id_mismatch``.
    """

    def __init__(self, claim_id: str, artifact: str, reason: str) -> None:
        self.claim_id = claim_id
        self.artifact = artifact
        self.reason = reason
        super().__init__(f"mixed generation for {claim_id}: {artifact} ({reason})")


def new_run_id() -> str:
    """Mint a run-scoped generation id.

    Format ``{UTC:%Y%m%dT%H%M%S}-{uuid4 hex[:8]}`` is lexically sortable for
    humans reading a results tree and collision-free across concurrent runs.

    :return: New run id string.
    """
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def publish_claim_generation(
    *,
    results_root: Path,
    claim_id: str,
    run_id: str,
    bodies: dict[str, str],
    manifest_name: str,
    source: str,
) -> PublishedGeneration:
    """Stage, fsync, and atomically promote one claim generation under results_root.

    Staging lives at ``results_root/.staging/{run_id}/{claim_id}/``. Artifacts are
    promoted with ``os.replace``, then the manifest is renamed **last** — it is
    the commit point of the generation, and validity is defined against it.

    :param results_root: Config-rooted results directory.
    :param claim_id: Safe claim folder segment (validated at this filesystem boundary).
    :param run_id: Generation id stamped into the manifest (bodies already carry it).
    :param bodies: Mapping of artifact filename → JSON text to publish.
    :param manifest_name: Commit-marker filename (config-rooted).
    :param source: Publication origin (``analysis`` or ``preprocess``).
    :return: Paths of the promoted artifacts and the committed manifest.
    :raises ValueError: When ``claim_id`` is not a safe single path segment.
    """
    from compliance.preprocessing.claim_batch import _validate_claim_dir_name

    _validate_claim_dir_name(claim_id)
    staging_root = results_root / ".staging" / run_id / claim_id
    claim_dir = results_root / claim_id
    claim_dir.mkdir(parents=True, exist_ok=True)
    staging_root.mkdir(parents=True, exist_ok=True)

    staged = _staged_bodies(staging_root, bodies)
    promoted = _promoted_artifacts(staged, claim_dir)
    # Manifest rename is last: it is the commit point. A generation is valid only
    # when the manifest run_id equals the run_id stamped in each named artifact.
    manifest_text = _manifest_body(run_id=run_id, source=source, artifacts=tuple(bodies))
    staged_manifest = staging_root / manifest_name
    staged_manifest.write_text(manifest_text, encoding="utf-8")
    _fsynced_file(staged_manifest)
    _fsynced_directory(staging_root)
    manifest_dest = claim_dir / manifest_name
    os.replace(staged_manifest, manifest_dest)
    _fsynced_directory(claim_dir)
    _removed_empty_staging(results_root, run_id, claim_id)
    return PublishedGeneration(
        run_id=run_id,
        claim_id=claim_id,
        artifacts=promoted,
        manifest=manifest_dest,
    )


def artifact_run_id(path: Path) -> str | None:
    """Return the ``run_id`` stamped in a JSON artifact, or None if absent/missing.

    :param path: Path to a published JSON artifact.
    :return: The run_id string, or None when the file is missing or has no stamp.
    """
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    value = raw.get("run_id")
    return value if isinstance(value, str) else None


def published_generation(claim_results_dir: Path, manifest_name: str) -> ClaimGeneration | None:
    """Load the committed generation from a claim results directory.

    :param claim_results_dir: ``results_dir/{claim_id}/``.
    :param manifest_name: Commit-marker filename.
    :return: Parsed ClaimGeneration, or None when no manifest (legacy tree).
    """
    path = claim_results_dir / manifest_name
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    artifacts = raw.get("artifacts") or []
    return ClaimGeneration(
        run_id=str(raw["run_id"]),
        published_at=str(raw.get("published_at", "")),
        source=str(raw.get("source", "")),
        artifacts=tuple(str(name) for name in artifacts),
    )


def generation_mismatch(
    claim_results_dir: Path,
    artifact_name: str,
    manifest_name: str,
) -> str | None:
    """Return a mismatch reason when the artifact disagrees with the committed generation.

    No manifest → None (pre-SR-005 legacy tolerance). Present manifest that
    disagrees → ``artifact_missing``, ``run_id_missing``, or ``run_id_mismatch``.

    :param claim_results_dir: ``results_dir/{claim_id}/``.
    :param artifact_name: Artifact filename to check.
    :param manifest_name: Commit-marker filename.
    :return: Reason code, or None when the generation is valid / legacy.
    """
    generation = published_generation(claim_results_dir, manifest_name)
    if generation is None:
        return None
    path = claim_results_dir / artifact_name
    if not path.is_file():
        return "artifact_missing"
    stamped = artifact_run_id(path)
    if stamped is None:
        return "run_id_missing"
    if stamped != generation.run_id:
        return "run_id_mismatch"
    return None


def write_failed_run_manifest(
    results_root: Path,
    run_id: str,
    outcomes: Sequence[ClaimRunOutcome],
) -> Path | None:
    """Write ``results_root/.runs/{run_id}.json`` when any claim failed.

    :param results_root: Config-rooted results directory.
    :param run_id: Run id shared by every claim in the batch.
    :param outcomes: Per-claim statuses for the run.
    :return: Path written, or None when every outcome succeeded.
    """
    failed = [o for o in outcomes if o.status == "failed"]
    if not failed:
        return None
    runs_dir = results_root / ".runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{run_id}.json"
    payload = {
        "run_id": run_id,
        "outcomes": [{"claim_id": o.claim_id, "status": o.status, "error": o.error} for o in outcomes],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _staged_bodies(staging_root: Path, bodies: dict[str, str]) -> tuple[Path, ...]:
    """Write each body into staging, fsync each file, and return their paths.

    :param staging_root: Per-claim staging directory.
    :param bodies: Artifact filename → JSON text.
    :return: Paths of the staged files in insertion order.
    """
    paths: list[Path] = []
    for name, text in bodies.items():
        path = staging_root / name
        path.write_text(text, encoding="utf-8")
        _fsynced_file(path)
        paths.append(path)
    _fsynced_directory(staging_root)
    return tuple(paths)


def _promoted_artifacts(staged: tuple[Path, ...], claim_dir: Path) -> tuple[Path, ...]:
    """Atomically rename each staged artifact into the published claim directory.

    :param staged: Staged file paths.
    :param claim_dir: Destination ``results_dir/{claim_id}/``.
    :return: Destination paths after promote.
    """
    promoted: list[Path] = []
    for src in staged:
        dest = claim_dir / src.name
        os.replace(src, dest)
        promoted.append(dest)
    return tuple(promoted)


def _manifest_body(*, run_id: str, source: str, artifacts: tuple[str, ...]) -> str:
    """Build the JSON text for the publication commit marker.

    :param run_id: Generation id.
    :param source: Publication origin.
    :param artifacts: Artifact filenames this generation publishes.
    :return: Pretty-printed JSON with trailing newline.
    """
    payload = {
        "run_id": run_id,
        "published_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source,
        "artifacts": list(artifacts),
    }
    return json.dumps(payload, indent=2) + "\n"


def _fsynced_file(path: Path) -> None:
    """Flush file contents to durable storage.

    :param path: Openable file path.
    """
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsynced_directory(path: Path) -> None:
    """Fsync a directory entry so renames into it are durable on POSIX.

    :param path: Directory to fsync.
    """
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _removed_empty_staging(results_root: Path, run_id: str, claim_id: str) -> None:
    """Remove the staging claim directory and the run directory when empty.

    :param results_root: Results root holding ``.staging``.
    :param run_id: Run id whose staging tree to clean.
    :param claim_id: Claim segment under the run staging directory.
    """
    claim_staging = results_root / ".staging" / run_id / claim_id
    if claim_staging.is_dir() and not any(claim_staging.iterdir()):
        claim_staging.rmdir()
    run_staging = results_root / ".staging" / run_id
    if run_staging.is_dir() and not any(run_staging.iterdir()):
        run_staging.rmdir()
    staging_root = results_root / ".staging"
    if staging_root.is_dir() and not any(staging_root.iterdir()):
        staging_root.rmdir()
