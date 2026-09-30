---
phase: 260929-fzf-sr-001-repair-preprocessing-import-symbo
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/test_foo.py
  - .gsd/review_backlog.md
autonomous: true
requirements: [SR-001]

estimate:
  tokens: 20000
  raw_tokens: 20000
  tasks: 2
  confidence: low

must_haves:
  truths:
    - "uv run python -c \"import compliance.preprocessing\" succeeds on the working tree and every name in compliance.preprocessing.__all__ resolves"
    - "A snapshot of the git index (the tree the user's next commit will record) imports compliance.preprocessing and collects the non-integration pytest suite with zero collection errors (was: 1 ImportError from tests/test_foo.py)"
    - "vision_ocr_text stays defined in and re-exported from compliance.preprocessing.document; it is NOT moved into signature_detect.py"
    - "signature_detect.py gains no chat-helper imports (it references neither helper; adding them would be unused and fail ruff F401)"
    - "The only git mutation is the staged removal of tests/test_foo.py: HEAD, stash count, and every other index entry and working-tree change are identical to the Step-0 baseline; nothing is committed"
    - "SR-001 is marked resolved in .gsd/review_backlog.md with a note that its first two work bullets were stale"
  artifacts:
    - path: "src/compliance/preprocessing/document.py"
      provides: "Defining module of vision_ocr_text (unchanged)"
      contains: "def vision_ocr_text("
    - path: "src/compliance/preprocessing/__init__.py"
      provides: "Package public exports including vision_ocr_text (unchanged)"
      contains: "\"vision_ocr_text\","
    - path: ".gsd/review_backlog.md"
      provides: "SR-001 resolution record (gitignored, local only)"
      contains: "### [x] SR-001"
  key_links:
    - from: "src/compliance/preprocessing/__init__.py"
      to: "src/compliance/preprocessing/document.py"
      via: "package re-export of vision_ocr_text from its defining module"
      pattern: "from compliance.preprocessing.document import .*vision_ocr_text"
---

<objective>
Close SR-001 (from `.gsd/review_backlog.md`) against the LIVE repository state: fix the one ImportError that still breaks pytest collection, and record that the other SR-001 work bullets are already satisfied instead of inventing changes for them.

Purpose: SR-001 is the P0 release blocker ahead of SR-002/SR-003. The review's premise about where `vision_ocr_text` lives is stale; following it literally would move vision-LLM OCR into the YOLO signature module and add unused imports that fail ruff.
Output: staged removal of the placeholder test `tests/test_foo.py` (no commit), plus an SR-001 resolution note in the gitignored backlog. No source file under `src/` changes.
</objective>

<scope_findings>
Planning-time investigation (2026-09-29, HEAD 87e9c09d288ce2e62b08f83ef10e7824996ef578). Checked on three trees: the working tree, a `git checkout-index` snapshot of the index, and a `git archive HEAD` snapshot.

| SR-001 item | Live state | Action in this plan |
|---|---|---|
| Export/import `vision_ocr_text` from its defining module (the backlog says `signature_detect`) | ALREADY SATISFIED. The backlog premise is wrong. `vision_ocr_text` is defined in `src/compliance/preprocessing/document.py` (~line 66) in all three trees, and `__init__.py` already imports it from `document`. `signature_detect.py` does not define it, and no test or other module imports it from elsewhere. | None. Guard only (Task 2). Do not move it: `signature_detect.py` is YOLO signature scoring, while `vision_ocr_text` is vision-LLM OCR used by `DocumentPreprocessor`. |
| Fix missing `ChatFn` / `response_content` imports in `signature_detect` | ALREADY SATISFIED. `signature_detect.py` references neither name. mypy on `src/compliance/preprocessing/` reports no undefined-name or import errors, and ruff passes. | None. Guard only (Task 2). Adding those imports would be unused and fail ruff F401. |
| `import compliance.preprocessing` and public imports succeed | ALREADY SATISFIED in all three trees. | Guard only (Tasks 1 and 2). |
| Fast pytest collection has no ImportError | STILL BROKEN in the committed and staged trees. `tests/test_foo.py` is the cookiecutter placeholder (`from compliance.foo import foo`), and `compliance.foo` does not exist. The user already deleted it in the working tree (`git status`: ` D tests/test_foo.py`), but the deletion is unstaged. The index and HEAD snapshots therefore fail with "Interrupted: 1 error during collection". The working tree collects 236 tests (233 without integration) cleanly. | Task 1: stage that single deletion. |

