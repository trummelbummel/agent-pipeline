---
phase: 06-prediction-evaluation
plan: 01
subsystem: evaluation
tags: [evaluation, metrics, f1, confusion-matrix, hatch, pydantic-config]

requires:
  - phase: 03-preprocessing-pipeline-orchestration
    provides: results_dir / data_dir path roots and _validate_claim_dir_name
  - phase: 01-claim-preprocessing-pipeline
    provides: AnswerReader / GroundTruth schema
provides:
  - hatch-packaged evaluation.Evaluator for single-claim scoring
  - EvaluationConfig (labels + metrics_artifact) on AppConfig
  - Hand-rolled confusion matrix, accuracy, macro F1
affects:
  - 06-02 batch discovery and CLI

actuals:
  tokens: 6764
  tasks: 2
  commits: 4

plan_head_before: dfdf0dc8e5be07f15f70c7a152e635d2b420618a

tech-stack:
  added: []
  patterns:
    - "Hand-rolled metrics (no sklearn) with config.evaluation.labels as matrix axes"
    - "A5 macro F1: mean over all labels; zero-support → 0.0; effective pred remaps matches to true label"
    - "Path safety via _validate_claim_dir_name before joining claim_id under config roots"

key-files:
  created:
    - src/evaluation/__init__.py
    - src/evaluation/evaluator.py
    - tests/test_evaluation/__init__.py
    - tests/test_evaluation/test_evaluator.py
  modified:
    - pyproject.toml
    - config.yaml
    - src/compliance/config/settings.py
    - src/compliance/config/__init__.py
    - tests/test_config/test_settings.py

key-decisions:
  - "Unknown pred/gt decisions raise ValueError at evaluate_claim boundary (T-06-04)"
  - "Package lives at src/evaluation (hatch), importable as evaluation — parallel to src/api"
  - "Score predicted_answer.json vs answer.json only — not analysis_result.json"

patterns-established:
  - "EvaluationResult frozen dataclass with claim_ids, y_true/y_pred, matches, matrix, accuracy, f1_macro"
  - "Private helpers named after products: _match_decision, _confusion_matrix, _macro_f1, _effective_pred_label"

requirements-completed: [TBD]

coverage:
  - id: D1
    description: "src/evaluation hatch-packaged and importable as evaluation.Evaluator"
    requirement: TBD
    verification:
      - kind: unit
        ref: "tests/test_evaluation/test_evaluator.py#test_evaluator_import_requires_no_network"
        status: pass
      - kind: other
        ref: "rg src/evaluation pyproject.toml hatch packages"
        status: pass
    human_judgment: false
  - id: D2
    description: "Single-claim Evaluator returns accuracy and macro F1 vs predicted_answer/answer.json"
    requirement: TBD
    verification:
      - kind: unit
        ref: "tests/test_evaluation/test_evaluator.py#test_evaluate_claim_perfect_match"
        status: pass
      - kind: unit
        ref: "tests/test_evaluation/test_evaluator.py#test_evaluate_claim_mismatch"
        status: pass
    human_judgment: false
  - id: D3
    description: "EvaluationConfig labels + metrics_artifact loaded from config.yaml"
    requirement: TBD
    verification:
      - kind: unit
        ref: "tests/test_config/test_settings.py#test_load_config_reads_evaluation_section"
        status: pass
    human_judgment: false
  - id: D4
    description: "A4 acceptable_decision match + A5 matrix/F1 edge cases; unknown labels rejected"
    requirement: TBD
    verification:
      - kind: unit
        ref: "tests/test_evaluation/test_evaluator.py#test_acceptable_decision_counts_as_match"
        status: pass
      - kind: unit
        ref: "tests/test_evaluation/test_evaluator.py#test_unknown_pred_label_raises"
        status: pass
    human_judgment: false
  - id: D5
    description: "Unsafe claim_id raises ValueError before file reads (T-06-01)"
    requirement: TBD
    verification:
      - kind: unit
        ref: "tests/test_evaluation/test_evaluator.py#test_refuses_unsafe_claim_id"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-09-25
status: complete
---

# Phase 06 Plan 01: One-Claim Evaluator Tracer Summary

**Hatch-packaged `evaluation.Evaluator` scores one claim's `predicted_answer.json` against `answer.json` with config-driven labels, hand-rolled confusion matrix, accuracy, and macro F1**

## Performance

- **Duration:** 5 min
- **Started:** 2026-09-25T16:08:33Z
- **Completed:** 2026-09-25T16:14:17Z
- **Tasks:** 2
- **Files modified:** 15

