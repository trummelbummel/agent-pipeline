---
phase: 260929-ftg-sr-004-single-authoritative-coverage-rou
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/compliance/workflows/claim_pipeline.py
  - tests/test_workflows/test_claim_pipeline.py
  - .gsd/review_backlog.md
autonomous: true
requirements: [SR-004]

estimate:
  tokens: 90000
  raw_tokens: 90000
  tasks: 3
  confidence: low

must_haves:
  truths:
    - "Coverage selections [\"1\",\"2\"] and [\"2\",\"1\"] with the same probabilities produce the same routed_coverage_label_code, the same LLM call path, and the same decision. The selected label with the highest probability wins (D-01)"
    - "For [\"False\",\"1\"] and [\"1\",\"False\"]: when False has the highest probability, the claim takes the persist-only path (1 LLM call) with decision UNCERTAIN / coverage_false_label and human_in_the_loop true. When 1 has the highest probability, the claim runs the full cancellation path (D-02)"
    - "An exact probability tie goes to the earlier label in analysis.coverage positive-label config order, and any positive label beats the abstention labels (other_label, then False). A selected label with no probability entry counts as 0.0 (D-04, D-05, D-06)"
    - "routed_coverage is computed once in _classify_coverage_node and stored in graph state together with coverage_probabilities. Routing, document-stage selection, acceptable/classified document codes, the cancellation-only medical/identity/signature gates, the coverage-abstention decision and the coverage HITL term all read state routed_coverage. The raw coverage label list is read from state only to persist coverage_labels / coverage_label_codes"
    - "A losing False in the coverage selection does not raise human_in_the_loop. A winning False does (P-01)"
    - "When coverage routes to missed departure or personal effects, a document code that collides with the cancellation medical codes (stage-local overlap, e.g. missed-doc 1) never triggers the authenticity / incomplete / identity / signature medical checks"
    - "analysis_result.json keeps coverage_labels and coverage_label_codes unchanged (raw classifier order) and adds routed_coverage_label, routed_coverage_label_code and coverage_probabilities (P-02)"
    - "SUMMARY lists every existing test/fixture whose decision changed (expected: none). It includes a before/after table for the multi-label matrix captured with the scratch harness and a claim 9 dataset before/after entry (D-03)"
    - "Gates: ruff check --no-fix and ruff format --check are clean on both touched .py files. pytest shows only the known test_analysis_coverage_other_label_is_false failure. mypy error count on the two touched .py files is <= the recaptured baseline (17 at planning time: 6 src + 11 test)"
    - "The git index, HEAD and stash list are untouched: no commit, add, stash, reset, restore, checkout or pre-commit run"
  artifacts:
    - path: src/compliance/workflows/claim_pipeline.py
      provides: "RoutedCoverage NamedTuple, CoverageBranch Literal, _routed_coverage helper, all branch consumers gated on state routed_coverage"
      contains: "class RoutedCoverage(NamedTuple)"
    - path: tests/test_workflows/test_claim_pipeline.py
      provides: "Parametrized coverage-route matrix (order, abstention conflict, ties, missing probability, stage-local overlap)"
      contains: "routed_coverage_label_code"
    - path: .gsd/review_backlog.md
      provides: "SR-004 checked off with recorded steering decisions"
      contains: "### [x] SR-004"
  key_links:
    - from: "ClaimPipeline._classify_coverage_node"
      to: "ClaimAnalysisState.routed_coverage"
      via: "self._routed_coverage(result) computed once from ClassificationResult labels + probabilities"
      pattern: "routed_coverage"
    - from: "_route_after_coverage / _document_stage_for_coverage / _acceptable_document_codes / _classified_document_codes / _is_cancellation_coverage / _decision_from_state / _classifier_returned_false"
      to: "state[\"routed_coverage\"]"
      via: "direct TypedDict read (no fallback: coverage node always runs before every consumer)"
      pattern: "state\\[\"routed_coverage\"\\]"
    - from: "ClaimPipeline._analysis_result_payload"
      to: "analysis_result.json"
      via: "routed_coverage_label, routed_coverage_label_code, coverage_probabilities keys beside raw coverage_labels / coverage_label_codes"
      pattern: "routed_coverage_label_code"