Out of scope (SR-002, "Clear mypy + Ruff C901 gate"): mypy reports `union-attr` at `signature_detect.py:155` and `override` at `document.py:792`. Neither is an import or symbol-boundary error. Do not touch them here.
</scope_findings>

<execution_context>
@~/.claude/gsd-core/workflows/execute-plan.md
@~/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@.gsd/review_backlog.md
@src/compliance/preprocessing/__init__.py
@src/compliance/preprocessing/signature_detect.py

## HARD RULES FOR THE EXECUTOR (override the default execute-plan commit protocol)

The user holds a large in-progress set of staged changes: 40 index entries at planning time, `git write-tree` = 33c65323400e6cdd40ad971c6d882e6ff64768f9, stash list empty. Same precedent as quick task 260928-o5k:
- Do NOT run `git commit`, `git add` (any form), `git stash`, `git reset`, `git restore`, `git checkout -- <file>`, or `pre-commit run`. Any commit triggers the installed pre-commit hook, which stashes the user's whole unstaged diff and runs `git checkout -- .` before re-applying it.
- The ONLY permitted index mutation is `git rm --cached --quiet tests/test_foo.py`. The only permitted rollback is `git reset -q HEAD -- tests/test_foo.py`, and only if the Step-0 comparison in Task 1 fails.
- Make no per-task commits and no docs/SUMMARY commit from this plan. The user commits the staged deletion together with their own work.
- Do not edit `src/compliance/preprocessing/__init__.py`, `document.py`, or `signature_detect.py` (see scope_findings). Do not create a `compliance/foo.py` module to satisfy the placeholder test.
- The shell is zsh. Quote every variable expansion.
</context>

<tasks>

<task type="tracer">
  <name>Task 1: Staged tree to package import to fast-lane collection, end-to-end, by staging the placeholder-test removal</name>
  <files>tests/test_foo.py</files>
  <precondition>tests/test_foo.py is absent from the working tree (`test ! -e /Users/theresa/Desktop/projects/compliance/tests/test_foo.py`); if the user has restored it, halt and report rather than deleting it.</precondition>
  <reversibility rating="reversible">Index-only removal of a file the user already deleted from the working tree; undone with a path-limited `git reset -q HEAD -- tests/test_foo.py`.</reversibility>
  <action>
Implements SR-001's "fast pytest collection no longer fails on ImportError" for the tree the user will commit next. From /Users/theresa/Desktop/projects/compliance:

Step 0 (baseline, before any git mutation): make a baseline dir with `mktemp -d` and save its path in a variable. Record `git rev-parse HEAD`, the full `git stash list` output (empty at planning time), and `git write-tree` there. Also record the staged and unstaged name-status lists, filtered to drop lines for `tests/test_foo.py`. Write each raw git output to a file first (`git diff --cached --name-status > "$B/cached.raw"`, `git diff --name-status > "$B/unstaged.raw"`) so a git failure stops the step. Then filter those files with `grep -v 'tests/test_foo.py'`. Never pipe git straight into a filter, because the pipeline would hide git's exit status. Additionally run `git stash create` (it writes an unreferenced stash commit object and does not touch the worktree, index, or stash list). Keep its hash as a recovery reference for the user's tracked changes and record it in the SUMMARY.

Step 1: if `git diff --cached --name-status -- tests/test_foo.py` already prints a `D` line, the user staged it meanwhile: skip to Step 2. Otherwise run exactly `git rm --cached --quiet tests/test_foo.py`. Do not use `git add -u` or `git add -A`: they would sweep the user's other unstaged edits into the index.

Step 2 (baseline comparison): re-capture HEAD, the stash list, and both filtered name-status lists, using the same capture-then-filter method. Diff them against Step 0; they must be byte-identical. `git diff --cached --name-status -- tests/test_foo.py` must now print exactly one line, the `D` status for that path. If anything else differs, run the permitted rollback, stop, and report the diff.

