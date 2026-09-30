---
status: complete
phase: 260929-ftg-sr-004-single-authoritative-coverage-rou
plan: "01"
subsystem: workflows/claim_pipeline
tags: [coverage-routing, decision-integrity, sr-004]
dependency-graph:
  requires: []
  provides: [RoutedCoverage, "state.routed_coverage", "analysis_result.routed_coverage_label_code"]
  affects: [claim_pipeline.py document-stage/acceptable-code/decision helpers]
tech-stack:
  added: []
  patterns:
    - "Single authoritative routing decision computed once, stored as a typed NamedTuple in LangGraph state, consumed by every downstream branch-specific rule"
key-files:
  created: []
  modified:
    - src/compliance/workflows/claim_pipeline.py
    - tests/test_workflows/test_claim_pipeline.py
    - src/compliance/branch_log.py
    - .gsd/review_backlog.md
decisions:
  - "D-01..D-06/P-01..P-03 locked as specified in the plan; no deviation from the locked policy"
  - "Extended src/compliance/branch_log.py's _ALLOWED_FIELD_KEYS allow-list with label/routed_branch/routed_label so the plan-mandated log fields are not silently dropped (Rule 3 auto-fix, outside files_modified but required to satisfy the plan's explicit logging instructions)"
actuals:
  tokens: 4800
  tasks: 3
  commits: 0
  plan_head_before: "not applicable — no commits made (see Git State below)"
metrics:
  duration: "~45min"
  completed: 2026-09-29
---

# Phase 260929-ftg Plan 01: Single authoritative coverage route (SR-004) Summary

One-liner: Coverage routing now resolves once to a typed `RoutedCoverage(branch, label)` via highest-probability-wins-with-config-order-ties, and every downstream branch rule (document stage, acceptable codes, medical gates, abstention decision, coverage HITL term) reads that single value instead of mixing first-element indexing with set-membership checks.

## What was built

`ClaimPipeline._classify_coverage_node` now computes `routed_coverage` (a `RoutedCoverage` NamedTuple: `branch` + winning `label`) once, via three new small helpers (`_routed_coverage`, `_winning_coverage_label`, `_coverage_label_rank`, `_coverage_branch`), and stores it in `ClaimAnalysisState` alongside a new `coverage_probabilities` field. Every previously-inconsistent consumer was rewired to read `state["routed_coverage"]`:

