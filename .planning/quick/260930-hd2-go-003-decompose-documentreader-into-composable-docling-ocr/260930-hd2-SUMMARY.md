---
phase: 260930-hd2-go-003-decompose-documentreader-into-composable-docling-ocr
plan: 01
subsystem: preprocessing
tags: [document-reader, composition, r16, from_config, docling, ocr-retry, benford]
quick_id: 260930-hd2

requires:
  - phase: GO-001
    provides: OcrRetryConfig passed into detect_signature_with_yolo
provides:
  - DocumentReader.from_config composing DoclingPrimaryOcr / VisionOcrRetry / SignatureVerifier / BenfordGate
affects: [GO-004 ClaimReaders once-per-pipeline]

actuals:
  tokens: 25417
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Phase 9 CheckSuite shape: from_config(section, deps) + small collaborators; DocumentReader orchestrates only"

key-files:
  created: []
  modified:
    - src/compliance/preprocessing/document.py
    - src/compliance/preprocessing/claim_batch.py
    - tests/test_preprocessing/test_document.py
    - tests/test_preprocessing/test_extraction_failure.py
    - .planning/refactor.md
    - LOGIC.md

key-decisions:
  - "Collaborators live in document.py (prefer edit existing file); DocumentReader.__init__ takes only collaborator objects"
  - "from_config takes prep / ocr_retry / extraction_failure sections plus injectable deps — no same-kind knob fan-out"
  - "claim_batch still builds per claim (GO-004 owns once-per-pipeline lifetime)"

patterns-established:
  - "DocumentReader.from_config(PreprocessingConfig, OcrRetryConfig, ExtractionFailure|Config, **deps)"

requirements-completed: []

coverage:
  - id: D1
    description: DocumentReader decomposed into DoclingPrimaryOcr, VisionOcrRetry, SignatureVerifier, BenfordGate with from_config
    verification:
      - kind: unit
        ref: "tests/test_preprocessing/test_document.py"
        status: pass
      - kind: unit
        ref: "tests/test_preprocessing/test_extraction_failure.py"
        status: pass
      - kind: other
        ref: "make test"
        status: pass
    human_judgment: false

duration: 4min
completed: 2026-09-30
status: complete
plan_head_before: 4676b740aa51adbaee28e555543b52e4f0ca3b93
commits: 2
---

# Phase 260930-hd2 Plan 01: Decompose DocumentReader Summary

**`DocumentReader` is no longer a 10-param god constructor — it orchestrates Docling / vision-retry / signature / Benford collaborators built via `from_config`.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-09-30T11:33:03Z
- **Completed:** 2026-09-30T11:37:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Split `DocumentReader` into `DoclingPrimaryOcr`, `VisionOcrRetry`, `SignatureVerifier`, and `BenfordGate` (Phase 9 shape).
- Production construction is `DocumentReader.from_config(prep, ocr_retry, extraction_failure, **deps)`.
- OCR text, HITL, Benford early DENY, vision retry, and `SignatureDetectionError` raise-through preserved (`make test`: 499 passed).
- GO-003 checked off in `.planning/refactor.md` and `.gsd/refactor.md` (gitignored).

## Task Commits

1. **Task 1: Extract collaborators** - `9de4df0` (refactor)
2. **Task 2: Preserve contract + wire call sites** - `203a686` (refactor)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Accidental BATCH.json in Task 1 commit**
- **Found during:** Task 1 commit (pre-staged index)
- **Issue:** `.planning/quick-batches/260930-hcz/BATCH.json` landed in Task 1 despite constraint not to write it.
- **Fix:** Removed in Task 2 commit.
- **Files modified:** `.planning/quick-batches/260930-hcz/BATCH.json` (deleted)
- **Commit:** `203a686`

**2. [Scope] Pre-existing LOGIC.md WIP staged with GO-003 note**
- **Found during:** Task 2
- **Issue:** `LOGIC.md` already had unstaged algorithm-doc edits; `git add LOGIC.md` included them along with the DocumentReader.from_config note.
- **Fix:** Left as-is (docs only; GO-003 note is present). No code impact.
- **Files modified:** `LOGIC.md`
- **Commit:** `203a686`

## Self-Check: PASSED

- `src/compliance/preprocessing/document.py` — FOUND
- `9de4df0` — FOUND
- `203a686` — FOUND
- `make test` — 499 passed, 3 deselected
