---
phase: 260929-n7w-sr-013-extract-policy-engine-from-claimp
plan: 01
subsystem: policy
tags: [policy-extract, langgraph, claim-pipeline, c901, tdd]

requires:
  - phase: SR-004/008/010/011
    provides: stabilized coverage routing, typed checker outcomes, medical rule gating, config validation
provides:
  - compliance/policy package of pure policy functions
  - ClaimArtifactReader filesystem boundary
  - thin ClaimPipeline orchestration under 480 lines
  - tests/test_policy direct unit suite
affects: [future-policy-changes, claim-pipeline-maintenance]

estimate:
  tokens: 150000
  tasks: 3
actuals:
  tokens: 45133
  tasks: 3
  commits: 5
plan_head_before: 1d7b69c04eaafb9e6ea71c9737982f147a79a5b5

tech-stack:
  added: []
  patterns:
    - "policy as pure functions over plain data; orchestration owns I/O"
    - "ordered decision gate table clears C901 by structure"
    - "two-level __all__ surfaces (package vs module)"

key-files:
  created:
    - src/compliance/policy/__init__.py
    - src/compliance/policy/coverage.py
    - src/compliance/policy/state.py
    - src/compliance/policy/rules.py
    - src/compliance/policy/checks.py
    - src/compliance/policy/documents.py
    - src/compliance/policy/decision.py
    - src/compliance/policy/payload.py
    - src/compliance/workflows/claim_artifacts.py
    - src/compliance/claim_dates.py
    - tests/test_policy/test_coverage.py
    - tests/test_policy/test_rules.py
    - tests/test_policy/test_documents.py
    - tests/test_policy/test_checks.py
    - tests/test_policy/test_decision.py
    - tests/test_policy/test_payload.py
    - tests/test_workflows/test_claim_artifacts.py
  modified:
    - src/compliance/workflows/claim_pipeline.py
    - src/compliance/workflows/claim_dates.py
    - README.md
    - LOGIC.md
    - .gsd/review_backlog.md

key-decisions:
  - "D-01: New package compliance/policy/"
  - "D-02: Behaviour-preserving extract only"
  - "D-03: Thin public surface via explicit __all__"
  - "P-04: Preserve asymmetric document_metadata roots"
  - "Moved claim_dates to compliance.claim_dates so policy does not import workflows"

patterns-established:
  - "Policy modules take config/state as explicit args; ClaimPipeline wires them"
  - "ClaimArtifactReader is the sole claim-input filesystem boundary for analysis"

requirements-completed: [SR-013]

coverage:
  - id: D1
    description: "Coverage router extracted as route_coverage pure function"
    requirement: SR-013
    verification:
      - kind: unit
        ref: "tests/test_policy/test_coverage.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "ClaimPipeline is thin LangGraph orchestration under 480 lines"
    requirement: SR-013
    verification:
      - kind: other
        ref: "grep -c '' src/compliance/workflows/claim_pipeline.py → 469"
        status: pass
    human_judgment: false
  - id: D3
    description: "Decision fold is ordered gate table; C901 clear at max-complexity 7"
    requirement: SR-013
    verification:
      - kind: unit
        ref: "tests/test_policy/test_decision.py"
        status: pass
      - kind: other
        ref: "ruff C901 --config max-complexity=7 on policy + claim_pipeline"
        status: pass
    human_judgment: false
  - id: D4
    description: "Full suite behaviour-preserving; artifacts identical for same inputs"
    requirement: SR-013
    verification:
      - kind: integration
        ref: "tests/test_workflows/test_claim_pipeline.py (untouched)"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-09-29
status: complete
---

# Phase 260929-n7w: SR-013 Extract policy engine Summary

**Extracted claim analysis policy into `compliance/policy/` as pure functions; left `ClaimPipeline` as 469-line LangGraph wiring with a filesystem-free policy surface and direct unit tests.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-09-29T15:07:11Z
- **Completed:** 2026-09-29T15:22:00Z
- **Tasks:** 3/3
- **Files modified:** 23 (diff vs plan head)

## Baselines vs final gates

| Gate | Baseline (planning / Task 1 Step 0) | Final |
|------|-------------------------------------|-------|
| `claim_pipeline.py` lines | 1414 | **469** |
| Fast lane pytest | 436 passed, 3 deselected | **486 passed**, 3 deselected |
| Total coverage | 91.52% | **92.06%** |
| ruff check src tests | clean | clean |
| mypy src | 0 errors / 45 files | 0 errors / **55** files |
| mypy `test_claim_pipeline.py` | 11 errors | **11** errors (unchanged) |
| C901 at max-complexity 7 on pipeline | `_decision_from_state` complex 8 | **clean** on pipeline + `compliance/policy/` |
| C901 suppressions in extract | none | none |

## Accomplishments