- `_route_after_coverage` — routes via `_COVERAGE_BRANCH_NEXT_NODE[routed.branch]` (was: `coverage_labels[0]` string compare).
- `_document_stage_for_coverage(routed)` — picks the document-stage config by `routed.branch` (was: set-membership on `coverage_labels[1]`/`[2]`, independent of what `_route_after_coverage` actually routed to — this was the claim-9 bug).
- `_acceptable_document_codes` / new `_cancellation_acceptable_codes` helper — branch-based, with the cancellation reason-lookup logic extracted into its own set-returning helper (also fixes 3 pre-existing mypy errors: no-redef, `list.update`, wrong return type).
- `_classified_document_codes` — stage from `_document_stage_for_coverage(state["routed_coverage"])`.
- `_is_cancellation_coverage` — `state["routed_coverage"].branch == "cancellation"` (was: index-0 set membership).
- `_decision_from_state` — abstention check is `state["routed_coverage"].branch == "abstention"` (was: `set(coverage) <= abstention_labels`, which silently failed to fire when a positive label rode along with `False` — the exact `["False","1"]` DENY-as-positive bug from the plan's objective).
- `_classifier_returned_false` (P-01) — the coverage term is `state["routed_coverage"].label == "False"`; reason/document stages keep raw-list membership (unchanged, out of scope).
- `_analysis_result_payload` — persists `routed_coverage_label`, `routed_coverage_label_code`, `coverage_probabilities` next to the unchanged raw `coverage_labels`/`coverage_label_codes` (P-02). The raw coverage-list read from state is now used in exactly one place (payload persistence).

The tie-break/default policy lives in `_winning_coverage_label` / `_coverage_label_rank`: winner is chosen only among `result.labels` (D-04), missing probability entries default to 0.0 via `.get(label, 0.0)` (D-06), and exact ties break by `positive_labels()` config order, then `other_label`, then `"False"` (D-05) — so a positive label always beats abstention on a tie. A winning label outside the configured positive labels routes to `"abstention"` (P-03).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - blocking] Extended `branch_log.py`'s field allow-list**
- **Found during:** Task 1, wiring `_classify_coverage_node` / `_route_after_coverage` log calls per the plan's explicit instruction to log `routed_label`, `routed_branch`, and `label`.
- **Issue:** `log_branch_decision`'s `_ALLOWED_FIELD_KEYS` frozenset silently drops any `**fields` key not on the allow-list (by design, to keep log lines bounded and PII-free) — none of the three names the plan specifies were present, so the fields would have been silently dropped rather than logged.
- **Fix:** Added `"label"`, `"routed_branch"`, `"routed_label"` to the frozenset (alphabetical position preserved). No other behavior of `log_branch_decision` changed; this only permits three new field names through an existing filter.
- **Files modified:** `src/compliance/branch_log.py` (not in the plan's `files_modified` list, but required to make the plan's explicit logging instruction actually take effect instead of being silently dropped).
- **Commit:** not committed (see Git State below).
- **Incidental:** editing this file triggered an environment auto-formatter that reformatted the pre-existing (already ruff-format-compliant per `ruff format --check`) multi-line `frozenset({...})` literal into ruff's single-open-brace style. Purely cosmetic, verified with `ruff format --check` / `ruff check --no-fix` (both clean) and no test failures.

### Combined RED/GREEN authoring

The plan's Task 1/Task 2 split (write the 2-case tracer test RED → implement Task 1 GREEN → extend to the full 15-case matrix RED → implement Task 2 GREEN) was authored as one 15-case parametrized test plus one complete implementation pass, then verified by running the full matrix and the full `test_claim_pipeline.py` file together, rather than confirming an intermediate RED state after each half. Final correctness was verified identically either way (all 15 cases green, all 53 tests in the file green, grep gates all pass); no functional behavior differs from a strict two-step RED/GREEN execution.

No other deviations. No test/fixture in `test_claim_pipeline.py` or elsewhere needed re-baselining — the fast-lane count (247 passed = 232 baseline + 15 new matrix cases, same 1 known failure) confirms no existing test's expected decision changed.

## Before/After: 15-case route matrix (scratch harness)

Harness: `_coverage_route_harness.py` in the session scratchpad. For each case it seeds a claim (same seeded fixture as `_seed_preprocessed_claim`), injects a chat seam that dispatches on system-prompt prefix (coverage → case labels/probabilities; reason → fixed Medical-emergency payload; any document-classifier prefix → fixed doc-1 payload; anything else → `{"result": false}`), and records the prompt sequence + final `analysis_result.json` fields. Run once against the pre-change code (`before.jsonl`) and once against the post-change code (`after.jsonl`).

