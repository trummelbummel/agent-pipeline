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

## Validated

- R001, R002, R003, R004, R005, R006 — completed in phase 01 plans 01-01 through 01-03

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

## Coverage Summary

- Active requirements: 0
- Mapped to slices: 6
- Validated: 6
- Unmapped active requirements: 0
