---
phase: 260929-lni-sr-006-ground-truth-first-evaluation-ali
plan: 01
subsystem: evaluation
tags: [ground-truth-first, coverage_rate, raw-vs-policy, confusion-matrix, ClaimStatus, SR-006]

requires:
  - phase: 260929-l16-sr-005-transactional-run-scoped-artifact
    provides: MixedGenerationError / generation_mismatch guard preserved end to end
provides:
  - Ground-truth-first Evaluator population from data_dir with typed ClaimOutcome taxonomy
  - Matrix-derived named MetricSets raw and policy over one population with unscored column
  - coverage_rate and reshaped evaluation_metrics / confusion_matrix artifacts
affects: [make evaluation, SR-007, docs measured-batch refresh]

actuals:
  tokens: 21089
  tasks: 3
  commits: 4
plan_head_before: 042e064dbdc69728e615a974b0e8aa77b0c0d9cf

tech-stack:
  added: []
  patterns:
    - "Discover denominator from data_dir; missing/invalid predictions occupy unscored column"
    - "Named MetricSet scalars derived from one matrix (accuracy = trace/total)"
    - "raw vs policy match callables over the same ClaimOutcome list"

key-files:
  created: []
  modified:
    - src/evaluation/evaluator.py
    - src/evaluation/__main__.py
    - src/evaluation/visualization.py
    - src/evaluation/analysis_stats.py
    - src/compliance/config/settings.py
    - config.yaml
    - tests/test_evaluation/test_evaluator.py
    - tests/test_evaluation/test_cli.py
    - tests/test_config/test_settings.py
    - README.md
    - LOGIC.md
    - .gsd/review_backlog.md

key-decisions:
  - "D-01: Missing prediction with GT present counts incorrect; also report coverage_rate"
  - "D-02: Acceptable-decision credit is a second named metric (raw vs policy)"
  - "P-01: Denominator = readable in-vocabulary answer.json under data_dir; invalid GT excluded"
  - "P-02: One matrix per named metric; accuracy/F1 derived from cells; unscored column in FN"
  - "P-03: evaluation.unscored_label config-rooted (default NO_PREDICTION), validated unique"
  - "P-04: Flat unnamed accuracy/f1/n_evaluated removed — not aliased"
  - "P-05: One PNG renders the raw matrix; title carries both accuracies + coverage + HITL"
  - "P-06: Results-only claims reported as unmatched_prediction, outside every metric"
  - "P-07: analysis_stats keeps results_dir discovery; docstring states different population"
  - "P-08: evaluate_claim stays strict; soft classification is batch-only"

patterns-established:
  - "ClaimStatus(str, Enum) + frozen ClaimOutcome / MetricSet / EvaluationPopulation"
  - "UnscoredLabelCollisionError + EvaluationConfig._validated_metric_vocabulary at load"

requirements-completed: [SR-006]

coverage:
  - id: D1
    description: Ground-truth-only claim (no results folder) enters population, counted incorrect, coverage_rate 0.5
    requirement: SR-006
    verification:
      - kind: unit
        ref: tests/test_evaluation/test_evaluator.py::test_ground_truth_without_results_folder_is_counted_incorrect
        status: pass
      - kind: unit
        ref: tests/test_evaluation/test_cli.py::test_cli_writes_metrics_json
        status: pass
    human_judgment: false
  - id: D2
    description: Accuracy, F1 and matrix share one population by construction (matrix total == n_ground_truth)
    requirement: SR-006
    verification:
      - kind: unit
        ref: tests/test_evaluation/test_evaluator.py::test_matrix_total_equals_population
        status: pass
    human_judgment: false
  - id: D3
    description: Raw vs policy diverge on acceptable_decision; same n and matrix total
    requirement: SR-006
    verification:
      - kind: unit
        ref: tests/test_evaluation/test_evaluator.py::test_policy_metric_credits_acceptable_decision
        status: pass
      - kind: unit
        ref: tests/test_evaluation/test_evaluator.py::test_raw_and_policy_share_one_population
        status: pass
    human_judgment: false
  - id: D4
    description: SR-005 mixed-generation refusal preserved at evaluate_claim; batch counts invalid_prediction
    requirement: SR-006
    verification:
      - kind: unit
        ref: tests/test_evaluation/test_evaluator.py::test_evaluate_claim_rejects_mixed_generation
        status: pass
      - kind: unit
        ref: tests/test_evaluation/test_evaluator.py::test_batch_counts_mixed_generation_as_incorrect
        status: pass
      - kind: unit
        ref: tests/test_evaluation/test_evaluator.py::test_batch_scores_claim_without_manifest
        status: pass
    human_judgment: false

