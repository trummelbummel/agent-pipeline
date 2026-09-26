---
phase: 07-denial-rule-checkers-in-analysis-pipeline
plan: 01
subsystem: analysis
tags: [checker, authenticity, not_authentic, denial-rules, tdd, fail-closed]

requires:
  - phase: 07-denial-rule-checkers-in-analysis-pipeline
    provides: Wave 0 xfail stubs for authenticity / incomplete / suspicious dating
  - phase: 06-identity-healthy-and-signature-checkers
    provides: Checker healthy mode + claim_pipeline DENY fold patterns
provides:
  - CheckerMode not_authentic with OCR-focused messages and fail-closed parse
  - CheckingConfig.authenticity_prompt + incomplete_prompt (incomplete dispatch deferred)
  - checker_document_not_authentic DENY path through shared run_checker sink
  - Medical/hospital authenticity gate (_authenticity_required_applies)
affects:
  - 07-01b
  - 07-02
  - 07-03

actuals:
  tokens: 10125
  tasks: 1
  commits: 2

plan_head_before: 219649cbfb96a05b38d87ca6c1b38b12cdedc534

tech-stack:
  added: []
  patterns:
    - "Deny-on-True Checker modes fail-closed True on parse/validation failure"
    - "Medical authenticity gate mirrors identity/signature required codes"
    - "Omit authenticity key when gate skips or date UNCERTAIN early-exits"

key-files:
  created:
    - .planning/tdd/260926-07-01-task1-red-evidence.json
    - .planning/tdd/260926-07-01-task1-red-output.txt
  modified:
    - config.yaml
    - src/compliance/config/settings.py
    - src/compliance/llm/checker.py
    - src/compliance/workflows/claim_pipeline.py
    - tests/test_config/test_settings.py
    - tests/test_llm/test_checker.py
    - tests/test_workflows/test_claim_pipeline.py

key-decisions:
  - "A7: mode not_authentic; analysis key checker_document_not_authentic"
  - "A10: fail-closed True for not_authentic/incomplete parse failures"
  - "A11: authenticity gated on signature_required_codes + cancellation coverage"
  - "A12: extend shared run_checker sink — no new LangGraph node"
  - "incomplete_prompt stored on Checker/CheckingConfig; mode dispatch deferred to 07-02"

patterns-established:
  - "OCR-focused user content for not_authentic (mirrors healthy)"
  - "Medical-path chat_fn fixtures append authenticity False response after healthy"

requirements-completed: [R023, R027]

coverage:
  - id: D1
    description: "load_config exposes non-empty authenticity_prompt and incomplete_prompt"
    requirement: R027
    verification:
      - kind: unit
        ref: "tests/test_config/test_settings.py#test_load_config_reads_authenticity_and_incomplete_prompts"
        status: pass
    human_judgment: false
  - id: D2
    description: "Checker not_authentic true/false/fail-closed with injectable chat_fn"
    requirement: R027
    verification:
      - kind: unit
        ref: "tests/test_llm/test_checker.py#test_checker_not_authentic_true_when_ocr_format_suspect"
        status: pass
      - kind: unit
        ref: "tests/test_llm/test_checker.py#test_checker_not_authentic_false_on_llm_false"
        status: pass
      - kind: unit
        ref: "tests/test_llm/test_checker.py#test_checker_not_authentic_parse_failure_fail_closed_true"
        status: pass
    human_judgment: false
  - id: D3
    description: "End-to-end authenticity DENY with medical gate and date early-exit key omission"
    requirement: R023
    verification:
      - kind: unit
        ref: "tests/test_workflows/test_claim_pipeline.py#test_deny_when_checker_document_not_authentic"
        status: pass
      - kind: unit
        ref: "tests/test_workflows/test_claim_pipeline.py#test_authenticity_incomplete_skipped_for_non_medical_document"
        status: pass
      - kind: unit
        ref: "tests/test_workflows/test_claim_pipeline.py#test_payload_omits_llm_keys_on_date_uncertain_early_exit"
        status: pass
    human_judgment: false

