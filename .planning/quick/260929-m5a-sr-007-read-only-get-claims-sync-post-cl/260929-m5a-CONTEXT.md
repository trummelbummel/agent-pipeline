# Quick Task 260929-m5a: SR-007 Read-only GET + analysis POST - Context

**Gathered:** 2026-09-29
**Status:** Ready for planning

<domain>
## Task Boundary

Make `GET /claims/{id}` read-only. Add sync `POST /claims/{id}/analysis` with per-claim locking / idempotency (`claim_id` only). Stable error semantics for corrupt JSON on list. GET never writes artifacts or invokes OCR/LLM. Concurrent analysis for one claim cannot interleave writes. Breaking change for existing GET-mutates clients is acceptable.

</domain>

<decisions>
## Implementation Decisions

### Analysis trigger
- Sync `POST /claims/{id}/analysis` (not async job)

### Idempotency
- Key = `claim_id` only

### Breaking GET
- Acceptable — GET becomes read-only immediately

### Claude's Discretion
- Lock mechanism (threading.Lock map, file lock under claim results, etc.) — prefer something that works with SR-005 atomic publish
- Response shapes for GET (existing analysis) vs 404 when no analysis yet
- Corrupt list-item JSON → skip with log vs 422 vs partial response with error field
- Whether POST returns same ClaimDecision schema as old GET

</decisions>

<specifics>
## Specific Ideas

Canonical: `.gsd/steering-decisions-2026-09-29.md` (SR-007). Coordinate with SR-005 publication; do not expand into SR-009 upload limits.

</specifics>

<canonical_refs>
## Canonical References

- `.gsd/review_backlog.md` (SR-007)
- `.gsd/steering-decisions-2026-09-29.md`
- `src/api/routes_claims.py`
- `src/compliance/workflows/orchestration.py`
- SR-005 artifact publication module

</canonical_refs>
