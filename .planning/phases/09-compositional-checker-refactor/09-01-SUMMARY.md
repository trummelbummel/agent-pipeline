---
phase: 09-compositional-checker-refactor
plan: 01
status: complete
completed: 2026-09-30
---

# Plan 09-01 Summary: Compositional checks, gates, and suite

## Outcome
`compliance.llm.checker.Checker` is gone. Checks are composable objects behind a `Check` protocol, sharing one `LlmCheckClient`; date gates are `Gate` objects. Both are built once in `ClaimPipeline.__init__` from `CheckingConfig`.

## What changed
- **New** `src/compliance/llm/checks/`: `base.py` (`CheckOutcome`, `CheckerMode`, `CheckContext`, `Check`, `normalized_text`, policy matrix docstring), `client.py` (`LlmCheckClient`, JSON contracts, `NameExtraction`), `boolean.py` (`BooleanLlmCheck`, `Polarity`, message builders), `containment.py` (`ContainmentCheck` wrapping an LLM fallback), `identity.py` (`IdentityCheck` + name helpers), `suite.py` (`CheckSuite.from_config`, ordered `run`).
- **New** `src/compliance/policy/gates.py`: `Gate` protocol, `DepartureGate`, `SuspiciousDatingGate`, `gates_from_config`.
- `policy/checks.py`: `run_checks(context, rule_set, gates, suite)`; removed `_build_checker` / `_checker_outcomes`. `CheckerRunResult` unchanged.
- `workflows/claim_pipeline.py`: builds suite + gates once; `_run_checker_node` passes a `CheckContext`.
- Imports moved to `compliance.llm.checks` in `policy/decision.py`, `policy/state.py`, `llm/__init__.py` (no longer exports `Checker` / `BooleanCheckResult`), and policy tests.
- **Deleted** `src/compliance/llm/checker.py`, `tests/test_llm/test_checker.py`.
- **Tests** `tests/test_llm/test_checks/`: containment, boolean (contradicts/healthy/incomplete + transport retry), identity, suite order/config wiring.
- `LOGIC.md` analyze step references `CheckSuite` / gates instead of `Checker`.

## Deviations
- Dropped the "unsupported mode raises" test: string-mode dispatch no longer exists, so the error type was removed rather than kept defensively.
- Gate `fires` is evaluated only for applicable gates (same as before); `today` is resolved once per claim in the runner.

## Verification
- `make test`: 499 passed, coverage 91.91% (floor 90%); new modules 91–100%.
- `uv run mypy`: clean. `ruff check src tests`: clean.
- `tests/test_workflows/test_claim_pipeline.py` passed with no expectation changes (fixed call order and message payloads preserved).

## Follow-ups
- `gates_from_config` with `departure_uncertain_enabled: false` has no direct test (the branch existed before as an inline `and`).
- `src/compliance/policy/decision.py` has a pre-existing `ruff format` diff from uncommitted work outside this phase.
