# Phase 04: Claim Analysis Pipeline - Research

**Researched:** 2026-09-25
**Domain:** LangGraph orchestration + config-driven LLM classifiers + Checker over preprocessed claim artifacts
**Confidence:** HIGH (codebase seams + official LangGraph docs + PyPI versions); MEDIUM on exact Checker placement / analysis output schema (no discuss-phase CONTEXT)

<user_constraints>
## User Constraints (from CONTEXT.md)

**No CONTEXT.md** — user chose plan from requirements/roadmap only. Constraints below are taken from ROADMAP Phase 04, CLAUDE.md, and the research prompt.

### Locked Decisions
- Build a `ClaimPipeline` that analyzes **preprocessed** claim data via classifiers and Checker steps
- Structure the pipeline as a **LangGraph**
- Classifiers use a **local LLM from config** (no hardcoded model names)
- Classification graph (from ROADMAP):
  1. Coverage type (`description.txt`) → Trip Cancellation or Rescheduling | Personal Effects | Missed Departure or Missed Connection | None
  2. Cancellation reason (`description.txt`, only if Trip Cancellation or Rescheduling) → Jury duty | Medical emergency | Theft or criminal incident | Other specified personal emergencies | None
  3. Supporting document type (cancellation path) → medical certificate | police report | jury summon letter | None
  4. Personal Effects document (only if Personal Effects) → Proof of theft, loss, or damage | None
  5. Missed Departure/Connection document (only if Missed Departure or Missed Connection) → Incident report or documentation explaining the cause of delay | Proof of booking | None
- Reuse/extend Phase 02 `Classifier`/`CaseClassifier` and existing `Checker`; wire as graph nodes over Phase 03 preprocessed artifacts
- Prefer extending CaseClassifier pattern (config labels, injectable `chat_fn`, `ClassificationResult`)
- Local LLM via ollama (existing pattern)
- Externalize all labels/models/prompts to `config.yaml`

### Claude's Discretion
- Exact module layout under `workflows/` / `models/`
- Config schema shape for multi-stage classifiers (`analysis` section vs extending `classification`)
- How Checker nodes attach after document classification (which modes, which texts)
- Analysis output artifact name/shape under `results_dir`
- Whether coverage `other_label` stays `Other` (Phase 02) or becomes `None` (Phase 04 roadmap wording)
- Whether to add a dedicated CLI entrypoint vs extend `main.py`

### Deferred Ideas (OUT OF SCOPE)
- Full deny-rule engine / payout formulas from LOGIC.md (Benford, identity mismatch heuristics, compensation math) beyond wiring Checker as graph steps
- LangSmith deployment / production checkpointers
- Replacing ollama with LangChain `init_chat_model` / cloud providers
- Discuss-phase UX / UAT scripts (unless planner adds them)
</user_constraints>

<phase_requirements>
## Phase Requirements

> Proposed IDs for planner to add to REQUIREMENTS.md (none exist yet for Phase 04).

| ID | Description | Research Support |
|----|-------------|------------------|
| R010 | `ClaimPipeline` LangGraph loads Phase 03 preprocessed artifacts and runs coverage → reason/doc routing | Architecture Patterns; Standard Stack (langgraph); existing `PreprocessingPipeline` artifact names |
| R011 | Coverage classifier on `description.txt` with config labels + None/Other fallback | Extend `CaseClassifier`; config externalization |
| R012 | Conditional cancellation-reason classifier only when coverage is trip cancellation/rescheduling | LangGraph `add_conditional_edges`; stage config |
| R013 | Path-specific supporting-document classifiers (cancellation / personal effects / missed departure) | Same `CaseClassifier` with different stage configs; inputs from supporting markdown |
| R014 | Checker step(s) wired as graph node(s) using existing `Checker` + `checking` config | `src/compliance/llm/checker.py`; containment/contradicts modes |
| R015 | All analysis labels, models, prompts externalized in `config.yaml` (no hardcoded taxonomy/model strings) | Extend `settings.py` AppConfig; CLAUDE.md |
| R016 | Unit tests use injectable `chat_fn` (no live Ollama required); mypy + pytest pass | Mirror Phase 02/Checker test seams |
</phase_requirements>

