# Requirements

This file is the explicit capability and coverage contract for the project.

## Active

### R001 — Parse all 25 claim folders into structured JSON (processed.json per claim)
- Class: core-capability
- Status: validated
- Description: Parse all 25 claim folders into structured JSON (processed.json per claim)
- Why it matters: Foundation for all downstream analysis — agents and rules engines need structured data, not raw files
- Source: discuss-phase D001
- Validation: All 25 claim folders produce a valid processed.json with correct fields populated

### R002 — Convert documents to PNG then extract text via Docling into extensible DocumentData
- Class: core-capability
- Status: validated
- Description: FormatConverter (preprocessing.py) converts configured document formats to PNG first; DocumentReader then runs Docling on the PNG and maps to DocumentData (core person + date, plus arbitrary fields dict); flag human_in_the_loop when confidence is below threshold
- Why it matters: ~22 heterogeneous documents (medical certs, boarding passes, booking confirmations) need a uniform PNG→Docling path and a non-medical-specific schema (D007, D008)
- Source: discuss-phase D005, D007, D008
- Validation: Configured-format docs convert to PNG (passthrough if already PNG) before Docling; DocumentData entries have non-empty raw_text where OCR succeeds; person/date filled when present else np.nan; extra keys land in fields; low-confidence docs set human_in_the_loop=True

### R003 — Pydantic models with maximal/extensible fields; missing values filled with np.nan
- Class: core-capability
- Status: validated
- Description: Pydantic models (GroundTruth, BookingData, DocumentData, ClaimBundle) define schemas for each file type; DocumentData is extensible (person, date, + arbitrary fields); absent values default to np.nan
- Why it matters: Typed contracts between preprocessing and downstream consumers; uniform missing-value semantics; document types vary per claim
- Source: discuss-phase D001, D004, D008
- Validation: ClaimBundle validates for all 25 processed claims; mypy passes; absent optional fields are np.nan; DocumentData accepts arbitrary extracted fields without schema changes

### R004 — Preprocessing handles missing files gracefully
- Class: quality-attribute
- Status: validated
- Description: Claims without supporting1.md or documents produce valid output with np.nan / empty list fields
- Why it matters: File presence varies (supporting1.md in 18/25, images in ~17/25, internal data in 7/25)
- Source: discuss-phase, Knowledge Rule 3
- Validation: Claims 1, 21 produce valid processed.json with np.nan/empty optional fields as appropriate

### R005 — Config values externalized to config.yaml
- Class: quality-attribute
- Status: validated
- Description: data paths, Docling document_formats, confidence_threshold, LLM model name, and InformationExtractor prompt live in config.yaml
- Why it matters: CLAUDE.md mandate — no hardcoded config values in code
- Source: CLAUDE.md, D003, D005, D006
- Validation: No hardcoded paths, format lists, model names, or prompts in source; all loaded via load_config()

### R006 — Extensible Reader/Preprocessor ABCs with InformationExtractor for descriptions
- Class: core-capability
- Status: validated
- Description: Reader + Preprocessor ABCs; AnswerReader, MarkdownReader (key normalize/translate), DescriptionReader, DocumentReader. InformationExtractor takes a Pydantic model + config LLM + config prompt and extracts BookingData fields from description.txt
- Why it matters: Extensible per document type; description free text cannot be regex-parsed reliably across 6 languages
- Source: D004, D006
- Validation: Each reader subclass returns its Pydantic model; DescriptionReader output matches BookingData shape; new format = new Reader subclass without changing existing readers

### R007 — Classifier ABC with structured labels and probability estimates
- Class: core-capability
- Status: validated
- Description: `Classifier` ABC in `models/classifier.py` defines a `classify(text: str)` interface that returns a structured `ClassificationResult` carrying selected label(s) and probability estimates (not raw scalars or bare tuples)
- Why it matters: Downstream agents/rules need a typed classification contract before orchestration wires case routing
- Source: ROADMAP Phase 02 goal
- Validation: Subclasses implement `classify`; return type exposes labels + probabilities; mypy passes on models package

### R008 — CaseClassifier maps description text to coverage-type labels
- Class: core-capability
- Status: validated
- Description: `CaseClassifier` classifies description.txt narrative into coverage-type label(s) with probabilities. Default targets match policy coverage types (Trip cancellation or rescheduling, Personal Effects, Missed Departure or Missed Connection) plus a configurable Other when no class fits. Uses config LLM via injectable `chat_fn` (same pattern as InformationExtractor)
- Why it matters: Case type gates which policy rules apply; free-text descriptions cannot be keyword-routed reliably across languages
- Source: ROADMAP Phase 02 goal; policy.md coverage types
- Validation: Injectable chat_fn tests prove config labels appear in prompts and ClassificationResult; Other used when model returns empty/non-matching labels; no live Ollama required for unit tests

### R009 — Classification labels, model, and prompt externalized in config.yaml
- Class: quality-attribute
- Status: validated
- Description: `classification` section in config.yaml holds `labels`, `other_label`, `model`, and `prompt`; `load_config()` exposes typed `ClassificationConfig`. CaseClassifier reads classification targets from config — no hardcoded model names, prompts, or label lists in source
- Why it matters: CLAUDE.md mandate; coverage taxonomy may change without code edits
- Source: ROADMAP Phase 02; extends R005 pattern
- Validation: config.yaml lists policy coverage labels + Other; settings tests read classification section; source has no hardcoded LLM model name for classification

