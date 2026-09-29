---
phase: 260929-lni-sr-006-ground-truth-first-evaluation-ali
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/evaluation/evaluator.py
  - src/evaluation/__main__.py
  - src/evaluation/visualization.py
  - src/evaluation/analysis_stats.py
  - src/compliance/config/settings.py
  - config.yaml
  - tests/test_evaluation/test_evaluator.py
  - tests/test_evaluation/test_cli.py
  - tests/test_config/test_settings.py
  - README.md
  - LOGIC.md
  - .gsd/review_backlog.md
autonomous: true
requirements: [SR-006]

estimate:
  tokens: 120000
  raw_tokens: 120000
  tasks: 3
  confidence: low

must_haves:
  truths:
    - "The evaluated population is discovered from ground truth, not from results: every claim folder under data_dir whose answer.json is readable and whose decision is in evaluation.labels enters the denominator, including claims with no results folder at all and claims whose results folder holds no prediction (D-01). Discovery no longer starts at results_dir"
    - "A missing prediction is an incorrect sample, not an absent one: it lands in the population, lowers accuracy and macro F1, and is reported alongside a coverage_rate (scored / ground-truth population) so the gap between what was scored and what exists is visible in the metrics artifact (D-01)"
    - "Accuracy, macro F1 and the confusion matrix of a named metric are all derived from one matrix over one population: rows are the configured labels, columns are the labels plus a configured unscored column, every ground-truth-backed claim occupies exactly one cell, matrix total equals the population size, and accuracy equals trace / total by construction"
    - "Two named metric sets are reported side by side over that same population: raw compares the predicted decision to the ground-truth decision exactly, policy additionally credits a prediction that equals a non-nan acceptable_decision and remaps it onto the true label for the matrix (D-02). Neither number can be read without its name"
    - "Non-scored claims are counted and attributable, never silently dropped: the result carries per-claim outcomes with a status (scored, missing_prediction, invalid_prediction, invalid_ground_truth, unmatched_prediction) and a reason, and the population block reports each count"
    - "SR-005 mixed-generation refusal is preserved end to end: evaluate_claim still raises MixedGenerationError for a prediction whose run_id disagrees with the published manifest, and the batch records that claim as an invalid prediction counted incorrect rather than scoring stale JSON. Manifest-less legacy trees still score"
    - "analysis_stats keeps its results_dir discovery and says why in its docstring: it aggregates analysis artifacts, which is a deliberately different population from the scored one, so the two n values in the CLI log are not comparable"
    - "Gates: uv run python -m pytest -q --cov (fast lane, integration deselected) passes with coverage at or above the 90 floor. ruff check --no-fix and ruff format --check are clean on every touched .py file. uv run mypy src reports 0 errors, and tests/test_evaluation is no worse than its 20-error baseline"
  artifacts:
    - path: src/evaluation/evaluator.py
      provides: "ClaimStatus, ClaimOutcome, MetricSet, EvaluationPopulation, reshaped EvaluationResult; ground-truth-first discovery; per-claim outcome classification; matrix-derived raw and policy metric sets; coverage_rate"
      contains: "class ClaimStatus"
    - path: src/evaluation/__main__.py
      provides: "metrics payload with population, named raw / policy blocks and per-claim outcomes; confusion-matrix artifact carrying both matrices and the column label axis"
      contains: "population"
    - path: src/evaluation/visualization.py
      provides: "heatmap over labels x (labels + unscored column) with a two-line title carrying both accuracies, coverage and HITL counts"
      contains: "unscored_label"
    - path: src/compliance/config/settings.py
      provides: "EvaluationConfig.unscored_label plus load-time validation that labels are unique and the unscored column name does not collide with them"
      contains: "unscored_label"
    - path: config.yaml
      provides: "evaluation.unscored_label beside evaluation.labels"
      contains: "unscored_label"
    - path: tests/test_evaluation/test_evaluator.py
      provides: "ground-truth-only claim in the population, missing/invalid prediction accounting, invalid ground truth exclusion, unmatched predictions, matrix-total invariant, raw vs policy divergence, mixed-generation accounting"
      contains: "coverage_rate"
    - path: tests/test_evaluation/test_cli.py
      provides: "metrics artifact shows the ground-truth-first population, coverage_rate and both named metric blocks; PNGs still render"
      contains: "coverage_rate"
    - path: .gsd/review_backlog.md
      provides: "SR-006 checked off with recorded steering decisions (gitignored, never staged)"
      contains: "### [x] SR-006"
  key_links:
    - from: "Evaluator.evaluate"
      to: "config.preprocessing.data_dir claim folders"
      via: "the denominator is discovered from the ground-truth tree, so a claim with no results folder is still evaluated"
      pattern: "data_dir"
    - from: "Evaluator._classified_outcome"
      to: "ClaimStatus.MISSING_PREDICTION"
      via: "an absent prediction becomes a counted incorrect sample instead of a skipped one (D-01)"
      pattern: "MISSING_PREDICTION"
    - from: "Evaluator._metric_set"
      to: "EvaluationResult.raw / EvaluationResult.policy"
      via: "both named metric sets are built by the same matrix-derived helper over the same outcome list (D-02)"
      pattern: "_metric_set\\("
    - from: "MetricSet.accuracy / MetricSet.f1_macro"
      to: "MetricSet.confusion_matrix"
      via: "accuracy is the matrix trace over its total and F1 is computed from the same cells, so the three cannot describe different populations"
      pattern: "confusion_matrix"
    - from: "Evaluator._classified_outcome"
      to: "compliance.workflows.artifact_publication.MixedGenerationError"
      via: "an SR-005 generation mismatch is classified as an invalid prediction and counted incorrect instead of scored"
      pattern: "MixedGenerationError"
    - from: "evaluation.__main__._write_artifacts"
      to: "EvaluationResult.population"
      via: "the metrics artifact reports scored / missing / invalid counts and coverage_rate beside the named metrics"
      pattern: "coverage_rate"
---