## Summary

Phase 04 wires Phase 02 classifiers and the existing Checker into a **LangGraph `StateGraph`** that reads Phase 03 mirrored artifacts under `preprocessing.preprocessed_dir` (default `data/preprocessed`). LangGraph is **not** currently a project dependency; install `langgraph` (verified latest **1.2.12** on PyPI, pulls `langchain-core`). Keep LLM calls on the existing **ollama + injectable `chat_fn`** seam — do **not** adopt LangChain chat models for this phase.

Reuse `CaseClassifier` as a generic config-driven label classifier: construct one instance per taxonomy stage from a new multi-stage analysis config. Route with `add_conditional_edges` on the selected coverage label. Attach Checker after document-type classification to validate claim text against supporting documents (containment / contradicts). Compile **without** a checkpointer for one-shot batch analysis.

**Primary recommendation:** Add `langgraph`, introduce `AnalysisConfig` (multiple `ClassificationConfig`-shaped stages) in `config.yaml`/`settings.py`, implement `ClaimPipeline` in `workflows/` as a Graph-API `StateGraph` over TypedDict state, reuse `CaseClassifier` + `Checker` as node bodies with injectable chat seams.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Load preprocessed claim artifacts | API / Backend | Database / Storage | Filesystem I/O at boundary from `preprocessed_dir` |
| Coverage / reason / document classification | API / Backend | — | Pure Python + local ollama; no browser |
| Conditional routing by coverage | API / Backend | — | LangGraph edges own control flow |
| Checker (containment / contradicts) | API / Backend | — | Existing `Checker` LLM/deterministic logic |
| Persist analysis / predicted results | Database / Storage | API / Backend | Write under config `results_dir` only |
| Config / label taxonomy | API / Backend | CDN / Static | `config.yaml` via `load_config()` |

## Project Constraints (from CLAUDE.md)

- Small functions; private helpers named after **products** produced
- Return structured data (dict / dataclass / NamedTuple / Pydantic) — not raw scalars/tuples for classification outcomes
- Public methods orchestrate; private helpers do work
- Prefer editing existing files over creating new ones (extend `CaseClassifier`, `Checker`, `settings.py`, `workflows/`)
- `from __future__ import annotations`; typed params/returns; `X | None`; public docstrings with `:param:`
- Validate at system boundaries only (claim path names, file I/O, config load)
- Externalize models, labels, prompts, paths to `config.yaml`
- Roots from config: `data_dir`, `preprocessed_dir`, `results_dir` — never hardcode
- Join paths with `Path` / `/` only
- No secrets/PII in logs
- Tests: real implementations where possible; do not mock internals; injectable seams OK; only tests asked for

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `langgraph` | 1.2.12 | `StateGraph`, `START`/`END`, conditional edges | ROADMAP-locked; official Graph API for branching workflows `[VERIFIED: pypi.org/pypi/langgraph]` |
| `langchain-core` | 1.6.5 (transitive) | Required by langgraph | Pulled by langgraph; no need to import ChatModels `[VERIFIED: uv pip dry-run]` |
| `pydantic` | (existing) | `ClassificationResult`, config models | Already project standard |
| `ollama` | >=0.6.2 (existing) | Local LLM chat | Existing CaseClassifier/Checker/InformationExtractor pattern `[VERIFIED: pyproject.toml:20-28]` |
| `pyyaml` | (existing) | Config load | Existing `load_config` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | >=9.0.2 (dev) | Unit tests with injectable `chat_fn` | All Phase 04 automated tests |
| `mypy` | (dev) | Static typing | Phase gate |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| LangGraph Graph API | Hand-rolled if/else pipeline | Faster to write but contradicts ROADMAP lock; harder to visualize/extend |
| LangGraph Functional API (`@entrypoint`) | Graph API | Functional hides branching topology; Graph API matches classification graph explicitly `[CITED: docs.langchain.com/oss/python/langgraph/quickstart]` |
| LangChain `init_chat_model` | Existing `ollama.chat` + `ChatFn` | Would hard-couple to LangChain providers and break injectable test seam |
| `pydantic-ai` graphs | LangGraph | Already in deps but ROADMAP specifies LangGraph |

