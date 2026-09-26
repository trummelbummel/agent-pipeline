# Phase 07: Denial-rule checkers in analysis pipeline - Research

**Researched:** 2026-09-26
**Domain:** ClaimPipeline Checker modes / decision-fold policy over preprocessed claim text
**Confidence:** HIGH (codebase + LOGIC.md + REQUIREMENTS); MEDIUM on authenticity/incomplete heuristics not yet implemented

## Summary

Phase 07 closes the gap between LOGIC.md’s denial-rule catalog and what `ClaimPipeline` actually emits and folds into APPROVE/DENY/UNCERTAIN. Four of six denial categories already have executable checks (`checker_missing_documentation`, `healthy_check`, `identity_check`/`identity_unclear`, `signature_check`) plus two date-based UNCERTAIN short-circuits (`departure_within_days`, `multiple_document_dates`). The remaining Phase 07 work is primarily: (1) add analysis-time **authenticity/format**, **broader incomplete-document**, and **suspicious-dating** checks that IMP-013 notes are documented but absent from the decision fold; (2) reconcile aspirational LOGIC summary names with shipped `analysis_result.json` keys; (3) persist every in-scope flag and wire DENY/UNCERTAIN precedence; (4) injectable `chat_fn` tests — no live Ollama.

Do **not** add packages. Extend existing `Checker` + `CheckingConfig` + `_checker_results` / `_violated_checkers` / `_decision_from_state` seams. Keep Benford off for synthetic data; authenticity must use OCR/format signals only.

**Primary recommendation:** Treat shipped keys as canonical; implement three missing/partial rules (`checker_document_not_authentic`, broader incomplete beyond signature, `checker_suspicious_dating` → UNCERTAIN) on the existing shared `run_checker` sink; update LOGIC.md aliases to match code (IMP-013).

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| R023 | Denial-rule Checker steps in ClaimPipeline; persist in `analysis_result.json`; config prompts/models | Architecture Patterns: extend `run_checker` sink; Standard Stack: reuse Checker/CheckingConfig |
| R024 | Missing documentation (claims 1, 2, 21, 25) | Already implemented via `_is_missing_documentation` + `required_documents`; tests exist — retain/regression |
| R025 | Healthy-certificate / contradicts-claim (10, 14, 22) | Already implemented as `healthy_check` + `checker_contradicts`; naming ≠ LOGIC `checker_healthy_contradiction` — reconcile docs |
| R026 | Identity unverifiable (4, 15) | Already implemented as `identity_check` / `identity_unclear` gated by `identity_required_codes` |
| R027 | Document authenticity / format (7, 8, 18) | **Gap** — add `checker_document_not_authentic`; OCR/format LLM (or hybrid); Benford stays preprocess-optional off |
| R028 | Incomplete document (17) | **Partial** — `signature_check` only; add broader incomplete fields (discharge date / diagnosis) as Phase 07 |
| R029 | Suspicious dating (13, 20, 23) | **Partial** — `departure_within_days` + `multiple_document_dates` exist; stamp/issue-vs-care heuristic (`checker_suspicious_dating`) still out of scope of fph quick task |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Denial-rule evaluation | API / Backend (`ClaimPipeline`) | — | Shared `run_checker` node + `_decision_from_state` already own policy |
| LLM boolean / identity modes | API / Backend (`Checker`) | — | Injectable `chat_fn`; prompts from `CheckingConfig` |
| Required-doc / signature gates | API / Backend (pipeline helpers) | Database / Storage (preprocessed metadata) | Deterministic over classifier labels + `document_metadata.json` |
| Benford forensics | Preprocessing | — | Optional, default off; **not** Phase 07 authenticity path |
| Persist analysis flags | Database / Storage (`results_dir`) | — | `analysis_result.json` + `predicted_answer.json` |
| Config externalization | Config (`config.yaml`) | — | CLAUDE.md: no hardcoded prompts/models/thresholds |

## Gap Analysis: LOGIC rules vs shipped code

