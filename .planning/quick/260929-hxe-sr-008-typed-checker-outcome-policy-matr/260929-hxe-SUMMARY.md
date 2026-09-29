---
status: complete
phase: 260929-hxe-sr-008-typed-checker-outcome-policy-matr
plan: "01"
subsystem: llm/checker
tags: [check-outcome, policy-matrix, transport-retry, sr-008]
dependency-graph:
  requires: []
  provides:
    - CheckOutcome
    - checker_outcomes
    - TransportRetryConfig
    - chat_content_with_retry
  affects: [claim_pipeline decision fold, analysis_result.json]
tech-stack:
  added: []
  patterns:
    - "Typed CheckOutcome with one per-mode polarity table; ClaimPipeline folds outcomes (VIOLATION > ERROR > identity ABSTAIN)"
    - "Bounded TRANSPORT_ERRORS retry via chat_content_with_retry; exhaustion → ERROR → UNCERTAIN"
key-files:
  created: []
  modified:
    - src/compliance/llm/checker.py
    - src/compliance/llm/chat.py
    - src/compliance/config/settings.py
    - config.yaml
    - src/compliance/workflows/claim_pipeline.py
    - tests/test_llm/test_checker.py
    - tests/test_workflows/test_claim_pipeline.py
    - .gsd/review_backlog.md
decisions:
  - "D-01: PASS|VIOLATION|ABSTAIN|ERROR; ERROR→UNCERTAIN+HITL; containment ERROR record-only; VIOLATION beats ERROR"
  - "D-02: identity VIOLATION only when both names extracted and distance exceeded"
  - "D-03: transport retry then ERROR; claim still persisted UNCERTAIN"
  - "P-01..P-07 planner discretion as locked in PLAN.md"
actuals:
  tokens: 21881
  tasks: 3
  commits: 3
  plan_head_before: "f5d99cc316a9ace89012add59b8493b8d9c54528"
requirements-completed: [SR-008]
metrics:
  duration: "~7min"
  completed: 2026-09-29
---

# Phase 260929-hxe Plan 01: Typed checker outcome policy matrix (SR-008) Summary

Checker returns a typed `CheckOutcome` (PASS | VIOLATION | ABSTAIN | ERROR); ClaimPipeline folds that model into DENY/UNCERTAIN/APPROVE with an explicit precedence, persists `checker_outcomes`, and retries transport failures via `checking.transport_retry` before recording ERROR so claims get UNCERTAIN instead of being skipped.

## Performance

- **Duration:** ~7 min wall clock for this executor pass (Task 1 WIP was already largely present)
- **Started:** 2026-09-29T12:17:31Z
- **Completed:** 2026-09-29T12:24:58Z
- **Tasks:** 3/3
- **Files modified:** 7 source/test/config (+ gitignored backlog)

## Accomplishments

- Replaced mode-dependent bool / fail-closed defaults with `CheckOutcome` + `_MODE_POLARITY`
- Pipeline decision fold: VIOLATION → DENY, ERROR → UNCERTAIN `checker_error:<modes>` (containment ERROR record-only), identity ABSTAIN → UNCERTAIN
- Configurable transport retry (`TransportRetryConfig` / `chat_content_with_retry`) wired through Checker and ClaimPipeline
- Policy matrix (30 rows) + identity (5) + precedence (4) covered by parametrized pipeline tests
- SR-008 checked off in `.gsd/review_backlog.md` with steering recorded

## Task Commits

1. **Task 1: typed CheckOutcome through pipeline** — `1bd8d33` (feat)
2. **Task 2: transport retry then ERROR** — `fbd1f28` (feat)
3. **Task 3: pipeline wiring + transport column + close SR-008** — `ff6da56` (feat)

## Files Created/Modified

- `src/compliance/llm/checker.py` — `CheckOutcome`, polarity table, structured name extraction, transport-aware chat
- `src/compliance/llm/chat.py` — `TRANSPORT_ERRORS`, `chat_content_with_retry`
- `src/compliance/config/settings.py` — `TransportRetryConfig` under `CheckingConfig`
- `config.yaml` — `checking.transport_retry` (+ preserved SR-004 False abstention labels)
- `src/compliance/workflows/claim_pipeline.py` — `checker_outcomes`, outcome fold, `transport_retry=` wiring
- `tests/test_llm/test_checker.py` — CheckOutcome assertions + transport retry tests
- `tests/test_workflows/test_claim_pipeline.py` — policy matrix / identity / precedence / transport
- `.gsd/review_backlog.md` — SR-008 `[x]` + steering (gitignored, not committed)

## Policy matrix (boolean modes)

| Mode | result true | result false | malformed / missing / empty | transport after retries |
|------|-------------|--------------|-----------------------------|-------------------------|
| containment | PASS → APPROVE | ABSTAIN → APPROVE | ERROR → APPROVE (record-only) | ERROR → APPROVE (record-only) |
| contradicts | VIOLATION → DENY | PASS → APPROVE | ERROR → UNCERTAIN | ERROR → UNCERTAIN |
| healthy | VIOLATION → DENY | PASS → APPROVE | ERROR → UNCERTAIN | ERROR → UNCERTAIN |
| not_authentic | VIOLATION → DENY | PASS → APPROVE | ERROR → UNCERTAIN | ERROR → UNCERTAIN |
| incomplete | VIOLATION → DENY | PASS → APPROVE | ERROR → UNCERTAIN | ERROR → UNCERTAIN |

