---
phase: 02-case-classifier-models
reviewed: 2026-09-25T12:04:00Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - src/compliance/models/classifier.py
  - src/compliance/config/settings.py
  - src/compliance/config/__init__.py
  - src/compliance/models/__init__.py
  - config.yaml
  - tests/test_models/test_classifier.py
  - tests/test_config/test_settings.py
findings:
  critical: 0
  warning: 3
  info: 2
  total: 5
status: issues
---

# Phase 02: Code Review Report

**Reviewed:** 2026-09-25T12:04:00Z
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues

## Summary

Phase 02 delivers a solid config-driven `CaseClassifier` with injectable `chat_fn`, Other fallback, probability clamping, and safe WARNING logs (no claim-text/PII dump). Threat mitigations T-02-01 and T-02-02 look correctly implemented. No critical/security blockers. Main concerns: duplicate labels can leak into `ClassificationResult.labels`, response-parsing helpers are copy-pasted from `InformationExtractor` (drift risk), and the YAML prompt hardcodes `"Other"` separately from `other_label`.

## Warnings

### WR-01: Duplicate labels preserved in ClassificationResult

**File:** `src/compliance/models/classifier.py:105`
**Issue:** Filtering keeps every allowed occurrence from the LLM list. A response like `["Trip cancellation or rescheduling", "Trip cancellation or rescheduling"]` yields duplicate entries in `result.labels`. Downstream routing or multi-label agents can double-count the same class.
**Fix:** Deduplicate while preserving order:

```python
selected: list[str] = []
seen: set[str] = set()
for label in raw_labels:
    if label in allowed and label not in seen:
        selected.append(label)
        seen.add(label)
```

### WR-02: Response-content parsing duplicated from InformationExtractor

**File:** `src/compliance/models/classifier.py:132-146` (mirror of `src/compliance/preprocessing/extractor.py:69-83`)
**Issue:** `_response_content` (and the `ChatFn` alias) are identical copies of the Phase 01 extractor helpers. CLAUDE.md requires DRY. If Ollama’s response shape changes and only one copy is updated, the classifier can silently fall through to empty content → Other fallback while extraction still works (or the reverse).
**Fix:** Extract a shared helper (e.g. `compliance.llm.chat._response_content` / `ChatFn`) and import it from both `InformationExtractor` and `CaseClassifier`.

### WR-03: Prompt hardcodes "Other" independent of `other_label`

**File:** `config.yaml:33`
**Issue:** Classification config has a separate `other_label: Other`, but the prompt text says `Use Other only when no coverage class fits.` Renaming `other_label` (e.g. to `"Unclassified"`) leaves the model instructed to emit `"Other"`, which is then treated as an unknown label and forced through the Other fallback — confusing probability mass and selected labels.
**Fix:** Either (a) interpolate `other_label` into the system prompt in `classify()` instead of baking the name into YAML, or (b) document that operators must keep the prompt wording and `other_label` in sync, and prefer generating the allowed-label list only in code (already partially done at lines 76–77).

## Info

### IN-01: No validation that classification vocabulary is non-empty

**File:** `src/compliance/config/settings.py:45-48`
**Issue:** `ClassificationConfig` accepts `labels: []` and `other_label: ""`. Degenerate config would make every claim fall through to an empty-string “Other” without a load-time error.
**Fix:** Add Pydantic constraints, e.g. `labels: list[str] = Field(min_length=1)` and `other_label: str = Field(min_length=1)`.

### IN-02: Selected label can carry probability 0.0

**File:** `src/compliance/models/classifier.py:111-116`
**Issue:** If the model includes a label in `labels` but omits it from `probabilities`, the label stays selected and defaults to `0.0`. Callers that threshold on probabilities may disagree with `.labels`. This matches the plan’s “missing keys default to 0.0” rule, but is easy to misuse.
**Fix:** Document in `ClassificationResult` / `classify` that `.labels` is authoritative; optionally backfill missing selected-label probs to a small positive mass or `1.0 / len(selected)` in a later phase.

---

_Reviewed: 2026-09-25T12:04:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
