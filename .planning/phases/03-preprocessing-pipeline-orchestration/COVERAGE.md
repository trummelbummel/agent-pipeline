# API Coverage — Phase 03

**Verdict:** no external API / SDK integration in this phase.

Phase 03 adds a `workflows/` orchestration layer that composes Phase 1 Readers/Preprocessors and writes a mirrored `preprocessed/` tree. It does not introduce new vendor APIs, REST/GraphQL clients, or SDK surfaces. Docling and Ollama remain Phase 1 concerns; this phase only invokes existing injectable reader seams (same test doubles as `tests/test_preprocessing/test_pipeline.py`).