- New `compliance/policy/` package: coverage, state, rules, checks, documents, decision, payload + thin `__all__`.
- `ClaimArtifactReader` owns all claim-input reads; policy never touches the filesystem.
- Decision fold restructured as an ordered gate table — stricter-than-configured complexity gate is green.
- `tests/test_policy/` proves policy with hand-written arguments (no graph / MagicMock / tmp_path).
- SR-013 closed in `.gsd/review_backlog.md` (gitignored, not staged); all thirteen senior-review tasks complete.

## Task Commits

1. **Task 1 (tracer): coverage router** — `562b805` (feat)
2. **Task 2 Commit A: state / rules / checks** — `92badc7` (refactor)
3. **Task 2 Commit B: documents / decision / payload** — `2108e5d` (refactor)
4. **Task 2 Commit C: ClaimArtifactReader + thin pipeline** — `d675762` (refactor)
5. **Task 3: unit tests + docs** — `7450f4d` (test)

## Extraction map (as implemented)

| Source in claim_pipeline | Destination | Notes |
|---|---|---|
| CoverageBranch, RoutedCoverage, route helpers | `policy/coverage.py` | as planned |
| ClaimAnalysisState | `policy/state.py` | as planned (P-02) |
| GatedCheck, CheckerRuleSet, rule matrix | `policy/rules.py` | as planned |
| CheckerRunResult, run_checks, legacy booleans | `policy/checks.py` | as planned |
| document acceptability helpers | `policy/documents.py` | as planned |
| decision fold + HITL | `policy/decision.py` | ordered gate table (P-08) |
| analysis_result_payload | `policy/payload.py` | as planned |
| artifact reads | `workflows/claim_artifacts.py` | as planned |
| graph / batch / publish | stayed in `claim_pipeline.py` | as planned |
| `_predicted_answer_path` | deleted | unused (P-09) |
| `workflows/claim_dates.py` body | `compliance/claim_dates.py` | **deviation** — see below; shim left at old path |

## Decisions (D-01..D-03, P-01..P-10)

- **D-01 / D-02 / D-03:** Honored — new package, behaviour-preserving, thin `__all__`.
- **P-01..P-03, P-05..P-10:** Implemented as planned.
- **P-04:** Asymmetric metadata roots preserved: OCR failure from `preprocessed_root / claim_id`, run id from claim input root; comment at persist records the discrepancy.

## Behaviour preservation (D-02)

- `tests/test_workflows/test_claim_pipeline.py` was **never modified** across all five SR-013 commits.
- Full fast lane green at every Task 2 commit and at plan end; key sets, decision strings, `checker_rule_set` / `checker_skipped`, and boolean presence/absence unchanged by construction (move + identical gate order/explanations).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] claim_dates import vs policy↔workflows ban**
- **Found during:** Task 2 Commit C verify (`! rg compliance.workflows src/compliance/policy`)
- **Issue:** `run_checks` must call date gates that lived under `compliance.workflows.claim_dates`, but policy must not import `compliance.workflows`.
- **Fix:** Moved the module body to `compliance/claim_dates.py`; left a thin re-export shim at `compliance.workflows.claim_dates` so untouched tests keep resolving. Policy imports `compliance.claim_dates`.
- **Files modified:** `src/compliance/claim_dates.py`, `src/compliance/workflows/claim_dates.py`, `src/compliance/policy/checks.py`
- **Commit:** `d675762`

**2. [Rule 1 - Bug] Accidental deletion of `_COVERAGE_BRANCH_NEXT_NODE` during Commit A**
- **Found during:** Task 2 Commit A (107 test failures / NameError)
- **Issue:** Script that removed gated-check / CheckerRunResult also deleted the next-node map and decision constants still needed until later commits.
- **Fix:** Restored `_COVERAGE_BRANCH_NEXT_NODE` and decision/payload constants for Commit A; later commits moved the constants properly.
- **Commit:** fixed before `92badc7`

## TDD Gate Compliance

- Task 1: RED evidence recorded (`.planning/tdd/260929-n7w-task1-red-evidence.json`, verdict `RED_EVIDENCE_OK`); GREEN implemented in the same plan-specified feat commit (plan requested a single feat commit, not a separate test commit).
- Task 3: Direct unit tests authored against real signatures after Task 2 (plan `tdd="true"` with post-extract proofs).

## Follow-ups

- Reconcile the two `document_metadata.json` roots (P-04) on a dedicated behaviour-changing task.
- Remaining stricter-complexity offenders outside this plan: `claim_dates._unique_calendar_dates`, `checker._names_within_edit_distance`, `claim_batch._predicted_answer_from_bundle`, `document._maybe_retry_ocr`.
- Graph-level tests in `test_claim_pipeline.py` could gradually re-express as policy unit tests (out of scope).
- Batch-loop locking item still open from SR-007 notes (if any residual).

## Self-Check: PASSED

- `src/compliance/policy/*.py` present with planned entry points
- `src/compliance/workflows/claim_artifacts.py` present
- Commits `562b805`, `92badc7`, `2108e5d`, `d675762`, `7450f4d` on main
- `claim_pipeline.py` line count 469 < 480
- Backlog `### [x] SR-013` present; not staged
