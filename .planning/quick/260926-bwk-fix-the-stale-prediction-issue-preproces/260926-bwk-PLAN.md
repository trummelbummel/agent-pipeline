---
phase: 260926-bwk-fix-the-stale-prediction-issue-preproces
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/compliance/workflows/predicted_answer_io.py
  - src/compliance/workflows/pipeline.py
  - src/compliance/workflows/claim_pipeline.py
  - tests/test_workflows/test_pipeline.py
  - tests/test_workflows/test_predicted_answer_io.py
autonomous: true
requirements: []

estimate:
  tokens: 22000
  raw_tokens: 22000
  tasks: 2
  confidence: low

must_haves:
  truths:
    - "Preprocess with no bundle decision does not delete an analysis-authored predicted_answer.json"
    - "Preprocess with no bundle decision still removes a Benford/fraud preprocess-origin predicted_answer when analysis_result.json is absent"
    - "Preprocess with a fraud decision still writes/overwrites predicted_answer under results_dir"
    - "ClaimPipeline analysis still writes evaluator-facing predicted_answer.json from _decision_from_state"
    - "predicted_answer write/remove ownership lives in one small module with explicit source + removal rules"
  artifacts:
    - path: "src/compliance/workflows/predicted_answer_io.py"
      provides: "Central write + safe-remove for predicted_answer.json"
      contains: "remove_stale_preprocess_prediction"
    - path: "src/compliance/workflows/pipeline.py"
      provides: "Preprocess uses shared I/O; no blind unlink"
      contains: "predicted_answer_io"
    - path: "src/compliance/workflows/claim_pipeline.py"
      provides: "Analysis writes via shared I/O with analysis source"
      contains: "predicted_answer_io"
    - path: "tests/test_workflows/test_pipeline.py"
      provides: "Regression: preserve analysis prediction; clear fraud-only stale"
    - path: "tests/test_workflows/test_predicted_answer_io.py"
      provides: "Unit coverage for origin detection and remove rules"
  key_links:
    - from: "PreprocessingPipeline._predicted_answer_path"
      to: "predicted_answer_io.write_preprocess / remove_stale_preprocess_prediction"
      via: "_predicted_answer_from_bundle None vs GroundTruth"
    - from: "ClaimPipeline._written_predicted_answer"
      to: "predicted_answer_io.write_analysis"
      via: "_decision_from_state payload"
    - from: "remove_stale_preprocess_prediction"
      to: "results_dir/{claim}/predicted_answer.json"
      via: "source marker OR fraud explanation heuristic; never when analysis_result.json exists"
---

<objective>
Fix stale prediction deletion: preprocess must not unlink analysis-written `predicted_answer.json` when it has no early decision. Consolidate predicted_answer write/remove into one small module so ownership is explicit.

Purpose: `make analyze` always preprocesses first; the current blind `unlink` on `stale_no_pipeline_decision` deletes evaluator predictions (and races concurrent preprocess), causing FileNotFoundError in eval.
Output: Shared `predicted_answer_io` + preprocess/analysis wired through it + regression tests.
</objective>

<execution_context>
@~/.claude/gsd-core/workflows/execute-plan.md
@~/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@src/compliance/workflows/pipeline.py
@src/compliance/workflows/claim_pipeline.py
@src/compliance/preprocessing/claim_batch.py
@src/compliance/models/claim.py
@src/compliance/branch_log.py
@tests/test_workflows/test_pipeline.py
@tests/test_workflows/test_claim_pipeline.py

## Locked design (validated against code)

Bug root: `PreprocessingPipeline._predicted_answer_path` (pipeline.py ~373–401) unlinks **any** existing `results_dir/{claim}/predicted_answer.json` when `_predicted_answer_from_bundle` returns None (`reason=stale_no_pipeline_decision`). Intent was only to drop leftover Benford DENYs after `benford.enabled` is off. Analysis owns the real evaluator file via `ClaimPipeline._written_predicted_answer` (writes beside `analysis_result.json`).