---

<objective>
SR-004: make one authoritative coverage route. Normalize the coverage classifier output once into a typed `routed_coverage` (branch + winning label code) stored in LangGraph state. Every branch-specific rule reads it instead of mixing first-element routing with set-membership priority (PE > Missed > Cancellation).

Decisions (IDs for traceability; there is no CONTEXT.md for this quick task):
- D-01 (user, locked): with multiple positive labels, the label with the HIGHEST PROBABILITY wins and its path is followed.
- D-02 (user, locked): positive plus False/None also resolves by highest probability. If the abstention label wins, the claim takes the abstention/persist path. Otherwise it follows the winning positive label.
- D-03 (user, locked): re-baselining is ALLOWED and decisions may change anywhere. Record before/after behaviour for the changed cases in the SUMMARY.
- D-04 (orchestrator default, FLAGGED): the winner is chosen only among labels the classifier SELECTED (`ClassificationResult.labels`), using `ClassificationResult.probabilities`.
- D-05 (orchestrator default, FLAGGED): exact ties break deterministically by config order. First come `analysis.coverage.positive_labels()` in order, then `other_label`, then `"False"`. As a result, a positive label beats abstention on an exact tie.
- D-06 (orchestrator default, FLAGGED): a selected label with no probability entry counts as 0.0.
- P-01 (planner discretion, FLAGGED): the coverage stage adds to the "classifier returned False" HITL term only when the ROUTED label is `"False"`. A losing `"False"` has no side effect. The reason and document stages keep raw membership, which is out of SR-004 scope. HITL for a winning abstention is unchanged, because the decision is UNCERTAIN and that already forces HITL.
- P-02 (planner discretion, FLAGGED): `coverage_probabilities` is persisted in analysis_result.json next to the routed label. Today the route cannot be audited or re-derived from persisted artifacts; claim 9 shows this.
- P-03 (planner discretion): if the winning label is not a configured positive label, the branch is `"abstention"`, which gives persist plus UNCERTAIN `coverage_false_label`. This keeps T-04-03 ("unknown coverage treated as other_label"). The CaseClassifier allow-list means this cannot happen from the live classifier.

Out of scope (do not touch): SR-010 per-coverage medical gating semantics (only the INPUT of `_is_cancellation_coverage` changes), SR-011 config-order validation (branch mapping keeps the existing positive-label index convention), the reason/document-stage False HITL terms, and the known failing `tests/test_config/test_settings.py::test_analysis_coverage_other_label_is_false`.

Task classification (project skill classify-tasks): all 3 tasks come from SR-004, which was classified complex (H1/H5/M3). User steering is recorded as D-01..D-03. D-04..D-06 and P-01..P-03 are flagged in the return for user confirmation and do not block execution.

Purpose: stop silent wrong-branch approvals. Examples: claim 9 (`["1","3"]`) was routed to cancellation, but its document names and acceptable codes came from the missed-departure stage. `["False","1"]` skipped every stage and was then denied as if it were a positive claim.
Output: typed routed coverage in `claim_pipeline.py`, a parametrized route-matrix test, a SUMMARY with the before/after table, and the SR-004 backlog entry checked off.
</objective>

<execution_context>
@~/.claude/gsd-core/workflows/execute-plan.md
@~/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@./CLAUDE.md
@.gsd/review_backlog.md (section "SR-004", ~L93-117, and "## Steering status" table, ~L351-363)
@src/compliance/workflows/claim_pipeline.py
@src/compliance/llm/classifier.py (ClassificationResult: labels list, probabilities dict normalized/clamped over labels + other_label; labels never empty because it falls back to other_label)
@src/compliance/config/settings.py (ClassificationConfig.positive_labels / abstention_labels / resolve_label_names, ~L61-100; read-only, do not edit)
@tests/test_workflows/test_claim_pipeline.py (helpers L24-230: _config, _seed_preprocessed_claim, _chat_response; MagicMock side_effect sequence pattern, e.g. _pe_chat_fn L765, _missed_chat_fn L780)
@tests/conftest.py (cancellation_chat_factory L299, build_minimal_app_config; read-only)