**Installation:**

```bash
uv add langgraph
```

**Version verification:** `pip index versions langgraph` → latest **1.2.12**; earliest upload **2024-01-08** (`0.0.8`); `requires_python >=3.10` compatible with project `>=3.10,<4.0`. `[VERIFIED: pypi.org/pypi/langgraph]`

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `langgraph` | PyPI | since 2024-01-08; latest 1.2.12 (2026-09-21) | seam: null | github.com/langchain-ai/langgraph | **SUS** (too-new + unknown-downloads heuristics on latest publish) | Flagged — planner must add `checkpoint:human-verify` before install; **recommend approve** (official LangChain package, long release history, docs.langchain.com) |
| `langchain-core` | PyPI | transitive via langgraph | seam: null | github.com/langchain-ai/langchain | **SUS** (same heuristic) | Transitive only — do not add explicitly unless needed; same human-verify checkpoint |

**Packages removed due to [SLOP] verdict:** none

**Packages flagged as suspicious [SUS]:** `langgraph`, `langchain-core` — legitimacy seam flagged latest-release freshness / null download counters, not missing registry identity. Official docs: https://docs.langchain.com/oss/python/langgraph/overview ; Source: https://github.com/langchain-ai/langgraph

*Do not invent alternate packages. ROADMAP locks LangGraph.*

## Architecture Patterns

### System Architecture Diagram

```text
                    ┌─────────────────────────┐
                    │ config.yaml             │
                    │ analysis.* stages       │
                    │ checking.*              │
                    │ preprocessing.* paths   │
                    └───────────┬─────────────┘
                                │ load_config()
                                ▼
┌──────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│ preprocessed │────▶│ ClaimPipeline        │────▶│ results_dir/{claim}/ │
│ claim N/     │     │ (LangGraph compile)  │     │ analysis artifacts   │
│ description  │     └──────────┬───────────┘     └─────────────────────┘
│ supporting_* │                │
└──────────────┘                ▼
                    START → load_artifacts
                              │
                              ▼
                      classify_coverage
                      (CaseClassifier)
                              │
              add_conditional_edges(coverage)
           ┌──────────┼──────────────┬──────────────┐
           ▼          ▼              ▼              ▼
     classify_   classify_pe_   classify_missed_   END
     reason      document       document         (None/Other)
           │          │              │
           ▼          │              │
     classify_cancel_ │              │
     document         │              │
           │          │              │
           └────┬─────┴──────┬───────┘
                ▼            ▼
           run_checker  (containment / contradicts)
                │
                ▼
               END
```

### Recommended Project Structure

```text
src/compliance/
├── config/settings.py          # + AnalysisConfig / stage configs
├── models/classifier.py        # reuse CaseClassifier (no fork unless needed)
├── llm/checker.py              # reuse Checker
├── workflows/
│   ├── pipeline.py             # Phase 03 PreprocessingPipeline (unchanged role)
│   ├── claim_pipeline.py       # NEW: ClaimPipeline StateGraph + load helpers
│   └── __main__.py             # optional: subcommand or keep preprocess-only
config.yaml                     # + analysis: { coverage, cancellation_reason, ... }
tests/
├── test_workflows/test_claim_pipeline.py   # NEW
└── test_config/test_settings.py            # extend for analysis section
```

### Pattern 1: Config-driven stage classifiers

**What:** One `CaseClassifier` instance per taxonomy stage; labels/model/prompt/`other_label` from config.

**When to use:** Every classification node in the graph.

**Example:**

