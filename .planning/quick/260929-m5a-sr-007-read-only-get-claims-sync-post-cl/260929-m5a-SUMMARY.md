---
phase: 260929-m5a-sr-007-read-only-get-claims-sync-post-cl
plan: 01
subsystem: api
tags: [fastapi, flock, idempotency, read-only, claim-analysis]

requires:
  - phase: 260929-l16 (SR-005)
    provides: publish_claim_generation, generation_mismatch, run_manifest contract
provides:
  - "Read-only GET /claims/{claim_id} with no pipeline dependencies"
  - "Sync POST /claims/{claim_id}/analysis under per-claim non-blocking flock"
  - "ClaimListItem.errors with SR-005 reason codes on stable 200 list"
  - "CLI --claim-id shares analyze_claim_exclusively lock"
affects: [SR-009, SR-013]

actuals:
  tokens: 14959
  tasks: 3
  commits: 7

plan_head_before: 87e66604372b3631889a0522d1a3c2df6567aa27

tech-stack:
  added: []
  patterns:
    - "fcntl.flock LOCK_EX|LOCK_NB on results_dir/.locks/{claim_id}.lock, never unlinked"
    - "analyze_claim_exclusively wraps process_then_analyze under the lock"
    - "ArtifactRead reader enforces generation_mismatch before json.loads"

key-files:
  created:
    - tests/test_api/test_claims_analysis.py
  modified:
    - src/compliance/workflows/artifact_publication.py
    - src/compliance/workflows/orchestration.py
    - src/compliance/workflows/__init__.py
    - src/api/routes_claims.py
    - src/api/schemas.py
    - src/main.py
    - tests/test_api/test_claims_get.py
    - tests/test_api/test_claims_list.py
    - tests/test_api/test_claims_e2e.py
    - tests/test_workflows/test_orchestration.py
    - tests/test_workflows/test_pipeline.py
    - README.md

key-decisions:
  - "D-01 sync POST /claims/{id}/analysis (not async job)"
  - "D-02 idempotency key = claim_id only"
  - "D-03 breaking GET-mutates is acceptable"
  - "P-01 non-blocking flock; refuse 409 rather than wait-then-duplicate"
  - "P-02 lock files never unlinked; live under results_dir/.locks/"
  - "P-03 lock at API POST + CLI --claim-id only (batch loop deferred)"
  - "P-04 repeat POST after completion re-runs analysis"
  - "P-05 POST returns 200 ClaimDecision (not 201 Location)"
  - "P-06 list reports corrupt items via errors, never skip or 500"
  - "P-07 reuse SR-005 reason codes verbatim"
  - "P-08 GET takes no lock; validates generation instead"

patterns-established:
  - "Filesystem lock primitive beside publication; policy seam in orchestration"
  - "One ArtifactRead path for decision GET, analysis POST response, and list"

requirements-completed: [SR-007]

coverage:
  - id: D1
    description: "GET /claims/{id} is read-only — unchanged tree, zero chat calls, no pipeline Depends"
    requirement: SR-007
    verification:
      - kind: unit
        ref: "tests/test_api/test_claims_get.py::test_get_claim_reads_published_generation_unchanged"
        status: pass
    human_judgment: false
  - id: D2
    description: "POST /claims/{id}/analysis returns ClaimDecision; 404 claim_not_found; 409 when lock held"
    requirement: SR-007
    verification:
      - kind: unit
        ref: "tests/test_api/test_claims_analysis.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "Two concurrent POSTs → one 200 + one 409, one LLM pass, consistent generation"
    requirement: SR-007
    verification:
      - kind: unit
        ref: "tests/test_api/test_claims_analysis.py::test_concurrent_post_analysis_one_success_one_conflict"
        status: pass
    human_judgment: false
  - id: D4
    description: "GET /claims stays 200 with per-item errors for invalid_json and run_id_mismatch"
    requirement: SR-007
    verification:
      - kind: unit
        ref: "tests/test_api/test_claims_list.py"
        status: pass
    human_judgment: false
  - id: D5
    description: "CLI --claim-id exits 1 when per-claim lock held"
    requirement: SR-007
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_pipeline.py::test_cli_claim_id_exits_1_when_lock_held"
        status: pass
    human_judgment: false