| Denial rule | Example claims | Shipped today | Canonical key(s) | Phase 07 action |
|-------------|----------------|---------------|------------------|-----------------|
| Missing documentation | 1, 2, 21, 25 | Yes | `checker_missing_documentation` | Keep; ensure regression tests |
| Healthy certificate | 10, 14, 22 | Yes | `healthy_check` (True → DENY) | Keep; do **not** rename; update LOGIC alias |
| Identity unverifiable | 4, 15 | Yes | `identity_check` False → DENY; `identity_unclear` → UNCERTAIN | Keep; LOGIC summary name `checker_identity_unverifiable` is aspirational only |
| Document not authentic | 7, 8, 18 | **No** | — → add `checker_document_not_authentic` | New Checker mode + decision DENY |
| Incomplete document | 17 (+20 signature) | Partial | `signature_check` False → DENY | Keep signature; add `checker_incomplete_document` for missing discharge/diagnosis/condition fields |
| Suspicious dating | 13, 20, 23 | Partial | `departure_within_days`, `multiple_document_dates` → UNCERTAIN | Add `checker_suspicious_dating` (issue-before-care / implausible year); UNCERTAIN preferred |
| Containment / contradicts | — | Yes | `checker_containment` (info only), `checker_contradicts` (DENY) | Retain unchanged |

**Evidence (shipped keys):** `[VERIFIED: src/compliance/workflows/claim_pipeline.py:1053-1134]` — `_violated_checkers` appends `"checker_missing_documentation"`, `"identity_check"`, `"signature_check"`, `"healthy_check"`, `"checker_contradicts"`; `_decision_from_state` orders coverage abstention → `departure_within_days` → `multiple_document_dates` → DENY → `identity_unclear` → APPROVE.

**Evidence (Checker modes):** `[VERIFIED: src/compliance/llm/checker.py:15-16]` — `CheckerMode = Literal["containment", "contradicts", "identity", "healthy"]`.

**Evidence (LOGIC aspirational names):** `[VERIFIED: LOGIC.md:570-573]` — Summary lists `checker_healthy_contradiction`, `checker_identity_unverifiable`, `checker_document_not_authentic`, `checker_incomplete_document`, `checker_suspicious_dating`. Table at `[VERIFIED: LOGIC.md:349-353]` already maps incomplete to `signature_check` and notes broader incomplete “still Phase 07”; authenticity/suspicious dating listed as not yet in fold (IMP-013).

**Evidence (fph deferred stamp heuristic):** `[VERIFIED: .planning/quick/260926-fph-add-two-analysis-checkers-that-yield-unc/260926-fph-PLAN.md:108-111]` — Out of scope: ``checker_suspicious_dating`` stamp-year heuristics.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Existing `Checker` | in-repo | Boolean / identity / healthy LLM modes | Already wired; extend `CheckerMode` |
| Existing `ClaimPipeline` | in-repo | LangGraph analysis + decision fold | R010–R014 foundation |
| `CheckingConfig` / `AnalysisConfig` | in-repo + `config.yaml` | Prompts, model, required_documents, date window | CLAUDE.md externalization |
| `langgraph` | `>=1.2.12` in pyproject | StateGraph `run_checker` node | Phase 04 stack — **no topology change required** `[VERIFIED: pyproject.toml:29]` |
| `pydantic` | 2.13.5 (env) | Config + `BooleanCheckResult` | Existing pattern `[VERIFIED: uv run]` |
| `ollama` + injectable `ChatFn` | project dep | LLM seam | Unit tests without live Ollama |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | `>=9.0.2` (env 9.1.1) | Unit tests | Wave validation `[VERIFIED: pyproject.toml:42]` |
| `mypy` | `>=1.19.1` | Type gate | Phase gate with `make check` / `uv run mypy` |
| `BenfordLawChecker` | in-repo | Image forensics | **Do not enable** for Phase 07 authenticity (`benford.enabled: false`) `[VERIFIED: config.yaml:243-247]` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Extend `Checker` modes | Separate `DenialRuleEngine` class | Premature — Phase 08 IMP-018 owns policy/orchestration split |
| LLM authenticity | Re-enable Benford | Too sensitive on synthetic images; ROADMAP forbids as default |
| Rename `healthy_check` → `checker_healthy_contradiction` | Alias dual-write | Renames break eval/tests; prefer doc sync |

