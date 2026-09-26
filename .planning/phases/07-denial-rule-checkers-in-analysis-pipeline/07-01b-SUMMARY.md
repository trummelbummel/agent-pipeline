---
phase: 07-denial-rule-checkers-in-analysis-pipeline
plan: 01b
subsystem: testing
tags: [checking-config, authenticity_prompt, incomplete_prompt, test-fixtures]

requires:
  - phase: 07-denial-rule-checkers-in-analysis-pipeline
    provides: CheckingConfig.authenticity_prompt + incomplete_prompt required fields (07-01)
provides:
  - Secondary test AppConfig/CheckingConfig helpers supply authenticity_prompt and incomplete_prompt
  - YAML load_config fixtures in test_cli / test_pipeline include the new prompts
affects:
  - 07-02
  - 07-03

actuals:
  tokens: 2594
  tasks: 1
  commits: 3

plan_head_before: 3bf0459d8eb70c57cf5563f75c092c8ea570610b

tech-stack:
  added: []
  patterns:
    - "Secondary CheckingConfig placeholders match primary claim_pipeline helper (authenticity / incomplete)"

key-files:
  created: []
  modified:
    - tests/test_api/conftest.py
    - tests/test_workflows/test_orchestration.py
    - tests/test_workflows/test_pipeline.py
    - tests/test_evaluation/test_evaluator.py
    - tests/test_evaluation/test_analysis_stats.py
    - tests/test_evaluation/test_cli.py
    - tests/test_preprocessing/test_claim_batch.py
    - tests/test_preprocessing/test_integration.py

key-decisions:
  - "Identical placeholders authenticity/incomplete across secondary helpers for consistency with 07-01"
  - "YAML checking fixtures treated as CheckingConfig sites (Rule 1) so load_config tests collect"

patterns-established:
  - "Propagate required CheckingConfig fields through both Python constructors and inline YAML fixtures"

requirements-completed: [R023]

coverage:
  - id: D1
    description: "Secondary CheckingConfig helpers include authenticity_prompt and incomplete_prompt"
    requirement: R023
    verification:
      - kind: unit
        ref: "uv run pytest tests/test_api tests/test_evaluation tests/test_workflows/test_orchestration.py tests/test_workflows/test_pipeline.py tests/test_preprocessing/test_claim_batch.py -q"
        status: pass
    human_judgment: false

duration: 3min
completed: 2026-09-26
status: complete
---

# Phase 07 Plan 01b: Secondary CheckingConfig Prompt Propagation Summary

**Propagated required authenticity_prompt / incomplete_prompt across all secondary test AppConfig helpers and YAML checking fixtures so api/evaluation/orchestration/preprocessing suites collect after 07-01.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-09-26T10:59:28Z
- **Completed:** 2026-09-26T11:01:42Z
- **Tasks:** 1/1
- **Files modified:** 8 test modules (+ WINDOWS ledger)

## Accomplishments

- Every secondary `CheckingConfig(...)` under the listed helpers now passes `authenticity_prompt="authenticity"` and `incomplete_prompt="incomplete"`
- Inline YAML `checking:` blocks in `test_cli.py` and `test_pipeline.py` updated so `load_config` no longer raises ValidationError
- Primary phase suites (checker / claim_pipeline / settings minus pre-existing other_label drift) stay green with secondary modules

## Task Commits

1. **Task 1: Propagate CheckingConfig new prompts across remaining test helpers** - `5fad912` (test)

**Plan metadata:** `e671a02` (docs: complete plan)

## Files Created/Modified

- `tests/test_api/conftest.py` — API AppConfig fixture CheckingConfig prompts
- `tests/test_workflows/test_orchestration.py` — orchestration helper CheckingConfig prompts
- `tests/test_workflows/test_pipeline.py` — Python helper + two YAML checking fixtures
- `tests/test_evaluation/test_evaluator.py` — evaluator helper CheckingConfig prompts
- `tests/test_evaluation/test_analysis_stats.py` — analysis_stats helper CheckingConfig prompts
- `tests/test_evaluation/test_cli.py` — YAML checking fixture prompts (Rule 1)
- `tests/test_preprocessing/test_claim_batch.py` — claim_batch helper CheckingConfig prompts
- `tests/test_preprocessing/test_integration.py` — integration helper CheckingConfig prompts

## Decisions Made

- Used the same `"authenticity"` / `"incomplete"` placeholder strings as 07-01's `test_claim_pipeline` helper
- Extended scope to YAML fixtures that construct CheckingConfig via `load_config` (same ValidationError class)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] YAML checking fixtures missing new required prompts**
- **Found during:** Task 1 (verify)
- **Issue:** `test_cli.py` and two inline YAML configs in `test_pipeline.py` omitted `authenticity_prompt` / `incomplete_prompt`, causing `load_config` ValidationError after 07-01
- **Fix:** Added the two prompt keys to each YAML checking block
- **Files modified:** `tests/test_evaluation/test_cli.py`, `tests/test_workflows/test_pipeline.py`
- **Commit:** `5fad912`

### Deferred Issues

- `test_analysis_coverage_other_label_is_false`: pre-existing `config.yaml` `other_label: "None"` vs test expecting `"False"` (already on WINDOWS ledger; not caused by this plan)
- `mypy src/compliance/`: 7 pre-existing errors; 07-01b changed no production code

## TDD Gate Compliance

Task marked `tdd="true"` but `task.is-behavior-adding` returned false (`has_source_files: false` — test-only glue). Full RED/GREEN/REFACTOR cycle exempt; single test commit.

## Known Stubs

None.

## Threat Flags

None — test fixtures only; no new runtime surface.

## Self-Check: PASSED

- FOUND: all eight modified test files
- FOUND: commit `5fad912`
- FOUND: authenticity_prompt on every `CheckingConfig(` site under `tests/`
