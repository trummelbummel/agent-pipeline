# Phase 9: Compositional checker refactor - Context

**Gathered:** 2026-09-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the monolithic `compliance.llm.checker.Checker` with small composable checks and gates, built once from `CheckingConfig`. This is a **behavior-preserving refactor**: claim decisions, `CheckOutcome` polarity, legacy booleans, `analysis_result.json` keys, check execution order, and LLM message contents must not change.

In scope:
- Split `Checker` into per-check classes behind one `Check` protocol.
- One shared `LlmCheckClient` owns model name, transport retry, chat seam, and JSON parsing.
- `CheckSuite.from_config(CheckingConfig, chat_fn)` built once per `ClaimPipeline`.
- Departure / suspicious-dating become `Gate` implementations composed before the suite.
- Move `CheckOutcome` / `CheckerMode` and update all imports; delete `llm/checker.py`.
- Split `tests/test_llm/test_checker.py` into per-check tests plus a suite test.

Out of scope:
- New checks, new config keys, prompt changes, or changed decision precedence.
- Changes to `decision_from_state`, `rule_set_for_claim`, or the LangGraph topology.
- Refactoring `CaseClassifier` / classifier stages.

</domain>

<decisions>
## Implementation Decisions

### Package layout
- **D-01:** New package `src/compliance/llm/checks/` replaces `src/compliance/llm/checker.py`:
  - `base.py` — `CheckOutcome`, `CheckerMode`, `CheckContext` (description, document, booking texts), `Check` protocol (`name`, `run(context) -> CheckOutcome`).
  - `client.py` — `LlmCheckClient` (model, `TransportRetryConfig`, `ChatFn`) with a boolean-result call and a name-extraction call; owns `BooleanCheckResult` / `ExtractedNameResult` parsing.
  - `boolean.py` — LLM boolean checks (contradicts, healthy, incomplete) driven by a polarity value, not per-mode if/elif.
  - `containment.py` — deterministic normalized-substring hit, then LLM fallback.
  - `identity.py` — booking-name parsing, role-note skip, containment, name extraction, Levenshtein matching.
  - `suite.py` — `CheckSuite` with `from_config` and ordered execution of selected modes.
  `src/compliance/policy/checks.py` stays the runner (`run_checks`, `checker_state_updates`, `legacy_booleans_from_outcomes`). — **Reversibility:** costly — every import of the checker module moves.

### CheckOutcome / CheckerMode home
- **D-02:** `CheckOutcome` and `CheckerMode` move to `compliance.llm.checks.base`. Update every importer (`policy/decision.py`, `policy/state.py`, `policy/checks.py`, `policy/payload.py` if applicable, `llm/__init__.py`, tests). Delete `llm/checker.py` outright — **no re-export shim**. `llm/__init__.py` stops exporting `Checker`.

### Suite lifetime and config reuse
- **D-03:** `ClaimPipeline.__init__` builds the suite once: `CheckSuite.from_config(config.checking, chat_fn or ollama.chat)`. `run_checks` receives the suite (and gates) instead of `CheckingConfig` + `chat_fn`. No per-claim construction; no unpacking of `CheckingConfig` into many constructor parameters. Each check receives only the shared client plus its own prompt / threshold.

### Date gates
- **D-04:** Introduce a `Gate` protocol for deterministic early-UNCERTAIN gates, with `DepartureGate` and `SuspiciousDatingGate` composed before the check suite. Gates live in `src/compliance/policy/gates.py` (deterministic policy, not LLM). A gate returns whether it fires; gates run only when their name is in `rule_set.applicable` (departure additionally requires `departure_uncertain_enabled`). Gates are built once from `CheckingConfig` alongside the suite. When any gate fires, LLM checks are skipped exactly as today. `CheckerRunResult` keeps its fields (`departure_within_days`, `suspicious_dating`, `outcomes`, `legacy_booleans`).

### Tests
- **D-05:** Split `tests/test_llm/test_checker.py` into per-check test modules under `tests/test_llm/test_checks/` (containment, boolean checks, identity, client transport/parsing) plus one suite test covering mode selection and fixed order. Preserve the existing behaviors under test; no speculative new coverage. Pipeline-level tests (`tests/test_workflows/test_claim_pipeline.py`) must pass unchanged in behavior — only construction/import adjustments are allowed.

### Invariants (must hold after the refactor)
- **D-06:** Execution order stays containment → contradicts → identity → healthy → incomplete (pipeline tests rely on `MagicMock` `side_effect` ordering). Identity keeps booking-extraction-before-document-extraction order.
- **D-07:** LLM message payloads (system prompt, user content strings, `format="json"`, `model`) and retry `context` labels stay byte-identical.
- **D-08:** Polarity table and containment's record-only ERROR semantics are unchanged; the module-docstring policy matrix moves with the code.

### Claude's Discretion
- Exact class names beyond `Check`, `CheckContext`, `LlmCheckClient`, `CheckSuite`, `Gate`, `DepartureGate`, `SuspiciousDatingGate`.
- Whether Levenshtein / name normalization helpers are module-level functions in `identity.py`.
- How `run_checks` composes gates (list vs named fields), provided `CheckerRunResult` is unchanged.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Code being refactored
- `src/compliance/llm/checker.py` — current `Checker`, policy matrix docstring, polarity table, identity algorithm.
- `src/compliance/policy/checks.py` — `run_checks`, `_build_checker`, `_checker_outcomes`, legacy boolean mapping.
- `src/compliance/workflows/claim_pipeline.py` — `ClaimPipeline.__init__` and `_run_checker_node` (only `run_checks` caller).
- `src/compliance/claim_dates.py` — `_reference_today`, `_departure_beyond_days`, `_suspicious_dating` used by gates.
- `src/compliance/llm/chat.py` — `chat_content_with_retry`, `parse_llm_json_object`, `ChatFn`.
- `src/compliance/config/settings.py` — `CheckingConfig`, `TransportRetryConfig`.

### Project rules
- `CLAUDE.md` — code style (small functions, structured returns, docstrings with `:param:`, delete unused code, no mocking internals).
- `README.md` §Algorithm design choices / §Identity checker — documented checker behavior that must not change.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `chat_content_with_retry` / `parse_llm_json_object` — the client wraps these; no new transport logic.
- `_MODE_POLARITY` table — becomes per-check polarity configuration.

### Established Patterns
- Chat seam: `ChatFn` injected via `ClaimPipeline(config, chat_fn=...)`; tests pass `MagicMock` chat functions.
- Pydantic strict models for LLM JSON contracts (`BooleanCheckResult`, `ExtractedNameResult`).
- `NamedTuple` structured returns (`CheckerRunResult`, `_NameExtraction`).

### Integration Points
- `ClaimPipeline.__init__` (build suite + gates), `_run_checker_node` (call `run_checks` with suite/gates).
- Importers of `CheckOutcome` / `CheckerMode`: `policy/decision.py`, `policy/state.py`, `policy/checks.py`, tests in `tests/test_policy/`.

</code_context>

<specifics>
## Specific Ideas

From the design discussion:

```python
class HealthyCheck:
    name = "healthy"

    def __init__(self, client: LlmCheckClient, prompt: str) -> None: ...
    def run(self, context: CheckContext) -> CheckOutcome: ...


suite = CheckSuite.from_config(config.checking, chat_fn)
outcomes = suite.run(modes, context)
```

The user explicitly rejected merely shortening `Checker.__init__` by passing `CheckingConfig` — the god class must be decomposed.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 09-compositional-checker-refactor*
*Context gathered: 2026-09-30*
