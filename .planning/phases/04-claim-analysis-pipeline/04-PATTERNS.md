# Phase 04: Claim Analysis Pipeline - Pattern Map

**Mapped:** 2026-09-25
**Files analyzed:** 10
**Analogs found:** 9 / 10

> **Path correction vs RESEARCH.md:** `CaseClassifier` / `ClassificationResult` live at
> `src/compliance/llm/classifier.py` (tracked), **not** `src/compliance/models/classifier.py`.
> Reuse that module; do not create a models fork.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/compliance/workflows/claim_pipeline.py` | service | batch + file-I/O + transform | `src/compliance/workflows/pipeline.py` | role-match |
| `src/compliance/config/settings.py` | config | request-response (load/validate) | `src/compliance/config/settings.py` (`ClassificationConfig`) | exact |
| `config.yaml` | config | — | `config.yaml` (`classification` / `checking`) | exact |
| `src/compliance/config/__init__.py` | config | — | `src/compliance/config/__init__.py` | exact |
| `src/compliance/workflows/__init__.py` | utility | — | `src/compliance/workflows/__init__.py` | exact |
| `src/main.py` (optional CLI) | controller | request-response | `src/main.py` | exact |
| `pyproject.toml` | config | — | `pyproject.toml` (`dependencies`) | exact |
| `tests/test_workflows/test_claim_pipeline.py` | test | batch + transform | `tests/test_workflows/test_pipeline.py` + `tests/test_llm/test_classifier.py` | role-match |
| `tests/test_config/test_settings.py` | test | request-response | `tests/test_config/test_settings.py` | exact |
| LangGraph `StateGraph` topology (inside claim_pipeline) | service | event-driven / conditional | — | none (use RESEARCH) |

**Reuse-only (no new subclasses expected):**

| Existing File | Role | How Phase 04 uses it |
|---------------|------|----------------------|
| `src/compliance/llm/classifier.py` | service | One `CaseClassifier` per analysis stage; injectable `chat_fn` |
| `src/compliance/llm/checker.py` | service | Graph node body for containment / contradicts |
| `src/compliance/llm/chat.py` | utility | `ChatFn` type for injectable seams |

## Pattern Assignments

### `src/compliance/workflows/claim_pipeline.py` (service, batch + file-I/O + transform)

**Analog:** `src/compliance/workflows/pipeline.py`

**Imports pattern** (lines 1–26):
```python
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from compliance.branch_log import log_branch_decision
from compliance.config.settings import AppConfig, PreprocessedArtifactNames
# ... domain imports ...
```

**Path-safety boundary** (lines 31–60) — **must reuse** before reading under `preprocessed_dir`:
```python
def _validate_claim_dir_name(name: str) -> None:
    """Refuse claim folder names that could escape the output root (T-03-03).

    :param name: ``claim_dir.name`` path segment.
    :raises ValueError: When the name is not a single safe path segment.
    """
    if os.sep in name or (os.altsep is not None and os.altsep in name):
        _path_safety_denial(name, reason="path_separator")
    if name in {".", ".."}:
        _path_safety_denial(name, reason="dot_segment")
    # ... log PASS ...
```

**Orchestration class pattern** (lines 192–277): public methods orchestrate; roots from config via `Path(config_value)`; batch soft-fail:
```python
class PreprocessingPipeline:
    def __init__(self, config: AppConfig, **reader_overrides: Any) -> None:
        self._config = config
        self._reader_overrides = reader_overrides

    @property
    def output_root(self) -> Path:
        return Path(self._config.preprocessing.preprocessed_dir)

    @property
    def results_root(self) -> Path:
        return Path(self._config.preprocessing.results_dir)

    def process_claim(self, claim_dir: Path, output_root: Path | None = None) -> Path:
        _validate_claim_dir_name(claim_dir.name)
        # ... load → transform → write ...
        return claim_out

    def run(self) -> list[Path]:
        # discover → per-claim try/except soft-fail → return written paths
        ...