**Installation:** none — no new packages.

**Version verification:** `langgraph>=1.2.12`, `pytest>=9.0.2`, `pydantic` 2.13.5 observed via `uv run` / `pyproject.toml` this session.

## Package Legitimacy Audit

> No external packages to install for Phase 07.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| — | — | — | — | — | — | N/A — reuse in-repo stack |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
preprocessed claim/
  description.txt ──┐
  supporting_document.md ──┐
  supporting_documents.md ─┼─► load_claim
  document_metadata.json ──┘       │
                                   ▼
                         coverage → reason? → doc classifier
                                   │
                                   ▼
                            run_checker (shared sink)
              ┌────────────────────┼────────────────────┐
              │ deterministic      │ metadata gates     │ LLM Checker modes
              │ departure_within   │ signature_check    │ containment (info)
              │ multiple_dates     │ missing_doc (labels)│ contradicts
              │ suspicious_dating* │                    │ identity*
              │                    │                    │ healthy
              │                    │                    │ not_authentic*
              │                    │                    │ incomplete* (fields)
              └────────────────────┴────────────────────┘
                                   │
                                   ▼
                         _decision_from_state
              UNCERTAIN (coverage / dates / identity_unclear / suspicious_dating*)
              DENY (_violated_checkers)
              APPROVE
                                   │
                                   ▼
                    analysis_result.json + predicted_answer.json
