# Phase 5: FastAPI Claims API - Pattern Map

**Mapped:** 2026-09-25
**Files analyzed:** 16
**Analogs found:** 14 / 16

> Note: `05-CONTEXT.md` is absent; file list derived from `05-RESEARCH.md` recommended structure + locked decisions (R017–R022).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/api/__init__.py` | utility | — | `src/compliance/workflows/__init__.py` | role-match |
| `src/api/app.py` | controller | request-response | `src/main.py` | role-match |
| `src/api/deps.py` | provider | request-response | `src/compliance/workflows/claim_pipeline.py` | partial |
| `src/api/routes_claims.py` | controller | request-response + file-I/O | `src/main.py` + `src/compliance/preprocessing/claim_batch.py` | partial |
| `src/api/schemas.py` | model | request-response | `src/compliance/models/claim.py` | role-match |
| `src/compliance/workflows/orchestration.py` | service | transform | `src/main.py` + pipeline single-claim APIs | exact |
| `src/main.py` (modify) | controller | batch | itself | exact |
| `src/compliance/workflows/pipeline.py` (modify) | service | batch | itself | exact |
| `src/compliance/workflows/claim_pipeline.py` (modify) | service | batch | itself | exact |
| `src/compliance/workflows/__init__.py` (modify) | utility | — | itself | exact |
| `pyproject.toml` (modify) | config | — | itself | exact |
| `tests/test_api/__init__.py` | test | — | `tests/test_workflows/__init__.py` | role-match |
| `tests/test_api/test_claims_post.py` | test | file-I/O | `tests/test_workflows/test_pipeline.py` | role-match |
| `tests/test_api/test_claims_get.py` | test | request-response | `tests/test_workflows/test_claim_pipeline.py` | role-match |
| `tests/test_api/test_claims_list.py` | test | file-I/O | `tests/test_workflows/test_pipeline.py` | partial |
| `tests/test_api/test_deps_lifespan.py` | test | request-response | `tests/test_workflows/test_claim_pipeline.py` | partial |

**No in-repo FastAPI/Starlette code exists.** For HTTP surface files, copy project conventions (config roots, path safety, pydantic, injectable `chat_fn`, logging) from analogs below; copy FastAPI lifespan/`UploadFile`/`TestClient` shapes from `05-RESEARCH.md` Patterns 1–2 and Code Examples.

## Pattern Assignments

### `src/api/__init__.py` (utility)

**Analog:** `src/compliance/workflows/__init__.py`

**Barrel export pattern** (lines 1–15):
```python
from __future__ import annotations

from compliance.workflows.claim_pipeline import ClaimPipeline
from compliance.workflows.pipeline import (
    PreprocessingPipeline,
    output_root_from_config,
    results_root_from_config,
)

__all__ = [
    "ClaimPipeline",
    "PreprocessingPipeline",
    "output_root_from_config",
    "results_root_from_config",
]
```

Keep `api/__init__.py` minimal (empty or re-export `create_app` only). Prefer public factory on `api.app`.

---

### `src/api/app.py` (controller, request-response)

**Analog:** `src/main.py` (entrypoint + config load + structured args)

**Imports / config-load pattern** (lines 1–48):
```python
from __future__ import annotations

import argparse
import logging
from typing import Literal

from pydantic import BaseModel, Field

from compliance.config.settings import AppConfig, load_config
from compliance.workflows.claim_pipeline import ClaimPipeline
from compliance.workflows.pipeline import PreprocessingPipeline

logger = logging.getLogger(__name__)
```

**Boundary error handling** (lines 41–46): catch only system-boundary failures (`FileNotFoundError` for missing config); return structured exit / HTTP status — do not wrap internal pipeline errors defensively.

**Core factory pattern to mirror:** `main()` loads config once then constructs pipelines. For API, fold that into lifespan + `create_app(config: AppConfig | None = None)` so tests inject tmp roots (RESEARCH Open Question 4).

```python
# Shape from RESEARCH Pattern 1 — adapt to create_app(config=...)
config = load_config("config.yaml")  # or use injected AppConfig
# yield state with PreprocessingPipeline(config), ClaimPipeline(config)
```

**Logging:** reuse `_configure_logging` style from `src/main.py` lines 51–54 if the API process needs `basicConfig`; otherwise rely on uvicorn and module loggers.

---

### `src/api/deps.py` (provider, request-response)

**Analog:** `src/compliance/workflows/claim_pipeline.py` — constructor DI + TypedDict state

**Constructor injection pattern** (lines 46–55):
```python
class ClaimPipeline:
    def __init__(self, config: AppConfig, chat_fn: ChatFn | None = None) -> None:
        self._config = config
        self._chat_fn = chat_fn
