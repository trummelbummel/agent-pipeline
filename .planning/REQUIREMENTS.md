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
- Status: validated
- Description: `ClaimPipeline` is a LangGraph `StateGraph` that loads Phase 03 preprocessed claim artifacts and runs coverage → reason/doc routing with Checker steps
- Why it matters: Orchestrates analysis over structured preprocessed data with explicit conditional branches matching policy coverage types
- Source: ROADMAP Phase 04; 04-RESEARCH.md
- Validation: Graph loads artifacts under `preprocessed_dir`; conditional edges route by coverage label; unit tests with injectable chat_fn pass

### R011 — Coverage classifier on description.txt
- Class: core-capability
- Status: validated
- Description: Coverage classifier maps description.txt to Trip Cancellation or Rescheduling | Personal Effects | Missed Departure or Missed Connection | None (or config other_label), via CaseClassifier + local LLM from config
- Why it matters: Coverage type gates which reason/document classifiers and policy rules apply
- Source: ROADMAP Phase 04 classification graph step 1
- Validation: Injectable chat_fn tests return configured labels; fallback other/None when no match

### R012 — Conditional cancellation-reason classifier
- Class: core-capability
- Status: validated
- Description: When coverage is Trip Cancellation or Rescheduling, classify description.txt into Jury duty | Medical emergency | Theft or criminal incident | Other specified personal emergencies | None; skip reason node on other coverage paths
- Why it matters: Cancellation reasons determine required supporting documentation
- Source: ROADMAP Phase 04 classification graph step 2
- Validation: Reason node runs only on cancellation path; other coverage types skip it

### R013 — Path-specific supporting-document classifiers
- Class: core-capability
- Status: validated
- Description: Supporting docs classified by coverage branch — cancellation: medical certificate | police report | jury summon letter | None; Personal Effects: Proof of theft, loss, or damage | None; Missed Departure/Connection: Incident report or delay documentation | Proof of booking | None
- Why it matters: Document type must match policy requirements for the selected coverage
- Source: ROADMAP Phase 04 classification graph steps 3–5
- Validation: Correct doc classifier stage runs per coverage branch; injectable chat_fn tests

### R014 — Checker wired as graph node(s)
- Class: core-capability
- Status: validated
- Description: Existing `Checker` (containment / contradicts) wired as LangGraph node(s) after document classification, using `checking` config
- Why it matters: Validates claim narrative against supporting document text before downstream deny/approve logic
- Source: ROADMAP Phase 04; existing Checker quick task
- Validation: Checker node called with expected mode and texts in unit tests

### R015 — Analysis labels/models/prompts externalized
- Class: quality-attribute
- Status: validated
- Description: Multi-stage analysis taxonomy (coverage, reason, doc stages), models, and prompts live in `config.yaml` via typed AnalysisConfig; no hardcoded taxonomy or model strings in source
- Why it matters: CLAUDE.md; taxonomies change without code edits
- Source: ROADMAP Phase 04; extends R005/R009
- Validation: `load_config()` exposes analysis section; settings tests; source has no hardcoded analysis labels/models

### R016 — Injectable chat_fn tests; mypy + pytest pass
- Class: quality-attribute
- Status: validated
- Description: Unit tests inject MagicMock chat_fn (no live Ollama required); mypy and pytest pass for Phase 04 modules
- Why it matters: Deterministic CI without local LLM; mirrors Phase 02/Checker seams
- Source: 04-RESEARCH.md; Phase 02 pattern
- Validation: Default unit path never calls live ollama; mypy + pytest green

### R017 — POST /claims multipart intake under config data_dir
- Class: core-capability
- Status: active
- Description: `POST /claims` accepts multipart description.txt, supporting_documents.md, and an image whose extension is in config `document_formats`; writes under config `data_dir/{claim_id}/`
- Why it matters: HTTP boundary for new claim intake without hardcoding filesystem roots
- Source: ROADMAP Phase 05; 05-RESEARCH.md
- Validation: TestClient multipart → 201; files under injected data_dir; bad extension → 422; collision → 409

