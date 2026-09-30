# Quick Task 260929-kia: SR-010 Per-coverage medical rule gating - Context

**Gathered:** 2026-09-29
**Status:** Ready for planning

<domain>
## Task Boundary

Build explicit per-coverage rule sets. Run suspicious-dating / healthy-document / medical identity only on applicable taxonomy. Police/loss/booking evidence cannot be denied solely for medical semantics. Decision traces show which rule set ran. Inapplicable checks recorded as `skipped`.

</domain>

<decisions>
## Implementation Decisions

### Rule matrix
- Medical-only: healthy + suspicious dating + identity/signature apply only on cancellation medical taxonomy / applicable medical docs (identity_required / signature_required codes, medical reason path as already configured)
- Personal effects, missed departure, and police/jury/non-medical cancellation docs skip medical semantics (must not DENY solely for healthy/dating/identity/signature medical rules)

### Artifact recording
- Inapplicable checks recorded as `skipped` in artifacts (not omitted)

### Claude's Discretion
- Exact structure for per-coverage rule sets (config vs code constants vs derived from required_documents)
- Whether "skipped" lives in `checker_outcomes` as a new outcome value, a parallel `checker_skipped` map, or both
- Prefer minimal change that reuses SR-008 CheckOutcome fold; do not reinvent decision fold
- SR-011 named branches are available — gate on routed_coverage branch + document codes

</decisions>

<specifics>
## Specific Ideas

Done when: Police/loss/booking evidence cannot be denied solely for medical semantics; decision traces show which rule set ran.

Canonical: `.gsd/steering-decisions-2026-09-29.md` (SR-010).

</specifics>

<canonical_refs>
## Canonical References

- `.gsd/review_backlog.md` (SR-010)
- `.gsd/steering-decisions-2026-09-29.md`
- `src/compliance/workflows/claim_pipeline.py` (healthy always-on today; `_identity_required_applies`, `_medical_document_check_applies`, suspicious_dating)
- `src/compliance/llm/checker.py` (CheckOutcome — SR-008)
- `config.yaml` (identity_required_codes, signature_required_codes)

</canonical_refs>
