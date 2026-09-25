---
phase: 03-preprocessing-pipeline-orchestration
plan: 02
subsystem: workflows
tags: [preprocessing, workflows, batch, argparse, pytest]

requires:
  - phase: 03-preprocessing-pipeline-orchestration
    provides: "process_claim_to_preprocessed, output_root_from_config, path-segment guard"
provides:
  - "run_preprocessing_workflow soft-fail batch over all claim folders"
  - "main(--config) + python -m compliance.workflows entrypoint"
affects:
  - downstream-agents-dataset

actuals:
  tokens: 3040
  tasks: 2
  commits: 4

plan_head_before: 6dd47ac2fff37f186994786b904fdb471929db24

tech-stack:
  added: []
  patterns:
    - "Batch soft-fail mirrors Phase 1 run_pipeline (logger.exception + continue)"
    - "stdlib argparse --config → load_config → run_preprocessing_workflow"
    - "python -m via workflows/__main__.py delegating to pipeline.main"

key-files:
  created:
    - src/compliance/workflows/__main__.py
    - .planning/tdd/03-02-task1-red-evidence.json
    - .planning/tdd/03-02-task2-red-evidence.json
  modified:
    - src/compliance/workflows/pipeline.py
    - src/compliance/workflows/__init__.py
    - tests/test_workflows/test_pipeline.py

key-decisions:
  - "Soft-fail test raises via answer_reader (Phase 1 soft-catches document_reader)"
  - "main tested via monkeypatch of run_preprocessing_workflow; no console_scripts added"

patterns-established:
  - "run_preprocessing_workflow returns list[Path] of successful claim outs only"
  - "CLI logs claim names and counts only — no PII payloads (T-03-02 / T-03-07)"

requirements-completed: []

coverage:
  - id: D1
    description: "Batch mirrors all discovered claims into output_root with four artifacts each"
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_pipeline.py#test_run_preprocessing_workflow_mirrors_all_claims"
        status: pass
    human_judgment: false
  - id: D2
    description: "Per-claim failure is logged and skipped without aborting the full run"
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_pipeline.py#test_run_preprocessing_workflow_soft_fails_one_claim"
        status: pass
    human_judgment: false
  - id: D3
    description: "main loads --config and invokes run_preprocessing_workflow; missing config returns 2"
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_pipeline.py#test_main_runs_workflow_with_injected_config_path"
        status: pass
    human_judgment: false
  - id: D4
    description: "python -m compliance.workflows --help exits 0"
    verification:
      - kind: other
        ref: "uv run python -m compliance.workflows --help"
        status: pass
    human_judgment: false

duration: 3min
completed: 2026-09-25
status: complete
---

# Phase 03 Plan 02: Batch Orchestration + Main Entrypoint Summary

**Full-dataset `run_preprocessing_workflow` soft-fails per claim and `python -m compliance.workflows` runs the mirrored preprocessed tree end-to-end**

## Performance

- **Duration:** 3 min
- **Started:** 2026-09-25T12:10:31Z
- **Completed:** 2026-09-25T12:13:54Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Batch discovery via `_discover_claim_folders` writes mirrored `preprocessed/claim N/` for every successful claim
- Soft-fail loop logs `claim_dir.name` only and continues (T-03-05 / T-03-07)
- Runnable `main` + `__main__.py` with `--config` (default `config.yaml`); missing config → exit 2

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Batch soft-fail tests** - `4bd02b9` (test)
2. **Task 1 GREEN: run_preprocessing_workflow** - `6277c92` (feat)
3. **Task 2 RED: Main entrypoint tests** - `87fcf5f` (test)
4. **Task 2 GREEN: main + __main__.py** - `5024263` (feat)

**Plan metadata:** (pending docs commit)

_Note: TDD tasks produced RED → GREEN commits; measured `commits: 4` from plan_head_before._

## Files Created/Modified
- `src/compliance/workflows/pipeline.py` - `run_preprocessing_workflow`, `main`, argparse CLI
- `src/compliance/workflows/__main__.py` - `python -m compliance.workflows` entry
- `src/compliance/workflows/__init__.py` - exports `run_preprocessing_workflow`, `main`
- `tests/test_workflows/test_pipeline.py` - batch mirror, soft-fail, main unit tests
- `.planning/tdd/03-02-task1-red-evidence.json` / `03-02-task2-red-evidence.json` - RED gate records

## Decisions Made
- Soft-fail probe uses injectable `answer_reader` raise — Phase 1 already soft-catches document/description reader errors, so a document_reader raise never escapes to the batch loop
- Prefer `python -m compliance.workflows` over adding `[project.scripts]` console entry
- Monkeypatch `run_preprocessing_workflow` in main tests to keep CLI thin and avoid live readers

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Soft-fail test used document_reader raise but Phase 1 swallows it**
- **Found during:** Task 1 (GREEN verification)
- **Issue:** `_read_documents` logs WARNING and continues; claim 2 still wrote all four artifacts
- **Fix:** Raise via injectable `answer_reader` so the exception escapes `process_claim_to_preprocessed` into the batch soft-fail loop
- **Files modified:** `tests/test_workflows/test_pipeline.py`
- **Verification:** soft-fail test green; claim 2 absent from returned paths
- **Committed in:** `6277c92`

---

**Total deviations:** 1 auto-fixed (bug)
**Impact on plan:** Required for acceptance criteria (soft-fail must not abort run). No scope creep.

## Issues Encountered
None beyond the documented deviation.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 3 ROADMAP success criteria met: orchestrator module, mirrored preprocessed tree, four artifacts, runnable main, mypy + pytest green
- Downstream consumers can read `preprocessed/` without calling Phase 1 `processed.json`

## TDD Gate Compliance
- Task 1: Stub returned `[]`; multi-claim assertion failed (`RED_EVIDENCE_OK`)
- Task 2: Stub `main` returned 1; exit-code assertion failed (`RED_EVIDENCE_OK`)
- GREEN authorized only after `gsd_run check tdd-red-evidence` passed for each

## Self-Check: PASSED
- FOUND: `src/compliance/workflows/pipeline.py`
- FOUND: `src/compliance/workflows/__main__.py`
- FOUND: `tests/test_workflows/test_pipeline.py`
- FOUND: commits `4bd02b9`, `6277c92`, `87fcf5f`, `5024263`

---
*Phase: 03-preprocessing-pipeline-orchestration*
*Completed: 2026-09-25*
