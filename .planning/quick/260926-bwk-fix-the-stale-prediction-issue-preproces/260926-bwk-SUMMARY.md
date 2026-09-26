---
phase: 260926-bwk-fix-the-stale-prediction-issue-preproces
plan: 01
subsystem: workflows
tags: [predicted_answer, preprocess, analysis, ownership, TDD]

requires:
  - phase: 04-claim-analysis-pipeline
    provides: ClaimPipeline analysis_result + predicted_answer writes
  - phase: 03-preprocessing-pipeline-orchestration
    provides: PreprocessingPipeline results_dir predicted_answer path
provides:
  - Shared predicted_answer_io with source-stamped writes and origin-aware remove
  - Preprocess no longer blind-unlinks analysis predictions
affects: [evaluation, make-analyze, preprocess]

actuals:
  tokens: 16840
  tasks: 2
  commits: 4
plan_head_before: 5af25f2bb7f3642f04d9172dcaf767dd160739c5

tech-stack:
  added: []
  patterns:
    - "predicted_answer ownership via JSON source stamp (preprocess|analysis)"
    - "remove_stale only for preprocess-origin when analysis_result absent"

key-files:
  created:
    - src/compliance/workflows/predicted_answer_io.py
    - tests/test_workflows/test_predicted_answer_io.py
  modified:
    - src/compliance/workflows/pipeline.py
    - src/compliance/workflows/claim_pipeline.py
    - tests/test_workflows/test_pipeline.py
    - tests/test_workflows/test_claim_pipeline.py

key-decisions:
  - "Analysis source never removed by preprocess; also preserve when analysis_result.json exists"
  - "Legacy fraud/Benford explanation without source treated as preprocess-origin"
  - "source stamped on dump only — GroundTruth schema unchanged"

patterns-established:
  - "All predicted_answer write/remove goes through predicted_answer_io"

requirements-completed: []

coverage:
  - id: D1
    description: Preprocess with no bundle decision does not delete analysis-authored predicted_answer
    verification:
      - kind: unit
        ref: tests/test_workflows/test_pipeline.py#test_process_claim_preserves_analysis_predicted_answer_without_decision
        status: pass
    human_judgment: false
  - id: D2
    description: Preprocess still removes fraud/Benford preprocess-origin predicted_answer when analysis_result absent
    verification:
      - kind: unit
        ref: tests/test_workflows/test_pipeline.py#test_process_claim_skips_predicted_answer_without_pipeline_decision
        status: pass
      - kind: unit
        ref: tests/test_workflows/test_predicted_answer_io.py#test_remove_stale_unlinks_legacy_fraud_without_analysis_result
        status: pass
    human_judgment: false
  - id: D3
    description: Fraud deny still writes predicted_answer with source=preprocess
    verification:
      - kind: unit
        ref: tests/test_workflows/test_pipeline.py#test_process_claim_writes_predicted_answer_on_fraud_deny
        status: pass
    human_judgment: false
  - id: D4
    description: Analysis writes predicted_answer with source=analysis via shared I/O
    verification:
      - kind: unit
        ref: tests/test_workflows/test_claim_pipeline.py#test_analyze_claim_cancellation_path_writes_analysis_result
        status: pass
    human_judgment: false
  - id: D5
    description: Shared predicted_answer_io owns write/remove rules
    verification:
      - kind: unit
        ref: tests/test_workflows/test_predicted_answer_io.py
        status: pass
    human_judgment: false

duration: 4min
completed: 2026-09-26
status: complete
---

# Phase 260926-bwk Plan 01: Stale prediction fix Summary

**Preprocess no longer blind-unlinks evaluator predictions; shared `predicted_answer_io` stamps `source` and removes only preprocess-origin leftovers.**

## Performance

- **Duration:** 4min
- **Started:** 2026-09-26T06:36:35Z
- **Completed:** 2026-09-26T06:40:14Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Centralized predicted_answer write/remove in `predicted_answer_io` with `source=preprocess|analysis`
- Preprocess calls `remove_stale_preprocess_prediction` instead of unconditional `unlink`
- Analysis writes via `write_analysis_predicted_answer`; regression suite green (52 tests)

## Task Commits

Each task was committed atomically (TDD RED → GREEN):

1. **Task 1 RED:** `6aa85c9` — failing tests + stub I/O module
2. **Task 1 GREEN:** `b63a3df` — safe remove + preprocess wiring
3. **Task 2 RED:** `0bb7cc1` — assert analysis stamps `source=analysis`
4. **Task 2 GREEN:** `aa87ffb` — ClaimPipeline uses `write_analysis_predicted_answer`

## TDD Gate Compliance

| Task | RED | GREEN | Evidence |
|------|-----|-------|----------|
| 1 | ✓ `6aa85c9` (RED_EVIDENCE_OK) | ✓ `b63a3df` | `.planning/tdd/260926-bwk-task1-red-evidence.json` |
| 2 | ✓ `0bb7cc1` (RED_EVIDENCE_OK) | ✓ `aa87ffb` | `.planning/tdd/260926-bwk-task2-red-evidence.json` |

## Files Created/Modified

- `src/compliance/workflows/predicted_answer_io.py` — write_preprocess / write_analysis / remove_stale / origin heuristic
- `src/compliance/workflows/pipeline.py` — `_predicted_answer_path` uses shared I/O
- `src/compliance/workflows/claim_pipeline.py` — `_written_predicted_answer` uses shared I/O
- `tests/test_workflows/test_predicted_answer_io.py` — unit coverage for remove rules
- `tests/test_workflows/test_pipeline.py` — preserve analysis prediction + fraud source stamp
- `tests/test_workflows/test_claim_pipeline.py` — assert `source=analysis`

## Decisions Made

- Analysis-source files are never removed by preprocess; also preserve whenever `analysis_result.json` exists
- Legacy files without `source` but with fraud/Benford explanation remain removable
- `source` is stamped on JSON dump only (GroundTruth model unchanged)

## Deviations from Plan

### Auto-fixed Issues

None for the planned remove/write behavior.

### Bundled working-tree WIP (documented)

**1. [Rule 3 - Blocking] ClaimPipeline / test_claim_pipeline already diverged from HEAD**
- **Found during:** Task 2 staging
- **Issue:** Working tree already contained HITL/`False`-abstention updates to `claim_pipeline.py` and matching test fixtures relative to HEAD; staging the task files included that WIP so the new `source=analysis` assertion could run against the current analysis path
- **Fix:** Committed alongside the planned wiring (tests green for the full workflow suite)
- **Files modified:** `src/compliance/workflows/claim_pipeline.py`, `tests/test_workflows/test_claim_pipeline.py`
- **Committed in:** `0bb7cc1`, `aa87ffb`

**Total deviations:** 1 documented (bundled prior WIP)
**Impact on plan:** Plan goals met; extra WIP was prerequisite for current analysis tests, not scope creep on the stale-unlink fix.

## Issues Encountered

None beyond the pre-existing WIP noted above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

`make analyze` preprocess step should no longer delete analysis-authored `predicted_answer.json`. Eval FileNotFoundError from that race is addressed.

## Self-Check: PASSED

- FOUND: `src/compliance/workflows/predicted_answer_io.py`
- FOUND: commits `6aa85c9`, `b63a3df`, `0bb7cc1`, `aa87ffb`
- Verify: 52 passed (`test_predicted_answer_io` + `test_pipeline` + `test_claim_pipeline`)

---
*Phase: 260926-bwk-fix-the-stale-prediction-issue-preproces*
*Completed: 2026-09-26*