### R018 — GET /claims/{claim_id} runs preprocess then analyze
- Class: core-capability
- Status: active
- Description: `GET /claims/{claim_id}` runs PreprocessingPipeline then ClaimPipeline for one claim (same orchestration as main) and returns the decision JSON
- Why it matters: Single-claim decision path must not drift between API and CLI
- Source: ROADMAP Phase 05; 05-RESEARCH.md
- Validation: Injectable chat_fn TestClient returns analysis_result payload; missing raw folder → 404

### R019 — GET /claims lists processed answers from results_dir
- Class: core-capability
- Status: active
- Description: `GET /claims` lists all processed claim answers from config `results_dir` (optional predicted_answer and/or analysis_result per claim)
- Why it matters: Operators need a roster of decisions without scanning the filesystem manually
- Source: ROADMAP Phase 05; 05-RESEARCH.md
- Validation: Empty results → []; non-empty list stable by claim_id sort key

### R020 — Pipelines accept single claim folder and full directory
- Class: core-capability
- Status: active
- Description: PreprocessingPipeline / ClaimPipeline / main accept a caller-supplied `Path` that is either one claim folder or a directory of claims (batch). Scope is configured from outside the pipeline (API/CLI/caller); `None` uses config roots (`data_dir` / `preprocessed_dir`). Shared orchestrator for end-to-end single-claim.
- Why it matters: API GET and CLI must reuse the same process_claim → analyze_claim path without hardcoded roots or internal scope invention
- Source: ROADMAP Phase 05 locked decisions; user refinement 2026-09-25
- Validation: `--claim-id` CLI path + batch default regression tests

### R021 — Pipelines provided as FastAPI lifespan/DI resources
- Class: core-capability
- Status: active
- Description: PreprocessingPipeline and ClaimPipeline created once in FastAPI lifespan and injected via Depends/request.state
- Why it matters: Expensive Docling/LLM resources must not be reconstructed per request; TestClient needs `create_app(config=...)`
- Source: ROADMAP Phase 05; 05-RESEARCH.md Pattern 1
- Validation: test_deps_lifespan proves Depends resolves lifespan instances

### R022 — mypy + pytest pass for API + pipeline refactor
- Class: quality-attribute
- Status: active
- Description: mypy and pytest pass for `src/api`, workflow orchestration changes, and related tests (TestClient + httpx)
- Why it matters: Phase quality gate; hatch must package `src/api`
- Source: ROADMAP Phase 05; 05-VALIDATION.md
- Validation: Phase gate `pytest tests/test_api tests/test_workflows ... && mypy src/api ...` green

### R023 — Denial-rule Checker steps in ClaimPipeline
- Class: core-capability
- Status: active
- Description: Extend ClaimPipeline so denial rules from LOGIC.md that are not covered by containment/contradicts each have an explicit Checker mode or graph node; outcomes persist in `analysis_result.json`; prompts/models externalized in `config.yaml`
- Why it matters: Classification alone does not encode deny reasons; rules need auditable boolean checks before APPROVE/DENY
- Source: ROADMAP Phase 07; LOGIC.md Summary of Denial Rules
- Validation: Each denial rule maps to a named check field in analysis_result; injectable chat_fn tests; coverage for missing-doc, healthy-contradiction, identity, authenticity, incomplete, suspicious-dating

### R024 — Missing documentation check
- Class: core-capability
- Status: active
- Description: Detect when the claim has no usable medical certificate or supporting evidence (empty/faulty OCR, absent supporting_document) — targets claims 1, 2, 21, 25
- Why it matters: Primary deny path when no evidence is attached
- Source: LOGIC.md denial category 1; Phase 07
- Validation: Injectable/unit cases with empty or missing supporting_document → check true; substantive medical text → false

### R025 — Document-contradicts-claim (healthy certificate) check
- Class: core-capability
- Status: active
- Description: Detect when the medical certificate states the patient is healthy / fit, contradicting an illness-based claim (claims 10, 14, 22). May specialize or complement existing contradicts mode
- Why it matters: Generic contradicts may miss “healthy” certificates; this is an explicit deny rule in the dataset
- Source: LOGIC.md denial category 2; Phase 07
- Validation: Healthy-certificate fixture → check true; illness-supporting cert → false; existing containment/contradicts still present

