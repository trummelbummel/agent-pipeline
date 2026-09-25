---
status: testing
phase: 03-preprocessing-pipeline-orchestration
source:
  - 03-01-SUMMARY.md
  - 03-02-SUMMARY.md
started: 2026-09-25T12:35:10Z
updated: 2026-09-25T12:35:10Z
---

## Current Test

number: 10
name: Confirm Phase 03 end-to-end behavior
expected: |
  All automated coverage below already passed unit/CLI checks. Confirm from your side that this matches what you expect for Phase 03:

  Tracer (03-01):
  - One claim → four artifacts under preprocessed/claim N/ (description.txt, answer.json, supporting_document.json, supporting_documents.md)
  - Missing optionals still emit all four files
  - Unsafe claim folder names refused before write
  - preprocessed_dir comes from config.yaml; output_root_from_config resolves it

  Batch + CLI (03-02):
  - Batch mirrors all discovered claims with four artifacts each
  - One failing claim is soft-failed; the rest continue
  - python -m compliance.workflows (--config) runs the workflow; missing config exits 2
  - python -m compliance.workflows --help exits 0

  Optional spot-check: run `uv run python -m compliance.workflows` and inspect preprocessed/claim 1/ for the four files.

  Reply yes if this matches reality; otherwise describe what differs.
awaiting: user response

## Tests

### 1. One claim folder projects to four named artifacts under output_root/claim N/
expected: One claim folder projects to four named artifacts under output_root/claim N/
result: pass
source: automated
coverage_id: 03-01-D1

### 2. Missing optional markdown/documents still emit all four files
expected: Missing optional markdown/documents still emit all four files
result: pass
source: automated
coverage_id: 03-01-D2

### 3. Unsafe claim_dir.name refused before mkdir (T-03-03)
expected: Unsafe claim_dir.name refused before mkdir (T-03-03)
result: pass
source: automated
coverage_id: 03-01-D3

### 4. preprocessed_dir loaded from config.yaml; preprocessed/ gitignored
expected: preprocessed_dir loaded from config.yaml; preprocessed/ gitignored
result: pass
source: automated
coverage_id: 03-01-D4

### 5. output_root_from_config resolves Path(config.preprocessing.preprocessed_dir)
expected: output_root_from_config resolves Path(config.preprocessing.preprocessed_dir)
result: pass
source: automated
coverage_id: 03-01-D5

### 6. Batch mirrors all discovered claims into output_root with four artifacts each
expected: Batch mirrors all discovered claims into output_root with four artifacts each
result: pass
source: automated
coverage_id: 03-02-D1

### 7. Per-claim failure is logged and skipped without aborting the full run
expected: Per-claim failure is logged and skipped without aborting the full run
result: pass
source: automated
coverage_id: 03-02-D2

### 8. main loads --config and invokes run_preprocessing_workflow; missing config returns 2
expected: main loads --config and invokes run_preprocessing_workflow; missing config returns 2
result: pass
source: automated
coverage_id: 03-02-D3

### 9. python -m compliance.workflows --help exits 0
expected: python -m compliance.workflows --help exits 0
result: pass
source: automated
coverage_id: 03-02-D4

### 10. Confirm Phase 03 end-to-end behavior
expected: |
  All automated coverage already passed. Confirm Phase 03 matches expectations: mirrored preprocessed/claim N/ with four artifacts, soft-fail batch, and runnable python -m compliance.workflows entrypoint (optional: run CLI and inspect preprocessed/claim 1/).
result: [pending]

## Summary

total: 10
passed: 9
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps

[none yet]
