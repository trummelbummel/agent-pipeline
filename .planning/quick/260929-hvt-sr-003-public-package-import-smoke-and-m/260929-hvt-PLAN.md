---
phase: 260929-hvt-sr-003-public-package-import-smoke-and-m
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/test_public_imports.py
  - Makefile
  - README.md
  - .gsd/review_backlog.md
autonomous: true
requirements: [SR-003]

estimate:
  tokens: 22000
  raw_tokens: 22000
  tasks: 2
  confidence: low

must_haves:
  truths:
    - "`uv run python -m pytest tests/test_public_imports.py -q` reports `41 passed`. That is one case per public module: every module under the `api`, `compliance` and `evaluation` packages except `__main__` modules, plus the `main` entrypoint (src/main.py)."
    - "A broken public import makes the smoke test fail. Temporary mutations proved all three cases at plan time: an unresolvable `from X import Y` in a leaf module gives exit 1 (FAILED on the module), the same break inside a subpackage gives exit 2 (collection error, because walk errors are re-raised rather than skipped), and a phantom `__all__` entry gives exit 1."
    - "The smoke test never imports a `__main__` module and writes nothing under data/. `compliance.workflows.__main__` calls `main()` at import time, which runs the full preprocessing CLI over data/raw."
    - "`make test` is the fast lane. It runs `pytest --doctest-modules -m \"not integration\"`, so the 3 `integration`-marked tests are deselected. The only failure is the known pre-existing `test_analysis_coverage_other_label_is_false`, and the summary reads `1 failed, 288 passed, 3 deselected` (247 baseline + 41 smoke)."
    - "`make test-integration` is the explicit opt-in lane (`pytest -m integration`). Collection selects exactly the 3 integration tests. It is not executed during this plan."
    - "README `## Tests & quality` documents `make test` as the default fast lane and `make test-integration` as opt-in."
    - "Exactly one new commit exists on top of 05eace3. Its subject starts with `test(SR-003):` and it contains exactly tests/test_public_imports.py, Makefile and README.md. SR-012 files (.github/workflows/main.yml, tox.ini, pyproject.toml) are unchanged. .planning/STATE.md and .planning/config.json stay unstaged ` M`."
  artifacts:
    - path: "tests/test_public_imports.py"
      provides: "Parametrized import smoke over every public module, plus `__all__` resolution"
      contains: "def test_public_module_imports("
    - path: "Makefile"
      provides: "Fast-lane `test` target and opt-in `test-integration` target"
      contains: "test-integration:"
    - path: "README.md"
      provides: "Tests & quality section documenting both lanes"
      contains: "make test-integration"
  key_links:
    - from: "Makefile::test"
      to: "tests/test_public_imports.py"
      via: "pytest testpaths=[\"tests\"] collects the smoke module; the marker expression deselects integration only"
      pattern: "-m \"not integration\""
    - from: "tests/test_public_imports.py::PUBLIC_PACKAGES"
      to: "pyproject.toml [tool.hatch.build.targets.wheel] packages"
      via: "Same three top-level packages the wheel ships (src/compliance, src/evaluation, src/api)"
      pattern: "PUBLIC_PACKAGES"
    - from: "tests/test_public_imports.py::ENTRYPOINT_MODULES"
      to: "src/main.py (wheel force-include; `compliance-preprocess = main:main`)"
      via: "pytest pythonpath [\"src\", \"tests\"] makes `main` importable"
      pattern: "ENTRYPOINT_MODULES"
---

<objective>
Close SR-003 from `.gsd/review_backlog.md`. That means an import-smoke test over every public package, and a mandatory fast lane that is the default local check.

Purpose: SR-001 shipped because nothing imported `compliance.preprocessing` end-to-end. A parametrized smoke test makes any broken public import, or any `__all__` entry that does not resolve, a hard test failure. Making `make test` run the non-integration lane gives developers one fast, deterministic default check (about 4s) that includes the smoke test.

Output: one commit `test(SR-003): ...` touching tests/test_public_imports.py, Makefile and README.md, plus a local resolution note in the gitignored backlog.

Scope boundary (hard): SR-012 owns CI fast-lane ordering (.github/workflows/main.yml), pytest-cov install and threshold, tox `--cov`, and isolating provisioned integration tests. Do NOT touch .github/, tox.ini, pyproject.toml or uv.lock. Do NOT add a pytest `addopts` marker default in pyproject.toml. That would silently change what tox and CI run, which is SR-012's decision. The fast-lane default lives in the Makefile only.