```python
# Source: existing CaseClassifier [VERIFIED: src/compliance/models/classifier.py:50-74]
# + AppConfig classification shape [VERIFIED: src/compliance/config/settings.py:59-71]
from compliance.models.classifier import CaseClassifier

coverage_clf = CaseClassifier(
    labels=config.analysis.coverage.labels,
    model_name=config.analysis.coverage.model,
    prompt=config.analysis.coverage.prompt,
    other_label=config.analysis.coverage.other_label,
    chat_fn=chat_fn,  # injectable for tests
)
result = coverage_clf.classify(description_text)
# result.labels, result.probabilities
```

**Config shape recommendation (discretion):**

```yaml
analysis:
  coverage:
    labels:
      - Trip cancellation or rescheduling
      - Personal Effects
      - Missed Departure or Missed Connection
    other_label: None
    model: llama3.2
    prompt: |
      Classify coverage type. Return JSON labels + probabilities.
  cancellation_reason:
    labels:
      - Jury duty
      - Medical emergency
      - Theft or criminal incident
      - Other specified personal emergencies
    other_label: None
    model: llama3.2
    prompt: |
      Classify cancellation reason from the claim description...
  cancellation_document:
    labels:
      - medical certificate
      - police report
      - jury summon letter
    other_label: None
    model: llama3.2
    prompt: |
      Classify supporting document type from the document text...
  personal_effects_document:
    labels:
      - Proof of theft, loss, or damage
    other_label: None
    model: llama3.2
    prompt: |
      ...
  missed_departure_document:
    labels:
      - Incident report or documentation explaining the cause of delay
      - Proof of booking
    other_label: None
    model: llama3.2
    prompt: |
      ...
```

Reuse `ClassificationConfig` as the stage model type (already has `labels`, `other_label`, `model`, `prompt`). `[VERIFIED: src/compliance/config/settings.py:59-71]` — quote: `labels: list[str]`, `other_label: str`, `model: str`, `prompt: str`.

Keep existing top-level `classification:` section for backward compatibility with Phase 02 tests **or** migrate coverage to `analysis.coverage` and update R008/R009 tests in the same plan wave — planner choice; recommend **add `analysis` without deleting `classification`** in Wave 0/1 to avoid breaking validated requirements.

### Pattern 2: LangGraph Graph API with conditional routing

**What:** TypedDict state; nodes return partial updates; router returns next node name or `END`.

**When to use:** ClaimPipeline control flow.

**Example:**

```python
# Source: [CITED: docs.langchain.com/oss/python/langgraph/quickstart]
# Source: [CITED: docs.langchain.com/oss/python/langgraph/use-graph-api] Conditional branching
from typing import Literal
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

class ClaimAnalysisState(TypedDict, total=False):
    claim_id: str
    description_text: str
    supporting_document_text: str
    supporting_documents_text: str
    coverage_labels: list[str]
    reason_labels: list[str]
    document_labels: list[str]
    checker_containment: bool
    checker_contradicts: bool

def route_after_coverage(state: ClaimAnalysisState) -> Literal[
    "classify_reason",
    "classify_pe_document",
    "classify_missed_document",
    END,
]:
    label = (state.get("coverage_labels") or [None])[0]
    if label == "Trip cancellation or rescheduling":
        return "classify_reason"
    if label == "Personal Effects":
        return "classify_pe_document"
    if label == "Missed Departure or Missed Connection":
        return "classify_missed_document"
    return END

builder = StateGraph(ClaimAnalysisState)
builder.add_node("load_artifacts", load_artifacts)
builder.add_node("classify_coverage", classify_coverage)
builder.add_node("classify_reason", classify_reason)
# ... other nodes ...
builder.add_edge(START, "load_artifacts")
builder.add_edge("load_artifacts", "classify_coverage")
builder.add_conditional_edges("classify_coverage", route_after_coverage)
graph = builder.compile()  # no checkpointer for batch analysis
final = graph.invoke({"claim_id": claim_dir.name})
```

### Pattern 3: Checker as post-document node

**What:** After document labels are set, call `Checker.check(claim, text, mode=...)`.

**When to use:** Validate narrative vs supporting texts; align with LOGIC denial patterns (healthy cert contradicts illness; booking proof containment).

**Example:**

