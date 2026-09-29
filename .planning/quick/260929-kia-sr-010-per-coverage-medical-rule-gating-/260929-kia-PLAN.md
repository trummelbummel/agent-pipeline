---
phase: 260929-kia-sr-010-per-coverage-medical-rule-gating-
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/compliance/workflows/claim_pipeline.py
  - tests/test_workflows/test_claim_pipeline.py
  - README.md
  - LOGIC.md
  - .gsd/review_backlog.md
autonomous: true
requirements: [SR-010]

estimate:
  tokens: 95000
  raw_tokens: 95000
  tasks: 3
  confidence: low

must_haves:
  truths:
    - "One explicit rule set, computed once per claim from the routed coverage branch plus the classified document codes, decides which gated checks run. It replaces the four near-duplicate applicability helpers (identity / signature / authenticity / medical-document), so there is exactly one place that answers 'do medical rules apply to this claim?' (D-01)"
    - "Medical semantics — identity, signature, healthy, not_authentic, incomplete, suspicious_dating and departure_within_days — run only on the trip-cancellation branch when a classified document code is in the configured medical code set (identity via identity_required_codes; the other six via signature_required_codes). Personal effects, missed departure, and non-medical cancellation documents (police report, jury summons) skip all seven (D-01)"
    - "A non-medical claim cannot be DENIED for medical semantics even when every medical checker would have returned VIOLATION: the medical prompts are never sent, no medical outcome is recorded, and the only DENY sources left on those paths are checker_missing_documentation and checker_contradicts (D-01, backlog 'Done when')"
    - "analysis_result.json records the decision trace on every path that reaches the checker node: checker_rule_set names the rule set that ran (cancellation_medical | cancellation_non_medical | personal_effects_non_medical | missed_departure_non_medical) and checker_skipped lists every inapplicable gated check by name, in canonical order. checker_skipped is an empty list on a full medical path (D-02)"
    - "Invariant across the artifact: every gated check either has a recorded result (checker_outcomes entry, or its boolean key) or appears in checker_skipped — never both, never neither. Skipped checks are not silently written as passing booleans (D-02)"
    - "The run_checker branch log carries the rule-set name and the skipped check names, so a decision trace shows which rule set ran without reading the artifact. It logs check names and outcome values only — never OCR text, names or LLM content"
    - "Medical-path behaviour is unchanged apart from the two new trace keys: the SR-008 policy matrix, identity, precedence, healthy DENY, signature DENY, suspicious-dating UNCERTAIN and departure early-exit tests all still pass without assertion changes"
    - "Gates: uv run python -m pytest -q --cov (fast lane, integration deselected) passes with coverage at or above the 90 floor. ruff check --no-fix and ruff format --check are clean on both touched .py files. mypy reports 0 errors on claim_pipeline.py and no more than the 11-error baseline on the touched test file"
  artifacts:
    - path: src/compliance/workflows/claim_pipeline.py
      provides: "GatedCheck literal, _GATED_CHECKS canonical order, CheckerRuleSet NamedTuple, _checker_rule_set producer, rule-set-gated _checker_results / _checker_outcomes, checker_rule_set + checker_skipped state and payload keys"
      contains: "class CheckerRuleSet"
    - path: tests/test_workflows/test_claim_pipeline.py
      provides: "test_non_medical_branch_cannot_deny_for_medical_semantics, test_checker_rule_set_matrix, test_suspicious_dating_skipped_on_non_medical_branch, test_skipped_checks_have_no_recorded_result; PE/missed fixtures updated for the skipped healthy call"
      contains: "def test_checker_rule_set_matrix"
    - path: LOGIC.md
      provides: "Branch checker lists and the coverage-route table state medical semantics are medical-only, with suspicious dating included"
      contains: "healthy_check — skipped"
    - path: README.md
      provides: "Cheap-gate note and rule-matrix rows corrected for medical-only healthy / dating"
      contains: "medical semantics"
    - path: .gsd/review_backlog.md
      provides: "SR-010 checked off with recorded steering decisions (gitignored, never staged)"
      contains: "### [x] SR-010"
  key_links:
    - from: "ClaimPipeline._run_checker_node"
      to: "ClaimPipeline._checker_rule_set"
      via: "the node computes the rule set once and passes it to the checker run, the signature gate, and the payload builder"
      pattern: "_checker_rule_set\\(state\\)"
    - from: "CheckerRuleSet.applicable"
      to: "ClaimPipeline._checker_outcomes"
      via: "identity / healthy / not_authentic / incomplete each run only when their name is in the applicable set"
      pattern: "in rule_set.applicable"
    - from: "CheckerRuleSet.applicable"
      to: "compliance.workflows.claim_dates._suspicious_dating / _departure_beyond_days"
      via: "both deterministic date gates are computed only when their check is applicable"
      pattern: "\"suspicious_dating\" in rule_set.applicable"
    - from: "CheckerRuleSet"
      to: "analysis_result.json"
      via: "checker_rule_set (name) and checker_skipped (inapplicable check names) written beside checker_outcomes"
      pattern: "checker_skipped"
    - from: "CheckerRuleSet"
      to: "run_checker branch log"
      via: "log_branch_decision carries rule_set and skipped so decision traces name the rule set"
      pattern: "rule_set=rule_set.name"
