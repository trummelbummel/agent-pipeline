from __future__ import annotations

import errno
import json
import os
from pathlib import Path
from typing import Any

import pytest

from compliance.workflows.artifact_publication import (
    ClaimRunOutcome,
    generation_mismatch,
    new_run_id,
    publish_claim_generation,
    write_failed_run_manifest,
)


def _body(run_id: str, *, decision: str = "APPROVE") -> str:
    return json.dumps({"run_id": run_id, "decision": decision}, indent=2) + "\n"


def test_publishes_pair_with_manifest_last(tmp_path: Path) -> None:
    run_id = "20260929T120000-abcd1234"
    claim_id = "claim 1"
    results_root = tmp_path / "results"
    bodies = {
        "analysis_result.json": _body(run_id),
        "predicted_answer.json": _body(run_id, decision="DENY"),
    }

    published = publish_claim_generation(
        results_root=results_root,
        claim_id=claim_id,
        run_id=run_id,
        bodies=bodies,
        manifest_name="run_manifest.json",
        source="analysis",
    )

    claim_dir = results_root / claim_id
    assert published.manifest == claim_dir / "run_manifest.json"
    assert published.run_id == run_id
    assert {p.name for p in published.artifacts} == set(bodies)
    manifest = json.loads(published.manifest.read_text(encoding="utf-8"))
    assert manifest["run_id"] == run_id
    assert set(manifest["artifacts"]) == set(bodies)
    assert manifest["source"] == "analysis"
    for name, text in bodies.items():
        assert (claim_dir / name).read_text(encoding="utf-8") == text
        assert json.loads((claim_dir / name).read_text(encoding="utf-8"))["run_id"] == run_id
    assert not (results_root / ".staging").exists()
    assert {p.name for p in claim_dir.iterdir()} == {
        "analysis_result.json",
        "predicted_answer.json",
        "run_manifest.json",
    }


def test_interrupted_promote_leaves_no_valid_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results_root = tmp_path / "results"
    claim_id = "claim 1"
    old_run = "20260929T110000-oldrun01"
    new_run = "20260929T120000-newrun02"
    manifest_name = "run_manifest.json"

    publish_claim_generation(
        results_root=results_root,
        claim_id=claim_id,
        run_id=old_run,
        bodies={
            "analysis_result.json": _body(old_run),
            "predicted_answer.json": _body(old_run),
        },
        manifest_name=manifest_name,
        source="analysis",
    )
    claim_dir = results_root / claim_id
    old_manifest = (claim_dir / manifest_name).read_bytes()
    old_analysis = (claim_dir / "analysis_result.json").read_bytes()
    old_predicted = (claim_dir / "predicted_answer.json").read_bytes()

    real_replace = os.replace

    def _replace_fail_on_manifest(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        if Path(dst).name == manifest_name:
            raise OSError(errno.EIO)
        real_replace(src, dst)

    monkeypatch.setattr(
        "compliance.workflows.artifact_publication.os.replace",
        _replace_fail_on_manifest,
    )

    with pytest.raises(OSError):
        publish_claim_generation(
            results_root=results_root,
            claim_id=claim_id,
            run_id=new_run,
            bodies={
                "analysis_result.json": _body(new_run, decision="DENY"),
                "predicted_answer.json": _body(new_run, decision="DENY"),
            },
            manifest_name=manifest_name,
            source="analysis",
        )

    assert (claim_dir / manifest_name).read_bytes() == old_manifest
    # Artifacts may have been renamed; committed generation is still the old manifest.
    assert json.loads(old_manifest.decode())["run_id"] == old_run
    assert generation_mismatch(claim_dir, "analysis_result.json", manifest_name) == "run_id_mismatch"
    assert generation_mismatch(claim_dir, "predicted_answer.json", manifest_name) == "run_id_mismatch"
    # Previous generation bytes still readable somewhere — old files overwritten by promote,
    # so validity is defined by the still-committed old manifest disagreeing with new artifacts.
    assert (claim_dir / "analysis_result.json").read_bytes() != old_analysis
    assert (claim_dir / "predicted_answer.json").read_bytes() != old_predicted


def test_generation_mismatch_none_for_legacy_tree(tmp_path: Path) -> None:
    claim_dir = tmp_path / "claim 1"
    claim_dir.mkdir()
    (claim_dir / "predicted_answer.json").write_text(
        json.dumps({"decision": "APPROVE"}, indent=2) + "\n",
        encoding="utf-8",
    )
    assert generation_mismatch(claim_dir, "predicted_answer.json", "run_manifest.json") is None


def test_publish_rejects_unsafe_claim_id(tmp_path: Path) -> None:
    results_root = tmp_path / "results"
    results_root.mkdir()
    before = set(results_root.iterdir())

    with pytest.raises(ValueError, match="Unsafe claim directory name"):
        publish_claim_generation(
            results_root=results_root,
            claim_id=f"..{os.sep}escape",
            run_id="20260929T120000-abcd1234",
            bodies={"predicted_answer.json": _body("20260929T120000-abcd1234")},
            manifest_name="run_manifest.json",
            source="analysis",
        )

    assert set(results_root.iterdir()) == before


def test_failed_run_manifest_only_written_on_failure(tmp_path: Path) -> None:
    results_root = tmp_path / "results"
    run_id = new_run_id()
    ok = write_failed_run_manifest(
        results_root,
        run_id,
        [ClaimRunOutcome(claim_id="claim 1", status="ok", error=None)],
    )
    assert ok is None
    assert not (results_root / ".runs").exists()

    path = write_failed_run_manifest(
        results_root,
        run_id,
        [
            ClaimRunOutcome(claim_id="claim 1", status="ok", error=None),
            ClaimRunOutcome(claim_id="claim 2", status="failed", error="RuntimeError"),
        ],
    )
    assert path == results_root / ".runs" / f"{run_id}.json"
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    assert payload["run_id"] == run_id
    failed = [o for o in payload["outcomes"] if o["status"] == "failed"]
    assert failed == [{"claim_id": "claim 2", "status": "failed", "error": "RuntimeError"}]