```python
# Source: [VERIFIED: src/compliance/llm/checker.py:38-56]
# modes: Literal["containment", "contradicts"]
from compliance.llm.checker import Checker

def run_checker(state: ClaimAnalysisState) -> dict:
    checker = Checker(
        model_name=config.checking.model,
        containment_prompt=config.checking.containment_prompt,
        contradicts_prompt=config.checking.contradicts_prompt,
        chat_fn=chat_fn,
    )
    doc_text = state["supporting_document_text"]
    claim = state["description_text"]
    return {
        "checker_containment": checker.check(claim, doc_text, mode="containment"),
        "checker_contradicts": checker.check(claim, doc_text, mode="contradicts"),
    }
```

### Anti-Patterns to Avoid

- **Mutating state in-place:** Nodes must **return** updates; default reducer last-write-wins `[CITED: docs.langchain.com/oss/python/langgraph/use-graph-api]`
- **Hardcoding coverage/reason/doc labels in source:** Violates CLAUDE.md / R015
- **Using LangChain ChatModel in nodes:** Breaks injectable `chat_fn` / local ollama pattern
- **Requiring checkpointer + thread_id for batch:** Unnecessary complexity for one-shot claim analysis `[CITED: reference.langchain.com StateGraph.compile]`
- **Routing on ROADMAP display casing while config uses Phase 02 strings:** `"Trip Cancellation or Rescheduling"` ≠ `"Trip cancellation or rescheduling"` — routers must use **exact config label strings** `[VERIFIED: config.yaml:32-37]`
- **Mocking CaseClassifier/Checker internals in tests:** Inject `chat_fn` only (CLAUDE.md / Phase 02 pattern)
- **Hand-rolling JSON parse / label normalization:** Already in `CaseClassifier`

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Branching workflow engine | Custom node runner / FSM | `langgraph.graph.StateGraph` | ROADMAP lock; compile-time orphan checks |
| Label classification + JSON parse | New LLM wrapper per stage | `CaseClassifier` | Already clamps probs, Other/None fallback, injectable chat |
| Claim vs text checks | Ad-hoc string/LLM helpers | `Checker` | Existing containment + contradicts modes |
| Config validation | Manual dict access | Pydantic `AnalysisConfig` via `load_config` | Matches Phase 01–03 settings pattern |
| Path safety for claim folders | Ad-hoc join | Reuse `_validate_claim_dir_name` | `[VERIFIED: src/compliance/workflows/pipeline.py:31-64]` |

**Key insight:** Phase 04 is **orchestration + config stages**, not new ML primitives. The expensive edge cases (JSON parse, Other fallback, containment normalize) are already solved.

## Common Pitfalls

### Pitfall 1: Label vocabulary drift (Other vs None; casing)

**What goes wrong:** Router never matches; every claim exits early to END.

**Why it happens:** Phase 02 `other_label: Other` and labels `"Trip cancellation or rescheduling"` `[VERIFIED: config.yaml:32-37]` vs ROADMAP `"None"` / `"Trip Cancellation or Rescheduling"`.

**How to avoid:** Put Phase 04 taxonomy **verbatim in config**; routers compare against `config.analysis.*.labels` / `other_label` only. Document mapping in PLAN. Prefer `other_label: "None"` for analysis stages.

**Warning signs:** Unit tests pass with hardcoded ROADMAP strings that differ from YAML.

### Pitfall 2: Wrong artifact inputs

**What goes wrong:** Document classifiers see description text or empty files.

**Why it happens:** Phase 03 emits multiple files — `supporting_document.md` (Docling OCR) vs `supporting_documents.md` (booking/internal) `[VERIFIED: config.yaml:18-24]`.

**How to avoid:** Coverage/reason ← `description.txt`; document-type ← primarily `supporting_document.md`; booking proof / containment may also use `supporting_documents.md`. Load via `config.preprocessing.artifacts` names.

**Warning signs:** Classifiers always return None on claims with rich OCR text in `supporting_document.md`.

### Pitfall 3: In-place state mutation / list reducers

