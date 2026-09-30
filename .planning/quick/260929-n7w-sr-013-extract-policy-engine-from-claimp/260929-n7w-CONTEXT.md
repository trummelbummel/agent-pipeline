# Quick Task 260929-n7w: SR-013 Extract policy engine - Context

**Gathered:** 2026-09-29
**Status:** Ready for planning

<domain>
## Task Boundary

Extract coverage router, document policy, checker runner, decision policy, and artifact repository from ClaimPipeline into `compliance/policy/`. Leave ClaimPipeline as thin LangGraph orchestration. Behavior-preserving extract after SR-008/010/011. Unit tests target extracted modules without MagicMock graph sequences where possible. C901 cleared by structure, not `# noqa`. Thin public API: ClaimPipeline + thin helpers; rest private.

</domain>

<decisions>
## Implementation Decisions

### Module layout
- New package `compliance/policy/`

### Timing
- Behavior-preserving extract now (SR-008/010/011 already done); do not combine with new policy changes

### Public API
- Public surface = `ClaimPipeline` + thin helpers; policy internals private (underscore modules or explicit `__all__`)

### Claude's Discretion
- Exact module split (suggested: coverage_router, document_policy, checker_rules / checker_runner, decision_policy, maybe reuse existing artifact_publication as repository)
- Whether CheckerRuleSet / RoutedCoverage move with the extract
- How many commits (prefer incremental move-then-wire over big-bang)
- Keep existing tests green; add focused unit tests on extracted modules where cheap

</decisions>

<specifics>
## Specific Ideas

claim_pipeline.py is ~1414 lines. Natural seams already exist: RoutedCoverage, CheckerRuleSet, _checker_outcomes, _decision_from_state, artifact_publication.py (SR-005). Prefer move + re-export / thin wrappers over rewriting policy.

Canonical: `.gsd/steering-decisions-2026-09-29.md` (SR-013).

</specifics>

<canonical_refs>
## Canonical References

- `.gsd/review_backlog.md` (SR-013)
- `.gsd/steering-decisions-2026-09-29.md`
- `src/compliance/workflows/claim_pipeline.py`
- `src/compliance/workflows/artifact_publication.py`
- SR-008/010/011 SUMMARYs for stabilized policy contracts

</canonical_refs>