Task classification (classify-tasks rules): Task 1 simple, Task 2 simple. No high-weight signals apply: a new test file, the Makefile and the README have no import coupling, and every behavior is concrete. No human pause is needed.
</objective>

<execution_context>
@~/.claude/gsd-core/workflows/execute-plan.md
@~/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/STATE.md
@Makefile
@pyproject.toml

Planning-time facts (HEAD 05eace3). Do not re-derive these:
- Public packages are exactly `api`, `compliance` and `evaluation`, matching `[tool.hatch.build.targets.wheel] packages`. `src/main.py` is force-included in the wheel and backs the `compliance-preprocess = "main:main"` script.
- Walking those packages yields 37 submodules, excluding the two `__main__` modules (`compliance.workflows.__main__` and `evaluation.__main__`). With the 3 top-level packages and `main`, that is 41 importable public modules. Importing all of them takes about 3.4s.
- DANGER: `src/compliance/workflows/__main__.py` is `from main import main` followed by `raise SystemExit(main())`, with no `__name__` guard. Importing it runs the full preprocessing CLI over data/raw. During planning, one accidental import rewrote 108 files under data/preprocessed and 3 predicted_answer.json files under data/results. data/ is untracked, so git cannot restore it. The smoke test MUST NOT import any `*.__main__` module.
- `pkgutil.walk_packages` imports subpackages so it can recurse. When no `onerror` is given it silently skips subpackages whose import raises ImportError, which gives a false green. It calls `onerror(name)` from inside its `except` block, so a bare `raise` in the callback re-raises the original exception.
- pytest config: `testpaths = ["tests"]`, `pythonpath = ["src", "tests"]`, and the marker `integration`. Exactly 3 tests carry it, all in tests/test_preprocessing/test_integration.py.
- Current fast lane (`pytest -m "not integration"`): `1 failed, 247 passed, 3 deselected` in about 4s. The failure is pre-existing (tests/test_config/test_settings.py::test_analysis_coverage_other_label_is_false). Ignore it and do not fix it.
- Ruff runs on tests/ through pre-commit (`ruff-check --exit-non-zero-on-fix`, `ruff-format`). S101 is ignored for `tests/*`. ARG rules are NOT selected, so any lint-suppression comment for the unused `onerror` parameter is flagged by RUF100 as unused. Do not add one. mypy only checks src/.
- The environment variable `PYTHON` is unset. Even so, the Makefile test targets keep using the literal `$(UV) run python -m pytest` exactly as today, so a shell-exported `PYTHON` can never redirect pytest outside the uv env.
</context>

<tasks>

<task type="tracer">
  <name>Task 1: Public-module import smoke test wired into the `make test` fast lane</name>
  <files>tests/test_public_imports.py, Makefile</files>
  <read_first>Makefile (the `test:` target near the "Existing quality / build targets" banner, and the `.PHONY` list at the top); pyproject.toml (`[tool.hatch.build.targets.wheel]` and `[tool.pytest.ini_options]`); src/compliance/workflows/__main__.py (the unguarded import-time CLI call)</read_first>
  <action>
Build the thinnest end-to-end path: a smoke module that pytest collects, run by the default `make test` lane, with integration deselected.

1. Create tests/test_public_imports.py. It starts with `from __future__ import annotations` and imports only `importlib`, `pkgutil` and `pytest`. Use no mocks, fakes or monkeypatching. It must import the real packages, per the CLAUDE.md testing rules.
   - `PUBLIC_PACKAGES: tuple[str, ...] = ("api", "compliance", "evaluation")`. Add a one-line WHY comment saying it mirrors the wheel packages in pyproject.toml.
   - `ENTRYPOINT_MODULES: tuple[str, ...] = ("main",)`. Add a one-line WHY comment saying it is the force-included src/main.py behind the `compliance-preprocess` script.
   - Add a private `_reraise_walk_error(name: str) -> None` whose body is a bare `raise`. Give it a WHY comment explaining that `pkgutil.walk_packages` invokes `onerror` inside its except block and otherwise silently skips subpackages that fail with ImportError, and that re-raising turns a broken subpackage into a hard collection error. Add no lint-suppression comment, because ARG rules are not selected.
   - Add a private `_public_module_names() -> list[str]` with a short docstring and a `:return:` line. It collects `ENTRYPOINT_MODULES`. For each name in `PUBLIC_PACKAGES` it adds the package name itself, then every `info.name` from `pkgutil.walk_packages(package.__path__, prefix=f"{package_name}.", onerror=_reraise_walk_error)` except names ending in `.__main__`. It returns the result sorted so parametrize IDs are deterministic. Put a WHY comment on the `.__main__` filter: `compliance.workflows.__main__` runs the full preprocessing CLI at import time and overwrites data/preprocessed.
   - Add `test_public_module_imports(module_name: str) -> None`, decorated with `@pytest.mark.parametrize("module_name", _public_module_names())`. Give it a docstring with a `:param module_name:` line explaining that it is a dotted public module path whose import and `__all__` exports must resolve. The body calls `importlib.import_module(module_name)` and then asserts that the list of names in `getattr(module, "__all__", ())` for which `hasattr(module, name)` is False equals `[]`. That catches SR-001-style phantom exports that a plain import would miss.
   - Keep it to exactly these three functions and two constants, and do not add a filesystem walker. Build no paths from `__file__` or the cwd, per the CLAUDE.md Paths rule. Enumeration comes from the imported packages' `__path__`.

