# Quick Task 260929-mqy: SR-009 Harden upload/path/symlink - Context

**Gathered:** 2026-09-29
**Status:** Ready for planning

<domain>
## Task Boundary

Stream uploads with hard byte limits. Validate configured artifact names as basenames; resolve containment before R/W. Reject symlinked claim roots. Oversized upload rejected; path traversal via config/symlink cannot escape data roots. Tests cover traversal, symlink, and size limit cases. Same containment on CLI batch discovery.

</domain>

<decisions>
## Implementation Decisions

### Size limits
- 25 MB per file, 50 MB total request

### Symlinks
- Hard-reject symlinked claim roots (not resolve-and-contain)

### CLI
- Same containment applies to CLI batch discovery

### Claude's Discretion
- Where limits live in config.yaml (api.upload or preprocessing)
- Streaming vs chunked read with running total
- How to detect claim-root symlink (Path.is_symlink on the claim dir itself and/or any parent under data_dir)
- Basename enforcement for config artifact filenames at load vs use site

</decisions>

<specifics>
## Specific Ideas

Canonical: `.gsd/steering-decisions-2026-09-29.md` (SR-009).

</specifics>

<canonical_refs>
## Canonical References

- `.gsd/review_backlog.md` (SR-009)
- `.gsd/steering-decisions-2026-09-29.md`
- `src/api/routes_claims.py` upload path
- `src/compliance/preprocessing/claim_batch.py`
- SR-007 read paths / SR-005 containment patterns

</canonical_refs>