Chosen approach (combine origin-aware remove + consolidate):
1. New small module `src/compliance/workflows/predicted_answer_io.py` owns all predicted_answer path write/remove (CLAUDE: prefer edit-over-create, but scatter across pipeline + claim_pipeline + claim_batch is the root cause — one I/O module is the fit).
2. Writers stamp a JSON field `source`: `"preprocess"` | `"analysis"` (string constant; not a GroundTruth model field — add on dump only so GroundTruth schema stays unchanged).
3. `remove_stale_preprocess_prediction(predicted_path, *, analysis_result_path)` unlinks **only** when:
   - file exists, AND
   - sibling `analysis_result.json` does **not** exist, AND
   - file is preprocess-origin: `source == "preprocess"` OR (missing source AND explanation looks like fraud/Benford — covers legacy files written before this fix).
   - Otherwise SKIP (preserve analysis-authored or unknown-but-analysis-present files). Log branch outcomes with existing `log_branch_decision`.
4. When preprocess has a new decision: overwrite via write_preprocess (even if analysis file existed — fraud early-exit is intentional; analysis re-run rewrites).
5. Keep `_predicted_answer_from_bundle` in claim_batch.py (derivation only — not I/O).

Discretion: module name `predicted_answer_io.py` under workflows/; public functions named for what they produce (`write_preprocess_predicted_answer`, `write_analysis_predicted_answer`, `remove_stale_preprocess_prediction`, `is_preprocess_origin_prediction`). Do not add config keys.
</context>

<interfaces>
Existing:
- `_predicted_answer_from_bundle(bundle) -> GroundTruth | None` in claim_batch.py
- `PreprocessingPipeline._predicted_answer_path` — replace body to call shared I/O
- `ClaimPipeline._written_predicted_answer` — replace body write with shared I/O; keep HITL payload merge before write
- `artifacts.predicted_answer` / `artifacts.analysis_result` from PreprocessedArtifactNames
- `log_branch_decision(logger, branch="predicted_answer", outcome=..., reason=..., **fields)`

New surface (`predicted_answer_io.py`):
- `SOURCE_PREPROCESS = "preprocess"`, `SOURCE_ANALYSIS = "analysis"`
- `write_preprocess_predicted_answer(path: Path, prediction: GroundTruth) -> Path` — mkdir parent, dump JSON with `source=preprocess`, log WROTE
- `write_analysis_predicted_answer(path: Path, payload: dict[str, Any]) -> Path` — mkdir parent, ensure `source=analysis` on payload, write, log WROTE reason=analysis_decision
- `is_preprocess_origin_prediction(data: dict[str, Any]) -> bool` — source==preprocess OR (no source and fraud/benford explanation heuristic)
- `remove_stale_preprocess_prediction(predicted_path: Path, *, analysis_result_path: Path) -> bool` — True if unlinked; False if skipped/absent
</interfaces>

<tasks>

