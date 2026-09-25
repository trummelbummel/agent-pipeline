---
gsd_state_version: "1.0"
milestone: v1.0
current_phase: 2
current_phase_name: Case Classifier Models
current_plan: Not started
status: ready
stopped_at: Phase 03 added — not planned yet
last_updated: "2026-09-25T11:49:10.851Z"
last_activity: 2026-09-25
last_activity_desc: Phase 03 added (Preprocessing Pipeline Orchestration)
state_head: 61a3dabad4496075f1422685af0826b6b29c8225
progress:
  total_phases: 3
  completed_phases: 1
  total_plans: 4
  completed_plans: 3
milestone_name: Claim Preprocessing
---

# Project State

## Project Reference

See: .planning/PROJECT.md

**Current focus:** Phase 02 — Case Classifier Models

## Current Position

Phase: 2 (Case Classifier Models) — READY TO EXECUTE
Current Plan: Not started
Total Plans in Phase: 1
Status: ready
Last activity: 2026-09-25 — Phase 03 added

Progress: [███·······] 33%

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

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-09-25T11:25:00.000Z
Stopped at: Phase 02 added — not planned yet
Resume file: None

## Performance Metrics

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 01 P01-01 | 6min | 3 tasks | 12 files |
| Phase 01 P02 | 3min | 4 tasks | 11 files |
| Phase 01 P03 | 10min | 5 tasks | 13 files |
