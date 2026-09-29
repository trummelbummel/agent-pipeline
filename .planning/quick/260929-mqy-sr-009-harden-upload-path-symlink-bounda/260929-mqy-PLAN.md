---
phase: 260929-mqy-sr-009-harden-upload-path-symlink-bounda
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/compliance/config/settings.py
  - config.yaml
  - src/api/uploads.py
  - src/api/app.py
  - src/api/routes_claims.py
  - src/compliance/preprocessing/claim_batch.py
  - src/compliance/workflows/pipeline.py
  - src/compliance/workflows/claim_pipeline.py
  - src/compliance/workflows/artifact_publication.py
  - src/main.py
  - tests/test_api/test_claims_post.py
  - tests/test_api/test_uploads.py
  - tests/test_api/test_claims_paths.py
  - tests/test_config/test_settings.py
  - tests/test_preprocessing/test_claim_batch.py
  - tests/test_workflows/test_artifact_publication.py
  - README.md
  - .gsd/review_backlog.md
autonomous: true
requirements: [SR-009]

estimate:
  tokens: 130000
  raw_tokens: 130000
  tasks: 3
  confidence: low

must_haves:
  truths:
    - "An oversized upload is refused before it becomes disk: a part larger than the configured per-file cap and a request larger than the configured total cap both return 413 with a stable reason code, and the raw claim tree under data_dir is byte-for-byte what it was before the request — no claim folder, no partial file (D-01)"
    - "The per-file and per-request caps are 25 MiB and 50 MiB, sourced from config.yaml and never hardcoded in a handler, so an operator changes the limit by editing config and restarting rather than by editing Python (D-01)"
    - "A request whose declared Content-Length already exceeds the total cap is refused before the multipart parser buffers any part, so an attacker cannot spend server memory or spool space merely by announcing a huge body (D-01)"
    - "An upload that fits is written by streaming in bounded chunks with a running total rather than one whole-file read, so the peak memory of an intake request does not scale with the size of the uploaded file, and a file just under the cap still lands byte-identical"
    - "A symlinked claim root is refused, not followed: every entry point that analyses or preprocesses one named claim raises a path-safety error for a claim directory that is a symlink, and the API maps it to 422 while the CLI exits 1 (D-02)"
    - "Batch discovery applies the same containment: a symlinked claim directory, or one whose resolved path escapes the configured root, is excluded from the batch with a WARNING branch log naming the reason instead of being processed or silently dropped (D-03)"
    - "A configured artifact filename can no longer be a path: a name containing a separator, an absolute path, or a dot segment fails at config load with an error naming the offending field, so a config edit cannot redirect a write outside data_dir, preprocessed_dir or results_dir"
    - "Write-side roots are contained too: a symlinked results or preprocessed claim directory cannot redirect published artifacts outside the configured root, because the publication and mirroring paths validate the destination claim directory before creating or replacing anything in it"
    - "Gates: uv run python -m pytest -q --cov (fast lane, integration deselected) passes with coverage at or above the 90 floor. ruff check --no-fix src tests is clean, ruff format --check is clean on every touched path, and uv run mypy src reports 0 errors with tests/test_api no worse than its 8-error baseline"
  artifacts:
    - path: src/compliance/config/settings.py
      provides: "UploadLimitsConfig / ApiConfig carrying max_file_bytes and max_request_bytes on AppConfig.api, plus load-time basename validation for every configured artifact filename"
      contains: "class UploadLimitsConfig"
    - path: config.yaml
      provides: "api.upload section with the 25 MiB per-file and 50 MiB per-request byte caps (D-01)"
      contains: "max_request_bytes"
    - path: src/api/uploads.py
      provides: "the intake byte-limit boundary — UploadSizeLimitMiddleware (Content-Length precheck), write_upload_stream (chunked copy with per-file and running-request caps), and UploadTooLargeError carrying the reason code"
      contains: "class UploadSizeLimitMiddleware"
    - path: src/api/routes_claims.py
      provides: "create_claim streaming the three parts under the configured caps and returning 413 with file_too_large / request_too_large, leaving no claim folder behind; analysis POST validating the claim root against data_dir"
      contains: "file_too_large"
    - path: src/compliance/preprocessing/claim_batch.py
      provides: "_validate_claim_root — symlinked-claim-root hard reject plus optional resolve-based containment — and ClaimRootContainmentError; discovery excludes and logs rejected entries"
      contains: "def _validate_claim_root"
    - path: src/compliance/workflows/artifact_publication.py
      provides: "publication validates the destination claim directory under results_root before staging or promoting"
      contains: "_validate_claim_root"
    - path: tests/test_api/test_uploads.py
      provides: "unit proof of the chunked writer — per-file cap, running-request cap, partial-file cleanup, and byte-identical write just under the cap"
      contains: "UploadTooLargeError"
    - path: tests/test_api/test_claims_paths.py
      provides: "API path-boundary proof — symlinked claim root rejected with 422 on the analysis POST, traversal claim id rejected, and nothing read or written outside the configured roots"
      contains: "symlink"
    - path: tests/test_preprocessing/test_claim_batch.py
      provides: "discovery excludes symlinked and escaping claim directories; single-claim validation raises for a symlinked root"
      contains: "ClaimRootContainmentError"
    - path: tests/test_config/test_settings.py
      provides: "api.upload defaults and cap-ordering validation; artifact filenames that are not basenames rejected at load"
      contains: "max_file_bytes"
    - path: .gsd/review_backlog.md
      provides: "SR-009 checked off with recorded steering decisions (gitignored, never staged)"
      contains: "### [x] SR-009"
  key_links:
    - from: "config.yaml api.upload"
      to: "UploadSizeLimitMiddleware and write_upload_stream"
      via: "both enforcement layers read the same configured caps, so the declared-length precheck and the streamed total cannot disagree (D-01)"
      pattern: "max_request_bytes"
    - from: "POST /claims multipart intake"
      to: "write_upload_stream"
      via: "every uploaded part reaches disk only through the chunked writer that counts bytes against the per-file and per-request caps"
      pattern: "write_upload_stream"
    - from: "UploadTooLargeError"
      to: "HTTP 413 plus removal of the claim directory this request created"
      via: "an oversized upload is a stable client-visible outcome that leaves no partial claim folder under data_dir"
      pattern: "413"
    - from: "_validate_claim_root"
      to: "API analysis POST, CLI --claim-id, process_claim, analyze_claim, publish_claim_generation"
      via: "one helper is the single definition of a safe claim root, so no entry point can follow a symlinked claim directory (D-02)"
      pattern: "_validate_claim_root"
    - from: "_discover_claim_folders / discover_claim_folder_names"
      to: "path_safety DENY branch log"
      via: "batch discovery excludes a symlinked or escaping entry and records why, instead of processing it or dropping it silently (D-03)"
      pattern: "symlinked_claim_root"
    - from: "PreprocessedArtifactNames / EvaluationConfig artifact filenames"
      to: "UnsafeArtifactNameError at config load"
      via: "a configured filename is validated as a single basename before it is ever joined to a configured root"
      pattern: "UnsafeArtifactNameError"