duration: 11min
completed: 2026-09-29
status: complete
---

# Phase 260929-m5a Plan 01: SR-007 Read-only GET + locked analysis POST Summary

**GET /claims/{id} is a pure published-generation read; analysis moved to sync POST under a non-blocking per-claim flock so concurrent requests collapse to one OCR/LLM pass and one consistent publication.**

## Performance

- **Duration:** 11min
- **Started:** 2026-09-29T14:10:03Z
- **Completed:** 2026-09-29T14:20:46Z
- **Tasks:** 3/3
- **Files modified:** 13 tracked (+ gitignored backlog)

## Gates (baseline → final)

| Gate | Baseline (Task 1 start) | Final |
|------|-------------------------|-------|
| `pytest -q --cov` (fast lane) | 401 passed, 3 deselected, **91.30%** | 414 passed, 3 deselected, **91.34%** |
| `ruff check --no-fix src tests` | clean | clean |
| `ruff format --check` (scoped) | 2 files would reformat | clean on touched paths |
| `mypy src` | 0 errors | 0 errors |
| `mypy tests/test_api` | 8 errors (conftest noise) | 8 errors (same baseline) |

## Endpoint contract (as implemented)

**`GET /claims/{claim_id}`** — read only (`results_dir`); no pipeline Depends.

| Situation | Status | Detail |
|-----------|--------|--------|
| unsafe id | 422 | existing path-safety prose |
| no analysis artifact | 404 | `analysis_not_found` |
| unparseable / non-object | 409 | `invalid_json` |
| disagrees with manifest | 409 | `run_id_missing` / `run_id_mismatch` / `artifact_missing` |
| valid generation | 200 | `ClaimDecision` |

**`POST /claims/{claim_id}/analysis`** — only mutating claim verb; lock across preprocess+analyse.

| Situation | Status | Detail |
|-----------|--------|--------|
| unsafe id | 422 | existing path-safety prose |
| no raw folder | 404 | `claim_not_found` |
| lock held | 409 | `analysis_in_progress` |
| completes | 200 | `ClaimDecision` |
| pipeline raises | 500 | log-and-reraise |

**`GET /claims`** — always 200; unreadable artifact → null + `errors[{filename}] = {reason}`; clean items have `errors: null`.

**Lock:** `results_root/.locks/{claim_id}.lock`, exclusive non-blocking, opened fresh per acquisition, never unlinked.

## Behaviour-change register (intended)

- `GET /claims/{id}` no longer triggers analysis; 404 means no published analysis (raw-folder 404 moved to POST).
- Clients that relied on GET to produce a decision must `POST .../analysis` first (D-03).
- `GET /claims` gains `errors` and no longer 500s on corrupt JSON.
- CLI `--claim-id` exits 1 when another analysis holds the lock.

## Accomplishments

- Structural read-only GET: pipeline Depends removed so OCR/LLM are unreachable from the handler
- Sync analysis POST with claim_id-only concurrent idempotency via non-blocking flock
- List reports unreadable artifacts per item; CLI single-claim shares the lock
- README + gitignored backlog close SR-007 with D-01..D-03 and P-01..P-08

## Task Commits

1. **Task 1 (tracer):** `ef3f055` — feat(SR-007): serve claim decisions read-only and analyse under a per-claim lock
2. **Task 2:** `4d733f1` — feat(SR-007): report unreadable artifacts on the claim list and lock the CLI single-claim run
3. **Rule 1 fix (Task 3 gate):** `753fe73` — fix(SR-007): keep tests/test_api mypy at the 8-error baseline
4. **Task 3:** `ec03fa8` — feat(SR-007): document the read-only decision GET and the locked analysis POST

**Plan metadata:** `63c263d`, `0428029` (docs: complete plan + activity refresh)

## Files Created/Modified

