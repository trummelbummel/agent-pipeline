---
phase: 260929-gux-sr-002-clear-mypy-and-ruff-c901-gate
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - pyproject.toml
  - src/compliance/preprocessing/signature_detect.py
  - src/compliance/preprocessing/document.py
  - src/compliance/workflows/claim_pipeline.py
  - .gsd/review_backlog.md
autonomous: true
requirements: [SR-002]

estimate:
  tokens: 25000
  raw_tokens: 25000
  tasks: 3
  confidence: low

must_haves:
  truths:
    - "`uv run mypy` prints `Success: no issues found in 43 source files`. Before this plan it reported 6 errors in 4 files."
    - "`uv run ruff check --no-fix src tests` passes. C901 stays enabled through the `C90` selector, and pyproject.toml now sets the threshold explicitly to `max-complexity = 10`, the same value as Ruff's default, so no function newly fails."
    - "`uv run pytest -m \"not integration\" -q --deselect tests/test_config/test_settings.py::test_analysis_coverage_other_label_is_false` shows 247 passed, the same count as the planning-time baseline."
    - "No new dependency is added: uv.lock is byte-identical to HEAD. The scipy stub gap is closed with a scoped mypy override instead of a new stubs package."
    - "No inline mypy suppression comments are added under src/. Every source fix narrows or re-signs the code."
    - "Runtime behavior does not change. OCR-failure precedence stays ocr_read_failure over ocr_failure. Classifier-False detection reads the same two label lists. The HITL log reason is still `classifier_false`, the decision explanation, or `uncertain`. Every DocumentReader call site still passes source_file explicitly."
    - "Exactly one new commit exists. Its subject starts with `fix(SR-002):` and it contains exactly pyproject.toml plus the 3 src files. The pre-existing working-tree edits to .planning/STATE.md and .planning/config.json stay unstaged."
  artifacts:
    - path: "pyproject.toml"
      provides: "Scoped scipy mypy override and explicit mccabe threshold"
      contains: "max-complexity = 10"
    - path: "src/compliance/preprocessing/signature_detect.py"
      provides: "YOLO results narrowed to ultralytics Results before .boxes access"
      contains: "isinstance(result, Results)"
    - path: "src/compliance/preprocessing/document.py"
      provides: "LSP-compatible DocumentReader._to_model override"
      contains: "source_file: str = \"\""
    - path: "src/compliance/workflows/claim_pipeline.py"
      provides: "Typed OCR-failure / classifier-False narrowing and extracted HITL-reason helper"
      contains: "def _human_in_the_loop_reason("
  key_links:
    - from: "src/compliance/preprocessing/document.py"
      to: "src/compliance/preprocessing/reader.py"
      via: "DocumentReader._to_model overrides abstract Reader._to_model(processed)"
      pattern: "def _to_model\\(self, processed: Any, \\*, source_file: str = \"\"\\)"
    - from: "src/compliance/workflows/claim_pipeline.py::_persist_human_in_the_loop_metadata"
      to: "src/compliance/branch_log.py::log_branch_decision"
      via: "reason: str produced by _human_in_the_loop_reason"
      pattern: "reason = self\\._human_in_the_loop_reason\\(state\\)"
---

<objective>
Close SR-002 from `.gsd/review_backlog.md`. The goal is a green mypy gate and a confirmed Ruff C901 gate, with no change in behavior.

Purpose: SR-002 is the P0 build gate between SR-001 (done) and SR-003. mypy is red with 6 errors. C901 already passes, and this plan pins its threshold explicitly so the gate is visible in the config instead of relying on Ruff's implicit default.
Output: one commit `fix(SR-002): ...` touching pyproject.toml, signature_detect.py, document.py and claim_pipeline.py, plus an SR-002 resolution note in the gitignored backlog.
</objective>

<scope_findings>
Planning-time investigation (2026-09-29, HEAD 6f287eb). Each fix below was applied to a scratch copy of `src/` and checked there. With all fixes applied, mypy reported `Success: no issues found in 43 source files`, `ruff check` passed, and the non-integration pytest suite passed. The only format drift was a single long line in claim_pipeline.py, which `ruff format` wraps.

