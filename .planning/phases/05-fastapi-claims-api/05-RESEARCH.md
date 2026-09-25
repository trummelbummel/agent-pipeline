# Phase 5: FastAPI Claims API - Research

**Researched:** 2026-09-25
**Domain:** FastAPI multipart Claims API + single-claim pipeline orchestration
**Confidence:** HIGH (codebase anchors); MEDIUM (FastAPI API surface from official docs via WebFetch)

<user_constraints>
## User Constraints (from CONTEXT.md / phase-add locked decisions)

> Note: `05-CONTEXT.md` does not exist. Locked decisions below are copied from the phase-add / orchestrator brief and ROADMAP Phase 05 success criteria.

### Locked Decisions
- FastAPI under `src/api`
- Paths from `config.yaml` never hardcoded
- Single-claim + batch refactor of pipelines (PreprocessingPipeline / ClaimPipeline / main)
- Lifespan/DI for pipeline instances
- Write submitted claims to `data/raw/{claim_id}/` (config `data_dir`, default `data/raw`)
- Three endpoints: `POST /claims`, `GET /claims/{claim_id}`, `GET /claims`
- mypy + pytest must pass

### Claude's Discretion
- claim_id generation scheme (must remain discoverable by existing batch helpers)
- Exact multipart field names / response JSON shapes
- Whether `GET /claims` returns `predicted_answer`, `analysis_result`, or both
- How main CLI exposes single-claim mode (flag vs path argument)
- Whether API package is hatch-packaged alongside `compliance`
- Sync `def` vs `async def` + thread offload for blocking pipeline calls

### Deferred Ideas (OUT OF SCOPE)
- Auth / API keys / multi-tenant access control (not in ROADMAP Phase 05)
- Async queue / background jobs for long-running analysis
- Flask alternative (takehome allows Flask; phase locks FastAPI)
- Changing Phase 04 LangGraph taxonomy or Checker behavior
</user_constraints>

<phase_requirements>
## Phase Requirements

Derived from ROADMAP Phase 05 success criteria (REQUIREMENTS.md has no R017+ yet — planner should add these IDs).

| ID | Description | Research Support |
|----|-------------|------------------|
| R017 | `POST /claims` multipart: description.txt, supporting_documents.md, image with extension in config `document_formats`; writes under config `data_dir/{claim_id}/` | UploadFile + File + Form; extension allowlist; path-safety; claim_id naming |
| R018 | `GET /claims/{claim_id}` runs PreprocessingPipeline then ClaimPipeline for one claim (same orchestration as main) and returns the decision | Existing `process_claim` / `analyze_claim`; shared orchestrator; TestClient with injectable chat_fn |
| R019 | `GET /claims` lists all processed claim answers from config `results_dir` | Scan `results_dir` claim folders; surface `predicted_answer` and/or `analysis_result` artifacts |
| R020 | Pipelines accept a single claim folder as well as a full directory; main shares that orchestration | Extend `run()` / CLI; prefer optional `claim_dir` over duplicating loops |
| R021 | Pipelines provided as FastAPI lifespan/resource fixtures (dependency injection) | Starlette lifespan state + Depends |
| R022 | mypy + pytest pass for API + pipeline refactor | TestClient + httpx; Wave 0 stubs; hatch package layout for `src/api` |
</phase_requirements>

## Summary

Phase 05 wraps existing preprocessing and claim-analysis pipelines behind a FastAPI surface under `src/api`. The heavy lifting is already present: `PreprocessingPipeline.process_claim` and `ClaimPipeline.analyze_claim` implement single-claim paths; `run()` implements soft-fail batch. What is missing is (1) a FastAPI app with multipart submit + list/get, (2) a shared “process one claim end-to-end” orchestrator used by both `GET /claims/{id}` and optionally `main`, (3) packaging/`uv add` for FastAPI stack, and (4) boundary validation for uploads (extension allowlist, path-safe claim_id).

