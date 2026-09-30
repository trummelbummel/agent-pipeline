# Phase 07: Denial-rule checkers in analysis pipeline - Pattern Map

**Mapped:** 2026-09-26
**Files analyzed:** 8
**Analogs found:** 7 / 8

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/compliance/llm/checker.py` | service | transform | `src/compliance/llm/checker.py` (self — extend modes) | exact |
| `src/compliance/workflows/claim_pipeline.py` | service | batch / request-response | `src/compliance/workflows/claim_pipeline.py` (self — `_checker_results` / decision fold) | exact |
| `src/compliance/config/settings.py` | config | transform | `src/compliance/config/settings.py` (`CheckingConfig`) | exact |
| `config.yaml` | config | — | `config.yaml` (`checking:` + `required_documents`) | exact |
| `tests/test_llm/test_checker.py` | test | transform | `tests/test_llm/test_checker.py` (healthy / parse-failure) | exact |
| `tests/test_workflows/test_claim_pipeline.py` | test | batch | `tests/test_workflows/test_claim_pipeline.py` (healthy DENY + date UNCERTAIN) | exact |
| `tests/test_config/test_settings.py` | test | — | `tests/test_config/test_settings.py` (`test_load_config_reads_checking_section`) | exact |
| `LOGIC.md` | docs | — | — (untracked; sync names to shipped keys) | none |

## Pattern Assignments

### `src/compliance/llm/checker.py` (service, transform)

**Analog:** `src/compliance/llm/checker.py` (extend in place — no new class)

**Imports pattern** (lines 1–11):
```python
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Literal

import ollama
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from compliance.llm.chat import ChatFn, parse_llm_json_object, response_content
```

**Core mode-extension pattern** (lines 15–16, 31–87):
```python
CheckerMode = Literal["containment", "contradicts", "identity", "healthy"]
# Phase 07: add "not_authentic" | "incomplete" (or equivalent) to Literal + __init__ prompts

class Checker:
    def __init__(
        self,
        model_name: str,
        containment_prompt: str,
        contradicts_prompt: str,
        identity_prompt: str,
        healthy_prompt: str,
        chat_fn: ChatFn | None = None,
    ) -> None:
        ...
        self.healthy_prompt = healthy_prompt
        self._chat: ChatFn = chat_fn or ollama.chat

    def check(self, claim: str, text: str, mode: CheckerMode) -> bool:
        if mode == "healthy":
            return self._llm_boolean_result(
                self.healthy_prompt, claim, text, mode=mode
            )
        raise ValueError(f"Unsupported checker mode: {mode!r}")
```

**LLM boolean + message layout** (lines 123–185) — copy for authenticity / incomplete:
```python
def _llm_boolean_result(
    self, prompt: str, claim: str, text: str, *, mode: CheckerMode
) -> bool:
    response = self._chat(
        model=self.model_name,
        messages=self._check_messages(prompt, claim, text, mode=mode),
        format="json",
    )
    return self._parse_boolean_result(response_content(response))

@staticmethod
def _check_messages(
    prompt: str, claim: str, text: str, *, mode: CheckerMode = "containment"
) -> list[dict[str, str]]:
    if mode == "healthy":
        user_content = f"Supporting document (OCR):\n{text}"
    else:
        user_content = f"Claim:\n{claim}\n\nText:\n{text}"
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_content},
    ]
```

**Error / parse-default pattern** (lines 187–196) — Phase 07 must diverge for deny-on-True modes:
```python
@staticmethod
def _parse_boolean_result(content: str) -> bool:
    parsed = parse_llm_json_object(content, context="checker")
    if parsed is None:
        return False  # unsafe for not_authentic / incomplete → fail-closed True
    try:
        return BooleanCheckResult.model_validate(parsed).result
    except ValidationError:
        logger.warning("LLM checker JSON missing bool result")
        return False
