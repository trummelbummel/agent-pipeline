---
phase: 260929-mqy-sr-009-harden-upload-path-symlink-bounda
plan: 01
subsystem: api
tags: [upload-limits, path-safety, symlink, content-length, streaming]

requires:
  - phase: 260929-m5a (SR-007)
    provides: sync analysis POST, read-only GET, claim_analysis_lock
  - phase: 260929-k1p (SR-011)
    provides: StrictConfigModel extra=forbid, load-time ValueError subclasses
provides:
  - "api.upload max_file_bytes / max_request_bytes (25 MiB / 50 MiB) with Content-Length middleware + chunked writer"
  - "413 file_too_large / request_too_large with no partial claim folder"
  - "_validate_claim_root hard-reject symlink + optional root containment at every entry point"
  - "Load-time UnsafeArtifactNameError for configured artifact basenames"
affects: [SR-013]

actuals:
  tokens: 12617
  tasks: 3
  commits: 3

plan_head_before: 4764dbbc17c749a160ad40fb5a1daece36770fe5

tech-stack:
  added: []
  patterns:
    - "Two-layer intake: ASGI Content-Length precheck + 64 KiB chunked write with running totals"
    - "_validate_claim_root(claim_dir, root=None) — symlink hard-reject; resolve containment when root given"
    - "Raw claim_id validated before Path join so separators are not dropped by Path.name"

key-files:
  created:
    - src/api/uploads.py
    - tests/test_api/test_uploads.py
    - tests/test_api/test_claims_paths.py
  modified:
    - src/compliance/config/settings.py
    - config.yaml
    - src/api/app.py
    - src/api/routes_claims.py
    - src/compliance/preprocessing/claim_batch.py
    - src/compliance/workflows/pipeline.py
    - src/compliance/workflows/claim_pipeline.py
    - src/compliance/workflows/artifact_publication.py
    - src/main.py
    - tests/test_api/test_claims_post.py
    - tests/test_config/test_settings.py
    - tests/test_preprocessing/test_claim_batch.py
    - tests/test_workflows/test_artifact_publication.py
    - README.md

key-decisions:
  - "D-01: 25 MiB per file / 50 MiB total request (26214400 / 52428800 bytes)"
  - "D-02: Hard-reject symlinked claim roots (not resolve-and-contain)"
  - "D-03: Same containment on CLI batch discovery (skip + WARNING)"
  - "P-01: Caps under api.upload, not preprocessing"
  - "P-02: Store caps as bytes; YAML comment names MiB"
  - "P-03: Middleware + chunked writer (FastAPI buffers before handler)"
  - "P-04: 413 with file_too_large / request_too_large"
  - "P-05: 64 KiB chunks; remove claim_dir on breach (mkdir parents=False owns it)"
  - "P-06: Artifact basename validation at config load"
  - "P-07: ClaimRootContainmentError is ValueError subclass"
  - "P-08: root=None preserves R020 external claim folders"
  - "P-09: _is_claim_folder left unchanged"
  - "P-10: Discovery excludes + logs rather than aborting the batch"

patterns-established:
  - "UploadSizeLimitMiddleware bound at create_app with resolved config"
  - "path_safety DENY reasons: symlinked_claim_root, outside_root"

requirements-completed: [SR-009]

coverage:
  - id: D1
    description: "Oversized multipart intake returns 413 and leaves data_dir unchanged"
    requirement: SR-009
    verification:
      - kind: unit
        ref: "tests/test_api/test_claims_post.py::test_post_claims_rejects_file_too_large"
        status: pass
      - kind: unit
        ref: "tests/test_api/test_uploads.py::test_write_upload_stream_rejects_file_too_large"
        status: pass
    human_judgment: false
  - id: D2
    description: "Symlinked claim roots rejected at API, discovery, publication; targets untouched"
    requirement: SR-009
    verification:
      - kind: unit
        ref: "tests/test_api/test_claims_paths.py::test_post_analysis_rejects_symlinked_claim_root"
        status: pass
      - kind: unit
        ref: "tests/test_preprocessing/test_claim_batch.py::test_discover_excludes_symlinked_claim"
        status: pass
    human_judgment: false
  - id: D3
    description: "Configured artifact filenames that are not basenames fail at load"
    requirement: SR-009
    verification:
      - kind: unit
        ref: "tests/test_config/test_settings.py::test_artifact_filename_must_be_basename"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-09-29