**Primary recommendation:** Add `src/api` with lifespan-yielded `PreprocessingPipeline` + `ClaimPipeline` on `request.state`, three REST routes matching ROADMAP, write uploads under `Path(config.preprocessing.data_dir) / claim_id`, and extract a small shared helper that calls `process_claim` then `analyze_claim` so CLI and API cannot drift.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Multipart claim intake (`POST /claims`) | API / Backend | Database / Storage | HTTP boundary validates files; persistence is filesystem under config `data_dir` |
| Single-claim preprocess + analyze (`GET /claims/{id}`) | API / Backend | — | Orchestrates existing sync pipelines; no browser logic |
| List processed answers (`GET /claims`) | API / Backend | Database / Storage | Reads `results_dir` artifacts only |
| Pipeline batch / single-claim refactor | API / Backend | — | Domain logic stays in `compliance.workflows`; API/CLI call it |
| Lifespan DI of pipelines | API / Backend | — | Shared expensive resources created once per process |
| Config roots / artifact names | Database / Storage | — | Owned by `config.yaml` → `AppConfig` |
| Path-safety / upload sanitization | API / Backend | — | System-boundary validation (CLAUDE.md) |

## Project Constraints (from CLAUDE.md)

- Small helpers named after products; structured returns; public orchestrates / private works
- `from __future__ import annotations`; typed params/returns; `X | None`; public docstrings with `:param:`
- Validate only at system boundaries; no defensive internal try/except theater
- Config values (paths, formats, models) from `config.yaml` only — never hardcode roots
- Join with `Path` / `/`; config string → `Path(...)` once at call site
- Sanitize external input; no PII/secrets in logs
- Test real implementations where possible; do not mock internals; only tests for what was asked

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | 0.141.1 (PyPI latest probed) | ASGI web framework, routing, DI, OpenAPI | Locked by phase; takehome allows FastAPI/Flask |
| python-multipart | 0.0.32 | Parses `multipart/form-data` for `File`/`Form` | Required by FastAPI for uploads `[CITED: fastapi.tiangolo.com/tutorial/request-files/]` |
| uvicorn | 0.54.0 | ASGI server to run the app locally | FastAPI’s standard production/dev server |
| httpx | 0.28.1 | HTTP client; required by FastAPI `TestClient` | Official testing path `[CITED: fastapi.tiangolo.com/tutorial/testing/]` |

### Supporting (already in repo)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic | (via fastapi / existing) | Response/request models | API response schemas aligned with analysis payloads |
| pytest | 9.1.1 | Unit/API tests | Existing project test runner |
| mypy | 2.3.1 | Static typing | `pyproject.toml` `[tool.mypy]` covers `src` |
| pyyaml + AppConfig | existing | Config load | Lifespan loads `load_config()` once |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| FastAPI | Flask | Takehome allows Flask; **locked out** by phase decision |
| Lifespan state | `@app.on_event("startup")` | Deprecated vs lifespan; FastAPI recommends lifespan only `[CITED: fastapi.tiangolo.com/advanced/events/]` |
| `bytes` File param | `UploadFile` | `bytes` loads whole file into memory; images should use `UploadFile` |
| BackgroundTasks | Sync `def` route | Phase wants immediate decision on GET; no queue in scope |

**Installation:**
```bash
uv add fastapi "uvicorn[standard]" python-multipart
uv add --dev httpx
```

**Version verification:** PyPI `pip index versions` on 2026-09-25: fastapi `0.141.1`, uvicorn `0.54.0`, python-multipart `0.0.32`, httpx `0.28.1`. `[VERIFIED: pip index versions]`

## Package Legitimacy Audit

> Seam `gsd_run query package-legitimacy check --ecosystem pypi` returned **SUS** for all four packages with reasons `unknown-downloads` / `too-new` (uvicorn). Registry existence and official GitHub repos confirmed; downloads metadata appears unavailable to the checker — treat as **Flagged** per protocol, not SLOP.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| fastapi | PyPI | mature (exists; latest 0.141.1) | unknown to seam | https://github.com/fastapi/fastapi | SUS | Flagged — planner must add `checkpoint:human-verify` before `uv add` |
| uvicorn | PyPI | mature (0.54.0 published 2026-09-25 per seam) | unknown | https://github.com/Kludex/uvicorn | SUS | Flagged — human-verify |
| python-multipart | PyPI | mature (0.0.32) | unknown | https://github.com/Kludex/python-multipart | SUS | Flagged — human-verify |
| httpx | PyPI | mature (0.28.1) | unknown | https://github.com/encode/httpx | SUS | Flagged — human-verify (dev dep) |