| Gate item | Live state | Fix (behavior-preserving because...) |
|---|---|---|
| Ruff C901 | ALREADY PASSING. `C90` is in `[tool.ruff.lint] select`. No `[tool.ruff.lint.mccabe]` table exists, so the Ruff default of 10 applies. `uv run ruff check --select C901 src` shows "All checks passed". No noqa C901 markers exist in src/. | Pin `max-complexity = 10` (Task 1). This equals the default, so nothing newly fails. No claim_pipeline refactor is needed for C901. The one helper extracted in Task 2 exists for the typing fix and CLAUDE.md structure, not for complexity. |
| mypy `tools/benford.py:9` import-untyped `scipy.fft` | scipy 1.18.1 ships without stubs, and `dctn` is used once (line ~112). | A `[[tool.mypy.overrides]]` for `scipy.*` with `ignore_missing_imports = true`, verified in a scratch config with zero new errors. Chosen over adding `scipy-stubs` because it adds no dependency or supply-chain surface, needs no package-legitimacy checkpoint, avoids the lock/Python-3.10 resolution risk against `requires-python >=3.10`, and has one call site. Do NOT edit benford.py. It is not ruff-formatted, so staging it would make the pre-commit ruff-format hook rewrite it and fail the commit. |
| mypy `signature_detect.py:155` union-attr `.boxes` on `Results \| Tensor` | Ultralytics types `predict()` as `Iterator[Results \| Tensor] \| list[Results] \| list[Tensor]`. Tensor only appears in embed mode, which is never used here. | Import `Results` lazily next to `YOLO` inside the existing ImportError guard. Narrow with `isinstance`, treating a non-Results item like "no boxes". Real predict output is always Results, so the scores are identical. |
| mypy `document.py:792` override: `_to_model(self, processed, *, source_file: str)` vs `Reader._to_model(self, processed)` | DocumentReader overrides `read()` wholesale. Both internal call sites (~292, ~420) pass `source_file=` explicitly. AnswerReader, DescriptionReader and MarkdownReader match the base signature. No tests call `_to_model`. | Give the keyword-only param a default `source_file: str = ""`. That makes it a Liskov-compatible override, and the call sites don't change. The empty string follows the module's existing "unknown source" convention (line ~695 `source_file or document.metadata.source_file`). |
| mypy `claim_pipeline.py:513` operator `in` on `object` | `_document_metadata_entries` returns `list[dict[str, object]]` (a JSON file boundary). `failure_reasons` is always written as `list[str]` by `DocumentMetaData`. | Narrow `failure_reasons` with `isinstance(..., list)` at this boundary. A non-list value contributes no codes, the same as today's missing/None to `[]` path. Keep the precedence ocr_read_failure first, then ocr_failure, else None. |
| mypy `claim_pipeline.py:535` operator `in` on `object` | `state.get(key)` with a loop-variable key on a TypedDict returns `object`. | Read the two literal keys directly (`state.get("reason_labels") or []`, `state.get("document_labels") or []`), which gives `list[str]` and the same semantics. |
| mypy `claim_pipeline.py:572` assignment `str \| float` into `str` | `GroundTruth.explanation` is `NanStr` (`str \| float`). All 7 return branches of `_decision_from_state` set a non-empty str explanation. | Extract the private helper `_human_in_the_loop_reason(state) -> str`. Narrow with `isinstance(explanation, str) and explanation`, which mirrors the existing patterns at claim_pipeline.py ~903 and evaluation/analysis_stats.py ~240. The output matches for every reachable state. |

Baseline: `uv run pytest -m "not integration" -q --deselect tests/test_config/test_settings.py::test_analysis_coverage_other_label_is_false` gave 247 passed, 4 deselected. The deselected test is a known unrelated pre-existing failure and must be ignored. Pre-commit runs ruff-check (`--exit-non-zero-on-fix`), ruff-format, check-toml, end-of-file-fixer and trailing-whitespace. It does not run mypy.
</scope_findings>

<execution_context>
@~/.claude/gsd-core/workflows/execute-plan.md
@~/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@.gsd/review_backlog.md
@pyproject.toml
@src/compliance/preprocessing/reader.py
@src/compliance/preprocessing/signature_detect.py
@src/compliance/models/claim.py
</context>

<tasks>

<task type="tracer">
  <name>Task 1: Wire the gate end-to-end through config (scipy mypy override and explicit C901 threshold)</name>
  <files>pyproject.toml</files>
  <read_first>pyproject.toml (the `[tool.mypy]` and `[tool.ruff.lint]` tables)</read_first>
  <action>
Do NOT commit in this task. SR-002 ships as one commit in Task 3.