2. Edit the Makefile `test:` target so it becomes the fast lane. Keep the target name. Change the help text after `##` to: Fast lane (default local/merge check): unit tests + public-package import smoke; deselects integration. Change the echo to: 🚀 Testing code: Running pytest fast lane (not integration). The command becomes `@$(UV) run python -m pytest --doctest-modules -m "not integration"`. Keep `--doctest-modules` and keep `$(UV) run python`, as noted in context. Do not touch any other target in this task.

3. Run `uv run ruff format tests/test_public_imports.py` and `uv run ruff check --no-fix tests/test_public_imports.py`.

4. Negative proof (required; do not skip). Temporarily break imports in three ways and confirm the smoke test fails each time, restoring after each with `git checkout -- <file>`. This is exactly what the automated verify below runs.
   - (a) Append a line importing a non-existent name from `compliance.models` to src/evaluation/analysis_stats.py. That module is a leaf reachable only through evaluation.visualization and the excluded `__main__`. Expect exit 1.
   - (b) Make the same append to src/compliance/tools/benford.py, which is inside a subpackage. Expect exit 2, a collection error from the re-raised walk.
   - (c) Add a phantom string to `__all__` in src/compliance/tools/__init__.py. Expect exit 1 from the `__all__` assertion.
   - Afterwards, `git diff --quiet -- src` must succeed. Never leave a mutation in the tree, and never stage src/.

Do NOT commit in this task. The single SR-003 commit happens in Task 2.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && M=$(mktemp) && OUT=$(uv run python -m pytest tests/test_public_imports.py -q -p no:cacheprovider) && echo "$OUT" | tail -1 && echo "data writes: $(find data -type f -newer "$M" | wc -l | tr -d ' ')" && echo "__main__ ids: $(uv run python -m pytest tests/test_public_imports.py --collect-only -q -p no:cacheprovider | grep -c '__main__')" && uv run ruff check --no-fix tests/test_public_imports.py && uv run ruff format --check tests/test_public_imports.py && (make test > "$M.log" 2>&1; echo "unexpected FAILED: $(grep -E '^FAILED' "$M.log" | grep -vc 'test_analysis_coverage_other_label_is_false')"; tail -1 "$M.log")</automated>
    <automated>cd /Users/theresa/Desktop/projects/compliance && smoke() { uv run python -m pytest tests/test_public_imports.py -q -p no:cacheprovider >/dev/null 2>&1; } && printf '\nfrom compliance.models import SR003_MISSING_SYMBOL\n' >> src/evaluation/analysis_stats.py && { smoke; A=$?; git checkout -- src/evaluation/analysis_stats.py; } && printf '\nfrom compliance.models import SR003_MISSING_SYMBOL\n' >> src/compliance/tools/benford.py && { smoke; B=$?; git checkout -- src/compliance/tools/benford.py; } && sed -i '' 's/"BenfordResult",/"BenfordResult", "SR003Phantom",/' src/compliance/tools/__init__.py && { smoke; C=$?; git checkout -- src/compliance/tools/__init__.py; } && echo "rc leaf=$A subpkg=$B all=$C" && git diff --quiet -- src && test "$A" -ne 0 && test "$B" -ne 0 && test "$C" -ne 0 && echo "mutation proof OK"</automated>
  </verify>
  <acceptance_criteria>
    - The smoke run prints `41 passed`
    - `data writes: 0` and `__main__ ids: 0`
    - `ruff check --no-fix` and `ruff format --check` on tests/test_public_imports.py both pass
    - The `make test` log ends with `1 failed, 288 passed, 3 deselected`, and `unexpected FAILED: 0`
    - Mutation proof prints non-zero codes (expected `rc leaf=1 subpkg=2 all=1`), then `mutation proof OK`, and `git diff --quiet -- src` succeeds
  </acceptance_criteria>
  <done>Every public module has its own import smoke case and fails loudly on broken imports or phantom exports. `make test` runs that smoke test inside the non-integration fast lane with integration deselected. src/ is untouched.</done>
