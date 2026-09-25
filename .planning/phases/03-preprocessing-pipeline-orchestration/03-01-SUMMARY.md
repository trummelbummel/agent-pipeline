---
phase: 03-preprocessing-pipeline-orchestration
plan: 01
subsystem: workflows
tags: [preprocessing, workflows, pydantic, pytest, config]

requires:
  - phase: 01-claim-preprocessing-pipeline
    provides: "_process_single_claim, ClaimBundle, Readers/Preprocessors"
provides:
  - "process_claim_to_preprocessed writing four named artifacts under output_root/claim N/"
  - "PreprocessingConfig.preprocessed_dir config field"
  - "output_root_from_config Path helper for 03-02 batch"
affects:
  - 03-preprocessing-pipeline-orchestration
  - downstream-agents-dataset

actuals:
  tokens: 4800
  tasks: 3
  commits: 10

plan_head_before: de7c8a7ed4c236b1e94cf3329aed14b797433ea3

tech-stack:
  added: []
  patterns:
    - "Compose Phase 1 _process_single_claim; project ClaimBundle into mirrored preprocessed/ artifacts"
    - "Validate claim_dir.name at filesystem boundary before mkdir (T-03-03)"
    - "Serialize JSON via Pydantic model_dump_json / model_dump(mode=json)"

key-files:
  created:
    - src/compliance/workflows/pipeline.py
    - tests/test_workflows/test_pipeline.py
  modified:
    - src/compliance/workflows/__init__.py
    - src/compliance/config/settings.py
    - config.yaml
    - .gitignore
    - tests/test_config/test_settings.py
    - tests/test_preprocessing/test_pipeline.py
    - tests/test_preprocessing/test_integration.py

key-decisions:
  - "Extend PreprocessingConfig.preprocessed_dir instead of a separate workflows AppConfig section"
  - "description.txt empty bytes when description_text missing/nan; supporting_documents.md uses _none_ when all sources empty"
  - "Refuse claim_dir.name with path separators or .. before any mkdir/write"

patterns-established:
  - "Workflows compose Phase 1 ClaimBundle path; never write Phase 1 processed.json"
  - "Private helpers named after products: _description_txt_bytes, _answer_json_text, _supporting_document_json_text, _supporting_documents_md_text, _write_claim_artifacts"
  - "Injectable description/document readers in unit tests — no live Ollama/Docling"

requirements-completed: []

coverage:
  - id: D1
    description: "One claim folder projects to four named artifacts under output_root/claim N/"
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_pipeline.py#test_process_claim_writes_four_artifacts"
        status: pass
    human_judgment: false
  - id: D2
    description: "Missing optional markdown/documents still emit all four files"
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_pipeline.py#test_process_claim_missing_optionals_still_emits_four_files"
        status: pass
    human_judgment: false
  - id: D3
    description: "Unsafe claim_dir.name refused before mkdir (T-03-03)"
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_pipeline.py#test_process_claim_refuses_unsafe_claim_dir_name"
        status: pass
    human_judgment: false
  - id: D4
    description: "preprocessed_dir loaded from config.yaml; preprocessed/ gitignored"
    verification:
      - kind: unit
        ref: "tests/test_config/test_settings.py#test_load_config_reads_preprocessed_dir"
        status: pass
    human_judgment: false
  - id: D5
    description: "output_root_from_config resolves Path(config.preprocessing.preprocessed_dir)"
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_pipeline.py#test_output_root_from_config_matches_preprocessing_dir"
        status: pass
    human_judgment: false

duration: 4min
completed: 2026-09-25
status: complete
---

# Phase 03 Plan 01: One-Claim Preprocessed Tracer Summary

**Workflows `process_claim_to_preprocessed` composes Phase 1 ClaimBundle into a mirrored four-artifact tree under config-driven `preprocessed_dir`**

## Performance