---

<objective>
SR-010 makes the per-coverage rule set explicit. Today `healthy` and `suspicious_dating` run on every branch, so a police report, a theft proof or a boarding pass can be DENIED (healthy) or made UNCERTAIN (dating) by rules that only mean something on a medical certificate. Identity, signature, authenticity and incomplete are already gated, but through four near-duplicate `_*_applies` helpers (one of which, `_authenticity_required_applies`, is dead code) — there is no single place that states the rule matrix, and no trace of which rules ran.

This plan introduces one `CheckerRuleSet` computed once per claim, gates all seven medical checks through it, and records the rule set plus the skipped checks in the artifact and the branch log.

Locked decisions (from CONTEXT.md and `.gsd/steering-decisions-2026-09-29.md`):
- D-01: Medical-only matrix. `healthy`, `suspicious_dating`, and identity/signature apply only on the cancellation medical taxonomy / applicable documents (identity_required_codes, signature_required_codes). Personal effects, missed departure, and non-medical cancellation documents (police report, jury summons) skip medical semantics and must not DENY for them.
- D-02: Inapplicable checks are recorded as skipped in the artifacts, not omitted.

Planner discretion (flagged; report in SUMMARY):
- P-01: `CheckOutcome` gains no `SKIPPED` member. `Checker` never produces a skip — applicability is a pipeline/coverage concern — and the parallel record covers the three deterministic gates (signature, suspicious_dating, departure) that have no `CheckOutcome` at all. Skips are recorded once, in `checker_skipped`, using the vocabulary of check names.
- P-02: One artifact invariant instead of two representations of the same fact: a skipped check has **no** recorded result. `healthy_check`, `signature_check`, `checker_suspicious_dating` and `departure_within_days` keys are omitted on paths where those checks are skipped, and the check name appears in `checker_skipped` instead. This is what makes "cannot be denied solely for medical semantics" structurally true rather than only test-true: the DENY fold reads legacy keys and `CheckOutcome.VIOLATION` entries that no longer exist for skipped checks. Today `signature_check: true` is written on non-medical paths, meaning "not applicable" — an inapplicable check reported as a pass. That key now moves to `checker_skipped`.
- P-03: Two code groups, mirroring the two existing config lists rather than merging them: `identity_required_codes` enables `identity`; `signature_required_codes` enables `signature`, `healthy`, `not_authentic`, `incomplete`, `suspicious_dating`, `departure`. Both are `["1", "4"]` in config.yaml (medical certificate, hospital admission), so the two groups coincide in practice, but a deployment that separates them keeps the separation. Empty list = that group never applies (today's semantics, preserved).
- P-04: `departure_within_days` moves from its incidental coupling (it is gated on `run_identity` today) onto the medical document group. Same effective behaviour, explicit reason. The gate is disabled in config.yaml (`departure_uncertain_enabled: false`), so this cannot change live decisions.
- P-05: Rule-set names are `{branch}_medical` / `{branch}_non_medical`, so a trace distinguishes a cancellation claim with a medical certificate from one with a police report. The coverage-abstention path never reaches the checker node, so it has no rule set and the two trace keys stay absent (unchanged artifact shape for that path).
- P-06: `missing_documentation`, `containment` and `contradicts` are never gated — they carry no medical semantics. After this change the only DENY sources on a non-medical path are `checker_missing_documentation` and `checker_contradicts`.

Behaviour changes to record in the SUMMARY (intended by D-01, not regressions to fix here):
- A PE / missed-departure / police-report / jury-summons claim whose supporting document asserts the patient is healthy is no longer DENIED for `healthy_check`.
- The same claims are no longer made UNCERTAIN by `checker_suspicious_dating`.
- Per LOGIC.md's last measured batch, `healthy_check` decided claims 2, 10, 14 and `checker_suspicious_dating` is expected on 13, 16. Whether any of those flips depends on the coverage/document route each claim takes at analysis time (claims 17 and 22 are known to route cancellation-medical, since `signature_check` fired on them). Re-running `make analyze` + `make evaluation` to re-measure is a follow-up, not part of this plan (evaluation validity is SR-006).

Purpose: stop rules with medical meaning from deciding non-medical evidence (backlog risk "Non-medical docs denied for medical rules"), and make the applied rule set auditable.
Output: one explicit rule-set model, seven gated checks, a per-claim rule-set trace in artifacts and logs, tests over all four routed rule sets, corrected docs, and SR-010 closed in the backlog.
</objective>

<execution_context>
@~/.claude/gsd-core/workflows/execute-plan.md
@~/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/STATE.md
@.planning/quick/260929-kia-sr-010-per-coverage-medical-rule-gating-/260929-kia-CONTEXT.md
@.gsd/steering-decisions-2026-09-29.md (SR-010)
@.gsd/review_backlog.md (section "SR-010" and the "## Steering status" table; the SR-008 / SR-011 sections show the resolved-steering format)
@src/compliance/workflows/claim_pipeline.py (_legacy_booleans_from_outcomes, ClaimAnalysisState, _STATE_BOOLEAN_KEYS, CheckerRunResult, _run_checker_node, _signature_required_applies / _identity_required_applies / _authenticity_required_applies / _medical_document_check_applies, _is_cancellation_coverage, _signature_check_result, _checker_results, _checker_outcomes, _classified_document_codes, _analysis_result_payload, _violated_checkers, _decision_from_state)
@src/compliance/llm/checker.py (CheckOutcome, CheckerMode — read only; this plan does not modify it)
@src/compliance/workflows/claim_dates.py (_suspicious_dating, _departure_beyond_days, _reference_today)
@config.yaml (analysis.required_documents: identity_required_codes, signature_required_codes)
@tests/test_workflows/test_claim_pipeline.py (_config, _analysis_config, _seed_preprocessed_claim, _COVERAGE_WINNER_TAILS, _COVERAGE_WINNER_EXPECTATIONS, _pe_chat_fn, _missed_chat_fn, _seed_policy_matrix_claim, _policy_matrix_chat_side_effect, _with_transport_retry)
@tests/conftest.py (build_minimal_app_config, cancellation_chat_factory)
@LOGIC.md (lines ~118-215: cheap-gate table, branch diagram, coverage-route table; ~270-300 denial-rule descriptions)
@README.md (lines ~222-235: cheap-gate table and the note on LLM-only checks)

Facts verified at planning time (files re-read fresh; a concurrent session has been landing other SR-* items):
- `healthy` is the only LLM checker with no applicability gate today, and `_suspicious_dating` is computed for every branch. `departure_within_days` is gated on `run_identity`, i.e. on identity_required_codes.
- `_authenticity_required_applies` is dead code: it only delegates to `_medical_document_check_applies`, and nothing calls it. None of the four `_*_applies` helpers is referenced from tests or from any other module.
- `_legacy_booleans_from_outcomes` keys off mode presence in the outcomes dict, so a mode that does not run already yields the right legacy shape (identity absent → identity_check True / identity_unclear False; healthy absent → no healthy_check key). Nothing else needs to learn about skips.
- `_violated_checkers` reads `"signature_check" in state` and `_state_boolean_flags` filters `_STATE_BOOLEAN_KEYS` by presence, so omitting a skipped check's boolean is already safe in the fold and in persistence. `src/evaluation/analysis_stats.py` counts presence separately from truth (`checker_present_counts`), so dropped keys lower a present count and need no change there. `src/api` passes the analysis payload through as `dict[str, Any]`.
- Existing PE/missed chat fixtures supply a `healthy` response and assert an exact `call_count`: `_pe_chat_fn` / `_missed_chat_fn` (4 calls, asserted at three sites) and `_COVERAGE_WINNER_TAILS` + `_COVERAGE_WINNER_EXPECTATIONS` for PE and missed departure (`call_count: 4`). Each drops to 3 once `healthy` is skipped. `_coverage_route_chat_fn` relies on StopIteration for an unexpected extra call, so the tails must shrink rather than keep an unused response.
- Every assertion on `signature_check`, `departure_within_days` and `checker_suspicious_dating` in the test suite is on a cancellation medical-certificate or hospital-admission claim, so omitting those keys on non-medical paths breaks no existing assertion.
- `tests/test_api/conftest.py` builds `AnalysisConfig` with the default `RequiredDocumentsConfig` (all code lists empty), so API claims resolve to a non-medical rule set and simply make fewer chat calls; those tests assert neither call counts nor checker keys.
- Checker system prompts in tests are the exact strings "containment", "contradicts", "identity", "healthy", "authenticity", "incomplete" (tests/conftest.py), and classifier prompts are "classify ..." strings — so prompt-level assertions can compare exact values.
- ruff targets py310, line-length 120, C901 max-complexity 10, TRY rules on. `.gsd/` is gitignored.
- Baselines recaptured at planning time: `uv run python -m pytest -q --cov` → 368 passed, 3 deselected, 2.7s, total coverage 90.95% against a `fail_under = 90` floor (thin headroom — new untested branches can fail the gate). ruff check + ruff format clean on both touched .py files. mypy: 0 errors on `src/compliance/workflows/claim_pipeline.py`, 11 errors on `tests/test_workflows/test_claim_pipeline.py`.
</context>

<rule_matrix>
The locked matrix (D-01). "run" = the check executes and records a result; "skipped" = the check name goes in `checker_skipped` and no result is recorded (P-02).

| Routed path → rule set | missing_documentation | containment | contradicts | identity | signature | healthy | not_authentic | incomplete | suspicious_dating | departure |
|------------------------|-----------------------|-------------|-------------|----------|-----------|---------|---------------|------------|-------------------|-----------|
| cancellation + medical certificate / hospital admission → `cancellation_medical` | run | run | run | run | run | run | run | run | run | run |
| cancellation + police report / jury summons → `cancellation_non_medical` | run | run | run | skipped | skipped | skipped | skipped | skipped | skipped | skipped |
| personal effects → `personal_effects_non_medical` | run | run | run | skipped | skipped | skipped | skipped | skipped | skipped | skipped |
| missed departure → `missed_departure_non_medical` | run | run | run | skipped | skipped | skipped | skipped | skipped | skipped | skipped |
| coverage abstention | checker node never runs (UNCERTAIN `coverage_false_label`); no rule set, no trace keys |

Applicability source (P-03), evaluated against the non-abstention classified document codes of the routed document stage:
- `identity` ← `analysis.required_documents.identity_required_codes`
- `signature`, `healthy`, `not_authentic`, `incomplete`, `suspicious_dating`, `departure` ← `analysis.required_documents.signature_required_codes`
- both groups require the routed branch to be `cancellation`; an empty configured list means that group never applies.

Canonical check order (used for `checker_skipped` ordering): identity, signature, healthy, not_authentic, incomplete, suspicious_dating, departure.

DENY sources surviving on a non-medical path: `checker_missing_documentation`, `checker_contradicts` (P-06).
</rule_matrix>

<tasks>

<task type="tracer" tdd="true">
  <name>Task 1 (tracer): one CheckerRuleSet gates every medical check, end to end from routing to artifact</name>
  <files>src/compliance/workflows/claim_pipeline.py, tests/test_workflows/test_claim_pipeline.py</files>
  <read_first>src/compliance/workflows/claim_pipeline.py (lines ~36-210 types/constants/state, ~468-508 run_checker node, ~679-756 applicability helpers + signature gate, ~830-963 checker results/outcomes, ~964-1012 payload), tests/test_workflows/test_claim_pipeline.py (lines ~240-320 coverage tails/expectations, ~656-680 identity-skip test, ~947-1040 PE/missed fixtures and route tests, ~1986-2014 authenticity-skip test)</read_first>
  <behavior>
    - Tracer end-to-end: a personal-effects claim whose supporting document would trip every medical checker (OCR asserts the patient is clinically healthy and carries an implausible certificate issue date) is APPROVED. `checker_outcomes` holds only containment and contradicts; `checker_rule_set` is `personal_effects_non_medical`; `checker_skipped` lists all seven gated checks in canonical order; `healthy_check`, `signature_check`, `checker_suspicious_dating` and `departure_within_days` are absent from the artifact; the checker system prompts sent are exactly {"containment", "contradicts"} and none of {"identity", "healthy", "authenticity", "incomplete"} is ever sent.
    - Medical path unchanged plus trace: the cancellation medical-certificate claim still runs all six checker modes in the existing order, and its artifact now also has `checker_rule_set` == `cancellation_medical` with `checker_skipped` == [].
    - Existing PE / missed-departure fixtures make one fewer chat call (no healthy), and every pre-existing medical-path test (SR-008 policy matrix, identity policy, precedence, healthy DENY, signature DENY, suspicious-dating UNCERTAIN, departure early-exit, coverage-abstention) passes with no assertion changes.
  </behavior>
  <action>
Step 0, before editing: re-read both files fresh and recapture the baselines for the SUMMARY — `uv run python -m pytest -q --cov` (pass count + total coverage), `uv run ruff check --no-fix` / `uv run ruff format --check` on both files, `uv run mypy src/compliance/workflows/claim_pipeline.py` and `uv run mypy tests/test_workflows/test_claim_pipeline.py` (error counts). Planning-time values are in the context block. Write the failing tests first (RED), then implement.

claim_pipeline.py, implementing D-01, D-02 with P-01..P-06:
- Add a `GatedCheck` Literal alias beside `CoverageBranch` with the seven members in canonical order, and a module-level `_GATED_CHECKS: tuple[GatedCheck, ...]` holding that order. A short WHY comment states these are the checks whose semantics are specific to a medical document, per the rule matrix.
- Add a `CheckerRuleSet` NamedTuple (fields `name: str`, `applicable: frozenset[GatedCheck]`) with a class docstring carrying the rule matrix in the compact form of the plan's table, `:param:` for both fields, and a `skipped` property returning the `_GATED_CHECKS` members absent from `applicable`, as a tuple. Do not name the deleted helpers in any comment or docstring.
- Add `_checker_rule_set(self, state) -> CheckerRuleSet`, the single producer: a non-cancellation branch yields `f"{branch}_non_medical"` with an empty applicable set; on cancellation it intersects `_classified_document_codes(state)` with each configured code group (P-03) and unions the enabled checks, then names the set `cancellation_medical` when anything applies and `cancellation_non_medical` otherwise. Express the two groups as one module-level table of (enabled checks) keyed by group so there is no if/elif ladder growth when a group is added; read the code lists off `self._config.analysis.required_documents` explicitly, not by attribute-name string lookup.
- Delete `_signature_required_applies`, `_identity_required_applies`, `_medical_document_check_applies`, `_authenticity_required_applies` (dead) and `_signature_check_result`. `_is_cancellation_coverage` stays: the rule-set producer uses it.
- `_checker_results`: replace the `run_identity` / `run_medical_document_checks` keyword pair with a single `rule_set: CheckerRuleSet` compound parameter (CLAUDE.md: prefer one compound parameter). Compute `departure_within_days` only when `departure` is applicable (keeping the existing `departure_uncertain_enabled` conjunction) and `suspicious_dating` only when `suspicious_dating` is applicable; both are False when skipped. The existing early-exit (either date flag True → empty outcomes) is unchanged. Pass the rule set through to `_checker_outcomes`.
- `_checker_outcomes`: take `rule_set` instead of the two booleans and gate `identity`, `healthy`, `not_authentic` and `incomplete` on membership in `rule_set.applicable`. Keep the call order exactly containment → contradicts → identity → healthy → not_authentic → incomplete; the module docstring note about MagicMock side_effect order still holds and must be kept accurate. `containment` and `contradicts` stay ungated (P-06).
- Add `checker_rule_set: str` and `checker_skipped: list[str]` to `ClaimAnalysisState` with `:param:` docstrings explaining that the pair is the per-claim rule-set trace and that a listed check has no recorded result (P-02). Note in the `healthy_check` / `signature_check` / `departure_within_days` / `checker_suspicious_dating` params that the key is absent when the check is skipped.
- `_run_checker_node`: compute the rule set once, pass it to `_checker_results`, and extract the payload assembly into a helper named after what it produces (e.g. `_checker_node_payload(state, rule_set, results)`) so the node stays a compute-log-return orchestrator and every method stays inside C901 10. The payload always carries `checker_rule_set` (name) and `checker_skipped` (`list(rule_set.skipped)`). `departure_within_days` and `checker_suspicious_dating` are included only when their check is applicable, preserving today's rule that the suspicious-dating key appears on the early-exit path. `signature_check` is included only when `signature` is applicable, and its value is `document_has_signature` from state. When no date gate fired, the payload also carries `checker_outcomes` and the derived legacy booleans exactly as today.
- Branch log in `_run_checker_node`: keep the existing fields but replace the hard-coded non-early-exit reason string with the rule-set name, and add `rule_set` plus a comma-joined `skipped`. Log check names and outcome values only.
- `_analysis_result_payload`: write `checker_rule_set` and `checker_skipped` when present in state, beside the existing `checker_outcomes` block. `_STATE_BOOLEAN_KEYS` is unchanged (presence filtering already does the right thing).

tests/test_workflows/test_claim_pipeline.py:
- Update the fixtures that assumed an always-on healthy check: drop the trailing healthy response from `_pe_chat_fn` and `_missed_chat_fn` (and their docstrings), drop the second `{"result": False}` from the PERSONAL_EFFECTS and MISSED_DEPARTURE entries of `_COVERAGE_WINNER_TAILS`, and lower those two `_COVERAGE_WINNER_EXPECTATIONS` `call_count` values to 3. Fix the three exact `call_count == 4` assertions on PE/missed claims (in the identity-skip test and the two coverage-route tests) to 3, and correct the inline comment listing the calls.
- Add a seeding helper for a non-medical claim with hostile medical evidence: a PE claim whose description is not embedded in the supporting document (so containment reaches the LLM), whose OCR asserts the patient is clinically healthy, and whose OCR carries an issue date far from the booking reference date (reuse the dating pattern from the existing suspicious-dating test: booking `**current date**` 2022-06-01 with a 2021-01-01 certificate issue date).
- Add `test_non_medical_branch_cannot_deny_for_medical_semantics` over that claim, asserting the full tracer behaviour above. Assert the skipped list equals the canonical seven-name order, and assert the absent keys explicitly.
- Extend one existing medical-path assertion set (the cancellation analysis-result test) with `checker_rule_set` == `cancellation_medical` and `checker_skipped` == [].

Commit: stage only the two paths explicitly (never `git add -A` / `git add .`, never bypass hooks). First run `git status --short` and `git diff --stat -- <the 2 paths>`; if a path shows hunks this task did not write (concurrent session), stop and report instead of committing. Message `feat(SR-010): gate medical checker rules on an explicit per-coverage rule set`, ending with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && uv run python -m pytest -q tests/test_workflows/test_claim_pipeline.py tests/test_api tests/test_evaluation && uv run python -m pytest -q tests/test_workflows/test_claim_pipeline.py -k "non_medical_branch_cannot_deny" && uv run ruff check --no-fix src/compliance/workflows/claim_pipeline.py tests/test_workflows/test_claim_pipeline.py && uv run ruff format --check src/compliance/workflows/claim_pipeline.py tests/test_workflows/test_claim_pipeline.py && uv run mypy src/compliance/workflows/claim_pipeline.py && test "$(grep -vE '^\s*#' src/compliance/workflows/claim_pipeline.py | grep -cE '_identity_required_applies|_medical_document_check_applies|_authenticity_required_applies|_signature_required_applies')" = 0 && grep -q "class CheckerRuleSet" src/compliance/workflows/claim_pipeline.py</automated>
  </verify>
  <done>One `CheckerRuleSet` decides all seven gated checks; the four applicability helpers are gone. A PE claim with hostile medical OCR is APPROVED, sends no medical prompt, and records `checker_rule_set` + the seven skipped names. The medical path is unchanged apart from the trace keys. Pipeline, API and evaluation tests pass; ruff, format and mypy (src) are clean. The commit contains exactly the 2 files.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: rule-set matrix coverage for all four routed paths plus the skipped-result invariant</name>
  <files>tests/test_workflows/test_claim_pipeline.py</files>
  <read_first>tests/test_workflows/test_claim_pipeline.py (the Task 1 helpers, `_seed_policy_matrix_claim`, `_policy_matrix_chat_side_effect`, `_classifier_responses`, the suspicious-dating tests ~1790-1990), src/compliance/workflows/claim_pipeline.py as left by Task 1</read_first>
  <behavior>
    - `test_checker_rule_set_matrix`, parametrized over the four routed rule sets — cancellation + medical certificate, cancellation + hospital admission, cancellation + police report (reason: theft/criminal), cancellation + jury summons (reason: jury duty), personal effects (proof of theft), missed departure (incident report) — asserts for each: `checker_rule_set`, the exact `checker_skipped` list, which modes appear in `checker_outcomes`, the decision (APPROVE with `checker_consistent` on every row, since no non-medical violation is seeded) and that the checker system prompts contain no medical prompt on the non-medical rows.
    - `test_suspicious_dating_skipped_on_non_medical_branch`: the same implausible dating that yields UNCERTAIN `checker_suspicious_dating` on a medical certificate yields APPROVE on a police-report cancellation claim, with `suspicious_dating` in `checker_skipped` and no `checker_suspicious_dating` key.
    - `test_skipped_checks_have_no_recorded_result`: for one medical and one non-medical claim, every name in `checker_skipped` has neither a `checker_outcomes` entry nor its boolean artifact key, and every gated check missing from `checker_skipped` has exactly one of the two. Drive the check→artifact-key mapping from a single module-level table so the invariant cannot drift from the rule matrix.
  </behavior>
  <action>
Re-read the file as left by Task 1. Tests only — no source change in this task; if the invariant test fails, fix `claim_pipeline.py` and say so in the SUMMARY.

- Add a module-level table mapping each `GatedCheck` name to how its result is recorded: the four LLM modes to their `checker_outcomes` key, and `signature` / `suspicious_dating` / `departure` to their boolean artifact keys (`signature_check`, `checker_suspicious_dating`, `departure_within_days`). This table is the single source for both the matrix test and the invariant test.
- Add a DRY seeding + chat helper pair for arbitrary routed paths, reusing `_seed_preprocessed_claim` and `_classifier_responses` rather than copying classifier response blocks per row: the parameters that vary are the coverage code, the optional reason code, the document code, and the checker responses the path is expected to consume. Keep the response order coverage → (reason) → document → checker modes in the pipeline's fixed order.
- Add the three tests from the behavior block. Every row must assert `chat_fn.call_count == len(side_effect)` so an unexpectedly-run medical check fails loudly rather than silently consuming a benign response.
- Non-medical cancellation rows must not trip `checker_missing_documentation`: pair reason 3 (theft or criminal incident) with document 2 (police report) and reason 1 (jury duty) with document 3 (jury summons), matching `cancellation_by_reason` in the test analysis config.
- Keep the existing SR-008 matrix, identity and precedence tests untouched; they already cover the medical path and must still pass unchanged.

Commit (stage only the one path, with the same concurrent-change check as Task 1): `test(SR-010): cover the per-coverage rule set matrix and skipped-result invariant`, ending with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && uv run python -m pytest -q tests/test_workflows/test_claim_pipeline.py -k "rule_set_matrix or suspicious_dating_skipped_on_non_medical or skipped_checks_have_no_recorded_result" && uv run python -m pytest -q --cov && uv run ruff check --no-fix tests/test_workflows/test_claim_pipeline.py && uv run ruff format --check tests/test_workflows/test_claim_pipeline.py && grep -q "def test_checker_rule_set_matrix" tests/test_workflows/test_claim_pipeline.py</automated>
  </verify>
  <done>All four routed rule sets (six parametrized rows) assert their name, skipped list, recorded modes and decision. Suspicious dating is proven skipped on a non-medical cancellation claim. The skipped-vs-recorded invariant holds on both a medical and a non-medical claim. The full fast lane passes with coverage at or above the 90 floor. The commit contains exactly the 1 file.</done>
</task>

<task type="auto">
  <name>Task 3: correct the documented rule matrix, run the gates, close SR-010</name>
  <files>LOGIC.md, README.md, .gsd/review_backlog.md</files>
  <read_first>LOGIC.md (lines ~118-130 cheap-gate table and the LLM-only note, ~131-215 branch diagram and coverage-route table, ~270-300 denial-rule list and the code note, ~350-356 denial-rule table rows for identity and suspicious dating), README.md (lines ~222-235), .gsd/review_backlog.md (the SR-010 section, the SR-008 / SR-011 resolved-steering format, and the "## Steering status" table)</read_first>
  <action>
Docs must state the locked matrix; today both files claim `healthy_check` runs on personal effects and missed departure, and describe suspicious dating as branch-agnostic. Change only the statements that are now wrong — no restructuring, no new sections.

- LOGIC.md: in the branch diagram, change the `healthy_check` bullet under the Personal Effects and Missed Departure `run_checker` boxes to the skipped form already used there for identity and signature, and under the Trip cancellation box qualify `healthy_check` (and add suspicious dating) as applying on the medical certificate / hospital admission codes. Preserve the box-drawing alignment exactly. In the coverage-route table, move `healthy_check` on the PE and missed rows into the "skipped" clause and qualify it on the cancellation row. Update the LLM-only note so it says medical semantics (healthy, suspicious dating, identity, signature, authenticity, incomplete) are skipped on non-medical branches. In the denial-rule descriptions, add to the healthy entry that it runs only on the medical document codes, and to the suspicious-dating entry that it is evaluated on medical documents only. Add one sentence naming the two trace keys (`checker_rule_set`, `checker_skipped`) and stating that a skipped check records no result.
- README.md: in the sentence that today says `contradicts` and `healthy_check` stay LLM-only while identity/signature are skipped on non-medical branches, keep the LLM-only claim for `contradicts` and correct the skip list to the full medical set. In the cheap-gate table, mark the medical-only gates as such where the table implies they are universal.
- Gates, compared against the Task 1 baselines: `uv run python -m pytest -q --cov` (fast lane) passes with coverage at or above the 90 floor; `uv run ruff check --no-fix` and `uv run ruff format --check` clean on both touched .py files; `uv run mypy src/compliance/workflows/claim_pipeline.py` 0 errors and `uv run mypy tests/test_workflows/test_claim_pipeline.py` no worse than the recaptured baseline. Fix any new failure before committing.
- Backlog (`.gsd/review_backlog.md` is gitignored: edit, never stage). Change the SR-010 header to `### [x] SR-010: Per-coverage medical rule gating ⚠️`, replace its "**Steering needed**" questions with a "**Steering (resolved 2026-09-29)**" block in the SR-008 style listing D-01 and D-02 plus P-01..P-06 as "planner discretion, flagged", and add a one-paragraph "**Resolution:**" naming `CheckerRuleSet`, the `checker_rule_set` / `checker_skipped` keys, the two config code groups and the quick id 260929-kia. Update the Steering status row to `| SR-010 | Steered 2026-09-29: medical-only healthy/dating/identity/signature; inapplicable recorded as skipped — done (quick 260929-kia) |`. Touch no other SR entry.
- SUMMARY content (written by the executor workflow) must include: recaptured baselines vs final gate numbers; the rule matrix as implemented; the behaviour-change register from the objective, including which artifact keys are no longer written on non-medical paths and the claims (2, 10, 14 healthy; 13, 16 dating) whose measured decisions may move; P-01..P-06; and the follow-ups — re-run `make analyze` + `make evaluation` to re-measure accuracy under the new matrix (SR-006 territory), and SR-013 can now extract the rule set as the seed of the policy engine.

Commit (stage only LOGIC.md and README.md explicitly, with the same concurrent-change check as Task 1): `docs(SR-010): document the medical-only checker rule matrix`, ending with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && uv run python -m pytest -q --cov && uv run ruff check --no-fix src/compliance/workflows/claim_pipeline.py tests/test_workflows/test_claim_pipeline.py && uv run ruff format --check src/compliance/workflows/claim_pipeline.py tests/test_workflows/test_claim_pipeline.py && uv run mypy src/compliance/workflows/claim_pipeline.py && grep -q "healthy_check — skipped" LOGIC.md && grep -q "checker_skipped" LOGIC.md && grep -q "### \[x\] SR-010" .gsd/review_backlog.md && grep -q "| SR-010 | Steered 2026-09-29" .gsd/review_backlog.md && STAGED="$(git diff --cached --name-only)" && test "$(printf '%s' "$STAGED" | grep -c review_backlog)" = 0</automated>
  </verify>
  <done>LOGIC.md and README.md state the medical-only matrix and the two trace keys, with no remaining claim that healthy or suspicious dating runs on PE / missed / non-medical cancellation paths. The fast lane, ruff, format and mypy gates all meet their baselines. SR-010 is checked off with steering recorded in the backlog and the Steering status table, and the backlog is not staged. The commit contains exactly the 2 doc files.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Claimant document OCR → checker rule selection | Attacker-influenced document text reaches the classifiers whose codes select the rule set |
| LLM checker output → claim decision | Untrusted model output becomes a DENY / UNCERTAIN reason |
| config.yaml `required_documents` → rule set | Operator-supplied code lists decide which rules apply |
| Pipeline → logs / artifacts | Decision traces must not leak OCR text, patient names or LLM content |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-SR010-01 | Tampering | `_checker_outcomes` / `_checker_results` medical gating | high | mitigate | Medical checks run only when the rule set marks them applicable (D-01), so a police report, theft proof or booking screenshot cannot be DENIED by `healthy` / identity / authenticity / incomplete or made UNCERTAIN by suspicious dating. Proven by the tracer test and the six-row rule-set matrix, each asserting exact chat call counts. |
| T-SR010-02 | Elevation of Privilege | skipped-check recording (`checker_skipped`) | high | mitigate | A skipped check records no outcome and no boolean (P-02), so the DENY fold — which reads `CheckOutcome.VIOLATION` entries and legacy boolean keys — has nothing to deny on. Enforced by `test_skipped_checks_have_no_recorded_result`. |
| T-SR010-03 | Repudiation | analysis_result.json + run_checker branch log | medium | mitigate | Every claim that reaches the checker node records `checker_rule_set` and `checker_skipped` in the artifact, and the branch log names the rule set, so an operator can tell which rule set decided the claim (D-02). |
| T-SR010-04 | Information Disclosure | rule-set branch log fields | medium | mitigate | The log carries the rule-set name, gated-check names and outcome enum values only — never OCR text, extracted names or LLM content (CLAUDE.md security rule). |
| T-SR010-05 | Tampering | `required_documents` code lists | medium | accept | An empty or narrowed code list means medical rules never apply, i.e. gating fails open toward APPROVE. This is pre-existing config semantics, cross-validated against stage vocabularies at load time by SR-011, and the rule-set name in every artifact makes the resulting posture visible per claim. No clamp is added, to avoid silently overriding the operator. |
| T-SR010-06 | Spoofing | document classifier choosing the rule set | medium | accept | A crafted document that classifies as a medical certificate pulls itself into the stricter medical rule set, and one that misclassifies away from it escapes those rules. Classification robustness is out of scope here (SR-004 settled routing); the artifact records the code and rule set that were used, so the escape is auditable. |

No package installs in this plan, so there is no supply-chain row.
</threat_model>

<verification>
- `uv run python -m pytest -q --cov` (fast lane, integration deselected) passes with total coverage at or above the `fail_under = 90` floor; the 368-test planning baseline plus the new SR-010 tests all pass.
- `uv run ruff check --no-fix` and `uv run ruff format --check` are clean on `src/compliance/workflows/claim_pipeline.py` and `tests/test_workflows/test_claim_pipeline.py`.
- `uv run mypy src/compliance/workflows/claim_pipeline.py` reports 0 errors; the touched test file is no worse than its 11-error baseline.
- `git log --stat -3` shows 3 SR-010 commits, each containing only its task's files; `.gsd/review_backlog.md` is never staged.
- An artifact from a personal-effects claim contains `checker_rule_set` / `checker_skipped` and no `healthy_check`, `signature_check`, `checker_suspicious_dating` or `departure_within_days` key; an artifact from a cancellation medical-certificate claim contains all of them with `checker_skipped: []`.
</verification>

<success_criteria>
- Police, loss, booking and other non-medical evidence cannot be denied solely for medical semantics (backlog "Done when"), even when every medical checker would have returned a violation.
- Decision traces show which rule set ran and which checks were skipped, in both the artifact and the `run_checker` branch log (backlog "Done when", D-02).
- Tests cover personal effects, missed departure, and police-report / jury-summons cancellation paths against the medical-certificate and hospital-admission paths.
- One rule-set producer is the only place that decides medical applicability; the four `_*_applies` helpers are gone and nothing was left behind by a `# noqa`.
- README.md and LOGIC.md describe the implemented matrix, and SR-010 is marked `[x]` with steering recorded in `.gsd/review_backlog.md`.
</success_criteria>

<output>
Create `.planning/quick/260929-kia-sr-010-per-coverage-medical-rule-gating-/260929-kia-SUMMARY.md` when done
</output>
