# God-object refactor quick tasks

Source tracker: `.gsd/refactor.md` (R16 remaining). One bullet = one `/gsd-quick` item.

- GO-001: Pass OcrRetryConfig (or SignatureDetectSettings) into detect_signature_with_yolo instead of unpacking signature_model/weights/confidence; update call sites in document.py and tests. Independent; no depends_on.
- GO-002: In PreprocessingPipeline._document_metadata_entries, construct ExtractionFailure from config.extraction_failure (not bare ExtractionFailure()); preserve empty-doc HITL behavior. Independent; no depends_on.
- GO-003: Decompose DocumentReader into composable Docling OCR / vision-retry / signature-verify / Benford collaborators with from_config (Phase 9 CheckSuite shape); preserve HITL flags and SignatureDetectionError. Blocks GO-004; files_modified centered on preprocessing/document.py and related tests.
- GO-004: Add ClaimReaders.from_config built once in PreprocessingPipeline.__init__; pass readers into _process_single_claim so DocumentReader/Docling are not rebuilt per claim. Depends on GO-003; touches claim_batch.py and pipeline.py.
