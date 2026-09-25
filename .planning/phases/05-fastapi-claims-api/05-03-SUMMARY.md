---
phase: 05-fastapi-claims-api
plan: 03
subsystem: workflows
tags: [run-source, claim-id, process_then_analyze, R020, R022, mypy, pytest]

requires:
  - phase: 05-fastapi-claims-api
    provides: process_then_analyze + GET decision/list (05-02)
provides:
  - PreprocessingPipeline.run(source: Path | None) single-or-directory
  - ClaimPipeline.run(source: Path | None) single-or-directory
  - CLI --claim-id → process_then_analyze under data_dir
  - Phase 05 mypy + pytest gate green (R022)
affects:
  - phase-06-prediction-evaluation
  - phase-07-denial-rule-checkers

actuals:
  tokens: 13542
  tasks: 2
  commits: 2
  plan_head_before: e12c1b89ddf730fdd8fbf9c418979fe846e3ec28

tech-stack:
  added: []
  patterns:
    - "run(source): claim folder → single; directory → soft-fail batch; None → config roots"
    - "CLI --claim-id validates via _validate_claim_dir_name then process_then_analyze"
    - "_is_claim_folder: safe segment + startswith claim detects single vs batch root"

key-files:
  created:
    - .planning/tdd/260925-05-03-task1-red-evidence.json
  modified:
    - src/compliance/workflows/pipeline.py
    - src/compliance/workflows/claim_pipeline.py
    - src/main.py
    - tests/test_workflows/test_pipeline.py
    - tests/test_workflows/test_claim_pipeline.py

key-decisions:
  - "CLI --claim-id always runs process_then_analyze (same as GET); mode only applies to batch run(None)"
  - "ClaimPipeline loads from claim_dir when supporting_document artifact present; else preprocessed_root/name (keeps process_then_analyze raw-path compatible)"

patterns-established:
  - "Caller configures Path outside pipelines — run never hardcodes roots beyond AppConfig when source is None"
  - "Shared _is_claim_folder gate distinguishes single claim from claims directory"

requirements-completed: [R020, R022]

coverage:
  - id: D1
    description: "PreprocessingPipeline.run(claim_folder) processes one claim; siblings untouched"
    requirement: R020
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_pipeline.py::test_run_with_claim_folder_processes_one"
        status: pass
    human_judgment: false
  - id: D2
    description: "PreprocessingPipeline.run(parent_dir) soft-fail batches under caller Path"
    requirement: R020
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_pipeline.py::test_run_with_directory_batches"
        status: pass
    human_judgment: false
  - id: D3
    description: "run(None) uses config data_dir / preprocessed_dir roots"
    requirement: R020
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_pipeline.py::test_run_none_uses_config_roots"
        status: pass
      - kind: unit
        ref: "tests/test_workflows/test_claim_pipeline.py::test_run_none_uses_config_roots"
        status: pass
    human_judgment: false
  - id: D4
    description: "CLI --claim-id resolves under data_dir and calls process_then_analyze"
    requirement: R020
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_pipeline.py::test_cli_or_api_passes_path_from_outside"
        status: pass
    human_judgment: false
  - id: D5
    description: "Phase gate pytest + mypy + workflows --help green for API/workflows/config/main"
    requirement: R022
    verification:
      - kind: unit
        ref: "uv run pytest tests/test_api tests/test_workflows tests/test_config/test_settings.py"
        status: pass
      - kind: other
        ref: "uv run mypy src/api/ src/compliance/workflows/ src/compliance/config/ src/main.py"
        status: pass
    human_judgment: false

duration: 7min
completed: 2026-09-25
status: complete
---

# Phase 05 Plan 03: run(source) + phase quality gate Summary

**Caller-configured `run(source)` on both pipelines plus CLI `--claim-id` → `process_then_analyze`; Phase 05 mypy/pytest gate green (R020, R022)**

## Performance

- **Duration:** 7 min
- **Started:** 2026-09-25T16:44:45Z
- **Completed:** 2026-09-25T16:51:21Z
- **Tasks:** 2/2
- **Files modified:** 7

## Accomplishments

- `PreprocessingPipeline.run(source)` / `ClaimPipeline.run(source)` accept one claim folder, a claims directory, or `None` (config roots)
- CLI `--claim-id` validates the segment, joins under `data_dir`, and shares `process_then_analyze` with GET
- Full phase gate: 60 pytest passed; mypy clean on api/workflows/config/main; `--help` shows `--claim-id`

## Task Commits

1. **Task 1 RED: failing run(source) tests** - `78c6b26` (test)
2. **Task 1 GREEN: run(source) + CLI --claim-id** - `babce52` (feat)
3. **Task 2: phase gate** — no code commit (already green; no obsolete xfails)

## Files Created/Modified

- `src/compliance/workflows/pipeline.py` — `run(source)`, `_is_claim_folder`
- `src/compliance/workflows/claim_pipeline.py` — `run(source)`, input_root loading for external claim folders
- `src/main.py` — `--claim-id` → `process_then_analyze`
- `tests/test_workflows/test_pipeline.py` / `test_claim_pipeline.py` — R020 coverage
- `.planning/tdd/260925-05-03-task1-red-evidence.json` — RED gate record

## Decisions Made

- `--claim-id` always runs end-to-end `process_then_analyze` (aligned with GET); `--mode` only selects batch `run(None)`
- ClaimPipeline loads artifacts from the caller folder when `supporting_document` exists there; otherwise from `preprocessed_dir/{name}` so raw paths from `process_then_analyze` keep working

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] ClaimPipeline input_root for caller-supplied folders**
- **Found during:** Task 1 GREEN
- **Issue:** `analyze_claim` only read `preprocessed_root / name`, so `run(external_parent)` could not load artifacts from discovered folders
- **Fix:** Thread `input_root` in graph state; prefer claim_dir when supporting_document artifact is present
- **Files modified:** `src/compliance/workflows/claim_pipeline.py`
- **Commit:** `babce52`

**2. [Rule 3 - Blocking] Stale force-included site-packages/main.py**
- **Found during:** Task 1 GREEN verify
- **Issue:** Hatch `force-include` left an old `main.py` in `.venv` without `claim_id`; pytest imported it over `src/main.py`
- **Fix:** `uv pip install -e . --reinstall-package compliance` (no source change)
- **Files modified:** none (env only)
- **Commit:** n/a

## TDD Gate Compliance

- RED evidence: `.planning/tdd/260925-05-03-task1-red-evidence.json` — `RED_EVIDENCE_OK`
- RED commit: `78c6b26`
- GREEN commit: `babce52`
- REFACTOR: skipped (no cleanup needed)

## Auth Gates

None

## Issues Encountered

None blocking. Task 2 found no xfail markers under `tests/test_api/`.

## User Setup Required

None

## Next Phase Readiness

- Phase 05 R017–R022 complete
- Pipelines ready for evaluation / denial-rule phases to call `run(source)` with caller Paths

## Self-Check: PASSED

- FOUND: src/compliance/workflows/pipeline.py, claim_pipeline.py, src/main.py
- FOUND: tests/test_workflows/test_pipeline.py, test_claim_pipeline.py
- FOUND: 78c6b26, babce52
- VERIFY: pytest api+workflows+settings → 60 passed; mypy → clean; `--help` → `--claim-id`

---
*Phase: 05-fastapi-claims-api*
*Completed: 2026-09-25*