---

<objective>
SR-009 is the last input-boundary hole in the backlog: "DoS + path escape". Today `POST /claims` reads all three multipart parts fully into memory (`description.file.read()`, `supporting_documents.file.read()`, `image.file.read()`) with no byte limit anywhere — no per-part cap, no request cap, no Content-Length precheck — so a single request can spend unbounded memory and unbounded disk under `data_dir`. On the path side, claim-name safety is well covered (`_validate_claim_dir_name` is called at every join) but *path* safety is not: nothing rejects a claim directory that is a symlink pointing outside the configured roots, and nothing validates that a configured artifact filename is a basename — `artifacts.analysis_result: ../../etc/x.json` in config.yaml would pass load and be joined to `results_dir` at every read and write.

This plan closes both. Intake gets two enforcement layers that read the same configured caps: an ASGI middleware that refuses a request whose declared `Content-Length` already exceeds the total cap (before FastAPI's multipart parser buffers or spools anything), and a chunked writer that copies each part to disk in bounded blocks while counting bytes against the per-file cap and a running request total. Both caps live in a new `api.upload` config section at 25 MiB and 50 MiB (D-01). A breach is a 413 with a stable reason code, and the claim directory this request created is removed, so a rejected upload leaves the raw tree exactly as it found it.

Containment gets one helper, `_validate_claim_root`, next to the existing name validator in `claim_batch.py`. It hard-rejects a symlinked claim root (D-02 — reject, not resolve-and-contain) and, when given a root, requires the resolved claim directory to stay inside the resolved root. Every entry point that names one claim calls it: the API analysis POST, the CLI `--claim-id`, `PreprocessingPipeline.process_claim`, `ClaimPipeline.analyze_claim`, and `publish_claim_generation` on the write side. Batch discovery applies the same containment (D-03), excluding a symlinked or escaping entry with a WARNING branch log rather than processing it or dropping it without a trace. Separately, every configured artifact filename is validated as a single basename at config load, so a config typo or edit can never redirect a path join.

Locked decisions (from CONTEXT.md and `.gsd/steering-decisions-2026-09-29.md`):
- D-01: 25 MB per file, 50 MB total request.
- D-02: Hard-reject symlinked claim roots (not resolve-and-contain).
- D-03: The same containment applies to CLI batch discovery.

Planner discretion (flagged; report in SUMMARY):
- P-01: The caps live in a new top-level `api.upload` section (`AppConfig.api.upload.max_file_bytes` / `max_request_bytes`), not under `preprocessing`. They bound an HTTP request, not document processing, and `preprocessing` is shared with the CLI and the evaluator where the concept has no meaning. `ApiConfig` defaults so no existing config file, fixture or test config needs a new key. A load-time validator requires `max_request_bytes >= max_file_bytes`, because a per-file cap above the request cap is unreachable policy — the SR-011 principle that contradictory config fails at startup.
- P-02: "25 MB / 50 MB" is expressed as binary megabytes: 26214400 and 52428800 bytes. Bytes are the unit the enforcement actually compares, so storing bytes removes a conversion that could drift between the two layers; the YAML comment names the MiB figures for a human reader.
- P-03: Two layers, not one. FastAPI parses the multipart body *before* the handler's dependencies run, so a check inside `create_claim` can only fire after the parts are already buffered/spooled — useless against the memory-and-disk DoS the backlog names. The middleware refuses an over-declared `Content-Length` before the parser sees the body; the chunked writer is the ground truth for a chunked or under-declared body. Both read the same config values.
- P-04: 413 (not 422) with stable snake_case details `file_too_large` and `request_too_large`, matching the SR-007 reason-code convention. The request is well-formed; it is too large. The existing 422s for filename and extension validation are untouched.
- P-05: 64 KiB chunks. On breach the partially written file is unlinked and `create_claim` removes the claim directory it created — safe because the directory is created with `mkdir(parents=False)`, which fails when it already exists, so the request provably owns it. A rejected upload therefore cannot leave a half-claim that a later batch run would try to process.
- P-06: Artifact-filename basename validation happens at config **load**, not at each use site, on `PreprocessedArtifactNames` and on the `EvaluationConfig` artifact fields, through one shared checker raising a dedicated `UnsafeArtifactNameError` (TRY003 style, as SR-011 established). A bad name is a config defect; catching it once at startup beats sprinkling checks over every join, and the error names the field.
- P-07: `ClaimRootContainmentError` is a plain `ValueError` subclass living beside `UnsafeClaimDirectoryError` in `claim_batch.py`, so every existing boundary that already catches `ValueError` — the API's 422 mapping, the CLI's exit 1, the soft-fail batch loops, the evaluator's skip — handles it with no new mapping and no new import at those sites.
- P-08: `_validate_claim_root(claim_dir, *, root=None)` takes an optional root. Entry points that join under a configured root (API, CLI `--claim-id`, discovery, publication, mirrored output) pass the root and get symlink rejection **plus** resolve-based containment. Entry points that legitimately accept a caller-supplied path from outside the configured tree (R020: `run(source)` / `process_claim` / `analyze_claim` with an external claim folder, proven by `test_cli_or_api_passes_path_from_outside`) pass no root and get symlink rejection only. Weakening that feature to force containment would break a shipped capability that no steering decision touches.
- P-09: `_is_claim_folder` is deliberately left unchanged. If it returned False for a symlinked claim directory, the caller would treat that directory as a *batch root* and iterate into it — strictly worse than the current behaviour, where it is recognised as a single claim and then hard-rejected by `process_claim` / `analyze_claim`.
- P-10: Batch discovery records and excludes rather than aborting the run: a rejected entry is logged `path_safety / DENY / symlinked_claim_root` (or `outside_root`) at WARNING and left out of the batch, matching the existing soft-fail batch convention and the backlog rule that a refused claim leaves a trace. Single-claim callers still get a raised error.

Behaviour changes to record in the SUMMARY (intended, not regressions):
- `POST /claims` can now return 413 for an oversized part or an oversized request.
- `config.yaml` gains an `api:` section; because `AppConfig` is `extra="forbid"`, a config file carrying `api:` keys outside the new model now fails at load.
- `create_app` resolves the configuration once at factory time (the middleware needs the cap before the first request), so a missing or invalid `config.yaml` surfaces when `uvicorn api.app:create_app --factory` builds the app rather than at first startup event.
- A symlinked claim directory under `data_dir` is excluded from every batch run and from evaluation discovery, and is rejected outright when named directly.

Purpose: make the intake boundary bounded and the path boundary unescapable, so neither an oversized upload nor a symlink or config edit can spend the box or reach outside the configured data roots.
Output: configured upload caps with a Content-Length precheck and a chunked writer, one claim-root containment helper wired into every single-claim and batch entry point plus the write side, load-time basename validation for artifact filenames, tests covering traversal / symlink / size limits, updated README, and SR-009 closed in the backlog.
</objective>

<execution_context>
@~/.claude/gsd-core/workflows/execute-plan.md
@~/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/STATE.md
@.planning/quick/260929-mqy-sr-009-harden-upload-path-symlink-bounda/260929-mqy-CONTEXT.md
@.gsd/steering-decisions-2026-09-29.md (SR-009, lines 33-37)
@.gsd/review_backlog.md (the SR-009 section around line 291 and the "## Steering status" table; the SR-007 / SR-010 / SR-011 sections show the resolved-steering + Resolution format to copy)
@src/api/routes_claims.py (whole file — 367 lines: `ArtifactRead` ~34-42, `_next_claim_id` ~45-57, `_allowed_image_suffix` ~60-77, `_write_claim_upload` ~80-102, `_artifact_read` ~105-129, `_claim_decision_from_results` ~132-162, `_claim_list_item` ~165-208, `create_claim` ~211-262, `list_claims` ~265-289, `get_claim` ~292-316, `analyze_claim` ~319-367)
@src/api/app.py (whole file — 58 lines; `create_app` and the lifespan that currently calls `load_config("config.yaml")`)
@src/api/deps.py (whole file — get_config / get_preprocessing / get_claims)
@src/compliance/config/settings.py (whole file — 632 lines: `StrictConfigModel` ~13-20, `PreprocessedArtifactNames` ~23-43, `PreprocessingConfig` ~46-62, `CoverageClassificationConfig` ~144-174 for the model_validator style, `EvaluationConfig` ~369-409, `AppConfig` ~451-490, the ValueError subclasses ~493-614, `load_config` ~617-632)
@config.yaml (whole file — `preprocessing.artifacts` ~18-26; `evaluation` ~329-338; there is no `api:` section yet)
@src/compliance/preprocessing/claim_batch.py (`UnsafeClaimDirectoryError` ~42-50, `_validate_claim_dir_name` ~53-70, `_path_safety_denial` ~73-82, `_is_claim_folder` ~85-97, `_discover_claim_folders` ~100-111, `discover_claim_folder_names` ~114-125, `_claim_sort_key` ~128-134)
@src/compliance/workflows/pipeline.py (`__all__` re-export ~35-39, `process_claim` ~206-245, `run` ~247-284, `_write_mirrored_artifacts` ~341-357, `_predicted_answer_path` ~359-410)
@src/compliance/workflows/claim_pipeline.py (`results_root` / `preprocessed_root` ~320-328, `analyze_claim` ~361-391, `run` ~393-443, `_batch_analysis_outcomes` ~456-483)
@src/compliance/workflows/artifact_publication.py (whole file — 366 lines: `claim_analysis_lock` ~84-119, `publish_claim_generation` ~134-184, `generation_mismatch` ~225-251, `_fsynced_directory` ~338-347)
@src/compliance/workflows/orchestration.py (whole file — 64 lines; `process_then_analyze`, `analyze_claim_exclusively`)
@src/main.py (whole file — 126 lines; `_workflow_exit_code` ~83-96, `_single_claim_exit_code` ~99-122)
@src/compliance/branch_log.py (`log_branch_decision` ~35-60 — the key=value branch logging convention)
@src/evaluation/evaluator.py (~185-300 — `_validate_claim_dir_name` in `evaluate_claim`, the discovery helpers that call `discover_claim_folder_names` on data_dir and results_dir)
@tests/conftest.py (whole file — `build_minimal_app_config` / `minimal_app_config_factory`, `cancellation_analysis_config`, `cancellation_chat_factory`, `mock_description_reader_factory`, `mock_document_reader_factory`)
@tests/test_api/conftest.py (whole file — `api_config_factory`, `compact_analysis_config`, `cancellation_chat_fn`)
@tests/test_api/test_claims_post.py (whole file — 158 lines; `_multipart_files` ~17-29 and the five intake tests, including the no-files-written assertion style)
@tests/test_api/test_claims_analysis.py (whole file — 187 lines; `_seed_raw_claim`, the 404 / 422 / 409 cases and the threaded concurrency proof)
@tests/test_api/test_deps_lifespan.py (whole file — 91 lines; both tests pass an explicit config, so resolving config in `create_app` is safe)
@tests/test_preprocessing/test_claim_batch.py (the discovery test at ~22-30 and the file's fixture style)
@tests/test_config/test_settings.py (the `load_config("config.yaml")` assertions ~124-210 — the pattern for a new `api.upload` test)
@tests/test_workflows/test_artifact_publication.py (the publication tests, including the unsafe-claim-id case)
@README.md (the API server section ~171-193 — endpoint table plus the SR-007 semantics paragraph)

Facts verified at planning time (files re-read fresh):
- `_write_claim_upload` writes each part with a single whole-file read into memory. There is no size check anywhere in `src/api/`, and no `api` section in `config.yaml` or in `AppConfig`.
- FastAPI reads and parses the multipart body in the route handler wrapper *before* solving dependencies, so a size check expressed as a handler statement or as a `Depends` cannot run before the parts are buffered. Only ASGI middleware sees the request ahead of the parser — this is why P-03 needs two layers.
- Starlette copies the lifespan state into each request scope, but the middleware is constructed once at app build time, so passing the cap into the middleware constructor is simpler and has no scope-dict coupling. `create_app` already accepts an optional `config`; resolving it once in the function body (instead of inside `lifespan`) serves both the middleware and the lifespan. `make serve` runs `uvicorn api.app:create_app --factory`, so the factory is still called at server start.
- Both tests in `tests/test_api/test_deps_lifespan.py` pass an explicit config; nothing asserts that `config.yaml` is loaded lazily inside the lifespan.
- `AppConfig` and every nested model inherit `StrictConfigModel` (`extra="forbid"`, SR-011 D-02), so the new `api:` block in `config.yaml` requires the matching model in the same change or config load fails.
- `PreprocessedArtifactNames` carries eight filenames and `EvaluationConfig` five more; all thirteen are joined directly to `preprocessed_dir` / `results_dir` at read and write sites. None is validated today.
- `_validate_claim_dir_name` rejects path separators and `.` / `..` and logs a `path_safety` branch decision on both the PASS and DENY paths. It is called from `routes_claims` (3 sites), `main`, `artifact_publication` (2 local imports), `claim_pipeline` (3 sites), `pipeline`, `evaluator` and `analysis_stats`. It says nothing about symlinks.
- `UnsafeClaimDirectoryError` is a `ValueError`; `routes_claims` and `main` catch bare `ValueError` around it, and the batch loops catch `Exception`, so a sibling `ValueError` subclass needs no new handling at those sites.
- `_is_claim_folder` decides single-claim vs batch-root. `_discover_claim_folders` raises `FileNotFoundError` for a missing root; `discover_claim_folder_names` returns `[]`. Both filter on a case-insensitive `claim` name prefix, which is also what keeps `.staging`, `.runs` and `.locks` invisible to discovery.
- `publish_claim_generation` validates `claim_id` then does `claim_dir.mkdir(parents=True, exist_ok=True)` and `os.replace` into it — a symlinked `results_dir/{claim_id}` would redirect every promoted artifact today.
- `ruff` config: target py310 (so `Path.is_relative_to` and `os.replace` are available and already used), line-length 120, `C901 max-complexity 10`, TRY rules on, `S` (bandit) on, `tests/*` ignores S101, `src/api/routes_claims.py` ignores B008.
- Baselines recaptured at planning time: `uv run python -m pytest -q --cov` → **414 passed, 3 deselected, 4.1s, total coverage 91.34%** against `fail_under = 90`. `uv run ruff check --no-fix src tests` clean. `uv run ruff format --check src tests` → **3 files would be reformatted**, all pre-existing and none touched by this plan (`src/compliance/preprocessing/extractor.py`, `src/compliance/preprocessing/preprocessing.py`, `src/compliance/tools/benford.py`) — so the format gates below are scoped to the touched paths; do not reformat unrelated files to make a wider gate pass. `uv run mypy src` → 0 errors in 44 files. `uv run mypy tests/test_api` → 8 errors in 2 files (`conftest.py` no-any-return, `test_claims_e2e.py` import-not-found / no-any-unimported), all pre-existing.
- `data/results/`, `data/preprocessed/` and `.gsd/` are gitignored.
</context>

<boundary_contract>
The contract every task implements (D-01..D-03, P-01..P-10).

**Upload byte limits — `POST /claims`.**

| Situation | Status | Detail |
|-----------|--------|--------|
| declared `Content-Length` > `api.upload.max_request_bytes` | 413 | `request_too_large` (refused before the multipart parser runs) |
| any single part streams past `api.upload.max_file_bytes` | 413 | `file_too_large` |
| the three parts together stream past `max_request_bytes` | 413 | `request_too_large` |
| filename missing / extension not in `document_formats` | 422 | existing prose (unchanged) |
| within both caps | 201 | `ClaimCreated`, parts written byte-identical |

A 413 leaves `data_dir` exactly as it was: no claim folder, no partial file.

**Claim-root containment — every entry point.**

| Caller | Root passed | Rejection surfaces as |
|--------|-------------|-----------------------|
| `POST /claims/{claim_id}/analysis` | `data_dir` | 422 |
| CLI `--claim-id` | `data_dir` | exit 1 |
| `PreprocessingPipeline.process_claim` (input) | none (R020 external paths allowed) | raised `ValueError` |
| `PreprocessingPipeline.process_claim` (mirrored output dir) | the output root | raised `ValueError` |
| `ClaimPipeline.analyze_claim` | none (R020) | raised `ValueError` |
| `publish_claim_generation` | `results_root` | raised `ValueError` |
| `_discover_claim_folders` / `discover_claim_folder_names` | the discovery root | entry excluded + WARNING `path_safety` log |

Reasons: `symlinked_claim_root` (the claim directory is a symlink — D-02) and `outside_root` (its resolved path is not inside the resolved root).

**Configured artifact filenames.** Every filename on `PreprocessedArtifactNames` and every artifact filename on `EvaluationConfig` must be a single basename. A separator, an absolute path, an empty string, or `.` / `..` fails `load_config` with `UnsafeArtifactNameError` naming the field.
</boundary_contract>

<tasks>

<task type="tracer" tdd="true">
  <name>Task 1 (tracer): bounded intake — configured upload caps enforced from Content-Length through the streamed write</name>
  <files>src/compliance/config/settings.py, config.yaml, src/api/uploads.py, src/api/app.py, src/api/routes_claims.py, tests/test_api/test_uploads.py, tests/test_api/test_claims_post.py, tests/test_config/test_settings.py</files>
  <read_first>src/api/routes_claims.py (whole file), src/api/app.py (whole file), src/api/deps.py, src/compliance/config/settings.py (`StrictConfigModel`, `PreprocessedArtifactNames`, `EvaluationConfig`, `AppConfig`, the ValueError subclass block, `load_config`), config.yaml (`preprocessing` and `evaluation` sections), tests/test_api/test_claims_post.py (whole file), tests/test_api/conftest.py, tests/test_api/test_deps_lifespan.py, tests/conftest.py (`build_minimal_app_config`), tests/test_config/test_settings.py (the `load_config("config.yaml")` tests)</read_first>
  <behavior>
    - Tracer end-to-end: with the caps left at their configured values, the existing multipart intake still returns 201 and writes all three parts byte-identical; with a test config whose per-file cap is a few kilobytes, a part above that cap returns 413 `file_too_large` and `data_dir` contains no new claim folder and no partial file.
    - Three parts each under the per-file cap but together above the request cap return 413 `request_too_large`, and again nothing is left under `data_dir`.
    - A request whose declared `Content-Length` exceeds the request cap is refused before the handler runs: the response is 413 `request_too_large` and no claim folder exists.
    - A part exactly at the per-file cap is accepted and written byte-identical; a part one byte over is refused — the boundary is inclusive of the cap.
    - Unit level: the chunked writer returns the byte count it wrote, raises `UploadTooLargeError` with reason `file_too_large` when a single stream passes the per-file cap and with `request_too_large` when it passes the remaining request allowance, and in both cases the destination file it was writing does not exist afterwards.
    - `load_config("config.yaml")` exposes `api.upload.max_file_bytes == 26214400` and `api.upload.max_request_bytes == 52428800`; an `AppConfig` built without an `api` section gets the same defaults; a config whose request cap is below its per-file cap fails to load with an error naming both values.
  </behavior>
  <action>
Step 0, before editing: re-read the files above fresh and recapture the baselines for the SUMMARY — `uv run python -m pytest -q --cov` (pass count + total coverage), `uv run ruff check --no-fix src tests`, `uv run ruff format --check` on the touched paths, `uv run mypy src`, `uv run mypy tests/test_api`. Planning-time values are in the context block. Write the failing tests first (RED), then implement.

`src/compliance/config/settings.py` (P-01, P-02) — add beside the other config models, keeping the file's ordering convention (models first, error classes in the trailing block):
- `class UploadLimitsConfig(StrictConfigModel)` with `max_file_bytes: int = Field(default=26_214_400, gt=0)` and `max_request_bytes: int = Field(default=52_428_800, gt=0)`, with `:param:` lines stating that these bound one multipart part and one whole request respectively. Add a `model_validator(mode="after")` named for what it produces (follow `_validated_branch_map` / `_validated_metric_vocabulary`) that raises a new `UploadLimitOrderError(ValueError)` when the request cap is below the per-file cap — carry both numbers in the message and build it inside `__init__` (TRY003 convention used by every error class in this module).
- `class ApiConfig(StrictConfigModel)` with `upload: UploadLimitsConfig = Field(default_factory=UploadLimitsConfig)`, and `api: ApiConfig = Field(default_factory=ApiConfig)` on `AppConfig` with its `:param:` line. Defaulting matters: no fixture, no test config and no other config file needs a new key.

`config.yaml` — add a top-level `api:` section with an `upload:` block carrying both byte values. One comment above them stating the figures they encode and the decision they implement; no other config change.

`src/api/uploads.py` (new) — the intake byte-limit boundary, module docstring saying so:
- `class UploadTooLargeError(ValueError)` storing `reason` (`file_too_large` / `request_too_large`) and the field name, building its message in `__init__`.
- `write_upload_stream(upload, dest, *, max_file_bytes, remaining_bytes) -> int` — copy `upload.file` to `dest` in 64 KiB blocks, accumulating the byte count; raise `UploadTooLargeError` as soon as the running count passes `max_file_bytes` or `remaining_bytes`, and unlink the partial destination before the error leaves the function. Return the number of bytes written. One comment carrying the non-obvious WHY: the count is checked per block rather than from a declared size because a client controls both the declared size and the stream.
- `class UploadSizeLimitMiddleware` — a pure ASGI middleware taking the inner app and `max_request_bytes` at construction. For an HTTP scope, read the `content-length` header; when it parses to a value above the cap, send a 413 JSON body `{"detail": "request_too_large"}` and return without delegating; otherwise await the inner app. A comment states WHY it exists as middleware rather than a handler check: FastAPI parses the multipart body before handler code runs, so a handler-level check cannot prevent the buffering this cap exists to prevent.

`src/api/app.py` — resolve the configuration once in `create_app` (the middleware needs the cap at build time) and have the lifespan use that resolved object instead of loading again; register `UploadSizeLimitMiddleware` with `resolved.api.upload.max_request_bytes`. Update the `create_app` docstring to say the config is resolved when the app is built. Change nothing else about the lifespan contract — the same `AppState` keys, the same shared pipeline instances.

`src/api/routes_claims.py` — route the three parts through the writer:
- `_write_claim_upload` keeps its keyword-only shape but takes the two caps, writes each part through `write_upload_stream`, and carries the running request total across the three calls by subtracting what each write consumed from the remaining allowance. It stays a small orchestrator over the writer; do not re-implement counting in the route module.
- `create_claim` passes `config.api.upload` values in, wraps the write in a `try`, and on `UploadTooLargeError` removes the claim directory and raises `HTTPException(413, detail=exc.reason)` with `from exc`. One comment states WHY removing the directory is safe: it was created moments earlier with `mkdir(parents=False)`, which fails when the path already exists, so this request provably owns it. Update the docstring to name the 413 outcome. Leave `_allowed_image_suffix`, the basename coercion and the existing 422/409 behaviour untouched.

`tests/test_api/test_uploads.py` (new) — unit coverage for the writer, constructing `UploadFile` objects over `BytesIO` directly (no HTTP): the byte count it returns, the per-file breach, the request-remaining breach, the absent partial file after each breach, and a stream exactly at the cap succeeding.

`tests/test_api/test_claims_post.py` — extend with the HTTP cases from the behaviour list, building configs through `api_config_factory` and overriding the caps on the returned config object (or adding an optional cap argument to the factory in `tests/test_api/conftest.py` if that reads cleaner). Each rejection test asserts the status, the detail code, and that the set of entries under `data_dir` is unchanged from before the request. Keep the existing five tests passing unmodified in intent.

`tests/test_config/test_settings.py` — assert the two values from `load_config("config.yaml")`, the defaults on a config built without an `api` section, and the cap-ordering failure.

Commit: stage only the eight paths explicitly (never `git add -A` / `git add .`, never bypass hooks). First run `git status --short` and `git diff --stat -- <the paths>`; if a path shows hunks this task did not write (concurrent session), stop and report instead of committing. Message `feat(SR-009): bound multipart intake with configured per-file and per-request byte caps`, ending with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && uv run python -m pytest -q tests/test_api tests/test_config && uv run python -m pytest -q tests/test_api/test_uploads.py tests/test_api/test_claims_post.py -k "large or cap or limit or stream" && uv run python -m pytest -q --cov && uv run ruff check --no-fix src/api src/compliance/config tests/test_api tests/test_config && uv run ruff format --check src/api src/compliance/config tests/test_api tests/test_config && uv run mypy src && grep -q "class UploadLimitsConfig" src/compliance/config/settings.py && grep -q "class ApiConfig" src/compliance/config/settings.py && grep -q "max_request_bytes" config.yaml && grep -q "26214400" config.yaml && grep -q "class UploadSizeLimitMiddleware" src/api/uploads.py && grep -q "def write_upload_stream" src/api/uploads.py && grep -q "class UploadTooLargeError" src/api/uploads.py && grep -q "UploadSizeLimitMiddleware" src/api/app.py && grep -q "write_upload_stream" src/api/routes_claims.py && grep -q "413" src/api/routes_claims.py</automated>
  </verify>
  <done>Intake is bounded by configuration. `api.upload.max_file_bytes` (25 MiB) and `max_request_bytes` (50 MiB) live in config.yaml on a defaulted `AppConfig.api`, and a request cap below the file cap fails at load. A declared Content-Length over the request cap is refused with 413 `request_too_large` before the multipart parser runs; a part over the per-file cap and three parts over the request total are refused with 413 during the streamed write; every rejection leaves `data_dir` with no new folder and no partial file. A conforming upload still returns 201 with byte-identical parts, written in 64 KiB blocks rather than one whole-file read. Fast lane passes with coverage at or above the 90 floor; ruff, format and mypy are clean on the touched paths. The commit contains exactly the 8 files.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: one claim-root containment rule — symlinked roots hard-rejected, configured filenames forced to basenames</name>
  <files>src/compliance/preprocessing/claim_batch.py, src/compliance/config/settings.py, src/compliance/workflows/pipeline.py, src/compliance/workflows/claim_pipeline.py, src/compliance/workflows/artifact_publication.py, src/api/routes_claims.py, src/main.py, tests/test_preprocessing/test_claim_batch.py, tests/test_api/test_claims_paths.py, tests/test_config/test_settings.py, tests/test_workflows/test_artifact_publication.py</files>
  <read_first>src/compliance/preprocessing/claim_batch.py (~40-135), src/compliance/config/settings.py as left by Task 1 (`PreprocessedArtifactNames`, `EvaluationConfig`, the error-class block), src/compliance/workflows/pipeline.py (~200-290 and `_write_mirrored_artifacts`), src/compliance/workflows/claim_pipeline.py (~360-395 and `_batch_analysis_outcomes`), src/compliance/workflows/artifact_publication.py (~84-185), src/api/routes_claims.py as left by Task 1 (`create_claim`, `analyze_claim`), src/main.py (whole file), src/compliance/branch_log.py, src/evaluation/evaluator.py (~260-300), tests/test_preprocessing/test_claim_batch.py (whole file), tests/test_api/test_claims_analysis.py (the `_seed_raw_claim` helper and the 422 case), tests/test_workflows/test_artifact_publication.py (the unsafe-claim-id test), tests/test_workflows/test_pipeline.py (`test_cli_or_api_passes_path_from_outside`)</read_first>
  <behavior>
    - A claim directory that is a symlink is refused wherever it is named: `PreprocessingPipeline.process_claim` and `ClaimPipeline.analyze_claim` raise, `POST /claims/{claim_id}/analysis` returns 422, and CLI `--claim-id` exits 1 — and in every case the symlink target is neither read nor written (D-02).
    - A raw claim folder that is a real directory keeps working unchanged, including a caller-supplied claim folder that lives outside `data_dir` (the shipped R020 external-path capability must not regress).
    - Batch discovery under a root excludes a symlinked claim entry and an entry whose resolved path escapes the resolved root, logs one WARNING `path_safety` branch decision per excluded entry naming the reason, and processes every remaining claim (D-03).
    - `discover_claim_folder_names` applies the same exclusion, so evaluation and analysis-stats discovery cannot follow a symlinked claim directory either.
    - `publish_claim_generation` refuses to publish into a symlinked `results_root/{claim_id}`, and the mirrored preprocessing write refuses a symlinked output claim directory — neither leaves an artifact at the symlink target.
    - `load_config` rejects an artifact filename that is not a single basename — a separator, an absolute path, an empty string, and `..` each fail with an error naming the offending config field — for both the preprocessing artifact names and the evaluation artifact names; the shipped `config.yaml` still loads.
  </behavior>
  <action>
Re-read the files as left by Task 1 before editing. Write the failing tests first (RED), then implement.

`src/compliance/preprocessing/claim_batch.py` — the single containment rule (P-07, P-08):
- `class ClaimRootContainmentError(ValueError)` beside `UnsafeClaimDirectoryError`, storing the path and the reason and building its message in `__init__`.
- `_validate_claim_root(claim_dir: Path, *, root: Path | None = None) -> None` with a `:param:` docstring per parameter and a `:raises:` line. It calls the existing name validator first, then rejects a claim directory for which `Path.is_symlink()` is true with reason `symlinked_claim_root`, then — only when a root is given — resolves both paths and rejects with reason `outside_root` when the resolved claim directory is not relative to the resolved root. Reuse the existing `_path_safety_denial` logging shape (branch `path_safety`, outcome `DENY`, WARNING, `claim=` the name) by extending that helper to carry the new reasons rather than writing a second logging block.
- Its docstring states WHY rejection rather than resolution: a symlinked claim root is refused outright (D-02), because resolving and re-containing would still let an operator's tree decide which bytes a claim run reads.
- `_discover_claim_folders` and `discover_claim_folder_names` filter their candidate list through `_validate_claim_root(path, root=<the discovery root>)`, excluding a candidate that raises and letting the existing `_path_safety_denial` WARNING be the trace (P-10). Extract the shared filtering into one private helper named for what it produces so the two discoveries cannot drift. Leave `_is_claim_folder` untouched (P-09) and leave the `claim` name-prefix filter and `_claim_sort_key` ordering exactly as they are.

`src/compliance/config/settings.py` (P-06): add a module-level checker that validates one configured filename as a single basename and raises a new `UnsafeArtifactNameError(ValueError)` carrying the dotted field path and the offending value. Reject a value containing `os.sep` or `os.altsep`, an absolute path, an empty or whitespace-only string, `.`, `..`, or any value whose `Path(...).name` differs from itself. Call it from a `model_validator(mode="after")` on `PreprocessedArtifactNames` over all eight filenames and on `EvaluationConfig` over its five artifact filenames, naming each field in the error. Keep the validators small: iterate the model's own fields rather than listing names twice.

Wire the containment rule at every entry point (the table in `<boundary_contract>` is the contract):
- `src/compliance/workflows/pipeline.py`: in `process_claim`, replace the bare name validation with `_validate_claim_root(claim_dir)` (no root — R020 external claim folders stay supported, P-08), and validate the mirrored destination `root / claim_dir.name` against `root` before `mkdir`. Keep the `__all__` re-export list in sync if the new helper belongs in it.
- `src/compliance/workflows/claim_pipeline.py`: in `analyze_claim`, replace the bare name validation with `_validate_claim_root(claim_dir)` (no root). Leave `_load_artifacts_node` and `_batch_analysis_outcomes` as they are — discovery already filtered, and the per-claim soft-fail loop already records a failure.
- `src/compliance/workflows/artifact_publication.py`: in `publish_claim_generation`, extend the existing local-import boundary validation to `_validate_claim_root(results_root / claim_id, root=results_root)` before the `mkdir`. Leave `claim_analysis_lock` validating the name only — a lock file is not a claim root.
- `src/api/routes_claims.py`: in the analysis POST, validate the joined `data_dir / claim_id` against `data_dir` inside the existing `try` that maps `ValueError` to 422, before the raw-folder existence check. In `create_claim`, validate the new claim directory against `data_dir` before writing into it.
- `src/main.py`: `_single_claim_exit_code` validates the joined claim directory against `data_dir` in its existing `ValueError` branch, so an unsafe or symlinked root exits 1 with the existing logging shape. Update its docstring and the `--claim-id` help text to say the claim root must be a real directory inside `data_dir`.

Tests:
- `tests/test_preprocessing/test_claim_batch.py`: `_validate_claim_root` raises for a symlinked claim directory and for one whose resolved path escapes the given root, and passes for a real directory inside the root and for a real directory outside the root when no root is given. Both discoveries exclude a symlinked entry while still returning every real claim, with the excluded name absent from the result. Build the symlink with `Path.symlink_to` against a target outside `tmp_path`'s claim root and assert the target is untouched.
- `tests/test_api/test_claims_paths.py` (new): with a raw tree seeded as `tests/test_api/test_claims_analysis.py` does, a symlinked claim directory under `data_dir` returns 422 from `POST /claims/{claim_id}/analysis`, the injected chat seam is never called, and nothing is written at the symlink target; the percent-encoded traversal id still returns 422 on both claim endpoints.
- `tests/test_workflows/test_artifact_publication.py`: publishing into a symlinked `results_root/{claim_id}` raises and writes nothing at the target.
- `tests/test_config/test_settings.py`: the four rejected filename shapes on a preprocessing artifact field and one on an evaluation artifact field, each asserting the error names the field; plus `load_config("config.yaml")` still succeeding.

Commit (stage only the eleven paths explicitly, with the same concurrent-change check as Task 1): `feat(SR-009): reject symlinked claim roots and force configured artifact names to basenames`, ending with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && uv run python -m pytest -q tests/test_preprocessing/test_claim_batch.py tests/test_api tests/test_config tests/test_workflows && uv run python -m pytest -q tests/test_preprocessing/test_claim_batch.py tests/test_api/test_claims_paths.py -k "symlink or contain or root or traversal" && uv run python -m pytest -q --cov && uv run ruff check --no-fix src tests && uv run ruff format --check src/api src/compliance/config src/compliance/preprocessing/claim_batch.py src/compliance/workflows src/main.py tests/test_api tests/test_config tests/test_preprocessing/test_claim_batch.py tests/test_workflows && uv run mypy src && grep -q "def _validate_claim_root" src/compliance/preprocessing/claim_batch.py && grep -q "class ClaimRootContainmentError" src/compliance/preprocessing/claim_batch.py && grep -q "symlinked_claim_root" src/compliance/preprocessing/claim_batch.py && grep -q "outside_root" src/compliance/preprocessing/claim_batch.py && grep -q "class UnsafeArtifactNameError" src/compliance/config/settings.py && grep -q "_validate_claim_root" src/compliance/workflows/pipeline.py && grep -q "_validate_claim_root" src/compliance/workflows/claim_pipeline.py && grep -q "_validate_claim_root" src/compliance/workflows/artifact_publication.py && grep -q "_validate_claim_root" src/api/routes_claims.py && grep -q "_validate_claim_root" src/main.py</automated>
  </verify>
  <done>There is one definition of a safe claim root and every entry point uses it. A symlinked claim directory is hard-rejected by the preprocessing and analysis single-claim paths, by the analysis POST (422), by the CLI (exit 1), and by publication into results_dir — with the symlink target never read or written. Batch discovery and the shared name discovery exclude symlinked and escaping entries with a WARNING `path_safety` trace while processing every real claim, and the R020 caller-supplied external claim folder still works. Every configured artifact filename must be a single basename or `load_config` fails naming the field. Fast lane passes with coverage at or above the 90 floor; ruff, format and mypy are clean on the touched paths. The commit contains exactly the 11 files.</done>
</task>

<task type="auto">
  <name>Task 3: document the intake and path boundaries and close SR-009</name>
  <files>README.md, .gsd/review_backlog.md</files>
  <read_first>src/api/uploads.py, src/api/routes_claims.py, src/compliance/config/settings.py and src/compliance/preprocessing/claim_batch.py as left by Tasks 1-2, config.yaml (the new `api` section), README.md (the API server section ~171-193 and the config/data sections ~95-110), .gsd/review_backlog.md (the SR-009 section around line 291, the SR-007 / SR-010 / SR-011 resolved-steering and Resolution format, and the "## Steering status" table)</read_first>
  <behavior>
    - A reader of README.md learns the two upload caps, where they are configured, and what an operator sees when a request exceeds them — enough to raise the limit without reading the source.
    - The path rules are stated plainly: a symlinked claim root is rejected rather than followed, batch discovery skips and logs such entries, and configured artifact filenames must be basenames.
    - No invented numbers, endpoints or config keys: only the surface the code now exposes, with the key names matching `config.yaml` exactly.
  </behavior>
  <action>
Re-read the modules as left by Tasks 1-2 so the documented keys, status codes and reason codes match the code exactly.

README.md — change only what is now incomplete; no restructuring and no new top-level sections:
- In the API server section, after the existing endpoint semantics paragraph, add a short paragraph on intake limits: the per-file and per-request caps with their `config.yaml` keys and their MiB values (D-01), that an over-declared request is refused before the body is parsed, that a breach returns `413` with `file_too_large` or `request_too_large`, and that a rejected upload leaves no claim folder behind.
- Add a second short paragraph on path boundaries: claim ids are single path segments, a claim directory that is a symlink is rejected rather than followed (D-02), batch discovery skips such entries with a warning rather than processing them (D-03), and configured artifact filenames must be plain basenames or config load fails.
- If the config or data-layout section lists `config.yaml` sections, add `api` there so the new section is discoverable.

Gates, compared against the Task 1 baselines: `uv run python -m pytest -q --cov` (fast lane) passes with coverage at or above the 90 floor; `uv run ruff check --no-fix src tests` clean; `uv run mypy src` reports 0 errors; `uv run mypy tests/test_api` no worse than the recaptured baseline. Fix any new failure before committing.

Backlog (`.gsd/review_backlog.md` is gitignored: edit, never stage):
- Change the SR-009 header to `### [x] SR-009: Harden upload / path / symlink boundaries ⚠️`.
- Replace its "**Steering needed**" questions with a "**Steering (resolved 2026-09-29)**" block in the SR-007 / SR-011 style listing D-01, D-02 and D-03, plus P-01..P-10 as "planner discretion, flagged".
- Add a one-paragraph "**Resolution:**" naming the `api.upload` config section with both caps, the Content-Length middleware plus the chunked writer and why both layers exist, the 413 reason codes and the no-partial-folder guarantee, `_validate_claim_root` with its symlink hard-reject and optional root containment, the entry points wired to it including the write side, the discovery skip-and-log behaviour, the load-time artifact basename validation, and the quick id 260929-mqy.
- Update the Steering status row to `| SR-009 | Steered 2026-09-29: 25MB/file 50MB total; hard-reject symlink roots; CLI same containment — done (quick 260929-mqy) |`. Touch no other SR entry.

SUMMARY content (written by the executor workflow) must include: recaptured baselines vs final gate numbers; the boundary contract as implemented with every status code and reason code; P-01..P-10; the behaviour-change register from the objective (the new 413s, the `api:` section under `extra="forbid"`, config resolution moving into `create_app`, symlinked claims excluded from batch and evaluation discovery); and the follow-ups — the caps bound one request but there is no global concurrent-request budget, and SR-013 still owns the policy-engine extract.

Commit (stage only `README.md` explicitly, with the same concurrent-change check as Task 1): `feat(SR-009): document upload byte caps and claim-root containment`, ending with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && uv run python -m pytest -q --cov && uv run ruff check --no-fix src tests && uv run mypy src && grep -q "max_file_bytes" README.md && grep -q "request_too_large" README.md && grep -qi "symlink" README.md && grep -q "### \[x\] SR-009" .gsd/review_backlog.md && grep -q "| SR-009 | Steered 2026-09-29" .gsd/review_backlog.md && STAGED="$(git diff --cached --name-only)" && test "$(printf '%s' "$STAGED" | grep -c review_backlog)" = 0</automated>
  </verify>
  <done>README.md documents both new boundaries accurately: the two upload caps with their config keys and MiB values, the pre-parse refusal, the 413 reason codes and the no-partial-folder guarantee; and the path rules — single-segment claim ids, symlinked claim roots rejected rather than followed, batch discovery skipping and logging them, configured artifact filenames forced to basenames. All gates meet or beat the Task 1 baselines. SR-009 is checked off with steering and a resolution recorded in the backlog, and the backlog is not staged. The commit contains exactly the 1 tracked file.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| HTTP client → multipart request body | Untrusted bytes of unbounded size cross into process memory, spool space and `data_dir` |
| HTTP client → uploaded filename | An untrusted string becomes a filename under a claim directory |
| Filesystem tree → claim discovery | Directory entries under the configured roots decide which bytes a run reads and where it writes |
| config.yaml → path joins | Configured artifact filenames and roots are joined to build every read and write path |
| Pipeline writes → configured output roots | Published artifacts must land inside `results_dir` / `preprocessed_dir` and nowhere else |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-SR009-01 | Denial of Service | `POST /claims` request body | high | mitigate | `UploadSizeLimitMiddleware` refuses a declared `Content-Length` above `api.upload.max_request_bytes` before FastAPI's multipart parser buffers or spools any part, returning 413 `request_too_large` (D-01, P-03). Proven by the over-declared-length test asserting no claim folder is created. |
| T-SR009-02 | Denial of Service | multipart part → memory | high | mitigate | Parts are copied in 64 KiB blocks by `write_upload_stream` with a running count, replacing the whole-file reads, so peak memory no longer scales with upload size; a part past `max_file_bytes` and a request past `max_request_bytes` are refused mid-stream with 413 (D-01, P-05). |
| T-SR009-03 | Denial of Service | `data_dir` free space | high | mitigate | The same running count bounds bytes written to disk per request, and a breach unlinks the partial file and removes the claim directory this request created, so repeated oversized uploads cannot accumulate residue (P-05). |
| T-SR009-04 | Tampering | symlinked claim root under `data_dir` | high | mitigate | `_validate_claim_root` hard-rejects a claim directory that is a symlink at every single-claim entry point — API analysis POST (422), CLI (exit 1), `process_claim`, `analyze_claim` — so a symlink planted in the raw tree cannot make a run read or write at its target (D-02). Proven by the API symlink test asserting the target is untouched. |
| T-SR009-05 | Tampering | batch discovery under a configured root | high | mitigate | Both discoveries filter candidates through `_validate_claim_root` with the discovery root, excluding symlinked entries and entries whose resolved path escapes the resolved root (D-03, P-10). Exclusions are logged `path_safety / DENY` so a refused claim is traceable rather than silently missing. |
| T-SR009-06 | Tampering | configured artifact filenames | high | mitigate | Every filename on `PreprocessedArtifactNames` and `EvaluationConfig` is validated as a single basename at config load, raising `UnsafeArtifactNameError` naming the field, so `../../x.json` in config.yaml can never reach a path join (P-06). |
| T-SR009-07 | Tampering | symlinked output claim directory | high | mitigate | `publish_claim_generation` validates `results_root/{claim_id}` against `results_root`, and the mirrored preprocessing write validates its output claim directory against the output root, before any `mkdir` or `os.replace` — so a symlinked destination cannot redirect published artifacts (P-08). |
| T-SR009-08 | Elevation of Privilege | uploaded filename → path join | medium | accept | Already mitigated before this task: `create_claim` coerces the filename to `Path(...).name`, rejects `.` / `..`, checks the suffix against `document_formats`, and asserts the resolved image path stays under the claim root. This plan adds the size bound on the same path and changes none of that logic; the existing traversal test stays green. |
| T-SR009-09 | Information Disclosure | rejection responses and path-safety logs | medium | mitigate | Rejections carry fixed snake_case reason codes (`file_too_large`, `request_too_large`, `symlinked_claim_root`, `outside_root`) and the path-safety branch logs carry the claim name and reason only — no symlink target, no absolute path outside the configured roots, no upload content (CLAUDE.md security rule). |
| T-SR009-10 | Denial of Service | many concurrent in-cap uploads | medium | accept | The caps bound a single request, not a global concurrency budget; a fleet-level limit belongs to the deployment (reverse proxy / worker limits), not to this application boundary. Recorded as a follow-up in the SUMMARY rather than silently omitted. |

No package installs in this plan — the middleware and the chunked writer use FastAPI/Starlette and stdlib only, so there is no supply-chain row.
</threat_model>

<verification>
- `uv run python -m pytest -q --cov` (fast lane, integration deselected) passes with total coverage at or above the `fail_under = 90` floor; the 414-test planning baseline plus the new SR-009 tests all pass.
- `uv run ruff check --no-fix src tests` is clean; `uv run ruff format --check` is clean on every touched path (the three pre-existing unformatted files are untouched); `uv run mypy src` reports 0 errors; `tests/test_api` is no worse than its 8-error mypy baseline.
- `POST /claims` returns 413 `request_too_large` for an over-declared `Content-Length`, 413 `file_too_large` for a part over the per-file cap, and 413 `request_too_large` for three parts over the request cap — each leaving `data_dir` with no new folder and no partial file; a conforming upload still returns 201 with byte-identical parts.
- `load_config("config.yaml")` exposes `api.upload.max_file_bytes == 26214400` and `api.upload.max_request_bytes == 52428800`; a request cap below the file cap fails at load; an artifact filename that is not a basename fails at load with the field named.
- A symlinked claim directory is rejected by `process_claim`, `analyze_claim`, `POST /claims/{claim_id}/analysis` (422), CLI `--claim-id` (exit 1) and `publish_claim_generation`, with nothing written at the symlink target.
- `_discover_claim_folders` and `discover_claim_folder_names` exclude symlinked and escaping entries, log one WARNING `path_safety` decision each, and still return every real claim; `test_cli_or_api_passes_path_from_outside` still passes.
- `git log --stat -3` shows 3 SR-009 commits, each containing only its task's tracked files; `.gsd/review_backlog.md` is never staged.
</verification>

<success_criteria>
- Oversized upload rejected (backlog "Done when"): per-file and per-request byte caps from config, enforced before the parser and again during the streamed write, at 25 MiB and 50 MiB (D-01).
- Path traversal via config or symlink cannot escape the data roots (backlog "Done when"): configured artifact filenames must be basenames, and a symlinked claim root is hard-rejected at every read and write entry point (D-02).
- Tests cover traversal, symlink, and size-limit cases (backlog "Done when"), including the CLI/batch discovery path (D-03).
- Uploads are streamed in bounded chunks rather than read whole into memory, and a rejected upload leaves no partial claim folder.
- SR-009 is marked `[x]` with steering and a resolution recorded in `.gsd/review_backlog.md`, and the backlog is never staged.
- Nothing in this change touches the policy engine — SR-013 keeps that scope — and the shipped R020 external-claim-folder capability still works.
</success_criteria>

<output>
Create `.planning/quick/260929-mqy-sr-009-harden-upload-path-symlink-bounda/260929-mqy-SUMMARY.md` when done
</output>
