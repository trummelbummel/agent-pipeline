# Roadmap

## Milestones

- 🔄 **v1.0 Claim Preprocessing** — Parse claim folders into structured processed.json

## Phases

- [x] **Phase 01: Claim Preprocessing Pipeline** `profiles: []` (completed 2026-09-25)
  Plans: 01-01, 01-02, 01-03
  Goal: Parse all 25 insurance claim folders into structured processed.json via Reader/Preprocessor ABCs, FormatConverter→PNG→Docling, and InformationExtractor
  Success criteria:
  - All 25 claims produce valid processed.json
  - DocumentData (person, date, + arbitrary fields) from Docling path
  - Config externalized; mypy + pytest pass

- [x] **Phase 02: Case Classifier Models** `profiles: []` (completed 2026-09-25)
  Plans: 02-01
  Goal: Add `src/compliance/models/classifier.py` with Classifier ABC and CaseClassifier child that classifies description.txt into config-driven coverage labels with probability estimates
  Success criteria:
  - Classifier ABC defines classify interface returning labels + probabilities
  - CaseClassifier classifies description.txt text into: Trip cancellation or rescheduling, Personal Effects, Missed Departure or Missed Connection, or Other
  - Labels (and fallback Other) are configurable via config.yaml
  - mypy + pytest pass

- [x] **Phase 03: Preprocessing Pipeline Orchestration** `profiles: []` (completed 2026-09-25)
  Plans: 03-01, 03-02
  Goal: Add `workflows/pipeline.py` that reads + preprocesses all claim files and writes a mirrored `preprocessed/` tree; add a main entrypoint to run the full pipeline
  Success criteria:
  - `src/compliance/workflows/pipeline.py` orchestrates Reader + Preprocessor over all claims
  - Output under `preprocessed/` mirrors claim folder structure
  - Each claim emits description.txt, answer.json, supporting_document.json, supporting_documents.md
  - Runnable main entrypoint executes all preprocessing steps
  - mypy + pytest pass

- [ ] **Phase 04: Claim Analysis Pipeline** `profiles: []`
  Plans: 04-01, 04-02, 04-03, 04-04
  Goal: ClaimPipeline LangGraph over preprocessed claims — coverage/reason/document classifiers + Checker, local LLM
  Success criteria:
  - ClaimPipeline is a LangGraph that loads preprocessed claim artifacts and routes through classifiers and Checker steps
  - description.txt → coverage type: Trip Cancellation or Rescheduling | Personal Effects | Missed Departure or Missed Connection | None
  - When coverage is Trip Cancellation or Rescheduling → reason: Jury duty | Medical emergency | Theft or criminal incident | Other specified personal emergencies | None
  - Supporting documents → medical certificate | police report | jury summon letter | None (cancellation path)
  - When coverage is Personal Effects → supporting docs: Proof of theft, loss, or damage | None
  - When coverage is Missed Departure or Missed Connection → supporting docs: Incident report / delay documentation | Proof of booking | None
  - Classifiers configured with a local LLM via config.yaml (no hardcoded model names)
  - mypy + pytest pass

## Progress

| Phase | Plans | Status | Completed |
|-------|-------|--------|-----------|
| 01 | 3/3 | Complete    | 2026-09-25 |
| 02 | 1/1 | Complete    | 2026-09-25 |
| 03 | 2/2 | Complete   | 2026-09-25 |
| 04 | 0/4 | Planned     | — |

### Phase 2: Case Classifier Models

**Goal:** Add `models/classifier.py` with a Classifier ABC and CaseClassifier that takes description.txt text and returns label(s) with probability estimates. Default labels map to policy coverage types: Trip cancellation or rescheduling, Personal Effects, Missed Departure or Missed Connection, plus Other when no class fits. CaseClassifier must accept config-specified labels so classification targets are externalized.
**Requirements**: R007, R008, R009
**Depends on:** Phase 1
**Plans:** 1/1 plans complete

Plans:

- [x] 02-01-PLAN.md — Tracer: ClassificationResult + Classifier ABC + CaseClassifier with config-driven labels, Other fallback, injectable chat_fn

### Phase 3: Preprocessing Pipeline Orchestration

**Goal:** Add `src/compliance/workflows/pipeline.py` that reads all claim files via the Reader, runs Preprocessor steps, and stores results under `preprocessed/` using the same folder structure as `data/claim N/`. Each claim folder emits `description.txt`, `answer.json`, `supporting_document.json`, and `supporting_documents.md` — this is the dataset used downstream. Provide a main entrypoint that runs the full preprocessing pipeline end-to-end.
**Requirements**: TBD
**Depends on:** Phase 1
**Plans:** 2/2 plans complete

Plans:
**Wave 1**

- [x] 03-01-PLAN.md — Tracer: one claim → four preprocessed/ artifacts via Phase 1 ClaimBundle composition + preprocessed_dir config

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 03-02-PLAN.md — Batch all claims with soft-fail + `python -m compliance.workflows` main entrypoint

### Phase 4: Claim Analysis Pipeline

**Goal:** Build a `ClaimPipeline` that analyzes preprocessed claim data via classifiers and Checker steps. Structure the pipeline as a LangGraph. Classifiers use a local LLM from config.

Classification graph:
1. **Coverage type** (description.txt) → Trip Cancellation or Rescheduling | Personal Effects | Missed Departure or Missed Connection | None
2. **Cancellation reason** (description.txt, only if Trip Cancellation or Rescheduling) → Jury duty | Medical emergency (needs medical report) | Theft or criminal incident (needs police report) | Other specified personal emergencies | None
3. **Supporting document type** (cancellation path) → medical certificate | police report | jury summon letter | None
4. **Personal Effects document** (only if Personal Effects) → Proof of theft, loss, or damage (e.g. police report / airline acknowledgement) | None
5. **Missed Departure/Connection document** (only if Missed Departure or Missed Connection) → Incident report or documentation explaining the cause of delay | Proof of booking | None

Reuse/extend Phase 02 `Classifier`/`CaseClassifier` and existing `Checker`; wire them as graph nodes over Phase 03 preprocessed artifacts.
**Requirements**: R010, R011, R012, R013, R014, R015, R016
**Depends on:** Phase 2 (classifiers), Phase 3 (preprocessed data)
**Plans:** 0/4 plans complete

Plans:

**Wave 0**

- [ ] 04-01-PLAN.md — Wave 0: human-verify langgraph + AnalysisConfig taxonomy + Nyquist stubs (R015, R016)

**Wave 1** *(blocked on Wave 0)*

- [ ] 04-02-PLAN.md — Tracer: cancellation path load → coverage → reason → cancel-doc → Checker → analysis_result.json (R010–R014, R016)

**Wave 2** *(blocked on Wave 1)*

- [ ] 04-03-PLAN.md — Expand PE / missed-departure document branches + other_label skip (R012, R013)

**Wave 3** *(blocked on Wave 2)*

- [ ] 04-04-PLAN.md — Soft-fail batch over preprocessed_dir + `--mode analyze` CLI (R010, R016)