```

**TypedDict state pattern** (lines 21–44): use a TypedDict (or RESEARCH `AppState`) for lifespan-yielded keys (`config`, `preprocessing`, `claims`) rather than ad-hoc attributes.

**Depends helpers:** thin functions that read `request.state[...]` — no business logic. Tests inject `chat_fn` by constructing `ClaimPipeline(config, chat_fn=...)` inside a test-specific lifespan / `create_app` override (same seam as Phase 04 tests).

---

### `src/api/routes_claims.py` (controller, request-response + file-I/O)

**Analogs:**
1. `src/main.py` — orchestrate preprocess then analyze
2. `src/compliance/preprocessing/claim_batch.py` — discovery filter + format allowlist
3. `src/compliance/workflows/pipeline.py` — `_validate_claim_dir_name`, Path from config

**Claim discovery / claim_id naming** (`claim_batch.py` lines 35–57):
```python
folders = [path for path in data_dir.iterdir() if path.is_dir() and path.name.lower().startswith("claim")]
return sorted(folders, key=_claim_sort_key)
```
POST-generated `claim_id` **must** lowercase-start with `"claim"` or batch helpers ignore it. Prefer next `claim {n}` using `_CLAIM_NUM` / `_claim_sort_key`.

**Extension allowlist** (`claim_batch.py` lines 60–79):
```python
formats = {fmt.lower().lstrip(".") for fmt in document_formats}
...
suffix = path.suffix.lower().lstrip(".")
```
Map uploaded image suffix the same way against `config.preprocessing.document_formats`; reject with HTTP 422 when missing.

**Path safety** (`pipeline.py` lines 31–60):
```python
def _validate_claim_dir_name(name: str) -> None:
    if os.sep in name or (os.altsep is not None and os.altsep in name):
        _path_safety_denial(name, reason="path_separator")
    if name in {".", ".."}:
        _path_safety_denial(name, reason="dot_segment")
    ...
    raise ValueError(f"Unsafe claim directory name: {name!r}")
```
Call before any `data_dir / claim_id` join. Map `ValueError` → HTTP 422 at the route boundary. Store uploads with `Path(filename).name` only.

**Config roots — never hardcode** (`pipeline.py` lines 207–215, 260):
```python
return Path(self._config.preprocessing.preprocessed_dir)
...
data_dir = Path(self._config.preprocessing.data_dir)
```
Routes use `Path(config.preprocessing.data_dir)` / `results_dir` / `artifacts.*` from `AppConfig`.

**Artifact filenames** (`settings.py` lines 22–28):
```python
description: str = "description.txt"
answer: str = "answer.json"
predicted_answer: str = "predicted_answer.json"
analysis_result: str = "analysis_result.json"
supporting_document: str = "supporting_document.md"
supporting_documents: str = "supporting_documents.md"
```
POST writes `description.txt`, `supporting_documents.md`, and image basename under raw `data_dir/{claim_id}/`. List/GET read `artifacts.predicted_answer` / `artifacts.analysis_result` under `results_dir`.

**File write style** (`pipeline.py` lines 326–343, 360–364):
```python
(claim_out / names.description).write_bytes(...)
(claim_out / names.supporting_documents).write_text(..., encoding="utf-8")
results_claim.mkdir(parents=True, exist_ok=True)
predicted_path.write_text(predicted.model_dump_json(indent=2) + "\n", encoding="utf-8")
```
For POST new claims: `claim_dir.mkdir(parents=False)` (no `exist_ok`) → map `FileExistsError` to 409. Prefer sync `def` route handlers for pipeline endpoints (Starlette threadpool; RESEARCH Pitfall 5).

**Orchestration for GET** — call shared helper (see `orchestration.py`), not duplicated loops:
```python
preprocessing.process_claim(claim_dir)
return claims.analyze_claim(claim_dir)  # claim_dir.name is the safe segment
```

**List endpoint:** iterate `Path(config.preprocessing.results_dir)` subdirs (same `startswith("claim")` filter), load optional JSON files via artifact names; return pydantic schemas.

**Logging:** claim id + exception type only — see Shared Patterns / `branch_log`.

---

### `src/api/schemas.py` (model, request-response)

**Analog:** `src/compliance/models/claim.py` + `src/compliance/config/settings.py`

**Pydantic conventions** (`claim.py` lines 1–6, 33–49):
```python
from __future__ import annotations

