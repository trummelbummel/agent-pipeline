---
phase: 260925-mol-checker-class-modes-containment-determin
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - config.yaml
  - src/compliance/config/settings.py
  - src/compliance/config/__init__.py
  - src/compliance/llm/checker.py
  - src/compliance/llm/__init__.py
  - tests/test_llm/test_checker.py
  - tests/test_config/test_settings.py
  - tests/test_workflows/test_pipeline.py
autonomous: true
requirements: []

estimate:
  tokens: 28000
  raw_tokens: 28000
  tasks: 2
  confidence: low

must_haves:
  truths:
    - "Checker.check(claim, text, mode='containment') returns True when the normalized claim is a substring of the normalized text without calling the LLM"
    - "Checker.check(claim, text, mode='containment') falls back to injectable chat_fn when deterministic containment fails and returns the LLM boolean"
    - "Checker.check(claim, text, mode='contradicts') returns True when the claim contradicts the text and False when supported/consistent (LLM-only)"
    - "Model name and both mode prompts come from config.yaml checking section via load_config()"
  artifacts:
    - path: "src/compliance/llm/checker.py"
      provides: "Checker with check(claim, text, mode) -> bool"
      contains: "class Checker"
    - path: "config.yaml"
      provides: "checking.model, containment_prompt, contradicts_prompt"
      contains: "checking:"
    - path: "src/compliance/config/settings.py"
      provides: "CheckingConfig on AppConfig"
      contains: "class CheckingConfig"
    - path: "tests/test_llm/test_checker.py"
      provides: "Unit tests with injectable chat_fn (no live Ollama)"
  key_links:
    - from: "load_config().checking"
      to: "Checker(model_name, containment_prompt, contradicts_prompt, chat_fn)"
      via: "constructor args from CheckingConfig fields"
    - from: "Checker.check mode=containment"
      to: "bool"
      via: "normalize+lowercase substring then optional LLM JSON {\"result\": bool}"
    - from: "Checker.check mode=contradicts"
      to: "bool"
      via: "LLM JSON {\"result\": bool} (True=contradicts, False=supported)"
---

<objective>
Add a reusable `Checker` that takes a claim string and a reference text, with `containment` (deterministic normalize+lowercase then LLM fallback) and `contradicts` (LLM: True if claim contradicts text, False if supported) modes.

Purpose: Downstream claim-validation agents need a shared LLM-backed seam for text support/contradiction checks, mirroring InformationExtractor / CaseClassifier injection patterns.
Output: `src/compliance/llm/checker.py`, `checking` config section + `CheckingConfig`, and pytest coverage with injectable `chat_fn`.
</objective>

<execution_context>
@~/.claude/gsd-core/workflows/execute-plan.md
@~/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@src/compliance/preprocessing/extractor.py
@src/compliance/models/classifier.py
@src/compliance/llm/chat.py
@src/compliance/config/settings.py
@config.yaml
@tests/test_models/test_classifier.py

## Plan notes
- Quick task (no CONTEXT.md / RESEARCH.md). Honor user intent + existing LLM patterns only.
- Place `Checker` under `src/compliance/llm/checker.py` (alongside `ChatFn` / `response_content`) — not `tools/` — to avoid colliding with `BenfordLawChecker`.
- Reuse `compliance.llm.chat.ChatFn` and `response_content`; default `chat_fn` to `ollama.chat`. Do not invent a parallel Ollama client.
- Claude's discretion: normalization = Unicode NFKC + `casefold()` + collapse runs of whitespace to a single space + strip; LLM responses use `format="json"` with payload `{"result": true|false}`; unparseable / missing result → `False`; unknown `mode` → `ValueError`.
</context>

<interfaces>
Existing seams to reuse (do not reinvent):
- `ChatFn` / `response_content` in `src/compliance/llm/chat.py`
- `InformationExtractor` / `CaseClassifier`: `chat_fn: ChatFn | None = None` → `self._chat = chat_fn or ollama.chat`
- `load_config` / `AppConfig` pattern in `src/compliance/config/settings.py`

New public surface:
- `Checker.__init__(model_name: str, containment_prompt: str, contradicts_prompt: str, chat_fn: ChatFn | None = None)`
- `Checker.check(claim: str, text: str, mode: Literal["containment", "contradicts"]) -> bool`
- `CheckingConfig(model: str, containment_prompt: str, contradicts_prompt: str)` on `AppConfig.checking`
</interfaces>

<tasks>

