---
phase: 260929-hxe-sr-008-typed-checker-outcome-policy-matr
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/compliance/llm/checker.py
  - src/compliance/llm/chat.py
  - src/compliance/config/settings.py
  - config.yaml
  - src/compliance/workflows/claim_pipeline.py
  - tests/test_llm/test_checker.py
  - tests/test_workflows/test_claim_pipeline.py
  - .gsd/review_backlog.md
autonomous: true
requirements: [SR-008]

estimate:
  tokens: 120000
  raw_tokens: 120000
  tasks: 3
  confidence: low

must_haves:
  truths:
    - "Checker.check and Checker.check_identity return a typed CheckOutcome (PASS | VIOLATION | ABSTAIN | ERROR). One per-mode polarity table inside Checker resolves True/False, so ClaimPipeline never branches on True vs False per mode (D-01)"
    - "For every boolean mode (containment, contradicts, healthy, not_authentic, incomplete), malformed JSON, a missing or non-bool result field, or an empty response produces ERROR. Malformed not_authentic/incomplete output no longer DENYs. Malformed contradicts/healthy/containment output no longer passes silently. All of these produce UNCERTAIN with human_in_the_loop true (D-01)"
    - "Decision precedence, first match wins: OCR failure, coverage abstention, departure_within_days, checker_suspicious_dating (all UNCERTAIN, unchanged). Then any VIOLATION (checker outcome, or deterministic missing-documentation / signature rule) gives DENY, even when another checker returned ERROR. Then any ERROR gives UNCERTAIN with explanation checker_error:<modes> and human_in_the_loop true. Then identity ABSTAIN gives UNCERTAIN identity_unclear. Otherwise APPROVE checker_consistent (D-01)"
    - "Identity is a VIOLATION (DENY identity_check) only when both the booking and patient names were extracted and they exceed identity_max_edit_distance. A null or blank extraction is ABSTAIN (UNCERTAIN identity_unclear). An unparseable or schema-invalid extraction, or a transport failure during extraction, is ERROR (UNCERTAIN checker_error:identity) (D-02)"
    - "A checker chat call that raises a transport error (ConnectionError, TimeoutError, httpx.TransportError, ollama.ResponseError) is retried checking.transport_retry.max_retries times, with exponential backoff from checking.transport_retry.backoff_seconds, and then recorded as ERROR. The claim still gets analysis_result.json and an UNCERTAIN predicted_answer.json instead of being skipped. Any other exception still propagates (D-03)"
    - "analysis_result.json keeps every existing boolean key, now derived from the outcomes (identity_unclear is true on identity ABSTAIN or ERROR), and adds checker_outcomes {mode: outcome string} for every mode that ran. src/evaluation/analysis_stats.py is unchanged (P-02, P-03)"
    - "The policy matrix (mode x {valid true, valid false, malformed JSON, missing field, empty response, transport error after retries}) is documented as a table in the checker module docstring. One parametrized pipeline test covers it and asserts the per-mode outcome, the decision, the explanation and the chat call count"
    - "Gates: ruff check --no-fix and ruff format --check are clean on every touched .py file. uv run pytest -q shows only the known test_analysis_coverage_other_label_is_false failure. mypy reports 0 errors on the touched src modules, and the touched test files have no more errors than the baseline recaptured before editing (30 at planning time)"
  artifacts:
    - path: src/compliance/llm/checker.py
      provides: "CheckOutcome enum, per-mode boolean polarity table, structured name extraction, identity outcome fold, policy-matrix module docstring"
      contains: "class CheckOutcome"
    - path: src/compliance/llm/chat.py
      provides: "TRANSPORT_ERRORS tuple and chat_content_with_retry (bounded retry + exponential backoff, None after exhaustion)"
      contains: "def chat_content_with_retry"
    - path: src/compliance/config/settings.py
      provides: "TransportRetryConfig nested under CheckingConfig.transport_retry"
      contains: "class TransportRetryConfig"
    - path: config.yaml
      provides: "checking.transport_retry.max_retries / backoff_seconds"
      contains: "transport_retry:"
    - path: src/compliance/workflows/claim_pipeline.py
      provides: "checker_outcomes state + persistence, outcome-based decision fold, legacy boolean derivation, transport_retry wiring"
      contains: "checker_outcomes"
    - path: tests/test_workflows/test_claim_pipeline.py
      provides: "test_checker_policy_matrix, test_identity_outcome_policy, test_checker_outcome_precedence"
      contains: "def test_checker_policy_matrix"
    - path: tests/test_llm/test_checker.py
      provides: "CheckOutcome assertions, identity extraction outcomes, transport retry count tests"
      contains: "def test_checker_transport_retry_count_honoured"
    - path: .gsd/review_backlog.md
      provides: "SR-008 checked off with recorded steering decisions (gitignored, not committed)"
      contains: "### [x] SR-008"
  key_links:
    - from: "Checker boolean-mode helper and person-name extraction"
      to: "compliance.llm.chat.chat_content_with_retry"
      via: "every Checker chat call goes through the retry helper; None return maps to CheckOutcome.ERROR"
      pattern: "chat_content_with_retry\\("
    - from: "ClaimPipeline._run_checker_node"
      to: "ClaimAnalysisState.checker_outcomes"
      via: "structured checker run result; legacy booleans derived from outcomes in one table-driven helper"
      pattern: "\"checker_outcomes\""
    - from: "ClaimPipeline._decision_from_state / _violated_checkers"
      to: "state checker_outcomes"
      via: "VIOLATION -> DENY, ERROR -> UNCERTAIN checker_error, identity ABSTAIN -> UNCERTAIN identity_unclear"
      pattern: "checker_error:"
    - from: "ClaimPipeline Checker construction"
      to: "config.checking.transport_retry"
      via: "Checker(..., transport_retry=checking.transport_retry)"
      pattern: "transport_retry=checking.transport_retry"
    - from: "ClaimPipeline._analysis_result_payload"
      to: "analysis_result.json"
      via: "checker_outcomes {mode: outcome.value} beside the unchanged _STATE_BOOLEAN_KEYS booleans"
      pattern: "checker_outcomes"
