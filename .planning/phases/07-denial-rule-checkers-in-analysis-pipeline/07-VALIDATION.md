---
phase: "07"
slug: "denial-rule-checkers-in-analysis-pipeline"
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-26"
---

# Phase 07 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest ≥9.0.2 (env 9.1.1) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_llm/test_checker.py tests/test_workflows/test_claim_pipeline.py -q --tb=line` |
| **Full suite command** | `uv run pytest tests/test_llm tests/test_workflows tests/test_config -q` && `uv run mypy` |
| **Estimated runtime** | ~15–30 seconds (unit); mypy ~3s |

---

## Sampling Rate

- **After every task commit:** Run quick command above
- **After every plan wave:** Quick + `tests/test_config/test_settings.py` + mypy
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-*-* | TBD | 0–N | R023–R029 | — | No PII in logs; injectable chat_fn only | unit | see RESEARCH Sampling Rate | ❌ W0 for R027–R029 | ⬜ pending |

*Filled by planner into PLAN.md verify blocks; Wave 0 stubs close File Exists gaps.*

---

## Wave 0 Requirements

- [ ] `tests/test_llm/test_checker.py` — stubs for authenticity / incomplete modes (injectable chat_fn; polarity + parse-failure)
- [ ] `tests/test_workflows/test_claim_pipeline.py` — stubs for DENY on not-authentic / incomplete; UNCERTAIN on suspicious dating; payload key persistence
- [ ] `tests/test_config/test_settings.py` — new `checking.*` prompt fields required by `load_config()`

Existing missing-doc / healthy / identity / signature / date-UNCERTAIN tests remain regression anchors.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| — | — | All phase behaviors have automated verification. | — |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