<objective>
SR-006 makes evaluation ground-truth-first and stops one number from hiding three different populations. Today `Evaluator._discover_claim_ids` lists claim folders under **results_dir**, so a claim that has ground truth but never produced a results folder is invisible to the metrics — it is neither scored nor counted. Inside the discovered set the accounting then splits: `accuracy` is `mean(all_matches)` over samples that have readable ground truth (a failed pair counts as wrong), while the confusion matrix and macro F1 are built only from fully scored pairs. Three numbers in the same artifact therefore describe three different denominators, and the headline accuracy silently credits `acceptable_decision` soft matches without naming that it did. That is the backlog risk "Inflated accuracy / F1".

This plan inverts discovery and makes the population explicit. The denominator is every claim folder under `data_dir` with a readable, in-vocabulary `answer.json`. Each such claim resolves to exactly one typed outcome — scored, missing prediction, invalid prediction, invalid ground truth — and each outcome occupies exactly one cell of a confusion matrix whose columns are the configured labels **plus one unscored column**. Accuracy is that matrix's trace over its total and macro F1 is computed from the same cells, so accuracy, F1 and the matrix cannot disagree about who was measured. Two metric sets are reported by name over that one population: `raw` (exact decision equality) and `policy` (acceptable-decision credit, with the A5 remap onto the true label). `coverage_rate` reports how much of the population was actually scorable.

Locked decisions (from CONTEXT.md and `.gsd/steering-decisions-2026-09-29.md`):
- D-01: A missing prediction with ground truth present counts as **incorrect**; `coverage_rate` is also reported.
- D-02: The acceptable-decision remapping stays, as a **second named metric** — raw vs policy.

Planner discretion (flagged; report in SUMMARY):
- P-01: The denominator is claim folders under `data_dir` whose `answer.json` parses **and** whose decision is in `evaluation.labels`. A claim whose ground truth is unreadable or out of vocabulary cannot be placed on a matrix row at all, so it is excluded from the population and reported separately as an invalid-ground-truth count rather than being scored against a guess.
- P-02: One confusion matrix per named metric: rows are the labels, columns are the labels plus one unscored column. Accuracy and macro F1 are derived **from that matrix** (trace/total; per-label tp/fp/fn read off the cells). This is the structural answer to "accuracy, F1 and matrix share a documented population" — they are the same object, not three parallel computations. A missing prediction becomes a false negative for its true label and a false positive for nothing, which is exactly what "missing counts as incorrect" means for F1.
- P-03: The unscored column name is config-rooted: `evaluation.unscored_label`, default `NO_PREDICTION`, validated at load to be unique against `evaluation.labels` (CLAUDE.md: vocabularies live in `config.yaml`, never hardcoded in source; SR-011 precedent for fail-hard config validation).
- P-04: The named metric sets are `raw` and `policy`; the flat legacy `accuracy` / `f1_macro` / `confusion_matrix` / `n_evaluated` fields are **removed, not aliased**. Keeping a flat unnamed accuracy is the defect — a reader could not tell which population or which matching rule it used. This follows the SR-011 D-01 precedent of breaking named keys immediately, and `data/results/` is gitignored so no committed artifact needs migrating.
- P-05: One PNG, not two: the heatmap renders the `raw` matrix and carries both accuracies, the coverage rate and the HITL counts in a two-line title. The raw matrix is the un-credited view, so the chart cannot flatter the run on its own.
- P-06: A prediction whose claim has no ground-truth folder is reported as an unmatched-prediction count and kept out of every metric. It was silently dropped before; counting it is how an operator notices the two trees have drifted apart.
- P-07: `analysis_stats` keeps its `results_dir` discovery. It aggregates `analysis_result.json` payloads, which is deliberately a different population from the scored one; the docstring will say so, and the CLI log labels the two counts distinctly so they are not read as the same n.
- P-08: `evaluate_claim` stays strict — it still raises on a missing, unparseable, out-of-vocabulary or mixed-generation prediction (Phase 06 decision: unknown pred/gt decisions raise at the `evaluate_claim` boundary). Soft classification is a **batch** policy; the single-claim API remains the place where a caller finds out exactly what is wrong.

Behaviour changes to record in the SUMMARY (intended, not regressions to fix here):
- `evaluation_metrics.json` and `confusion_matrix.json` change shape: named `raw` / `policy` blocks, a `population` block with `coverage_rate`, a per-claim `outcomes` list, and a `column_labels` axis one wider than `labels`.
- Reported accuracy will drop on the take-home batch for two independent reasons: the denominator now includes ground-truth claims that never produced a prediction, and the headline is no longer the acceptable-credited number. Nothing about the pipeline got worse.
- The confusion matrix is no longer square.

Purpose: make the metric population impossible to misread, so a number in `evaluation_metrics.json` cannot be better than the run it describes.
Output: a ground-truth-first evaluator with typed per-claim outcomes, two named matrix-derived metric sets, a config-rooted unscored column, updated CLI artifacts and chart, tests over missing/invalid/unmatched claims and raw-vs-policy divergence, corrected docs, and SR-006 closed in the backlog.
</objective>

