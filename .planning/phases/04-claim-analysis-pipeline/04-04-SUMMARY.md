---
phase: 04-claim-analysis-pipeline
plan: 04
subsystem: workflows
tags: [ClaimPipeline, soft-fail, batch, CLI, analyze, pytest]

requires:
  - phase: 04-claim-analysis-pipeline
    provides: Full coverage routing (04-03)
  - phase: 03-preprocessing-pipeline-orchestration
    provides: Soft-fail PreprocessingPipeline.run + main entrypoint
provides:
  - ClaimPipeline.run soft-fail batch over preprocessed_dir
  - CLI --mode analyze (preprocess default preserved)
  - analysis_result.json per successful claim under results_dir
affects: []

actuals:
  tokens: 3559
  tasks: 2
  commits: 4
plan_head_before: 7506e93be5e978fe5dc9e9e437f59d92889db612

tech-stack:
  added: []
  patterns:
    - "ClaimPipeline.run mirrors PreprocessingPipeline soft-fail via _discover_claim_folders"
    - "main --mode {preprocess,analyze} default preprocess; compliance-preprocess unbroken"
    - "Batch/CLI logs claim names + exception types only (T-04-02)"

key-files:
  created:
    - src/main.py
    - .planning/tdd/260925-04-04-task1-red-evidence.json
    - .planning/tdd/260925-04-04-task2-red-evidence.json
  modified:
    - src/compliance/workflows/claim_pipeline.py
    - tests/test_workflows/test_claim_pipeline.py
    - tests/test_workflows/test_pipeline.py

key-decisions:
  - "Reuse _discover_claim_folders for preprocessed_dir discovery (same claim-name sort as Phase 03)"
  - "CLI --mode on main preferred over separate claim_pipeline module entry"
  - "Pipeline CLI fixture YAML updated to include required analysis section (Rule 3)"

patterns-established:
  - "Analysis batch soft-fail: try/except per claim → SKIP branch_log + continue"
  - "Injectable chat_fn on ClaimPipeline for unit path; no live Ollama"

requirements-completed: [R010, R016]

coverage:
  - id: D1
    description: "ClaimPipeline.run discovers preprocessed claims and writes analysis_result.json for successes"
    requirement: R010
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_claim_pipeline.py::test_run_batch_writes_analysis_for_successful_claims"
        status: pass
    human_judgment: false
  - id: D2
    description: "Batch soft-fails one claim; siblings still analyzed"
    requirement: R010
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_claim_pipeline.py::test_run_batch_soft_fails_one_claim"
        status: pass
    human_judgment: false
  - id: D3
    description: "CLI --mode analyze invokes ClaimPipeline.run"
    requirement: R010
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_claim_pipeline.py::test_main_analyze_mode_invokes_claim_pipeline_run"
        status: pass
    human_judgment: false
  - id: D4
    description: "Default CLI still runs preprocess; mypy+pytest phase gate green"
    requirement: R016
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_claim_pipeline.py::test_main_default_still_preprocess"
        status: pass
      - kind: other
        ref: "uv run mypy src/compliance/workflows/ src/compliance/config/ src/main.py"
        status: pass
    human_judgment: false

duration: 3min
completed: 2026-09-25
status: complete
---

# Phase 04 Plan 04: Batch Soft-Fail + Analyze CLI Summary

**ClaimPipeline.run soft-fails over all preprocessed claims, and `main --mode analyze` runs analysis without breaking the preprocess default.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-09-25T15:32:52Z
- **Completed:** 2026-09-25T15:36:25Z
- **Tasks:** 2
- **Files modified:** 6 (plan commits)

## Accomplishments

- Implemented `ClaimPipeline.run` with `_discover_claim_folders` + per-claim soft-fail
- Extended CLI with `--mode {preprocess,analyze}` (default preprocess)
- Phase gate green: claim_pipeline + pipeline + settings pytest; mypy; `--help`

## Task Commits

1. **Task 1 RED:** `08eff20` — `test(04-04): add failing soft-fail batch run tests`
2. **Task 1 GREEN:** `5f6869e` — `feat(04-04): soft-fail batch ClaimPipeline.run over preprocessed_dir`
3. **Task 2 RED:** `c21f5ef` — `test(04-04): add failing analyze CLI mode tests`
4. **Task 2 GREEN:** `3ad42eb` — `feat(04-04): add --mode analyze CLI without breaking preprocess`

**Plan metadata:** docs commit after SUMMARY/state updates

## Files Created/Modified

- `src/compliance/workflows/claim_pipeline.py` — `run` + `_written_analysis_outputs`
- `src/main.py` — `--mode` CLI wiring
- `tests/test_workflows/test_claim_pipeline.py` — batch + CLI tests
- `tests/test_workflows/test_pipeline.py` — analysis section in CLI fixture YAML
- `.planning/tdd/260925-04-04-task{1,2}-red-evidence.json` — TDD RED gates

## Decisions Made

- Reuse Phase 03 `_discover_claim_folders` for preprocessed discovery and name sorting
- Prefer `main --mode analyze` over a separate claim_pipeline module entry
- Soft-fail logs claim name + exception type only (no description/OCR bodies)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Pipeline CLI fixture missing required `analysis` section**
- **Found during:** Task 2 verify (`test_pipeline.py` in phase gate)
- **Issue:** `test_main_runs_workflow_with_injected_config_path` YAML omitted `analysis`, failing `load_config` after AnalysisConfig became required
- **Fix:** Added full analysis stage block to the fixture YAML
- **Files modified:** `tests/test_workflows/test_pipeline.py`
- **Commit:** `3ad42eb`

### Auth Gates

None.

## TDD Gate Compliance

- Task 1 `tdd="true"`: RED evidence `.planning/tdd/260925-04-04-task1-red-evidence.json` → `RED_EVIDENCE_OK` (`target_test_failed` for `test_run_batch_writes_analysis_for_successful_claims`)
- Task 2 `tdd="true"`: RED evidence `.planning/tdd/260925-04-04-task2-red-evidence.json` → `RED_EVIDENCE_OK` (`target_test_failed` for `test_main_analyze_mode_invokes_claim_pipeline_run`)

## Known Stubs

None.

## Threat Flags

None beyond plan register (T-04-01 name validation before analyze; T-04-02 claim/error-type logging; T-04-07 soft-fail continue).

## Next

Phase 04 complete — ready for verification / ship.

## Self-Check: PASSED

- `ClaimPipeline.run` exists with soft-fail batch semantics
- `main --mode analyze` wired; default preprocess preserved
- Commits `08eff20`, `5f6869e`, `c21f5ef`, `3ad42eb` on branch
- Suite: 39 passed (claim_pipeline + pipeline + settings); mypy clean