from pydantic import BaseModel, Field
...
class GroundTruth(NanAwareModel):
    """Ground-truth decision from answer.json.

    :param decision: Required approve/deny/uncertain decision string.
    ...
    """
    decision: str
    explanation: NanStr = _MISSING
```

**Config models** (`settings.py` lines 31–47): public models get class docstrings with `:param:`; use `Field(default_factory=...)` for nested defaults.

API response models should be plain `BaseModel` (no NanAware unless echoing claim domain models). Suggested shapes from RESEARCH:
- `ClaimCreated` — `{claim_id: str}` (201)
- `ClaimDecision` — `{claim_id, analysis_result?, predicted_answer?}`
- `ClaimListItem` / `ClaimListResponse` — list of the above

Prefer nesting `dict[str, object]` or typed submodels aligned with `_analysis_result_payload` (`claim_pipeline.py` lines 432–449):
```python
payload: dict[str, object] = {
    "claim_id": state["claim_id"],
    "coverage_labels": list(state.get("coverage_labels") or []),
    "reason_labels": list(state.get("reason_labels") or []),
    "document_labels": list(state.get("document_labels") or []),
}
```

---

### `src/compliance/workflows/orchestration.py` (service, transform)

**Analogs:** `src/main.py` `_workflow_exit_code` + single-claim APIs on both pipelines

**CLI orchestration today** (`main.py` lines 73–80):
```python
def _workflow_exit_code(config: AppConfig, *, mode: CliMode) -> int:
    if mode == "analyze":
        written = ClaimPipeline(config).run()
        ...
        return 0
    written = PreprocessingPipeline(config).run()
    ...
```

**Single-claim APIs already exist** — compose them; do not reimplement Docling/LangGraph:

`pipeline.py` lines 222–230:
```python
def process_claim(self, claim_dir: Path, output_root: Path | None = None) -> Path:
    """Project one claim folder into a mirrored preprocessed artifact tree.
    ...
    """
    _validate_claim_dir_name(claim_dir.name)
```

`claim_pipeline.py` lines 102–119:
```python
def analyze_claim(self, claim_dir: Path) -> Path:
    """Run claim analysis for one claim and write analysis_result.json.
    ...
    """
    _validate_claim_dir_name(claim_dir.name)
    ...
    graph.invoke({"claim_id": claim_dir.name})
    return self._analysis_result_path(claim_dir.name)
```

**Target helper** (RESEARCH Pattern 3 — place in this module):
```python
def process_then_analyze(
    claim_dir: Path,
    preprocessing: PreprocessingPipeline,
    claims: ClaimPipeline,
) -> Path:
    """Preprocess one raw claim folder then run ClaimPipeline analysis.

    :param claim_dir: Raw claim directory under data_dir (name = claim_id).
    :param preprocessing: Injected PreprocessingPipeline.
    :param claims: Injected ClaimPipeline.
    :return: Path to written analysis_result.json.
    """
    preprocessing.process_claim(claim_dir)
    return claims.analyze_claim(claim_dir)
