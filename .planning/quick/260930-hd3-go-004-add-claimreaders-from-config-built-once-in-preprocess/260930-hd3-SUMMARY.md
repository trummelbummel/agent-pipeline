---
phase: 260930-hd3-go-004-add-claimreaders-from-config-built-once-in-preprocess
plan: 01
subsystem: preprocessing
tags: [claim-readers, composition, r16, from_config, docling, once-per-pipeline]
quick_id: 260930-hd3

requires:
  - phase: 260930-hd2
    provides: DocumentReader.from_config composing Docling / retry / signature / Benford
provides:
  - ClaimReaders.from_config built once in PreprocessingPipeline and run_pipeline
affects: []

actuals:
  tokens: 4634
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "ClaimReaders NamedTuple + from_config(AppConfig, **overrides) at composition root"
    - "Prebuilt readers passed into _process_single_claim; kwargs remain test injection seams"

key-files:
  created: []
  modified:
    - src/compliance/preprocessing/claim_batch.py
    - src/compliance/preprocessing/__init__.py
    - src/compliance/workflows/pipeline.py
    - tests/test_preprocessing/test_claim_batch.py
    - tests/test_workflows/test_pipeline.py
    - .planning/refactor.md

key-decisions:
  - "ClaimReaders lives in claim_batch.py (prefer edit existing file) as a NamedTuple with from_config"
  - "PreprocessingPipeline.__init__ builds ClaimReaders once and reuses format_converter / extraction_failure from the bundle"
  - "run_pipeline also builds once before the claim loop so batch entry matches pipeline lifetime"

patterns-established:
  - "ClaimReaders.from_config(AppConfig, **overrides) — DocumentReader not reconstructed per claim"

requirements-completed: []

coverage:
  - id: D1
    description: ClaimReaders.from_config holds answer/markdown/description/document readers plus shared FormatConverter and ExtractionFailure
    verification:
      - kind: unit
        ref: "tests/test_preprocessing/test_claim_batch.py::test_claim_readers_from_config_honors_overrides"
        status: pass
      - kind: unit
        ref: "tests/test_preprocessing/test_claim_batch.py::test_run_pipeline_builds_document_reader_once"
        status: pass
    human_judgment: false
  - id: D2
    description: PreprocessingPipeline builds ClaimReaders once in __init__ and passes them into every claim
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_pipeline.py::test_preprocessing_pipeline_builds_document_reader_once"
        status: pass
      - kind: other
        ref: "make test"
        status: pass
    human_judgment: false

duration: 7min
completed: 2026-09-30
status: complete
plan_head_before: 893b006bd2435bf3e6146d9a85bf1f8c5d98d43a
commits: 2
---

# Phase 260930-hd3 Plan 01: ClaimReaders once-per-pipeline Summary

**Claim readers (including Docling-backed `DocumentReader`) are built once via `ClaimReaders.from_config` at the pipeline/batch root and reused across claims.**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-09-30T11:38:14Z
- **Completed:** 2026-09-30T11:45:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Added `ClaimReaders` NamedTuple with `from_config(AppConfig, **overrides)` holding answer/markdown/description/document readers plus shared `FormatConverter` and `ExtractionFailure`.
- `run_pipeline` and `PreprocessingPipeline.__init__` build readers once; `_process_single_claim` accepts a prebuilt bundle while keeping `document_reader=` / etc. injection seams.
- Marked GO-004 done in `.planning/refactor.md` (and locally in `.gsd/refactor.md`, not committed).

## Task Commits

1. **Task 1: ClaimReaders bundle** - `cd8eced` (refactor)
2. **Task 2: Wire pipeline + mark GO-004** - `3139683` (refactor)

## Files Created/Modified

- `src/compliance/preprocessing/claim_batch.py` — `ClaimReaders` + once-per-batch wiring
- `src/compliance/preprocessing/__init__.py` — export `ClaimReaders`
- `src/compliance/workflows/pipeline.py` — build readers in `__init__`, pass into `_process_single_claim`
- `tests/test_preprocessing/test_claim_batch.py` — override + once-construction tests
- `tests/test_workflows/test_pipeline.py` — pipeline once-construction test
- `.planning/refactor.md` — GO-004 checked off

## Decisions Made

- Prefer `NamedTuple` + `from_config` in `claim_batch.py` over a new module.
- Share the pipeline's PNG converter and extraction-failure detector from the same `ClaimReaders` instance.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

GO-004 complete; god-object quick-batch items GO-001–GO-004 are done. Ready for next refactor or milestone work.

## Self-Check: PASSED

- FOUND: `src/compliance/preprocessing/claim_batch.py` (`ClaimReaders`)
- FOUND: `src/compliance/workflows/pipeline.py` (once-init wiring)
- FOUND: `cd8eced`, `3139683`
- FOUND: `.planning/quick/.../260930-hd3-SUMMARY.md`
- `make test`: 502 passed

---
*Phase: 260930-hd3-go-004-add-claimreaders-from-config-built-once-in-preprocess*
*Completed: 2026-09-30*
