---
status: complete
quick_id: 260930-hd1
completed: 2026-09-30
---

# GO-002 Summary

`PreprocessingPipeline` builds `ExtractionFailure(config.extraction_failure)` once.
`_document_metadata_entries` / `_document_metadata_json_text` take that detector;
empty-doc HITL no longer uses bare `ExtractionFailure()`. Tests:
`tests/test_workflows/test_pipeline.py` green.