```

**Results write pattern** (lines 346–377) — analysis JSON should mirror this under `results_dir/{claim}/`:
```python
results_claim = self.results_root / claim_out.name
results_claim.mkdir(parents=True, exist_ok=True)
predicted_path = results_claim / self.artifacts.predicted_answer
predicted_path.write_text(
    predicted.model_dump_json(indent=2) + "\n", encoding="utf-8"
)
```

**Artifact filename source** (lines 218–220 + settings 21–26): always
`config.preprocessing.artifacts.description` / `.supporting_document` / `.supporting_documents` — never hardcode names.

**ClaimPipeline-specific (no in-repo LangGraph analog):** follow RESEARCH Pattern 2 — TypedDict state, nodes return partial dicts (do not mutate), `add_conditional_edges` on coverage label strings from **config**, `builder.compile()` without checkpointer. Wire node bodies by constructing `CaseClassifier` / `Checker` with config fields + injectable `chat_fn` (see classifier/checker patterns below).

---

### `src/compliance/config/settings.py` — `AnalysisConfig` (config)

**Analog:** same file — `ClassificationConfig` + nested optional sections like `OcrRetryConfig`

**Stage config shape** (lines 59–71) — reuse as type for each analysis stage:
```python
class ClassificationConfig(BaseModel):
    """LLM case-classification settings for CaseClassifier.

    :param labels: Coverage class names the classifier may return.
    :param other_label: Fallback label when no coverage class fits.
    :param model: LLM model name used for classification.
    :param prompt: System/instruction prompt for classification.
    """

    labels: list[str]
    other_label: str
    model: str
    prompt: str
```

**Nested multi-field section pattern** (lines 74–84, 101–111) — copy for `AnalysisConfig` holding five `ClassificationConfig` stages:
```python
class CheckingConfig(BaseModel):
    model: str
    containment_prompt: str
    contradicts_prompt: str

class OcrRetryConfig(BaseModel):
    enabled: bool = False
    model: str = ""
    prompt: str = ""
```

**AppConfig + load_config** (lines 114–146):
```python
class AppConfig(BaseModel):
    preprocessing: PreprocessingConfig
    extraction: ExtractionConfig
    classification: ClassificationConfig
    checking: CheckingConfig
    benford: BenfordConfig = BenfordConfig()
    ocr_retry: OcrRetryConfig = Field(default_factory=OcrRetryConfig)
    # ADD: analysis: AnalysisConfig

def load_config(path: str | Path = "config.yaml") -> AppConfig:
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(raw)
```

**Planner note:** Keep top-level `classification:` for Phase 02; add parallel `analysis:` (RESEARCH A3). Prefer `other_label: "None"` on analysis stages.

---

### `config.yaml` — `analysis:` section (config)

**Analog:** `config.yaml` lines 32–54 (`classification` + `checking`)

**Labels/model/prompt externalization:**
```yaml
classification:
  labels:
    - Trip cancellation or rescheduling
    - Personal Effects
    - Missed Departure or Missed Connection
  other_label: Other
  model: llama3.2
  prompt: |
    Classify the claim description into one or more of the allowed coverage labels.
    ...
    Use {other_label} only when no coverage class fits.

checking:
  model: llama3.2
  containment_prompt: |
    Decide whether the claim is present in or entailed by the reference text.
    Return JSON only: {"result": true} ...
  contradicts_prompt: |
    Decide whether the claim contradicts the reference text.
    Return JSON only: {"result": true} ...
```

Mirror that shape under `analysis.coverage`, `analysis.cancellation_reason`, `analysis.cancellation_document`, `analysis.personal_effects_document`, `analysis.missed_departure_document` (exact label strings for routers — see RESEARCH Pitfall 1).

---

### `src/compliance/llm/classifier.py` — reuse as node body (service, transform)

**Analog for ClaimPipeline nodes:** this file (exact)

**Injectable construction** (lines 54–74):
```python
class CaseClassifier(Classifier):
    def __init__(
        self,
        labels: list[str],
        model_name: str,
        prompt: str,
        other_label: str,
        chat_fn: ChatFn | None = None,
    ) -> None:
        self.labels = list(labels)
        self.model_name = model_name
        self.prompt = prompt
        self.other_label = other_label
        self._chat: ChatFn = chat_fn or ollama.chat
```

**Core classify + structured result** (lines 76–94):
```python
def classify(self, text: str) -> ClassificationResult:
    response = self._chat(
        model=self.model_name,
        messages=self._classification_messages(text),
        format="json",
    )
    content = response_content(response)
    payload = self._parse_classification_payload(content)
    if payload is None:
        return self._normalized_classification([], {})
    return self._normalized_classification(payload.labels, payload.probabilities)
```

**Allow-list / Other fallback** (lines 123–133) — do not re-implement in graph nodes:
```python
def _selected_labels(self, raw_labels: list[str]) -> _LabelSelection:
    allowed = set(self.labels) | {self.other_label}
    # ... filter unknowns → other_label ...