<task type="tracer" tdd="true">
  <name>Task 1: End-to-end Checker containment — config through deterministic True without LLM</name>
  <files>config.yaml, src/compliance/config/settings.py, src/compliance/config/__init__.py, src/compliance/llm/checker.py, src/compliance/llm/__init__.py, tests/test_llm/test_checker.py, tests/test_config/test_settings.py, tests/test_workflows/test_pipeline.py</files>
  <read_first>
    - src/compliance/llm/chat.py
    - src/compliance/preprocessing/extractor.py (chat_fn injection + ollama.chat default)
    - src/compliance/models/classifier.py (JSON format="json" + parse helpers pattern)
    - src/compliance/config/settings.py (ExtractionConfig / ClassificationConfig mirror)
    - config.yaml
    - tests/test_models/test_classifier.py (_chat_returning fixture)
    - tests/test_config/test_settings.py (tmp yaml fixtures — add checking section)
    - tests/test_workflows/test_pipeline.py (inline config.yaml writer around load_config — add checking:)
  </read_first>
  <behavior>
    - test_checker_containment_deterministic_hit_skips_llm: claim differs only by case/whitespace from a substring of text; Checker.check(..., mode="containment") is True and injected chat_fn is never called
    - test_load_config_reads_checking_section: load_config("config.yaml") exposes checking.model and non-empty containment_prompt / contradicts_prompt
  </behavior>
  <action>
    Add required `checking:` section to `config.yaml` with `model: llama3.2` plus `containment_prompt` and `contradicts_prompt` instructing JSON `{"result": true|false}` (containment = claim present/entailed; contradicts = True when claim contradicts text, False when supported/consistent).

    Add `CheckingConfig` (model, containment_prompt, contradicts_prompt) to `settings.py`, require it on `AppConfig`, export from `config/__init__.py`. Update every test-written minimal config YAML that must still validate (test_settings tmp fixtures and test_workflows inline config) to include a `checking:` block so load_config keeps passing.

    Create `src/compliance/llm/checker.py` with public `Checker` (docstrings, `from __future__ import annotations`, typed). Constructor binds model_name + both prompts + optional `chat_fn` (default `ollama.chat`). Implement private `_normalized_text(value: str) -> str` (NFKC + casefold + whitespace collapse + strip). Implement `check(claim, text, mode)`: for `mode=="containment"`, if normalized claim is non-empty and a substring of normalized text return True without calling `_chat`; otherwise call LLM with containment_prompt and parse `{"result": bool}`. Export `Checker` from `llm/__init__.py`.

    Write `tests/test_llm/test_checker.py` with the deterministic-hit behavior above (MagicMock chat_fn). Add `test_load_config_reads_checking_section` in `tests/test_config/test_settings.py`.
  </action>
  <verify>
    <automated>pytest tests/test_llm/test_checker.py::test_checker_containment_deterministic_hit_skips_llm tests/test_config/test_settings.py::test_load_config_reads_checking_section -x</automated>
  </verify>
  <done>Deterministic containment returns True without LLM; config.checking loads model + both prompts; AppConfig requires CheckingConfig.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Containment LLM fallback + contradicts mode + parse edges</name>
  <files>src/compliance/llm/checker.py, tests/test_llm/test_checker.py</files>
  <read_first>
    - src/compliance/llm/checker.py (from Task 1)
    - tests/test_llm/test_checker.py
    - tests/test_models/test_classifier.py (JSON chat mock pattern)
  </read_first>
  <behavior>
    - test_checker_containment_llm_fallback_true: deterministic miss; chat_fn returns {"result": true}; check(..., mode="containment") is True and chat_fn called once with format="json" and containment prompt in system message
    - test_checker_containment_llm_fallback_false: deterministic miss; chat_fn returns {"result": false}; result is False
    - test_checker_contradicts_true_when_claim_conflicts: chat_fn returns {"result": true}; check(..., mode="contradicts") is True (no deterministic short-circuit)
    - test_checker_contradicts_false_when_supported: chat_fn returns {"result": false}; check(..., mode="contradicts") is False
    - test_checker_invalid_mode_raises: mode not in {containment, contradicts} raises ValueError
    - test_checker_unparseable_llm_response_returns_false: empty or non-JSON content yields False
  </behavior>
  <action>
    Complete `Checker.check` for `mode=="contradicts"`: always call `_chat` with contradicts_prompt (no substring short-circuit). Share a private helper that builds messages (system=prompt, user includes claim + text), invokes `_chat(model=..., messages=..., format="json")`, and parses boolean `result` via `response_content` + `json.loads` (dict with bool `result`; anything else → False, log WARNING like CaseClassifier).

    Raise `ValueError` for unsupported mode strings. Keep functions small: public `check` orchestrates; private helpers produce normalized text, LLM boolean, and messages.

    Expand `tests/test_llm/test_checker.py` with the behaviors above using injected chat_fn only (no live Ollama).
  </action>
  <verify>
    <automated>pytest tests/test_llm/test_checker.py tests/test_config/test_settings.py -x</automated>
  </verify>
  <done>Both modes behave per user intent; LLM path covered with injectable chat_fn; invalid mode and bad JSON handled; config + checker tests green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| claim/text strings → Checker.check | Untrusted free text enters LLM prompts and substring logic |
| config.yaml → CheckingConfig | Operator-controlled model/prompt settings |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-260925-mol-01 | Information Disclosure | Checker._chat messages | medium | mitigate | Do not log full claim/text or LLM payloads; WARNING logs on parse failure only (no PII dump) |
| T-260925-mol-02 | Tampering | LLM JSON result parse | medium | mitigate | Strict JSON object + bool `result`; malformed → False; format="json" |
| T-260925-mol-03 | Elevation of Privilege | N/A | low | accept | Library helper only; no auth or filesystem writes in this task |
| T-260925-mol-SC | Tampering | npm/pip/cargo installs | low | accept | No new package installs in this plan |
</threat_model>

<verification>
pytest tests/test_llm/test_checker.py tests/test_config/test_settings.py -x
</verification>

<success_criteria>
- `Checker` lives under `src/compliance/llm/` and uses injectable `ChatFn`
- containment: normalize+lowercase substring first, else LLM boolean
- contradicts: LLM True if contradicts, False if supported
- model + prompts externalized under `config.yaml` `checking:`
- CI-safe unit tests with no live LLM
</success_criteria>

<output>
Create `.planning/quick/260925-mol-checker-class-modes-containment-determin/260925-mol-SUMMARY.md` when done
</output>