### R010 — ClaimPipeline LangGraph over preprocessed artifacts
- Class: core-capability
- Status: active
- Description: `ClaimPipeline` is a LangGraph `StateGraph` that loads Phase 03 preprocessed claim artifacts and runs coverage → reason/doc routing with Checker steps
- Why it matters: Orchestrates analysis over structured preprocessed data with explicit conditional branches matching policy coverage types
- Source: ROADMAP Phase 04; 04-RESEARCH.md
- Validation: Graph loads artifacts under `preprocessed_dir`; conditional edges route by coverage label; unit tests with injectable chat_fn pass

### R011 — Coverage classifier on description.txt
- Class: core-capability
- Status: active
- Description: Coverage classifier maps description.txt to Trip Cancellation or Rescheduling | Personal Effects | Missed Departure or Missed Connection | None (or config other_label), via CaseClassifier + local LLM from config
- Why it matters: Coverage type gates which reason/document classifiers and policy rules apply
- Source: ROADMAP Phase 04 classification graph step 1
- Validation: Injectable chat_fn tests return configured labels; fallback other/None when no match

### R012 — Conditional cancellation-reason classifier
- Class: core-capability
- Status: active
- Description: When coverage is Trip Cancellation or Rescheduling, classify description.txt into Jury duty | Medical emergency | Theft or criminal incident | Other specified personal emergencies | None; skip reason node on other coverage paths
- Why it matters: Cancellation reasons determine required supporting documentation
- Source: ROADMAP Phase 04 classification graph step 2
- Validation: Reason node runs only on cancellation path; other coverage types skip it

### R013 — Path-specific supporting-document classifiers
- Class: core-capability
- Status: active
- Description: Supporting docs classified by coverage branch — cancellation: medical certificate | police report | jury summon letter | None; Personal Effects: Proof of theft, loss, or damage | None; Missed Departure/Connection: Incident report or delay documentation | Proof of booking | None
- Why it matters: Document type must match policy requirements for the selected coverage
- Source: ROADMAP Phase 04 classification graph steps 3–5
- Validation: Correct doc classifier stage runs per coverage branch; injectable chat_fn tests

### R014 — Checker wired as graph node(s)
- Class: core-capability
- Status: active
- Description: Existing `Checker` (containment / contradicts) wired as LangGraph node(s) after document classification, using `checking` config
- Why it matters: Validates claim narrative against supporting document text before downstream deny/approve logic
- Source: ROADMAP Phase 04; existing Checker quick task
- Validation: Checker node called with expected mode and texts in unit tests

### R015 — Analysis labels/models/prompts externalized
- Class: quality-attribute
- Status: active
- Description: Multi-stage analysis taxonomy (coverage, reason, doc stages), models, and prompts live in `config.yaml` via typed AnalysisConfig; no hardcoded taxonomy or model strings in source
- Why it matters: CLAUDE.md; taxonomies change without code edits
- Source: ROADMAP Phase 04; extends R005/R009
- Validation: `load_config()` exposes analysis section; settings tests; source has no hardcoded analysis labels/models

### R016 — Injectable chat_fn tests; mypy + pytest pass
- Class: quality-attribute
- Status: active
- Description: Unit tests inject MagicMock chat_fn (no live Ollama required); mypy and pytest pass for Phase 04 modules
- Why it matters: Deterministic CI without local LLM; mirrors Phase 02/Checker seams
- Source: 04-RESEARCH.md; Phase 02 pattern
- Validation: Default unit path never calls live ollama; mypy + pytest green

## Validated

- R001, R002, R003, R004, R005, R006 — completed in phase 01 plans 01-01 through 01-03
- R007, R008, R009 — completed in phase 02 plan 02-01

## Deferred

## Out of Scope

## Traceability

| ID | Class | Status | Primary owner | Supporting | Proof |
| --- | --- | --- | --- | --- | --- |
| R001 | core-capability | validated | 01-03 | none | All 25 claim folders produce a valid processed.json with correct fields populated |
| R002 | core-capability | validated | 01-03 | none | FormatConverter → PNG then Docling → DocumentData (person, date, + fields); low confidence → human_in_the_loop |
| R003 | core-capability | validated | 01-01 | none | ClaimBundle validates for all 25; DocumentData extensible; missing fields are np.nan; mypy passes |
| R004 | quality-attribute | validated | 01-03 | none | Claims 1, 21 produce valid processed.json with np.nan/empty optional fields |
| R005 | quality-attribute | validated | 01-01 | none | Formats, model, prompt, paths come from config.yaml only |
| R006 | core-capability | validated | 01-03 | 01-02 | Reader/Preprocessor ABCs + InformationExtractor produce BookingData from description.txt |
| R007 | core-capability | validated | 02-01 | none | Classifier ABC + ClassificationResult with labels and probabilities |
| R008 | core-capability | validated | 02-01 | none | CaseClassifier classifies description text into config-driven coverage labels |
| R009 | quality-attribute | validated | 02-01 | none | classification section in config.yaml via load_config / ClassificationConfig |
| R010 | core-capability | active | 04 | none | ClaimPipeline LangGraph loads preprocessed artifacts and routes classifiers |
| R011 | core-capability | active | 04 | none | Coverage classifier on description.txt |
| R012 | core-capability | active | 04 | none | Conditional cancellation-reason classifier |
| R013 | core-capability | active | 04 | none | Path-specific supporting-document classifiers |
| R014 | core-capability | active | 04 | none | Checker wired as graph node(s) |
| R015 | quality-attribute | active | 04 | none | analysis section externalized in config.yaml |
| R016 | quality-attribute | active | 04 | none | Injectable chat_fn tests; mypy + pytest pass |

## Coverage Summary

- Active requirements: 7 (R010–R016)
- Mapped to slices: 16
- Validated: 9
- Unmapped active requirements: 0
