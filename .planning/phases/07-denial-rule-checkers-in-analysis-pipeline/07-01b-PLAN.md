---
phase: 07-denial-rule-checkers-in-analysis-pipeline
plan: 01b
type: execute
wave: 2
depends_on:
  - "07-01"
files_modified:
  - tests/test_api/conftest.py
  - tests/test_workflows/test_orchestration.py
  - tests/test_workflows/test_pipeline.py
  - tests/test_evaluation/test_evaluator.py
  - tests/test_evaluation/test_analysis_stats.py
  - tests/test_preprocessing/test_claim_batch.py
  - tests/test_preprocessing/test_integration.py
autonomous: true
requirements:
  - R023
user_setup: []

estimate:
  tokens: 22000
  raw_tokens: 22000
  tasks: 1
  confidence: low

must_haves:
  truths:
    - "All AppConfig/CheckingConfig test helpers under tests/ compile with authenticity_prompt and incomplete_prompt"
    - "Secondary suites (api, evaluation, orchestration, preprocessing) collect without CheckingConfig ValidationError after 07-01 required fields"
  artifacts:
    - path: "tests/test_api/conftest.py"
      provides: "CheckingConfig placeholders for new prompts"
      contains: "authenticity_prompt"
    - path: "tests/test_workflows/test_orchestration.py"
      provides: "CheckingConfig placeholders for new prompts"
      contains: "authenticity_prompt"
  key_links:
    - from: "CheckingConfig required fields (07-01)"
      to: "secondary test AppConfig fixtures"
      via: "authenticity_prompt / incomplete_prompt placeholders"
---

<objective>
Propagate CheckingConfig's new required prompts across secondary test helpers so the full suite collects after 07-01 made authenticity_prompt / incomplete_prompt required.

Purpose: Keep the authenticity tracer plan under the per-plan file budget while unblocking api/evaluation/orchestration/preprocessing modules before incomplete/suspicious-dating work.
Output: Every remaining CheckingConfig(...) site under tests/ (conftest + workflows/evaluation/preprocessing helpers; primary claim_pipeline owned by 07-01) supplies the new prompt fields; suite collects green.
</objective>

<execution_context>
@~/.claude/gsd-core/workflows/execute-plan.md
@~/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/STATE.md
@.planning/phases/07-denial-rule-checkers-in-analysis-pipeline/07-01-PLAN.md
@.planning/phases/07-denial-rule-checkers-in-analysis-pipeline/07-01-SUMMARY.md
@.planning/phases/07-denial-rule-checkers-in-analysis-pipeline/07-RESEARCH.md
@.planning/phases/07-denial-rule-checkers-in-analysis-pipeline/07-PATTERNS.md
@src/compliance/config/settings.py
@tests/test_workflows/test_claim_pipeline.py
@CLAUDE.md

## Locked assumptions (carry forward)

- **A1–A13** from 07-00/07-01 remain in force.
- **A8 (config):** authenticity_prompt and incomplete_prompt are already required on CheckingConfig from 07-01; this plan only updates secondary test literals.
</context>

<source_audit>
| SOURCE   | ID    | Feature/Requirement                                              | Plan    | Status  | Notes |
|----------|-------|------------------------------------------------------------------|---------|---------|-------|
| REQ      | R023  | Config-driven checking (suite must load CheckingConfig)          | 07-01b  | COVERED | Test-helper propagation |
| RESEARCH | —     | CheckingConfig required fields after authenticity prompts        | 07-01b  | COVERED | Glue after tracer |
| CONTEXT  | —     | (absent)                                                         | —       | N/A     | |
</source_audit>

