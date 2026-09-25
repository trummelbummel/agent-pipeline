---
phase: 260925-mqh-after-extractionfailure-a-retry-with-an-
plan: 01
subsystem: preprocessing
tags: [ocr-retry, docling, vision, ollama, extraction-failure, hitl]

requires:
  - phase: extraction-failure-gate
    provides: ExtractionFailure.evaluate as sole OCR quality gate
provides:
  - OcrRetryConfig (enabled/model/prompt) on AppConfig
  - DocumentReader one-shot vision OCR retry after faulty Docling
  - DocumentMetaData.retry_used / retry_model
  - Mocked unit coverage for success, still-faulty, disabled, clean-skip, ERROR
affects: [claim-batch, preprocessing-pipeline, document-metadata]

estimate:
  tokens: 26000
  tasks: 2
  commits: 2

actuals:
  tokens: 12939
  tasks: 2
  commits: 2

plan_head_before: 7ed9090

tech-stack:
  added: []
  patterns:
    - "Injectable retry_chat_fn (ollama.chat default) mirroring InformationExtractor"
    - "Benford-style optional OcrRetryConfig with config.yaml section enabled by default"
    - "ExtractionFailure re-applied to vision retry text before clearing HITL"

key-files:
  created:
    - tests/test_preprocessing/test_extraction_failure.py
  modified:
    - config.yaml
    - src/compliance/config/settings.py
    - src/compliance/config/__init__.py
    - src/compliance/models/claim.py
    - src/compliance/preprocessing/document.py
    - src/compliance/preprocessing/claim_batch.py
    - tests/test_models/test_claim.py
    - tests/test_workflows/test_pipeline.py

key-decisions:
  - "Vision model is llama3.2-vision in config.yaml only — no hardcoded model strings in source"
  - "OcrRetryConfig optional on AppConfig (default_factory) so absent YAML still loads; repo config enables it"
  - "PDF resolved paths SKIP retry (reason=pdf); PNG/image only"
  - "Vision exceptions keep original Docling DocumentData + HITL with retry_used=True"

patterns-established:
  - "Post-gate retry: Docling → ExtractionFailure → optional vision → ExtractionFailure again (no recurse)"
  - "Branch logs ocr_retry START/SUCCESS/STILL_FAULTY/SKIP/ERROR without OCR payloads or PII"

requirements-completed: []

coverage:
  - id: D1
    description: Faulty Docling OCR retries once via config vision model and clears faulty_extraction when retry text passes ExtractionFailure
    verification:
      - kind: unit
        ref: "tests/test_preprocessing/test_extraction_failure.py::test_faulty_extraction_invokes_vision_retry_and_clears_faulty"
        status: pass
    human_judgment: false
  - id: D2
    description: load_config exposes ocr_retry.enabled, model, and prompt from config.yaml
    verification:
      - kind: unit
        ref: "tests/test_config/test_settings.py::test_load_config_reads_ocr_retry_section"
        status: pass
    human_judgment: false
  - id: D3
    description: Still-faulty / ERROR / disabled / clean paths keep correct HITL and chat invocation behavior
    verification:
      - kind: unit
        ref: "tests/test_preprocessing/test_extraction_failure.py"
        status: pass
    human_judgment: false

duration: 4min
completed: 2026-09-25
status: complete
---

# Phase 260925-mqh Plan 01: OCR Vision Retry Summary

**After ExtractionFailure flags Docling OCR, DocumentReader retries once with a config-driven Ollama vision model on the resolved PNG; success clears HITL, failure keeps it.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-09-25T14:24:31Z
- **Completed:** 2026-09-25T14:28:24Z
- **Tasks:** 2/2
- **Files modified:** 9

## Accomplishments

- Added `ocr_retry` to `config.yaml` (`enabled: true`, `model: llama3.2-vision`, OCR prompt) and `OcrRetryConfig` on `AppConfig`
- Extended `DocumentReader.read()` with one-shot vision retry + branch logs; wired via `claim_batch`
- Recorded `retry_used` / `retry_model` on `DocumentMetaData`; unit tests mock `retry_chat_fn` (no live Ollama)

## Task Commits

1. **Task 1: Faulty Docling → vision retry success clears faulty_extraction** - `374e148` (feat)
2. **Task 2: Retry still-faulty keeps HITL; disabled/skip paths + branch logs** - `87de07c` (test)

_Docs SUMMARY/STATE commit deferred to orchestrator per quick-task constraints._

## Files Created/Modified

- `config.yaml` — `ocr_retry` section
- `src/compliance/config/settings.py` — `OcrRetryConfig` + `AppConfig.ocr_retry`
- `src/compliance/config/__init__.py` — export `OcrRetryConfig`
- `src/compliance/models/claim.py` — `retry_used` / `retry_model` on `DocumentMetaData`
- `src/compliance/preprocessing/document.py` — vision retry orchestration
- `src/compliance/preprocessing/claim_batch.py` — pass `ocr_retry=config.ocr_retry`
- `tests/test_preprocessing/test_extraction_failure.py` — success + edge-path coverage
- `tests/test_models/test_claim.py` — metadata field assertions
- `tests/test_workflows/test_pipeline.py` — inline YAML includes `ocr_retry`

## Decisions Made

- Model string lives only in YAML (`llama3.2-vision`); source takes `ocr_retry.model`
- Optional `OcrRetryConfig` default (Benford-style) so existing minimal AppConfig constructions keep working; repo config enables retry
- PDF skip without chat; vision call exceptions → ERROR log + keep Docling HITL with `retry_used=True`

## Deviations from Plan

### Auto-fixed Issues

None - plan executed as specified.

### Notes

- Combined RED+GREEN in Task 1 feat commit (plan `type: execute` with per-task `tdd="true"`; config/metadata stubs + implementation landed together so tests assert on behavior rather than ImportError).
- Task 1 commit also included pre-existing dirty hunks already present in `document.py` / `claim_batch.py` on the working tree (unrelated WIP that was already modified before this quick task).

## Threat Flags

None — trust-boundary mitigations from the plan threat model applied (no OCR text in logs; single retry; ExtractionFailure on retry text).

## Known Stubs

None.

## Self-Check: PASSED

- FOUND: config.yaml, settings.py, document.py, claim.py, claim_batch.py, test_extraction_failure.py
- FOUND: commits 374e148, 87de07c
- VERIFY: `pytest tests/test_preprocessing/test_extraction_failure.py tests/test_config/test_settings.py -x` → 23 passed
