# Remaining God-Object Refactors (R16)

Tracked: 2026-09-30
Source: style-review R16 (`config-fan-out-god-object`) after Phase 9 compositional checker refactor
Rule: `CLAUDE.md` §Composition · style-review checklist R16

## Already done (this session)

| ID | Site | Fix |
|----|------|-----|
| GO-000a | `ClaimPipeline` stage classifiers | Built once via `CaseClassifier.from_config` |
| GO-000b | `api/routes_claims.py` artifact filenames | Helpers take `PreprocessedArtifactNames` |
| GO-000c | `PreprocessingPipeline._write_document_pngs` | `FormatConverter` built once in `__init__` |
| Phase 9 | `llm/checker.Checker` | Decomposed into `compliance.llm.checks` + `policy/gates` |

## Remaining

### [x] GO-001: Pass OCR-retry section into YOLO signature detect

**Signals:** R16-1 (field fan-out)
**Sites:** `src/compliance/preprocessing/document.py` (`_run_signature_detect`), `src/compliance/preprocessing/signature_detect.py` (`detect_signature_with_yolo`)

**Work**

- Stop unpacking `ocr_retry.signature_model` / `signature_weights` / `signature_confidence` at the call site.
- Pass `OcrRetryConfig` (or a small `SignatureDetectSettings` extracted from it) into `detect_signature_with_yolo`.
- Update tests that construct the helper with three kwargs.

**Done when**

- No call site fans out 3+ fields of `ocr_retry` into YOLO.
- `make test` green; mypy/ruff clean on touched files.

**Quick:** independent — no depends_on.

---

### [x] GO-002: Use configured ExtractionFailure thresholds in empty-doc HITL

**Signals:** R16-related (ignores config section)
**Site:** `src/compliance/workflows/pipeline.py` (`_document_metadata_entries`)

**Work**

- Replace `ExtractionFailure()` with `ExtractionFailure(self._config.extraction_failure)` (or a detector built once on the pipeline).
- Keep the `"_none_"` empty-doc HITL behavior; only the thresholds change.

**Done when**

- Empty-doc metadata path uses `config.extraction_failure`.
- Existing empty-doc tests still pass (or are updated for config-aware thresholds).

**Quick:** independent — no depends_on.

---

### [ ] GO-003: Decompose DocumentReader into composable OCR / retry / signature / Benford pieces

**Signals:** R16-2 (wide constructor), R16-4 (mixed layers)
**Site:** `src/compliance/preprocessing/document.py` (`DocumentReader`)

**Work**

- Split the 10-parameter god reader into small collaborators behind clear seams, e.g.:
  - Docling primary OCR
  - Vision OCR retry (shared chat client + `OcrRetryConfig`)
  - Signature verify (detector + retry/signature settings)
  - Optional Benford gate
- Prefer `DocumentReader.from_config(section, deps)` (or composition at the pipeline/batch root) over field fan-out.
- Preserve public read behavior, HITL flags, and error types (`SignatureDetectionError`, etc.).
- Follow Phase 9 shape: shared client for transport; one small class per behavior.

**Done when**

- `DocumentReader` no longer owns transport + YOLO + Benford + Docling as one flat constructor of same-kind knobs.
- `make test` green (esp. preprocessing / extraction_failure / signature tests).

**Quick:** depends on nothing; **blocks GO-004**.

---

### [ ] GO-004: Build claim readers once (`ClaimReaders.from_config`) — not per claim

**Signals:** R16-1, R16-5 (per-item rebuild; expensive Docling converter)
**Sites:** `src/compliance/preprocessing/claim_batch.py` (`_process_single_claim`), `src/compliance/workflows/pipeline.py` (`PreprocessingPipeline`)

**Work**

- Introduce `ClaimReaders.from_config(AppConfig, **overrides)` holding `AnswerReader`, `MarkdownReader`, `DescriptionReader` / `InformationExtractor`, `DocumentReader`, optional `BenfordLawChecker`, `ExtractionFailure`, `FormatConverter`.
- Build once in `PreprocessingPipeline.__init__` (and batch entry); pass into `_process_single_claim`.
- Keep test injection seams (`document_reader=`, etc.).

**Done when**

- Batch / pipeline no longer construct `DocumentReader` (and Docling converter) per claim when overrides are absent.
- `make test` green.

**Quick:** **depends on GO-003** (compose the decomposed reader).

---

## Quick-batch task list

Executable descriptions for `/gsd-quick-batch --file` (also mirrored under `.planning/refactor-god-objects-tasks.md`):

1. GO-001: Pass OcrRetryConfig (or SignatureDetectSettings) into detect_signature_with_yolo instead of unpacking signature_model/weights/confidence; update call sites and tests. Independent.
2. GO-002: In PreprocessingPipeline._document_metadata_entries, construct ExtractionFailure from config.extraction_failure (not bare ExtractionFailure()); preserve empty-doc HITL. Independent.
3. GO-003: Decompose DocumentReader into composable Docling OCR / vision retry / signature verify / Benford collaborators with from_config; preserve HITL and errors. Blocks GO-004.
4. GO-004: Add ClaimReaders.from_config built once in PreprocessingPipeline; pass into _process_single_claim so DocumentReader is not rebuilt per claim. Depends on GO-003.

## Execution notes

- Pattern rule encoded in `CLAUDE.md` §Composition and style-review **R16**.
- Prefer `--jobs 1` or natural DAG layers so GO-004 waits for GO-003.
- Behavior-preserving: OCR outcomes, HITL, signature errors, and Benford early DENY must not change.