Identity: both names within distance → PASS; beyond → VIOLATION DENY; null/blank → ABSTAIN UNCERTAIN; parse/transport fail → ERROR UNCERTAIN `checker_error:identity`.

## Before / after behaviour

| Case | Before | After |
|------|--------|-------|
| malformed not_authentic / incomplete | DENY (fail-closed True) | UNCERTAIN `checker_error:<mode>` |
| malformed contradicts / healthy | silent PASS / APPROVE | UNCERTAIN `checker_error:<mode>` |
| malformed containment | no effect | ERROR recorded; decision still APPROVE (record-only) |
| identity parse failure | UNCERTAIN `identity_unclear` | UNCERTAIN `checker_error:identity` (`identity_unclear` legacy bool still true) |
| checker transport failure | claim skipped (exception) | retried then ERROR → UNCERTAIN predicted answer |

## Pre-existing test assertion changes (`test_checker.py`)

- All bool / `"match"` / `"mismatch"` / `"unclear"` assertions → `CheckOutcome`
- Containment false → `ABSTAIN` (was False)
- Parse-failure tests (containment empty, not_authentic empty, incomplete missing field) → `ERROR` (intended D-01)
- Added `test_identity_extraction_outcomes_*`, transport retry / recover / identity transport tests

## Gates (baselines vs final)

| Gate | Baseline (planning / Task 1 start) | Final |
|------|--------------------------------------|-------|
| ruff check + format (6 touched .py) | clean | clean |
| mypy (4 src modules) | 0 | 0 |
| mypy (src + 2 test files) | 30 | 30 |
| `uv run pytest -q` | 1 known fail (`test_analysis_coverage_other_label_is_false`) | **339 passed, 3 deselected, 0 failed** — known fail now passes (SR-004 False labels in `config.yaml` landed with Task 2) |
| policy / identity / precedence | n/a | 39 passed |

## Planner discretion (P-01..P-07)

- **P-01:** containment false → ABSTAIN record-only; containment ERROR also record-only (locked D-01; differs from literal plan table “ERROR → UNCERTAIN”)
- **P-02:** `identity_unclear` = ABSTAIN or ERROR; `identity_check` = PASS or not run
- **P-03:** keep `_STATE_BOOLEAN_KEYS`; add `checker_outcomes`; leave `analysis_stats.py` unchanged
- **P-04:** TRANSPORT_ERRORS = ConnectionError, TimeoutError, httpx.TransportError, ollama.ResponseError; no pyproject change
- **P-05:** `TransportRetryConfig(max_retries=2, backoff_seconds=1.0)`; Checker defaults when omitted
- **P-06:** ERROR explanation `checker_error:` + modes in recorded order
- **P-07:** retry helper in `compliance.llm.chat`; CaseClassifier transport still out of scope

## Follow-ups

- CaseClassifier transport errors still skip claims (not SR-008)
- No ollama client request timeout configured
- `httpx` imported directly but only declared transitively via `ollama`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Containment ERROR decision vs plan table**
- **Found during:** Task 1 matrix tests
- **Issue:** Plan table said containment ERROR → UNCERTAIN; locked D-01 / CONTEXT / WIP implementation use record-only
- **Fix:** Matrix expects APPROVE for containment ERROR; `_ERROR_DECISION_MODES` excludes containment
- **Files:** `claim_pipeline.py`, `test_claim_pipeline.py`
- **Commit:** `1bd8d33`

**2. [Rule 3 - Blocking] C901 / mypy on matrix helpers**
- **Found during:** Task 3 verify
- **Issue:** `_policy_matrix_chat_side_effect` exceeded C901; new mypy errors from `list[Exception]` invariance
- **Fix:** Extract `_append_chat_items`; use `Mapping` / `Sequence` types
- **Commit:** `ff6da56`

**3. [documented] Task 2 `config.yaml` also includes SR-004 False abstention labels**
- Preserved concurrent WIP as instructed; committed with `transport_retry` in `fbd1f28`
- Side effect: `test_analysis_coverage_other_label_is_false` now passes (was the known allowed failure)

### Combined RED/GREEN

Task 1 implementation was largely present uncommitted; pipeline matrix tests were written and verified green against that WIP in one pass (no separate RED commit). Tasks 2–3 followed tests + implementation then verify.

## Known Stubs

None.

## Self-Check: PASSED

- `src/compliance/llm/checker.py` — FOUND (`CheckOutcome`)
- `src/compliance/llm/chat.py` — FOUND (`chat_content_with_retry`)
- `src/compliance/config/settings.py` — FOUND (`TransportRetryConfig`)
- Commits `1bd8d33`, `fbd1f28`, `ff6da56` — FOUND
- `.gsd/review_backlog.md` SR-008 `[x]` — FOUND (gitignored)