<interfaces>
Live code at planning time (line numbers are hints only):
- ClaimAnalysisState (TypedDict, total=False) ~L52: has coverage_labels, reason_labels, document_labels, human_in_the_loop, checker booleans.
- _route_after_coverage ~L255: routes on the first element of coverage_labels only.
- _classify_coverage_node ~L341: returns only coverage_labels and discards result.probabilities.
- _is_missing_documentation / _violated_checkers / _decision_from_state ~L906-1014.
- _classifier_returned_false ~L525 (staticmethod): "False" in any of the coverage/reason/document label lists.
- _signature_required_applies / _identity_required_applies / _medical_document_check_applies ~L596-654: all gate on _is_cancellation_coverage plus _classified_document_codes.
- _is_cancellation_coverage ~L656: set membership of positive label index 0.
- _analysis_result_payload ~L812: coverage_codes from raw state list, document stage from _document_stage_for_coverage(coverage_codes).
- _document_stage_for_coverage ~L847 / _acceptable_document_codes ~L861 / _classified_document_codes ~L895: set membership with PE > Missed > Cancellation priority.
- _decision_from_state ~L983: coverage abstention only when set(coverage) is a subset of abstention labels.
- Test config (_analysis_config): coverage.labels ["1","2","3","False"], other_label "False", names 1=Trip cancellation or rescheduling, 2=Personal Effects, 3=Missed Departure or Missed Connection. cancellation_document 1=medical certificate. personal_effects_document 1=Proof of theft, loss, or damage. missed_departure_document 1=Incident report or documentation explaining the cause of delay. Classifier prompts are "classify coverage", "classify reason", "classify cancel doc", "classify pe doc", "classify missed doc". required_documents: cancellation_by_reason 2=["1","4"], personal_effects ["1"], missed_departure ["1","2"], signature/identity codes ["1","4"]. departure_uncertain_enabled is false by default.
- LLM call counts on the seeded claim (containment and identity short-circuit deterministically): cancellation path with reason 2 and doc 1 = 7 calls (coverage, reason, cancel doc, contradicts, healthy, not_authentic, incomplete). PE path with doc 1 = 4 calls (coverage, pe doc, contradicts, healthy). Missed path with doc 1 = 4 calls. Abstention = 1 call.
</interfaces>

Baselines recaptured at planning time (2026-09-29, working tree as-is):
- `uv run pytest -q -m "not integration"`: 232 passed, 1 failed (known), 3 deselected, ~1 s.
- `uv run pytest -q` (full, includes Docling integration): 235 passed, 1 failed (known), ~6 min. Run it in the background with a >= 600 s timeout.
- `uv run mypy src/compliance/workflows/claim_pipeline.py tests/test_workflows/test_claim_pipeline.py`: 17 errors (6 in claim_pipeline.py at ~L516, L531, L568, L886, L888, L890; 11 in the test file).
- ruff check --no-fix and ruff format --check: clean on both .py files.

HARD CONSTRAINTS for the executor (the working tree holds ~40 staged + unstaged user files):
- Do NOT run git add / commit / stash / reset / restore / checkout, and do NOT run pre-commit. Edit files in place only. Do not commit this plan or the SUMMARY.
- Always pass `--no-fix` to `ruff check` (pyproject sets fix = true). Only run `uv run ruff format` in write mode on the two touched .py files, and only if `--check` fails.
- Scratch scripts and before/after captures go in the executor's session scratchpad directory, never inside the repo. Never write into data/results or data/preprocessed.
</context>

<tasks>

<task type="tracer" tdd="true">
  <name>Task 1: Tracer, from coverage classification to typed routed_coverage in state, then route, then persisted routed label</name>
  <files>src/compliance/workflows/claim_pipeline.py, tests/test_workflows/test_claim_pipeline.py</files>
  <behavior>
    - Case tracer_23: coverage labels ["2","3"], probabilities {"2":0.4,"3":0.8}. routed_coverage_label_code == "3", routed_coverage_label == "Missed Departure or Missed Connection", coverage_label_codes == ["2","3"] (raw order kept), coverage_probabilities["3"] == 0.8, chat_fn.call_count == 4, decision == "APPROVE".
    - Case tracer_32: coverage labels ["3","2"], same probabilities, identical expectations. This checks order invariance (D-01).
  </behavior>
  <action>
