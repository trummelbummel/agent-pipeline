---
phase: 05-fastapi-claims-api
plan: 01
subsystem: api
tags: [fastapi, lifespan, multipart, UploadFile, TestClient, path-safety]

requires:
  - phase: 05-fastapi-claims-api
    provides: FastAPI stack deps + tests/test_api Nyquist stubs (05-00)
provides:
  - create_app(config=..., chat_fn=...) with lifespan DI
  - Depends helpers (get_config / get_preprocessing / get_claims)
  - POST /claims multipart intake under config data_dir
  - ClaimCreated response schema
affects:
  - 05-02-fastapi-claims-api
  - 05-03-fastapi-claims-api

actuals:
  tokens: 5405
  tasks: 3
  commits: 5
  plan_head_before: d880ab81bf5ee46eb82a2ced8c787d7a0e7c42c7

tech-stack:
  added: []
  patterns:
    - "create_app injects AppConfig + chat_fn; lifespan yields AppState to request.state"
    - "Sync POST with File(...) defaults (future-annotations safe)"
    - "claim_id next claim {n} via claim_batch sort key; Path(filename).name + resolve check"

key-files:
  created:
    - src/api/app.py
    - src/api/deps.py
    - src/api/schemas.py
    - src/api/routes_claims.py
  modified:
    - src/api/__init__.py
    - tests/test_api/test_deps_lifespan.py
    - tests/test_api/test_claims_post.py

key-decisions:
  - "Probe lifespan tests call deps with Request (Annotated Depends breaks under future annotations in nested test fns)"
  - "409 conflict test patches _next_claim_id to simulate TOCTOU against max+1 id scheme"
  - "Image path hardened with resolve().is_relative_to(claim_dir) after basename coerce"

patterns-established:
  - "API tests build tmp AppConfig like workflow tests; with TestClient(app) as client for lifespan"
  - "Route File/Depends use default-value form under from __future__ import annotations"

requirements-completed: [R017, R021]

coverage:
  - id: D1
    description: "create_app lifespan yields config + PreprocessingPipeline + ClaimPipeline; Depends read request.state"
    requirement: R021
    verification:
      - kind: unit
        ref: "tests/test_api/test_deps_lifespan.py::test_lifespan_exposes_pipelines_via_depends"
        status: pass
      - kind: unit
        ref: "tests/test_api/test_deps_lifespan.py::test_create_app_uses_injected_config_roots"
        status: pass
    human_judgment: false
  - id: D2
    description: "POST /claims multipart writes three files under Path(config.preprocessing.data_dir)/claim_id"
    requirement: R017
    verification:
      - kind: unit
        ref: "tests/test_api/test_claims_post.py::test_post_claims_writes_raw_folder"
        status: pass
    human_judgment: false
  - id: D3
    description: "Disallowed image extension → 422; existing claim folder → 409; no overwrite"
    requirement: R017
    verification:
      - kind: unit
        ref: "tests/test_api/test_claims_post.py::test_post_claims_rejects_disallowed_image_extension"
        status: pass
      - kind: unit
        ref: "tests/test_api/test_claims_post.py::test_post_claims_conflict_when_folder_exists"
        status: pass
    human_judgment: false
  - id: D4
    description: "Traversal-like image filenames stay under claim_dir; generated claim_id is single safe segment"
    requirement: R017
    verification:
      - kind: unit
        ref: "tests/test_api/test_claims_post.py::test_post_rejects_path_traversal_image_filename"
        status: pass
      - kind: unit
        ref: "tests/test_api/test_claims_post.py::test_generated_claim_id_always_safe_single_segment"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-09-25
status: complete
---

# Phase 05 Plan 01: FastAPI create_app + POST /claims Summary

**Lifespan DI factory and multipart POST /claims write path-safe claim folders under injected config data_dir (R017, R021)**

## Performance

- **Duration:** 5 min
- **Started:** 2026-09-25T16:29:54Z
- **Completed:** 2026-09-25T16:36:08Z
- **Tasks:** 3/3
- **Files modified:** 7

## Accomplishments

