---
phase: 260929-k1p-sr-011-strong-config-policy-validation-n
plan: "01"
subsystem: config
tags: [config-validation, coverage-branches, pydantic, sr-011]
dependency-graph:
  requires: []
  provides:
    - analysis.coverage.branches keyed routing
    - StrictConfigModel extra=forbid
    - required-document cross-reference validation
    - classification↔coverage vocabulary alignment
  affects: [claim_pipeline coverage routing, config.yaml policy contract]
tech-stack:
  added: []
  patterns:
    - "CoverageClassificationConfig.branches as authoritative label→branch map (D-01)"
    - "Tree-wide StrictConfigModel with extra=forbid (D-02)"
    - "Dedicated ValueError subclasses for TRY003-safe validation messages (P-07)"
key-files:
  created: []
  modified:
    - src/compliance/config/settings.py
    - src/compliance/config/__init__.py
    - config.yaml
    - src/compliance/workflows/claim_pipeline.py
    - tests/conftest.py
    - tests/test_api/conftest.py
    - tests/test_workflows/test_claim_pipeline.py
    - tests/test_workflows/test_pipeline.py
    - tests/test_preprocessing/test_integration.py
    - tests/test_config/test_settings.py
    - tests/test_evaluation/test_cli.py
    - .gsd/review_backlog.md
decisions:
  - "D-01: breaking named coverage.branches map; no positional zip"
  - "D-02: fail hard on unknown keys via StrictConfigModel"
  - "P-01: YAML branches sibling to labels"
  - "P-02: CoverageClassificationConfig only on coverage stage"
  - "P-03: extra=forbid tree-wide through one strict base"
  - "P-04: other_label not required in labels (explicit non-goal)"
  - "P-05: branch values must be unique"
  - "P-06: classification↔coverage alignment on positive sets only"
  - "P-07: dedicated ValueError subclasses for TRY003"
  - "P-08: SR-004 tie-break still order-sensitive (explicit non-goal)"
actuals:
  tokens: 12573
  tasks: 3
  commits: 3
  plan_head_before: "d3150c505fa0e6ddd3e9255226ba108ce49a680e"
requirements-completed: [SR-011]
metrics:
  duration: "~7min"
  completed: 2026-09-29
status: complete
---

# Phase 260929-k1p Plan 01: Strong config policy validation (SR-011) Summary

`config.yaml` is now a validated policy contract: coverage routing reads an explicit `analysis.coverage.branches` map by key, unknown keys fail at load, label/range hygiene is enforced, and every required-document / taxonomy cross-reference is checked when the config loads.

## Performance

- **Duration:** ~7 min wall clock
- **Started:** 2026-09-29T12:38:09Z
- **Completed:** 2026-09-29T12:44:57Z
- **Tasks:** 3/3
- **Files modified:** 11 source/test/config (+ gitignored backlog)

## Accomplishments

- Replaced positional `zip(positive_labels, hard-coded branches)` with keyed `coverage.branches` lookup; reordering `labels` no longer remaps routing.
- Applied `extra="forbid"` tree-wide via `StrictConfigModel`; duplicate/empty labels, unknown `label_names` keys, and out-of-range numerics fail at load.
- Validated every `required_documents` cross-reference and classification↔coverage positive vocabulary alignment at startup; closed SR-011 in the backlog.

## Task Commits

1. **Task 1 (tracer): named coverage keys** - `2b1e8f5` (feat)
2. **Task 2: forbid unknown keys + label/range constraints** - `082962b` (feat)
3. **Task 3: taxonomy cross-references + close SR-011** - `1a190a5` (feat)

## Baselines vs final gates

| Gate | Baseline (Task 1 Step 0) | Final |
|------|--------------------------|-------|
| `uv run pytest -q` | 339 passed, 3 deselected | 368 passed, 3 deselected |
| `uv run mypy` (settings + claim_pipeline) | 0 errors | 0 errors |
| `uv run ruff check --no-fix` (touched .py) | clean | clean |
| `uv run ruff format --check` | 1 pre-existing unformatted (`test_integration.py`) | clean (formatted when migrated) |
| `grep -c 'zip(' claim_pipeline.py` | 1 | 0 |

## Exact `branches` YAML block

```yaml
    # Authoritative label-code → routing-branch map; label order carries no routing meaning (D-01).
    branches:
      "1": cancellation
      "2": personal_effects
      "3": missed_departure
```

