---
phase: 260926-gij-create-common-fixtures-across-api-tests
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/test_api/conftest.py
  - tests/test_api/test_claims_post.py
  - tests/test_api/test_claims_get.py
  - tests/test_api/test_claims_list.py
  - tests/test_api/test_claims_e2e.py
  - tests/test_api/test_deps_lifespan.py
  - /Users/theresa/.claude/skills/dedup-review/SKILL.md
  - /Users/theresa/.claude/skills/dedup-review/references/signals.md
autonomous: true
requirements: []

estimate:
  tokens: 18000
  raw_tokens: 18000
  tasks: 2
  confidence: low

must_haves:
  truths:
    - "API tests share reusable function-scoped configuration and cancellation-path fixtures from tests/test_api/conftest.py instead of redefining the same AppConfig builders in five modules"
    - "Fixture extraction preserves each API test's existing roots, analysis vocabulary, fresh MagicMock side effects, and request behavior"
    - "One-off multipart payloads, seeded artifacts, probe routes, and endpoint-specific setup remain local when sharing would obscure the test"
    - "The dedup-review skill detects repeated pytest fixtures and complex setup helpers across test files, while recommending the narrowest conftest.py scope"
    - "All API tests and the complete project test suite pass after the refactor"
  artifacts:
    - path: "tests/test_api/conftest.py"
      provides: "API-scoped config factory and cancellation-path fixtures"
    - path: "/Users/theresa/.claude/skills/dedup-review/SKILL.md"
      provides: "Test-setup-aware module-map and consolidation workflow"
    - path: "/Users/theresa/.claude/skills/dedup-review/references/signals.md"
      provides: "Dedicated repeated-test-setup detection signal"
  key_links:
    - from: "tests/test_api/test_claims_*.py and test_deps_lifespan.py"
      to: "tests/test_api/conftest.py"
      via: "pytest fixture injection with function-scoped mutable objects"
    - from: "dedup-review detect-redundancies workflow"
      to: "repeated test setup"
      via: "fixture/helper manifest fields and a signal that distinguishes meaningful setup from one-off arrangements"
---

<objective>
Consolidate concrete setup duplication across the Claims API tests and teach dedup-review to identify the same class of duplication in future test reviews.

Purpose: Five API modules currently repeat near-identical AnalysisConfig/AppConfig construction, four repeat the same delayed create_app import wrapper, and GET/E2E repeat the same cancellation analysis/chat setup. The wider suite also repeats config builders and some mock-reader helpers, confirming that test setup is a real deduplication signal, but those wider variants encode subsystem-specific labels/default roots and should not be folded into one suite-global abstraction in this atomic quick task.
Output: An API-scoped conftest.py, migrated API tests with unchanged behavior, and test-fixture detection guidance in the dedup-review skill.
</objective>

<execution_context>
@~/.claude/gsd-core/workflows/execute-plan.md
@~/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@tests/test_api/test_claims_post.py
@tests/test_api/test_claims_get.py
@tests/test_api/test_claims_list.py
@tests/test_api/test_claims_e2e.py
@tests/test_api/test_deps_lifespan.py
@/Users/theresa/.claude/skills/dedup-review/SKILL.md
@/Users/theresa/.claude/skills/dedup-review/references/signals.md

## Inspection findings

- All five API test modules define an AppConfig builder with the same preprocessing, extraction, classification, checking, and evaluation boilerplate. POST/list/lifespan use the same compact AnalysisConfig; GET/E2E use the same labeled cancellation AnalysisConfig.
- GET and E2E define equivalent `_chat_response` and `_cancellation_chat_fn` setup. The MagicMock must remain function-scoped because its side-effect iterator is consumed.
- POST and E2E multipart payloads differ materially; GET's raw-claim seed, list result seeding, and lifespan probe routes are endpoint-specific. Keep these local.
- Outside API tests, AppConfig builders recur in preprocessing, workflows, and evaluation, but their label sets, required-documents/OCR settings, and root semantics differ. `_mock_description_reader` and `_mock_document_reader` are duplicated in two files, but moving two domain-local helpers to a suite-root conftest would broaden fixture visibility and obscure their local test contracts. Record these as evidence for the skill update; do not refactor them in this quick task.
- The working tree is heavily dirty. Preserve all user changes, avoid broad formatting, and stage/commit only files listed in this plan plus GSD summary/state artifacts required by the executor.
</context>

<tasks>

