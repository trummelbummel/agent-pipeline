# Quick Task 260929-k1p: SR-011 Strong config policy validation - Context

**Gathered:** 2026-09-29
**Status:** Ready for planning

<domain>
## Task Boundary

Strong config policy validation: named coverage keys (not positional meaning); unique labels; range constraints; forbid unknown fields. Validate every required-document / taxonomy cross-reference at load time. Invalid cross-refs and duplicate labels fail at startup with clear errors. Reordering label lists cannot silently change routing when keys are used.

</domain>

<decisions>
## Implementation Decisions

### Schema migration
- Breaking named coverage keys now — no dual-read positional→named migration
- Explicit mapping e.g. coverage label `"1"` → branch `cancellation` (not zip of positive_labels order to hard-coded branch tuple)

### Unknown fields
- Fail hard on unknown keys (`extra="forbid"` or equivalent at AppConfig / nested models)

### Claude's Discretion
- Exact YAML shape for named branches (e.g. `analysis.coverage.branches: {"1": cancellation, ...}` vs per-label objects)
- Which nested models get `extra="forbid"` (prefer AppConfig tree-wide consistency)
- How uniqueness / range constraints are expressed (Pydantic validators)
- Migration of `config.yaml` and all tests/fixtures that construct AppConfig
- Keep classification.labels vs analysis.coverage.labels alignment rules explicit at load time

</decisions>

<specifics>
## Specific Ideas

Done when: invalid cross-refs and duplicate labels fail at startup with clear errors; reordering lists cannot silently change routing when keys are used.

Canonical steering also in `.gsd/steering-decisions-2026-09-29.md` (SR-011).

</specifics>

<canonical_refs>
## Canonical References

- `.gsd/review_backlog.md` (SR-011)
- `.gsd/steering-decisions-2026-09-29.md`
- `src/compliance/config/settings.py`
- `src/compliance/workflows/claim_pipeline.py` (`_coverage_branch` positional zip — must become key lookup)
- `config.yaml`

</canonical_refs>
