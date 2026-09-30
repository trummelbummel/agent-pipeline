---
phase: 260928-o5k-fix-ruff-lint-errors-s101-try003-try401-
plan: 01
status: complete
subsystem: preprocessing, llm, config, workflows, evaluation
tags: [ruff, lint, exception-classes, typing, refactor]
dependency-graph:
  requires: []
  provides:
    - "SignatureDetectionError subclass hierarchy (SignatureDependencyError, SignatureWeightsDownloadError, SignatureInferenceError, SignatureModelNotConfiguredError)"
    - "UnsupportedCheckerModeError(ValueError) in checker.py"
    - "ConfigFileNotFoundError(FileNotFoundError) in settings.py"
    - "UnsafeClaimDirectoryError(ValueError) in claim_batch.py"
    - "_present_path typed path-narrowing helper in claim_batch.py"
    - "_STATE_BOOLEAN_KEYS + _state_boolean_flags helper in claim_pipeline.py"
  affects:
    - "src/api/routes_claims.py (imports SignatureDetectionError family and catches ValueError; behavior unchanged since new classes subclass the originals)"
tech-stack:
  added: []
  patterns:
    - "Exception classes own their message templates (typed __init__ building the message, no msg-variable-then-raise)"
    - "typing.cast for internal-guarantee return narrowing instead of assert (CLAUDE.md: no defensive checks on internal paths)"
key-files:
  created: []
  modified:
    - src/compliance/preprocessing/signature_detect.py
    - src/compliance/preprocessing/document.py
    - src/compliance/llm/checker.py
    - src/compliance/config/settings.py
    - src/compliance/preprocessing/claim_batch.py
    - src/compliance/workflows/pipeline.py
    - tests/test_workflows/test_pipeline.py
    - tests/test_workflows/test_claim_pipeline.py
    - src/compliance/workflows/claim_pipeline.py
    - src/compliance/workflows/claim_dates.py
    - src/evaluation/__main__.py
    - src/evaluation/evaluator.py
    - src/evaluation/visualization.py
decisions:
  - "Exception-class approach (message built inside typed __init__) chosen over the msg = ...; raise X(msg) variable pattern, per orchestrator direction; also removed real duplication (inference message duplicated in document.py and signature_detect.py; weights-ref + auth-hint composition at 5 raise sites consolidated into one SignatureWeightsDownloadError template)"
  - "typing.cast used for Reader.read return narrowing instead of making Reader generic; a generic Reader[ModelT] would ripple through reader.py, answer.py, markdown.py, description.py, and document.py's BaseModel-typed OCR-retry chain — out of scope for a lint-fix task"
  - "Consolidated the five HF-download failure messages (gated repo, missing token, HTTP 401/403, other HTTP error, OSError) into one SignatureWeightsDownloadError(weights_ref, reason, auth_hint=...) template; wording changed but all information (weights ref, cause, HF_TOKEN hint where applicable) is preserved"
metrics:
  duration: "~35min"
  completed: "2026-09-28"
actuals:
  tokens: 78000
  tasks: 3
  commits: 0
---

# Quick Task 260928-o5k: Fix ruff lint errors (S101, TRY003, TRY401, ...) Summary

Cleared all 38 ruff violations across 13 staged source/test files by moving exception messages into typed exception-class `__init__` methods, replacing internal `assert`s with a typed path helper and `typing.cast`, extracting a C901-triggering boolean-flag block into a small static helper, and applying direct-return / `logger.exception` / ASCII-docstring fixes — with zero commits, zero staging, and the git index/HEAD/stash left exactly as found.

## What Was Built

**Task 1 — Exception classes own their messages (signature detection, checker mode, config file):**
- `src/compliance/preprocessing/signature_detect.py`: renamed `_HF_TOKEN_HINT` → `_HF_AUTH_HINT` (S105 false-positive on help text); added `SignatureDependencyError`, `SignatureWeightsDownloadError`, `SignatureInferenceError`, `SignatureModelNotConfiguredError` — all subclassing `SignatureDetectionError(RuntimeError)`; `resolve_signature_weights` and `detect_signature_with_yolo` raise the new classes with `weights_ref` computed once.
- `src/compliance/preprocessing/document.py`: imports the two new exception classes; `_maybe_verify_signature` raises `SignatureModelNotConfiguredError()`; `_run_signature_detect` now takes `ocr_retry: OcrRetryConfig` as an explicit parameter (removes the `assert self.ocr_retry is not None`) and raises `SignatureInferenceError(image_path, exc)`.
- `src/compliance/llm/checker.py`: added `UnsupportedCheckerModeError(ValueError)`; `Checker.check` raises it instead of a bare `ValueError`.
- `src/compliance/config/settings.py`: added `ConfigFileNotFoundError(FileNotFoundError)`; `load_config` raises it; fixed the U+2212 minus sign in the `CheckingConfig` docstring.