<execution_context>
@~/.claude/gsd-core/workflows/execute-plan.md
@~/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/STATE.md
@.planning/quick/260929-lni-sr-006-ground-truth-first-evaluation-ali/260929-lni-CONTEXT.md
@.gsd/steering-decisions-2026-09-29.md (SR-006)
@.gsd/review_backlog.md (section "SR-006" and the "## Steering status" table; the SR-005 / SR-010 / SR-011 sections show the resolved-steering format)
@src/evaluation/evaluator.py (whole file — 433 lines: EvaluationResult ~21-48, evaluate_claim ~65-113, evaluate ~115-179, _count_failed_claim ~181-203, _discover_claim_ids ~205-210, _aggregate_scores ~212-285, _read_predicted / _assert_prediction_generation / _read_ground_truth ~287-325, _require_known_labels ~327-346, _match_decision ~348-360, _effective_pred_label ~362-370, _confusion_matrix ~372-390, _macro_f1 / _f1_for_label ~392-433)
@src/evaluation/__main__.py (whole file — 134 lines; `main` ~31-63, `_labeled_confusion_matrix` ~76-86, `_write_artifacts` ~89-130)
@src/evaluation/visualization.py (write_confusion_matrix_png ~25-35, _render_heatmap ~202-243, _cell_color ~246-252)
@src/evaluation/analysis_stats.py (aggregate_analysis_stats ~67-91, _discover_claim_ids ~125-131 — docstring change only)
@src/compliance/config/settings.py (EvaluationConfig ~369-385, the `_validated_label_vocabulary` validator pattern ~96-117, the ValueError subclasses ~480-580)
@src/compliance/preprocessing/claim_batch.py (_validate_claim_dir_name ~53-70, discover_claim_folder_names ~114-125)
@src/compliance/workflows/artifact_publication.py (generation_mismatch, MixedGenerationError — the SR-005 guard this plan must preserve)
@config.yaml (the `evaluation:` block, lines ~end of file)
@tests/test_evaluation/test_evaluator.py (whole file — 504 lines; `_write_pair` helper ~16-29 and every assertion that names a flat metric field)
@tests/test_evaluation/test_cli.py (whole file — 166 lines; `_write_minimal_config` ~9-79 carries the `evaluation:` yaml block)
@tests/test_config/test_settings.py (artifact-name and config-validation test patterns)
@tests/conftest.py (minimal_app_config_factory ~217-247 — takes `evaluation: EvaluationConfig | None`)
@README.md (lines ~100-115 directory table, ~142-161 Evaluation section, ~386-408 Results / latest eval, ~455-458 HITL metrics line)
@LOGIC.md (lines ~586-600 "Evaluation: Ground Truth vs Predicted", ~680-695 re-run guidance)

Facts verified at planning time (files re-read fresh; a concurrent session has been landing other SR-* items):
- `EvaluationResult` is consumed in exactly four places: `src/evaluation/__init__.py` (re-export), `src/evaluation/__main__.py`, `src/evaluation/visualization.py`, and `tests/test_evaluation/`. Nothing in `src/api`, `src/main.py` or `src/compliance` touches it, so reshaping it has a contained blast radius.
- `evaluate()` currently discovers from `results_dir` via `discover_claim_folder_names`; `_count_failed_claim` re-reads ground truth to decide whether a failed claim enlarges the accuracy denominator. Both disappear into the new outcome classification.
- `discover_claim_folder_names(root)` returns `[]` for a missing root and only matches directories whose name starts with `claim` (case-insensitive), sorted by numeric id. It works unchanged against `data_dir`; `data/raw` holds `claim 1` … `claim 25`.
- `AnswerReader.read` raises `FileNotFoundError` for an absent file and `json.JSONDecodeError` / `pydantic.ValidationError` / `TypeError` for a malformed one. `GroundTruth.acceptable_decision` defaults to the `np.nan` sentinel, so `is_nan_scalar` is the existing test for "no acceptable alternative".
- `GroundTruth` forbids extras, so a `run_id` in `predicted_answer.json` is invisible to the parsed model — the SR-005 guard reads the raw JSON through `generation_mismatch`, and that path must stay in front of the parse.
- `CheckOutcome` in `src/compliance/llm/checker.py:72` is the project's typed-enum precedent: `class CheckOutcome(str, Enum)` with `:cvar:` docstrings.
- `EvaluationConfig` is a `StrictConfigModel` (`extra="forbid"`), so adding a defaulted field is safe for the yaml fixtures in `tests/test_evaluation/test_cli.py` and `tests/test_config/test_settings.py`, which list `evaluation:` keys explicitly but need not list the new one. The validator + dedicated `ValueError` subclass pattern to copy is `ClassificationConfig._validated_label_vocabulary` with `DuplicateConfigLabelsError` (TRY003: message built inside the exception class).
- `_render_heatmap` assumes a square matrix and indexes `labels` on both axes; `_labeled_confusion_matrix` in `__main__` does the same. Both need the wider column axis.
- Baselines recaptured at planning time: `uv run python -m pytest -q --cov` → 391 passed, 3 deselected, 3.1s, total coverage 91.16% against a `fail_under = 90` floor (thin headroom — new untested branches can fail the gate). `uv run ruff check --no-fix src tests` clean. `uv run mypy src` → 0 errors in 44 files. `uv run mypy tests/test_evaluation` → 20 errors (16 in `test_evaluator.py`, 5 in `test_analysis_stats.py`), all pre-existing `no-any-unimported` noise from the conftest factory types.
- `uv run ruff format --check src tests` already fails on 5 files this plan does not touch. The directories this plan edits (`src/evaluation`, `src/compliance/config`, `tests/test_evaluation`, `tests/test_config`) are clean at baseline (14 files), so every format gate below is scoped to them. Do not reformat unrelated files to make a wider gate pass.
- `data/results/` and `data/preprocessed/` are gitignored; `.gsd/` is gitignored. ruff targets py310, line-length 120, C901 max-complexity 10, TRY rules on.
</context>

<population_contract>
The contract every task implements (D-01, D-02, P-01..P-08).

**Population (the denominator).** Discover claim folder names under `data_dir`. For each safe name, read `answer.json`:

| Ground truth | Prediction | Status | In population | Matrix cell |
|--------------|------------|--------|---------------|-------------|
| readable, in `labels` | readable, in `labels`, generation valid | `scored` | yes | `(gt, effective_pred)` |
| readable, in `labels` | file absent (no results folder, or folder without the artifact) | `missing_prediction` | yes | `(gt, unscored)` |
| readable, in `labels` | unparseable, out of vocabulary, or SR-005 generation mismatch | `invalid_prediction` | yes | `(gt, unscored)` |
| absent, unparseable, or out of vocabulary | anything | `invalid_ground_truth` | **no** | none |
| no claim folder under `data_dir` | present under `results_dir` | `unmatched_prediction` | **no** | none |

