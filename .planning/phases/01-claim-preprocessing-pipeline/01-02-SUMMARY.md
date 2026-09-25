---
phase: 01-claim-preprocessing-pipeline
plan: 01-02
subsystem: preprocessing
tags: [pillow, abc, reader, markdown, format-converter]

requires:
  - phase: 01-claim-preprocessing-pipeline
    provides: GroundTruth / BookingData models and load_config
provides:
  - Reader and Preprocessor ABCs
  - FormatConverter (raster → PNG via Pillow)
  - AnswerReader → GroundTruth
  - MarkdownReader → BookingData with EN/ES key translation
affects:
  - 01-03-claim-preprocessing-pipeline

actuals:
  tokens: 13169
  tasks: 4
  commits: 4

plan_head_before: 9e0349096d8e394818b4384ad318b4f727f62dc9

tech-stack:
  added: [Pillow]
  patterns:
    - "Reader.read = _load → preprocessor.preprocess → _to_model"
    - "Markdown keys normalize (lower/collapse) then alias-translate to BookingData"
    - "FormatConverter PNG passthrough; other rasters write temp PNG"

key-files:
  created:
    - src/compliance/preprocessing/reader.py
    - src/compliance/preprocessing/preprocessing.py
    - src/compliance/preprocessing/answer.py
    - src/compliance/preprocessing/markdown.py
    - tests/test_preprocessing/test_format_converter.py
    - tests/test_preprocessing/test_answer.py
    - tests/test_preprocessing/test_markdown.py
  modified:
    - src/compliance/preprocessing/__init__.py
    - pyproject.toml
    - uv.lock

key-decisions:
  - "PDF listed in source_formats raises ValueError (Pillow cannot convert; S03 may pass through)"
  - "Answer/Markdown tests committed with their feature tasks so per-task verify could pass"
  - "Unknown markdown keys logged at WARNING and dropped"

patterns-established:
  - "Concrete readers default their Preprocessor in __init__"
  - "Absent BookingData/GroundTruth scalars filled with np.nan at _to_model"

requirements-completed: []

coverage:
  - id: D1
    description: Reader and Preprocessor ABCs with FormatConverter (webp/jpg → PNG, PNG passthrough)
    requirement: R002
    verification:
      - kind: unit
        ref: tests/test_preprocessing/test_format_converter.py#test_webp_to_png
        status: pass
      - kind: unit
        ref: tests/test_preprocessing/test_format_converter.py#test_png_passthrough
        status: pass
    human_judgment: false
  - id: D2
    description: AnswerReader maps minimal/standard/uncertain answer.json to GroundTruth with np.nan gaps
    requirement: R006
    verification:
      - kind: unit
        ref: tests/test_preprocessing/test_answer.py#test_answer_minimal
        status: pass
      - kind: unit
        ref: tests/test_preprocessing/test_answer.py#test_answer_uncertain
        status: pass
    human_judgment: false
  - id: D3
    description: MarkdownReader normalizes/translates EN+ES keys into BookingData; unknown keys warned and dropped
    requirement: R006
    verification:
      - kind: unit
        ref: tests/test_preprocessing/test_markdown.py#test_markdown_spanish_claim_22
        status: pass
      - kind: unit
        ref: tests/test_preprocessing/test_markdown.py#test_markdown_unknown_key_dropped
        status: pass
    human_judgment: false

duration: 3min
completed: 2026-09-25
status: complete
---

# Phase 01 Plan 02: Reader ABCs + FormatConverter + Answer/Markdown Summary

**Extensible Reader/Preprocessor ABCs with Pillow FormatConverter and Answer/Markdown readers that map to GroundTruth and BookingData (EN/ES key translation).**

## Performance

- **Duration:** 3 min
- **Started:** 2026-09-25T10:08:56Z
- **Completed:** 2026-09-25T10:12:01Z
- **Tasks:** 4
- **Files modified:** 11

## Accomplishments
- Defined Reader and Preprocessor ABCs plus FormatConverter (webp/jpg → PNG, PNG passthrough)
- AnswerReader covers minimal/standard/uncertain answer.json schemas with np.nan for missing optionals
- MarkdownReader extracts bold/plain KV pairs, translates EN/ES aliases to BookingData, warns on unknowns
- 15 unit tests pass; mypy clean on `src/compliance/preprocessing/`

## Task Commits

Each task was committed atomically:

1. **Task 1: Define Reader ABC, Preprocessor ABC, and FormatConverter** - `e7e99e8` (feat)
2. **Task 2: Implement AnswerReader + AnswerPreprocessor** - `bd30fac` (feat)
3. **Task 3: Implement MarkdownReader + MarkdownPreprocessor with key translation** - `f8519bf` (feat)
4. **Task 4: Write FormatConverter + Answer + Markdown tests** - `8a9f233` (test)

**Plan metadata:** (pending docs commit)

## Files Created/Modified
- `src/compliance/preprocessing/reader.py` — Reader ABC (load → preprocess → to_model)
- `src/compliance/preprocessing/preprocessing.py` — Preprocessor ABC + FormatConverter
- `src/compliance/preprocessing/answer.py` — AnswerReader / AnswerPreprocessor
- `src/compliance/preprocessing/markdown.py` — MarkdownReader / key normalize+translate
- `src/compliance/preprocessing/__init__.py` — Public exports
- `tests/test_preprocessing/test_format_converter.py` — Conversion/passthrough/error tests
- `tests/test_preprocessing/test_answer.py` — Schema variant tests
- `tests/test_preprocessing/test_markdown.py` — EN/ES/sparse/unknown-key tests
- `pyproject.toml` / `uv.lock` — Pillow dependency

## Decisions Made
- PDF in `source_formats` raises ValueError rather than a false Pillow conversion (S03 DocumentReader can special-case)
- Answer and Markdown unit tests shipped with their feature tasks so each task's `<verify>` (pytest) could pass before T04
- Unknown markdown keys are warning-logged and dropped (plan verification requirement)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Shipped answer/markdown tests with T02/T03**
- **Found during:** Task 2 / Task 3
- **Issue:** Plan lists all tests under T04, but T02/T03 `<verify>` runs pytest on those files
- **Fix:** Wrote `test_answer.py` with T02 and `test_markdown.py` with T03; T04 added FormatConverter tests and re-ran the full suite
- **Files modified:** `tests/test_preprocessing/test_answer.py`, `tests/test_preprocessing/test_markdown.py`
- **Verification:** 15 pytest passed across all three modules
- **Committed in:** `bd30fac`, `f8519bf`

---

**Total deviations:** 1 auto-fixed (Rule 2)
**Impact on plan:** Ordering-only; same test coverage as planned, no scope creep.

## Issues Encountered
None beyond the verify-ordering deviation above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
ABCs, FormatConverter, AnswerReader, and MarkdownReader are ready for plan 01-03 (DocumentReader/Docling, DescriptionReader, InformationExtractor, pipeline orchestration).

## Self-Check: PASSED
- Found: reader.py, preprocessing.py, answer.py, markdown.py, three test modules
- Found commits: `e7e99e8`, `bd30fac`, `f8519bf`, `8a9f233`
- Verify: 15 pytest passed; mypy clean on preprocessing package