```

---

### `src/compliance/llm/checker.py` — reuse as checker node (service, transform)

**Analog:** this file (exact)

**Injectable construction + dual modes** (lines 18–55):
```python
class Checker:
    def __init__(
        self,
        model_name: str,
        containment_prompt: str,
        contradicts_prompt: str,
        chat_fn: ChatFn | None = None,
    ) -> None:
        self.model_name = model_name
        self.containment_prompt = containment_prompt
        self.contradicts_prompt = contradicts_prompt
        self._chat: ChatFn = chat_fn or ollama.chat

    def check(
        self,
        claim: str,
        text: str,
        mode: Literal["containment", "contradicts"],
    ) -> bool:
        if mode == "containment":
            return self._containment_result(claim, text)
        if mode == "contradicts":
            return self._llm_boolean_result(self.contradicts_prompt, claim, text)
        raise ValueError(f"Unsupported checker mode: {mode!r}")
```

Node should take prompts/model from `config.checking` and texts from state (`description_text` vs `supporting_document_text`).

---

### `src/main.py` / workflows entrypoint (controller, optional)

**Analog:** `src/main.py` lines 12–48

```python
def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    args = _cli_args(argv)
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        logger.error("Config file not found: %s", args.config)
        return 2
    return _workflow_exit_code(config)

def _cli_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="main")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to application YAML config (default: config.yaml)",
    )
    return parser.parse_args(argv)
```

**`workflows/__main__.py`** currently delegates to preprocess only:
```python
from main import main
raise SystemExit(main())
```
If analysis gets a CLI, prefer extending `main` with a mode flag **or** a separate `claim_pipeline` module entry — do not break `compliance-preprocess` (`pyproject.toml` scripts).

---

### Barrel exports

**Analog:** `src/compliance/workflows/__init__.py` (lines 1–13) and `src/compliance/config/__init__.py` (lines 1–25)

```python
# workflows/__init__.py — add ClaimPipeline to imports + __all__
from compliance.workflows.pipeline import (
    PreprocessingPipeline,
    output_root_from_config,
    results_root_from_config,
)

# config/__init__.py — add AnalysisConfig (and any stage aliases) to imports + __all__
from compliance.config.settings import (
    AppConfig,
    CheckingConfig,
    ClassificationConfig,
    # AnalysisConfig,
    load_config,
)
```

---

### `pyproject.toml` — add `langgraph` (config)

**Analog:** `pyproject.toml` lines 20–28

```toml
dependencies = [
    "docling>=2.130.0",
    "mcp>=2.0.0",
    "numpy>=2.2.6",
    "ollama>=0.6.2",
    "pillow>=12.3.0",
    "pydantic-ai>=2.49.0",
    "scipy>=1.15.0",
    "pyyaml>=6.0.3",
]
```

Add via `uv add langgraph` (after human-verify checkpoint per RESEARCH legitimacy audit). Do **not** add `langchain-core` explicitly unless needed.

---

### `tests/test_workflows/test_claim_pipeline.py` (test)

**Primary analog:** `tests/test_workflows/test_pipeline.py` — tmp_path fixtures, config helper, path-safety assertions, results_dir writes.

**Config helper pattern** (lines 29–50) — extend with `checking=` + `analysis=` when AppConfig requires them:
```python
def _config(
    data_dir: Path,
    *,
    preprocessed_dir: Path | str = "data/preprocessed",
    results_dir: Path | str = "data/results",
) -> AppConfig:
    return AppConfig(
        preprocessing=PreprocessingConfig(
            data_dir=str(data_dir),
            document_formats=["webp", "jpg", "jpeg", "png", "pdf"],
            confidence_threshold=0.7,
            preprocessed_dir=str(preprocessed_dir),
            results_dir=str(results_dir),
        ),
        extraction=ExtractionConfig(model="test-model", prompt="extract fields"),
        classification=ClassificationConfig(
            labels=["Trip cancellation or rescheduling"],
            other_label="Other",
            model="test-model",
            prompt="classify",
        ),
        # checking=CheckingConfig(...), analysis=AnalysisConfig(...),
    )
```

**Seed preprocessed artifacts** (adapt from lines 64–70 + artifact reads 202–216): write `description.txt` / `supporting_document.md` / `supporting_documents.md` under a claim folder that mimics `preprocessed_dir`, using `config.preprocessing.artifacts` names.

**Unsafe name test** (lines 279–296): call pipeline with `name` containing `os.sep` / `..` → `pytest.raises(ValueError)`.

**Chat injection analog:** `tests/test_llm/test_classifier.py` lines 10–46 — **do not mock CaseClassifier/Checker internals**:
```python
def _chat_returning(payload: dict[str, Any]) -> MagicMock:
    import json
    response = SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))
    return MagicMock(return_value=response)