`coverage_rate` = `n_scored / n_ground_truth` (0.0 for an empty population).

**Named metrics.** Two `MetricSet`s over the same outcome list, differing only in what counts as a match:

| Metric | Match rule | Effective column for a match |
|--------|------------|------------------------------|
| `raw` | `prediction == ground_truth` | the true label (identical by definition) |
| `policy` | raw match, **or** prediction equals a non-nan `acceptable_decision` | the true label (A5 remap) |

For a non-match the column is the raw predicted label; for a non-scored outcome it is the unscored column.

**Derivation (why the three numbers cannot disagree).** Each `MetricSet` builds its matrix first, then reads its scalars off that matrix: `accuracy = trace / total`, and per label `tp = m[i][i]`, `fp = Σ_{r≠i} m[r][i]`, `fn = Σ_{c≠i} m[i][c]` (the unscored column included in `fn`), macro-averaged over all labels with zero-support labels contributing 0.0 as today. `total == n_ground_truth` always.
</population_contract>

<tasks>

<task type="tracer" tdd="true">
  <name>Task 1 (tracer): ground-truth-first population end to end — a claim with no results folder reaches the metrics artifact</name>
  <files>src/evaluation/evaluator.py, src/compliance/config/settings.py, config.yaml, src/evaluation/__main__.py, src/evaluation/visualization.py, tests/test_evaluation/test_evaluator.py, tests/test_evaluation/test_cli.py, tests/test_config/test_settings.py</files>
  <read_first>src/evaluation/evaluator.py (whole file), src/evaluation/__main__.py (whole file), src/evaluation/visualization.py (~25-35 and ~202-252), src/compliance/config/settings.py (~369-385 EvaluationConfig, ~96-117 validator pattern, ~510-520 DuplicateConfigLabelsError), src/compliance/preprocessing/claim_batch.py (~53-70, ~114-125), tests/test_evaluation/test_evaluator.py (whole file), tests/test_evaluation/test_cli.py (whole file), config.yaml (the `evaluation:` block)</read_first>
  <behavior>
    - Tracer end-to-end: a tmp tree with `claim 1` (ground truth + matching prediction) and `claim 2` (ground truth only, **no results folder at all**) run through `evaluation.__main__.main` writes a metrics artifact whose population reports 2 ground-truth claims, 1 scored, 1 missing prediction and `coverage_rate` 0.5, whose raw accuracy is 0.5, and whose matrix totals 2; both PNGs still render.
    - A results folder that exists but holds no `predicted_answer.json` produces the same missing-prediction accounting as a claim with no results folder — the population is defined by ground truth, not by directory shape.
    - The matrix invariant holds on every batch: the sum of all cells equals the ground-truth population, and accuracy equals the trace over that total.
    - The missing claim is attributable: its per-claim outcome carries its claim id, its ground-truth decision, a missing-prediction status and a reason, and its row's unscored column holds the count.
    - Config boundary: `evaluation.unscored_label` defaults to `NO_PREDICTION`, and a config whose unscored column name collides with a label — or whose labels repeat — is rejected at load with a named error.
  </behavior>
  <action>
Step 0, before editing: re-read the files above fresh and recapture the baselines for the SUMMARY — `uv run python -m pytest -q --cov` (pass count + total coverage), `uv run ruff check --no-fix src tests`, `uv run ruff format --check src/evaluation src/compliance/config tests/test_evaluation tests/test_config`, `uv run mypy src`, and `uv run mypy tests/test_evaluation` (error count per file). Planning-time values are in the context block. Write the failing tests first (RED), then implement.

`src/compliance/config/settings.py` + `config.yaml` (P-03):
- Add `unscored_label: str = "NO_PREDICTION"` to `EvaluationConfig` with a `:param:` line saying it names the confusion-matrix column that holds ground-truth claims with no scorable prediction.
- Add an `@model_validator(mode="after")` named after what it guarantees (e.g. `_validated_metric_vocabulary`) that rejects duplicate entries in `labels` (reuse `DuplicateConfigLabelsError`) and rejects an `unscored_label` that appears in `labels`, via a new `ValueError` subclass beside the others at the bottom of the module that builds its own message (TRY003). The collision matters because the column axis is `labels + [unscored_label]`, and a collision would make two columns mean the same thing.
- List `unscored_label` in the `evaluation:` block of `config.yaml` beside `labels`.

`src/evaluation/evaluator.py` — the shape and the population (D-01, P-01, P-02, P-06, P-08). Public surface, all with `:param:` / `:cvar:` docstrings:
- `class ClaimStatus(str, Enum)` following the `CheckOutcome` precedent, with members for a scored claim, a missing prediction, an invalid prediction, invalid ground truth, and a prediction with no ground truth.
- `@dataclass(frozen=True) class ClaimOutcome`: `claim_id`, `status`, `ground_truth: str | None`, `prediction: str | None`, `reason: str | None`, `raw_match: bool`, `policy_match: bool`, `human_in_the_loop: bool | None`. Record `policy_match` here in Task 1 even though only the raw metric set is published yet — the acceptable-decision comparison is a property of the claim, and Task 2 consumes it without reshaping anything.
- `@dataclass(frozen=True) class MetricSet`: `name`, `accuracy`, `f1_macro`, `confusion_matrix`, `n`. Docstring states rows/columns and that the scalars are derived from the matrix.
- `@dataclass(frozen=True) class EvaluationPopulation`: `n_ground_truth`, `n_scored`, `n_missing_prediction`, `n_invalid_prediction`, `n_invalid_ground_truth`, `n_unmatched_prediction`, `coverage_rate`.
- Reshape `EvaluationResult` to `claim_ids` (ground-truth population in discovery order), `labels`, `unscored_label`, `outcomes`, `population`, `raw: MetricSet`, `human_in_the_loop_true`, `human_in_the_loop_false`. Remove the flat unnamed metric fields and the per-pair vectors that only tests read — a reader must not be able to pick up an accuracy without its name and population (P-04). <!-- planner-discipline-allow: n_evaluated -->