### R026 — Identity unverifiable check
- Class: core-capability
- Status: active
- Description: Detect redacted, obscured, or claimant-mismatched names on the medical/supporting document (claims 4, 15)
- Why it matters: Identity mismatch is a standalone deny reason independent of coverage classification
- Source: LOGIC.md denial category 3; Phase 07
- Validation: Redacted/mismatched name fixtures → true; matching name → false

### R027 — Document authenticity / format check
- Class: core-capability
- Status: active
- Description: Detect wrong format or authenticity concerns from document text/signals — text-only medical doc, photo instead of certificate, photoshopped stamp/signature cues (claims 7, 8, 18). Complements optional Benford (preprocess; off for synthetic data)
- Why it matters: Format/authenticity failures must be catchable in analysis without relying on Benford
- Source: LOGIC.md denial category 4; Phase 07
- Validation: Text-only / photo-instead-of-cert fixtures → true; normal certificate OCR → false

### R028 — Incomplete document check
- Class: core-capability
- Status: active
- Description: Detect missing required fields on medical certificates (signature, discharge date, diagnosis/condition) — claim 17 pattern
- Why it matters: Incomplete certificates are deny/UNCERTAIN drivers even when a document is present
- Source: LOGIC.md denial category 5; Phase 07
- Validation: Missing-signature / missing-date fixtures → true; complete cert → false

### R029 — Suspicious dating check
- Class: core-capability
- Status: active
- Description: Detect inconsistent or implausible document timestamps (claims 13, 20, 23); outcome may later map to UNCERTAIN rather than hard DENY
- Why it matters: Dating anomalies are a documented uncertainty/deny signal in the dataset
- Source: LOGIC.md denial category 6; Phase 07
- Validation: Implausible/inconsistent date fixtures → true; coherent dates → false

## Validated

- R001, R002, R003, R004, R005, R006 — completed in phase 01 plans 01-01 through 01-03
- R007, R008, R009 — completed in phase 02 plan 02-01
- R010, R011, R012, R013, R014, R015, R016 — completed in phase 04 plans 04-01 through 04-04

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
| R010 | core-capability | validated | 04-02 | 04-04 | ClaimPipeline LangGraph loads preprocessed artifacts and routes classifiers |
| R011 | core-capability | validated | 04-02 | none | Coverage classifier on description.txt |
| R012 | core-capability | validated | 04-02 | 04-03 | Conditional cancellation-reason classifier |
| R013 | core-capability | validated | 04-02 | 04-03 | Path-specific supporting-document classifiers |
| R014 | core-capability | validated | 04-02 | none | Checker wired as graph node(s) |
| R015 | quality-attribute | validated | 04-01 | none | analysis section externalized in config.yaml |
| R016 | quality-attribute | validated | 04-01 | 04-02, 04-04 | Injectable chat_fn tests; mypy + pytest pass |
| R017 | core-capability | active | 05-01 | 05-00 | POST /claims multipart writes under config data_dir/{claim_id}/ |
| R018 | core-capability | active | 05-02 | none | GET /claims/{id} process_then_analyze → decision JSON |
| R019 | core-capability | active | 05-02 | none | GET /claims lists results_dir answers |
| R020 | core-capability | active | 05-03 | 05-02 | run(source): one claim folder or claims directory from outside |
| R021 | core-capability | active | 05-01 | 05-00 | Lifespan DI pipelines via create_app |
| R022 | quality-attribute | active | 05-03 | 05-00 | mypy + pytest pass for api + workflows |
| R023 | core-capability | active | 07 | none | Denial-rule Checker steps in ClaimPipeline + analysis_result fields |
| R024 | core-capability | active | 07 | none | Missing documentation check (claims 1, 2, 21, 25) |
| R025 | core-capability | active | 07 | none | Healthy-certificate / contradicts-claim check (claims 10, 14, 22) |
| R026 | core-capability | active | 07 | none | Identity unverifiable check (claims 4, 15) |
| R027 | core-capability | active | 07 | none | Document authenticity / format check (claims 7, 8, 18) |
| R028 | core-capability | active | 07 | none | Incomplete document check (claim 17) |
| R029 | core-capability | active | 07 | none | Suspicious dating check (claims 13, 20, 23) |

## Coverage Summary

- Active requirements: 13
- Mapped to slices: 29
- Validated: 16
- Unmapped active requirements: 0
