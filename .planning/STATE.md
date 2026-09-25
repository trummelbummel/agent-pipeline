---
gsd_state_version: "1.0"
milestone: v1.0
current_phase: 03
current_phase_name: Preprocessing Pipeline Orchestration
current_plan: 2
status: verifying
stopped_at: Completed 03-02-PLAN.md
last_updated: "2026-09-25T12:14:32.408Z"
last_activity: 2026-09-25
last_activity_desc: Completed 03-02 batch orchestration and main entrypoint
state_head: 5024263d8680bf9b76b432d5ab5efcbaa709e429
progress:
  total_phases: 3
  completed_phases: 1
  total_plans: 6
  completed_plans: 6
milestone_name: Claim Preprocessing
---

# Project State

## Project Reference

See: .planning/PROJECT.md

**Current focus:** Phase 03 — Preprocessing Pipeline Orchestration

## Current Position

Phase: 03 — Preprocessing Pipeline Orchestration
Current Plan: 2
Total Plans in Phase: 2
Status: Phase complete — ready for verification
Last activity: 2026-09-25 — Completed 03-02 batch orchestration and main entrypoint

Progress: [██████████] 100%

## Accumulated Context

### Roadmap Evolution

- Phase 2 added: Case Classifier Models — Classifier ABC + CaseClassifier for description.txt → config-driven coverage labels with probabilities (Trip cancellation/rescheduling, Personal Effects, Missed Departure/Connection, Other)
- Phase 3 added: Preprocessing Pipeline Orchestration — workflows/pipeline.py + main entrypoint writing mirrored preprocessed/ (description.txt, answer.json, supporting_document.json, supporting_documents.md)

### Decisions

See .planning/DECISIONS.md (D001–D008)

- [Phase 1]: NanAwareModel + NanStr/NanFloat for np.nan defaults with JSON null round-trip
- [Phase 1]: DocumentData uses fields dict plus extra=allow (D008)
- [Phase 1]: Extraction model/prompt live only in config.yaml (default llama3.2)
- [Phase 1]: PDF in FormatConverter source_formats raises ValueError (Pillow cannot convert)
- [Phase 1]: Unknown markdown keys logged at WARNING and dropped
- [Phase 1]: PDF skips FormatConverter; passed through to Docling
- [Phase 1]: InformationExtractor uses ollama.chat with config model/prompt; injectable chat_fn for tests
- [Phase 1]: Integration skips live LLM when Ollama unavailable; Docling runs on real data/
- [Phase 02]: Mirror InformationExtractor injectable chat_fn for CaseClassifier — Same LLM seam as Phase 1; unit tests without live Ollama
- [Phase 02]: Other is config other_label in same vocabulary — Not a second identity model; ROADMAP Other fallback
- [Phase 02]: AppConfig requires classification section — R009 externalization; missing section raises ValidationError
- [Phase 03]: Extend PreprocessingConfig.preprocessed_dir instead of a separate workflows AppConfig section
- [Phase 03]: Refuse claim_dir.name with path separators or .. before any mkdir/write (T-03-03)
- [Phase 03]: Soft-fail test raises via answer_reader (Phase 1 soft-catches document_reader)
- [Phase 03]: main tested via monkeypatch of run_preprocessing_workflow; no console_scripts added

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-09-25T12:14:32.394Z
Stopped at: Completed 03-02-PLAN.md
Resume file: None

## Performance Metrics

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 01 P01-01 | 6min | 3 tasks | 12 files |
| Phase 01 P02 | 3min | 4 tasks | 11 files |
| Phase 01 P03 | 10min | 5 tasks | 13 files |
| Phase 02 P01 | 4 min | 3 tasks | 9 files |
| Phase 03 P01 | 4min | 3 tasks | 9 files |
| Phase 03 P02 | 3min | 2 tasks | 6 files |
