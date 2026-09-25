---
phase: 01-claim-preprocessing-pipeline
plan: 01-03
subsystem: preprocessing
tags: [docling, ollama, pipeline, document-reader, information-extractor]

requires:
  - phase: 01-claim-preprocessing-pipeline
    provides: GroundTruth / BookingData / DocumentData models and load_config
  - phase: 01-claim-preprocessing-pipeline
    provides: Reader/Preprocessor ABCs, FormatConverter, AnswerReader, MarkdownReader
provides:
  - DocumentReader (FormatConverter → PNG then Docling → DocumentData)
  - InformationExtractor + DescriptionReader (config LLM → BookingData)
  - run_pipeline writing processed.json for all 25 claims
affects:
  - future agent/rule milestones consuming processed.json

actuals:
  tokens: 12979
  tasks: 5
  commits: 9

plan_head_before: 597b885b6a1231f6b26d11950980bc72d75258a6

tech-stack:
  added: [docling]
  patterns:
    - "Raster → FormatConverter.to_png → Docling; PDF passes through to Docling"
    - "InformationExtractor(model_name, prompt) from config only; injectable chat_fn for tests"
    - "Pipeline soft-fails per file/claim; logs and continues"

key-files:
  created:
    - src/compliance/preprocessing/document.py
    - src/compliance/preprocessing/extractor.py
    - src/compliance/preprocessing/description.py
    - src/compliance/preprocessing/pipeline.py
    - tests/test_preprocessing/test_document.py
    - tests/test_preprocessing/test_extractor.py
    - tests/test_preprocessing/test_description.py
    - tests/test_preprocessing/test_pipeline.py
    - tests/test_preprocessing/test_integration.py
  modified:
    - src/compliance/preprocessing/__init__.py
    - pyproject.toml
    - uv.lock
    - .gitignore

key-decisions:
  - "PDF skips FormatConverter and goes straight to Docling (Pillow cannot convert)"
  - "ollama.chat with format=json for InformationExtractor; model/prompt from config.yaml"
  - "Integration skips live LLM when Ollama is unavailable; Docling runs on real data/"

patterns-established:
  - "DocumentData: person/date core + fields dict for arbitrary KV candidates"
  - "Reader injection kwargs on run_pipeline/_process_single_claim for unit tests"

requirements-completed: [R001, R002, R004, R006]

coverage:
  - id: D1
    description: DocumentReader applies FormatConverter.to_png before Docling; maps to extensible DocumentData
    requirement: R002
    verification:
      - kind: unit
        ref: tests/test_preprocessing/test_document.py#test_to_png_called_before_docling
        status: pass
      - kind: unit
        ref: tests/test_preprocessing/test_document.py#test_document_data_arbitrary_fields
        status: pass
    human_judgment: false
  - id: D2
    description: InformationExtractor + DescriptionReader extract BookingData using config model/prompt
    requirement: R006
    verification:
      - kind: unit
        ref: tests/test_preprocessing/test_extractor.py#test_extractor_schema_constrained_booking_data
        status: pass
      - kind: unit
        ref: tests/test_preprocessing/test_description.py#test_description_reader_extracts_booking_data
        status: pass
    human_judgment: false
  - id: D3
    description: Pipeline writes processed.json for all 25 claims; missing optionals OK
    requirement: R001
    verification:
      - kind: integration
        ref: tests/test_preprocessing/test_integration.py#test_pipeline_all_25_claims_write_processed_json
        status: pass
      - kind: unit
        ref: tests/test_preprocessing/test_pipeline.py#test_process_single_claim_missing_optional_files
        status: pass
    human_judgment: false
  - id: D4
    description: Claims without documents produce empty documents list (claim 21)
    requirement: R004
    verification:
      - kind: integration
        ref: tests/test_preprocessing/test_integration.py#test_spot_checks_key_claims
        status: pass
    human_judgment: false

duration: 10min
completed: 2026-09-25
status: complete
---

# Phase 01 Plan 03: Docling DocumentReader + InformationExtractor + pipeline Summary

**Full claim preprocessing pipeline: FormatConverter→Docling DocumentReader, config-driven LLM DescriptionReader, and run_pipeline writing processed.json for all 25 claims.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-09-25T10:15:02Z
- **Completed:** 2026-09-25T10:24:52Z
- **Tasks:** 5
- **Files modified:** 13