1. Directly after the `[tool.mypy]` table (before `[tool.pytest.ini_options]`), add a `[[tool.mypy.overrides]]` table with `module = ["scipy.*"]` and `ignore_missing_imports = true`. The `scipy.*` pattern covers `scipy` and every submodule, including `scipy.fft`. Do not add a stubs package (see scope_findings). Leave `src/compliance/tools/benford.py` untouched.
2. Add a `[tool.ruff.lint.mccabe]` table with `max-complexity = 10`. Place it after `[tool.ruff.lint.per-file-ignores]` and before `[tool.ruff.format]`. The value equals Ruff's default, so it makes the C901 gate explicit without changing which functions pass. Keep `C90` in `select`.
3. Run `uv run mypy` and confirm the benford import-untyped error is gone and exactly 5 errors remain (signature_detect, document, and claim_pipeline ×3). Run the C901 check.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && uv run mypy 2>&1 | tail -1 && uv run mypy 2>&1 | grep -c "tools/benford.py" ; uv run ruff check --no-fix --select C901 src tests && grep -n "max-complexity = 10" pyproject.toml && git diff --quiet HEAD -- uv.lock src/compliance/tools/benford.py && echo "lock+benford untouched"</automated>
  </verify>
  <acceptance_criteria>
    - `uv run mypy` last line is `Found 5 errors in 3 files (checked 43 source files)`
    - `uv run mypy 2>&1 | grep -c "tools/benford.py"` prints `0`
    - `uv run ruff check --no-fix --select C901 src tests` prints `All checks passed!`
    - `grep -n "max-complexity = 10" pyproject.toml` finds one line and `grep -n 'module = \["scipy.\*"\]' pyproject.toml` finds one line
    - `git diff --quiet HEAD -- uv.lock src/compliance/tools/benford.py` exits 0
  </acceptance_criteria>
  <done>Config is the only change. The scipy error is cleared, the C901 threshold is explicit at 10, no dependency or lockfile change is made, and nothing is committed yet.</done>
</task>

<task type="auto">
  <name>Task 2: Clear the 5 remaining mypy errors with real narrowing and signatures (no behavior change)</name>
  <files>src/compliance/preprocessing/signature_detect.py, src/compliance/preprocessing/document.py, src/compliance/workflows/claim_pipeline.py</files>
  <read_first>src/compliance/preprocessing/signature_detect.py (`detect_signature_with_yolo`, ~lines 117-165), src/compliance/preprocessing/document.py (`_to_model`, ~line 792, and its callers ~292 and ~420), src/compliance/workflows/claim_pipeline.py (`_document_ocr_failure` ~500-520, `_classifier_returned_false` ~521-535, `_persist_human_in_the_loop_metadata` ~552-580, `_document_metadata_entries` ~582)</read_first>
  <action>
Do NOT commit in this task. Fix every error with narrowing or a correct signature. Do not add any inline mypy suppression comment or noqa. Keep `from __future__ import annotations` and the existing docstring style (`:param:` / `:return:`, explaining purpose).

A. signature_detect.py, in `detect_signature_with_yolo`:
- Inside the existing ImportError try block, next to the lazy `from ultralytics import YOLO`, add `from ultralytics.engine.results import Results`. It stays lazy and maps to SignatureDependencyError like YOLO.
- In the scoring loop, replace the bare `result.boxes` read with `boxes = result.boxes if isinstance(result, Results) else None`. The existing `if boxes is None or len(boxes) == 0: continue` guard then treats a Tensor item as "no boxes".
- Leave everything else unchanged.

B. document.py, `DocumentReader._to_model`:
- Change the signature to `def _to_model(self, processed: Any, *, source_file: str = "") -> BaseModel:` so it is an LSP-compatible override of `Reader._to_model(self, processed)`.
- Update the `:param source_file:` docstring line so it says empty means the source basename is unknown (the base `Reader.read` contract passes none).
- Do not touch the two call sites. They already pass `source_file=` explicitly.
- Do not change `Reader` or the other readers.