<task type="tracer" tdd="true">
  <name>Task 1: Safe remove rules + shared I/O module + preprocess wiring</name>
  <files>src/compliance/workflows/predicted_answer_io.py, src/compliance/workflows/pipeline.py, tests/test_workflows/test_predicted_answer_io.py, tests/test_workflows/test_pipeline.py</files>
  <read_first>
    - src/compliance/workflows/pipeline.py (_predicted_answer_path unlink block ~373–421)
    - src/compliance/preprocessing/claim_batch.py (_predicted_answer_from_bundle)
    - tests/test_workflows/test_pipeline.py (test_process_claim_skips_predicted_answer_without_pipeline_decision ~183; fraud write test ~142)
    - src/compliance/branch_log.py
    - CLAUDE.md (helpers, Path joins, from __future__)
  </read_first>
  <behavior>
    - remove_stale: analysis-source predicted_answer + no analysis_result → still preserved (safe default without analysis_result? Prefer: analysis source never removed by preprocess; also preserve when analysis_result exists regardless of source)
    - remove_stale: fraud explanation legacy file, no analysis_result → unlinked
    - remove_stale: analysis-source file OR analysis_result.json present → file remains
    - preprocess process_claim with no decision does NOT delete analysis-written predicted_answer (setup: write analysis-shaped JSON with source=analysis or with analysis_result.json sibling)
    - existing fraud-stale test still passes (Benford-only file removed when no decision and no analysis_result)
    - fraud deny still writes predicted_answer with source=preprocess
  </behavior>
  <action>
    Create `predicted_answer_io.py` with the interfaces above (from __future__, typed, public docstrings with :param:). Wire `PreprocessingPipeline._predicted_answer_path`: on None decision call `remove_stale_preprocess_prediction(predicted_path, analysis_result_path=results_claim / artifacts.analysis_result)` instead of unconditional unlink; on decision call `write_preprocess_predicted_answer`. Update `test_process_claim_skips_predicted_answer_without_pipeline_decision` to keep asserting fraud-stale removal. Add new pipeline test: seed results with analysis-authored predicted_answer (and preferably analysis_result.json), run process_claim with no fraud decision, assert predicted_answer still present. Add focused unit tests in test_predicted_answer_io.py for origin heuristic and remove rules. Do not change claim_pipeline in this task.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance &amp;&amp; uv run pytest tests/test_workflows/test_predicted_answer_io.py tests/test_workflows/test_pipeline.py -q --tb=short -x</automated>
  </verify>
  <done>Preprocess no longer blindly deletes predicted_answer; fraud-only stale still cleared; shared module owns write/remove; tests green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Route analysis writer through predicted_answer_io</name>
  <files>src/compliance/workflows/claim_pipeline.py, tests/test_workflows/test_claim_pipeline.py, tests/test_workflows/test_pipeline.py</files>
  <read_first>
    - src/compliance/workflows/claim_pipeline.py (_written_predicted_answer ~920–949)
    - src/compliance/workflows/predicted_answer_io.py (from Task 1)
    - tests/test_workflows/test_claim_pipeline.py (assertions that predicted_answer exists after analyze)
  </read_first>
  <behavior>
    - After analyze_claim happy path, predicted_answer.json exists under results_dir with source=analysis and decision from analysis
    - Existing claim_pipeline predicted_answer assertions still pass
    - Re-run preprocess with no fraud decision after analysis: predicted_answer remains (integration of Task 1 rules + analysis source stamp)
  </behavior>
  <action>
    Replace the file write inside `ClaimPipeline._written_predicted_answer` with `write_analysis_predicted_answer(path, payload)` after building the HITL-enriched payload from `_decision_from_state`. Keep path construction and claim_id validation on ClaimPipeline. Confirm at least one existing claim_pipeline test still asserts predicted_answer content; if none stamp `source`, extend one lightweight assertion that `source == "analysis"` OR add a small pipeline integration test that writes via analysis helper then runs preprocess without decision and asserts file survives. Do not duplicate unlink logic in claim_pipeline.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance &amp;&amp; uv run pytest tests/test_workflows/test_predicted_answer_io.py tests/test_workflows/test_pipeline.py tests/test_workflows/test_claim_pipeline.py -q --tb=short -x</automated>
  </verify>
  <done>Both preprocess and analysis write predicted_answer through one module; analysis source stamped; full workflow test suite for these files green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| results_dir filesystem | Preprocess and analysis both read/write claim result artifacts; preprocess must not destroy analysis outputs |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-260926-bwk-01 | Tampering | remove_stale_preprocess_prediction | medium | mitigate | Only unlink preprocess-origin predictions; never when analysis_result.json exists or source=analysis |
| T-260926-bwk-02 | Information Disclosure | predicted_answer.json logs | low | accept | Existing branch logs already include claim id + path; no new secrets |
| T-260926-bwk-SC | Tampering | npm/pip/cargo installs | low | accept | No new packages in this quick task |
</threat_model>

<verification>
uv run pytest tests/test_workflows/test_predicted_answer_io.py tests/test_workflows/test_pipeline.py tests/test_workflows/test_claim_pipeline.py -q --tb=short
</verification>

<success_criteria>
- Blind `unlink` on missing preprocess decision is gone
- Analysis-authored predicted_answer survives preprocess re-run / make analyze preprocess step
- Fraud/Benford-only stale predictions still cleared when appropriate
- Single module owns predicted_answer write/remove rules
</success_criteria>

<output>
Create `.planning/quick/260926-bwk-fix-the-stale-prediction-issue-preproces/260926-bwk-SUMMARY.md` when done
</output>
