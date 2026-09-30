# Phase 9 Discussion Log

**Date:** 2026-09-30
**Origin:** Chat review of `Checker` — user found it "terrible": too many constructor parameters, not compositional, config not reused.

| Area | Options presented | Selected |
| ---- | ----------------- | -------- |
| Package placement | `llm/checks/` package · turn `policy/checks.py` into a package · top-level `compliance/checks/` | `llm/checks/` package |
| `CheckOutcome` / `CheckerMode` home | move + update imports, delete `llm/checker.py` · move + keep shim · leave in place | move + update imports, no shim |
| Suite lifetime | once in `ClaimPipeline.__init__` · per `run_checks` call | once in `ClaimPipeline.__init__` |
| Date gates | extract `_date_gates()` helper · `Gate` protocol with gate classes · untouched | `Gate` protocol with gate classes |
| Tests | split per check + suite test · adapt in place | split per check + suite test |

Notes:
- The user explicitly rejected only shortening `Checker.__init__` by passing `CheckingConfig`; the class must be decomposed.
- Behavior-preserving: order, message payloads, and polarity locked (CONTEXT D-06..D-08).

Deferred ideas: none.
