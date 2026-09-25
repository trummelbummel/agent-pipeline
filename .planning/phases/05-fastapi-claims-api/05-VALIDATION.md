---
phase: "05"
slug: "fastapi-claims-api"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-25"
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_api -x -q` |
| **Full suite command** | `uv run pytest && uv run mypy` |
| **Estimated runtime** | ~60 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_api -x -q`
- **After every plan wave:** Run `uv run pytest && uv run mypy`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-00-01 | 00 | 0 | R022 | T-05-SC | Package legitimacy human-verify before uv add | infra | `uv add fastapi uvicorn python-multipart && uv add --dev httpx` | ❌ W0 | ⬜ pending |
| 05-00-02 | 00 | 0 | R022 | — | Hatch packages includes src/api; test stubs collectable | infra | `uv run pytest tests/test_api -q --tb=short` | ❌ W0 | ⬜ pending |
| 05-01-01 | 01 | 1 | R021 | — | Lifespan exposes pipelines via Depends; create_app(config=...) | unit | `uv run pytest tests/test_api/test_deps_lifespan.py -x` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | R017 | T-05-01 / T-05-02 | Extension allowlist; basename-only filenames; safe claim_id; 409 on collide | unit | `uv run pytest tests/test_api/test_claims_post.py -x` | ❌ W0 | ⬜ pending |
| 05-01-03 | 01 | 1 | R017 | T-05-01 | Reject path traversal / unsafe claim_id | unit | `uv run pytest tests/test_api/test_claims_post.py -x` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 2 | R018 | T-05-01 | GET runs process_then_analyze; missing → 404 | unit | `uv run pytest tests/test_api/test_claims_get.py -x` | ❌ W0 | ⬜ pending |
| 05-02-02 | 02 | 2 | R019 | — | GET /claims lists results_dir; empty → []; stable claim_id order | unit | `uv run pytest tests/test_api/test_claims_list.py -x` | ❌ W0 | ⬜ pending |
| 05-03-01 | 03 | 3 | R020 | — | CLI --claim-id single-claim orchestration | unit | `uv run pytest tests/test_workflows/ -q --tb=short` | ❌ W0 | ⬜ pending |
| 05-03-02 | 03 | 3 | R022 | — | mypy + pytest gate on api/workflows/config/main | static | `uv run pytest tests/test_api tests/test_workflows tests/test_config/test_settings.py -q && uv run mypy src/api/ src/compliance/workflows/ src/compliance/config/ src/main.py` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Human-verify fastapi / uvicorn / python-multipart / httpx on PyPI (SUS seam)
- [ ] `uv add fastapi uvicorn python-multipart` + `uv add --dev httpx`
- [ ] Hatch `packages` includes `src/api`; `src/api/__init__.py` present
- [ ] `tests/test_api/` package + POST/GET/list/lifespan **stubs** (xfail OK) for R017–R021
- [ ] Do **not** implement `create_app` in Wave 0 — deferred to plan 05-01

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Package legitimacy (fastapi/uvicorn/multipart/httpx) | R022 | Research flagged SUS downloads metadata seam | Before `uv add`, confirm packages on PyPI match expected publishers |

*All other phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
