# Quick Task 260929-hxe: SR-008 Typed LLM/checker outcome policy matrix - Context

**Gathered:** 2026-09-29
**Status:** Ready for execution (plan already exists; Task 1 largely in working tree)

<domain>
## Task Boundary

Finish SR-008 per existing PLAN.md: typed CheckOutcome policy matrix, transport retry, pipeline wiring, tests, backlog close.

</domain>

<decisions>
## Implementation Decisions

### Outcome enum and ERROR promotion
- PASS | VIOLATION | ABSTAIN | ERROR
- ERROR → UNCERTAIN + HITL; containment ERROR remains record-only (planner P-01)
- VIOLATION beats ERROR in decision fold

### Identity mismatch
- VIOLATION only when both names extracted and edit distance exceeded
- null/blank → ABSTAIN; parse/schema fail → ERROR

### Transport errors
- Retry with checking.transport_retry then ERROR (claim still gets UNCERTAIN predicted answer)
- Non-transport exceptions still propagate

### Resume note
- Task 1 code appears largely present uncommitted in checker.py / claim_pipeline.py / tests
- Complete Tasks 2–3 (transport retry + wire + close); verify Task 1 gates before committing

</decisions>

<specifics>
## Specific Ideas

Canonical decisions also in `.gsd/steering-decisions-2026-09-29.md`. Follow existing `260929-hxe-PLAN.md` must_haves and task actions exactly.

</specifics>

<canonical_refs>
## Canonical References

- `.gsd/review_backlog.md` (SR-008)
- `.planning/quick/260929-hxe-sr-008-typed-checker-outcome-policy-matr/260929-hxe-PLAN.md`

</canonical_refs>
