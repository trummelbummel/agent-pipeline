---
phase: 02-case-classifier-models
plan: 01
subsystem: classification
tags: [classifier, pydantic, ollama, config, tdd]

requires:
  - phase: 01-claim-preprocessing-pipeline
    provides: InformationExtractor injectable chat_fn pattern, load_config/AppConfig, NanAwareModel baselines
provides:
  - Classifier ABC with classify(text) -> ClassificationResult
  - CaseClassifier with config-driven labels and Other fallback
  - ClassificationConfig + classification section in config.yaml
  - Injectable chat_fn unit tests (no live Ollama)
affects: [03-preprocessing-pipeline-orchestration, rule-agents, case-routing]

actuals:
  tokens: 4653
  tasks: 3
  commits: 6
plan_head_before: f92bd2aad61d7eebb1cfe436ec8986d2fb21385e

tech-stack:
  added: []
  patterns:
    - "Injectable chat_fn seam (mirror InformationExtractor)"
    - "Config-driven label vocabulary; no hardcoded taxonomy in CaseClassifier"
    - "Other fallback + full probability key coverage after JSON parse"

key-files:
  created:
    - src/compliance/models/classifier.py
    - tests/test_models/test_classifier.py
    - .planning/phases/02-case-classifier-models/02-01-red-evidence.json
    - .planning/phases/02-case-classifier-models/02-01-task2-red-evidence.json
  modified:
    - config.yaml
    - src/compliance/config/settings.py
    - src/compliance/config/__init__.py
    - src/compliance/models/__init__.py
    - tests/test_config/test_settings.py

key-decisions:
  - "Mirror InformationExtractor: ollama.chat default, injectable chat_fn, format=json"
  - "ClassificationResult.labels + probabilities keyed by label name; values are estimates in [0,1]"
  - "Other is config other_label in the same vocabulary — not a second identity model"
  - "AppConfig requires classification section (ValidationError when missing)"

patterns-established:
  - "Classifier ABC + concrete CaseClassifier for typed case-type signal"
  - "Private helpers named after products: _response_content, _parse_classification_payload, _normalized_classification"

requirements-completed: [R007, R008, R009]

coverage:
  - id: D1
    description: CaseClassifier.classify returns ClassificationResult with selected labels and probability estimates via injectable chat_fn
    requirement: R007
    verification:
      - kind: unit
        ref: tests/test_models/test_classifier.py#test_case_classifier_happy_path_trip_cancellation
        status: pass
    human_judgment: false
  - id: D2
    description: Classification targets, Other fallback name, model, and prompt come from config.yaml via load_config()
    requirement: R009
    verification:
      - kind: unit
        ref: tests/test_config/test_settings.py#test_load_config_reads_classification_section
        status: pass
      - kind: unit
        ref: tests/test_config/test_settings.py#test_load_config_reads_classification_labels_and_other
        status: pass
    human_judgment: false
  - id: D3
    description: Empty/unknown LLM labels fall back to other_label; probabilities cover every configured label plus Other in [0,1]
    requirement: R008
    verification:
      - kind: unit
        ref: tests/test_models/test_classifier.py#test_case_classifier_empty_labels_uses_other
        status: pass
      - kind: unit
        ref: tests/test_models/test_classifier.py#test_case_classifier_unknown_label_mapped_to_other
        status: pass
      - kind: unit
        ref: tests/test_models/test_classifier.py#test_case_classifier_probabilities_cover_configured_labels
        status: pass
    human_judgment: false
  - id: D4
    description: Public exports for Classifier, CaseClassifier, ClassificationResult, ClassificationConfig; missing classification YAML fails validation
    requirement: R007
    verification:
      - kind: unit
        ref: tests/test_config/test_settings.py#test_public_exports_include_classifier_and_classification_config
        status: pass
      - kind: unit
        ref: tests/test_config/test_settings.py#test_load_config_missing_classification_section_raises
        status: pass
    human_judgment: false

duration: 4 min
completed: 2026-09-25
status: complete
---

# Phase 02 Plan 01: Case Classifier Models Summary

**Config-driven CaseClassifier with injectable chat_fn returns ClassificationResult (labels + probabilities), including Other fallback when no class fits.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-09-25T11:54:42Z
- **Completed:** 2026-09-25T11:59:00Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments

- Shipped `Classifier` ABC, `CaseClassifier`, and `ClassificationResult` end-to-end under injectable `chat_fn` (no live Ollama)
- Externalized coverage labels, `other_label`, model, and prompt under `config.yaml` → `ClassificationConfig`
- Other fallback + probability key coverage for every configured label; mypy clean on models/config

## Task Commits

Each task was committed atomically (TDD RED→GREEN for Tasks 1–2):

1. **Task 1 RED:** `b15d042` — test(02-01): add failing test for case classifier happy path
2. **Task 1 GREEN:** `01da589` — feat(02-01): implement CaseClassifier with config-driven labels
3. **Task 2 RED:** `3bb7914` — test(02-01): add failing tests for Other fallback and probabilities
4. **Task 2 GREEN:** `ab3aaa7` — feat(02-01): add Other fallback and probability coverage
5. **Task 3:** `298dadc` — test(02-01): lock classification exports and config contract

## TDD Cycle

### RED
- Task 1: Stub `CaseClassifier` returned empty labels; happy-path assertion failed intentionally (`RED_EVIDENCE_OK`)
- Task 2: Empty-label Other fallback test failed before normalization (`RED_EVIDENCE_OK`)

### GREEN
- Task 1: Real LLM JSON parse path + `classification` config section
- Task 2: Filter to configured labels, Other fallback, full probability map with clamp to [0, 1]

### REFACTOR
- Skipped — no cleanup needed beyond GREEN helpers

## TDD Gate Compliance

- RED commits present: `b15d042`, `3bb7914`
- GREEN commits present: `01da589`, `ab3aaa7`
- RED evidence: both records classified `RED_EVIDENCE_OK` / `target_test_failed`

## Deviations from Plan

None - plan executed exactly as written.

## Threat Mitigations

- **T-02-01:** Labels filtered to configured set; invalid/empty → `other_label`
- **T-02-02:** WARNING logs on empty/invalid JSON only — no description/PII payload dump
- **T-02-SC:** No new packages

## Verification

```
uv run pytest tests/test_models/test_classifier.py tests/test_config/test_settings.py -q  # 11 passed
uv run mypy src/compliance/models/ src/compliance/config/  # Success
```

## Next

Phase 02 complete (single plan). Ready for phase verification / Phase 03 planning.

## Self-Check: PASSED
