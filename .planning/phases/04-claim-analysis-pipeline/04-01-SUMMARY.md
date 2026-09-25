---
phase: 04-claim-analysis-pipeline
plan: 01
subsystem: config
tags: [langgraph, AnalysisConfig, config.yaml, pydantic, pytest, nyquist]

requires:
  - phase: 02-case-classifier-models
    provides: ClassificationConfig + CaseClassifier injectable chat_fn seam
  - phase: 03-preprocessing-pipeline-orchestration
    provides: PreprocessedArtifactNames, results_dir, path-safety patterns
provides:
  - langgraph dependency (1.2.12) pinned in uv.lock after human legitimacy approval
  - AnalysisConfig with five ClassificationConfig stages on AppConfig
  - config.yaml analysis: taxonomy (other_label "None"; Phase 02 Other preserved)
  - PreprocessedArtifactNames.analysis_result externalized
  - Nyquist xfail stubs in tests/test_workflows/test_claim_pipeline.py
affects: [04-02 ClaimPipeline tracer, 04-03 PE/missed routing, 04-04 batch/CLI]

actuals:
  tokens: 51069
  tasks: 3
  commits: 3
plan_head_before: 10c99b661498d54826dd9fc98d1d1951622052fa

tech-stack:
  added: [langgraph>=1.2.12, langchain-core (transitive)]
  patterns:
    - "Parallel analysis: section beside Phase 02 classification:"
    - "Reuse ClassificationConfig as stage type for AnalysisConfig fields"
    - "Wave 0 xfail stubs documenting R010–R014/R016 before production ClaimPipeline"

key-files:
  created:
    - tests/test_workflows/test_claim_pipeline.py
    - .planning/tdd/260925-04-01-task2-red-evidence.json
  modified:
    - pyproject.toml
    - uv.lock
    - config.yaml
    - src/compliance/config/settings.py
    - src/compliance/config/__init__.py
    - tests/test_config/test_settings.py
    - tests/test_workflows/test_pipeline.py
    - tests/test_preprocessing/test_claim_batch.py
    - tests/test_preprocessing/test_integration.py

key-decisions:
  - "Task 1: human approved langgraph legitimacy (LangChain / langchain-ai) — install proceeded"
  - "analysis stage other_label is YAML string None; classification.other_label stays Other"
  - "Coverage labels keep Phase 02 casing (Trip cancellation or rescheduling, etc.)"
  - "analysis_result.json externalized on PreprocessedArtifactNames (A1)"

patterns-established:
  - "AnalysisConfig holds five ClassificationConfig stages; load_config requires analysis"
  - "ClaimPipeline unit stubs inject MagicMock chat_fn — no live Ollama"

requirements-completed: [R015, R016]

coverage:
  - id: D1
    description: "Typed AnalysisConfig + config.yaml analysis stages load via load_config"
    requirement: R015
    verification:
      - kind: unit
        ref: "tests/test_config/test_settings.py::test_load_config_reads_analysis_section"
        status: pass
    human_judgment: false
  - id: D2
    description: "analysis other_label is None while classification.other_label remains Other"
    requirement: R015
    verification:
      - kind: unit
        ref: "tests/test_config/test_settings.py::test_analysis_coverage_other_label_is_none"
        status: pass
    human_judgment: false
  - id: D3
    description: "langgraph installed after blocking-human package legitimacy approval"
    requirement: R015
    verification:
      - kind: other
        ref: "uv add langgraph → pyproject.toml/uv.lock langgraph>=1.2.12"
        status: pass
    human_judgment: true
    rationale: "T-04-SC supply-chain gate required human confirm of PyPI/GitHub LangChain identity"
  - id: D4
    description: "Nyquist claim_pipeline stubs for R010–R014/R016 collect without live Ollama"
    requirement: R016
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_claim_pipeline.py (7 xfail stubs)"
        status: pass
    human_judgment: false

duration: 3min
completed: 2026-09-25
status: complete
---

