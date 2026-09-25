---
gsd_state_version: "1.0"
milestone: v1.0
current_phase: 5
current_phase_name: FastAPI Claims API
current_plan: Not started
status: executing
stopped_at: Phase 4 complete, ready to plan Phase 05
last_updated: "2026-09-25T15:57:29.652Z"
last_activity: 2026-09-25
last_activity_desc: Phase 4 complete, transitioned to Phase 05
state_head: ecd23ad5655c92fffa00e42279f2e9189a96317d
progress:
  total_phases: 6
  completed_phases: 4
  total_plans: 14
  completed_plans: 10
milestone_name: Claim Preprocessing
---

# Project State

## Project Reference

See: .planning/PROJECT.md

**Current focus:** Phase 05 — FastAPI Claims API

## Current Position

Phase: 5 (FastAPI Claims API) — READY TO EXECUTE
Current Plan: Not started
Total Plans in Phase: 4
Status: Ready to execute
Last activity: 2026-09-25 — Phase 4 complete (verified 9/9), transitioned to Phase 05

Progress: [████████░░] 80% (4/5 phases complete)

## Accumulated Context

### Roadmap Evolution

- Phase 6 added: Prediction Evaluation — `src/evaluation` Evaluator compares predictions vs answer.json; confusion matrix, accuracy, F1
- Phase 5 added: FastAPI Claims API — `src/api` with POST/GET /claims; single-claim + batch pipeline refactor; pipelines as FastAPI resources
- Phase 2 added: Case Classifier Models — Classifier ABC + CaseClassifier for description.txt → config-driven coverage labels with probabilities (Trip cancellation/rescheduling, Personal Effects, Missed Departure/Connection, Other)
- Phase 3 added: Preprocessing Pipeline Orchestration — workflows/pipeline.py + main entrypoint writing mirrored preprocessed/ (description.txt, answer.json, supporting_document.json, supporting_documents.md)
- Phase 4 added: Claim Analysis Pipeline — ClaimPipeline LangGraph over preprocessed data; coverage/reason/document classifiers + Checker; local LLM config
- Phase 4 planned: 04-01..04-04 (Wave 0 langgraph+AnalysisConfig → tracer cancellation → PE/missed → batch/CLI)

### Roadmap Evolution

- Phase 2 added: Case Classifier Models — Classifier ABC + CaseClassifier for description.txt → config-driven coverage labels with probabilities (Trip cancellation/rescheduling, Personal Effects, Missed Departure/Connection, Other)
- Phase 3 added: Preprocessing Pipeline Orchestration — workflows/pipeline.py + main entrypoint writing mirrored preprocessed/ (description.txt, answer.json, supporting_document.json, supporting_documents.md)
- Phase 4 added: Claim Analysis Pipeline — ClaimPipeline LangGraph over preprocessed data; coverage/reason/document classifiers + Checker; local LLM config

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
- [Phase 04]: Task 1 approved langgraph (LangChain) legitimacy before uv add (T-04-SC)
- [Phase 04]: analysis other_label is string None; Phase 02 classification.other_label Other preserved
- [Phase 04]: analysis_result.json externalized on PreprocessedArtifactNames
- [Phase 04]: PE/missed coverage routes stub to END until 04-03; cancellation path fully wired
- [Phase 04]: Cancellation coverage label taken from config.analysis.coverage.labels[0]
- [Phase 04]: Path safety validated in analyze_claim (Task 1) with dedicated Task 2 Nyquist test
- [Phase 04]: PE/missed document classifiers use supporting_document_text + stage configs
- [Phase 04]: other_label routes to persist; checker keys omitted when Checker skipped
- [Phase 04]: Unknown coverage after allow-list treated as other_label → persist (T-04-03)
- [Phase 04]: Reuse _discover_claim_folders for ClaimPipeline.run batch discovery
- [Phase 04]: CLI --mode analyze on main; preprocess remains default

### Blockers/Concerns

None.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260925-mqh | after ExtractionFailure a retry with an expensive model should be done | 2026-09-25 | 87de07c | [260925-mqh-after-extractionfailure-a-retry-with-an-](./quick/260925-mqh-after-extractionfailure-a-retry-with-an-/) |
| 260925-mol | Checker class: modes containment (deterministic normalize+lowercase then LLM) and contradicts (LLM: True if claim contradicts text, False if supported); takes input and checks against a text | 2026-09-25 | 47de8d6 | [260925-mol-checker-class-modes-containment-determin](./quick/260925-mol-checker-class-modes-containment-determin/) |

## Session Continuity

Last session: 2026-09-25T15:36:50.687Z
Stopped at: Phase 4 complete, ready to plan Phase 05
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
| Phase 04 P01 | 3min | 3 tasks | 14 files |
| Phase 04 P02 | 4min | 2 tasks | 4 files |
| Phase 04 P03 | 3min | 2 tasks | 5 files |
| Phase 04 P04 | 3min | 2 tasks | 6 files |
