# Quick Task 260929-lni: SR-006 Ground-truth-first evaluation - Context

**Gathered:** 2026-09-29
**Status:** Ready for planning

<domain>
## Task Boundary

Ground-truth-first evaluation + aligned metrics: discover denominator from ground-truth `data_dir`; report scored / invalid / missing counts. Keep raw-prediction metrics separate from acceptable-alternative policy metrics. Claims with GT and no results folder appear in evaluation. Accuracy, F1, and matrix share a documented population (or explicitly separated named metrics).

</domain>

<decisions>
## Implementation Decisions

### Missing prediction
- Missing prediction (GT present) counts as **incorrect** for accuracy; also report `coverage_rate`

### Acceptable-decision remapping
- Keep as a **second named metric** (raw vs policy/acceptable)

### Claude's Discretion
- Exact metric field names and EvaluationResult shape
- Whether analysis_stats discovery stays results_dir-based (likely yes — different population)
- Interaction with SR-005 mixed-generation refusal (already in evaluator)
- How invalid GT / unreadable files are counted

</decisions>

<specifics>
## Specific Ideas

Canonical: `.gsd/steering-decisions-2026-09-29.md` (SR-006).

</specifics>

<canonical_refs>
## Canonical References

- `.gsd/review_backlog.md` (SR-006)
- `.gsd/steering-decisions-2026-09-29.md`
- `src/evaluation/evaluator.py`
- `src/evaluation/__main__.py`
- Recent SR-005 evaluator changes (mixed-generation)

</canonical_refs>