</task>

<task type="auto">
  <name>Task 2: Opt-in `make test-integration`, README lane docs, single test(SR-003) commit, backlog note</name>
  <files>Makefile, README.md, .gsd/review_backlog.md</files>
  <read_first>README.md (the `## Tests & quality` section, about line 182: a bash block containing `make test` and `make check`); .gsd/review_backlog.md (the `### [ ] SR-003` section at about line 75, and the resolved `### [x] SR-002` section for the Resolution-note format)</read_first>
  <action>
1. Makefile:
   - Add `test-integration` to the `.PHONY` list, right after `test`.
   - Add a new target directly below `test:`: `test-integration: ## Opt-in integration lane: pytest -m integration (Docling over real data/raw; slow)`.
   - Its recipe is an echo `🚀 Testing code: Running pytest integration lane (-m integration)`, then `@$(UV) run python -m pytest -m integration`, without `--doctest-modules` since doctests are not integration tests.
   - Do NOT run `make test-integration`. It runs Docling over real data/raw. Verify it only with `make -n` and `--collect-only`.

2. README.md `## Tests & quality`: replace the existing bash block with three lines, each with an aligned trailing shell comment:
   - `make test` — fast lane (default local/merge check): unit tests + public-package import smoke
   - `make test-integration` — opt-in: `integration`-marked tests (Docling over real data/raw, slow)
   - `make check`

   Below the block, add one sentence: `make test` runs `pytest -m "not integration"`, so integration tests are deselected unless you run `make test-integration`. Change nothing else in README.md, and leave CONTRIBUTING.md unchanged; its `make test` wording is still accurate.

3. Gate run from the repo root:
   - `make test`. The expected summary is `1 failed, 288 passed, 3 deselected`, and the only failure is the known pre-existing test_settings one. If any other test fails, stop and report it; do not edit tests.
   - `uv run ruff check --no-fix src tests`
   - `uv run mypy`

4. Commit:
   - Stage exactly tests/test_public_imports.py, Makefile and README.md, by explicit path. Never use `git add -A`, `git add .` or `git commit -a`.
   - Do not stage .planning/STATE.md, .planning/config.json or any other untracked path. Those are pre-existing user state.
   - Create ONE commit with subject `test(SR-003): add public-package import smoke and default fast lane`. Keep the body short: the smoke test covers 41 public modules plus `__all__` resolution and excludes `__main__`; `make test` is `-m "not integration"`; `make test-integration` is opt-in; CI, tox and coverage are left to SR-012. End the body with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
   - Let pre-commit hooks run normally and never bypass them. If a hook rewrites a file, re-stage the same three paths and create the commit again (a new commit, never an amend).