**Packages removed due to [SLOP] verdict:** none

**Packages flagged as suspicious [SUS]:** fastapi, uvicorn, python-multipart, httpx — all well-known stack packages; seam flag is downloads-metadata gap. Planner: single Wave 0 `checkpoint:human-verify` covering the FastAPI stack before install.

Inline: `fastapi` [WARNING: flagged as suspicious — verify before using.] Same for uvicorn, python-multipart, httpx.

## Architecture Patterns

### System Architecture Diagram

```text
Client (multipart / JSON)
        │
        ▼
┌───────────────────┐
│  FastAPI src/api  │  lifespan: load_config → PreprocessingPipeline + ClaimPipeline
│  Depends(state)   │
└─────────┬─────────┘
          │
    ┌─────┴──────┬────────────────────┐
    ▼            ▼                    ▼
POST /claims   GET /claims/{id}     GET /claims
    │            │                    │
    ▼            ▼                    ▼
write files   process_claim →      list results_dir/
under         analyze_claim →      {claim}/predicted_answer.json
data_dir/     return decision JSON   and/or analysis_result.json
{claim_id}/
```

### Recommended Project Structure

```text
src/
├── api/
│   ├── __init__.py
│   ├── app.py              # create_app(), lifespan, FastAPI instance
│   ├── deps.py             # Depends helpers reading request.state
│   ├── routes_claims.py    # POST/GET /claims
│   └── schemas.py          # Pydantic response models
├── compliance/
│   └── workflows/
│       ├── pipeline.py           # PreprocessingPipeline (existing)
│       ├── claim_pipeline.py     # ClaimPipeline (existing)
│       └── orchestration.py      # NEW optional: process_then_analyze(claim_dir)
└── main.py                 # CLI: batch + optional single-claim
tests/
└── test_api/
    ├── test_claims_post.py
    ├── test_claims_get.py
    └── test_claims_list.py
```

### Pattern 1: Lifespan-injected pipelines

**What:** Create config + pipelines once in lifespan; yield Starlette state; inject via `Depends`.

**When to use:** Any shared resource used across requests (locked for this phase).

**Example:**
```python
# Source: https://starlette.dev/lifespan/ + https://fastapi.tiangolo.com/advanced/events/
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, TypedDict

from fastapi import Depends, FastAPI, Request

from compliance.config.settings import AppConfig, load_config
from compliance.workflows.claim_pipeline import ClaimPipeline
from compliance.workflows.pipeline import PreprocessingPipeline


class AppState(TypedDict):
    config: AppConfig
    preprocessing: PreprocessingPipeline
    claims: ClaimPipeline


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[AppState]:
    config = load_config("config.yaml")
    yield {
        "config": config,
        "preprocessing": PreprocessingPipeline(config),
        "claims": ClaimPipeline(config),
    }


app = FastAPI(lifespan=lifespan)


def get_preprocessing(request: Request) -> PreprocessingPipeline:
    return request.state["preprocessing"]


def get_claims(request: Request) -> ClaimPipeline:
    return request.state["claims"]
```

### Pattern 2: Multipart upload → raw claim folder

**What:** Three `UploadFile` fields; validate image suffix against `config.preprocessing.document_formats`; write under `Path(config.preprocessing.data_dir) / claim_id`.

**When to use:** `POST /claims` only.

**Example:**
```python
# Source: https://fastapi.tiangolo.com/tutorial/request-forms-and-files/
from pathlib import Path
from typing import Annotated

from fastapi import File, HTTPException, UploadFile

from compliance.workflows.pipeline import _validate_claim_dir_name


async def write_claim_upload(
    *,
    data_dir: Path,
    claim_id: str,
    document_formats: list[str],
    description: UploadFile,
    supporting_documents: UploadFile,
    image: UploadFile,
) -> Path:
    _validate_claim_dir_name(claim_id)
    suffix = Path(image.filename or "").suffix.lower().lstrip(".")
    allowed = {fmt.lower().lstrip(".") for fmt in document_formats}
    if suffix not in allowed:
        raise HTTPException(status_code=422, detail="image extension not in document_formats")
    claim_dir = data_dir / claim_id
    claim_dir.mkdir(parents=False)  # fail if exists — avoid overwrite races
    (claim_dir / "description.txt").write_bytes(await description.read())
    (claim_dir / "supporting_documents.md").write_bytes(await supporting_documents.read())
    (claim_dir / Path(image.filename or f"document.{suffix}").name).write_bytes(
        await image.read()
    )
    return claim_dir
```