```

`*` = Phase 07 add or broaden.

### Recommended Project Structure

```
src/compliance/
├── llm/checker.py              # Extend CheckerMode + prompts for authenticity / incomplete
├── workflows/claim_pipeline.py # _checker_results, _violated_checkers, _decision_from_state, payload
├── config/settings.py          # CheckingConfig new prompt / threshold fields
config.yaml                     # checking.* prompts; optional dating thresholds
tests/test_llm/test_checker.py
tests/test_workflows/test_claim_pipeline.py
LOGIC.md                        # Align summary flag names with shipped keys (IMP-013)
```

Prefer edit-over-create (CLAUDE.md). Extract private helpers only when `_checker_results` grows another multi-step block.

### Pattern 1: Config-driven Checker mode (existing)

**What:** `Checker.check(claim, text, mode=...)` with prompt from `CheckingConfig`; JSON `{"result": bool}` via `BooleanCheckResult`.
**When to use:** LLM-judged denial signals (healthy, authenticity, incomplete fields, generic contradicts).
**Example:**

```python
# Source: src/compliance/llm/checker.py (existing healthy path)
healthy = checker.check(
    description_text,
    supporting_document_text,
    mode="healthy",
)
```

For authenticity, prefer mode name `not_authentic` (True = fail/deny) to match DENY polarity of `healthy_check` / `checker_contradicts`. Persist as `checker_document_not_authentic`.

### Pattern 2: Deterministic gate before LLM (existing date short-circuit)

**What:** Cheap flags first; early return omits LLM keys from state when UNCERTAIN is already decided.
**When to use:** Suspicious dating that can be decided from parsed calendar dates without chat.
**Example:** Mirror `_departure_within_days` / `_has_multiple_document_dates` — `[VERIFIED: src/compliance/workflows/claim_pipeline.py:834-873]`.

### Pattern 3: Decision-fold precedence

**Locked order today** `[VERIFIED: src/compliance/workflows/claim_pipeline.py:1085-1134]`:

1. Coverage abstention → UNCERTAIN `coverage_false_label`
2. `departure_within_days` → UNCERTAIN
3. `multiple_document_dates` → UNCERTAIN
4. `_violated_checkers` → DENY
5. `identity_unclear` → UNCERTAIN
6. APPROVE `checker_consistent`

**Phase 07 recommendation:** Insert `checker_suspicious_dating` as UNCERTAIN **with** the other date flags (before DENY). Add authenticity + incomplete to `_violated_checkers` (DENY). Do not let containment drive DENY.

### Anti-Patterns to Avoid

- **Renaming shipped keys** (`healthy_check` → `checker_healthy_contradiction`) without a migration — breaks tests/eval and contradicts IMP-013 “identical names” via churn; sync LOGIC instead.
- **Enabling Benford for R027** — config documents synthetic-data false positives `[VERIFIED: config.yaml:243-247]`.
- **New LangGraph nodes per rule** — LOGIC topology uses one shared `run_checker` sink `[VERIFIED: LOGIC.md:150-158]`.
- **Hand-rolling a second Checker class** — extend modes / helpers.
- **Treating empty OCR as authenticity fail only** — empty/faulty OCR often overlaps missing-doc / HITL; prefer ordered rules (missing doc first).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| LLM JSON bool parse | Custom regex | `BooleanCheckResult` + `parse_llm_json_object` | Already handles malformed → False |
| Date parsing | Ad-hoc per rule | Existing `_parse_calendar_date` / `_unique_calendar_dates` | Shared formats from fph |
| Booking name extract | New NLP | `Checker._booking_name` / identity path | Proven for claims 4/15 |
| Policy engine split | Big refactor | Stay in pipeline helpers | Phase 08 IMP-018 |
| Image fraud CNN | Custom CV | Optional Benford (off) + text authenticity mode | Dataset is synthetic |

**Key insight:** Phase 07 is a **policy-coverage completion** on an existing sink, not a new subsystem.

## Common Pitfalls

### Pitfall 1: Naming drift (IMP-013)

**What goes wrong:** Docs promise `checker_healthy_contradiction` while artifacts emit `healthy_check`.
**Why it happens:** LOGIC summary evolved faster than code.
**How to avoid:** Canonical = code/artifact keys; update LOGIC Summary + Denial-rule table in the same phase.
**Warning signs:** Evaluator/debug notes referencing flags absent from `analysis_result.json`.

### Pitfall 2: Polarity confusion

**What goes wrong:** Mixing “pass” vs “violation” booleans (`identity_check` True = OK; `healthy_check` True = DENY).
**Why it happens:** Modes differ by semantics.
**How to avoid:** Document polarity in docstrings; for new modes prefer `checker_*` True = violation (align with `checker_contradicts`, `checker_missing_documentation`).
**Warning signs:** APPROVE when authenticity True.

### Pitfall 3: Early-exit omits keys then soft-fails

**What goes wrong:** Date UNCERTAIN short-circuit omits LLM keys; later code assumes keys always present.
**Why it happens:** Payload uses `"key" in state` pattern `[VERIFIED: claim_pipeline.py:939-956]`.
**How to avoid:** Keep omit-when-skipped; tests assert key absence on early exit (existing fph tests).

### Pitfall 4: Overlapping rules on claim 17 / 13 / 8

**What goes wrong:** Multiple flags fire; explanation comma-join order surprises eval.
**Why it happens:** Claim 17 is healthy + no signature; claim 13 has multiple distinct dates already.
**How to avoid:** Stable `_violated_checkers` order; accept multi-flag DENY explanations; for 13 prefer UNCERTAIN dating before DENY.

### Pitfall 5: Authenticity LLM on non-medical PE/missed paths

**What goes wrong:** “Photo instead of certificate” prompts on boarding proofs.
**Why it happens:** Healthy/contradicts currently run on all positive branches (IMP-014).
**How to avoid:** Gate authenticity/incomplete like identity — medical/hospital codes from `signature_required_codes` / `identity_required_codes` (or a new config list). Full short-circuit optimization can wait for Phase 08 IMP-014, but **do** gate new medical-only modes.

### Pitfall 6: Malformed LLM → silent pass (IMP-005)

**What goes wrong:** `_parse_boolean_result` returns False on parse failure `[VERIFIED: checker.py:187-196]` — for `not_authentic` that means “authentic” (unsafe).
**Why it happens:** False is used as default for all boolean modes.
**How to avoid:** For deny-on-True authenticity/incomplete modes, treat parse failure as UNCERTAIN/HITL **or** True (fail-closed) — recommend fail-closed True for authenticity / incomplete violation modes in Phase 07; leave full ERROR taxonomy to Phase 08 IMP-005 if too large.

## Code Examples

### Extend CheckingConfig (same pattern as healthy)

```python
# Source: src/compliance/config/settings.py CheckingConfig pattern
class CheckingConfig(BaseModel):
    model: str
    containment_prompt: str
    contradicts_prompt: str
    identity_prompt: str
    healthy_prompt: str
    authenticity_prompt: str  # NEW — True when not authentic / wrong format
    incomplete_prompt: str    # NEW — True when required medical fields missing
    departure_uncertain_within_days: int = 14
    # Optional: suspicious_dating_year_delta_max: int = ...