```

Export from `workflows/__init__.py` if CLI/API both import it.

---

### `src/main.py` (modify — controller, batch)

**Analog:** itself

**Extend `_cli_args` / `CliArgs`** (lines 18–70): add optional `--claim-id` (or path) under Claude's discretion; keep default batch `.run()` unchanged.

**When claim filter set:** resolve `Path(config.preprocessing.data_dir) / claim_id`, validate name, call `process_then_analyze` (or mode-specific single-claim) instead of `.run()`.

**Do not** create pipelines twice differently from the API — same orchestration helper.

---

### `src/compliance/workflows/pipeline.py` / `claim_pipeline.py` (modify — service, batch)

**Analog:** themselves

**Batch soft-fail loop** (`pipeline.py` lines 279–298; mirrored in `claim_pipeline.py` 148–173):
```python
for claim_dir in folders:
    logger.info("Processing %s", claim_dir.name)
    try:
        written.append(self.process_claim(claim_dir, output_root))
    except Exception as exc:
        log_branch_decision(
            logger,
            branch="preprocessed_write",
            outcome="SKIP",
            reason="claim_failed",
            level=logging.ERROR,
            claim=claim_dir.name,
            error=type(exc).__name__,
        )
```

R020 is mostly satisfied by `process_claim` / `analyze_claim`. Prefer optional `claim_dir` / filter on `run()` **or** CLI-only filter rather than duplicating discovery loops. If extending `run()`, keep soft-fail semantics and discovery via `_discover_claim_folders`.

---

### `pyproject.toml` (modify — config)

**Analog:** itself

**Hatch packages** (lines 51–55) — must include `src/api` (RESEARCH Pitfall 6):
```toml
[tool.hatch.build.targets.wheel]
packages = ["src/compliance"]

[tool.hatch.build.targets.wheel.force-include]
"src/main.py" = "main.py"
```

Change `packages` to `["src/compliance", "src/api"]` (or equivalent force-include). Add runtime deps via `uv add fastapi "uvicorn[standard]" python-multipart` and `uv add --dev httpx` after human-verify checkpoint.

**mypy** already covers `files = ["src"]` (line 63) — new `src/api` is included automatically.

---

### `tests/test_api/test_claims_post.py` (test, file-I/O)

**Analog:** `tests/test_workflows/test_pipeline.py` — tmp claim folders + config roots

**Config builder pattern** (from `test_claim_pipeline.py` lines 95–133 — prefer this fuller helper for API tests needing analysis too):
```python
def _config(
    data_dir: Path,
    *,
    preprocessed_dir: Path | str | None = None,
    results_dir: Path | str | None = None,
) -> AppConfig:
    return AppConfig(
        preprocessing=PreprocessingConfig(
            data_dir=str(data_dir),
            document_formats=["webp", "jpg", "jpeg", "png", "pdf"],
            confidence_threshold=0.7,
            preprocessed_dir=str(preprocessed_dir or data_dir / "preprocessed"),
            results_dir=str(results_dir or data_dir / "results"),
        ),
        ...
    )
