---
phase: 260926-fph-add-two-analysis-checkers-that-yield-unc
plan: 01
subsystem: analysis
tags: [claim-pipeline, uncertain, date-checkers, config]

requires:
  - phase: 04
    provides: ClaimPipeline checker node + CheckingConfig
provides:
  - Deterministic departure-proximity UNCERTAIN (config-driven n)
  - Deterministic multiple-OCR-dates UNCERTAIN
  - Early return skipping LLM Checker modes when either flag fires
affects: [evaluation, claim-analysis]

actuals:
  tokens: 8155
  tasks: 2
  commits: 3

plan_head_before: 2d6d8c1779432d394701ffa753435e095d466427

tech-stack:
  added: []
  patterns:
    - "Deterministic date flags computed before Checker LLM; early-return omits LLM state keys"
    - "Decision-fold UNCERTAIN date flags before DENY from _violated_checkers"

key-files:
  created: []
  modified:
    - config.yaml
    - src/compliance/config/settings.py
    - src/compliance/workflows/claim_pipeline.py
    - tests/test_workflows/test_claim_pipeline.py
    - tests/test_config/test_settings.py

key-decisions:
  - "n = checking.departure_uncertain_within_days default 14 on CheckingConfig"
  - "Reference today from BookingData.current_date else date.today(); helpers take explicit today"
  - "Both date flags always computed; either True skips LLM checkers"
  - "Decision precedence: coverage abstention → departure_within_days → multiple_document_dates → DENY → identity_unclear → APPROVE"

patterns-established:
  - "Shared _parse_calendar_date / _unique_calendar_dates for booking + OCR text"
  - "analysis_result payload passthrough for departure_within_days / multiple_document_dates when present in state"

requirements-completed: []

coverage:
  - id: D1
    description: Departure within n days of reference today yields UNCERTAIN departure_within_days and skips LLM checkers
    verification:
      - kind: unit
        ref: tests/test_workflows/test_claim_pipeline.py::test_uncertain_departure_within_days_skips_llm_checkers
        status: pass
      - kind: unit
        ref: tests/test_config/test_settings.py::test_load_config_reads_checking_section
        status: pass
    human_judgment: false
  - id: D2
    description: Two distinct OCR calendar days yield UNCERTAIN multiple_document_dates and skip LLM checkers
    verification:
      - kind: unit
        ref: tests/test_workflows/test_claim_pipeline.py::test_uncertain_multiple_document_dates_skips_llm_checkers
        status: pass
    human_judgment: false
  - id: D3
    description: Combined flags persist both; explanation prefers departure_within_days
    verification:
      - kind: unit
        ref: tests/test_workflows/test_claim_pipeline.py::test_departure_within_and_multiple_document_dates_prefer_departure
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-09-26
status: complete
---

# Phase 260926-fph Plan 01: UNCERTAIN date checkers Summary

**Deterministic departure-proximity and multi-OCR-date checkers yield UNCERTAIN and short-circuit expensive LLM Checker modes.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-09-26T09:21:45Z
- **Completed:** 2026-09-26T09:29:31Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Config key `checking.departure_uncertain_within_days` (default 14) on `CheckingConfig`
- Shared calendar-date parsers + `_departure_within_days` / `_has_multiple_document_dates`
- `_checker_results` early-returns omitting LLM keys when either date flag is true
- `_decision_from_state` prefers date UNCERTAIN explanations before DENY

## Task Commits

1. **Task 1 RED:** `c880c04` — test(260926-fph-01): add failing tests for departure UNCERTAIN
2. **Task 1 GREEN:** `36e258c` — feat(260926-fph-01): departure proximity UNCERTAIN with LLM early skip
3. **Task 2 tests:** `d36caa8` — test(260926-fph-01): cover multiple_document_dates UNCERTAIN path

_No docs/SUMMARY commit (orchestrator owns that)._

## Files Created/Modified

- `config.yaml` — `departure_uncertain_within_days: 14`
- `src/compliance/config/settings.py` — `CheckingConfig.departure_uncertain_within_days`; `ClassificationConfig.positive_labels` / `abstention_labels` (Rule 3 — already called by pipeline)
- `src/compliance/workflows/claim_pipeline.py` — date helpers, early return, decision fold, payload keys
- `tests/test_workflows/test_claim_pipeline.py` — departure / multiple-dates / combined precedence tests
- `tests/test_config/test_settings.py` — assert config key loads as int 14

## Decisions Made

- Honor D-01..D-04 from plan exactly (inclusive day delta; both flags always computed; precedence before DENY)
- Prefer edit-over-create: helpers live as module-level privates in `claim_pipeline.py`
- Task 1 GREEN also wired multiple-document-dates (D-03 requires both flags before early return); Task 2 added regression coverage only

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] ClassificationConfig.positive_labels / abstention_labels**
- **Found during:** Task 1 GREEN
- **Issue:** Committed `claim_pipeline` already called these methods but `CheckingConfig`/settings HEAD lacked them, so scoped GREEN would leave the tree broken.
- **Fix:** Added the two helpers on `ClassificationConfig` alongside the new checking field.
- **Files modified:** `src/compliance/config/settings.py`
- **Commit:** `36e258c`

**2. [Rule 2 - Critical] Multiple-document-dates implemented in Task 1**
- **Found during:** Task 1 GREEN (D-03 early-return contract)
- **Issue:** Plan split D-02 into Task 2, but early-return semantics require both flags before skipping LLM.
- **Fix:** Implemented `_has_multiple_document_dates` + decision-fold step in Task 1; Task 2 shipped tests only (no second feat commit).
- **Files modified:** `claim_pipeline.py`, Task 2 tests
- **Commit:** `36e258c` (impl), `d36caa8` (tests)

### TDD notes

- Task 1: RED evidence `RED_EVIDENCE_OK` (`.planning/tdd/260926-fph-task1-red-evidence.json`)
- Task 2: no intentional RED — feature already present from Task 1; documented in `.planning/tdd/260926-fph-task2-red-evidence.json`
- No REFACTOR commit (implementation stayed lean)

## Self-Check: PASSED

- FOUND: config.yaml, settings.py, claim_pipeline.py, test_claim_pipeline.py
- FOUND: c880c04, 36e258c, d36caa8