Methods (public orchestrates, private helpers do the work):
- `evaluate_claim(claim_id)` keeps its strict contract (P-08): validate the name, read prediction (SR-005 generation guard stays in front of the parse), read ground truth, reject decisions outside `labels`, then build one outcome and aggregate it through the shared helpers so the one-claim result has the same shape as a batch of one.
- `evaluate()` becomes an orchestrator: collect ground-truth claim ids, classify each into an outcome, append unmatched-prediction outcomes for results-only claims, then build the population and the raw metric set. One summary log line reporting ground-truth count, scored count, coverage rate and raw accuracy.
- `_ground_truth_claim_ids()` — `discover_claim_folder_names(Path(data_dir))`, keeping the existing unsafe-name skip with its `evaluation_batch` branch log.
- `_prediction_claim_ids()` — the same over `results_dir`, used only to find unmatched predictions.
- `_classified_outcome(claim_id)` — the batch path, never raising for a known failure: read ground truth first (failure or an out-of-vocabulary decision → invalid-ground-truth outcome), then the prediction (absent file → missing; mismatch, parse failure or out-of-vocabulary decision → invalid), each with a short stable reason code and a WARNING `log_branch_decision` in the existing `evaluation_batch` style. Keep it inside C901 10 by delegating each read to a helper named after what it produces.
- `_outcome_from_pair(claim_id, gt, pred)` — the single place that computes `raw_match` and `policy_match` (keep `_match_decision` / `is_nan_scalar` as the acceptable-decision test) so the strict and classified paths cannot drift.
- `_metric_set(outcomes, labels, *, name, matched)` where `matched` is a `Callable[[ClaimOutcome], bool]`; module-level `_raw_match(outcome)` supplies the raw rule. It builds the matrix through `_confusion_matrix(outcomes, labels, matched)` (rows `labels`, columns `labels + [unscored_label]`), then `_accuracy_from_matrix` and `_macro_f1_from_matrix` read the scalars off those cells. Delete the vector-based matrix/F1 helpers and `_effective_pred_label`'s vector signature — replaced by the per-outcome column resolution — so there is one metric derivation, not two.
- Empty population: every count 0, `coverage_rate` 0.0, accuracy and F1 0.0, matrix of the right shape filled with zeros.

`src/evaluation/__main__.py`: rebuild the two JSON payloads around the new shape.
- Metrics payload keys: `claim_ids`, `labels`, `column_labels` (labels plus the unscored column), `population` (the dataclass as a dict, including `coverage_rate`), `raw` (`accuracy`, `f1_macro`, `n`, `confusion_matrix`, `confusion_matrix_labeled`), `human_in_the_loop_true`, `human_in_the_loop_false`, and `outcomes` (one compact object per claim: id, status value, ground truth, prediction, reason).
- Confusion-matrix payload: `labels`, `column_labels`, `rows`/`cols` axis descriptions as today, and a `raw` block with `matrix` + `labeled`.
- `_labeled_confusion_matrix` takes the matrix and both axes so it can label the wider column set.
- The completion log line reports ground-truth count, scored count, coverage rate and raw accuracy, and labels the analysis-stats count distinctly so the two n values are not read as the same population (P-07).

`src/evaluation/visualization.py` (P-05): `_render_heatmap` draws `labels` rows against `labels + [unscored_label]` columns (width follows the column count) and uses `result.raw.confusion_matrix`. Title becomes two lines: the first with the raw accuracy, raw macro F1 and the ground-truth population; the second with the coverage rate and the HITL counts. Add the extra title band to the computed height so nothing is clipped.

tests/test_evaluation/test_evaluator.py: update every assertion to the named fields, and add the tracer coverage:
- `test_ground_truth_without_results_folder_is_counted_incorrect` — `claim 1` correct, `claim 2` ground truth only with no results directory: population 2 / scored 1 / missing 1, `coverage_rate` 0.5, raw accuracy 0.5, `claim 2` present in `claim_ids` with a missing-prediction outcome, and its row's unscored column holding 1.
- `test_matrix_total_equals_population` — all cells sum to the ground-truth population and accuracy equals trace/total on a mixed batch.
- Rework `test_evaluate_batch_skips_missing_prediction` into the results-folder-without-artifact case with the same accounting, and rename it to say what it now asserts.
- Keep `test_acceptable_decision_counts_as_match` / `test_acceptable_decision_ignored_when_nan` passing by asserting the recorded per-claim match flags (raw false, policy true for the acceptable case); the named policy metric arrives in Task 2.
- Update `test_confusion_matrix_label_order` for the wider column axis, and `test_evaluate_batch_empty` for the zeroed population.
- Update the existing mixed-generation batch test to the new field names, keeping its semantics (one scored, one counted incorrect) — SR-005 behaviour is proven in depth in Task 2.

tests/test_evaluation/test_cli.py: add `unscored_label` to the `evaluation:` yaml fixture, seed the ground-truth-only second claim, and assert the metrics payload's population block, `coverage_rate`, `raw` block and `outcomes` list, plus that both PNGs still start with the PNG magic bytes.

tests/test_config/test_settings.py: assert the `unscored_label` default and that a colliding unscored column name is rejected at load.