**What goes wrong:** Stale labels; lists accumulate duplicates across nodes.

**Why it happens:** Mutating `state["coverage_labels"].append(...)` or using `operator.add` reducers when replacement was intended.

**How to avoid:** Return new dicts; use default (replace) reducers for label fields; only add reducers if intentionally accumulating check results.

**Warning signs:** Second invoke in tests shows previous claim's labels.

### Pitfall 4: Live Ollama required in CI/unit tests

**What goes wrong:** Flaky or blocked pytest when Ollama is down (environment currently: ollama CLI present but **no running instance**).

**How to avoid:** Inject `chat_fn` everywhere (classifier + checker); integration marker optional for live runs (mirror Phase 01).

**Warning signs:** Tests call real `ollama.chat` without mocks.

### Pitfall 5: Scope creep into full LOGIC.md deny engine

**What goes wrong:** Phase balloons into Benford, identity matching, payout formulas.

**Why it happens:** LOGIC.md documents rich denial categories; Checker exists and looks like a full adjudicator.

**How to avoid:** Phase success criteria = graph + classifiers + Checker **steps**; defer full adjudication policy to a later phase unless planner explicitly expands R0xx.

**Warning signs:** Tasks rewriting `predicted_answer` fraud paths or Benford thresholds.

## Code Examples

### Load preprocessed artifacts (boundary)

```python
# Artifact names [VERIFIED: src/compliance/config/settings.py:21-26]
# description: str = "description.txt"
# supporting_document: str = "supporting_document.md"
# supporting_documents: str = "supporting_documents.md"
from pathlib import Path
from compliance.config.settings import AppConfig
from compliance.workflows.pipeline import _validate_claim_dir_name

def _loaded_claim_texts(config: AppConfig, claim_dir: Path) -> dict[str, str]:
    _validate_claim_dir_name(claim_dir.name)
    names = config.preprocessing.artifacts
    root = Path(config.preprocessing.preprocessed_dir) / claim_dir.name
    return {
        "claim_id": claim_dir.name,
        "description_text": (root / names.description).read_text(encoding="utf-8"),
        "supporting_document_text": (root / names.supporting_document).read_text(encoding="utf-8"),
        "supporting_documents_text": (root / names.supporting_documents).read_text(encoding="utf-8"),
    }
```

### Conditional edge after coverage

```python
# Source: [CITED: docs.langchain.com/oss/python/langgraph/use-graph-api]
builder.add_conditional_edges("classify_coverage", route_after_coverage)
# Router returns node name string matching add_node keys, or END
```

### Compile without persistence