## Validation rules added (per model / error class)

| Model / check | Rule | Error class |
|---------------|------|-------------|
| `CoverageClassificationConfig` | keys = positive labels; unique branch values; valid `CoverageRoute` | `CoverageBranchMappingError`, `DuplicateCoverageBranchError` (+ pydantic Literal) |
| `ClassificationConfig` | non-empty labels; no duplicates; `label_names` ⊆ labels∪{other_label} | `EmptyConfigLabelsError`, `DuplicateConfigLabelsError`, `UnknownLabelNameKeysError` |
| All config models via `StrictConfigModel` | reject unknown keys | pydantic `extra_forbidden` |
| Numeric Fields | confidence/signature ∈ [0,1]; block_size ≥ 2; chi² > 0; counts ≥ 0 | pydantic Field constraints |
| `AnalysisConfig` | required_documents codes ⊆ target stage positives; non-empty `cancellation_by_reason` value lists | `UnknownTaxonomyCodeError`, `EmptyAcceptableDocumentCodesError` |
| `AppConfig` | classification.positive_labels() set == analysis.coverage.positive_labels() set | `CoverageVocabularyMismatchError` |

## Migrated builder sites (7 planned + 2 blocking CLI YAML helpers)

1. `config.yaml`
2. `tests/conftest.py` (`cancellation_analysis_config`, `minimal_analysis_config_factory`)
3. `tests/test_api/conftest.py` (`compact_analysis_config`)
4. `tests/test_workflows/test_claim_pipeline.py` (`_analysis_config`, `_minimal_cli_config_yaml`)
5. `tests/test_preprocessing/test_integration.py`
6. `tests/test_config/test_settings.py` (`_MINIMAL_ANALYSIS_YAML`)
7. `tests/test_evaluation/test_cli.py` (`_write_minimal_config`)
8. **[Rule 3]** `tests/test_workflows/test_pipeline.py` (two CLI YAML builders — required for green suite)

## Reorder-does-not-remap evidence

`test_coverage_label_order_does_not_remap_branch`: labels reversed to `["3","2","1","False"]`, branches unchanged, winner `"1"` at 0.9 → still cancellation path (`reason_label_codes=["2"]`, medical certificate, APPROVE, call_count=7). Under positional zip this remapped to missed_departure (RED: `assert [] == ['2']`).

## Planner discretion (P-01..P-08)

- **P-01:** single `branches` map sibling to `labels` (keeps other stages unchanged).
- **P-02:** `CoverageClassificationConfig` only on `AnalysisConfig.coverage`.
- **P-03:** tree-wide `StrictConfigModel`.
- **P-04 (explicit non-goal):** `other_label` need not be in `labels`.
- **P-05:** branch values unique (many-to-one would make document-stage selection ambiguous).
- **P-06:** classification↔coverage alignment on positive sets only (not `label_names`).
- **P-07:** dedicated `ValueError` subclasses compose messages in `__init__`.
- **P-08 (explicit non-goal):** SR-004 exact-probability tie-break still follows `labels` order; reorder test uses unambiguous probabilities.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Migrated CLI YAML builders in `test_pipeline.py` and `_minimal_cli_config_yaml`**
- **Found during:** Task 1 verify
- **Issue:** Five CLI/main tests wrote coverage YAML without `branches`, failing load after the schema break.
- **Fix:** Added `branches: {"1": cancellation}` to those builders (same pattern as evaluation CLI).
- **Files modified:** `tests/test_workflows/test_pipeline.py`, `tests/test_workflows/test_claim_pipeline.py`
- **Commit:** `2b1e8f5`

## Follow-ups (untouched)

- SR-010 medical gating and SR-013 policy extraction remain out of scope.
- `analysis.*.label_names` completeness (every label must have a name) is still not required.

## Self-Check: PASSED

- FOUND: `src/compliance/config/settings.py` (`CoverageClassificationConfig`, `StrictConfigModel`, cross-ref validators)
- FOUND: `config.yaml` (`branches:`)
- FOUND: `tests/test_config/test_settings.py` (`test_unknown_config_key_rejected`, cross-ref tests)
- FOUND: `tests/test_workflows/test_claim_pipeline.py` (`test_coverage_label_order_does_not_remap_branch`)
- FOUND: commits `2b1e8f5`, `082962b`, `1a190a5`
- FOUND: `.gsd/review_backlog.md` `### [x] SR-011` (gitignored, not staged)