## Accomplishments
- DocumentReader converts rasters to PNG before Docling; PDFs pass through; output is extensible DocumentData
- InformationExtractor + DescriptionReader populate BookingData from description.txt using config.yaml model/prompt
- run_pipeline discovers all claim folders, soft-fails per file, writes 25× processed.json
- Unit suite (31) + Docling integration (3) pass; LLM skipped when Ollama unavailable

## Task Commits

Each task was committed atomically:

1. **Task 1: Add Docling (+ LLM client) dependencies** - `fee7e9a` (chore)
2. **Task 2: Implement DocumentReader (FormatConverter then Docling)** - `aaa0db2` (feat)
3. **Task 3: Implement InformationExtractor + DescriptionReader** - `07b8381` (feat)
4. **Task 4: Implement pipeline orchestrator** - `1a259a1` (feat)
5. **Task 5: Write unit + integration tests** - `dffe03f` (test)

**Plan metadata:** `694584a` (docs: complete plan)

## Files Created/Modified
- `src/compliance/preprocessing/document.py` — DocumentReader + DocumentPreprocessor
- `src/compliance/preprocessing/extractor.py` — InformationExtractor (ollama JSON)
- `src/compliance/preprocessing/description.py` — DescriptionReader retaining raw text
- `src/compliance/preprocessing/pipeline.py` — discover/classify/process/run_pipeline
- `src/compliance/preprocessing/__init__.py` — public exports including run_pipeline
- `tests/test_preprocessing/test_*.py` — unit + integration coverage
- `pyproject.toml` / `uv.lock` — docling dependency + pytest integration mark
- `.gitignore` — ignore generated `data/**/processed.json`

## Decisions Made
- PDF listed in `document_formats` skips FormatConverter and is passed to Docling directly (aligns with 01-02 FormatConverter limitation)
- Used existing `ollama` dependency with injectable `chat_fn` for tests; model name and prompt only from config
- Integration uses a passthrough DescriptionReader when Ollama is down; Docling still runs on real images

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Shipped unit tests with T02–T04**
- **Found during:** Tasks 2–4
- **Issue:** Plan lists tests under T05, but each task `<verify>` runs pytest on those modules
- **Fix:** Wrote `test_document.py`, `test_extractor.py`, `test_description.py`, `test_pipeline.py` with their feature tasks; T05 added integration + markers
- **Files modified:** tests under `tests/test_preprocessing/`
- **Verification:** Per-task pytest + mypy passed
- **Committed in:** `aaa0db2`, `07b8381`, `1a259a1`

**2. [Rule 2 - Missing Critical] PDF pass-through in DocumentReader**
- **Found during:** Task 2
- **Issue:** Plan says always `to_png` before Docling, but FormatConverter raises on PDF (01-02)
- **Fix:** Rasters call `to_png`; PDF paths go straight to Docling (documented + unit-tested)
- **Files modified:** `src/compliance/preprocessing/document.py`, `tests/test_preprocessing/test_document.py`
- **Verification:** `test_pdf_skips_format_converter` passes
- **Committed in:** `aaa0db2`

**3. [Rule 2 - Missing Critical] Gitignore generated processed.json**
- **Found during:** Task 5
- **Issue:** Integration writes 25× processed.json under data/; leaving them untracked pollutes status
- **Fix:** Added `data/**/processed.json` to `.gitignore`
- **Files modified:** `.gitignore`
- **Verification:** Files exist on disk; git ignores them
- **Committed in:** `dffe03f`

---

**Total deviations:** 3 auto-fixed (3× Rule 2)
**Impact on plan:** Required for verify gates, PDF correctness, and clean working tree; no scope creep.

## Issues Encountered
- Docling OCR often returns sparse/`<!-- image -->` text on some claim images; pipeline still emits DocumentData entries with confidence/HITL flags
- Ollama not reachable in this environment — description booking fields left empty in integration (raw description_text still retained)

## User Setup Required
Optional for richer description extraction: run Ollama locally with the model named in `config.yaml` (`llama3.2`). Pipeline works without it (logs/skips LLM fields).

## Next Phase Readiness
Milestone M001 preprocessing complete — `processed.json` available for downstream agents/rules. Phase verification / UAT can spot-check claim 1 and claim 16 outputs.

## Self-Check: PASSED
- Found: document.py, extractor.py, description.py, pipeline.py, five test modules
- Found commits: `fee7e9a`, `aaa0db2`, `07b8381`, `1a259a1`, `dffe03f`
- Verify: 31 unit + 3 integration tests passed; mypy clean on preprocessing package