<task type="tracer">
  <name>Task 1: Introduce API-scoped fixtures and migrate all Claims API tests</name>
  <files>tests/test_api/conftest.py, tests/test_api/test_claims_post.py, tests/test_api/test_claims_get.py, tests/test_api/test_claims_list.py, tests/test_api/test_claims_e2e.py, tests/test_api/test_deps_lifespan.py</files>
  <read_first>
    - tests/test_api/test_claims_post.py (_analysis_config, _config, _create_app, _multipart_files)
    - tests/test_api/test_claims_get.py (_analysis_config, _config, _create_app, _cancellation_chat_fn)
    - tests/test_api/test_claims_list.py (_analysis_config, _config, _create_app)
    - tests/test_api/test_claims_e2e.py (_analysis_config, _config, _cancellation_chat_fn)
    - tests/test_api/test_deps_lifespan.py (_analysis_config, _config, _create_app)
  </read_first>
  <action>
    Create `tests/test_api/conftest.py` with `from __future__ import annotations`, fully typed fixtures, and descriptive public fixture docstrings. Provide an API config factory fixture that accepts the raw data root plus optional preprocessed/results roots and optional AnalysisConfig, preserving each caller's current path semantics. Provide separate compact and labeled-cancellation AnalysisConfig fixtures (or a clearly typed factory profile) so list/POST/lifespan do not inherit labels they do not need. Provide a function-scoped cancellation chat fixture that returns a new MagicMock for every test and preserves the exact seven-response sequence used by GET/E2E. Import `create_app` directly now that the API factory exists; remove the repeated try/import wrappers rather than wrapping a stable import in another fixture.

    Migrate all five API test modules to fixture injection and remove superseded imports/helpers. Preserve endpoint-specific setup locally: multipart payload factories, raw claim seeding, result artifact writes, mock document/description readers, and lifespan probe routes. Do not introduce an always-open TestClient fixture because tests need differently configured apps and context-managed lifespan boundaries. Do not add autouse or session-scoped mutable fixtures. Run Ruff only against these API test files if formatting/import cleanup is needed, so unrelated dirty files are untouched.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance &amp;&amp; uv run pytest tests/test_api -q --tb=short &amp;&amp; uv run ruff check tests/test_api</automated>
  </verify>
  <done>All API modules consume API-scoped fixtures, duplicate config/create-app/cancellation-chat setup is removed, endpoint-specific arrangements remain readable and local, and the complete API test directory passes.</done>
</task>

<task type="auto">
  <name>Task 2: Extend dedup-review with repeated test-setup detection</name>
  <files>/Users/theresa/.claude/skills/dedup-review/SKILL.md, /Users/theresa/.claude/skills/dedup-review/references/signals.md</files>
  <read_first>
    - /Users/theresa/.claude/skills/dedup-review/SKILL.md (scope, build-module-map, detect-redundancies, plan-consolidation, anti_patterns, success_criteria)
    - /Users/theresa/.claude/skills/dedup-review/references/signals.md (S01-S08 format and thresholds)
  </read_first>
  <action>
    Update the skill so a standalone or test-inclusive review records pytest fixtures and private setup helpers in addition to production public symbols. Add a new signal after S08 for repeated test setup: detect equivalent fixture bodies or multi-step setup helpers in at least two test modules, confirm actual bodies before reporting, and distinguish meaningful shared setup from coincidentally similar one-off arrangements. Its remediation must prefer `conftest.py` at the narrowest common test directory, preserve function scope for consumed/mutable objects, and avoid autouse fixtures unless behavior genuinely applies to every test in scope.

    Reconcile the current anti-pattern that categorically forbids test-file reorganization with this new behavior: production module moves remain propose-only, while verified test setup may be safely extracted without reorganizing test modules. State that simple one-off setup, assertion-specific data, and domain variants with materially different semantics stay local. Update signal ranges/counts and success criteria wherever the skill currently assumes only S01-S08 or only production abstractions. Use the API duplication and the wider-suite findings in this plan as threshold examples, without adding project-specific file names to this reusable skill.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance &amp;&amp; uv run python -m pytest --doctest-modules -q --tb=short &amp;&amp; python -c "from pathlib import Path; s=Path('/Users/theresa/.claude/skills/dedup-review/SKILL.md').read_text(); r=Path('/Users/theresa/.claude/skills/dedup-review/references/signals.md').read_text(); assert 'conftest.py' in s + r; assert 'S09' in s + r; assert 'fixture' in (s + r).lower()"</automated>
  </verify>
  <done>The reusable dedup-review workflow detects and safely scopes repeated pytest setup, its guidance no longer excludes all test consolidation, and the full project test command passes after the fixture refactor.</done>
</task>

</tasks>

<verification>
- `uv run pytest tests/test_api -q --tb=short` passes all Claims API tests.
- `uv run ruff check tests/test_api` reports no API-test lint errors.
- `uv run python -m pytest --doctest-modules -q --tb=short` passes the same full test surface as the Makefile test target.
- Final diff contains no production-code edits and no unrelated dirty-file changes.
</verification>

<success_criteria>
- API configuration and cancellation chat setup each have one API-scoped source of truth.
- Test behavior and isolation are unchanged; every mutable/consumed mock is fresh per test.
- Local one-off arrangements remain visible in their endpoint tests.
- dedup-review explicitly detects repeated fixture/setup patterns and recommends narrow conftest scope.
- Focused and full test verification pass.
</success_criteria>

<output>
Create `.planning/quick/260926-gij-create-common-fixtures-across-api-tests-/260926-gij-SUMMARY.md` when done.
</output>