- `create_app(config=..., chat_fn=...)` yields AppConfig + both pipelines once via lifespan; deps read `request.state`
- `POST /claims` accepts description / supporting_documents / image → `data_dir/claim {n}/` with artifact names from config
- Path-safety: basename-only image names, resolve escape check, 422 on bad extension, 409 on mkdir collision

## Task Commits

1. **Task 1 RED: lifespan DI tests** - `dafc7ef` (test)
2. **Task 1 GREEN: create_app lifespan DI** - `a23dc8b` (feat)
3. **Task 2 RED: POST /claims tests** - `c75985e` (test)
4. **Task 2 GREEN: POST /claims intake** - `03ad8e2` (feat)
5. **Task 3: path-safety prove + harden** - `08f31dd` (feat)

**Plan metadata:** (pending docs commit)

## Files Created/Modified

- `src/api/app.py` — `create_app` + lifespan AppState; mounts claims router
- `src/api/deps.py` — `get_config` / `get_preprocessing` / `get_claims`
- `src/api/schemas.py` — `ClaimCreated`
- `src/api/routes_claims.py` — POST /claims + `_next_claim_id` / `_write_claim_upload`
- `src/api/__init__.py` — re-exports `create_app`
- `tests/test_api/test_deps_lifespan.py` — green R021 tests
- `tests/test_api/test_claims_post.py` — green R017 + path-safety tests

## Decisions Made

- Lifespan probe routes call deps with `Request` because nested `Annotated[..., Depends(...)]` is stringified under `from __future__ import annotations` and FastAPI treats params as query fields
- 409 test patches `_next_claim_id` (route helper, not pipeline) to force TOCTOU against max+1 naming
- Extra `resolve().is_relative_to(claim_dir)` after `Path(filename).name` for T-05-01

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Nested Annotated Depends unusable in tests under future annotations**
- **Found during:** Task 1 GREEN
- **Issue:** Probe routes with `Annotated[..., Depends(...)]` inside the test function returned 422 (params treated as query)
- **Fix:** Call `get_*` helpers with `Request` in probes; production routes use `= File(...)` / `= Depends(...)` defaults
- **Files modified:** `tests/test_api/test_deps_lifespan.py`, `src/api/routes_claims.py`
- **Commit:** `a23dc8b` / `03ad8e2`

**2. [Rule 1 - Bug] Conflict test vs max+1 claim_id**
- **Found during:** Task 2 GREEN
- **Issue:** Pre-seeding `claim 1` makes `_next_claim_id` return `claim 2`, so mkdir never collides
- **Fix:** Patch `_next_claim_id` to return existing `claim 1` (simulates concurrent TOCTOU)
- **Files modified:** `tests/test_api/test_claims_post.py`
- **Commit:** `03ad8e2`

**3. [Rule 2 - Missing critical] Resolve-boundary check for image path**
- **Found during:** Task 3
- **Issue:** Basename-only write was already safe; plan asked to harden T-05-01
- **Fix:** Reject when resolved image path is not under claim_dir
- **Files modified:** `src/api/routes_claims.py`
- **Commit:** `08f31dd`

**Note:** Task 3 path-safety tests passed immediately (mitigations shipped in Task 2); Task 3 added proving tests + resolve harden without a separate failing RED gate.

---

**Total deviations:** 3 auto-fixed
**Impact on plan:** R017/R021 still satisfied; conflict coverage requires helper patch for deterministic 409.

## Auth Gates

None

## Issues Encountered

None blocking

## User Setup Required

None

## Next Phase Readiness

- Ready for 05-02: GET /claims/{id} + GET /claims (orchestration + list)
- Do not change ClaimPipeline taxonomy here (honored)
- 05-02 stubs remain xfail under `tests/test_api/test_claims_get.py` and `test_claims_list.py`

## Self-Check: PASSED

- FOUND: src/api/app.py, deps.py, schemas.py, routes_claims.py
- FOUND: tests/test_api/test_deps_lifespan.py, test_claims_post.py
- FOUND: dafc7ef, a23dc8b, c75985e, 03ad8e2, 08f31dd
- VERIFY: `uv run pytest tests/test_api -q` → 7 passed, 5 xfailed; `mypy src/api/` clean

---
*Phase: 05-fastapi-claims-api*
*Completed: 2026-09-25*