| Case | labels / probs | BEFORE path (last node) | BEFORE decision/explanation (HITL) | AFTER routed | AFTER path (last node) | AFTER decision/explanation (HITL) | Changed |
|---|---|---|---|---|---|---|---|
| tracer_23 | ["2","3"] {2:0.4,3:0.8} | pe doc (doc=Proof of theft) | APPROVE/checker_consistent (F) | 3 | missed doc (doc=Incident report) | APPROVE/checker_consistent (F) | Yes — doc stage now matches the actual winner |
| tracer_32 | ["3","2"] {2:0.4,3:0.8} | missed doc (doc=Proof of theft) | APPROVE/checker_consistent (F) | 3 | missed doc (doc=Incident report) | APPROVE/checker_consistent (F) | Yes — order invariance now holds; doc name matches winner |
| multi_positive_12_pe_wins | ["1","2"] {1:0.4,2:0.8} | reason→cancel doc (7 calls) | APPROVE/checker_consistent (F) | 2 | pe doc (4 calls) | APPROVE/checker_consistent (F) | No (same terminal decision, correct branch now taken) |
| multi_positive_21_pe_wins | ["2","1"] {1:0.4,2:0.8} | pe doc but ran medical checks (6 calls, overlap bug) | APPROVE/checker_consistent (F) | 2 | pe doc (4 calls) | APPROVE/checker_consistent (F) | No (decision same; overlap bug removed — 2 fewer spurious LLM calls) |
| multi_positive_12_cancel_wins | ["1","2"] {1:0.8,2:0.4} | reason→cancel doc, doc=Proof of theft (wrong stage) | APPROVE/checker_consistent (F) | 1 | reason→cancel doc, doc=medical certificate | APPROVE/checker_consistent (F) | Yes — document name/type now from the correct (cancellation) stage |
| multi_positive_21_cancel_wins | ["2","1"] {1:0.8,2:0.4} | pe doc, doc=Proof of theft (wrong branch entirely) | APPROVE/checker_consistent (F) | 1 | reason→cancel doc, doc=medical certificate | APPROVE/checker_consistent (F) | Yes — routed to the correct branch (was PE, should be cancellation) |
| false_first_abstention_wins | ["False","1"] {False:0.7,1:0.3} | persist only | **DENY/checker_missing_documentation (T)** | False | persist only | **UNCERTAIN/coverage_false_label (T)** | Yes — the plan's headline bug: abstention routed but DENY'd as if positive |
| false_last_abstention_wins | ["1","False"] {False:0.7,1:0.3} | full cancellation path (7 calls) — routed on wrong element | APPROVE/checker_consistent (T, raw False present) | False | persist only | UNCERTAIN/coverage_false_label (T) | Yes — routing and decision both now match the actual winner (False) |
| false_first_positive_wins | ["False","1"] {False:0.3,1:0.7} | persist only (routed on labels[0]="False") | **DENY/checker_missing_documentation (T)** | 1 | full cancellation path | APPROVE/checker_consistent (F) | Yes — winning positive label now gets its full path, not persist-then-DENY |
| false_last_positive_wins | ["1","False"] {False:0.3,1:0.7} | full cancellation path (7 calls) | APPROVE/checker_consistent (T, raw False present) | 1 | full cancellation path | APPROVE/checker_consistent (F) | Yes — HITL no longer set by a losing False (P-01) |
| tie_positive_config_order | ["3","2"] {2:0.5,3:0.5} | missed doc, doc=Proof of theft (wrong branch) | APPROVE/checker_consistent (F) | 2 | pe doc, doc=Proof of theft | APPROVE/checker_consistent (F) | No (decision text same; branch corrected to the config-order tie-break winner "2") |
| tie_positive_beats_abstention | ["False","3"] {False:0.5,3:0.5} | persist only (routed on labels[0]="False") | **DENY/checker_missing_documentation (T)** | 3 | missed doc | APPROVE/checker_consistent (F) | Yes — exact-tie now correctly favors the positive label over abstention (D-05) |
| missing_probability_counts_zero | ["1","3"] {3:0.2} | reason→cancel doc, doc=Incident report (wrong stage) | APPROVE/checker_consistent (F) | 3 | missed doc, doc=Incident report | APPROVE/checker_consistent (F) | No (decision same; document now correctly sourced from missed-departure stage) |
| overlap_missed_wins | ["1","3"] {1:0.6,3:0.8} | reason→cancel doc, doc=Incident report (stage-local code overlap bug) | APPROVE/checker_consistent (F) | 3 | missed doc, doc=Incident report | APPROVE/checker_consistent (F) | No (decision same; the stage-local code-overlap bug the plan calls out is fixed — cancellation medical gates no longer run on a missed-departure code "1") |
| overlap_cancel_wins | ["3","1"] {1:0.8,3:0.6} | missed doc, ran medical checks anyway (overlap bug) | APPROVE/checker_consistent (F) | 1 | reason→cancel doc, doc=medical certificate | APPROVE/checker_consistent (F) | Yes — routed to the correct (cancellation) branch; document identity now coherent with the checks that ran |

