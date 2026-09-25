---
phase: 04-claim-analysis-pipeline
plan: 03
subsystem: workflows
tags: [langgraph, ClaimPipeline, CaseClassifier, Personal Effects, Missed Departure, other_label, pytest]

requires:
  - phase: 04-claim-analysis-pipeline
    provides: ClaimPipeline cancellation tracer (04-02)
  - phase: 02-case-classifier-models
    provides: CaseClassifier + Checker injectable chat_fn
provides:
  - Full coverage routing (cancellation / PE / missed / other_label)
  - classify_pe_document + classify_missed_document nodes
  - other_label persist-only path (skip reason/doc/checker)
affects: [04-04 batch/CLI]

actuals:
  tokens: 4319
  tasks: 2
  commits: 4
plan_head_before: 29f4d3ad13df49eab3425de68f24cf0d375c5c45

tech-stack:
  added: []
  patterns:
    - "Coverage router compares config.analysis.coverage.labels[i] + other_label exact strings"
    - "PE/missed document nodes → run_checker → persist; reason only on cancellation"
    - "other_label → persist with checker keys omitted from analysis_result.json"

key-files:
  created:
    - .planning/tdd/260925-04-03-task1-red-evidence.json
    - .planning/tdd/260925-04-03-task2-red-evidence.json
  modified:
    - src/compliance/workflows/claim_pipeline.py
    - tests/test_workflows/test_claim_pipeline.py

key-decisions:
  - "PE/missed document classifiers use supporting_document_text + stage configs"
  - "other_label routes to persist (not END); checker keys omitted when Checker skipped"
  - "Unknown coverage after allow-list treated as other_label → persist (T-04-03)"

patterns-established:
  - "Non-cancellation coverage never enters classify_reason (R012)"
  - "Document stage CaseClassifier from analysis.personal_effects_document / missed_departure_document"

requirements-completed: [R012, R013]

coverage:
  - id: D1
    description: "Personal Effects coverage → PE document classifier → Checker → persist; reason skipped"
    requirement: R013
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_claim_pipeline.py::test_routes_personal_effects"
        status: pass
    human_judgment: false
  - id: D2
    description: "Missed Departure/Connection coverage → missed document classifier → Checker → persist; reason skipped"
    requirement: R013
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_claim_pipeline.py::test_routes_missed_departure"
        status: pass
    human_judgment: false
  - id: D3
    description: "Coverage other_label (None) skips reason/doc/checker and still writes analysis_result"
    requirement: R012
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_claim_pipeline.py::test_routes_coverage_other_skips_reason_and_docs"
        status: pass
    human_judgment: false
  - id: D4
    description: "Cancellation path still green after PE/missed/other expansion"
    requirement: R012
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_claim_pipeline.py::test_analyze_claim_cancellation_path_writes_analysis_result"
        status: pass
    human_judgment: false

duration: 3min
completed: 2026-09-25
status: complete
---

# Phase 04 Plan 03: PE / Missed / other_label Routing Summary

**ClaimPipeline now routes all five coverage outcomes: cancellation (reason+cancel-doc), Personal Effects, Missed Departure/Connection, and other_label (persist-only).**

## Performance

- **Duration:** 3 min
- **Started:** 2026-09-25T15:29:17Z
- **Completed:** 2026-09-25T15:31:54Z
- **Tasks:** 2
- **Files modified:** 5 (plan commits)

## Accomplishments

- Wired `classify_pe_document` and `classify_missed_document` with stage CaseClassifiers
- Router uses exact `config.analysis.coverage.labels` / `other_label` strings only
- other_label path persists coverage-only `analysis_result.json` without Checker keys
- Full `test_claim_pipeline.py` suite green (9 passed); mypy clean on workflows

## Task Commits

1. **Task 1 RED:** `814243d` — `test(04-03): add failing PE and missed document routing tests`
2. **Task 1 GREEN:** `e96ec88` — `feat(04-03): wire Personal Effects and Missed Departure document branches`
3. **Task 2 RED:** `40ca126` — `test(04-03): add failing other_label terminal path test`
4. **Task 2 GREEN:** `1760335` — `feat(04-03): route coverage other_label directly to persist`

**Plan metadata:** docs commit after SUMMARY/state updates

## Files Created/Modified

- `src/compliance/workflows/claim_pipeline.py` — PE/missed nodes + complete `route_after_coverage`
- `tests/test_workflows/test_claim_pipeline.py` — PE, missed, other_label routing tests (xfail stubs removed)
- `.planning/tdd/260925-04-03-task1-red-evidence.json` / `task2-red-evidence.json` — TDD RED gates

## Decisions Made

- PE/missed document classifiers read `supporting_document_text` from their analysis stage configs
- When Checker is skipped (other_label), omit `checker_containment` / `checker_contradicts` from JSON rather than writing false defaults
- Unknown coverage labels after CaseClassifier allow-list route like other_label → persist (T-04-03)

## Deviations from Plan

None - plan executed exactly as written.

### Auth Gates

None.

## TDD Gate Compliance

- Task 1 `tdd="true"`: RED evidence `.planning/tdd/260925-04-03-task1-red-evidence.json` → `RED_EVIDENCE_OK` (`target_test_failed` for `test_routes_personal_effects`)
- Task 2 `tdd="true"`: RED evidence `.planning/tdd/260925-04-03-task2-red-evidence.json` → `RED_EVIDENCE_OK` (`target_test_failed` for `test_routes_coverage_other_skips_reason_and_docs`)

## Known Stubs

None — PE/missed END stubs and Wave-0 xfail tests removed.

## Threat Flags

None beyond plan register (T-04-01 path validation retained; T-04-02 branch_log claim_id/node only; T-04-03 unknown→other persist).

## Next

Plan 04-04 — batch analysis over preprocessed claims + CLI entrypoint.

## Self-Check: PASSED

- `claim_pipeline.py` has classify_pe_document / classify_missed_document / complete route_after_coverage
- Commits `814243d`, `e96ec88`, `40ca126`, `1760335` on branch
- Suite: 9 passed; mypy clean