Step 3 (end-to-end proof on the staged tree): export the index to a fresh `mktemp -d` directory with `git checkout-index -a --prefix="$DIR/"` (the trailing slash is required). In that directory, with `PYTHONPATH="$DIR/src"` so the snapshot's sources shadow the editable install, use the project interpreter /Users/theresa/Desktop/projects/compliance/.venv/bin/python to: (a) import `compliance.preprocessing`, then (b) run pytest `--collect-only -q -m "not integration" -p no:cacheprovider`. pytest exits non-zero on any collection error, so the exit status is the gate. Expected: 233 of 236 tests collected, 3 deselected, 0 errors. Also re-run the two working-tree checks (`uv run python -c "import compliance.preprocessing"` and `uv run pytest -m "not integration" --collect-only -q`) as a regression guard.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && test "$(git diff --cached --name-status -- tests/test_foo.py)" = "$(printf 'D\ttests/test_foo.py')" && test "$(git rev-parse HEAD)" = "87e9c09d288ce2e62b08f83ef10e7824996ef578" && STASHES="$(git stash list)" && test -z "$STASHES" && DIR="$(mktemp -d)" && git checkout-index -a --prefix="$DIR/" && (cd "$DIR" && PYTHONPATH="$DIR/src" /Users/theresa/Desktop/projects/compliance/.venv/bin/python -c "import compliance.preprocessing" && PYTHONPATH="$DIR/src" /Users/theresa/Desktop/projects/compliance/.venv/bin/python -m pytest -m "not integration" --collect-only -q -p no:cacheprovider) && uv run python -c "import compliance.preprocessing" && uv run pytest -m "not integration" --collect-only -q</automated>
  </verify>
  <done>The index records the deletion of tests/test_foo.py and nothing else changed: HEAD is 87e9c09d, the stash list is empty, and both filtered name-status lists match Step 0. The index snapshot imports compliance.preprocessing and collects the non-integration suite with 0 errors. The working-tree import and collection still pass. The `git stash create` recovery hash is recorded for the SUMMARY.</done>
</task>

<task type="auto">
  <name>Task 2: Guard the already-satisfied symbol boundary and record the SR-001 resolution in the backlog</name>
  <files>.gsd/review_backlog.md</files>
  <action>
No source edits. This task proves that SR-001 work bullets 1-3 hold on the working tree, then records the outcome. From /Users/theresa/Desktop/projects/compliance:

Guard checks (read-only):
(a) Import the package and run a star-import. Assert that `compliance.preprocessing.vision_ocr_text.__module__` equals `compliance.preprocessing.document` and that every name in `compliance.preprocessing.__all__` resolves as a package attribute.
(b) `uv run ruff check src/compliance/preprocessing/` passes.
(c) `uv run mypy src/compliance/preprocessing/` reports no undefined-name, missing-attribute, or unresolved-import error codes. The two remaining errors (union-attr in signature_detect.py, override in document.py) are expected and belong to SR-002, so do not fix them here.
If any guard fails, the live tree has drifted since planning: stop and report the failing output instead of editing the three preprocessing modules.

Backlog record: `.gsd/review_backlog.md` is gitignored (.gitignore line ~214), so this edit stays local. Do not stage it. Use Edit, not a whole-file Write. Make two scoped changes to the SR-001 section only:
- Flip the heading checkbox so it reads `### [x] SR-001: Repair preprocessing import / symbol boundary ✅`.
- Directly after the `**Files (expected):**` line of SR-001, add a paragraph starting with `**Resolution (2026-09-29, quick 260929-fzf):**`. It must state:
  - Work bullets 1-2 were stale. `vision_ocr_text` is defined in `document.py`, not `signature_detect.py`, and `__init__.py` already re-exports it from there. `signature_detect.py` uses neither chat helper, so no imports were missing.
  - `import compliance.preprocessing` already succeeded.
  - The real collection ImportError came from the tracked cookiecutter placeholder `tests/test_foo.py`, which imports the nonexistent `compliance.foo`. Its removal is now staged for the user's next commit (not committed).
  - The remaining mypy errors in these files are handed to SR-002.