- **Duration:** 4 min
- **Started:** 2026-09-25T12:04:20Z
- **Completed:** 2026-09-25T12:08:39Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments
- One-claim tracer writes `description.txt`, `answer.json`, `supporting_document.json`, `supporting_documents.md` under `output_root / claim_dir.name`
- Path-traversal refusal on unsafe `claim_dir.name` before mkdir (T-03-03); JSON via Pydantic dumps only (T-03-01)
- `preprocessed_dir` externalized in `config.yaml` / `PreprocessingConfig`; `output_root_from_config` ready for 03-02 batch

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: End-to-end four artifacts** - `75f1fdd` (test)
2. **Task 1 GREEN: Implement artifact writer** - `9daf8dc` (feat)
3. **Task 1 follow-up: docstring acceptance scan** - `865ccf5` (fix)
4. **Task 2 RED: preprocessed_dir config test** - `cf6889a` (test)
5. **Task 2 GREEN: Externalize preprocessed_dir** - `5218a86` (feat)
6. **Task 3: output_root_from_config helper** - `dc08279` (feat)

**Plan metadata:** `3ede379` (docs: complete plan), `b0d2494` (docs: advance STATE)

_Note: TDD tasks produced RED → GREEN commits; measured `commits: 10` includes interleaved Phase 02 docs commits on main between plan start and finish._

## Files Created/Modified
- `src/compliance/workflows/pipeline.py` - `process_claim_to_preprocessed`, artifact helpers, `output_root_from_config`
- `src/compliance/workflows/__init__.py` - public exports
- `src/compliance/config/settings.py` - `PreprocessingConfig.preprocessed_dir`
- `config.yaml` - `preprocessing.preprocessed_dir: preprocessed`
- `.gitignore` - `preprocessed/`
- `tests/test_workflows/test_pipeline.py` - four-artifact, optionals, unsafe-name, output_root tests
- `tests/test_config/test_settings.py` - preprocessed_dir load test
- `tests/test_preprocessing/test_pipeline.py` / `test_integration.py` - fixture field updates

## Decisions Made
- Extended `PreprocessingConfig` rather than adding a `workflows:` AppConfig section (avoids merge fight with Phase 2 `classification`)
- Markdown empty-state is `# Supporting documents` + `_none_`; non-empty uses `## Booking` / `## Internal: N` / `## Document: N`
- Logging uses claim folder names and artifact paths only — never letter/raw_text (T-03-02)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Updated PreprocessingConfig fixtures after required field add**
- **Found during:** Task 2 (Externalize preprocessed_dir)
- **Issue:** Required `preprocessed_dir` broke existing `PreprocessingConfig(...)` constructors in preprocessing tests
- **Fix:** Passed `preprocessed_dir="preprocessed"` in workflow, preprocessing, and integration fixtures; added field to tmp YAML samples
- **Files modified:** `tests/test_preprocessing/test_pipeline.py`, `tests/test_preprocessing/test_integration.py`, `tests/test_config/test_settings.py`, `tests/test_workflows/test_pipeline.py`
- **Verification:** `uv run pytest tests/test_config/test_settings.py tests/test_workflows/test_pipeline.py -q` green
- **Committed in:** `5218a86` (Task 2)

**2. [Rule 1 - Bug] Docstring mentioned processed.json and failed acceptance rg**
- **Found during:** Task 1 post-GREEN acceptance scan
- **Issue:** `rg processed\.json` matched docstring despite no write path
- **Fix:** Rephrased docstring to avoid Phase 1 filename
- **Files modified:** `src/compliance/workflows/pipeline.py`
- **Verification:** `rg` returns no matches
- **Committed in:** `865ccf5`

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 bug)
**Impact on plan:** Both required for correctness / acceptance criteria. No scope creep.

## Issues Encountered
None beyond the documented deviations. Interleaved Phase 02 docs commits landed on main during this plan's window (reflected in measured commit count).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Tracer + config path ready for 03-02 batch loop and `__main__` entrypoint
- Soft-fail / discover-all-claims orchestration still out of scope (03-02)

## TDD Gate Compliance
- Task 1: Stub wrote empty dir; four-artifact assertion failed (`RED_EVIDENCE_OK`)
- Task 2: Missing `preprocessed_dir` attribute failed (`RED_EVIDENCE_OK`)
- GREEN authorized only after `gsd_run check tdd-red-evidence` passed for each

## Self-Check: PASSED
- FOUND: `src/compliance/workflows/pipeline.py`
- FOUND: `tests/test_workflows/test_pipeline.py`
- FOUND: commits `75f1fdd`, `9daf8dc`, `865ccf5`, `cf6889a`, `5218a86`, `dc08279`

---
*Phase: 03-preprocessing-pipeline-orchestration*
*Completed: 2026-09-25*
