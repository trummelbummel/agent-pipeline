---
phase: 260925-mol-checker-class-modes-containment-determin
plan: 01
subsystem: llm
tags: [checker, containment, contradicts, ollama, pydantic, pytest]

requires:
  - phase: 02-case-classifier-models
    provides: ChatFn / response_content injection pattern and CaseClassifier JSON parse style
provides:
  - Checker with containment (deterministic then LLM) and contradicts (LLM) modes
  - CheckingConfig on AppConfig from config.yaml checking section
affects: [claim-validation-agents, downstream-checking]

actuals:
  tokens: 9287
  tasks: 2
  commits: 5

plan_head_before: a9a3859e91e31b3c6e83d4b008934f5f71dd89b3

tech-stack:
  added: []
  patterns:
    - injectable chat_fn defaulting to ollama.chat
    - format=json with {"result": bool} parse; malformed → False

key-files:
  created:
    - src/compliance/llm/checker.py
    - tests/test_llm/test_checker.py
  modified:
    - config.yaml
    - src/compliance/config/settings.py
    - src/compliance/config/__init__.py
    - src/compliance/llm/__init__.py
    - tests/test_config/test_settings.py
    - tests/test_workflows/test_pipeline.py

key-decisions:
  - "Place Checker under llm/ (not tools/) to avoid BenfordLawChecker collision"
  - "Normalization = NFKC + casefold + whitespace collapse; containment short-circuits before LLM"
  - "WARNING logs on parse failure only — never dump claim/text payloads (T-260925-mol-01)"

patterns-established:
  - "Checker mirrors InformationExtractor/CaseClassifier chat_fn seam"
  - "Required CheckingConfig section externalizes model + both prompts"

requirements-completed: []

coverage:
  - id: D1
    description: Deterministic containment returns True without calling the LLM
    verification:
      - kind: unit
        ref: tests/test_llm/test_checker.py::test_checker_containment_deterministic_hit_skips_llm
        status: pass
    human_judgment: false
  - id: D2
    description: Containment LLM fallback and contradicts mode with injectable chat_fn
    verification:
      - kind: unit
        ref: tests/test_llm/test_checker.py
        status: pass
    human_judgment: false
  - id: D3
    description: load_config exposes checking.model and both prompts
    verification:
      - kind: unit
        ref: tests/test_config/test_settings.py::test_load_config_reads_checking_section
        status: pass
    human_judgment: false

duration: 4min
completed: 2026-09-25
status: complete
---

# Phase 260925-mol Plan 01: Checker Class Modes Summary

**Reusable `Checker` with deterministic containment short-circuit and LLM-backed containment/contradicts modes, wired through `config.yaml` `checking:`.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-09-25T14:22:13Z
- **Completed:** 2026-09-25T14:26:32Z
- **Tasks:** 2/2
- **Files modified:** 8

## Accomplishments

- `Checker.check(claim, text, mode)` supports `containment` (NFKC/casefold substring, then LLM) and `contradicts` (LLM-only)
- `CheckingConfig` required on `AppConfig`; model + both prompts live under `config.yaml` `checking:`
- CI-safe unit tests with injectable `chat_fn` (no live Ollama)

## Task Commits

Each task was committed atomically (TDD RED → GREEN):

1. **Task 1 RED:** `c536ee1` — test(260925-mol-01): failing containment + checking config tests
2. **Task 1 GREEN:** `979a43f` — feat(260925-mol-01): Checker containment + CheckingConfig
3. **Task 2 RED:** `0ea6473` — test(260925-mol-01): failing LLM fallback + contradicts tests
4. **Task 2 GREEN:** `47de8d6` — feat(260925-mol-01): LLM fallback + contradicts mode

_Note: `rev-list` from `plan_head_before` counts 5 commits because an unrelated `docs(260925-mqh)` commit landed between Task 1 RED and GREEN._

## Files Created/Modified

- `src/compliance/llm/checker.py` — Checker with normalization, LLM boolean parse, both modes
- `src/compliance/llm/__init__.py` — export Checker
- `config.yaml` — `checking:` model + containment/contradicts prompts
- `src/compliance/config/settings.py` — CheckingConfig on AppConfig
- `src/compliance/config/__init__.py` — export CheckingConfig
- `tests/test_llm/test_checker.py` — unit coverage with MagicMock chat_fn
- `tests/test_config/test_settings.py` — checking section load + fixture YAML
- `tests/test_workflows/test_pipeline.py` — inline config includes `checking:`

## Decisions Made

- Checker lives under `llm/` beside `ChatFn`, not `tools/`, to avoid colliding with `BenfordLawChecker`
- Containment: deterministic normalize+substring first; LLM only on miss
- Contradicts: always LLM; True = contradicts, False = supported/consistent
- Parse failures and missing bool `result` → False with WARNING (no claim/text in logs)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Landed working-tree AppConfig schema with CheckingConfig**
- **Found during:** Task 1 GREEN
- **Issue:** RED `test_settings` updates (already in working tree) and pipeline `load_config` fixtures expected `results_dir` / artifacts / benford.enabled that were uncommitted on HEAD while `CheckingConfig` became required
- **Fix:** Commit the working-tree `settings.py` / `config.yaml` / fixture updates together with `CheckingConfig` so `load_config` and Task 1 verify stay green
- **Files modified:** `config.yaml`, `src/compliance/config/settings.py`, `src/compliance/config/__init__.py`, `tests/test_config/test_settings.py`, `tests/test_workflows/test_pipeline.py`
- **Commit:** `979a43f`

## TDD Gate Compliance

- Task 1 RED evidence: `.planning/tdd/260925-mol-task1-red-evidence.json` → `RED_EVIDENCE_OK`
- Task 2 RED evidence: `.planning/tdd/260925-mol-task2-red-evidence.json` → `RED_EVIDENCE_OK`
- Tracer feedback gate: Task 1 verify re-run passed under `auto_advance`; expanded to Task 2

## Self-Check: PASSED

- FOUND: `src/compliance/llm/checker.py`, `config.yaml`, `src/compliance/config/settings.py`, `tests/test_llm/test_checker.py`
- FOUND: commits `c536ee1`, `979a43f`, `0ea6473`, `47de8d6`