### Pattern 3: Shared single-claim orchestration

**What:** One helper used by API GET and optionally CLI so “same logic as main” is literal.

```python
from pathlib import Path

from compliance.workflows.claim_pipeline import ClaimPipeline
from compliance.workflows.pipeline import PreprocessingPipeline


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

### Anti-Patterns to Avoid

- **Hardcoding `data/raw` or `data/results` in routes:** violates CLAUDE.md / locked decision — always `Path(config.preprocessing.*)`.
- **Creating pipelines per request:** defeats lifespan DI; Docling/LLM setup should be once.
- **UUID claim folders that do not start with `claim`:** batch discovery filters `startswith("claim")` — see Pitfall 1.
- **Returning description/OCR text in list/error logs:** CLAUDE.md + Phase 04 logging rule — log claim ids and exception types only.
- **Mixing JSON Body with multipart File params:** HTTP limitation documented by FastAPI.
- **Mocking PreprocessingPipeline internals in API tests:** inject `chat_fn` on ClaimPipeline and tmp `data_dir` instead; do not mock private helpers.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Multipart parsing | Custom CGI/boundary parsers | FastAPI `File`/`Form` + python-multipart | Encoding edge cases |
| ASGI test client | Custom HTTP harness | `fastapi.testclient.TestClient` + httpx | Official; runs lifespan with context manager |
| OpenAPI schema | Hand-written swagger | FastAPI auto OpenAPI | Takehome asks for API docs |
| Path traversal guards | Ad-hoc string checks only | Reuse `_validate_claim_dir_name` + basename for uploaded filenames | Already Phase 03/04 pattern |
| Config loading | Env-scattered paths | `load_config` / `AppConfig` | Existing typed config |

**Key insight:** Phase 05 is an HTTP adapter over mature pipelines — resist reimplementing classification or Docling inside `src/api`.

## Common Pitfalls

### Pitfall 1: claim_id not discoverable by batch helpers

**What goes wrong:** New folders named `uuid-...` never appear in `PreprocessingPipeline.run()` / ClaimPipeline batch.

**Why it happens:** `_discover_claim_folders` only keeps directories whose name lowercases to start with `"claim"`.

```45:45:src/compliance/preprocessing/claim_batch.py
    folders = [path for path in data_dir.iterdir() if path.is_dir() and path.name.lower().startswith("claim")]
```

`[VERIFIED: src/compliance/preprocessing/claim_batch.py:45]` quote: `path.name.lower().startswith("claim")`

**How to avoid:** Generate `claim {n}` (next integer after max under `data_dir`) or any single-segment name starting with `claim` that passes `_validate_claim_dir_name`.

**Warning signs:** POST succeeds but batch CLI ignores the new folder.

### Pitfall 2: Lifespan not entered in tests

**What goes wrong:** `request.state` missing / AttributeError in tests.

**Why it happens:** Instantiating `TestClient(app)` without context manager skips lifespan.

**How to avoid:** `with TestClient(app) as client:` `[CITED: starlette.dev/lifespan/]`

**Warning signs:** First test fails only when Depends reads state.

### Pitfall 3: Image extension vs filename spoofing

**What goes wrong:** Client uploads `.png.exe` or empty filename; Docling path mis-routes.

**Why it happens:** Trusting `content_type` alone or writing `Path(user_filename)` with parents.

**How to avoid:** Allowlist `suffix` against `document_formats`; store with `Path(filename).name` only; reject missing filename.

**Warning signs:** 500 from FormatConverter / DocumentReader on weird suffixes.

### Pitfall 4: Confusing “decision” artifacts

**What goes wrong:** `GET /claims` returns empty while folders exist, or GET-by-id returns preprocessing fraud deny instead of analysis.

**Why it happens:** Today `data/results/claim N/` commonly holds only `predicted_answer.json` (preprocessing Benford/fraud path). Analysis writes `analysis_result.json` via ClaimPipeline.

```21:25:src/compliance/config/settings.py
    description: str = "description.txt"
    answer: str = "answer.json"
    predicted_answer: str = "predicted_answer.json"
    analysis_result: str = "analysis_result.json"
    supporting_document: str = "supporting_document.md"