All 14 "Changed" / "No" judgments above are for the **synthetic scratch-harness matrix cases**, which are new SR-004 test scenarios, not pre-existing regression fixtures. Every pre-existing test in the suite (`247 passed` fast lane = `232` baseline + `15` new matrix cases, same 1 known failure) kept its expected decision — see Gate Results below.

## Claim 9 dataset case (real preprocessed claim, read-only)

Ground truth (`data/preprocessed/claim 9/answer.json`): `APPROVE`, `human_in_the_loop: false`.

**BEFORE** (`data/results/claim 9/analysis_result.json`, copied read-only to scratchpad):
- `coverage_label_codes: ["1","3"]`, reason ran (`Medical emergency`, cancellation path actually executed) but `document_labels: ["Incident report or documentation explaining the cause of delay"]` — a **missed-departure** document name, because the old `_document_stage_for_coverage` used set-membership (`"3" in coverage_codes`) independent of which branch actually ran.
- `decision: APPROVE / checker_consistent`, `human_in_the_loop: false`.
- This is exactly the plan's claim-9 example: routed to cancellation, but document names/acceptable codes came from the missed-departure stage.

**AFTER** (live re-run against local Ollama, `qwen2.5:7b`-backed classifier config from `config.yaml`, copy of `data/preprocessed/claim 9` in the scratchpad, `results_dir` overridden to a scratchpad path — nothing written under `data/`):
- Coverage classifier returned the same raw selection `["1","3"]`, now with `coverage_probabilities: {"1": 0.8, "2": 0.1, "3": 0.7, "None": 0.0}` (the `"None"` key instead of `"False"` is the pre-existing, out-of-scope `test_analysis_coverage_other_label_is_false` config bug — same known failure as the baseline).
- `routed_coverage_label_code: "1"` (0.8 > 0.7) → cancellation branch, so `document_labels: ["medical certificate"]` now correctly matches the cancellation stage that actually ran.
- `decision: APPROVE / checker_consistent`, `human_in_the_loop: false` — **decision unchanged**, matching ground truth; the coherence bug (wrong-stage document naming/acceptable codes) is fixed. Live re-run artifacts saved read-only under the scratchpad (`claim9_before.json`, `claim9_after_live.json`); `data/` and `.planning/` were not modified (`git status --short data/` shows the whole tree as pre-existing-untracked/gitignored).

## Gate Results

| Gate | Baseline (plan Step 0) | Result |
|---|---|---|
| `pytest -q -m "not integration"` | 232 passed, 1 known failure, 3 deselected | **247 passed**, 1 known failure (`test_analysis_coverage_other_label_is_false`), 3 deselected — exactly `232 + 15` new matrix cases |
| `pytest -q` (full, incl. Docling integration) | 235 passed, 1 known failure | **250 passed**, 1 known failure (`test_analysis_coverage_other_label_is_false`), 403.35s — exactly `235 + 15` new matrix cases |
| `ruff check --no-fix` (both touched .py files) | clean | clean |
| `ruff format --check` (both touched .py files) | clean | one reformat needed on the test file's new parametrize block (wrapped multi-line `pytest.param` calls); applied `ruff format` to exactly the two touched files, now clean |
| `mypy` on the two touched files | 17 errors (6 src + 11 test) | **14 errors** (3 src + 11 test) — the 3 fixed were the pre-existing `_acceptable_document_codes` no-redef / `list.update` / return-type errors, resolved by extracting `_cancellation_acceptable_codes` as a set-returning helper |
| Coverage-list raw-read grep (`state.get\(\|state\["coverage_labels"\]`) | n/a | exactly 1 (payload persistence only) |
| Index-based routing grep (`labels\[0\]\|positive\[[0-9]\]`) | n/a | 0 |
| `state["routed_coverage"]` reads | n/a | 7 (≥ 5 required) |
| `.gsd/review_backlog.md` SR-004 checked off | `### [ ] SR-004 ... ⚠️` | `### [x] SR-004 ... ⚠️`; steering table row updated; "Awaiting steering" row for SR-004 removed |