```

### Wire violation keys (decision fold)

```python
# Source: pattern from _violated_checkers
if "checker_document_not_authentic" in state and bool(state["checker_document_not_authentic"]):
    violated.append("checker_document_not_authentic")
if "checker_incomplete_document" in state and bool(state["checker_incomplete_document"]):
    violated.append("checker_incomplete_document")
# signature_check remains separate deterministic gate
```

### Suspicious dating → UNCERTAIN (with date flags)

```python
# Source: pattern from _decision_from_state date UNCERTAIN block
if bool(state.get("checker_suspicious_dating")):
    return GroundTruth(
        decision="UNCERTAIN",
        explanation="checker_suspicious_dating",
    )
```

### Fixture signals from dataset (for test design)

| Claim | GT signal | Implementation hint |
|-------|-----------|---------------------|
| 8 | text-form medical must DENY `[VERIFIED: data/preprocessed/claim 8/answer.json]` | Authenticity: text-only / no image certificate cues |
| 18 | picture instead of certificate `[VERIFIED: data/preprocessed/claim 18/answer.json]` | Authenticity + often empty supporting_document (`_none_`) |
| 7 | photoshopped stamp + missing discharge date `[VERIFIED: data/preprocessed/claim 7/answer.json]` | Authenticity LLM + incomplete fields |
| 13 | stamp 17/11/2023 vs care 16–17/12/2023 `[VERIFIED: data/preprocessed/claim 13/supporting_document.md:7-8]` | Suspicious dating: issue date before care window |
| 23 | weird dating 2016 vs care 2015 `[VERIFIED: data/preprocessed/claim 23/answer.json]` | Year skew / multiple dates |
| 17 | good condition + lacks signature `[VERIFIED: data/preprocessed/claim 17/answer.json]` | `healthy_check` + `signature_check`; OCR currently empty/faulty in metadata |

## State of the Art (this repo)

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Containment+contradicts only | + identity, healthy, signature, missing-doc | Phase 04 + follow-ons | Core DENY path |
| No date UNCERTAIN | `departure_within_days` + `multiple_document_dates` early-exit | 260926-fph | Closes timing false APPROVEs |
| LOGIC lists authenticity/suspicious dating | Not in decision fold | — | Phase 07 / IMP-013 |

**Deprecated/outdated:**
- LOGIC Summary names that do not match artifacts — update in Phase 07, do not leave dual vocabularies.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Fail-closed (True) on authenticity/incomplete LLM parse failure is preferred over UNCERTAIN | Pitfalls / Code Examples | Over-DENY rate rises; user may want HITL instead |
| A2 | Gate authenticity/incomplete to medical/hospital doc codes only | Pitfalls | PE/missed claims miss format checks if they ever need them |
| A3 | `checker_suspicious_dating` stays separate from `multiple_document_dates` (additive) | Gap Analysis | Redundant UNCERTAIN explanations if not documented |
| A4 | No discuss-phase CONTEXT — recommendations above are discretion defaults | Open Questions | User may want different flag names or DENY vs UNCERTAIN for dating |

## Open Questions (RESOLVED)

1. **Canonical naming for healthy/identity**
   - What we know: Code emits `healthy_check` / `identity_check`; LOGIC Summary uses different strings.
   - What's unclear: Whether product wants a rename or doc-only sync.
   - Recommendation: **Doc-only sync** (keep code keys); dual-write aliases only if an external consumer already expects LOGIC names (none found in-repo).
   - RESOLVED: Doc-only sync — keep shipped `healthy_check` / `identity_check` keys; LOGIC aliases in 07-03 (A2 / IMP-013).

2. **Authenticity fail-closed vs UNCERTAIN on LLM error**
   - What we know: Current bool parse defaults to False (unsafe for deny-on-True).
   - What's unclear: Phase 07 vs Phase 08 IMP-005 ownership.
   - Recommendation: Phase 07 fail-closed for new deny-on-True modes; IMP-005 later for typed ERROR across all modes.
   - RESOLVED: Fail-closed True for deny-on-True modes (`not_authentic`, `incomplete`) in Phase 07 (A10); typed ERROR across all modes deferred to IMP-005 / Phase 08.

3. **Claim 20**
   - What we know: LOGIC category 7 = missing signature → UNCERTAIN acceptable; `signature_check` currently DENY.
   - What's unclear: Softening signature to UNCERTAIN is policy, not in R023–R029 explicitly.
   - Recommendation: Leave signature → DENY; do not change in Phase 07 unless eval requires UNCERTAIN for claim 20.
   - RESOLVED: Leave `signature_check` → DENY unchanged in Phase 07 (A17); claim-20 UNCERTAIN softening out of scope.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | ✓ | 3.14.2 | — |
| `uv` / pytest | Tests | ✓ | pytest 9.1.1 | — |
| Ollama | Live LLM | not required | — | Injectable `chat_fn` for unit tests |
| Docling / Benford | Preprocess only | N/A for Phase 07 analysis work | — | Authenticity uses OCR text already on disk |

**Missing dependencies with no fallback:** none for Phase 07 unit path.

**Missing dependencies with fallback:** live Ollama — tests inject `chat_fn`.

Step 2.6: external tools only for optional live analysis runs; planning/execution of Phase 07 is code+pytest.

## Validation Architecture

> `workflow.nyquist_validation` absent from `.planning/config.json` → treat as **enabled**.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest ≥9.0.2 (env 9.1.1) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths = ["tests"]`) |
| Quick run command | `uv run pytest tests/test_llm/test_checker.py tests/test_workflows/test_claim_pipeline.py -q --tb=line` |
| Full suite command | `uv run pytest tests/ -q --ignore=tests/test_preprocessing/test_integration.py` (or `make test`) |
| Type gate | `uv run mypy` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| R024 | Empty / wrong doc type → `checker_missing_documentation` | unit | `uv run pytest tests/test_workflows/test_claim_pipeline.py -k missing_documentation -q` | ✅ |
| R025 | Healthy OCR → `healthy_check` True → DENY | unit | `uv run pytest tests/test_workflows/test_claim_pipeline.py -k healthy_check -q` + `tests/test_llm/test_checker.py -k healthy` | ✅ |
| R026 | Identity mismatch / unclear | unit | `uv run pytest tests/test_workflows/test_claim_pipeline.py -k identity -q` | ✅ |
| R027 | Text-only / photo / tamper cues → `checker_document_not_authentic` | unit | injectable chat_fn fixture | ❌ Wave 0 |
| R028 | Missing discharge/diagnosis → `checker_incomplete_document`; signature still DENY | unit | extend pipeline + checker tests | ❌ Wave 0 (signature ✅) |
| R029 | Implausible stamp/issue dating → `checker_suspicious_dating` UNCERTAIN | unit | deterministic helper + decision fold | ❌ Wave 0 (date UNCERTAIN ✅) |
| R023 | All flags persist in analysis_result; config prompts | unit | payload assertions + settings load | ❌ Wave 0 for new keys |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_llm/test_checker.py tests/test_workflows/test_claim_pipeline.py -q --tb=line`
- **Per wave merge:** same + `tests/test_config/test_settings.py`
- **Phase gate:** `uv run pytest tests/test_llm tests/test_workflows tests/test_config -q` && `uv run mypy`

### Wave 0 Gaps

- [ ] `tests/test_llm/test_checker.py` — modes for authenticity / incomplete (injectable chat_fn; polarity + parse-failure behavior)
- [ ] `tests/test_workflows/test_claim_pipeline.py` — DENY on `checker_document_not_authentic`; DENY on `checker_incomplete_document`; UNCERTAIN on `checker_suspicious_dating`; gating for non-medical docs; payload key persistence
- [ ] `tests/test_config/test_settings.py` — new `checking.*` prompt fields required by `load_config()`
- [ ] Optional: claim-shaped fixtures mirroring OCR snippets from claims 8/13/18 (synthetic strings — do not require live Docling)

*(Existing missing-doc / healthy / identity / signature / date-UNCERTAIN tests remain regression anchors.)*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | yes | Claim path safety already at `analyze_claim`; checker inputs are preprocessed text — no new external input surface |
| V6 Cryptography | no | — (Benford not crypto; leave disabled) |

### Known Threat Patterns for claim-analysis checkers

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection via OCR/claim text | Tampering | Structured JSON `format="json"` + Pydantic validate; no tool use in Checker |
| PII in logs | Information disclosure | CLAUDE.md: no PII in logs; log branch outcomes not raw names |
| Unsafe default on LLM parse fail | Elevation of privilege (false APPROVE) | Fail-closed for deny-on-True authenticity/incomplete |
| Path traversal via claim_id | Tampering | Existing safe claim_id validation (out of Phase 07 scope) |

## Project Constraints (from CLAUDE.md)

- Small functions; extract private helpers named after **what they produce**
- Return structured data (dict/dataclass), not raw scalars/tuples
- `from __future__ import annotations`; type all params/returns; `X | None`
- Docstrings on public methods with `:param:` purpose
- Validate only at system boundaries; no defensive try/except for impossible paths
- Externalize config (prompts, models, thresholds) to `config.yaml`
- Paths from config only; join with `Path` / `/`
- No secrets/PII in logs
- Test real implementations where possible; do not mock internals; only tests asked for
- Prefer editing existing files over creating new ones; delete unused code

## Sources

### Primary (HIGH confidence)

- `src/compliance/llm/checker.py` — modes, parse defaults
- `src/compliance/workflows/claim_pipeline.py` — checker node, missing-doc, decision fold
- `src/compliance/config/settings.py` + `config.yaml` — CheckingConfig / required_documents / benford
- `LOGIC.md` — Denial-rule checkers + Summary of Denial Rules + categories
- `.planning/REQUIREMENTS.md` — R023–R029
- `.gsd/IMPROVEMENTS.md` — IMP-013, IMP-014, IMP-005 overlap
- `.planning/quick/260926-fph-.../260926-fph-PLAN.md` — date UNCERTAIN + deferred suspicious dating
- `tests/test_llm/test_checker.py`, `tests/test_workflows/test_claim_pipeline.py`
- Preprocessed claim answers/OCR for 7, 8, 13, 17, 18, 23

### Secondary (MEDIUM confidence)

- ROADMAP Phase 7 success criteria (aligns with R023–R029)
- IMP-014 short-circuit (defer full optimization to Phase 08; gate new medical modes now)

### Tertiary (LOW confidence)

- A1–A4 discretion defaults (no CONTEXT.md / discuss-phase)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — reuse verified in-repo; no new deps
- Architecture: HIGH — shared `run_checker` sink documented and implemented
- Pitfalls: HIGH — naming drift and parse-default polarity verified in code
- New heuristic design (authenticity/incomplete/suspicious dating): MEDIUM — dataset signals clear; exact prompt/thresholds are discretion

**Research date:** 2026-09-26
**Valid until:** 2026-10-26 (stable in-repo domain)

## RESEARCH COMPLETE