# Phase 04 Plan 01: Wave 0 Foundation Summary

**langgraph + multi-stage AnalysisConfig taxonomy installed; Nyquist claim-pipeline stubs ready for 04-02 tracer.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-09-25T15:19:30Z
- **Completed:** 2026-09-25T15:22:37Z
- **Tasks:** 3
- **Files modified:** 14 (plan commits)

## Accomplishments

- Human-approved `langgraph` 1.2.12 in lockfile (T-04-SC mitigated)
- Five analysis stages externalized in `config.yaml` / `AnalysisConfig` with `other_label: "None"`
- Wave 0 xfail stubs document coverage/routing/checker/path-safety/injectable `chat_fn`

## Task Commits

1. **Task 1: Verify langgraph package legitimacy** — checkpoint cleared (user **approved**); no install commit
2. **Task 2 RED:** `aefe95d` — `test(04-01): add failing tests for AnalysisConfig`
3. **Task 2 GREEN:** `e2e0dc6` — `feat(04-01): add langgraph and AnalysisConfig taxonomy`
4. **Task 3:** `f5fb5cd` — `test(04-01): scaffold ClaimPipeline Nyquist stubs`

**Plan metadata:** docs commit on `main` after task commits (`docs(04-01): complete Wave 0 AnalysisConfig plan`)

## Files Created/Modified

- `pyproject.toml` / `uv.lock` — langgraph dependency
- `config.yaml` — `analysis:` five stages + `analysis_result` artifact name
- `src/compliance/config/settings.py` — `AnalysisConfig`, `AppConfig.analysis`, artifact field
- `src/compliance/config/__init__.py` — export `AnalysisConfig`
- `tests/test_config/test_settings.py` — analysis load assertions
- `tests/test_workflows/test_claim_pipeline.py` — Nyquist xfail stubs
- AppConfig helpers updated in pipeline / claim_batch / integration tests

## Decisions Made

- Proceeded with Task 2 after Task 1 **approved** (no re-ask)
- Quoted YAML `"None"` so analysis `other_label` is the string `None`, not YAML null
- Kept Phase 02 `classification.other_label: Other` unchanged (A3/A6)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Updated AppConfig constructors missing required `analysis`**
- **Found during:** Task 2 GREEN
- **Issue:** Suite helpers in `test_pipeline.py`, `test_claim_batch.py`, `test_integration.py` constructed `AppConfig` without `analysis` (and claim_batch/integration also lacked `checking`), which would fail ValidationError once `analysis` became required
- **Fix:** Added `_analysis_config()` / inline `AnalysisConfig` plus `CheckingConfig` where missing
- **Files modified:** `tests/test_workflows/test_pipeline.py`, `tests/test_preprocessing/test_claim_batch.py`, `tests/test_preprocessing/test_integration.py`
- **Commit:** `e2e0dc6`

### Auth Gates

None (Task 1 was package legitimacy, not auth).

## TDD Gate Compliance

- Task 2 `tdd="true"`: RED evidence `.planning/tdd/260925-04-01-task2-red-evidence.json` → `RED_EVIDENCE_OK` (`target_test_failed` for `test_load_config_reads_analysis_section`)
- GREEN authorized only after evidence check; RED commit `aefe95d` then GREEN `e2e0dc6`

## Known Stubs

| File | Stub | Reason |
|------|------|--------|
| `tests/test_workflows/test_claim_pipeline.py` | 7 `@pytest.mark.xfail` tests raise AssertionError | Wave 0 Nyquist placeholders — production ClaimPipeline in 04-02/04-03 |

## Threat Flags

None beyond plan register (T-04-SC mitigated by human approval + uv.lock pin).

## Next

Plan 04-02 — ClaimPipeline LangGraph tracer (cancellation path + checker).

## Self-Check: PASSED

- SUMMARY, AnalysisConfig, claim_pipeline stubs, langgraph in pyproject, commits aefe95d/e2e0dc6/f5fb5cd all present