```

`[VERIFIED: src/compliance/config/settings.py:21-25]`

**How to avoid:** Define response schema that includes `claim_id` plus optional `predicted_answer` and `analysis_result` objects; GET-by-id should run both pipelines and return at least `analysis_result` payload (ROADMAP “decision”).

**Warning signs:** List endpoint only looks for one filename.

### Pitfall 5: Blocking LLM/Docling on the event loop

**What goes wrong:** Concurrent requests stall behind one Ollama/Docling call.

**Why it happens:** `async def` route calling sync `process_claim` / `analyze_claim` without offload.

**How to avoid:** Use sync `def` path operations (Starlette threadpool) for pipeline endpoints, or `asyncio.to_thread(...)`. Prefer `def` for simplicity.

**Warning signs:** Latency spikes under two parallel GETs.

### Pitfall 6: Hatch package omits `src/api`

**What goes wrong:** Installed wheel has no `api` module; `uvicorn api.app:app` fails after install.

**Why it happens:** Current hatch config packages only `compliance`:

```51:52:pyproject.toml
[tool.hatch.build.targets.wheel]
packages = ["src/compliance"]
```

`[VERIFIED: pyproject.toml:51-52]`

**How to avoid:** Add `src/api` to hatch `packages` (or force-include) in the same plan that creates the package.

## Code Examples

### TestClient multipart POST

```python
# Source: https://fastapi.tiangolo.com/tutorial/testing/ + httpx files= API
from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app


def test_post_claims_writes_raw_folder(tmp_path: Path, monkeypatch) -> None:
    # create_app should accept config path / AppConfig for tests
    app = create_app(config_path=...)  # factory with tmp data_dir
    with TestClient(app) as client:
        files = {
            "description": ("description.txt", b"I need to cancel", "text/plain"),
            "supporting_documents": ("supporting_documents.md", b"# docs\n", "text/markdown"),
            "image": ("scan.png", b"\x89PNG\r\n\x1a\n", "image/png"),
        }
        response = client.post("/claims", files=files)
    assert response.status_code == 201
    body = response.json()
    assert body["claim_id"].lower().startswith("claim")
```

### Single-claim CLI alignment (discretion)

```python
# Align main with API orchestration — optional --claim-id
# Existing batch path remains default.
written = ClaimPipeline(config).run()  # batch — already exists
# single:
ClaimPipeline(config).analyze_claim(Path(config.preprocessing.preprocessed_dir) / claim_id)
```

Current main only calls `.run()`:

```73:79:src/main.py
def _workflow_exit_code(config: AppConfig, *, mode: CliMode) -> int:
    if mode == "analyze":
        written = ClaimPipeline(config).run()
        logger.info("Analysis workflow complete (%d claims written)", len(written))
        return 0
    written = PreprocessingPipeline(config).run()
    logger.info("Preprocessing workflow complete (%d claims written)", len(written))
    return 0