Commit: stage only the eight paths explicitly (never `git add -A` / `git add .`, never bypass hooks). First run `git status --short` and `git diff --stat -- <the paths>`; if a path shows hunks this task did not write (concurrent session), stop and report instead of committing. Message `feat(SR-006): evaluate the ground-truth population and count missing predictions`, ending with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && uv run python -m pytest -q tests/test_evaluation tests/test_config && uv run python -m pytest -q tests/test_evaluation/test_evaluator.py -k "without_results_folder or matrix_total_equals_population" && uv run python -m pytest -q --cov && uv run ruff check --no-fix src/evaluation src/compliance/config tests/test_evaluation tests/test_config && uv run ruff format --check src/evaluation src/compliance/config tests/test_evaluation tests/test_config && uv run mypy src && grep -q "class ClaimStatus" src/evaluation/evaluator.py && grep -q "class EvaluationPopulation" src/evaluation/evaluator.py && grep -q "coverage_rate" src/evaluation/evaluator.py && grep -q "unscored_label" config.yaml && grep -q "unscored_label" src/compliance/config/settings.py && grep -q "coverage_rate" src/evaluation/__main__.py && grep -q "data_dir" src/evaluation/evaluator.py</automated>
  </verify>
  <done>The denominator comes from the ground-truth tree: a claim with `answer.json` and no results folder is in the population, counted incorrect, and visible in `evaluation_metrics.json` with a `coverage_rate`. Accuracy, macro F1 and the matrix are derived from one matrix whose total equals the population and whose columns include a config-rooted unscored column. Per-claim outcomes name the status and reason. The CLI writes the reshaped artifacts and both PNGs still render. Evaluation, config and fast-lane suites pass with coverage at or above the 90 floor; ruff, format and mypy are clean on the touched paths. The commit contains exactly the 8 files.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: publish the policy metric beside the raw one and prove the whole outcome taxonomy</name>
  <files>src/evaluation/evaluator.py, src/evaluation/__main__.py, src/evaluation/visualization.py, src/evaluation/analysis_stats.py, tests/test_evaluation/test_evaluator.py, tests/test_evaluation/test_cli.py</files>
  <read_first>src/evaluation/evaluator.py as left by Task 1, src/evaluation/__main__.py as left by Task 1, src/evaluation/visualization.py as left by Task 1, src/evaluation/analysis_stats.py (~67-91, ~125-131), tests/test_evaluation/test_evaluator.py as left by Task 1, tests/test_evaluation/test_cli.py as left by Task 1, src/compliance/workflows/artifact_publication.py (generation_mismatch / MixedGenerationError)</read_first>
  <behavior>
    - Raw vs policy divergence (D-02): a claim whose ground truth is UNCERTAIN with acceptable DENY and whose prediction is DENY is wrong under `raw` and right under `policy`; the raw matrix records the off-diagonal cell and the policy matrix records the diagonal one, and both metric sets report the same `n` and the same matrix total.
    - Invalid ground truth is excluded from the denominator, not scored: a claim folder under `data_dir` with an unparseable `answer.json`, and one whose decision is outside `evaluation.labels`, are both reported as invalid-ground-truth counts, are absent from `claim_ids`, and leave accuracy on the remaining claims unchanged.
    - An invalid prediction is counted incorrect: an out-of-vocabulary predicted decision and an unparseable `predicted_answer.json` each land in the population with an invalid-prediction status and occupy the unscored column.
    - SR-005 preserved: `evaluate_claim` still raises `MixedGenerationError` with claim, artifact and reason for a prediction whose run id disagrees with the published manifest; the batch classifies the same claim as an invalid prediction counted incorrect; a manifest-less legacy tree still scores.
    - A prediction under `results_dir` with no ground-truth claim folder is reported as an unmatched prediction and appears in no metric (P-06), and unsafe folder names from either tree are skipped without reading outside the roots.
    - The metrics artifact carries both named blocks with their shared population, and the chart title carries both accuracies.
  </behavior>
  <action>
Re-read the files as left by Task 1 before editing. Write the failing tests first (RED), then implement.

`src/evaluation/evaluator.py` (D-02):
- Add module-level `_policy_match(outcome)` beside `_raw_match`, and build a second `MetricSet` named for the policy rule from the same outcome list through the existing `_metric_set` helper — no second derivation path, no second population.
- Add `policy: MetricSet` to `EvaluationResult` with a `:param:` line contrasting it against `raw`: same claims, same matrix shape, the only difference is that a prediction equal to a non-nan `acceptable_decision` is credited and remapped onto the true label (A5). Extend the `EvaluationResult` class docstring with one sentence stating that the two names exist so a reader always knows which matching rule produced a number.
- Extend the batch summary log line with the policy accuracy.

`src/evaluation/__main__.py`: add the `policy` block to the metrics payload and to the confusion-matrix artifact, mirroring the `raw` block exactly (`accuracy`, `f1_macro`, `n`, `confusion_matrix`, `confusion_matrix_labeled`), and add the policy accuracy to the completion log.

`src/evaluation/visualization.py`: put the policy accuracy on the second title line beside the coverage rate, keeping the raw matrix as the rendered cells (P-05).

`src/evaluation/analysis_stats.py` (P-07): extend the `aggregate_analysis_stats` docstring (and the local discovery helper docstring) to state that this population is the set of readable `analysis_result.json` payloads under `results_dir` and is deliberately **not** the evaluator's ground-truth population, so `n_claims` and the evaluation population are not comparable. Docstrings only — no behaviour change.

