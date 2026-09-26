---
phase: 260926-f9c-in-evaluation-also-run-statistics-over-a
plan: 01
subsystem: evaluation
tags: [analysis_stats, evaluation, visualization, PIL, TDD]

requires:
  - phase: 06-prediction-evaluation
    provides: evaluation CLI, Evaluator discovery, confusion-matrix PNG writer
  - phase: 04-claim-analysis-pipeline
    provides: analysis_result.json under results_dir
provides:
  - aggregate_analysis_stats over results_dir/*/analysis_result.json
  - analysis_stats.json + multi-panel bar-chart PNG on every evaluation run
affects: [make-evaluation, operators-inspecting-analysis-mix]

actuals:
  tokens: 8324
  tasks: 2
  commits: 6
plan_head_before: 577070aa916ad58c6ff32fe5122b9e27ce848d04

tech-stack:
  added: []
  patterns:
    - "Focused analysis_stats module beside Evaluator (no pred/gt scoring)"
    - "Present-only boolean checker rates; soft-skip invalid analysis JSON"
    - "PIL multi-panel horizontal bars (top-N=12) without matplotlib"

key-files:
  created:
    - src/evaluation/analysis_stats.py
    - tests/test_evaluation/test_analysis_stats.py
  modified:
    - src/compliance/config/settings.py
    - src/evaluation/__main__.py
    - src/evaluation/visualization.py
    - config.yaml
    - Makefile
    - tests/test_evaluation/test_cli.py

key-decisions:
  - "New analysis_stats.py module instead of bloating Evaluator"
  - "Boolean checkers use fixed allowlist; absent keys omit from denominators"
  - "One multi-panel PNG with prefixed coverage/reason/document label keys"

patterns-established:
  - "Evaluation CLI always writes analysis stats JSON+PNG even when n_claims=0"

requirements-completed: []

coverage:
  - id: D1
    description: Aggregator returns sorted claim_ids, decision/checker/label/explanation counts
    verification:
      - kind: unit
        ref: tests/test_evaluation/test_analysis_stats.py#test_aggregate_two_claims_decisions_and_sorted_ids
        status: pass
    human_judgment: false
  - id: D2
    description: Soft-skip missing/invalid analysis_result; empty discovery writes empty-but-valid stats
    verification:
      - kind: unit
        ref: tests/test_evaluation/test_analysis_stats.py#test_aggregate_soft_skips_missing_and_invalid
        status: pass
      - kind: unit
        ref: tests/test_evaluation/test_cli.py#test_cli_exit_zero_on_empty_batch
        status: pass
    human_judgment: false
  - id: D3
    description: CLI writes analysis_stats.json beside evaluation metrics using config filenames
    verification:
      - kind: unit
        ref: tests/test_evaluation/test_cli.py#test_cli_writes_metrics_json
        status: pass
    human_judgment: false
  - id: D4
    description: write_analysis_stats_png produces PNG magic including empty stats
    verification:
      - kind: unit
        ref: tests/test_evaluation/test_analysis_stats.py#test_write_analysis_stats_png_writes_png_magic
        status: pass
      - kind: unit
        ref: tests/test_evaluation/test_analysis_stats.py#test_write_analysis_stats_png_empty_stats
        status: pass
    human_judgment: false
  - id: D5
    description: CLI writes both confusion PNG and analysis bar-chart PNG
    verification:
      - kind: unit
        ref: tests/test_evaluation/test_cli.py#test_cli_writes_metrics_json
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-09-26
status: complete
---

# Phase 260926-f9c: Analysis-result evaluation stats Summary

**`make evaluation` / `python -m evaluation` now aggregates `analysis_result.json` across results_dir and writes `analysis_stats.json` plus a multi-panel PIL bar-chart PNG beside the existing confusion-matrix artifacts.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-09-26T09:01:34Z
- **Completed:** 2026-09-26T09:08:29Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- Config-externalized `analysis_stats_artifact` / `analysis_visualization_artifact` on `EvaluationConfig`
- Aggregator with present-only checker rates, flattened label frequencies, soft-skip loads
- Multi-panel PIL bar chart (decisions, checker rates, prefixed labels, explanations)

## Task Commits

Each TDD task used RED → GREEN commits:

1. **Task 1 RED:** `ca3aaa5` — failing aggregator + CLI stats JSON tests (stub module)
2. **Task 1 GREEN:** `cc2364f` — `aggregate_analysis_stats` + CLI JSON wiring
3. **Task 2 RED:** `5889f7c` — failing PNG writer + CLI viz assertions
4. **Task 2 GREEN:** `c0b13ea` — `write_analysis_stats_png` + CLI PNG wiring
5. **Scope fix:** `d0667f1` — config.yaml evaluation keys only
6. **Scope fix:** `03fa7a2` — settings/Makefile evaluation-stats only

## Files Created/Modified

- `src/evaluation/analysis_stats.py` — `AnalysisStats` + `aggregate_analysis_stats`
- `src/evaluation/visualization.py` — `write_analysis_stats_png` multi-panel bars
- `src/evaluation/__main__.py` — write stats JSON + analysis PNG after evaluate
- `src/compliance/config/settings.py` — EvaluationConfig artifact filename fields
- `config.yaml` / `Makefile` — artifact names + evaluation help comment
- `tests/test_evaluation/test_analysis_stats.py` / `test_cli.py` — unit + CLI coverage

## Decisions Made

- Keep stats aggregation out of `Evaluator` (pred vs GT only)
- Soft-skip missing/invalid analysis JSON with WARNING branch log; always write artifacts
- Cap bar categories at top-12; merge label series with `coverage:` / `reason:` / `document:` prefixes

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Accidental staging of pre-existing WIP into GREEN commits**
- **Found during:** Task 1 GREEN / post-commit review
- **Issue:** Dirty `config.yaml`, `settings.py`, and `Makefile` WIP was staged with plan files
- **Fix:** Follow-up commits restored plan-scoped diffs; WIP returned to working tree unstaged
- **Files modified:** `config.yaml`, `src/compliance/config/settings.py`, `Makefile`
- **Commits:** `d0667f1`, `03fa7a2`

## TDD Gate Compliance

| Task | RED | GREEN | Evidence |
|------|-----|-------|----------|
| 1 | `ca3aaa5` | `cc2364f` | `.planning/tdd/260926-f9c-task1-red-evidence.json` → RED_EVIDENCE_OK |
| 2 | `5889f7c` | `c0b13ea` | `.planning/tdd/260926-f9c-task2-red-evidence.json` → RED_EVIDENCE_OK |

Tracer feedback gate (Task 1): re-ran verify after GREEN — 5 passed.

## Self-Check: PASSED

- `src/evaluation/analysis_stats.py` — FOUND
- `src/evaluation/visualization.py` contains `write_analysis_stats_png` — FOUND
- Commits `ca3aaa5`, `cc2364f`, `5889f7c`, `c0b13ea`, `d0667f1`, `03fa7a2` — FOUND
- `pytest tests/test_evaluation/test_analysis_stats.py tests/test_evaluation/test_cli.py` — 7 passed
