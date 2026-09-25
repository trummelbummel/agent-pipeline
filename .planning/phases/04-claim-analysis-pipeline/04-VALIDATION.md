---
phase: "04"
slug: "claim-analysis-pipeline"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-25"
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest ≥9.0.2 (dev) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_workflows/test_claim_pipeline.py tests/test_config/test_settings.py -q --tb=short` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | ~30 seconds (unit path; no live Ollama) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_workflows/test_claim_pipeline.py tests/test_config/test_settings.py -q --tb=short`
- **After every plan wave:** Run `uv run pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green + `uv run mypy`
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-T2 | 04-01 | 0 | R015 | T-04-SC | analysis taxonomy from config only | unit | `uv run pytest tests/test_config/test_settings.py -k analysis -q` | ❌ W0 | ⬜ pending |
| 04-01-T3 | 04-01 | 0 | R016 | — | Nyquist stubs collect without Ollama | unit | `uv run pytest tests/test_workflows/test_claim_pipeline.py -q` | ❌ W0 | ⬜ pending |
| 04-02-T1 | 04-02 | 1 | R010–R014, R016 | T-04-03 | injectable chat_fn; allow-listed labels | unit | `uv run pytest tests/test_workflows/test_claim_pipeline.py -q` | ❌ W0 | ⬜ pending |
| 04-02-T2 | 04-02 | 1 | R010 | T-04-01 | claim dir name validated before read/write | unit | `uv run pytest tests/test_workflows/test_claim_pipeline.py -k unsafe -q` | ❌ W0 | ⬜ pending |
| 04-03-T1 | 04-03 | 2 | R013 | — | PE/missed routing | unit | `uv run pytest tests/test_workflows/test_claim_pipeline.py -k "personal_effects or missed" -q` | ❌ W0 | ⬜ pending |
| 04-03-T2 | 04-03 | 2 | R012 | — | other_label skips reason/doc/checker | unit | `uv run pytest tests/test_workflows/test_claim_pipeline.py -k other -q` | ❌ W0 | ⬜ pending |
| 04-04-T1 | 04-04 | 3 | R010 | T-04-07 | soft-fail batch | unit | `uv run pytest tests/test_workflows/test_claim_pipeline.py -k batch -q` | ❌ W0 | ⬜ pending |
| 04-04-T2 | 04-04 | 3 | R016 | T-04-02 | CLI analyze; no PII in logs | unit | `uv run pytest tests/test_workflows/ -q && uv run mypy src/compliance/workflows/ src/compliance/config/` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

Existing related (do not replace): `tests/test_models/test_classifier.py`, `tests/test_llm/test_checker.py`, `tests/test_workflows/test_pipeline.py`.

---

## Wave 0 Requirements

- [ ] `uv add langgraph` after `checkpoint:human-verify` (SUS legitimacy flag — confirm official LangChain package)
- [ ] `tests/test_workflows/test_claim_pipeline.py` — covers R010–R014, R016
- [ ] Extend `tests/test_config/test_settings.py` — `analysis` section / R015
- [ ] Add `analysis:` block to `config.yaml` + `AnalysisConfig` in `settings.py`
- [ ] Framework already present — no pytest install needed

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Package legitimacy for langgraph 1.2.12 | Wave 0 | Supply-chain SUS heuristic | Confirm PyPI project is official LangChain org before `uv add` |

*All other phase behaviors have automated verification via injectable chat_fn.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
