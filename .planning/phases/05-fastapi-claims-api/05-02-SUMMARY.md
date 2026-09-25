---
phase: 05-fastapi-claims-api
plan: 02
subsystem: api
tags: [fastapi, orchestration, process_then_analyze, TestClient, results_dir]

requires:
  - phase: 05-fastapi-claims-api
    provides: create_app lifespan DI + POST /claims (05-01)
provides:
  - process_then_analyze shared orchestrator (D-09)
  - GET /claims/{claim_id} decision JSON via process_then_analyze (R018)
  - GET /claims list from results_dir with optional artifacts (R019)
affects:
  - 05-03-fastapi-claims-api

actuals:
  tokens: 7432
  tasks: 3
  commits: 6
  plan_head_before: 5d26625c67b7a740e5d3da270ee3d873a1724e1f

tech-stack:
  added: []
  patterns:
    - "process_then_analyze(claim_dir, preprocessing, claims) → analysis_result Path"
    - "Sync GET handlers; claim_id validated via _validate_claim_dir_name before join"
    - "List returns bare JSON array; optional artifact keys null when files absent"

key-files:
  created:
    - src/compliance/workflows/orchestration.py
    - tests/test_workflows/test_orchestration.py
  modified:
    - src/compliance/workflows/__init__.py
    - src/api/routes_claims.py
    - src/api/schemas.py
    - tests/test_api/test_claims_get.py
    - tests/test_api/test_claims_list.py

key-decisions:
  - "List response is a bare list[ClaimListItem] array (not a wrapper model)"
  - "Absent optional artifacts serialize as null on ClaimListItem / ClaimDecision.predicted_answer"
  - "Unsafe claim_id tested via percent-encoded %2E%2E so the segment reaches the handler"

patterns-established:
  - "API GET-by-id calls shared process_then_analyze — never duplicates preprocess+analyze in the route"
  - "GET list discovers results_dir folders with startswith claim + _claim_sort_key"

requirements-completed: [R018, R019]

coverage:
  - id: D1
    description: "process_then_analyze writes preprocessed artifacts then analysis_result and returns the analysis path"
    requirement: R018
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_orchestration.py::test_process_then_analyze_calls_process_then_analyze_order"
        status: pass
    human_judgment: false
  - id: D2
    description: "GET /claims/{claim_id} runs process_then_analyze and returns decision JSON with analysis_result"
    requirement: R018
    verification:
      - kind: unit
        ref: "tests/test_api/test_claims_get.py::test_get_claim_runs_process_then_analyze_returns_decision"
        status: pass
    human_judgment: false
  - id: D3
    description: "Missing raw claim folder → 404; unsafe claim_id → 422"
    requirement: R018
    verification:
      - kind: unit
        ref: "tests/test_api/test_claims_get.py::test_get_claim_missing_raw_folder_returns_404"
        status: pass
      - kind: unit
        ref: "tests/test_api/test_claims_get.py::test_get_claim_unsafe_id_returns_422"
        status: pass
    human_judgment: false
  - id: D4
    description: "GET /claims lists results_dir with [] when empty and stable claim_id order with optional artifacts"
    requirement: R019
    verification:
      - kind: unit
        ref: "tests/test_api/test_claims_list.py::test_list_claims_empty_results_dir_returns_empty_list"
        status: pass
      - kind: unit
        ref: "tests/test_api/test_claims_list.py::test_list_claims_includes_optional_artifacts_stable_order"
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-09-25
status: complete
---

# Phase 05 Plan 02: GET decision + list + process_then_analyze Summary

**Shared process_then_analyze orchestrator plus GET /claims/{id} decision and GET /claims results_dir list (R018, R019)**

## Performance

- **Duration:** 6 min
- **Started:** 2026-09-25T16:37:40Z
- **Completed:** 2026-09-25T16:43:00Z
- **Tasks:** 3/3
- **Files modified:** 7

## Accomplishments

- `process_then_analyze` calls `process_claim` then `analyze_claim` and returns the analysis_result path (D-09)
- `GET /claims/{claim_id}` validates id → 404 if raw missing → shared orchestrator → ClaimDecision JSON
- `GET /claims` lists results_dir claim folders with optional predicted_answer / analysis_result; empty → []; stable numeric order

## Task Commits

1. **Task 1 RED: process_then_analyze test** - `c19b47f` (test)
2. **Task 1 GREEN: process_then_analyze** - `3263495` (feat)
3. **Task 2 RED: GET-by-id tests** - `f4b1960` (test)
4. **Task 2 GREEN: GET /claims/{claim_id}** - `938d770` (feat)
5. **Task 3 RED: GET list tests** - `8b30919` (test)
6. **Task 3 GREEN: GET /claims list** - `17bd40f` (feat)

**Plan metadata:** (pending docs commit)

## Files Created/Modified

- `src/compliance/workflows/orchestration.py` — `process_then_analyze`
- `src/compliance/workflows/__init__.py` — export `process_then_analyze`
- `src/api/routes_claims.py` — GET-by-id + GET list handlers
- `src/api/schemas.py` — `ClaimDecision`, `ClaimListItem`
- `tests/test_workflows/test_orchestration.py` — orchestration unit test
- `tests/test_api/test_claims_get.py` — green R018 tests
- `tests/test_api/test_claims_list.py` — green R019 tests

## Decisions Made

- List endpoint returns a bare JSON array (`list[ClaimListItem]`) rather than a wrapper model
- Optional artifacts use `null` when files are absent (schema fields default None)
- Unsafe-id test uses percent-encoded `%2E%2E` so Starlette delivers `..` to the handler for 422

## Deviations from Plan

None - plan executed exactly as written.

## Auth Gates

None

## Issues Encountered

None blocking

## User Setup Required

None

## Next Phase Readiness

- Ready for 05-03: single-claim `run(source)` / CLI alignment (R020) + mypy/pytest gate (R022)
- Shared orchestrator available for CLI reuse

## Self-Check: PASSED

- FOUND: src/compliance/workflows/orchestration.py
- FOUND: src/api/routes_claims.py, schemas.py
- FOUND: tests/test_workflows/test_orchestration.py, test_api/test_claims_get.py, test_claims_list.py
- FOUND: c19b47f, 3263495, f4b1960, 938d770, 8b30919, 17bd40f
- VERIFY: `uv run pytest tests/test_api/ tests/test_workflows/test_orchestration.py -q` → 13 passed; `mypy src/api/` clean

---
*Phase: 05-fastapi-claims-api*
*Completed: 2026-09-25*