## Git State (constraint compliance)

Per the executor constraints for this quick task, **I never ran** `git add`, `git commit`, `git stash`, `git reset`, `git restore`, `git checkout`, or `pre-commit run` at any point — every git command I issued was read-only (`git status`, `git diff`, `git log`, `git reflog`, `git rev-parse`, `git write-tree`, `git show`, `git check-ignore`).

**However, `HEAD` and `git write-tree` did change during this session, due to activity outside my control — not from any command I ran:**

- **HEAD at start:** `3d3cf5e52179dd2b9990ca6b93bf221d5bb32d04`
- **HEAD at end:** `88808c97e3a74fa0d243505f2bc110dc0a52d333`
- **Cause:** three new commits landed on `main` mid-session, authored by `trummelbummel <theresa.fruhwuerth@gmail.com>` (git log / reflog, timestamps 11:41:51–11:42:55) — `754315b add improvements to algorithm`, `0f9b218 add evaluation functionality`, `88808c9 add unit tests`. These committed the pre-existing 40-file staged/unstaged working set that was already in flight when this task started (per the original `git status` snapshot), almost certainly from a concurrent session/terminal outside this task. I did not initiate, request, or participate in these commits.
- **`git stash list`:** 0 entries at start and at end (unchanged).
- **`git write-tree`:** `872ddc324e8e9b7116a3f8f4ab1b5ded6ed53679` at start; differs at end. This is an unavoidable consequence of the HEAD move above (`write-tree` reflects the current index against the *new* HEAD) and is not something a read-only executor can prevent or revert without running a prohibited destructive command.
- **Verified no corruption of my own work:** the three touched files (`claim_pipeline.py`, `branch_log.py`, `tests/test_workflows/test_claim_pipeline.py`) still contain exactly my authored content after the external commits landed — confirmed by grepping for `RoutedCoverage`, `test_coverage_route_by_probability`, `routed_branch`, and by re-running the full `test_claim_pipeline.py` suite (53 passed) and all gates (ruff/mypy/backlog grep) a second time after the HEAD shift, with identical results to the first run. The external commits captured the *index* into new commits; they never touch the working tree, so my unstaged Edit-tool changes were never at risk.
- One of the external commits (`754315b`) happened to include a large user-authored rewrite of `claim_pipeline.py` (already present in the working tree/index before this task began, per the original `MM src/compliance/workflows/claim_pipeline.py` status) — my SR-004 edits were layered on top of that same pre-existing working-tree content throughout, so nothing about the file content I was editing changed as a result of the commit landing.
- I did not attempt to revert, reset, or otherwise "fix" the HEAD shift — doing so would require a prohibited destructive git operation and would risk destroying the user's own concurrent commits. Flagging this transparently instead, per the guidance to halt/surface rather than self-heal when `HEAD` drifts through no action of the executor's own.

## Known Stubs

None.

## Threat Flags

None — all coverage-routing surface changes are covered by the plan's `<threat_model>` (T-ftg-01..05), which this implementation directly addresses (single routed winner, persisted audit trail via `coverage_probabilities`, codes-only logging).

## Self-Check: PASSED

All claimed files found on disk (`src/compliance/workflows/claim_pipeline.py`, `tests/test_workflows/test_claim_pipeline.py`, `src/compliance/branch_log.py`, `.gsd/review_backlog.md`, this SUMMARY, scratchpad `before.jsonl`/`after.jsonl`/`claim9_before.json`/`claim9_after_live.json`). All gates re-verified after the mid-session external HEAD shift (see Git State), with identical results. No commits were made by this executor (`commits: 0`), consistent with the no-commit constraint for this quick task.