Step 0, BEFORE any edit: capture baselines and the BEFORE behaviour.
(a) Run `uv run mypy src/compliance/workflows/claim_pipeline.py tests/test_workflows/test_claim_pipeline.py 2>&1 | tail -1` and record the count (expected 17). This number is the mypy ceiling for Task 3.
(b) Write a scratch harness script in the session scratchpad (NOT in the repo). It puts `tests` and `tests/test_workflows` on sys.path and imports `_config`, `_seed_preprocessed_claim` and `_chat_response` from the test module. For each matrix case listed in Task 2 plus the two tracer cases, it seeds a claim under a fresh temp directory and runs `ClaimPipeline(config, chat_fn=fake).analyze_claim(claim_dir)`. The fake is a callable chat seam that dispatches on the system prompt `kwargs["messages"][0]["content"]`:
- prefix "classify coverage": return the case's coverage labels and probabilities.
- prefix "classify reason": return labels ["2"], probabilities {"2":0.85,"False":0.15}.
- prefix "classify cancel doc", "classify pe doc" or "classify missed doc": return labels ["1"], probabilities {"1":0.8,"False":0.2}.
- anything else: return {"result": false}.
The fake also records the ordered list of prompt prefixes it saw. For each case, the harness prints one JSON line with case id, the called prompt sequence, decision, decision_explanation, human_in_the_loop, document_labels and reason_label_codes from the written analysis_result.json. Save the output as before.jsonl in the scratchpad. Task 3 reruns the same harness for the AFTER column (D-03).

Step 1 (RED): in the test file, add a module-level helper that builds a MagicMock chat_fn for a coverage selection. It returns `_chat_response` of the coverage labels/probabilities, followed by the path tail for the expected winner. Tails:
- "1": reason ["2"] {"2":0.85,"False":0.15}, cancel doc ["1"] {"1":0.8,"False":0.2}, then four {"result": False}.
- "2" and "3": doc ["1"] {"1":0.8,"False":0.2}, then two {"result": False}.
- "False": no tail.
Keep the tails in one module-level dict keyed by winner code (DRY) and reuse the existing TRIP_CANCELLATION / PERSONAL_EFFECTS / MISSED_DEPARTURE / COVERAGE_FALSE constants. Add `test_coverage_route_by_probability`, parametrized with pytest.param ids, with the two tracer cases from <behavior>. Assert exactly the <behavior> fields. Using the side_effect sequence makes an unexpected extra LLM call fail with StopIteration, which is the path check. Do not rewrite the existing _pe_chat_fn / _missed_chat_fn builders. Run the test and confirm it fails (routed_coverage_label_code is absent).

Step 2 (GREEN), claim_pipeline.py:
- Add a module-level `CoverageBranch` Literal of "cancellation", "personal_effects", "missed_departure" and "abstention".
- Add a `CoverageNextNode` Literal of the four next-node names used by `_route_after_coverage`, and reuse it as that method's return annotation.
- Add a module-level `RoutedCoverage(NamedTuple)` with fields `branch: CoverageBranch` and `label: str` (the winning coverage code), plus a docstring with :param: lines.
- Add a module-level constant mapping each CoverageBranch to its CoverageNextNode: cancellation to classify_reason, personal_effects to classify_pe_document, missed_departure to classify_missed_document, abstention to persist.
- Extend ClaimAnalysisState with `coverage_probabilities: dict[str, float]` and `routed_coverage: RoutedCoverage`, and document both in the class docstring.
- `_classify_coverage_node` returns coverage_labels (raw, unchanged), coverage_probabilities (a plain dict copy of result.probabilities) and routed_coverage = `self._routed_coverage(result)`. Add routed_label and routed_branch to its log_branch_decision call. Log codes only, never description text (T-04-02).

