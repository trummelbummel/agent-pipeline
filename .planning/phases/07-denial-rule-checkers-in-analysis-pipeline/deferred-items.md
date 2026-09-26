# Deferred items — Phase 07

## Out of scope (discovered during 07-00)

| Item | File | Notes |
|------|------|-------|
| `test_analysis_coverage_other_label_is_false` expects `other_label == "False"` but config has `"None"` | `tests/test_config/test_settings.py` | Pre-existing mismatch vs `config.yaml`; not caused by Wave 0 stubs |
| `test_load_config_reads_ocr_retry_section` expects `on_missing_signature` on `OcrRetryConfig` | `tests/test_config/test_settings.py` | Attribute absent on current model; pre-existing |