C. claim_pipeline.py:
1. `_document_ocr_failure`: for each metadata entry, read `failure_reasons` via `entry.get("failure_reasons")`. Treat it as a list only when `isinstance(reasons, list)`. This is the JSON file boundary, and `DocumentMetaData` always writes `list[str]`. Accumulate those codes into a `found` set, then return the first code in the precedence tuple (`"ocr_read_failure"`, `"ocr_failure"`) that is in `found`, else None. A `next(...)` over the tuple is fine. Keep the return type `str | None` and keep the docstring.
2. `_classifier_returned_false`: replace the generator that loops over the key tuple with `state.get(key)` with reads of the two literal TypedDict keys. The result is `any("False" in labels for labels in (state.get("reason_labels") or [], state.get("document_labels") or []))`, which has the same semantics and precise `list[str]` types. Keep the routed-coverage check and the docstring.
3. Extract a private helper `_human_in_the_loop_reason(self, state: ClaimAnalysisState) -> str`, placed directly after `_persist_human_in_the_loop_metadata`. It returns `"classifier_false"` when `self._classifier_returned_false(state)` is true. Otherwise it reads `self._decision_from_state(state).explanation` and returns it when `isinstance(explanation, str) and explanation`, else `"uncertain"`. This mirrors the narrowing already used at claim_pipeline.py ~903.
   - Give it a docstring with `:param state:` and `:return:` explaining that it produces the log reason for the HITL flag.
   - In `_persist_human_in_the_loop_metadata`, replace the three-line reason computation with `reason = self._human_in_the_loop_reason(state)`. Leave the metadata write and the `log_branch_decision` call unchanged.

After editing, run `uv run ruff format` on the three files. It wraps the `_classifier_returned_false` return line at 120 chars. Then run `uv run ruff check` on them. This keeps the pre-commit ruff hooks from rewriting files at commit time.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && uv run ruff format src/compliance/preprocessing/signature_detect.py src/compliance/preprocessing/document.py src/compliance/workflows/claim_pipeline.py && uv run mypy && uv run ruff check --no-fix src tests && uv run pytest -m "not integration" -q tests/test_workflows/test_claim_pipeline.py tests/test_preprocessing</automated>
  </verify>
  <acceptance_criteria>
    - `uv run mypy` prints `Success: no issues found in 43 source files`
    - `grep -rn "type: ignore" src/ | wc -l` prints `0`
    - `grep -n "isinstance(result, Results)" src/compliance/preprocessing/signature_detect.py` finds one line
    - `grep -n 'def _to_model(self, processed: Any, \*, source_file: str = "") -> BaseModel:' src/compliance/preprocessing/document.py` finds one line
    - `grep -n "def _human_in_the_loop_reason(" src/compliance/workflows/claim_pipeline.py` finds one line, and `grep -n "reason = self._human_in_the_loop_reason(state)" src/compliance/workflows/claim_pipeline.py` finds one line
    - `grep -n 'state.get(key)' src/compliance/workflows/claim_pipeline.py | wc -l` prints `0`
    - `uv run ruff format --check src/compliance/preprocessing/signature_detect.py src/compliance/preprocessing/document.py src/compliance/workflows/claim_pipeline.py` reports all 3 files already formatted
    - The targeted claim_pipeline and preprocessing unit tests pass
  </acceptance_criteria>
  <done>mypy is green across 43 source files. The three source files are ruff-clean and formatted. Behavior is unchanged per the scope_findings reasoning, and nothing is committed yet.</done>
</task>

<task type="auto">
  <name>Task 3: Full gate run, single fix(SR-002) commit, and backlog resolution note</name>
  <files>.gsd/review_backlog.md</files>
  <read_first>.gsd/review_backlog.md (the `### [ ] SR-002` section, ~line 56, and the already-resolved `### [x] SR-001` section for format)</read_first>
  <action>
1. Run the full gate from the repo root:
   - `uv run mypy` (expect Success)
   - `uv run ruff check --no-fix src tests`
   - `uv run ruff check --no-fix --select C901 src tests`
   - `uv run pytest -m "not integration" -q --deselect tests/test_config/test_settings.py::test_analysis_coverage_other_label_is_false` (expect 247 passed)
   Ignore that pre-existing test_settings failure. It is unrelated to SR-002. If any other test fails, stop and report it; do not "fix" tests.
2. Stage exactly these four files: pyproject.toml, src/compliance/preprocessing/signature_detect.py, src/compliance/preprocessing/document.py, src/compliance/workflows/claim_pipeline.py.
   - Do not stage .planning/STATE.md, .planning/config.json, or any untracked path. Those are pre-existing user changes.
   - Create ONE commit with subject `fix(SR-002): clear mypy gate and pin ruff C901 threshold`. Let the body briefly list the scipy override, the Results narrowing, the `_to_model` LSP default, and the claim_pipeline narrowing plus `_human_in_the_loop_reason` helper. End the body with the `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` trailer.
   - Let the pre-commit hooks run normally; never bypass them. If a hook rewrites a file, re-run `uv run ruff format`/`uv run ruff check` on the staged files, re-stage those same four files, and create the commit again (a new commit, not an amend of an earlier one).