```

**Seed raw claim style** (`test_pipeline.py` lines 135–140):
```python
claim = tmp_path / "claim 7"
claim.mkdir()
(claim / "scan.png").write_bytes(b"png")
```

For POST: use `TestClient` multipart `files=` (RESEARCH Code Example); assert `201`, `claim_id.lower().startswith("claim")`, and files under `Path(config.preprocessing.data_dir) / claim_id`. Assert bad suffix → 422; unsafe name → 422; duplicate → 409.

**Do not mock** `PreprocessingPipeline` internals — only inject config roots + optional `chat_fn` on ClaimPipeline for GET tests.

---

### `tests/test_api/test_claims_get.py` (test, request-response)

**Analog:** `tests/test_workflows/test_claim_pipeline.py`

**Injectable chat_fn** (lines 140–161, 190–214):
```python
chat_fn = _cancellation_chat_fn()
pipeline = ClaimPipeline(config, chat_fn=chat_fn)
result_path = pipeline.analyze_claim(claim_dir)
payload = json.loads(result_path.read_text(encoding="utf-8"))
```

Wire the same `chat_fn` into `create_app` / lifespan so GET `/claims/{id}` does not call live Ollama. Assert response JSON matches `analysis_result` payload keys. Missing raw folder → 404.

**Lifespan in tests:** `with TestClient(app) as client:` (RESEARCH Pitfall 2).

---

### `tests/test_api/test_claims_list.py` (test, file-I/O)

**Analog:** `tests/test_workflows/test_pipeline.py` predicted_answer write assertions

Seed `results_dir / "claim N" / artifacts.predicted_answer` (and optionally `analysis_result`) then GET `/claims`; assert list length and claim_ids. Use artifact names from config, never hardcoded filenames in assertions beyond reading `config.preprocessing.artifacts`.

---

### `tests/test_api/test_deps_lifespan.py` (test, request-response)

**Analog:** constructor DI tests in `test_claim_pipeline.py`

Assert that under `with TestClient(app) as client:`, Depends-resolved pipelines are the same instances yielded by lifespan (identity or successful process call). No FastAPI analog in-repo — follow RESEARCH Pattern 1 + TestClient context manager.

## Shared Patterns

### Configuration & paths
**Source:** `src/compliance/config/settings.py` (`load_config`, `AppConfig`, `PreprocessedArtifactNames`)
**Apply to:** `app.py`, all routes, orchestration, tests

```184:198:src/compliance/config/settings.py
def load_config(path: str | Path = "config.yaml") -> AppConfig:
    ...
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(raw)
```

Always `Path(config.preprocessing.data_dir)` / `preprocessed_dir` / `results_dir` once at call site — never hardcode `data/raw` or `data/results`.

### Path-safety validation
**Source:** `src/compliance/workflows/pipeline.py` `_validate_claim_dir_name`
**Apply to:** POST claim_id, GET path param, any upload filename basename check

Reuse the existing function (import from `pipeline` or re-export). Translate `ValueError` to HTTP 422 at the API boundary only.

### Claim folder discovery
**Source:** `src/compliance/preprocessing/claim_batch.py` `_discover_claim_folders`
**Apply to:** claim_id generation, GET `/claims` listing, any batch filter

Names must `startswith("claim")` (case-insensitive). Sort via numeric `_claim_sort_key` when generating next id.

### Dependency injection for tests
**Source:** `ClaimPipeline(..., chat_fn=)` + `PreprocessingPipeline(..., **reader_overrides)`
**Apply to:** lifespan/`create_app` factory and GET tests

Do not mock private helpers; inject seams and tmp config roots.

### Structured branch logging (no PII)
**Source:** `src/compliance/branch_log.py`
**Apply to:** API error paths and orchestration logging

```34:61:src/compliance/branch_log.py
def log_branch_decision(
    log: logging.Logger,
    *,
    branch: str,
    outcome: str,
    reason: str,
    level: int = logging.INFO,
    **fields: object,
) -> None:
    ...
```

Log `claim=` and `error=type(exc).__name__` only — never description/OCR bodies (Phase 04 / CLAUDE.md).

### Module style
**Source:** CLAUDE.md + all `src/compliance/**/*.py`
**Apply to:** every new `src/api` module

- `from __future__ import annotations`
- Typed params/returns; `X | None`
- Public docstrings with `:param:`
- Small helpers named after products; public methods orchestrate
- Validate only at HTTP/filesystem boundaries

### Packaging
**Source:** `pyproject.toml` hatch wheel config
**Apply to:** Wave 0 packaging task

Include `src/api` in hatch `packages` alongside `src/compliance`.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| FastAPI `APIRouter` / `UploadFile` / `HTTPException` usage | controller | request-response | No ASGI/web framework code in repo yet — use `05-RESEARCH.md` Patterns 1–2 + official FastAPI docs |
| `fastapi.testclient.TestClient` harness | test | request-response | No HTTP tests yet — copy RESEARCH TestClient multipart example; reuse `_config` / `chat_fn` from workflow tests |

Planner should treat RESEARCH FastAPI snippets as the HTTP-layer analog and the files above as the domain/config/test analogs.

## Metadata

**Analog search scope:** `src/**/*.py`, `tests/**/*.py`, `pyproject.toml` (git-tracked only)
**Files scanned:** 47 tracked source/test/config paths under `src/`, `tests/`, `pyproject.toml`
**Tracked-source gate:** all listed analogs verified via `git ls-files`
**Pattern extraction date:** 2026-09-25