classifier = CaseClassifier(
    labels=_SAMPLE_LABELS,
    model_name="test-model",
    prompt="classify the claim into the provided labels",
    other_label=OTHER,
    chat_fn=chat,
)
```

**Checker injection analog:** `tests/test_llm/test_checker.py` lines 13–25 (`_make_checker` + MagicMock `chat_fn`).

---

### `tests/test_config/test_settings.py` — analysis section (test)

**Analog:** same file lines 88–100, 110–116

```python
def test_load_config_reads_classification_section() -> None:
    config = load_config("config.yaml")
    assert len(config.classification.labels) >= 3
    assert config.classification.other_label
    assert config.classification.model
    assert config.classification.prompt.strip()

def test_load_config_reads_checking_section() -> None:
    config = load_config("config.yaml")
    assert config.checking.model
    assert config.checking.containment_prompt.strip()
    assert config.checking.contradicts_prompt.strip()
```

Add parallel assertions for `config.analysis.coverage` (and sibling stages): labels, `other_label`, `model`, `prompt`. Update public-exports test to include `AnalysisConfig` once exported.

## Shared Patterns

### Injectable `chat_fn` (no live Ollama in unit tests)
**Source:** `src/compliance/llm/classifier.py` (54–74), `src/compliance/llm/checker.py` (18–35), `src/compliance/llm/chat.py` (`ChatFn`)
**Apply to:** All ClaimPipeline nodes that call LLM; all Phase 04 unit tests
```python
ChatFn = Callable[..., Any]
# constructor: chat_fn: ChatFn | None = None
# body: self._chat: ChatFn = chat_fn or ollama.chat
```

### Config externalization (no hardcoded labels/models)
**Source:** `src/compliance/config/settings.py` + `config.yaml`
**Apply to:** Every classifier stage and Checker prompts/model
- Labels, `other_label`, model, prompts → YAML
- Paths → `preprocessing.preprocessed_dir` / `results_dir` / `artifacts.*`

### Path safety at filesystem boundary
**Source:** `src/compliance/workflows/pipeline.py` lines 31–60
**Apply to:** ClaimPipeline load/write helpers before joining claim folder names under configured roots
```python
_validate_claim_dir_name(claim_dir.name)
root = Path(config.preprocessing.preprocessed_dir) / claim_dir.name
```

### Structured results (Pydantic / TypedDict), not raw tuples
**Source:** `ClassificationResult` (`llm/classifier.py` 25–36); CLAUDE.md
**Apply to:** Graph state fields and analysis artifact JSON written under `results_dir`

### Soft-fail batch + structured branch logging
**Source:** `pipeline.py` `run` / `_written_claim_outputs` (253–298)
**Apply to:** Optional batch `ClaimPipeline.run()` over all preprocessed claims — log SKIP on failure, continue

### Barrel re-exports
**Source:** `workflows/__init__.py`, `config/__init__.py`, `llm/__init__.py`
**Apply to:** Export `ClaimPipeline`, `AnalysisConfig` from package `__init__` when added

## No Analog Found

| File / Concern | Role | Data Flow | Reason |
|----------------|------|-----------|--------|
| LangGraph `StateGraph` / `add_conditional_edges` / `START`/`END` | service | conditional / event-driven | No LangGraph usage in repo yet; install `langgraph` then follow RESEARCH Pattern 2 + official Graph API docs |
| Analysis output schema (`analysis_result.json`) | model | file-I/O | No analysis artifact today; closest write pattern is `predicted_answer` under `results_dir` in `pipeline.py` 346–377 — planner defines schema |

## Metadata

**Analog search scope:** `src/compliance/workflows/`, `src/compliance/config/`, `src/compliance/llm/`, `src/main.py`, `tests/test_workflows/`, `tests/test_llm/`, `tests/test_config/`, `config.yaml`, `pyproject.toml`
**Files scanned:** ~40 Python modules under `src/compliance` + `tests`
**Tracked-source gate:** Analogs verified via `git ls-files` (non-empty). Note: RESEARCH path `models/classifier.py` does not exist; tracked classifier is `src/compliance/llm/classifier.py`.
**Pattern extraction date:** 2026-09-25
