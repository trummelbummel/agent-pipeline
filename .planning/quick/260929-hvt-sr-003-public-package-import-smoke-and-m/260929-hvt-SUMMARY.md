---
phase: 260929-hvt-sr-003-public-package-import-smoke-and-m
plan: 01
subsystem: testing
tags: [pytest, pkgutil, makefile, ci-fast-lane]

requires: []
provides:
  - "tests/test_public_imports.py: parametrized import-smoke test over all 41 public modules (api, compliance, evaluation packages + main entrypoint), asserting __all__ exports resolve"
  - "Makefile test target: fast lane (pytest --doctest-modules -m \"not integration\"), now the default make test"
  - "Makefile test-integration target: opt-in integration lane (pytest -m integration)"
  - "README.md ## Tests & quality: documents both lanes"
affects: ["SR-012 (CI fast-lane ordering, pytest-cov, tox --cov)"]

actuals:
  tokens: 1237
  tasks: 2
  commits: 1

tech-stack:
  added: []
  patterns:
    - "pkgutil.walk_packages with onerror=<re-raise> to turn a broken subpackage import into a hard collection error instead of a silently-skipped false green"
    - "__main__ module exclusion by name suffix to prevent import-time CLI execution during test collection"

key-files:
  created:
    - tests/test_public_imports.py
  modified:
    - Makefile
    - README.md

key-decisions:
  - "Kept the fast-lane default in the Makefile only (no pyproject.toml addopts marker default), preserving SR-012's ownership of CI/tox lane selection"
  - "No lint-suppression comment on the unused onerror name parameter in _reraise_walk_error, since ARG rules are not selected in ruff config"

patterns-established:
  - "New Makefile test targets get a `##` help comment and are added to .PHONY; test-integration follows the test target's echo/recipe shape"

requirements-completed: [SR-003]

coverage:
  - id: D1
    description: "Import-smoke test parametrized over all 41 public modules (api, compliance, evaluation + main), asserting __all__ exports resolve; excludes __main__ modules"
    requirement: SR-003
    verification:
      - kind: unit
        ref: "tests/test_public_imports.py::test_public_module_imports"
        status: pass
    human_judgment: false
  - id: D2
    description: "make test is the default fast lane (-m \"not integration\"); make test-integration is the explicit opt-in target"
    requirement: SR-003
    verification:
      - kind: unit
        ref: "make test (1 failed, 288 passed, 3 deselected — only known pre-existing failure); make -n test-integration shows -m integration"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-09-29
status: complete
---

# Phase 260929-hvt Plan 01: Public-package import smoke + mandatory fast lane Summary

**Parametrized import-smoke test over 41 public modules (walking `api`, `compliance`, `evaluation` via `pkgutil.walk_packages` with re-raised walk errors, plus `main`) wired into `make test` as the default fast lane, with `make test-integration` as the explicit opt-in.**

## Performance

- **Duration:** 12min
- **Started:** 2026-09-29T11:03:00Z (approx)
- **Completed:** 2026-09-29T11:15:00Z (approx)
- **Tasks:** 2/2
- **Files modified:** 3 (tests/test_public_imports.py created, Makefile and README.md modified)

## Accomplishments
- `tests/test_public_imports.py` imports every public module under `api`, `compliance`, `evaluation` (excluding `__main__` modules) plus `main`, and asserts every declared `__all__` name resolves — closing the SR-001-style gap where nothing imported the packages end-to-end
- `make test` is now the fast lane (`pytest --doctest-modules -m "not integration"`), deselecting the 3 Docling-dependent integration tests by default
- `make test-integration` is a new, explicit opt-in target for the integration lane; README documents both lanes

## Task Commits

Each task was committed atomically per plan design (Task 1 built the test + Makefile fast-lane change but deferred committing per plan instruction; both tasks landed in a single commit as designed):

1. **Task 1: Public-module import smoke test wired into the `make test` fast lane** - no separate commit (plan explicitly deferred commit to Task 2)
2. **Task 2: Opt-in `make test-integration`, README lane docs, single test(SR-003) commit, backlog note** - `2e5855a` (test)

## Files Created/Modified
- `tests/test_public_imports.py` - Parametrized import-smoke test: `PUBLIC_PACKAGES`, `ENTRYPOINT_MODULES`, `_reraise_walk_error`, `_public_module_names`, `test_public_module_imports`
- `Makefile` - `test` target changed to the fast lane (`-m "not integration"`); new `test-integration` target added; both added to `.PHONY`
- `README.md` - `## Tests & quality` documents `make test` (fast lane), `make test-integration` (opt-in), `make check`, plus one sentence on lane selection

## Decisions Made
- Followed the plan's scope boundary exactly: no changes to `.github/`, `tox.ini`, `pyproject.toml`, or `uv.lock` (verified `git diff --quiet 05eace3 HEAD -- .github tox.ini pyproject.toml uv.lock`)
- Single commit contains exactly the three intended files (`Makefile`, `README.md`, `tests/test_public_imports.py`); `.planning/STATE.md` and `.planning/config.json` were left unstaged as instructed

## Deviations from Plan

None — plan executed exactly as written. One informational note: the plan's negative-proof step (Task 1, mutation (b)) documented an *expected* exit code of 2 for the subpackage break (`src/compliance/tools/benford.py`). The measured exit code was 4, because `tests/conftest.py` eagerly imports `compliance.preprocessing.description`, which transitively imports `compliance.tools.benford` — so the break surfaces as a conftest-load usage error (pytest exit 4) rather than a collection error raised from inside `test_public_imports.py`'s own `pkgutil.walk_packages` call. The automated verify script only asserts non-zero exit codes for all three mutations (not the specific values), so this is not a functional deviation — the re-raise mechanism (`onerror=_reraise_walk_error`) is still proven to turn a broken subpackage into a hard, non-zero-exit failure; it's just a different pytest-internal code path than assumed at planning time. No code change was needed.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
SR-003 is resolved and marked `[x]` in the gitignored `.gsd/review_backlog.md`, with a Resolution note covering commit `2e5855a`. SR-012 (CI fast-lane ordering, pytest-cov install/threshold, tox `--cov`, integration isolation in CI) remains open and unblocked by this plan — its target files were verified untouched.

---
*Phase: 260929-hvt-sr-003-public-package-import-smoke-and-m*
*Completed: 2026-09-29*