3. After the commit, edit the gitignored `.gsd/review_backlog.md`. It is local only and must not be committed.
   - Flip `### [ ] SR-002: Clear mypy + Ruff C901 gate` to `### [x] SR-002: Clear mypy + Ruff C901 gate`.
   - Add a short resolution note under its Done-when block. The note should say mypy went from 6 errors to 0, the C901 gate was already green with the threshold now pinned at 10, scipy was handled through a mypy override rather than a stubs dependency, and the backlog's "~16 errors" count was stale. Include the new commit short SHA.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && uv run mypy && uv run ruff check --no-fix src tests && uv run pytest -m "not integration" -q --deselect tests/test_config/test_settings.py::test_analysis_coverage_other_label_is_false && SUBJ=$(git log -1 --format=%s) && echo "$SUBJ" | grep -E '^fix\(SR-002\):' && FILES=$(git show --name-only --format= HEAD) && echo "$FILES" | sort && git rev-list --count 6f287eb..HEAD && grep -n "### \[x\] SR-002" .gsd/review_backlog.md</automated>
  </verify>
  <acceptance_criteria>
    - mypy prints Success, ruff check passes, and pytest shows `247 passed` with the one pre-existing deselect (plus the integration deselects)
    - `git log -1 --format=%s` starts with `fix(SR-002):`
    - `git show --name-only --format= HEAD` lists exactly pyproject.toml, src/compliance/preprocessing/document.py, src/compliance/preprocessing/signature_detect.py, src/compliance/workflows/claim_pipeline.py
    - `git rev-list --count 6f287eb..HEAD` prints `1`
    - `git status --short .planning/STATE.md .planning/config.json` still shows both as ` M` (unstaged, uncommitted)
    - `grep -n "### \[x\] SR-002" .gsd/review_backlog.md` finds one line, and `git check-ignore .gsd/review_backlog.md` confirms it is ignored
  </acceptance_criteria>
  <done>Gates are green and SR-002 is shipped as one hook-checked commit containing only the 4 intended files. SR-002 is marked resolved in the local backlog.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| disk JSON to pipeline | `document_metadata.json` is read back from the preprocessed claim folder. `failure_reasons` crosses as untyped JSON. |
| dependency supply chain | Closing the scipy typing gap could have pulled in a new stubs package. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-SR002-01 | Tampering | `ClaimPipeline._document_ocr_failure` reading `failure_reasons` | low | mitigate | `isinstance(reasons, list)` narrowing at the JSON boundary. A malformed non-list value can no longer substring-match an OCR-failure code; it contributes no codes. |
| T-SR002-02 | Information disclosure | `_human_in_the_loop_reason` feeding `log_branch_decision(reason=...)` | low | accept | The reason is a decision code (`classifier_false`, checker explanation codes, `uncertain`) and never free text or PII. The existing branch_log key allowlist is unchanged. |
| T-SR002-SC | Tampering | npm/pip/cargo installs | low | mitigate | No package install. The scipy stub gap is closed with a scoped `[[tool.mypy.overrides]]` for `scipy.*`, and uv.lock must stay byte-identical to HEAD (Task 1 acceptance). |
</threat_model>

<verification>
- `uv run mypy` prints `Success: no issues found in 43 source files`
- `uv run ruff check --no-fix src tests` and `uv run ruff check --no-fix --select C901 src tests` both pass, with `max-complexity = 10` explicit in pyproject.toml
- `uv run pytest -m "not integration" -q --deselect tests/test_config/test_settings.py::test_analysis_coverage_other_label_is_false` shows 247 passed
- One new commit `fix(SR-002): ...` with exactly 4 files. uv.lock and benford.py are unchanged, and there are no inline mypy suppressions in src/
</verification>

<success_criteria>
- The SR-002 done-when is met: the mypy and Ruff complexity gates pass and the existing unit tests stay green (247 passed).
- All fixes are real typing (isinstance narrowing, an LSP-compatible signature, literal TypedDict keys). The only config-level accommodation is the scoped third-party scipy override.
- No runtime behavior change, and a single hook-checked commit.
</success_criteria>

<output>
Create `.planning/quick/260929-gux-sr-002-clear-mypy-and-ruff-c901-gate/260929-gux-SUMMARY.md` when done
</output>