duration: 9min
completed: 2026-09-29
status: complete
---

# Quick 260929-lni: SR-006 Ground-truth-first evaluation Summary

**Evaluation discovers from `data_dir`, counts missing predictions as incorrect with `coverage_rate`, and publishes matrix-derived `raw` and `policy` metrics over one documented population.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-09-29T13:46:17Z
- **Completed:** 2026-09-29T13:55:00Z
- **Tasks:** 3 (+ 1 auto-fix commit for mypy baseline)
- **Files modified:** 12 tracked (+ gitignored backlog)

## Baselines vs final gates

| Gate | Baseline (Task 1 start) | Final |
|------|-------------------------|-------|
| `pytest -q --cov` (fast lane) | 391 passed, 91.16% | 401 passed, 91.30% |
| `ruff check --no-fix src tests` | clean | clean |
| `ruff format --check` (scoped dirs) | 14 files clean | clean |
| `mypy src` | 0 errors | 0 errors |
| `mypy tests/test_evaluation` | 20 errors | **4** errors (analysis_stats conftest noise only) |

## Population contract (as implemented)

| Ground truth | Prediction | Status | In population | Matrix cell |
|--------------|------------|--------|---------------|-------------|
| readable, in labels | scored + generation valid | `scored` | yes | `(gt, effective_pred)` |
| readable, in labels | absent | `missing_prediction` | yes | `(gt, unscored)` |
| readable, in labels | unparseable / OOV / mixed-gen | `invalid_prediction` | yes | `(gt, unscored)` |
| absent / unparseable / OOV | anything | `invalid_ground_truth` | no | none |
| no data_dir folder | present under results_dir | `unmatched_prediction` | no | none |

`coverage_rate` = `n_scored / n_ground_truth`. Named metrics: `raw` (exact equality) and `policy` (acceptable-decision credit + A5 remap).

## Behavior-change register (intended)

- `evaluation_metrics.json` / `confusion_matrix.json` reshape: `population`, `raw` / `policy` blocks, `outcomes`, `column_labels` one wider than `labels`.
- Headline accuracy drops for two independent reasons: wider GT-first denominator, and un-credited `raw` headline (policy is separate).
- Confusion matrix is no longer square.
- Flat `accuracy` / `f1_macro` / `n_evaluated` / `y_true` / `y_pred` / `matches` fields removed (P-04).

## Accomplishments

- Ground-truth-first discovery; missing predictions counted incorrect with attributable outcomes.
- Matrix-derived raw + policy MetricSets; config-rooted `unscored_label` with load-time collision rejection.
- SR-005 MixedGenerationError preserved at single-claim boundary; batch records invalid_prediction.
- Docs + gitignored backlog closed for SR-006.

## Task Commits

1. **Task 1 (tracer):** `e7a6942` — feat(SR-006): evaluate the ground-truth population and count missing predictions
2. **Task 2:** `2ff619e` — feat(SR-006): report raw and acceptable-policy metrics over one population
3. **Task 3:** `d666b14` — feat(SR-006): document the ground-truth-first evaluation population
4. **Deviation fix:** `7941513` — fix(SR-006): drop conftest TYPE_CHECKING import for mypy baseline

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] mypy tests/test_evaluation exceeded 20-error baseline**
- **Found during:** Task 3 gate / close-out
- **Issue:** New tests reused `from conftest import MinimalAppConfigFactory` under `TYPE_CHECKING`, adding one `no-any-unimported` error per new test function (28 total vs 20 baseline).
- **Fix:** Alias `MinimalAppConfigFactory = Callable[..., AppConfig]` in `test_evaluator.py` (no conftest import).
- **Files modified:** `tests/test_evaluation/test_evaluator.py`
- **Commit:** recorded above as fix(SR-006)

## Auth Gates

None.

## Known Stubs

None.

## Threat Flags

None beyond the plan's `<threat_model>` mitigations (T-SR006-01..08).

## Follow-ups

- SR-007 owns read-only GET plus idempotent analysis.
- SR-009 owns upload/path hardening.
- SR-013 owns the policy-engine extract.
- Re-run `make analyze` + `make evaluation` to re-measure the take-home batch under the new population (docs mark legacy measured numbers explicitly).

## Self-Check: PASSED

- `src/evaluation/evaluator.py` FOUND (ClaimStatus, EvaluationPopulation, coverage_rate, policy)
- Commits `e7a6942`, `2ff619e`, `d666b14`, `7941513` FOUND
- SUMMARY at `.planning/quick/260929-lni-sr-006-ground-truth-first-evaluation-ali/260929-lni-SUMMARY.md`
- `.gsd/review_backlog.md` SR-006 checked `[x]`; never staged
- Final docs commit `87723b3`