**Task 2 — Batch preprocessing typed helpers, cast-based narrowing, else-return, exception-only logging:**
- `src/compliance/preprocessing/claim_batch.py`: added `UnsafeClaimDirectoryError(ValueError)`, used by `_path_safety_denial`; replaced `_is_present` (bool predicate) with `_present_path` (`Path | None`) used by `_read_ground_truth` and `_read_description`; replaced 4 `assert isinstance(...)` reader-narrowing checks with `typing.cast`; moved the success path of `_read_description` into an `else:` clause (TRY300); changed the batch-loop exception log to `logger.exception("Failed to process %s", claim_dir.name)` (TRY401).
- `src/compliance/workflows/pipeline.py`: same TRY401 fix in `_written_claim_outputs`.
- `tests/test_workflows/test_pipeline.py` / `tests/test_workflows/test_claim_pipeline.py`: `_UnsafeDir.__truediv__` / `_DotDot.__truediv__` fakes now `pytest.fail(...)` instead of `raise AssertionError(...)` (TRY003, and a stronger guard since a production `except Exception` can't swallow a pytest outcome); added module-level `_SimulatedClaimFailure(RuntimeError)` in `test_pipeline.py` used by the injected answer-read failure; fixed the EN DASH in a `test_claim_pipeline.py` docstring (RUF002).

**Task 3 — Analysis/evaluation simplifications, format pass, full gate:**
- `src/compliance/workflows/claim_pipeline.py`: added module-level `_STATE_BOOLEAN_KEYS` tuple (11 keys, exact payload order) and `ClaimPipeline._state_boolean_flags` static helper; `_analysis_result_payload` now does `payload.update(self._state_boolean_flags(state))` instead of 11 `if key in state:` blocks (C901, 13 > 10 → resolved); `_classifier_returned_false` is now a single `return any(...)` (SIM110); fixed the U+2212 minus sign in the `_checker_results` docstring (RUF002).
- `src/compliance/workflows/claim_dates.py`: `_suspicious_dating`'s trailing if/return True/return False collapsed into a direct boolean return (SIM103).
- `src/evaluation/__main__.py`: `except FileNotFoundError:` now logs with `logger.exception` instead of `logger.error` (TRY400); fixed the MULTIPLICATION SIGN in a docstring (RUF002).
- `src/evaluation/evaluator.py`, `src/evaluation/visualization.py`: fixed MULTIPLICATION SIGN / EN DASH in docstrings (RUF002).
- Ran `ruff format` over the full staged `.py` set (formatting-only; 23 of 40 staged files reformatted, matching the pre-existing "22 unformatted" baseline plus incidental changes from this task's edits).

## Before / After

| Check | Baseline (planning time) | After this task |
|---|---|---|
| Ruff gate on staged `.py` set | 38 violations | **0** (`All checks passed!`) |
| `ruff format --check` on staged `.py` set | 22 of 40 files would reformat | **0** (`40 files already formatted`) |
| mypy on the 11 touched src modules | 8 errors (pre-existing) | **8 errors** (identical set: `signature_detect.py` union-attr, `document.py` override, `claim_pipeline.py` x6) |
| pytest full run | 235 passed, 1 known failure | **235 passed, 1 known failure** (`test_analysis_coverage_other_label_is_false`, unchanged) |
| `git write-tree` | `33c65323400e6cdd40ad971c6d882e6ff64768f9` | **unchanged** (`33c65323400e6cdd40ad971c6d882e6ff64768f9`) |
| `git rev-parse HEAD` | `87e9c09d288ce2e62b08f83ef10e7824996ef578` | **unchanged** (`87e9c09d288ce2e62b08f83ef10e7824996ef578`) |
| `git stash list` count | 0 | **unchanged** (0) |
| `noqa` count in src/tests | 0 | **0** (no suppressions added) |
| `pyproject.toml` per-file-ignores | `"tests/*" = ["S101"]` only | **unchanged** |

## Files Changed

**13 lint-fix files (code changes, per plan `files_modified`):**
- `src/compliance/preprocessing/signature_detect.py`
- `src/compliance/preprocessing/document.py`
- `src/compliance/llm/checker.py`
- `src/compliance/config/settings.py`
- `src/compliance/preprocessing/claim_batch.py`
- `src/compliance/workflows/pipeline.py`
- `tests/test_workflows/test_pipeline.py`
- `tests/test_workflows/test_claim_pipeline.py`
- `src/compliance/workflows/claim_pipeline.py`
- `src/compliance/workflows/claim_dates.py`
- `src/evaluation/__main__.py`
- `src/evaluation/evaluator.py`
- `src/evaluation/visualization.py`

**Additional files touched by the `ruff format` pass only (no lint/behavior changes by this task — pre-existing unformatted state from the user's in-flight work):**
`src/api/routes_claims.py`, `src/compliance/llm/chat.py`, `src/compliance/llm/classifier.py`, `src/evaluation/analysis_stats.py`, `src/main.py`, `tests/conftest.py`, `tests/test_api/conftest.py`, `tests/test_api/test_claims_e2e.py`, `tests/test_api/test_claims_post.py`, `tests/test_config/test_settings.py`, `tests/test_evaluation/test_analysis_stats.py`, `tests/test_evaluation/test_cli.py`, `tests/test_evaluation/test_evaluator.py`, `tests/test_llm/test_classifier.py`, `tests/test_preprocessing/test_description.py`, `tests/test_preprocessing/test_document.py`, `tests/test_preprocessing/test_extractor.py`, `tests/test_preprocessing/test_markdown.py`, `tests/test_workflows/test_orchestration.py`, `tests/test_workflows/test_predicted_answer_io.py`.

**Nothing was committed or staged.** The user must `git add` these files (both the 13 lint-fix files and the formatting-only files) before re-running their commit — pre-commit lints the index, not the working tree.

## Deviations from Plan

None — plan executed exactly as written. All three tasks' `<action>` steps were followed literally; no Rule 1-4 auto-fixes or architectural questions arose during execution.

Rejected alternatives (as directed by the plan, documented for the record):
1. The `msg = ...; raise X(msg)` variable pattern would have satisfied TRY003 mechanically but was rejected in favor of exception classes owning their messages, which also removed real duplication (the YOLO inference-failure message was duplicated across `document.py` and `signature_detect.py`; the weights-ref + auth-hint composition existed at 5 separate raise sites and is now one `SignatureWeightsDownloadError` template).
2. A generic `Reader[ModelT]` refactor was rejected in favor of `typing.cast` at each `Reader.read` call site in `claim_batch.py`, since a generic would ripple through `reader.py`, `answer.py`, `markdown.py`, `description.py`, and `document.py`'s `BaseModel`-typed OCR-retry chain — well beyond a lint-fix task's scope.

## Out-of-Scope Follow-ups (not fixed, files not staged by this task)

- `src/main.py` TRY400 x2 (lines ~55, ~110) — not in this task's scope (formatting-only touch from the staged-set `ruff format` pass).
- `src/api/routes_claims.py` B008 x8 and TRY400 x1 — not in this task's scope.
- `src/evaluation/analysis_stats.py::_BOOLEAN_CHECKER_KEYS` diverges from the new `claim_pipeline.py::_STATE_BOOLEAN_KEYS` — different key sets for different purposes; merging them would change evaluation statistics and was explicitly out of scope per the plan.
- A dead `except SignatureDetectionError: raise` remains around the YOLO `predict` call in `detect_signature_with_yolo` (harmless but redundant given the outer `except SignatureDetectionError: raise` was already the pattern before this task).
- pre-commit pins `ruff-pre-commit` v0.15.7 while local `ruff` (used for all gates in this task) is 0.16.8 — version drift between the hook and the local tool, not addressed here.

## Known Stubs

None.

## Threat Flags

None — the only security-relevant surface touched (`UnsafeClaimDirectoryError`, `ConfigFileNotFoundError`) subclasses the exact exception type the existing `except` clauses and API mapping already handle, per the plan's threat register (T-o5k-01 through T-o5k-04), all previously disposed as `mitigate`/`accept`.

## Self-Check: PASSED

- `src/compliance/preprocessing/signature_detect.py` — FOUND, `grep -c "^class Signature"` = 5
- `src/compliance/llm/checker.py` — FOUND, `class UnsupportedCheckerModeError(ValueError)` present
- `src/compliance/config/settings.py` — FOUND, `class ConfigFileNotFoundError(FileNotFoundError)` present
- `src/compliance/preprocessing/claim_batch.py` — FOUND, `def _present_path` and `class UnsafeClaimDirectoryError(ValueError)` present, `_is_present` count = 0
- `src/compliance/workflows/claim_pipeline.py` — FOUND, `_STATE_BOOLEAN_KEYS` count = 3
- Ruff gate on staged `.py` set: 0 violations (verified)
- `ruff format --check` on staged `.py` set: 0 (verified)
- mypy on 11 touched modules: 8 errors, "checked 11 source files" (verified, matches baseline)
- Full pytest: 235 passed, 1 known failure (verified)
- `git write-tree` / `git rev-parse HEAD` / `git stash list`: all unchanged from Step-0 baseline (verified)
- No commits created (verified: `git rev-parse HEAD` unchanged)