New private helpers, each named after what it produces, each with a docstring:
- `_routed_coverage(result: ClassificationResult) -> RoutedCoverage`: orchestrates the two helpers below. Its docstring is the single documented policy: D-01, D-02, D-04, D-05, D-06, P-03.
- `_winning_coverage_label(result) -> str`: picks among result.labels (D-04) the label with the highest `result.probabilities.get(label, 0.0)` (D-06). Ties go to the lowest rank from `_coverage_label_rank()` (D-05). There is no empty-list check, because CaseClassifier always returns at least other_label (CLAUDE.md: trust internal guarantees).
- `_coverage_label_rank() -> dict[str, int]`: rank over `positive_labels()` in config order, then `other_label`, then "False", de-duplicated. A label missing from the map ranks after all known labels.
- `_coverage_branch(label: str) -> CoverageBranch`: zips `positive_labels()` with ("cancellation", "personal_effects", "missed_departure") and falls back to "abstention" (P-03).

Rewrite `_route_after_coverage` to read `state["routed_coverage"]` and return the mapped next node. Log with reason = branch and label = routed.label. Delete the first-element indexing of the label list and the index-based positive-label locals, and update its docstring to reference the routed policy.

In `_analysis_result_payload`, right after "coverage_label_codes", add three keys (P-02):
- "routed_coverage_label": the semantic name via coverage.resolve_label_names on the single routed code.
- "routed_coverage_label_code": the routed code.
- "coverage_probabilities": a dict copy of the state probabilities.
Keep "coverage_labels" / "coverage_label_codes" built from the raw state list, since that is the one allowed raw read.

Do not change the other consumers yet (Task 2). Follow CLAUDE.md: `from __future__ import annotations` is already present, full type annotations, :param: docstrings, no restating comments, no defensive fallbacks for state keys the coverage node always writes.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && uv run pytest -q tests/test_workflows/test_claim_pipeline.py -k coverage_route_by_probability && uv run pytest -q tests/test_workflows/test_claim_pipeline.py</automated>
  </verify>
  <done>before.jsonl exists in the scratchpad and the mypy baseline is recorded. Both tracer cases pass. All pre-existing tests in test_claim_pipeline.py still pass. analysis_result.json now carries routed_coverage_label, routed_coverage_label_code and coverage_probabilities next to the unchanged raw coverage fields. Routing reads only state routed_coverage.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Gate every branch-specific rule on routed_coverage and cover the full conflict matrix</name>
  <files>src/compliance/workflows/claim_pipeline.py, tests/test_workflows/test_claim_pipeline.py</files>
  <behavior>
    Extend the `test_coverage_route_by_probability` parametrize table. Each case gives (labels, probabilities, expected winner), and a module-level per-winner expectation dict asserts: routed_coverage_label_code, routed_coverage_label (semantic name), coverage_label_codes == labels, chat_fn.call_count (1: 7, 2: 4, 3: 4, False: 1), decision + decision_explanation, human_in_the_loop, document_labels, reason_label_codes, and whether "checker_document_not_authentic" is present.
    - Winner 1: document_labels ["medical certificate"], reason_label_codes ["2"], APPROVE / checker_consistent, HITL false, not_authentic key present.
    - Winner 2: document_labels ["Proof of theft, loss, or damage"], no reason codes, APPROVE, HITL false, not_authentic key absent.
    - Winner 3: document_labels ["Incident report or documentation explaining the cause of delay"], no reason codes, APPROVE, HITL false, not_authentic key absent.
    - Winner False: no document labels, no reason codes, UNCERTAIN / coverage_false_label, HITL true, not_authentic and checker_containment absent.
    Cases (id: labels, probabilities, winner):
    - multi_positive_12_pe_wins: ["1","2"], {"1":0.4,"2":0.8}, 2
    - multi_positive_21_pe_wins: ["2","1"], same, 2 (D-01 order invariance)
    - multi_positive_12_cancel_wins: ["1","2"], {"1":0.8,"2":0.4}, 1
    - multi_positive_21_cancel_wins: ["2","1"], same, 1
    - false_first_abstention_wins: ["False","1"], {"False":0.7,"1":0.3}, False (D-02)
    - false_last_abstention_wins: ["1","False"], same, False
    - false_first_positive_wins: ["False","1"], {"False":0.3,"1":0.7}, 1 (D-02, P-01: HITL false)
    - false_last_positive_wins: ["1","False"], same, 1
    - tie_positive_config_order: ["3","2"], {"2":0.5,"3":0.5}, 2 (D-05)
    - tie_positive_beats_abstention: ["False","3"], {"False":0.5,"3":0.5}, 3 (D-05)
    - missing_probability_counts_zero: ["1","3"], {"3":0.2}, 3 (D-06)
    - overlap_missed_wins: ["1","3"], {"1":0.6,"3":0.8}, 3 (stage-local overlap: missed-doc code 1 must not trigger medical checks; the call count of 4 enforces it)
    - overlap_cancel_wins: ["3","1"], {"1":0.8,"3":0.6}, 1 (document names come from the cancellation stage, not missed)
    - the two Task 1 tracer cases are kept, now with the full winner-3 expectations.
  </behavior>
  <action>
