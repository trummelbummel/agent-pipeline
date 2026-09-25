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

- [ ] **Phase 03: Preprocessing Pipeline Orchestration** `profiles: []`
  Plans: 03-01, 03-02
  Goal: Add `workflows/pipeline.py` that reads + preprocesses all claim files and writes a mirrored `preprocessed/` tree; add a main entrypoint to run the full pipeline
  Success criteria:
  - `src/compliance/workflows/pipeline.py` orchestrates Reader + Preprocessor over all claims
  - Output under `preprocessed/` mirrors claim folder structure
  - Each claim emits description.txt, answer.json, supporting_document.json, supporting_documents.md
  - Runnable main entrypoint executes all preprocessing steps
  - mypy + pytest pass

## Progress

| Phase | Plans | Status | Completed |
|-------|-------|--------|-----------|
| 01 | 3/3 | Complete    | 2026-09-25 |
| 02 | 1/1 | Complete    | 2026-09-25 |
| 03 | 1/2 | In Progress|  |

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
**Plans:** 2/2 plans executed

Plans:
**Wave 1**

- [x] 03-01-PLAN.md — Tracer: one claim → four preprocessed/ artifacts via Phase 1 ClaimBundle composition + preprocessed_dir config

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 03-02-PLAN.md — Batch all claims with soft-fail + `python -m compliance.workflows` main entrypoint