status: complete
---

# Phase 260929-mqy Plan 01: SR-009 Harden upload/path/symlink Summary

**Bounded multipart intake (25/50 MiB) with Content-Length precheck + chunked writes, and one claim-root containment rule that hard-rejects symlinks at every entry point.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-09-29T14:33:38Z
- **Completed:** 2026-09-29T14:41:47Z
- **Tasks:** 3
- **Files modified:** 17

## Baselines vs final gates

| Gate | Task 1 baseline | Final |
|------|-----------------|-------|
| `pytest -q --cov` | 414 passed, 3 deselected, 91.34% | 436 passed, 3 deselected, 91.52% |
| `ruff check --no-fix src tests` | clean | clean |
| `mypy src` | 0 errors / 44 files | 0 errors / 45 files |
| `mypy tests/test_api` | 8 errors / 2 files | 8 errors / 2 files (unchanged) |

## Boundary contract (as shipped)

| Situation | Status | Detail |
|-----------|--------|--------|
| Content-Length > max_request_bytes | 413 | `request_too_large` (middleware, pre-parse) |
| Part > max_file_bytes | 413 | `file_too_large` |
| Parts total > max_request_bytes | 413 | `request_too_large` |
| Symlinked claim root (analysis POST) | 422 | `ClaimRootContainmentError` → ValueError |
| Symlinked claim root (CLI `--claim-id`) | exit 1 | same helper |
| Discovery symlink / outside_root | excluded | WARNING `path_safety` / DENY |
| Artifact filename not a basename | load fail | `UnsafeArtifactNameError` naming field |

Caps: `api.upload.max_file_bytes=26214400`, `max_request_bytes=52428800`.

## Accomplishments

- Two-layer intake DoS bound: middleware refuses over-declared Content-Length; `write_upload_stream` counts 64 KiB chunks against both caps and unlinks partials.
- `_validate_claim_root` is the single containment definition — wired into API, CLI, preprocess/analyze, publication, and both discovery helpers.
- Configured artifact filenames forced to basenames at load; README and gitignored backlog close SR-009.

## Task Commits

1. **Task 1 (tracer): bounded intake** — `24378f8` (feat)
2. **Task 2: claim-root containment + basename validation** — `8a8bce8` (feat)
3. **Task 3: document + close SR-009** — `0807f87` (feat)

## Behaviour-change register (intended)

- `POST /claims` can return 413 for oversized part/request.
- `config.yaml` gains `api:`; unknown `api:` keys fail under `extra="forbid"`.
- `create_app` resolves config at factory time (middleware needs the cap).
- Symlinked claim dirs are excluded from batch/evaluation discovery and rejected when named directly.

## Planner discretion (P-01..P-10)

Recorded in frontmatter `key-decisions`. Caps live under `api.upload`; two enforcement layers; 413 reason codes; 64 KiB chunks; load-time basename checks; `root=None` preserves R020; discovery soft-excludes.

## Follow-ups

- Caps bound one request; no global concurrent-request budget (T-SR009-10) — deployment concern.
- SR-013 still owns the policy-engine extract.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Raw claim_id must be validated before Path join**
- **Found during:** Task 2 (`test_publish_rejects_unsafe_claim_id`)
- **Issue:** `results_root / "../escape"` yields `.name == "escape"`, so name validation on `claim_dir.name` missed separators and only hit `outside_root`.
- **Fix:** Call `_validate_claim_dir_name(claim_id)` on the raw segment before joining in publication, API analysis POST, and CLI `--claim-id`.
- **Files modified:** `artifact_publication.py`, `routes_claims.py`, `main.py`
- **Commit:** `8a8bce8`

**Total deviations:** 1 auto-fixed (Rule 1). **Impact:** Restores the unsafe-name contract for multi-segment claim ids.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None beyond the plan's mitigated register (T-SR009-01..07, 09).

## Self-Check: PASSED

- [x] `src/api/uploads.py`, `tests/test_api/test_uploads.py`, `tests/test_api/test_claims_paths.py` exist
- [x] Commits `24378f8`, `8a8bce8`, `0807f87` present
- [x] Fast lane 436 passed / 91.52% ≥ 90; ruff clean; mypy src 0; tests/test_api mypy ≤ 8
- [x] `.gsd/review_backlog.md` has `### [x] SR-009` and is not staged