## Accomplishments

- Packaged `src/evaluation` via hatch; importable as `evaluation` without Ollama/network
- Added required `EvaluationConfig` (`labels`, `metrics_artifact`) on `AppConfig` + `config.yaml`
- Single-claim `evaluate_claim` with A4 match (including `acceptable_decision`) and A5 macro F1
- Path-safety and unknown-label ValueError gates; logs claim_id + metric scalars only

## Task Commits

Each task was committed atomically (TDD RED → GREEN):

1. **Task 1 RED:** `af2cbef` — test(06-01): add failing tests for one-claim Evaluator
2. **Task 1 GREEN:** `23f4ee6` — feat(06-01): implement one-claim Evaluator with config-driven metrics
3. **Task 2 RED:** `98e8a20` — test(06-01): add failing tests for acceptable_decision and unknown labels
4. **Task 2 GREEN:** `c95bd6e` — feat(06-01): reject unknown decision labels at evaluate boundary

## TDD Gate Compliance

| Task | RED | GREEN | REFACTOR | Status |
|------|-----|-------|----------|--------|
| 1 | ✓ `af2cbef` (RED_EVIDENCE_OK) | ✓ `23f4ee6` | — | Pass |
| 2 | ✓ `98e8a20` (RED_EVIDENCE_OK) | ✓ `c95bd6e` | — | Pass |

RED evidence: `.planning/tdd/260925-06-01-task1-red-evidence.json`, `.planning/tdd/260925-06-01-task2-red-evidence.json`

## Files Created/Modified

- `src/evaluation/evaluator.py` — Evaluator + EvaluationResult
- `src/evaluation/__init__.py` — public exports
- `src/compliance/config/settings.py` — EvaluationConfig on AppConfig
- `config.yaml` — evaluation.labels + metrics_artifact
- `pyproject.toml` — hatch packages includes src/evaluation
- `tests/test_evaluation/test_evaluator.py` — tracer + edge-case tests
- `tests/test_config/test_settings.py` — evaluation section load test
- AppConfig test helpers updated to include evaluation (pipeline/batch/integration)

## Decisions Made

- Unknown decisions raise ValueError at the evaluate_claim boundary (preferred over silent matrix drop)
- Package path locked at `src/evaluation` per ROADMAP (not under compliance/)
- Score only GroundTruth-shaped predicted_answer vs answer — never analysis_result.json

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated AppConfig test helpers for required evaluation**
- **Found during:** Task 1 GREEN
- **Issue:** Making `AppConfig.evaluation` required broke existing `_config()` helpers in workflow/preprocessing tests
- **Fix:** Added `EvaluationConfig(...)` to test helpers and minimal CLI YAML fixtures
- **Files modified:** `tests/test_workflows/test_pipeline.py`, `tests/test_workflows/test_claim_pipeline.py`, `tests/test_preprocessing/test_claim_batch.py`, `tests/test_preprocessing/test_integration.py`
- **Verification:** Plan verify pytest green
- **Committed in:** `23f4ee6`

**2. [Incidental] Pre-staged `src/compliance/tools/benford.py` landed in Task 1 RED commit**
- **Found during:** Task 1 RED commit
- **Issue:** File was already in the index before staging; included in `af2cbef`
- **Fix:** None (unrelated dirty tree); subsequent commits staged explicitly after `git reset HEAD`
- **Impact:** Cosmetic — benford change unrelated to evaluation tracer

---

**Total deviations:** 2 (1 blocking auto-fix, 1 incidental staging)
**Impact on plan:** Helper updates required for suite collect; no scope creep into batch/CLI (06-02)

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Single-claim path ready for 06-02 batch discovery + CLI/metrics artifact write
- No blockers

## Verification Results

- `uv run pytest tests/test_evaluation/test_evaluator.py tests/test_config/test_settings.py -q` — 20+ passed (8 evaluator + settings)
- `uv run mypy src/evaluation/ src/compliance/config/` — Success
- Final Task 2: 8 passed in test_evaluator.py

## Self-Check: PASSED

- [x] `src/evaluation/evaluator.py` exists with `class Evaluator`
- [x] `src/compliance/config/settings.py` has `class EvaluationConfig`
- [x] Commits af2cbef, 23f4ee6, 98e8a20, c95bd6e present in git log
- [x] Plan verify commands green

---
*Phase: 06-prediction-evaluation*
*Completed: 2026-09-25*