5. After the commit, edit the gitignored .gsd/review_backlog.md. It is local only and must not be committed.
   - Flip `### [ ] SR-003: Public-package import smoke + mandatory fast lane ✅` to `### [x] SR-003: ...` (same title).
   - Add a `**Resolution:**` paragraph under its Done-when block, in the format of the SR-002 note. Cover these points:
     - tests/test_public_imports.py parametrizes 41 public modules. That is `api`, `compliance` and `evaluation` walked with `pkgutil.walk_packages` (walk errors re-raised, not skipped), plus the `main` entrypoint. It asserts every `__all__` name resolves.
     - `__main__` modules are excluded because `compliance.workflows.__main__` runs the preprocessing CLI at import time.
     - `make test` is the fast lane (`-m "not integration"`) and `make test-integration` is opt-in.
     - CI ordering, pytest-cov and tox `--cov` remain SR-012.
     - Include the commit short SHA.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && make -n test | grep -F -- '-m "not integration"' && make -n test-integration | grep -F -- '-m integration' && COL=$(uv run python -m pytest -m integration --collect-only -q -p no:cacheprovider) && echo "$COL" | tail -1 && make help | grep -c "test-integration" && grep -n "make test-integration" README.md && uv run ruff check --no-fix src tests && uv run mypy && SUBJ=$(git log -1 --format=%s) && echo "$SUBJ" | grep -E '^test\(SR-003\):' && FILES=$(git show --name-only --format= HEAD) && echo "$FILES" | sort && echo "commits since 05eace3: $(git rev-list --count 05eace3..HEAD)" && git diff --quiet 05eace3 HEAD -- .github tox.ini pyproject.toml uv.lock && echo "SR-012 files untouched" && git status --short .planning/STATE.md .planning/config.json && grep -n "### \[x\] SR-003" .gsd/review_backlog.md && git check-ignore .gsd/review_backlog.md</automated>
  </verify>
  <acceptance_criteria>
    - `make -n test` shows `-m "not integration"`, `make -n test-integration` shows `-m integration`, and `make help` lists `test-integration`
    - Integration collect-only prints `3/292 tests collected (289 deselected)`, meaning exactly 3 integration tests are selected
    - README.md contains `make test-integration` inside `## Tests & quality`
    - ruff check and mypy pass
    - `git log -1 --format=%s` starts with `test(SR-003):`, and `git show --name-only --format= HEAD` lists exactly Makefile, README.md and tests/test_public_imports.py
    - `commits since 05eace3: 1` and `SR-012 files untouched`
    - `git status --short .planning/STATE.md .planning/config.json` still shows both as ` M` (unstaged)
    - `### [x] SR-003` is present in .gsd/review_backlog.md, and `git check-ignore` confirms the file is ignored
  </acceptance_criteria>
  <done>The fast lane is the documented default, the integration lane is an explicit opt-in target, and SR-003 ships as one hook-checked commit containing only the three intended files. The local backlog marks SR-003 resolved.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| test process to local data roots | Importing a module can execute top-level code. `compliance.workflows.__main__` runs the preprocessing CLI, which reads data/raw and writes data/preprocessed and data/results. |
| test-lane selection to merge signal | Which tests `make test` selects decides whether a broken import can reach a commit green. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-SR003-01 | Tampering | `_public_module_names` enumerating `compliance.workflows.__main__` | high | mitigate | Filter out every `*.__main__` name before parametrizing. Task 1 verify asserts `__main__ ids: 0` in collect-only output and `data writes: 0` (a `find data -newer` marker) after the smoke run. This was observed for real during planning: an unfiltered walk overwrote 108 preprocessed files. |
| T-SR003-02 | Tampering | `pkgutil.walk_packages` silently skipping broken subpackages (false green) | medium | mitigate | `onerror=_reraise_walk_error` re-raises the original ImportError. The Task 1 mutation proof requires a non-zero exit for leaf, subpackage and phantom-`__all__` breaks. |
| T-SR003-03 | Denial of service | Fast lane deselecting integration hides Docling-path regressions | low | accept | `make test-integration` keeps the lane one command away. CI still runs `pytest tests` unchanged, and SR-012 owns the CI/integration isolation decision. |
| T-SR003-SC | Tampering | npm/pip/cargo installs | low | mitigate | No package install. pyproject.toml and uv.lock stay byte-identical to 05eace3 (Task 2 verify: `git diff --quiet 05eace3 HEAD -- ... pyproject.toml uv.lock`). |
</threat_model>

<verification>
- `uv run python -m pytest tests/test_public_imports.py -q` shows `41 passed`, no `__main__` IDs are collected, and nothing under data/ is written
- The mutation proof shows non-zero exits for a leaf break, a subpackage break and a phantom `__all__`, and src/ is clean afterwards
- `make test` shows `1 failed, 288 passed, 3 deselected`, where the only failure is the known test_settings one
- `make -n test-integration` shows `-m integration`, and integration collect-only selects exactly 3
- `uv run ruff check --no-fix src tests` and `uv run mypy` pass
- There is one `test(SR-003):` commit with exactly 3 files. SR-012 files are untouched, and STATE.md and config.json are unstaged.
</verification>

<success_criteria>
- SR-003 "Done when" #1: the smoke tests fail on broken public imports, proven by three mutations.
- SR-003 "Done when" #2: the Makefile `test` target (documented in README) runs the fast lane without selecting integration tests by default, and `make test-integration` is the explicit opt-in.
- No SR-012 scope was touched (CI workflow, tox, pytest-cov, pyproject addopts).
</success_criteria>

<output>
Create `.planning/quick/260929-hvt-sr-003-public-package-import-smoke-and-m/260929-hvt-SUMMARY.md` when done
</output>