```python
# Source: [CITED: docs.langchain.com/oss/python/langgraph/graph-api]
# "If we were adding persistence ... checkpointer ... passed in here."
graph = builder.compile()  # checkpointer omitted — fine for batch
result = graph.invoke(initial_state)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Ad-hoc Python if/else agent loops | LangGraph `StateGraph` + conditional edges | LangGraph ≥0.2 → 1.x | Explicit topology, compile checks |
| Cloud chat SDKs in demos | Local ollama + injectable seam (this repo) | Phase 01–02 | Tests without network/LLM |
| Single coverage classifier | Multi-stage taxonomy graph | Phase 04 | Policy-aligned routing |

**Deprecated/outdated:**

- Treating LangGraph as requiring LangChain chat agents for every node — nodes may be plain Python `[CITED: docs.langchain.com/oss/python/langgraph/graph-api]` (“Nodes … can contain an LLM or just good ol' code”)
- Assuming checkpointing is mandatory — only when resume/HITL persistence needed

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Analysis output should land under `results_dir` as a structured JSON (name TBD, e.g. `analysis_result.json`) rather than only in-memory | Architecture / Open Questions | Planner picks wrong path vs CLAUDE.md results convention |
| A2 | Checker should run containment + contradicts on description vs supporting_document text after document classification | Pattern 3 | May under/over-check; user may want booking-only containment |
| A3 | Keep Phase 02 `classification:` section and add parallel `analysis:` section | Pattern 1 | Duplicate taxonomies if not documented |
| A4 | Full LOGIC.md adjudication is out of Phase 04 scope beyond Checker wiring | Pitfall 5 | If user expected automatic APPROVE/DENY matching answer.json, success criteria undershoot |
| A5 | Legitimacy SUS on langgraph is a false positive of “latest publish date” heuristics | Package Audit | Human may block install unnecessarily — checkpoint still required by protocol |

## Open Questions

1. **Coverage fallback label: `Other` vs `None`?**
   - What we know: Phase 02 config uses `other_label: Other` `[VERIFIED: config.yaml:37]`; ROADMAP Phase 04 success criteria say `None`
   - What's unclear: Whether to migrate Phase 02 vocabulary
   - Recommendation: analysis stages use `None`; keep `classification.other_label: Other` until explicitly migrated; router treats both as terminal for coverage if both can appear

2. **Analysis artifact filename and schema?**
   - What we know: `results_dir` holds `predicted_answer.json` today `[VERIFIED: config.yaml:8-9,21]`
   - What's unclear: New file vs overwrite/extend predicted_answer
   - Recommendation: write `analysis_result.json` (labels + checker bools + optional explanation) under `results_dir/{claim}/`; leave preprocessing predicted_answer alone

3. **Checker depth for Phase 04?**
   - What we know: Checker has containment + contradicts `[VERIFIED: src/compliance/llm/checker.py:38-56]`
   - What's unclear: One node both modes vs reason-specific checks (e.g. contradicts only for medical path)
   - Recommendation: single `run_checker` node both modes; specialize later

4. **CLI entrypoint?**
   - What we know: `compliance-preprocess` / `main.py` runs preprocessing only `[VERIFIED: src/main.py:12-39]`
   - What's unclear: Separate module `__main__` vs flag
   - Recommendation: `python -m compliance.workflows.claim_pipeline` or `--mode analyze` — planner picks one; avoid breaking preprocess script

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | ✓ | 3.14.2 | — |
| uv | Install langgraph | ✓ | 0.9.18 | pip |
| pytest | Validation | ✓ | 9.1.1 | — |
| ollama CLI | Live LLM | ✓ (CLI) / ✗ (no running instance) | — | Injectable `chat_fn` for unit tests; skip live integration |
| langgraph | ClaimPipeline | ✗ not installed | — | `uv add langgraph` (Wave 0) |
| preprocessed data | Pipeline inputs | ✓ | 25 claim folders under `data/preprocessed` | Run Phase 03 preprocess first |

**Missing dependencies with no fallback:**
- None for unit-tested implementation (chat_fn injection)
- Live end-to-end LLM demo requires starting Ollama + pulling `llama3.2`

**Missing dependencies with fallback:**
- `langgraph` — install in Wave 0 after human-verify checkpoint
- Running Ollama — unit tests use injectable chat; optional `@pytest.mark.integration` for live

## Validation Architecture

> `workflow.nyquist_validation` absent in `.planning/config.json` → treated as **enabled**.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest ≥9.0.2 (dev) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_workflows/test_claim_pipeline.py tests/test_config/test_settings.py -q --tb=short` |
| Full suite command | `uv run pytest -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| R010 | Graph loads artifacts + routes nodes | unit | `uv run pytest tests/test_workflows/test_claim_pipeline.py -q` | ❌ Wave 0 |
| R011 | Coverage classification via injectable chat | unit | `uv run pytest tests/test_workflows/test_claim_pipeline.py::test_coverage_node -q` | ❌ Wave 0 |
| R012 | Reason node only on cancellation path | unit | `uv run pytest tests/test_workflows/test_claim_pipeline.py::test_routes_cancellation_to_reason -q` | ❌ Wave 0 |
| R013 | PE / missed doc classifiers on correct branches | unit | `uv run pytest tests/test_workflows/test_claim_pipeline.py::test_routes_personal_effects -q` | ❌ Wave 0 |
| R014 | Checker node called with expected mode/texts | unit | `uv run pytest tests/test_workflows/test_claim_pipeline.py::test_checker_node -q` | ❌ Wave 0 |
| R015 | `analysis` section loaded by `load_config` | unit | `uv run pytest tests/test_config/test_settings.py -k analysis -q` | ❌ Wave 0 |
| R016 | No live Ollama in default unit path | unit | assert MagicMock chat_fn only | ❌ Wave 0 |

Existing related (do not replace): `tests/test_models/test_classifier.py`, `tests/test_llm/test_checker.py`, `tests/test_workflows/test_pipeline.py`.

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_workflows/test_claim_pipeline.py tests/test_config/test_settings.py -q --tb=short`
- **Per wave merge:** `uv run pytest -q`
- **Phase gate:** Full suite green + `uv run mypy` before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `uv add langgraph` after `checkpoint:human-verify` (SUS legitimacy flag)
- [ ] `tests/test_workflows/test_claim_pipeline.py` — covers R010–R014, R016
- [ ] Extend `tests/test_config/test_settings.py` — `analysis` section / R015
- [ ] Add `analysis:` block to `config.yaml` + `AnalysisConfig` in `settings.py`
- [ ] Framework already present — no pytest install needed