```

`[VERIFIED: src/main.py:73-79]`

### Existing single-claim APIs (already implemented)

```222:228:src/compliance/workflows/pipeline.py
    def process_claim(self, claim_dir: Path, output_root: Path | None = None) -> Path:
        """Project one claim folder into a mirrored preprocessed artifact tree.

        :param claim_dir: Source claim folder path.
        :param output_root: Destination root; defaults to ``self.output_root``.
        :return: Path to the written claim output directory.
```

`[VERIFIED: src/compliance/workflows/pipeline.py:222-228]`

```102:119:src/compliance/workflows/claim_pipeline.py
    def analyze_claim(self, claim_dir: Path) -> Path:
        """Run claim analysis for one claim and write analysis_result.json.

        :param claim_dir: Claim folder whose ``name`` is the safe path segment.
        :return: Path to the written analysis_result.json under results_dir.
        :raises ValueError: When ``claim_dir.name`` is not a safe single path segment.
        """
        _validate_claim_dir_name(claim_dir.name)
        ...
        graph.invoke({"claim_id": claim_dir.name})
        return self._analysis_result_path(claim_dir.name)
```

`[VERIFIED: src/compliance/workflows/claim_pipeline.py:102-119]`

**Refactor scope note:** “Accept single claim folder as well as full directory” is **mostly done** at the pipeline class level. Remaining work is CLI/`run()` optional filter + shared API orchestrator so GET matches main.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@app.on_event("startup")` | `lifespan=` async context manager | FastAPI lifespan docs | Prefer lifespan exclusively |
| Module-level global pipelines | Lifespan `yield {state}` + `request.state` | Starlette lifespan state | Testable; typed state |
| Flask for takehome | FastAPI (locked) | Phase 05 add | OpenAPI free |

**Deprecated/outdated:**
- FastAPI `startup`/`shutdown` event handlers when `lifespan` is set — “all lifespan or all events, not both” `[CITED: fastapi.tiangolo.com/advanced/events/]`

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | claim_id should be next `claim {n}` under data_dir | Pitfall 1 / Discretion | User may want client-supplied id — still must start with `claim` or discovery breaks |
| A2 | GET decision body = `analysis_result.json` (+ optional `predicted_answer`) | Pitfall 4 | Product may want only predicted APPROVE/DENY |
| A3 | POST field names: `description`, `supporting_documents`, `image` (files named as in ROADMAP) | Pattern 2 | Client contract mismatch |
| A4 | Sync `def` routes are preferred for pipeline endpoints | Pitfall 5 | Team may prefer explicit `to_thread` |
| A5 | No auth for Phase 05 | Deferred | Takehome may later require tokens |
| A6 | Package legitimacy SUS is metadata gap, not malware | Package Audit | Still requires human-verify checkpoint |

## Open Questions (RESOLVED)

1. **claim_id generation** — RESOLVED (A1 / D-08)
   - What we know: discovery requires names starting with `claim`; path safety rejects separators/`..`
   - **Decision:** Server-generated next `claim {n}` (numeric max+1 under `data_dir`); must pass `_validate_claim_dir_name` and lowercase-startswith `claim`; return `claim_id` in 201 body. No client-provided ids in Phase 05.

2. **List endpoint payload** — RESOLVED (A3)
   - What we know: results_dir currently has mostly `predicted_answer.json` only (23 files observed; no `analysis_result.json` on disk at research time)
   - **Decision:** List `{claim_id, predicted_answer?, analysis_result?}` for each subdirectory under `results_dir` (optional objects when files exist). GET-by-id decision body requires `analysis_result` after successful `process_then_analyze`; `predicted_answer` optional if present.

3. **Missing raw claim on GET** — RESOLVED (Open Q3 / 05-02)
   - What we know: GET runs preprocess + analyze from raw folder
   - **Decision:** HTTP 404 if `data_dir/{claim_id}` is missing; do not invent empty claims or analyze-preprocessed-only fallbacks.

4. **Factory for tests** — RESOLVED (A5 / D-10)
   - What we know: lifespan loads `config.yaml` by default
   - **Decision:** `create_app(config: AppConfig | None = None, chat_fn=...)` factory; default loads `config.yaml`; TestClient injects tmp-root AppConfig. Implemented in plan 05-01 (not Wave 0).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | runtime | ✓ | 3.14.2 | — |
| uv | package install | ✓ | 0.9.18 | pip |
| pytest | Nyquist tests | ✓ | 9.1.1 | — |
| mypy | type gate | ✓ | 2.3.1 | — |
| fastapi | API | ✗ (not installed) | — | `uv add` after human-verify |
| uvicorn | run server | ✗ | — | `uv add` |
| python-multipart | uploads | ✗ | — | `uv add` |
| httpx | TestClient | ✗ | — | `uv add --dev` |
| Ollama / local LLM | live GET analyze | unknown | — | injectable `chat_fn` in unit tests (no live LLM) |

**Missing dependencies with no fallback:** none blocking planning — install is a Wave 0 task.

**Missing dependencies with fallback:** live LLM — unit tests inject `ClaimPipeline(..., chat_fn=...)` like Phase 04; optional integration mark for live runs.

## Validation Architecture

> `workflow.nyquist_validation` absent in `.planning/config.json` → treated as **enabled**.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_api -x -q` |
| Full suite command | `uv run pytest && uv run mypy` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| R017 | POST writes three files under tmp data_dir/{claim_id}/; rejects bad image ext | unit | `uv run pytest tests/test_api/test_claims_post.py -x` | ❌ Wave 0 |
| R017 | POST refuses unsafe claim_id / path traversal filename | unit | same | ❌ Wave 0 |
| R018 | GET runs process_claim + analyze_claim; returns analysis JSON (inject chat_fn) | unit | `uv run pytest tests/test_api/test_claims_get.py -x` | ❌ Wave 0 |
| R018 | GET 404 when claim folder missing | unit | same | ❌ Wave 0 |
| R019 | GET /claims lists results_dir entries | unit | `uv run pytest tests/test_api/test_claims_list.py -x` | ❌ Wave 0 |
| R020 | main or pipeline.run accepts optional single claim | unit | extend `tests/test_workflows/test_pipeline.py` / claim_pipeline / main tests | ❌ Wave 0 |
| R021 | TestClient context manager exposes pipelines via Depends | unit | `tests/test_api/test_deps_lifespan.py` | ❌ Wave 0 |
| R022 | mypy clean on `src/api` | static | `uv run mypy` | existing config |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_api -x -q` (or targeted file)
- **Per wave merge:** `uv run pytest && uv run mypy`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_api/` package + POST/GET/list tests
- [ ] `create_app(config=...)` factory for tmp roots
- [ ] Framework install: `uv add fastapi uvicorn python-multipart` + `uv add --dev httpx` after human-verify
- [ ] Hatch `packages` includes `src/api`
- [ ] Optional: stub `tests/test_workflows/test_single_claim_cli.py` if CLI gains `--claim`

## Security Domain

> `security_enforcement` absent → treated as **enabled**.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Deferred — no auth in Phase 05 |
| V3 Session Management | no | Stateless API |
| V4 Access Control | no | Local takehome; no multi-tenant |
| V5 Input Validation | yes | Extension allowlist; `_validate_claim_dir_name`; basename-only filenames; FastAPI validation errors |
| V6 Cryptography | no | No new crypto |

### Known Threat Patterns for FastAPI file upload + filesystem

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal in claim_id or filename | Tampering | `_validate_claim_dir_name`; `Path(name).name` only; never join unsanitized strings |
| Upload of disallowed binary type | Tampering | Suffix ∈ `document_formats` from config |
| Overwrite existing claim | Tampering | `mkdir` without `exist_ok` → 409 Conflict |
| PII leakage in logs | Information Disclosure | Log claim_id + error type only (Phase 04 pattern) |
| DoS via huge upload | Denial of Service | UploadFile spooling; optional size limit at reverse proxy (out of scope) |

## Sources

### Primary (HIGH confidence — codebase)

- `src/main.py` — CLI orchestration modes
- `src/compliance/workflows/pipeline.py` — `process_claim` / `run`
- `src/compliance/workflows/claim_pipeline.py` — `analyze_claim` / `run`
- `src/compliance/preprocessing/claim_batch.py` — discovery filter `startswith("claim")`
- `src/compliance/config/settings.py` + `config.yaml` — roots and artifact names
- `pyproject.toml` — hatch packages, mypy/pytest

### Secondary (MEDIUM — official docs via WebFetch)

- https://fastapi.tiangolo.com/advanced/events/ — lifespan
- https://fastapi.tiangolo.com/tutorial/request-files/ — UploadFile
- https://fastapi.tiangolo.com/tutorial/request-forms-and-files/ — File+Form
- https://fastapi.tiangolo.com/tutorial/testing/ — TestClient / httpx
- https://starlette.dev/lifespan/ — lifespan state + TestClient context manager

### Tertiary (LOW)

- Package legitimacy seam SUS (downloads null) — human-verify before install
- WebSearch synthesis of Depends + request.state patterns

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM — versions verified on PyPI; legitimacy seam SUS requires checkpoint
- Architecture: HIGH — pipelines and config anchors verified in-repo; FastAPI patterns from official docs
- Pitfalls: HIGH — discovery filter and dual results artifacts verified in-repo

**Research date:** 2026-09-25
**Valid until:** 2026-10-25 (FastAPI minors move quickly; re-check versions at execute)