```

**Planner note:** Prefer polarity `not_authentic` / incomplete → `True` = violation (like `healthy` / `contradicts`). Gate medical-only modes in the pipeline (not inside Checker), mirroring identity.

---

### `src/compliance/workflows/claim_pipeline.py` (service, batch)

**Analog:** `src/compliance/workflows/claim_pipeline.py` (self)

**State TypedDict fields** (lines 70–102) — add new optional bool keys alongside existing:
```python
checker_contradicts: bool
identity_check: bool
identity_unclear: bool
signature_check: bool
healthy_check: bool
departure_within_days: bool
multiple_document_dates: bool
# Phase 07: checker_document_not_authentic, checker_incomplete_document, checker_suspicious_dating
```

**Medical gating pattern** (lines 742–777) — reuse for authenticity / incomplete:
```python
def _identity_required_applies(self, state: ClaimAnalysisState) -> bool:
    if not self._is_cancellation_coverage(state):
        return False
    required = set(
        self._config.analysis.required_documents.identity_required_codes
    )
    if not required:
        return False
    return bool(self._classified_document_codes(state) & required)
```
Reuse `signature_required_codes` / `identity_required_codes` (or a new config list) — do not run authenticity on PE/missed paths.

**Deterministic date helpers** (lines 211–248, 148–181) — pattern for `checker_suspicious_dating`:
```python
def _departure_within_days(...) -> bool:
    ...
    return abs((departure - today).days) <= within_days

def _has_multiple_document_dates(supporting_document_text: str) -> bool:
    return len(_unique_calendar_dates(supporting_document_text)) >= 2
```
Add a sibling helper (e.g. `_suspicious_dating`) using `_unique_calendar_dates` / `_parse_calendar_date` — no ad-hoc date parsers.

**Shared `run_checker` sink** (lines 560–601) — early-exit omits LLM keys:
```python
def _run_checker_node(self, state: ClaimAnalysisState) -> dict[str, object]:
    results = self._checker_results(...)
    signature_check = self._signature_check_result(state)
    early_uncertain = bool(results.get("departure_within_days")) or bool(
        results.get("multiple_document_dates")
    )
    payload: dict[str, object] = {
        "departure_within_days": results["departure_within_days"],
        "multiple_document_dates": results["multiple_document_dates"],
        "signature_check": signature_check,
    }
    if not early_uncertain:
        payload["healthy_check"] = results["healthy_check"]
        # Phase 07: also set authenticity / incomplete when not early-exit
    return payload
```

**`_checker_results` construction** (lines 834–910):
```python
date_flags = {
    "departure_within_days": departure_flag,
    "multiple_document_dates": multiple_dates_flag,
}
if departure_flag or multiple_dates_flag:
    return date_flags  # omit LLM keys

checker = Checker(
    model_name=checking.model,
    containment_prompt=checking.containment_prompt,
    contradicts_prompt=checking.contradicts_prompt,
    identity_prompt=checking.identity_prompt,
    healthy_prompt=checking.healthy_prompt,
    chat_fn=self._chat_fn,
)
healthy = checker.check(description_text, supporting_document_text, mode="healthy")
return {**date_flags, "healthy_check": healthy, ...}
```
Wire new prompts into `Checker(...)`; compute `checker_suspicious_dating` in the deterministic block (before or with date flags) so it can short-circuit like other UNCERTAIN dates.

**Payload `"key" in state` persist** (lines 939–956):
```python
if "healthy_check" in state:
    payload["healthy_check"] = bool(state["healthy_check"])
# Same omit-when-absent pattern for new flags
```

**`_violated_checkers` DENY list** (lines 1053–1083) — append authenticity / incomplete here:
```python
if "healthy_check" in state and bool(state["healthy_check"]):
    violated.append("healthy_check")
if "checker_contradicts" in state and bool(state["checker_contradicts"]):
    violated.append("checker_contradicts")
# Phase 07:
# if "checker_document_not_authentic" in state and bool(...): append
# if "checker_incomplete_document" in state and bool(...): append
# Keep signature_check as separate deterministic DENY; do not rename healthy_check
```

**Decision-fold precedence** (lines 1085–1134) — insert suspicious dating with date UNCERTAINs:
```python
if bool(state.get("departure_within_days")):
    return GroundTruth(decision=_DECISION_UNCERTAIN, explanation="departure_within_days")
if bool(state.get("multiple_document_dates")):
    return GroundTruth(decision=_DECISION_UNCERTAIN, explanation="multiple_document_dates")
# Phase 07: if bool(state.get("checker_suspicious_dating")): UNCERTAIN before DENY
violated = self._violated_checkers(state)
if violated:
    return GroundTruth(decision=_DECISION_DENY, explanation=",".join(violated))