Step 1 (RED): add the per-winner expectation dict and the cases from <behavior> to the existing parametrize table, and strengthen the test body to assert every expectation field. Run the test and confirm several cases fail before the implementation. Expected failures: the PE-wins cases with 1 also selected, because StopIteration comes from extra medical-check calls; the tracer cases, because document names resolve from the PE stage; and the False-first positive-wins cases.

Step 2 (GREEN), claim_pipeline.py. Make every remaining consumer read `state["routed_coverage"]` and nothing else for coverage:
- `_document_stage_for_coverage(routed: RoutedCoverage) -> ClassificationConfig`: maps by routed.branch. personal_effects gives analysis.personal_effects_document. missed_departure gives analysis.missed_departure_document. cancellation and abstention give analysis.cancellation_document (this keeps today's fallback; abstention has no document labels). Update both call sites (payload, classified codes) to pass `state["routed_coverage"]`.
- `_acceptable_document_codes`: branch personal_effects gives set(required.personal_effects) or the stage positive labels. missed_departure gives set(required.missed_departure) or the stage positives. Otherwise, return a new private helper `_cancellation_acceptable_codes(state, stage_positive) -> set[str]` that holds the existing reason-based logic unchanged (by_reason union over non-abstention reason codes, then the union of all by_reason codes, then stage positives). Build it as a set from the start; this also removes the existing mypy no-redef / list-update / return-type errors in that method.
- `_classified_document_codes`: take the stage from `_document_stage_for_coverage(state["routed_coverage"])`.
- `_is_cancellation_coverage`: return `state["routed_coverage"].branch == "cancellation"`. The three medical gates (signature, identity, medical-document checks) keep calling it unchanged. SR-010 semantics are untouched.
- `_decision_from_state`: replace the subset-of-abstention check with `state["routed_coverage"].branch == "abstention"`, keeping explanation "coverage_false_label" and its place in the precedence. Update precedence item 2 in the docstring to "routed coverage branch is abstention".
- `_classifier_returned_false` (P-01): the coverage term becomes routed label == "False". The reason_labels / document_labels terms keep raw "False" membership. Update its docstring and the ClaimAnalysisState human_in_the_loop docstring to state that the coverage term follows the routed label.
- The only remaining read of the raw coverage list from state is the payload line that persists coverage_labels / coverage_label_codes.

Keep each helper small with :param:/:return: docstrings (CLAUDE.md). Do not add fallbacks for a missing routed_coverage, because the coverage node always runs first. Do not touch settings.py or conftest.py.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && uv run pytest -q tests/test_workflows/test_claim_pipeline.py && test "$(grep -cE 'state(\.get\(|\[)"coverage_labels"' src/compliance/workflows/claim_pipeline.py)" -eq 1 && test "$(grep -v '^[[:space:]]*#' src/compliance/workflows/claim_pipeline.py | grep -cE 'labels\[0\]|positive\[[0-9]\]')" -eq 0 && test "$(grep -c 'state\["routed_coverage"\]' src/compliance/workflows/claim_pipeline.py)" -ge 5</automated>
  </verify>
  <done>All 15 matrix cases and all pre-existing test_claim_pipeline tests pass. Exactly one raw coverage-list read from state remains (payload persistence). There is no first-element or index-based positive routing. Document stage, acceptable/classified codes, cancellation gate, abstention decision and coverage HITL all derive from routed_coverage.</done>
</task>

<task type="auto">
  <name>Task 3: Re-baseline, run the gates, add the claim 9 dataset before/after, and check off SR-004 in the backlog</name>
  <files>tests/test_workflows/test_claim_pipeline.py, .gsd/review_backlog.md</files>
  <action>
1. Fast lane: run `uv run pytest -q -m "not integration"`. Expect the baseline 232 passed plus the new parametrized cases, with only `tests/test_config/test_settings.py::test_analysis_coverage_other_label_is_false` failing. Then run the full `uv run pytest -q` in the background with a timeout of at least 600 s (about 6 min) and compare it with the baseline of 235 passed and 1 known failure, plus the new cases.
All existing coverage fixtures are single-label, so no existing test is expected to change decision. If any existing test in any file (test_claim_pipeline, test_orchestration, test_api/*, test_evaluation/*) fails because of an intended D-01..D-06 / P-01..P-03 behaviour change, update its expectation in place and record it for the SUMMARY: test id, old expected value, new value, and the decision that caused it (D-03). Any other failure is a regression: fix the code, not the test.

2. Rerun the Task 1 scratch harness against the new code and save the output as after.jsonl in the scratchpad. Diff it against before.jsonl.

3. Claim 9 dataset case, read-only on user data:
- Copy `data/results/claim 9/analysis_result.json` into the scratchpad as the BEFORE artifact. Today it has coverage codes ["1","3"] and APPROVE / checker_consistent, but its document names were resolved from the missed stage while the claim was routed to cancellation. Ground truth in `data/preprocessed/claim 9/answer.json` is APPROVE.
- Write the static AFTER for both possible winners. If 1 wins: cancellation path, document names from cancellation_document, acceptable codes from cancellation_by_reason. If 3 wins: missed-departure document classifier and missed required docs.
- Optional live re-run: only if `curl -s -m 2 http://localhost:11434/api/tags` succeeds. Copy the `data/preprocessed/claim 9` folder into the scratchpad, load config with `load_config()`, point preprocessing.results_dir at a scratchpad path, and call `ClaimPipeline(config).analyze_claim(<scratch copy>)`. Record the routed label, the coverage_probabilities and the decision. Never write into data/results or data/preprocessed.

4. Gates on the two touched .py files:
- `uv run ruff check --no-fix src/compliance/workflows/claim_pipeline.py tests/test_workflows/test_claim_pipeline.py` must be clean.
- `uv run ruff format --check` on the same files must be clean. If it is not, run `uv run ruff format` on exactly those two files.
- The mypy count on the same two files must be <= the Task 1 recorded baseline (17 at planning time). Task 2 should lower it by about 3.
Fix any new C901 / typing issue by extracting a helper, never with a suppression comment.

5. Only after every gate passes, edit `.gsd/review_backlog.md` in place:
- Change the heading `### [ ] SR-004: Single authoritative coverage route ⚠️` to `### [x] SR-004: ...` (keep the rest of the heading).
- Under SR-004, replace the three "Steering needed" questions with "Steering (resolved 2026-09-29)" lines summarizing D-01, D-02, D-03 and the flagged defaults D-04..D-06 / P-01..P-03.
- In the "## Steering status" table, change the SR-004 row status from "Awaiting steering" to: "Steered 2026-09-29: highest-probability selected label wins (incl. vs False/None); ties by config order; re-baseline allowed — done (quick 260929-ftg)".
No other backlog rows change.

6. The SUMMARY (per output section) must contain:
- the policy (D-01..D-06, P-01..P-03);
- the files changed;
- the test/fixture re-baseline list (explicitly "none" if none);
- a before/after table per harness case (called path, decision/explanation, HITL, document_labels) built from before.jsonl and after.jsonl;
- the claim 9 entry;
- the gate results (pytest counts for fast and full, ruff, mypy before → after);
- the git-untouched statement.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && uv run pytest -q -m "not integration" 2>&1 | tail -3 && uv run ruff check --no-fix src/compliance/workflows/claim_pipeline.py tests/test_workflows/test_claim_pipeline.py && uv run ruff format --check src/compliance/workflows/claim_pipeline.py tests/test_workflows/test_claim_pipeline.py && uv run mypy src/compliance/workflows/claim_pipeline.py tests/test_workflows/test_claim_pipeline.py 2>&1 | tail -1 && grep -c '### \[x\] SR-004' .gsd/review_backlog.md && ! grep -q '| SR-004 | Awaiting steering |' .gsd/review_backlog.md</automated>
  </verify>
  <done>The fast and full pytest runs show only the known failure plus all new cases passing. Any re-baselined existing tests are updated and listed. ruff and format are clean. The mypy count is <= baseline. The claim 9 before/after is recorded. SR-004 is checked with steering recorded. The SUMMARY is written. git index, HEAD and stash are untouched.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| LLM coverage classifier → ClaimPipeline routing | Untrusted model output (label list + probabilities) decides which policy branch a claim is judged under |
| ClaimPipeline → analysis_result.json / predicted_answer.json | The persisted decision is consumed by the evaluator, the API and operators; it must be auditable |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-ftg-01 | Tampering / Elevation | _routed_coverage + all branch consumers | high | mitigate | A single routed winner is computed once from selected labels and probabilities. Every gate reads state routed_coverage, so conflicting labels cannot mix stages (first-element route vs set-membership document stage). The overlap_* and multi_positive_* test cases enforce this through exact LLM call counts. |
| T-ftg-02 | Repudiation | _analysis_result_payload | medium | mitigate | Persist raw coverage_label_codes plus coverage_probabilities plus routed_coverage_label(_code), so every routing decision can be re-derived from the artifact (P-02). |
| T-ftg-03 | Information disclosure | log_branch_decision in coverage node / route | low | mitigate | Log only label codes and branch names. Never log the description or OCR text (T-04-02). |
| T-ftg-04 | Tampering | ClassificationResult.probabilities | low | accept | Values are already clamped to [0,1] and defaulted to 0.0 over the vocabulary by CaseClassifier. Exact ties are deterministic by config order (D-05), and missing entries count as 0.0 (D-06). |
| T-ftg-05 | Tampering | Abstention vs positive conflict | medium | mitigate | A winning abstention forces UNCERTAIN coverage_false_label plus HITL (no silent DENY/APPROVE). A losing abstention cannot skip stages (the false_* test cases). |
</threat_model>

<verification>
- `uv run pytest -q tests/test_workflows/test_claim_pipeline.py` shows all tests green, including the 15-case `test_coverage_route_by_probability` matrix.
- `uv run pytest -q -m "not integration"` and the full `uv run pytest -q` show only the known `test_analysis_coverage_other_label_is_false` failure.
- The grep gates show exactly one raw coverage-list read from state, no index-based routing, and at least 5 `state["routed_coverage"]` reads.
- ruff check --no-fix and ruff format --check are clean. The mypy count is <= the recorded baseline (17).
- `git status --short` staged/unstaged file set is unchanged apart from the three files_modified (plus the SUMMARY). `git stash list` and `git log -1` are unchanged.
</verification>

<success_criteria>
- `["1","2"]` and `["2","1"]` have one documented, deterministic, probability-decided outcome (backlog Done-when #1).
- `["False","1"]` can no longer skip stages and then behave as a positive claim. It either persists as UNCERTAIN (abstention wins) or runs the full positive path (positive wins) (backlog Done-when #2).
- Tests cover order, conflicts, ties, the missing-probability default and stage-local code overlap (backlog Done-when #3).
- Before/after behaviour for the changed cases is recorded in the SUMMARY (D-03). SR-004 is checked off in .gsd/review_backlog.md.
</success_criteria>

<output>
Create `/Users/theresa/Desktop/projects/compliance/.planning/quick/260929-ftg-sr-004-single-authoritative-coverage-rou/260929-ftg-SUMMARY.md` when done. Do NOT commit it.
</output>
