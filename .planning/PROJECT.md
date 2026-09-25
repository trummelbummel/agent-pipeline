# Project

## Core Value
Structured claim preprocessing so agents and rules engines can approve/deny insurance claims from typed data.

## Current Milestone
v1.0 Claim Preprocessing — Reader/Preprocessor pipeline producing processed.json per claim folder.

## Requirements
See REQUIREMENTS.md (R001–R009). Decisions D001–D009 in DECISIONS.md.

## Evolution

### 2026-09-25 — Phase 02 complete
CaseClassifier shipped: Classifier ABC, ClassificationResult (labels + probabilities), config-driven coverage labels + Other fallback via `classification` in config.yaml, injectable `chat_fn`. Verified 5/5 (R007–R009).

### 2026-09-25 — Phase 01 complete
Claim preprocessing pipeline shipped: Reader/Preprocessor ABCs, FormatConverter→PNG→Docling, InformationExtractor, processed.json for all 25 claims. Verified 6/6 (R001–R006).

---
*Last updated: 2026-09-25 after Phase 02*