---

<objective>
SR-008 replaces the mode-dependent bool defaults in `Checker` with one typed outcome model, `CheckOutcome` = PASS | VIOLATION | ABSTAIN | ERROR. `ClaimPipeline` folds that model into the claim decision through an explicit, documented and tested policy. Checker chat transport failures are retried and then recorded as ERROR, so the claim gets an UNCERTAIN predicted answer instead of being skipped.

Locked decisions (steering answers; there is no CONTEXT.md for this quick task):
- D-01: The outcome enum is PASS | VIOLATION | ABSTAIN | ERROR. ERROR covers malformed or unparseable LLM output, and a transport failure after retries. ERROR leads to UNCERTAIN plus human-in-the-loop, but a genuine VIOLATION from any checker still wins and gives DENY. Precedence: the existing UNCERTAIN gates (OCR failure, coverage abstention, departure_within_days, suspicious_dating), then DENY on any VIOLATION, then UNCERTAIN on any ERROR, then UNCERTAIN on identity ABSTAIN (today's identity_unclear), then APPROVE. Consequences: malformed not_authentic/incomplete output no longer DENYs (it was fail-closed before), and malformed contradicts/healthy output no longer passes silently.
- D-02: Identity mismatch is a VIOLATION (DENY) only when BOTH the booking and patient names were extracted and they exceed the edit distance. A failed or empty extraction is ABSTAIN (UNCERTAIN). An LLM parse failure during extraction is ERROR.
- D-03: Transport errors (the chat call raising, e.g. connection or timeout) are retried with backoff. The retry count and backoff live in config.yaml under `checking`. After the retries, ERROR is recorded, so the claim still gets an UNCERTAIN predicted answer instead of being skipped.

Planner discretion (flagged; report in SUMMARY):
- P-01: containment result false maps to ABSTAIN. It is recorded only and never drives the decision. Only identity ABSTAIN drives UNCERTAIN, through an explicit policy set in the pipeline. Under the literal reading of D-01 ("any ERROR"), a containment ERROR gives UNCERTAIN. That is a behaviour change: malformed containment had no effect before.
- P-02: Legacy `identity_unclear` = identity ABSTAIN or ERROR, so legacy readers never infer a DENY the decision did not make. `identity_check` = identity PASS, or identity not run (non-medical path, unchanged).
- P-03: Least-disruptive persistence. `_STATE_BOOLEAN_KEYS` and every existing boolean key in analysis_result.json stay, now derived from outcomes. Add a new `checker_outcomes` mapping of mode to outcome string ("PASS" etc.). `src/evaluation/analysis_stats.py` needs no change.
- P-04: The transport error set is ConnectionError, TimeoutError, httpx.TransportError and ollama.ResponseError. ollama raises the builtin ConnectionError on connect failure, lets httpx timeouts and read errors through, and raises ResponseError on server HTTP errors. Anything else propagates, so bugs and test-seam exhaustion are never converted into UNCERTAIN. httpx is imported directly as a hard dependency of ollama. pyproject.toml / uv.lock stay untouched because another session is active.
- P-05: `TransportRetryConfig(max_retries=2, backoff_seconds=1.0)`, both validated `ge=0` at config load. The sleep between attempts is `backoff_seconds * 2**attempt`, with no sleep after the last attempt. `Checker` defaults to `TransportRetryConfig()` when not passed, mirroring its existing `identity_max_edit_distance` default. The model is not re-exported from `compliance.config`, because src modules import config models from `compliance.config.settings` directly (e.g. document.py OcrRetryConfig).
- P-06: The ERROR explanation is `checker_error:` plus the errored modes, comma-joined in check order (e.g. `checker_error:contradicts,healthy`). The DENY explanation keeps the legacy keys in their existing order. Identity ABSTAIN keeps `identity_unclear`.
- P-07: The retry helper lives in `compliance/llm/chat.py`, the existing LLM transport/parse boundary module. CaseClassifier transport errors are out of scope (they still skip the claim), and no ollama client timeout is added. Both go in the SUMMARY as follow-ups.

Purpose: stop malformed LLM output and transient transport failures from silently producing a wrong DENY or APPROVE (backlog risk "Malformed output -> wrong DENY/PASS").
Output: typed outcome model and policy matrix, outcome-based decision fold, configurable transport retry, tests covering the matrix, and SR-008 checked off in the backlog.
</objective>

<execution_context>
@~/.claude/gsd-core/workflows/execute-plan.md
@~/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/STATE.md
@.gsd/review_backlog.md (section "SR-008" and the "## Steering status" table; SR-004 section shows the resolved-steering format)
@src/compliance/llm/checker.py
@src/compliance/llm/chat.py
@src/compliance/config/settings.py (CheckingConfig, OcrRetryConfig for nested-config style)
@src/compliance/workflows/claim_pipeline.py (ClaimAnalysisState, _STATE_BOOLEAN_KEYS, _run_checker_node, _checker_results, _state_boolean_flags, _analysis_result_payload, _violated_checkers, _decision_from_state, _written_analysis_outputs)
@tests/test_llm/test_checker.py
@tests/test_workflows/test_claim_pipeline.py (_config, _chat_response, _seed_preprocessed_claim, _with_departure_uncertain_enabled, test_deny_when_healthy_check_true, test_deny_when_identity_check_false)
@tests/conftest.py (chat_returning_factory, build_minimal_app_config)

Facts verified at planning time (re-read files fresh; another session is committing other SR-* items):
- Only claim_pipeline.py and tests/test_llm/test_checker.py consume Checker. src/api passes analysis_result as dict[str, Any], so a new key is safe.
- The seeded claim embeds the description in supporting_document.md (containment is a deterministic PASS, with no LLM call) and has booking name "Ada Lovelace" with "Patient: Ada Lovelace" in the OCR (identity is a deterministic PASS, with no LLM call). The medical checker chat order is: containment (LLM only when not contained), contradicts, identity (LLM only when the booking name is not contained), healthy, not_authentic, incomplete. This order must not change, because every MagicMock side_effect sequence depends on it.
- A MagicMock side_effect list raises any exception instance it contains, which is the existing fake-chat seam for transport tests. An exhausted side_effect raises StopIteration, which must keep propagating.
- ruff targets py310 (use `class CheckOutcome(str, Enum)`, not StrEnum). TRY rules are enabled (TRY300: put the success return in the try `else` branch). C901 max-complexity is 10.
- `.gsd/` is gitignored, so the backlog edit is never staged.
- Baselines at planning time: ruff + format clean on all touched .py files. mypy on the 4 touched src modules has 0 errors; mypy on src touched + the 2 touched test files has 30 errors (all in the test files). Full `uv run pytest -q`: 1 failed (tests/test_config/test_settings.py::test_analysis_coverage_other_label_is_false, pre-existing) and 250 passed, taking about 5.5 min because of Docling integration tests.
</context>

<policy_matrix>
Copy this into the checker module docstring (ASCII only). Task 1 writes it without the transport column. Task 2 adds the transport column.

Boolean LLM modes. "result" is the validated `{"result": bool}` field. The decision assumes every other checker is benign.

| Mode          | result true           | result false         | malformed JSON / missing or non-bool result / empty | transport error after retries |
|---------------|-----------------------|----------------------|------------------------------------------------------|-------------------------------|
| containment   | PASS -> APPROVE       | ABSTAIN -> APPROVE   | ERROR -> UNCERTAIN                                   | ERROR -> UNCERTAIN            |
| contradicts   | VIOLATION -> DENY     | PASS -> APPROVE      | ERROR -> UNCERTAIN                                   | ERROR -> UNCERTAIN            |
| healthy       | VIOLATION -> DENY     | PASS -> APPROVE      | ERROR -> UNCERTAIN                                   | ERROR -> UNCERTAIN            |
| not_authentic | VIOLATION -> DENY     | PASS -> APPROVE      | ERROR -> UNCERTAIN                                   | ERROR -> UNCERTAIN            |
| incomplete    | VIOLATION -> DENY     | PASS -> APPROVE      | ERROR -> UNCERTAIN                                   | ERROR -> UNCERTAIN            |

A deterministic containment hit (normalized claim substring of the text) is PASS with no LLM call.

Identity:

| Situation                                                                 | Outcome   | Decision (others benign)            |
|---------------------------------------------------------------------------|-----------|-------------------------------------|
| booking name field contained in OCR (no role note), no LLM call           | PASS      | APPROVE                             |
| both names extracted, within identity_max_edit_distance                   | PASS      | APPROVE                             |
| both names extracted, beyond identity_max_edit_distance                   | VIOLATION | DENY identity_check                 |
| an extraction returned {"name": null} or a blank name, none errored       | ABSTAIN   | UNCERTAIN identity_unclear          |
| an extraction was unparseable / schema-invalid / transport error          | ERROR     | UNCERTAIN checker_error:identity    |

Decision fold (ClaimPipeline._decision_from_state; the first match wins):
1. preprocess OCR failure -> UNCERTAIN
2. routed coverage abstention -> UNCERTAIN coverage_false_label
3. departure_within_days -> UNCERTAIN
4. checker_suspicious_dating -> UNCERTAIN
5. any VIOLATION (checker outcome, or deterministic missing documentation / signature) -> DENY, explanation = legacy keys comma-joined
6. any ERROR -> UNCERTAIN checker_error:<modes>, human_in_the_loop
7. identity ABSTAIN -> UNCERTAIN identity_unclear, human_in_the_loop
8. APPROVE checker_consistent

Legacy analysis_result.json booleans (derived from outcomes, kept for evaluation compatibility):
checker_containment = containment PASS. checker_contradicts = contradicts VIOLATION. identity_check = identity PASS or identity not run. identity_unclear = identity ABSTAIN or ERROR. healthy_check = healthy VIOLATION. checker_document_not_authentic = not_authentic VIOLATION (key present only when the mode ran). checker_incomplete_document = incomplete VIOLATION (key present only when the mode ran). The new checker_outcomes key maps mode to outcome string for every mode that ran.
</policy_matrix>

<tasks>

<task type="tracer" tdd="true">
  <name>Task 1 (tracer): typed CheckOutcome from Checker through the ClaimPipeline decision into analysis_result.json</name>
  <files>src/compliance/llm/checker.py, src/compliance/workflows/claim_pipeline.py, tests/test_llm/test_checker.py, tests/test_workflows/test_claim_pipeline.py</files>
  <read_first>src/compliance/llm/checker.py, src/compliance/workflows/claim_pipeline.py (lines ~1-140 state/keys, ~393-440 checker node, ~762-915 checker results/persistence, ~995-1090 fold), tests/test_llm/test_checker.py, tests/test_workflows/test_claim_pipeline.py (helpers ~140-230, identity/healthy deny tests ~480-760)</read_first>
  <behavior>
    - The policy matrix (5 boolean modes x {valid true, valid false, malformed JSON, missing field, empty response}): the pipeline writes checker_outcomes[mode] and decision / decision_explanation exactly as the policy_matrix table says. UNCERTAIN rows have human_in_the_loop true in predicted_answer.json. Every row consumes exactly the chat responses it was given.
    - Identity (pipeline): a close extracted name gives PASS/APPROVE; a far extracted name gives VIOLATION/DENY with identity_check in the explanation; {"name": null} gives ABSTAIN/UNCERTAIN identity_unclear; unparseable content gives ERROR/UNCERTAIN checker_error:identity.
    - Precedence (pipeline): healthy VIOLATION + contradicts ERROR gives DENY healthy_check. contradicts ERROR + healthy ERROR gives UNCERTAIN checker_error:contradicts,healthy. contradicts ERROR + identity ABSTAIN gives UNCERTAIN checker_error:contradicts. identity VIOLATION + incomplete ERROR gives DENY identity_check.
    - Checker unit tests: the existing tests assert CheckOutcome values instead of bool / "match" strings. The three old parse-failure tests (containment empty response, not_authentic empty response, incomplete missing field) now assert ERROR. Identity extraction: `{"name": 7}` gives ERROR, `{"name": "   "}` gives ABSTAIN, and an unparseable booking-name extraction (booking text with no markdown name field) gives ERROR.
  </behavior>
  <action>
Step 0, before editing anything: re-read the four files fresh. Recapture the baselines and record them for the SUMMARY: `uv run mypy` on the 4 touched src modules plus the 2 touched test files (error count), and `uv run ruff check --no-fix` / `uv run ruff format --check` on the touched .py files. Planning-time values are in the context block. Write the new tests first (RED), then implement.

Checker (src/compliance/llm/checker.py), implementing D-01 and D-02:
- Add a module docstring as the first statement, before `from __future__ import annotations`. It holds the policy_matrix tables from this plan WITHOUT the transport column (Task 2 adds it), in ASCII only.
- Add `CheckOutcome(str, Enum)` with members PASS, VIOLATION, ABSTAIN, ERROR whose values equal their names. The docstring states each member's meaning, and that polarity is already resolved per mode.
- Delete the deny-on-true mode frozenset and the fail-closed parse default. Replace them with one per-mode polarity table: a private NamedTuple with fields when_true / when_false, keyed by the five boolean modes, with values exactly as the policy_matrix rows. No per-mode if/elif polarity anywhere.
- `check()` returns CheckOutcome. Mode identity delegates to `check_identity`. Containment keeps its deterministic substring hit, which returns PASS with no chat call. The other boolean modes go through one helper that looks up the mode's prompt, calls chat exactly as today (same messages via `_check_messages`, `format="json"`), and returns the outcome. An unsupported mode still raises UnsupportedCheckerModeError before any chat call.
- Parse the boolean result into a CheckOutcome through a helper named after what it produces (e.g. `_boolean_outcome(content, mode)`). An empty or unparseable object from `parse_llm_json_object` gives ERROR. A BooleanCheckResult validation error gives ERROR, logged at WARNING with no response content. Otherwise use the polarity lookup.
- Name extraction returns structured data. Add a private NamedTuple (e.g. `_NameExtraction`) with `name: str | None` and `failed: bool`. The extraction helper returns failed=True when the content is unparseable or fails ExtractedNameResult validation, and name=None with failed=False for a null or blank name. The chat call and the user_content framing are unchanged.
- `check_identity()` returns CheckOutcome. A deterministic booking-name containment (no role note) is PASS with no chat call. Otherwise the booking side is the markdown name as a successful extraction, or else the LLM extraction. The document side is the LLM extraction. Keep today's call order: the booking LLM call (only when the markdown field is absent), then the document LLM call, both always made. Fold with a helper (e.g. `_identity_outcome(booking, document)`): any failed gives ERROR; else any missing name gives ABSTAIN; else PASS within identity_max_edit_distance, VIOLATION beyond it.
- Delete the now-unused three-way identity status Literal alias. Update the `check` / `check_identity` / `__init__` docstrings (`:return:` describes CheckOutcome). Leave `_levenshtein`, `_names_within_edit_distance`, `_identity_name_contained`, `_booking_name` and `_check_messages` untouched. Transport exceptions still propagate in this task (Task 2 handles them).

Pipeline (src/compliance/workflows/claim_pipeline.py), implementing D-01 and P-01..P-03, P-06:
- Import `CheckOutcome` and `CheckerMode` from compliance.llm.checker. Add `checker_outcomes: dict[CheckerMode, CheckOutcome]` to ClaimAnalysisState, with a docstring `:param:`. Note in the legacy key params that they are derived from checker_outcomes.
- Replace the `dict[str, bool]` return of `_checker_results` with a structured NamedTuple (e.g. `CheckerRunResult` with departure_within_days, suspicious_dating, and outcomes, which is empty when a date gate short-circuits the LLM checkers). Extract a helper that produces the outcomes dict, running the modes in the unchanged order and recording only the modes that ran (identity only when run_identity; not_authentic / incomplete only when run_medical_document_checks). Extract a helper that builds the Checker from config (Task 3 adds transport_retry there).
- Add one table-driven helper that produces the legacy booleans from the outcomes, per the policy_matrix legacy section. Identity absent gives identity_check True and identity_unclear False. The not_authentic / incomplete keys are present only when those modes ran. Use no per-mode if/elif chains.
- `_run_checker_node`: keep the early-exit payload shape exactly (departure_within_days, signature_check, and checker_suspicious_dating only when True). When the LLM checkers ran, the payload also carries checker_suspicious_dating, `checker_outcomes` and the derived legacy booleans. Log outcome values only (enum values, never OCR, names or LLM content).
- `_analysis_result_payload`: after `_state_boolean_flags`, add `checker_outcomes` as {mode: outcome.value} when present in state. `_STATE_BOOLEAN_KEYS` stays unchanged.
- Fold: `_violated_checkers` keeps the deterministic missing-documentation and signature rules. It reads checker VIOLATIONs from state checker_outcomes through a mode-to-legacy-key table (identity -> identity_check, healthy -> healthy_check, not_authentic -> checker_document_not_authentic, incomplete -> checker_incomplete_document, contradicts -> checker_contradicts). It preserves today's key order: checker_missing_documentation, identity_check, signature_check, healthy_check, checker_document_not_authentic, checker_incomplete_document, checker_contradicts.
- `_decision_from_state`: after the DENY step, any ERROR outcome gives UNCERTAIN with explanation `checker_error:` plus the errored modes comma-joined in recorded order (P-06). Then identity ABSTAIN gives UNCERTAIN `identity_unclear`, selected through an explicit module-level policy set of checkers whose ABSTAIN means UNCERTAIN (containing only identity, per P-01). Then APPROVE. Update the precedence docstring to the 8-step list. Keep every method at or below C901 10 by extracting small helpers named after what they produce (e.g. `_errored_checkers(state)`). `_resolved_human_in_the_loop` needs no change, because UNCERTAIN already implies HITL.

Tests:
- test_checker.py: convert every existing assertion to CheckOutcome per the policy_matrix polarity (e.g. containment False gives ABSTAIN, contradicts True gives VIOLATION, identity "mismatch" gives VIOLATION, "unclear" gives ABSTAIN). Rename and flip the three old parse-failure tests to assert ERROR, since that behaviour change is intended by D-01. Add a parametrized `test_identity_extraction_outcomes` covering the three extraction cases in the behavior block. Use the existing `chat_returning_factory` / MagicMock chat seam only.
- test_claim_pipeline.py: add one DRY helper that seeds a medical-certificate cancellation claim whose supporting_document does NOT contain the description (containment goes to the LLM) but does contain "Patient: Ada Lovelace" (identity stays deterministic), and one helper that builds the chat side_effect as the 3 classifier responses followed by per-mode checker responses from a dict of per-mode overrides over benign defaults (containment `{"result": true}`, the others `{"result": false}`). Override items are raw content strings (add a raw-content twin of `_chat_response`). For the identity rows, the claim seed uses booking name "Roy Hoffman" with OCR "Patient: Roy Hofman" so identity reaches the LLM; the helper inserts the identity response between contradicts and healthy.
- Add a module-level `_POLICY_MATRIX` list of rows (mode, case, expected outcome, decision, explanation) that mirrors the policy_matrix table for the 5 non-transport cases (valid_true `{"result": true}`, valid_false `{"result": false}`, malformed_json `{"result": tru`, missing_field `{"verdict": true}`, empty ``). Add `test_checker_policy_matrix` parametrized over it (ids like `contradicts-malformed_json`). It asserts analysis_result checker_outcomes[mode], decision, decision_explanation, predicted_answer.json decision and human_in_the_loop (true iff UNCERTAIN), and chat_fn.call_count == number of responses supplied.
- Add `test_identity_outcome_policy` (4 rows per the behavior block, also asserting legacy identity_check / identity_unclear per P-02) and `test_checker_outcome_precedence` (the 4 precedence rows).
- Leave every other existing pipeline test unchanged. They must still pass as-is.

Commit (stage only these 4 paths explicitly; never `git add -A` or `git add .`; do not bypass hooks). First run `git status --short` and `git diff --stat -- <the 4 paths>`. If a path shows hunks this task did not write (concurrent session), stop and report instead of committing. Message: `feat(SR-008): typed checker outcome model folded into pipeline decision`, ending with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && uv run pytest -q tests/test_llm/test_checker.py tests/test_workflows/test_claim_pipeline.py tests/test_evaluation && uv run pytest -q tests/test_workflows/test_claim_pipeline.py -k "policy_matrix or identity_outcome_policy or checker_outcome_precedence" && uv run ruff check --no-fix src/compliance/llm/checker.py src/compliance/workflows/claim_pipeline.py tests/test_llm/test_checker.py tests/test_workflows/test_claim_pipeline.py && uv run ruff format --check src/compliance/llm/checker.py src/compliance/workflows/claim_pipeline.py tests/test_llm/test_checker.py tests/test_workflows/test_claim_pipeline.py && uv run mypy src/compliance/llm/checker.py src/compliance/workflows/claim_pipeline.py && test "$(grep -vE '^\s*#' src/compliance/llm/checker.py | grep -cE '_DENY_ON_TRUE_MODES|fail_closed|IdentityStatus')" = 0</automated>
  </verify>
  <done>Checker returns CheckOutcome for every mode. The pipeline persists checker_outcomes and folds them per D-01/D-02. The 25 non-transport matrix rows, 4 identity rows and 4 precedence rows pass. All pre-existing checker, pipeline and evaluation tests pass (with only the intended CheckOutcome/ERROR assertion updates in test_checker.py). ruff, format and mypy (src) are clean. The Task 1 commit contains exactly the 4 files.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: configurable transport retry with backoff in Checker; exhaustion records ERROR</name>
  <files>src/compliance/config/settings.py, config.yaml, src/compliance/llm/chat.py, src/compliance/llm/checker.py, tests/test_llm/test_checker.py</files>
  <read_first>src/compliance/llm/chat.py, src/compliance/config/settings.py (CheckingConfig ~L103-146, OcrRetryConfig for nested style), config.yaml (checking section), src/compliance/llm/checker.py (as left by Task 1)</read_first>
  <behavior>
    - With transport_retry max_retries=2 and backoff_seconds=0.0, a contradicts check whose chat always raises ConnectionError, httpx.ConnectTimeout or ollama.ResponseError(status 503) returns ERROR after exactly 3 chat calls. With max_retries=0 it returns ERROR after exactly 1 call.
    - A single ConnectionError followed by `{"result": true}` returns VIOLATION for contradicts after exactly 2 chat calls (transient failure recovered).
    - check_identity with a booking markdown name that is not contained in the OCR, and a document extraction chat that always raises ConnectionError, returns ERROR after max_retries + 1 calls.
    - load_config("config.yaml").checking.transport_retry has max_retries=2 and backoff_seconds=1.0.
  </behavior>
  <action>
Implements D-03 with P-04, P-05, P-07. Re-read the files fresh (another session may have changed settings.py or config.yaml).

- settings.py: add `TransportRetryConfig(BaseModel)` with `max_retries: int = Field(default=2, ge=0)` and `backoff_seconds: float = Field(default=1.0, ge=0.0)`. The docstring gives `:param:` purpose for each field (retry count after the first attempt; base delay of the exponential backoff between attempts). Add `transport_retry: TransportRetryConfig = Field(default_factory=TransportRetryConfig)` to CheckingConfig and document it in the CheckingConfig docstring. Do not edit compliance/config/__init__.py (P-05).
- config.yaml: under `checking`, add a `transport_retry` block with `max_retries: 2` and `backoff_seconds: 1.0`. Precede it with a short comment: checker chat transport failures (connection / timeout / server error) are retried with delay backoff_seconds * 2**attempt, and after exhaustion the check is recorded as ERROR, giving UNCERTAIN + human_in_the_loop (SR-008). Touch nothing else in the file.
- chat.py: add a module-level `TRANSPORT_ERRORS: tuple[type[Exception], ...]` = ConnectionError, TimeoutError, httpx.TransportError, ollama.ResponseError. Add a one-line WHY comment: ollama maps connect failures to the builtin ConnectionError and lets httpx timeouts and read errors through. Add `chat_content_with_retry(chat_fn: ChatFn, retry: TransportRetryConfig, *, context: str, **chat_kwargs: Any) -> str | None` with a full docstring. It makes up to max_retries + 1 attempts. On success it returns `response_content(...)` (from the try `else` branch, for TRY300). It catches only the TRANSPORT_ERRORS tuple; no catch-all handler. Each failure is logged at WARNING with context, attempt number / total and the exception type name only (never messages, kwargs or content). It sleeps `retry.backoff_seconds * 2**attempt` via `time.sleep` only between attempts, and returns None after the final failure. Imports: time, httpx, ollama, and TransportRetryConfig from compliance.config.settings. Do not edit pyproject.toml (P-04).
- checker.py: add a keyword-only constructor parameter `transport_retry: TransportRetryConfig | None = None`, stored as the given value or `TransportRetryConfig()`, with a docstring `:param:`. Route both chat call sites (the boolean-mode helper and the person-name extraction) through `chat_content_with_retry(self._chat, ..., context=...)` with the same model/messages/format kwargs as today. A None result gives ERROR for boolean modes and a failed extraction (`failed=True`) for names, so identity yields ERROR. Add the transport column to the module docstring matrix exactly as in the policy_matrix section, and add to the identity row wording that a transport error during extraction gives ERROR.
- test_checker.py: `_make_checker` gains a `transport_retry` argument defaulting to `TransportRetryConfig(max_retries=2, backoff_seconds=0.0)` so no test sleeps. Add `test_checker_transport_retry_count_honoured`, parametrized over exception instance (ConnectionError, httpx.ConnectTimeout, ollama.ResponseError with status 503) and max_retries (0, 2), using a MagicMock chat whose side_effect is that exception repeated max_retries + 1 times. It asserts ERROR and call_count == max_retries + 1. Also add `test_checker_transport_recovers_after_transient_failure` and `test_identity_transport_error_is_error` per the behavior block. Use only the chat_fn seam; do not patch Checker or chat.py internals.

Commit (stage only these 5 paths explicitly, with the same concurrent-change check as Task 1): `feat(SR-008): retry checker chat transport errors then record ERROR`, ending with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && uv run pytest -q tests/test_llm/test_checker.py tests/test_config tests/test_workflows/test_claim_pipeline.py -k "not test_analysis_coverage_other_label_is_false" && uv run python -c "from compliance.config.settings import load_config; r = load_config('config.yaml').checking.transport_retry; assert (r.max_retries, r.backoff_seconds) == (2, 1.0), r" && uv run ruff check --no-fix src/compliance/config/settings.py src/compliance/llm/chat.py src/compliance/llm/checker.py tests/test_llm/test_checker.py && uv run ruff format --check src/compliance/config/settings.py src/compliance/llm/chat.py src/compliance/llm/checker.py tests/test_llm/test_checker.py && uv run mypy src/compliance/config/settings.py src/compliance/llm/chat.py src/compliance/llm/checker.py && test "$(grep -vE '^\s*#' src/compliance/llm/chat.py | grep -cE 'except (Exception|BaseException)\b|except:')" = 0</automated>
  </verify>
  <done>Checker chat transport failures are retried per checking.transport_retry and then yield ERROR (boolean modes and identity). Non-transport exceptions still propagate. config.yaml carries the new block and loads. The new retry tests pass without sleeping. ruff, format and mypy (src) are clean. The Task 2 commit contains exactly the 5 files.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: wire checking.transport_retry into ClaimPipeline, add the matrix transport column, run gates, close SR-008</name>
  <files>src/compliance/workflows/claim_pipeline.py, tests/test_workflows/test_claim_pipeline.py, .gsd/review_backlog.md</files>
  <read_first>src/compliance/workflows/claim_pipeline.py (Checker builder helper from Task 1), tests/test_workflows/test_claim_pipeline.py (_POLICY_MATRIX, the policy helpers, _with_departure_uncertain_enabled), .gsd/review_backlog.md (SR-004 resolved block, SR-008 section, Steering status table)</read_first>
  <behavior>
    - With config checking.transport_retry = max_retries 1 and backoff_seconds 0.0 (deliberately NOT the default 2, which proves the pipeline honours config), each of the 5 boolean modes whose chat raises ConnectionError twice records ERROR, and the claim still writes analysis_result.json and predicted_answer.json with UNCERTAIN checker_error:<mode> and human_in_the_loop true. chat_fn.call_count equals exactly the responses supplied, with no extra retry.
    - Identity extraction raising ConnectionError twice gives ERROR / UNCERTAIN checker_error:identity.
  </behavior>
  <action>
Implements D-03 end to end. Re-read the files fresh.

- claim_pipeline.py: the Checker builder helper passes `transport_retry=checking.transport_retry`. Update the `run` / `_written_analysis_outputs` docstring wording only if it claims that checker LLM failures skip claims. The per-claim exception handler itself stays unchanged: it still covers classifier and I/O failures.
- test_claim_pipeline.py: add `_with_transport_retry(config, *, max_retries, backoff_seconds)`, mirroring `_with_departure_uncertain_enabled` (model_copy of checking with a new TransportRetryConfig). Apply it with max_retries=1 and backoff_seconds=0.0 in the matrix, identity and precedence tests. Add the 5 `transport_error` rows to `_POLICY_MATRIX` (override = two ConnectionError instances; expected ERROR / UNCERTAIN / checker_error:<mode>) and a transport row to `test_identity_outcome_policy`. The override helper must accept exception instances as items (MagicMock raises them). Existing rows must still pass unchanged.
- Gates, compared against the Task 1 baselines: `uv run ruff check --no-fix` and `uv run ruff format --check` on all 6 touched Python files (checker.py, chat.py, settings.py, claim_pipeline.py, test_checker.py, test_claim_pipeline.py). `uv run mypy` on the 4 touched src modules gives 0 errors, and on src + the 2 test files gives an error count no higher than baseline. Full `uv run pytest -q` (takes about 5.5 min) shows only the known test_analysis_coverage_other_label_is_false failure. If any new failure appears, fix it before continuing.
- Backlog (.gsd/review_backlog.md is gitignored: edit, never stage). Change the SR-008 header to `### [x] SR-008: Typed LLM/checker outcome policy matrix ⚠️`. Replace its "**Steering needed**" question list with a "**Steering (resolved 2026-09-29)**" block in the SR-004 style, listing D-01, D-02 and D-03 verbatim in substance, plus P-01..P-07 as "planner discretion, flagged". Add a one-paragraph "**Resolution:**" naming CheckOutcome, the checker_outcomes key, checking.transport_retry and the quick id 260929-hxe. Change the Steering status row to: `| SR-008 | Steered 2026-09-29: PASS/VIOLATION/ABSTAIN/ERROR; VIOLATION -> DENY beats ERROR -> UNCERTAIN + HITL; identity VIOLATION only when both names extracted; transport retry via checking.transport_retry then ERROR — done (quick 260929-hxe) |`. Touch no other SR entry.
- SUMMARY content (written by the executor workflow) must include: the recaptured baselines vs final gate numbers; the full policy matrix table; a before/after behaviour table (malformed not_authentic/incomplete DENY -> UNCERTAIN; malformed contradicts/healthy APPROVE -> UNCERTAIN; malformed containment no effect -> UNCERTAIN; identity parse failure UNCERTAIN identity_unclear -> UNCERTAIN checker_error:identity; checker transport failure claim skipped -> UNCERTAIN); every pre-existing test whose assertion changed and why; P-01..P-07; follow-ups (CaseClassifier transport errors still skip claims; no ollama client request timeout configured; httpx is imported directly but only declared transitively via ollama).

Commit (stage only claim_pipeline.py and test_claim_pipeline.py explicitly, with the same concurrent-change check): `feat(SR-008): honour checking.transport_retry in ClaimPipeline and cover transport column`, ending with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && uv run pytest -q tests/test_workflows/test_claim_pipeline.py -k "policy_matrix or identity_outcome_policy or checker_outcome_precedence" && grep -q "transport_retry=checking.transport_retry" src/compliance/workflows/claim_pipeline.py && uv run ruff check --no-fix src/compliance/llm/checker.py src/compliance/llm/chat.py src/compliance/config/settings.py src/compliance/workflows/claim_pipeline.py tests/test_llm/test_checker.py tests/test_workflows/test_claim_pipeline.py && uv run ruff format --check src/compliance/llm/checker.py src/compliance/llm/chat.py src/compliance/config/settings.py src/compliance/workflows/claim_pipeline.py tests/test_llm/test_checker.py tests/test_workflows/test_claim_pipeline.py && uv run mypy src/compliance/llm/checker.py src/compliance/llm/chat.py src/compliance/config/settings.py src/compliance/workflows/claim_pipeline.py && uv run pytest -q 2>&1 | tail -3 && grep -q "### \[x\] SR-008" .gsd/review_backlog.md && grep -q "| SR-008 | Steered 2026-09-29" .gsd/review_backlog.md</automated>
  </verify>
  <done>ClaimPipeline honours checking.transport_retry (proven with a non-default max_retries=1). All 30 matrix rows plus the identity and precedence rows pass. The full suite shows only the known pre-existing failure. ruff, format and mypy gates meet their baselines. SR-008 is checked off, with steering recorded in the backlog and the Steering status table. The Task 3 commit contains exactly the 2 source/test files.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| LLM response -> Checker | Untrusted model output (possibly steered by adversarial OCR text in a submitted document) crosses into a claim decision |
| Ollama transport -> Checker | Network/server failures of the local LLM service |
| Checker/pipeline -> logs | OCR text, patient/booking names and LLM content must not leak into log output |
| config.yaml -> CheckingConfig | Operator-supplied retry/backoff values |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-SR008-01 | Tampering | Checker boolean parse (`_boolean_outcome`) | high | mitigate | Malformed, missing-field or empty output from any mode gives ERROR, which gives UNCERTAIN + HITL; it never falls back to a PASS/deny default (D-01). Covered by the 25 non-transport matrix rows. |
| T-SR008-02 | Tampering | Identity extraction (`check_identity`) | high | mitigate | VIOLATION only when both names were validated via strict ExtractedNameResult; parse/schema failures give ERROR, null gives ABSTAIN (D-02); test_identity_outcome_policy + test_identity_extraction_outcomes |
| T-SR008-03 | Denial of Service | chat_content_with_retry | medium | mitigate | Bounded attempts (max_retries + 1) with ge=0 validation at config load; exhaustion yields ERROR, so the batch continues and the claim gets UNCERTAIN instead of being skipped (D-03). Retry-count tests prove the bound. |
| T-SR008-04 | Elevation of Privilege | chat_content_with_retry exception scope | medium | mitigate | Catch only the TRANSPORT_ERRORS tuple. Programming errors propagate to the existing per-claim handler instead of being disguised as UNCERTAIN. The Task 2 verify greps for the absence of a catch-all handler. |
| T-SR008-05 | Information Disclosure | retry / parse WARNING logs, run_checker branch log | medium | mitigate | Log only context labels, attempt counts, exception type names and outcome enum values, never response content, OCR text or extracted names (CLAUDE.md security rule) |
| T-SR008-06 | Repudiation | analysis_result.json | low | mitigate | Persist checker_outcomes per mode plus explanation checker_error:<modes>, so every UNCERTAIN/DENY is traceable to the checker outcome that caused it |
| T-SR008-07 | Denial of Service | large operator backoff_seconds | low | accept | Operator-controlled config value; exponential growth is bounded by small max_retries. There is no upper clamp, to avoid silently overriding the operator. |

No package installs in this plan (httpx and ollama are already installed), so there is no supply-chain row.
</threat_model>

<verification>
- `uv run pytest -q` shows only tests/test_config/test_settings.py::test_analysis_coverage_other_label_is_false failing (pre-existing), with every new SR-008 test passing.
- `uv run ruff check --no-fix` and `uv run ruff format --check` are clean on the 6 touched Python files.
- `uv run mypy` gives 0 errors on the 4 touched src modules; the touched test files have no more errors than the recaptured baseline.
- `git log --stat -3` shows 3 SR-008 commits, each containing only its task's files. .gsd/review_backlog.md is never staged.
- analysis_result.json for a seeded claim contains checker_outcomes plus the unchanged legacy boolean keys.
</verification>

<success_criteria>
- Malformed identity output cannot spuriously DENY, and malformed contradiction/healthy output cannot silently pass (backlog "Done when").
- The documented matrix (checker module docstring) is covered by parametrized tests for mode x {valid true, valid false, malformed JSON, missing field, empty response, transport error after retries}, together with the identity and precedence cases.
- A checker transport failure yields an UNCERTAIN predicted answer with human_in_the_loop instead of a skipped claim, and the retry count comes from config.yaml.
- SR-008 is marked [x] with steering recorded in .gsd/review_backlog.md.
</success_criteria>

<output>
Create `.planning/quick/260929-hxe-sr-008-typed-checker-outcome-policy-matr/260929-hxe-SUMMARY.md` when done
</output>