## Security Domain

> `security_enforcement` absent → treated as **enabled**.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | no | Local batch CLI; no user auth |
| V3 Session Management | no | No sessions; no LangGraph checkpointer threads in MVP |
| V4 Access Control | no | Single-user local process |
| V5 Input Validation | yes | `_validate_claim_dir_name` on claim folder names; config via Pydantic; read only under configured roots |
| V6 Cryptography | no | No new crypto; don't hand-roll |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via claim folder name | Tampering | Reuse `_validate_claim_dir_name` before mkdir/read `[VERIFIED: src/compliance/workflows/pipeline.py:31-64]` |
| Prompt/log PII leakage | Information Disclosure | Branch logs without OCR payloads / raw claim bodies (existing `branch_log` discipline) |
| LLM prompt injection via claim text | Tampering | Treat model output as untrusted; CaseClassifier allow-list filter already drops unknown labels `[VERIFIED: src/compliance/models/classifier.py:113-123]` |
| Supply-chain (new deps) | Tampering | Package legitimacy checkpoint for langgraph; pin via uv.lock |

## Sources

### Primary (HIGH confidence)

- `src/compliance/models/classifier.py` — CaseClassifier / ClassificationResult
- `src/compliance/llm/checker.py` — Checker modes
- `src/compliance/config/settings.py` — ClassificationConfig, CheckingConfig, artifact names
- `src/compliance/workflows/pipeline.py` — PreprocessingPipeline, path safety
- `config.yaml` — live label/model/path values
- `pyproject.toml` — deps (no langgraph today)
- https://pypi.org/pypi/langgraph/json — version 1.2.12, history since 2024-01-08
- https://docs.langchain.com/oss/python/langgraph/quickstart — StateGraph, START/END, conditional edges
- https://docs.langchain.com/oss/python/langgraph/graph-api — state, reducers, compile
- https://docs.langchain.com/oss/python/langgraph/use-graph-api — conditional branching; return updates not mutate

### Secondary (MEDIUM confidence)

- https://reference.langchain.com/python/langgraph/graph/state/StateGraph/compile — checkpointer optional
- WebSearch synthesis on checkpointer/thread_id gotchas (cross-checked with official compile docs)

### Tertiary (LOW confidence)

- Community cheat sheets on LangGraph antipatterns (mutable state) — consistent with official “return updates” guidance but not used as sole authority

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — PyPI + official docs + dry-run resolve
- Architecture: HIGH — maps cleanly onto existing CaseClassifier/Checker/preprocessed artifacts; LangGraph Graph API matches classification graph
- Pitfalls: HIGH — label drift and artifact mix-ups evidenced in-repo; Ollama down verified in environment
- Checker placement / output schema: MEDIUM — no CONTEXT.md; logged as assumptions

**Research date:** 2026-09-25
**Valid until:** 2026-10-25 (langgraph 1.x still moving; re-check version at execute time)
