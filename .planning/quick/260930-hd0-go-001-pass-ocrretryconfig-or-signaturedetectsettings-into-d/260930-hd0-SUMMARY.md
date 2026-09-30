---
status: complete
quick_id: 260930-hd0
completed: 2026-09-30
---

# GO-001 Summary

`detect_signature_with_yolo(image_path, ocr_retry: OcrRetryConfig)` — no more
`model=` / `weights=` / `confidence=` fan-out. `DocumentReader._run_signature_detect`
passes the section. Tests: `tests/test_preprocessing/test_document.py` green.