<interfaces>
No production interface changes — glue only:
- CheckingConfig(...) call sites under listed test modules must pass authenticity_prompt and incomplete_prompt
- Live grep sites in scope: tests/test_api/conftest.py, tests/test_workflows/test_orchestration.py, tests/test_workflows/test_pipeline.py, tests/test_evaluation/test_evaluator.py, tests/test_evaluation/test_analysis_stats.py, tests/test_preprocessing/test_claim_batch.py, tests/test_preprocessing/test_integration.py (tests/test_workflows/test_claim_pipeline.py owned by 07-01)
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Propagate CheckingConfig new prompts across remaining test helpers</name>
  <precondition>07-01 SUMMARY committed — CheckingConfig requires authenticity_prompt and incomplete_prompt; primary tracer tests green</precondition>
  <files>tests/test_api/conftest.py, tests/test_workflows/test_orchestration.py, tests/test_workflows/test_pipeline.py, tests/test_evaluation/test_evaluator.py, tests/test_evaluation/test_analysis_stats.py, tests/test_preprocessing/test_claim_batch.py, tests/test_preprocessing/test_integration.py</files>
  <read_first>
    - src/compliance/config/settings.py (CheckingConfig required fields after 07-01)
    - tests/test_workflows/test_claim_pipeline.py (updated CheckingConfig pattern from 07-01)
    - tests/test_api/conftest.py (API AppConfig fixture CheckingConfig literal)
    - .planning/phases/07-denial-rule-checkers-in-analysis-pipeline/07-PATTERNS.md (CheckingConfig / settings test analog)
    - Grep all CheckingConfig( call sites under tests/ for missing authenticity_prompt / incomplete_prompt
  </read_first>
  <behavior>
    - Every CheckingConfig(...) construction in the listed secondary helpers supplies authenticity_prompt and incomplete_prompt (placeholder strings fine)
    - Full non-integration suite still collects; no TypeError / ValidationError on AppConfig construction in these modules
  </behavior>
  <action>
  Update every remaining secondary CheckingConfig literal under tests/ in the listed files (conftest, orchestration, pipeline, evaluator, analysis_stats, claim_batch, integration — live CheckingConfig( sites only; per A8) to pass authenticity_prompt and incomplete_prompt string placeholders matching 07-01's primary helper pattern. Prefer identical placeholder values ("authenticity" / "incomplete") for consistency. Do not change production logic. Do not touch live Ollama. Skip rewriting unrelated assertions. Leave test_claim_pipeline.py to 07-01.
  </action>
  <verify>
    <automated>uv run pytest tests/test_llm/test_checker.py tests/test_workflows/test_claim_pipeline.py tests/test_config/test_settings.py tests/test_api tests/test_evaluation tests/test_workflows/test_orchestration.py tests/test_workflows/test_pipeline.py tests/test_preprocessing/test_claim_batch.py -q --tb=short && uv run mypy src/compliance/</automated>
    <fails_when>non-zero exit, TypeError/ValidationError from Missing authenticity_prompt or incomplete_prompt on CheckingConfig, collection errors, or mypy errors under src/compliance/</fails_when>
  </verify>
  <acceptance_criteria>
    - `rg -n "CheckingConfig\(" tests -g '*.py' -A6` shows authenticity_prompt on each construction site in the listed files
    - pytest verify command exits 0
  </acceptance_criteria>
  <done>All secondary test CheckingConfig helpers include the new required prompts; suite collects and primary phase tests stay green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Test fixtures → CheckingConfig | Synthetic placeholders only; no new runtime input |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-07-SC | Tampering | package installs | high | mitigate | No new packages |
| T-07-03 | Information Disclosure | test logs | low | accept | Fixture placeholders only; no PII |
</threat_model>

## Artifacts this phase produces

| Symbol / path | Kind | Introduced in |
|---------------|------|---------------|
| Secondary CheckingConfig authenticity/incomplete placeholders | tests | 07-01b |

<verification>
- Secondary CheckingConfig sites updated
- api / evaluation / orchestration / preprocessing collect green with primary phase tests
- mypy src/compliance clean
</verification>

<success_criteria>
- Full test suite collects after CheckingConfig required-field expansion from 07-01
- No production behavior change
</success_criteria>

<output>
Create `.planning/phases/07-denial-rule-checkers-in-analysis-pipeline/07-01b-SUMMARY.md` when done
</output>
