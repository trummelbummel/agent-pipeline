---
gsd_state_version: "1.0"
milestone: v1.0
current_phase: 07
current_phase_name: Denial-rule checkers in analysis pipeline
current_plan: 4
status: executing
stopped_at: Completed 07-01b-PLAN.md
last_updated: "2026-09-26T11:02:12.231Z"
last_activity: 2026-09-26
last_activity_desc: Phase 07 execution started
state_head: 5fad9121ddb1bf78e3fd692668d72d3963a43472
progress:
  total_phases: 8
  completed_phases: 4
  total_plans: 21
  completed_plans: 19
milestone_name: Claim Preprocessing
---

# Project State

## Project Reference

See: .planning/PROJECT.md

**Current focus:** Phase 07 — Denial-rule checkers in analysis pipeline

## Current Position

Phase: 07 (Denial-rule checkers in analysis pipeline) — EXECUTING
Current Plan: 4
Total Plans in Phase: 5
Status: Ready to execute
Last activity: 2026-09-26 — Phase 07 execution started

Progress: [████████░░] 80% (4/5 phases complete; Phase 05 plans 3/4)

## Accumulated Context

### Roadmap Evolution

- Phase 8 added: Engineering improvements from `.gsd/IMPROVEMENTS.md` — prioritized decision safety, result integrity, evaluation validity, evidence association, API/configuration hardening, and policy-engine maintainability
- Phase 7 added: Denial-rule checkers in analysis pipeline — extend ClaimPipeline Checker steps for LOGIC.md deny rules not covered by containment/contradicts (missing doc, healthy cert, identity, authenticity, incomplete, suspicious dating)
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
- [Phase 06]: Unknown pred/gt decisions raise ValueError at evaluate_claim boundary
- [Phase 06]: evaluation package at src/evaluation (hatch); scores predicted_answer vs answer.json only
- [Phase 06]: Public batch API named evaluate(); soft-skip unsafe/missing pairs; always write metrics JSON including empty batch
- [Phase 05]: User approved FastAPI stack legitimacy (fastapi/uvicorn/python-multipart/httpx) despite SUS downloads-metadata seam
- [Phase 05]: Kept src/evaluation in hatch packages and added src/api alongside it
- [Phase 05]: Probe lifespan tests call deps with Request (Annotated Depends breaks under future annotations in nested test fns)
- [Phase 05]: 409 conflict test patches _next_claim_id to simulate TOCTOU against max+1 id scheme
- [Phase 05]: Image path hardened with resolve().is_relative_to(claim_dir) after basename coerce
- [Phase 05]: List response is a bare list[ClaimListItem] array (not a wrapper model)
- [Phase 05]: Absent optional artifacts serialize as null on ClaimListItem / ClaimDecision.predicted_answer
- [Phase 05]: Unsafe claim_id tested via percent-encoded %2E%2E so the segment reaches the handler
- [Phase 05]: CLI --claim-id always runs process_then_analyze (same as GET); mode only applies to batch run(None)
- [Phase 05]: ClaimPipeline loads from claim_dir when supporting_document artifact present; else preprocessed_root/name
- [Phase 05]: Date UNCERTAIN checkers: departure_within_days (n from config) and multiple_document_dates short-circuit LLM Checker before DENY
- [Phase 07]: Wave 0 xfail strict=False for R027–R029 Nyquist stubs until 07-01/07-02
- [Phase 07]: Canonical keys: checker_document_not_authentic, checker_incomplete_document, checker_suspicious_dating
- [Phase 07]: not_authentic OCR layout mirrors healthy; deny-on-True parse failure fail-closed True
- [Phase 07]: A7/A10/A11: not_authentic fail-closed + medical signature_required_codes gate; key checker_document_not_authentic
- [Phase 07]: incomplete_prompt stored in 07-01; incomplete mode dispatch deferred to 07-02
- [Phase 07]: Secondary CheckingConfig helpers use authenticity/incomplete placeholders matching 07-01

### Blockers/Concerns

None.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260926-gij | Create common fixtures across API tests and update dedup-review fixture detection | 2026-09-26 | 3c1582d | [260926-gij-create-common-fixtures-across-api-tests-](./quick/260926-gij-create-common-fixtures-across-api-tests-/) |
| 260926-fph | Add two analysis checkers that yield UNCERTAIN (departure proximity; multiple OCR dates) | 2026-09-26 | cbfa126 | [260926-fph-add-two-analysis-checkers-that-yield-unc](./quick/260926-fph-add-two-analysis-checkers-that-yield-unc/) |
| 260926-f9c | In evaluation, also run statistics over analysis_result.json and visualize as bar charts | 2026-09-26 | c0b13ea | [260926-f9c-in-evaluation-also-run-statistics-over-a](./quick/260926-f9c-in-evaluation-also-run-statistics-over-a/) |
| 260926-bwk | Fix the stale prediction issue: preprocess must not delete analysis-authored predicted_answer | 2026-09-26 | aa87ffb | [260926-bwk-fix-the-stale-prediction-issue-preproces](./quick/260926-bwk-fix-the-stale-prediction-issue-preproces/) |
| 260925-mqh | after ExtractionFailure a retry with an expensive model should be done | 2026-09-25 | 87de07c | [260925-mqh-after-extractionfailure-a-retry-with-an-](./quick/260925-mqh-after-extractionfailure-a-retry-with-an-/) |
| 260925-mol | Checker class: modes containment (deterministic normalize+lowercase then LLM) and contradicts (LLM: True if claim contradicts text, False if supported); takes input and checks against a text | 2026-09-25 | 47de8d6 | [260925-mol-checker-class-modes-containment-determin](./quick/260925-mol-checker-class-modes-containment-determin/) |

## Session Continuity

Last session: 2026-09-26T11:02:12.199Z
Stopped at: Completed 07-01b-PLAN.md
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
| Phase 06 P01 | 5 min | 2 tasks | 15 files |
| Phase 06 P02 | 2 min | 2 tasks | 6 files |
| Phase 05 P00 | 1min | 3 tasks | 8 files |
| Phase 05 P01 | 5min | 3 tasks | 7 files |
| Phase 05 P02 | 6min | 3 tasks | 7 files |
| Phase 05 P03 | 7min | 2 tasks | 7 files |
| Phase 260926-fph P01 | 8min | 2 tasks | 5 files |
| Phase 07 P00 | 3min | 2 tasks | 4 files |
| Phase 07-denial-rule-checkers-in-analysis-pipeline P01 | 7min | 1 tasks | 9 files |
| Phase 07 P01b | 3min | 1 tasks | 8 files |