```

**Anti-pattern:** Do not add a new LangGraph node — topology already has single `run_checker` (lines 290–303).

---

### `src/compliance/config/settings.py` (config, transform)

**Analog:** `src/compliance/config/settings.py` — `CheckingConfig` (lines 103–121)

```python
class CheckingConfig(BaseModel):
    """LLM claim-checking settings for Checker modes.

    :param healthy_prompt: System prompt for healthy / fit certificate detection.
    :param departure_uncertain_within_days: Inclusive absolute day window; ...
    """

    model: str
    containment_prompt: str
    contradicts_prompt: str
    identity_prompt: str
    healthy_prompt: str
    departure_uncertain_within_days: int = 14
    # Phase 07: authenticity_prompt: str; incomplete_prompt: str
    # Optional: suspicious_dating_* threshold fields (int defaults)
```

**Gating codes home** (lines 124–145) — medical codes already on `RequiredDocumentsConfig`:
```python
signature_required_codes: list[str] = Field(default_factory=list)
identity_required_codes: list[str] = Field(default_factory=list)
```
Prefer reusing these for authenticity/incomplete gates; only add a new list if semantics diverge.

**Load path** (lines 283–288): `load_config` → `AppConfig.checking: CheckingConfig` — new required prompt fields must exist in `config.yaml` or Pydantic validation fails at startup.

---

### `config.yaml` (config)

**Analog:** `config.yaml` `checking:` block (lines 61–96) and `required_documents` (lines 222–241)

```yaml
checking:
  model: qwen2.5:7b
  containment_prompt: |
    ...
  healthy_prompt: |
    Decide whether the supporting document states that the patient is healthy, ...
    Return JSON only: {"result": true} if ...
  departure_uncertain_within_days: 14
  # Phase 07: authenticity_prompt / incomplete_prompt — JSON {"result": bool}
  # True = violation (not authentic / incomplete fields)

analysis:
  required_documents:
    signature_required_codes: ["1", "4"]
    identity_required_codes: ["1", "4"]

benford:
  enabled: false  # Do NOT enable for Phase 07 authenticity (R027 uses OCR/format LLM)
```

---

### `tests/test_llm/test_checker.py` (test, transform)

**Analog:** `tests/test_llm/test_checker.py`

**Fixture pattern** (lines 13–27):
```python
def _chat_returning(payload: dict[str, Any] | str) -> MagicMock:
    content = payload if isinstance(payload, str) else json.dumps(payload)
    response = SimpleNamespace(message=SimpleNamespace(content=content))
    return MagicMock(return_value=response)

def _make_checker(chat: MagicMock) -> Checker:
    return Checker(
        model_name="test-model",
        containment_prompt="...",
        contradicts_prompt="...",
        identity_prompt="...",
        healthy_prompt="...",
        chat_fn=chat,
    )
```
Extend `_make_checker` with new prompt kwargs when `Checker.__init__` grows.

**Healthy mode assertion** (lines 239–253) — template for authenticity / incomplete:
```python
def test_checker_healthy_true_when_document_says_healthy() -> None:
    chat = _chat_returning({"result": True})
    checker = _make_checker(chat)
    result = checker.check(claim="", text="...CLÍNICAMENTE SANA...", mode="healthy")
    assert result is True
    user = chat.call_args.kwargs["messages"][1]["content"]
    assert "Supporting document" in user
```

**Parse-failure baseline** (lines 276+) — today returns `False`; Phase 07 tests for new modes should assert **fail-closed True** (or documented UNCERTAIN path) per RESEARCH pitfall 6.

**Invalid mode** (lines 270–273): keep `ValueError` contract for unsupported modes.

---

### `tests/test_workflows/test_claim_pipeline.py` (test, batch)

**Analog:** `tests/test_workflows/test_claim_pipeline.py`

**Config + injectable chat** (lines 141–190, 586–643):
```python
checking=CheckingConfig(
    model="test-model",
    containment_prompt="containment",
    contradicts_prompt="contradicts",
    identity_prompt="identity",
    healthy_prompt="healthy",
),
# Update when CheckingConfig gains authenticity_prompt / incomplete_prompt