- `src/compliance/workflows/artifact_publication.py` — `ClaimAnalysisBusyError`, `claim_analysis_lock`
- `src/compliance/workflows/orchestration.py` — `analyze_claim_exclusively`
- `src/api/routes_claims.py` — read-only GET, POST analysis, `ArtifactRead`, list errors
- `src/api/schemas.py` — `ClaimListItem.errors`; ClaimDecision docstring
- `src/main.py` — CLI exclusive single-claim path
- `tests/test_api/test_claims_*.py` / orchestration / pipeline — coverage for read-only, POST, contention, concurrency, list errors, CLI
- `README.md` — four-endpoint table + lock/idempotency docs
- `.gsd/review_backlog.md` — SR-007 `[x]` (gitignored, never staged)

## Decisions Made

Honored D-01..D-03 and P-01..P-08 from CONTEXT / steering / plan (see frontmatter key-decisions).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Read-only test asserted `.locks` absent after POST**
- **Found during:** Task 1
- **Issue:** Plan test text said neither `.locks` nor `.staging` exists after POST+GET, but P-02 never unlinks lock files, so POST leaves `.locks/`.
- **Fix:** Assert snapshot unchanged + no `.staging`; `.locks` may exist from POST.
- **Files modified:** `tests/test_api/test_claims_get.py`
- **Commit:** `ef3f055`

**2. [Rule 1 - Bug] Unsafe-id POST used `quote('..')` which does not escape dots**
- **Found during:** Task 1
- **Issue:** `urllib.parse.quote` never escapes `.`, so `/claims/../analysis` normalized to `/analysis` → 404.
- **Fix:** Use percent-encoded `%2E%2E` like the GET test.
- **Files modified:** `tests/test_api/test_claims_analysis.py`
- **Commit:** `ef3f055`

**3. [Rule 1 - Bug] Concurrent test assumed all 9 chat side_effects are consumed**
- **Found during:** Task 2
- **Issue:** Cancellation path skips some checkers; one analysis used 5 of 9 responses.
- **Fix:** Assert `0 < call_count <= expected_calls` and `< 2×` (one pass, not two).
- **Files modified:** `tests/test_api/test_claims_analysis.py`
- **Commit:** `4d733f1`

**4. [Rule 1 - Bug] Concurrency helper return type worsened mypy baseline**
- **Found during:** Task 3 gates
- **Issue:** Annotating `Response` clashed with httpx/httpx2 stubs (9 errors vs 8 baseline).
- **Fix:** Return `Any` from the threaded POST helper.
- **Files modified:** `tests/test_api/test_claims_analysis.py`
- **Commit:** `753fe73`

## Follow-ups (out of scope)

- ClaimPipeline batch loop and preprocessing-only batch do not take the lock (P-03) — needs wait-vs-skip policy.
- SR-009 owns upload size / path / symlink hardening — not touched.
- SR-013 owns policy-engine extract — not touched.

## Known Stubs

None.

## Threat Flags

None beyond the plan's mitigated register (T-SR007-01..08); T-SR007-09 remains transferred to SR-009.

## Self-Check: PASSED

- `src/compliance/workflows/artifact_publication.py` — FOUND (`claim_analysis_lock`, `ClaimAnalysisBusyError`, `LOCK_NB`)
- `src/compliance/workflows/orchestration.py` — FOUND (`analyze_claim_exclusively`)
- `src/api/routes_claims.py` — FOUND (`claims/{claim_id}/analysis`, `analysis_in_progress`, `ArtifactRead`)
- `src/api/schemas.py` — FOUND (`errors`, `invalid_json`)
- `src/main.py` — FOUND (`analyze_claim_exclusively`, `ClaimAnalysisBusyError`)
- `README.md` — FOUND (`claims/{claim_id}/analysis`, `analysis_in_progress`, `run_manifest`)
- `.gsd/review_backlog.md` — FOUND (`### [x] SR-007`, steered done row); never staged
- Commits `ef3f055`, `4d733f1`, `753fe73`, `ec03fa8`, `63c263d` — FOUND