tests/test_evaluation/test_evaluator.py — the expansion matrix:
- `test_policy_metric_credits_acceptable_decision` and `test_raw_and_policy_share_one_population` per the behaviours above, asserting the specific diverging cells in both matrices.
- `test_invalid_ground_truth_excluded_from_population` (unparseable `answer.json`) and a second case for an out-of-vocabulary ground-truth decision.
- `test_invalid_prediction_counts_as_incorrect` for an out-of-vocabulary predicted decision and for unparseable prediction JSON.
- Deepen the mixed-generation tests: `evaluate_claim` still raises with the three attributes, the batch records the invalid-prediction status with the mismatch reason and counts it incorrect, and the manifest-less claim still scores (keep the existing legacy test's expectations intact).
- `test_prediction_without_ground_truth_is_unmatched` for the orphan results folder, replacing the old skips-missing-ground-truth assertions with the counted version.
- Update `test_evaluate_batch_refuses_unsafe_names_in_discovery` to patch the ground-truth discovery helper (and keep its proof that a sibling file outside the roots is never read).

tests/test_evaluation/test_cli.py: assert both named blocks in the metrics payload and in `confusion_matrix.json`, with equal `n` and equal matrix totals.

Commit (stage only the six paths explicitly, with the same concurrent-change check as Task 1): `feat(SR-006): report raw and acceptable-policy metrics over one population`, ending with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && uv run python -m pytest -q tests/test_evaluation && uv run python -m pytest -q tests/test_evaluation/test_evaluator.py -k "policy or invalid_ground_truth or invalid_prediction or mixed_generation or unmatched or without_manifest" && uv run python -m pytest -q --cov && uv run ruff check --no-fix src/evaluation tests/test_evaluation && uv run ruff format --check src/evaluation tests/test_evaluation && uv run mypy src && grep -q "policy" src/evaluation/evaluator.py && grep -q "MixedGenerationError" src/evaluation/evaluator.py && test "$(grep -vE '^\s*#' src/evaluation/evaluator.py | grep -c '_metric_set(')" -ge 3 && grep -q "policy" src/evaluation/__main__.py</automated>
  </verify>
  <done>Both named metric sets are published from one outcome list: `raw` and `policy` share the ground-truth population, the same matrix shape and the same total, and the acceptable-decision credit is visible only under its own name. Every non-scored claim is classified and counted — invalid ground truth out of the denominator, missing and invalid predictions in it and incorrect, unmatched predictions reported separately. The SR-005 mixed-generation refusal is unchanged at the single-claim boundary and counted incorrect in the batch. `analysis_stats` documents its different population. Fast lane passes with coverage at or above the 90 floor. The commit contains exactly the 6 files.</done>
</task>

<task type="auto">
  <name>Task 3: document the evaluated population and close SR-006</name>
  <files>README.md, LOGIC.md, .gsd/review_backlog.md</files>
  <read_first>src/evaluation/evaluator.py and src/evaluation/__main__.py as left by Tasks 1-2, README.md (~100-115, ~142-161, ~386-408, ~455-458), LOGIC.md (~586-600, ~680-695), .gsd/review_backlog.md (the SR-006 section, the SR-005 / SR-010 resolved-steering format, and the "## Steering status" table)</read_first>
  <behavior>
    - A reader of README.md learns which claims are evaluated (ground truth first), that a missing prediction counts as incorrect, what `coverage_rate` means, and that accuracy exists under two names with different matching rules.
    - LOGIC.md's evaluation section states the population contract and the matrix column axis, and its stale measured numbers are explicitly marked as measured under the previous results-first population rather than silently left as current.
    - No fabricated metrics: numbers are only changed where they are re-measured in this task, and the docs say re-running `make analyze` + `make evaluation` is what refreshes them.
  </behavior>
  <action>
Re-read the modules as left by Tasks 1-2 so the documented field names match the code exactly. Change only statements that are now wrong; no restructuring, no new top-level sections.

README.md:
- Evaluation section: state that the evaluated population is discovered from the ground-truth tree (`data_dir`), so a claim with `answer.json` and no prediction is counted as incorrect rather than skipped, and that `coverage_rate` reports the scored share of that population. Add the two named metrics with one line each on their matching rule, and note the matrix column axis is the labels plus the unscored column.
- Artifact table: keep the three filenames, and say the metrics JSON now carries a population block, per-claim outcomes and both named metric blocks.
- The line pairing predictions with answers by folder name: correct it to say pairing is ground-truth-driven and that predictions with no ground-truth folder are reported as unmatched.
- Results / latest eval: mark the measured table as measured under the previous results-first population and the acceptable-credited rule, and point at `make analyze` + `make evaluation` to re-measure under the new population. Do not invent replacement numbers.
- The HITL metrics line: say the HITL counts are over scored predictions.

LOGIC.md:
- In the evaluation section, add the population contract (which claims are in the denominator, what a missing or invalid prediction does, what excludes a claim entirely) and the raw-vs-policy distinction, plus the matrix column axis and the fact that accuracy and F1 are derived from that matrix.
- Mark the existing measured figures with the population they were measured under and keep the re-run instruction.

Gates, compared against the Task 1 baselines: `uv run python -m pytest -q --cov` (fast lane) passes with coverage at or above the 90 floor; `uv run ruff check --no-fix src tests` clean; `uv run mypy src` reports 0 errors; `uv run mypy tests/test_evaluation` no worse than the recaptured baseline. Fix any new failure before committing.

Backlog (`.gsd/review_backlog.md` is gitignored: edit, never stage):
- Change the SR-006 header to `### [x] SR-006: Ground-truth-first evaluation + aligned metrics ⚠️`.
- Replace its "**Steering needed**" questions with a "**Steering (resolved 2026-09-29)**" block in the SR-005 / SR-010 style listing D-01 and D-02, plus P-01..P-08 as "planner discretion, flagged".
- Add a one-paragraph "**Resolution:**" naming the ground-truth-first denominator, the typed per-claim outcomes, the matrix-derived metric sets with the unscored column, `coverage_rate`, the raw/policy split, the removal of the flat unnamed metric fields, the unchanged `analysis_stats` population, and the quick id 260929-lni.
- Update the Steering status row to `| SR-006 | Steered 2026-09-29: missing pred = incorrect + coverage_rate; raw vs acceptable-policy metrics — done (quick 260929-lni) |`. Touch no other SR entry.

SUMMARY content (written by the executor workflow) must include: recaptured baselines vs final gate numbers; the population contract as implemented; P-01..P-08; the behaviour-change register from the objective (reshaped metrics artifacts, non-square matrix, expected accuracy drop from the wider denominator and the un-credited headline); and the follow-ups — SR-007 owns read-only GET plus idempotent analysis, SR-009 owns upload/path hardening, SR-013 owns the policy-engine extract, and re-running `make analyze` + `make evaluation` is what re-measures the batch under the new population.

Commit (stage only `README.md` and `LOGIC.md` explicitly, with the same concurrent-change check as Task 1): `feat(SR-006): document the ground-truth-first evaluation population`, ending with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && uv run python -m pytest -q --cov && uv run ruff check --no-fix src tests && uv run mypy src && grep -q "coverage_rate" README.md && grep -q "coverage_rate" LOGIC.md && grep -q "### \[x\] SR-006" .gsd/review_backlog.md && grep -q "| SR-006 | Steered 2026-09-29" .gsd/review_backlog.md && STAGED="$(git diff --cached --name-only)" && test "$(printf '%s' "$STAGED" | grep -c review_backlog)" = 0</automated>
  </verify>
  <done>README.md and LOGIC.md describe the ground-truth-first population, the missing-prediction rule, `coverage_rate`, the two named metrics and the widened matrix axis, and their stale measured numbers are labelled with the population they came from instead of being silently reused or invented. All gates meet or beat the Task 1 baselines. SR-006 is checked off with steering recorded in the backlog, and the backlog is not staged. The commit contains exactly the 2 tracked files.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Claim folder name → ground-truth and prediction reads | Discovered directory names become path segments under `data_dir` and `results_dir` |
| Published results tree → reported metrics | Artifacts written by a pipeline run are turned into numbers a reviewer trusts |
| Config vocabulary → matrix axes | `evaluation.labels` and the unscored column name define every cell index |
| Metric payloads and logs → operators | Evaluation output leaves the process as JSON, PNG and log lines |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-SR006-01 | Repudiation | metric population | high | mitigate | The denominator is the ground-truth population, missing and invalid predictions are counted incorrect, and accuracy, F1 and the matrix are derived from one matrix whose total equals that population (D-01, P-02). A run can no longer report a number that quietly excludes the claims it failed on. Proven by the matrix-total invariant test and the ground-truth-only claim test. |
| T-SR006-02 | Repudiation | acceptable-decision credit | medium | mitigate | The credit is published only under the policy name, beside the raw number over the same population (D-02). A reader cannot pick up a credited accuracy believing it is exact-match. Proven by the raw-vs-policy divergence test. |
| T-SR006-03 | Tampering | claim folder name → filesystem reads | high | mitigate | Both discoveries keep `_validate_claim_dir_name` with the existing skip-and-log behaviour before any path is joined, and the unsafe-name discovery test still asserts that a file outside the roots is never read. |
| T-SR006-04 | Tampering | stale or torn result generations scored as current | high | mitigate | The SR-005 `generation_mismatch` guard stays in front of the prediction parse; a mismatch raises at the single-claim boundary and becomes an invalid prediction counted incorrect in the batch (Task 2). Scoring a superseded generation remains impossible. |
| T-SR006-05 | Tampering | config vocabulary collision | medium | mitigate | `unscored_label` is validated at load to be absent from `labels`, and duplicate labels are rejected, so no two matrix columns can denote the same thing (P-03). Failure is at config load, not mid-run. |
| T-SR006-06 | Information Disclosure | metrics artifacts and evaluation logs | medium | mitigate | Outcomes, payloads and log lines carry claim ids, decision labels, statuses and short reason codes only — never explanation text, OCR content, extracted names or any other claim narrative (CLAUDE.md security rule). |
| T-SR006-07 | Denial of Service | large ground-truth trees | low | accept | Evaluation is a bounded local batch over one claim folder at a time with no concurrency and no unbounded buffering; the ground-truth tree is the same set the pipeline already walks. |
| T-SR006-08 | Repudiation | analysis_stats population read as the evaluated one | low | mitigate | `analysis_stats` keeps its `results_dir` discovery and documents that it is a different population, and the CLI log labels the two counts distinctly (P-07). |

No package installs in this plan, so there is no supply-chain row.
</threat_model>

<verification>
- `uv run python -m pytest -q --cov` (fast lane, integration deselected) passes with total coverage at or above the `fail_under = 90` floor; the 391-test planning baseline plus the new SR-006 tests all pass.
- `uv run ruff check --no-fix src tests` is clean; `uv run ruff format --check src/evaluation src/compliance/config tests/test_evaluation tests/test_config` is clean; `uv run mypy src` reports 0 errors; `tests/test_evaluation` is no worse than its 20-error mypy baseline.
- A claim with `answer.json` and no results folder appears in `claim_ids`, carries a missing-prediction outcome, occupies the unscored column of its ground-truth row, and lowers both accuracy and `coverage_rate`.
- For both named metric sets, the sum of all confusion-matrix cells equals `population.n_ground_truth` and accuracy equals the trace over that total.
- A claim matching only through `acceptable_decision` is wrong under `raw` and right under `policy`, with the two matrices differing in exactly those two cells.
- A claim whose prediction disagrees with its SR-005 run manifest raises at `evaluate_claim` and is counted incorrect in the batch; a manifest-less claim still scores.
- `evaluation_metrics.json` carries `population` with `coverage_rate`, both named metric blocks, `column_labels` one entry wider than `labels`, and a per-claim `outcomes` list; both PNGs render.
- `git log --stat -3` shows 3 SR-006 commits, each containing only its task's tracked files; `.gsd/review_backlog.md` is never staged.
</verification>

<success_criteria>
- Claims with ground truth and no results folder appear in the evaluation, counted as incorrect, with `coverage_rate` reporting the scored share (backlog "Done when", D-01).
- Accuracy, F1 and the confusion matrix share one documented population by construction, and the acceptable-decision rule is published as an explicitly separated named metric (backlog "Done when", D-02).
- Every claim in either tree is accounted for: scored, missing, invalid prediction, invalid ground truth, or unmatched prediction — each counted and attributable per claim.
- Tests cover missing predictions, ground-truth-first discovery, and raw vs acceptable metrics.
- The SR-005 mixed-generation refusal is preserved at the single-claim boundary and counted incorrect in the batch.
- README.md and LOGIC.md describe the implemented population contract, and SR-006 is marked `[x]` with steering recorded in `.gsd/review_backlog.md`.
</success_criteria>

<output>
Create `.planning/quick/260929-lni-sr-006-ground-truth-first-evaluation-ali/260929-lni-SUMMARY.md` when done
</output>