chat_fn = MagicMock(
    side_effect=[coverage, reason, document, containment, contradicts, identity, healthy]
)
pipeline = ClaimPipeline(config, chat_fn=chat_fn)
payload = json.loads(pipeline.analyze_claim(claim_dir).read_text(encoding="utf-8"))
assert payload["healthy_check"] is True
assert payload["decision"] == "DENY"
assert "healthy_check" in payload["decision_explanation"]
```

**Date UNCERTAIN + key omission** (lines 1338–1401) — template for `checker_suspicious_dating`:
```python
assert payload["decision"] == "UNCERTAIN"
assert payload["decision_explanation"] == "departure_within_days"
assert "healthy_check" not in payload
assert chat_fn.call_count == 3  # classifiers only
```

**Medical gate skip** — copy `test_identity_skipped_for_non_medical_document` (~496): PE path must not invoke authenticity/incomplete prompts.

**Regression anchors (keep):** missing_documentation, healthy_check DENY, identity mismatch/unclear, signature_check DENY, departure/multiple_dates UNCERTAIN.

---

### `tests/test_config/test_settings.py` (test)

**Analog:** `tests/test_config/test_settings.py` lines 146–153

```python
def test_load_config_reads_checking_section() -> None:
    config = load_config("config.yaml")
    assert config.checking.model
    assert config.checking.containment_prompt.strip()
    assert config.checking.contradicts_prompt.strip()
    within_days = getattr(config.checking, "departure_uncertain_within_days", None)
    assert isinstance(within_days, int)
    assert within_days == 14
```
Extend with `authenticity_prompt` / `incomplete_prompt` (and any new dating thresholds). Update any inline YAML fixtures in this file that construct minimal `checking:` blocks (lines ~18–93).

---

### `LOGIC.md` (docs)

**No tracked analog** (`git ls-files -- LOGIC.md` empty). Treat as documentation sync only.

**Edit targets** (untracked working tree):
- Summary of Denial Rules (~570–579): replace aspirational `checker_healthy_contradiction` / `checker_identity_unverifiable` with shipped `healthy_check` / `identity_check`+`identity_unclear`
- Denial-rule table (~349–353): map incomplete to both `signature_check` and new `checker_incomplete_document`; keep authenticity / suspicious dating keys aligned with code

Do **not** rename code keys to match old LOGIC names (IMP-013).

## Shared Patterns

### Injectable `chat_fn` (no live Ollama)
**Source:** `ClaimPipeline.__init__` (claim_pipeline.py:258–260) + Checker `chat_fn=`
**Apply to:** All unit tests for new modes / pipeline DENY-UNCERTAIN paths
```python
pipeline = ClaimPipeline(config, chat_fn=chat_fn)
checker = Checker(..., chat_fn=chat)
```

### Config-driven prompts / thresholds
**Source:** `CheckingConfig` + `config.yaml` `checking:`
**Apply to:** authenticity, incomplete, optional suspicious-dating thresholds
Never hardcode prompts in `Checker` or pipeline helpers.

### Decision polarity conventions
**Source:** `_violated_checkers` / `_decision_from_state`
**Apply to:**
| Flag | True means | Outcome |
|------|------------|---------|
| `healthy_check`, `checker_contradicts`, `checker_missing_documentation` | violation | DENY |
| `identity_check`, `signature_check` | pass | False → DENY |
| `departure_within_days`, `multiple_document_dates`, `identity_unclear` | uncertain | UNCERTAIN |
| Phase 07 `checker_document_not_authentic`, `checker_incomplete_document` | violation | DENY |
| Phase 07 `checker_suspicious_dating` | uncertain | UNCERTAIN (with date flags, before DENY) |

### Early-exit key omission
**Source:** `_checker_results` + `_analysis_result_payload` (`"key" in state`)
**Apply to:** Any new LLM flags — omit from payload when date UNCERTAIN short-circuits; tests assert absence.

### Medical-document gating
**Source:** `_identity_required_applies` / `_signature_required_applies`
**Apply to:** authenticity + incomplete LLM modes (cancellation coverage + codes `1`/`4`).

### Logging without PII
**Source:** `log_branch_decision` in `_run_checker_node`
**Apply to:** Log flag outcomes / branch reason, not raw OCR names.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `LOGIC.md` | docs | — | Untracked; no prior doc-sync code pattern — align text to shipped artifact keys per RESEARCH IMP-013 |

## Metadata

**Analog search scope:** `src/compliance/llm/`, `src/compliance/workflows/`, `src/compliance/config/`, `config.yaml`, `tests/test_llm/`, `tests/test_workflows/`, `tests/test_config/`
**Files scanned:** 7 tracked analogs + LOGIC.md (untracked)
**Tracked-source gate:** all analogs verified via `git ls-files` except LOGIC.md
**Pattern extraction date:** 2026-09-26