Leave the Task Classification table and every other SR entry untouched.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && uv run python -c "import compliance.preprocessing as p; from compliance.preprocessing import *; assert p.vision_ocr_text.__module__ == 'compliance.preprocessing.document'; missing = [n for n in p.__all__ if not hasattr(p, n)]; assert not missing, missing" && uv run ruff check src/compliance/preprocessing/ && ! (uv run mypy src/compliance/preprocessing/ 2>&1 | grep -Eq '\[(name-defined|attr-defined|import-not-found)\]') && grep -q '^### \[x\] SR-001' .gsd/review_backlog.md && grep -q 'Resolution (2026-09-29, quick 260929-fzf)' .gsd/review_backlog.md && grep -q '^### \[ \] SR-002' .gsd/review_backlog.md</automated>
  </verify>
  <done>vision_ocr_text resolves from compliance.preprocessing.document and every name in __all__ resolves. ruff passes on the preprocessing package. mypy shows no import or symbol-boundary errors there, only the two SR-002 errors. The SR-001 heading is checked and carries the resolution note. SR-002 and later entries are unchanged.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| agent to the user's git index and working tree | The executor acts on a repo holding a large uncommitted, partially staged change set that the user owns |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-fzf-01 | Tampering | git index (user's 40 staged entries) | high | mitigate | Only `git rm --cached --quiet tests/test_foo.py` is allowed. `git add` in any form is forbidden. Task 1 Step 2 byte-compares the filtered staged and unstaged name-status lists, HEAD, and the stash count against Step 0, with a path-limited rollback on mismatch. |
| T-fzf-02 | Denial of Service (data loss) | user's uncommitted working-tree changes | high | mitigate | No commit is made, so the pre-commit hook's stash plus `checkout -- .` cycle never runs. `git stash create` records a recovery commit for tracked changes without modifying the worktree, index, or stash list. |
| T-fzf-03 | Tampering | src/compliance/preprocessing symbol boundary | medium | mitigate | Following the stale backlog premise (moving vision_ocr_text, adding unused imports) is explicitly forbidden. Task 2 guards assert the defining module and ruff/mypy cleanliness. |
| T-fzf-04 | Information Disclosure | SUMMARY / backlog text | low | accept | The only content written is file paths, commit hashes, and error codes. No secrets, tokens, or PII are involved. |
</threat_model>

<verification>
1. Staged tree: `git checkout-index` snapshot imports compliance.preprocessing and collects `-m "not integration"` with 0 errors (planning baseline: 1 ImportError from tests/test_foo.py).
2. Working tree: `uv run python -c "import compliance.preprocessing"` and `uv run pytest -m "not integration" --collect-only -q` both exit 0.
3. Symbol boundary: vision_ocr_text.__module__ is compliance.preprocessing.document; every name in __all__ resolves; ruff is clean on src/compliance/preprocessing/; mypy shows no undefined-name or import errors there.
4. Git: HEAD unchanged (87e9c09d), stash list empty, no commit created, index differs from Step 0 only by the D line for tests/test_foo.py, and unstaged changes are otherwise identical.
5. No diff against planning-time content in src/compliance/preprocessing/__init__.py, document.py, or signature_detect.py from this plan.
</verification>

<success_criteria>
- SR-001 done-when is met for the tree the user will commit: the package imports and fast collection has no ImportError.
- The three already-satisfied SR-001 bullets are documented as such (plan scope_findings, SUMMARY, backlog resolution note), not "fixed" with invented changes.
- The user's in-progress git state is preserved except for the single intended staged deletion, and nothing is committed.
</success_criteria>

<output>
Create `/Users/theresa/Desktop/projects/compliance/.planning/quick/260929-fzf-sr-001-repair-preprocessing-import-symbo/260929-fzf-SUMMARY.md` when done. Do NOT commit or stage it. Include:
- The scope_findings table outcome, with each bullet marked already-satisfied or fixed.
- Step-0 vs final values: HEAD, stash count, `git write-tree` (expected to change only through the test_foo removal), and the filtered name-status comparison result.
- The `git stash create` recovery hash.
- Collection results for the index snapshot and the working tree (collected, deselected, and error counts).
- A user handoff: the deletion of tests/test_foo.py is staged and lands with the user's next commit. HEAD itself still contains the placeholder until then, so a clean checkout of 87e9c09d still fails collection.
- Out-of-scope follow-ups: the mypy union-attr (signature_detect.py:155) and override (document.py:792) errors go to SR-002.
</output>