duration: 7min
completed: 2026-09-26
status: complete
---

# Phase 07 Plan 01: Authenticity DENY Tracer Summary

**Document authenticity DENY ships end-to-end: config prompts → Checker `not_authentic` (fail-closed) → medical-gated pipeline fold → `checker_document_not_authentic` persistence.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-09-26T10:50:50Z
- **Completed:** 2026-09-26T10:57:40Z
- **Tasks:** 1
- **Files modified:** 9

## Accomplishments

- Authenticity denial path works through config → Checker → ClaimPipeline → analysis_result
- Deny-on-True parse defaults close the T-07-02 unsafe-False threat for `not_authentic`
- Wave 0 authenticity xfails turned green; incomplete / suspicious dating remain xfail for 07-02

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED):** `5eb4ed8` — `test(07-01): add failing authenticity DENY tests`
2. **Task 1 (GREEN):** `5ce544f` — `feat(07-01): ship document authenticity DENY path`

_TDD: no REFACTOR commit (implementation stayed minimal)._

## TDD Gate Compliance

| Task | RED commit | GREEN commit | RED evidence | Verdict |
|------|------------|--------------|--------------|---------|
| 1 | `5eb4ed8` | `5ce544f` | `.planning/tdd/260926-07-01-task1-red-evidence.json` → `RED_EVIDENCE_OK` | Pass |

## Files Created/Modified

- `config.yaml` — `checking.authenticity_prompt` + `incomplete_prompt`
- `src/compliance/config/settings.py` — required CheckingConfig prompt fields
- `src/compliance/llm/checker.py` — `not_authentic` mode + fail-closed parse for deny-on-True modes
- `src/compliance/workflows/claim_pipeline.py` — gate, results, payload, `_violated_checkers`
- Primary test modules — green authenticity behaviors; medical chat fixtures include authenticity response

## Decisions Made

- Fail-closed True for `not_authentic` / prepared `incomplete` parse failures (A10)
- Gate authenticity with `signature_required_codes` on cancellation coverage only (A11)
- Store `incomplete_prompt` now; do not dispatch `incomplete` mode until 07-02 (A8)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Medical-path chat fixtures exhausted after authenticity call**
- **Found during:** Task 1 GREEN
- **Issue:** Existing injectable `side_effect` lists ended at healthy; new authenticity LLM call raised `StopIteration`
- **Fix:** Append `authenticity` False responses to medical helpers; update call_args indices for identity/healthy assertions
- **Files modified:** `tests/test_workflows/test_claim_pipeline.py`
- **Commit:** `5ce544f`

**2. [Rule 3 - Blocking] Minimal YAML fixtures missing new CheckingConfig fields**
- **Found during:** Task 1 GREEN
- **Issue:** Temp config YAML / `_MINIMAL_CHECKING_YAML` lacked required prompts → ValidationError
- **Fix:** Add authenticity/incomplete prompts to settings + claim_pipeline minimal YAML writers
- **Files modified:** `tests/test_config/test_settings.py`, `tests/test_workflows/test_claim_pipeline.py`
- **Commit:** `5ce544f`

### Deferred (pre-existing, out of scope)

- `test_analysis_coverage_other_label_is_false` expects `other_label == "False"` but `config.yaml` has `"None"` (already in deferred-items.md)
- `mypy src/compliance/` still reports pre-existing errors in benford/document/claim_pipeline acceptable-codes typing — not introduced by this plan; checker.py + settings.py mypy clean

## Threat Flags

None — mitigations T-07-01..T-07-04 applied as planned (JSON bool contract, fail-closed, no PII logs, medical gate). No new packages (T-07-SC).

## Self-Check: PASSED

- [x] `07-01-SUMMARY.md` exists
- [x] Commits `5eb4ed8`, `5ce544f` present on branch
- [x] `rg not_authentic` / `checker_document_not_authentic` / `authenticity_prompt` match
- [x] Authenticity behavior tests green
