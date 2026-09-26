---
phase: 260926-fph-add-two-analysis-checkers-that-yield-unc
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - config.yaml
  - src/compliance/config/settings.py
  - src/compliance/workflows/claim_pipeline.py
  - tests/test_workflows/test_claim_pipeline.py
  - tests/test_config/test_settings.py
autonomous: true
requirements: []

estimate:
  tokens: 28000
  raw_tokens: 28000
  tasks: 2
  confidence: low

must_haves:
  truths:
    - "When booking departure is within checking.departure_uncertain_within_days of reference today, decision is UNCERTAIN with explanation departure_within_days"
    - "When supporting_document.md OCR text contains two or more distinct calendar dates, decision is UNCERTAIN with explanation multiple_document_dates"
    - "Once either UNCERTAIN date checker fires, containment/contradicts/identity/healthy LLM checkers are not invoked"
    - "UNCERTAIN date flags are applied in _decision_from_state before DENY from other checker flags"
    - "n is loaded from config.yaml via CheckingConfig (not hardcoded in pipeline logic)"
  artifacts:
    - path: "config.yaml"
      provides: "checking.departure_uncertain_within_days integer"
      contains: "departure_uncertain_within_days"
    - path: "src/compliance/config/settings.py"
      provides: "CheckingConfig.departure_uncertain_within_days"
      contains: "departure_uncertain_within_days"
    - path: "src/compliance/workflows/claim_pipeline.py"
      provides: "Deterministic date checkers + early return + decision fold precedence"
      contains: "departure_within_days"
    - path: "tests/test_workflows/test_claim_pipeline.py"
      provides: "UNCERTAIN + early-return regression coverage"
      contains: "departure_within_days"
  key_links:
    - from: "_run_checker_node / _checker_results"
      to: "deterministic date flags before Checker LLM modes"
      via: "early return omitting LLM checker state keys"
    - from: "_decision_from_state"
      to: "GroundTruth UNCERTAIN"
      via: "departure_within_days / multiple_document_dates checked before _violated_checkers"
    - from: "CheckingConfig.departure_uncertain_within_days"
      to: "day-delta comparison"
      via: "config.checking"
---

<objective>
Add two deterministic analysis checkers that yield UNCERTAIN (departure proximity; multiple OCR dates) and short-circuit the checker node so expensive LLM modes do not run once UNCERTAIN is decided.

Purpose: Close false-APPROVE gaps on timing / dating GT cases (e.g. claim 6) without new LLM modes.
Output: Config key + pipeline early-return fold + state/payload flags + focused tests. No LOGIC.md/README updates in this quick task.
</objective>

<execution_context>
@~/.claude/gsd-core/workflows/execute-plan.md
@~/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@src/compliance/workflows/claim_pipeline.py
@src/compliance/config/settings.py
@config.yaml
@src/compliance/models/claim.py
@src/compliance/preprocessing/markdown.py
@tests/test_workflows/test_claim_pipeline.py
@tests/test_config/test_settings.py

## Locked design (from intent — honor exactly)

### D-01 — Departure proximity → UNCERTAIN
If the claim's departure/travel calendar date is within ``n`` days of reference "today", set state ``departure_within_days: true`` and decide UNCERTAIN with explanation ``departure_within_days``.
- ``n`` = ``checking.departure_uncertain_within_days`` in ``config.yaml`` (default suggest **14**), typed on ``CheckingConfig`` with the same default so existing ``CheckingConfig(...)`` test fixtures keep working without every call site updated.
- Inclusive absolute day delta: ``abs(departure_date - today).days <= n``.
- Departure source (priority): parse ``supporting_documents_text`` via existing ``MarkdownPreprocessor`` → ``BookingData.departure``; if missing/unparseable, fall back to the first parseable calendar date in ``description_text``. If still unparseable → flag False (do not UNCERTAIN).
- Reference "today" (locked): parse ``BookingData.current_date`` from the same ``supporting_documents_text`` when that yields a calendar date; else ``datetime.date.today()``. Helpers take an explicit ``today: date`` parameter so unit tests inject a fixed clock without monkeypatching; pipeline computes today once and passes it in.

### D-02 — Multiple dates in supporting_document.md → UNCERTAIN
If ``supporting_document_text`` (medical OCR only — not booking markdown) contains **two or more distinct calendar days**, set ``multiple_document_dates: true`` and decide UNCERTAIN with explanation ``multiple_document_dates``.
- Deterministic regex/date parsing only (no LLM). Reuse one shared date-extraction helper for both checkers.
- Count unique ``date`` values after normalize; ignore unparseable tokens.

### D-03 — Early return once UNCERTAIN
Inside ``_checker_results`` (called from ``_run_checker_node``):
1. Run both deterministic checks (cheap; always compute both flags for observability).
2. If either flag is True: return a dict with ``departure_within_days`` / ``multiple_document_dates`` only (plus whatever non-LLM keys already returned today that are still needed). **Omit** ``checker_containment``, ``checker_contradicts``, ``identity_check``, ``identity_unclear``, ``healthy_check`` so they are absent from state (matches existing payload ``"key" in state`` pattern). Do not construct ``Checker`` / do not call chat.
3. ``_run_checker_node`` still computes ``signature_check`` from metadata (no LLM) — keep that; it must not override UNCERTAIN in the decision fold when date flags fired (see precedence).

### D-04 — Decision-fold precedence (document in code docstring)
Update ``_decision_from_state`` order to:
1. Coverage abstention → UNCERTAIN ``coverage_false_label`` (unchanged; checker node never ran)
2. ``departure_within_days`` True → UNCERTAIN ``departure_within_days``
3. ``multiple_document_dates`` True → UNCERTAIN ``multiple_document_dates``
4. ``_violated_checkers`` non-empty → DENY (existing)
5. ``identity_unclear`` → UNCERTAIN (existing)
6. APPROVE ``checker_consistent``

Rationale: steps 2–3 sit **before** DENY so an early-exit path that somehow still had deny-shaped keys cannot fall through to DENY; when early exit omits LLM keys, step 4 is empty anyway. Signature deny only applies when date UNCERTAIN flags are false.

### Out of scope
- LOGIC.md / README updates
- New LLM Checker modes
- ``checker_suspicious_dating`` stamp-year heuristics (separate from multiple distinct dates)

### Discretion
- Module-level private helpers in ``claim_pipeline.py`` (or a tiny sibling module only if the file split is clearly cleaner) — prefer edit-over-create.
- Date formats to support at minimum: ISO ``YYYY-MM-DD``, ``DD/MM/YYYY``, ``DD-MM-YYYY``, ``DD.MM.YYYY``, and English month names (``14 April 2017`` / ``April 14, 2017``). Strip trailing time suffixes from booking departure values (e.g. ``2016-08-10 13:15 (local)`` → date part).
</context>

<interfaces>
Existing:
- ``ClaimAnalysisState`` — add optional bools ``departure_within_days``, ``multiple_document_dates``
- ``_checker_results(...) -> dict[str, bool]`` — extend return / early-exit shape
- ``_decision_from_state`` / ``_violated_checkers`` / ``_analysis_result_payload``
- ``CheckingConfig`` in settings.py; ``checking:`` block in config.yaml
- ``MarkdownPreprocessor.preprocess(text) -> dict`` + ``BookingData.model_validate``
- Test fixtures: ``_config``, ``_seed_preprocessed_claim``, ``_cancellation_chat_fn`` / MagicMock chat_fn call_count patterns (see ``test_identity_skipped_for_non_medical_document``)

New surface:
- ``CheckingConfig.departure_uncertain_within_days: int`` (default 14)
- Helpers e.g. ``_parse_calendar_date(raw: str) -> date | None``, ``_unique_calendar_dates(text: str) -> set[date]``, ``_departure_within_days(*, supporting_documents_text, description_text, today, within_days) -> bool``, ``_has_multiple_document_dates(supporting_document_text: str) -> bool``
- analysis_result.json keys ``departure_within_days``, ``multiple_document_dates`` when present in state
</interfaces>

<tasks>

<task type="tracer" tdd="true">
  <name>Task 1: Config + departure UNCERTAIN early-return path</name>
  <files>config.yaml, src/compliance/config/settings.py, src/compliance/workflows/claim_pipeline.py, tests/test_workflows/test_claim_pipeline.py, tests/test_config/test_settings.py</files>
  <read_first>
    - src/compliance/workflows/claim_pipeline.py (_run_checker_node, _checker_results, _decision_from_state, _analysis_result_payload, ClaimAnalysisState)
    - src/compliance/config/settings.py (CheckingConfig)
    - config.yaml (checking: block)
    - src/compliance/preprocessing/markdown.py (MarkdownPreprocessor)
    - tests/test_workflows/test_claim_pipeline.py (_config, _seed_preprocessed_claim, test_uncertain_when_identity_unclear, test_identity_skipped_for_non_medical_document)
  </read_first>
  <behavior>
    - load_config("config.yaml") exposes checking.departure_uncertain_within_days as int
    - Given supporting_documents with current_date=2017-08-01 and departure=2017-08-10 and n=14, after classification path reaches run_checker → decision UNCERTAIN, explanation departure_within_days, payload departure_within_days true
    - Same claim: chat_fn is never called for containment/contradicts/identity/healthy (only coverage/reason/document classifier calls) — assert via MagicMock call_count / system prompt contents
    - Helper: abs day delta exactly n → True; n+1 → False; unparseable departure → False
  </behavior>
  <action>
    Per D-01 and D-03/D-04: add ``checking.departure_uncertain_within_days`` to config.yaml and CheckingConfig (default 14). Implement shared calendar-date parse helpers and departure-within-days check. Wire ClaimAnalysisState + _checker_results early return (omit LLM checker keys when flag true) + _decision_from_state precedence (departure flag before _violated_checkers) + payload passthrough. Update _run_checker_node logging reason to reflect early uncertain exit when applicable. Add test_settings assertion for the new config key. Add one e2e pipeline test with fixed booking current_date/departure and stub classifiers only (no checker LLM responses in side_effect). Follow CLAUDE.md (annotations, boundary validation only, Path from config).
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && python -m pytest tests/test_config/test_settings.py::test_load_config_reads_checking_section tests/test_workflows/test_claim_pipeline.py -k "departure_within" -x -q</automated>
  </verify>
  <done>
    Config key loads; departure proximity yields UNCERTAIN with early LLM skip; decision fold prefers departure_within_days over DENY.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Multiple-document-dates UNCERTAIN + combined coverage</name>
  <files>src/compliance/workflows/claim_pipeline.py, tests/test_workflows/test_claim_pipeline.py</files>
  <read_first>
    - src/compliance/workflows/claim_pipeline.py (_checker_results early-return branch from Task 1, _decision_from_state)
    - tests/test_workflows/test_claim_pipeline.py (Task 1 departure test as template)
  </read_first>
  <behavior>
    - supporting_document_text with two distinct calendar days → multiple_document_dates true, decision UNCERTAIN, explanation multiple_document_dates, LLM checkers not invoked
    - single calendar day (repeated same day OK) → flag false; checkers may proceed
    - when both departure_within_days and multiple_document_dates true: both flags persisted; explanation is departure_within_days (first in D-04 precedence)
    - unit: _unique_calendar_dates on sample OCR snippets returns expected set size
  </behavior>
  <action>
    Per D-02: implement multiple-dates check on supporting_document_text only using the shared date extractor; always compute both flags before early return; persist both in state/payload; decision fold step for multiple_document_dates after departure_within_days and before _violated_checkers (D-04). Add pipeline tests for multiple-dates UNCERTAIN + early skip, and a combined-flags precedence test. Do not edit docs.
  </action>
  <verify>
    <automated>cd /Users/theresa/Desktop/projects/compliance && python -m pytest tests/test_workflows/test_claim_pipeline.py -k "departure_within or multiple_document_dates" -x -q</automated>
  </verify>
  <done>
    Multiple OCR dates yield UNCERTAIN with early LLM skip; combined with departure proximity, departure explanation wins while both flags appear in analysis_result.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Preprocessed claim text → date parsers | Untrusted OCR/booking strings enter deterministic regex parsers |
| config.yaml → CheckingConfig | Operator-supplied threshold ``n`` |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-fph-01 | Tampering | Date regex on OCR text | low | accept | Parsers return None/empty on garbage; no eval/exec; failures fail-closed to non-UNCERTAIN |
| T-fph-02 | Denial of service | Pathological long OCR strings | low | accept | Same trust model as existing checkers reading full document text; no new network I/O |
| T-fph-03 | Elevation | checking.departure_uncertain_within_days | low | accept | Config already trusted at process start; invalid types rejected by Pydantic |
| T-fph-SC | Tampering | npm/pip/cargo installs | high | accept | No new packages in this plan |
</threat_model>

<verification>
- pytest filters above pass
- Manual spot-check optional: claim 6-style fixture with current_date ~2 weeks before departure and n=14 → UNCERTAIN
</verification>

<success_criteria>
- Both UNCERTAIN checkers deterministic and config-driven for ``n``
- Early return skips LLM checker modes when either flag fires
- Decision precedence documented in ``_decision_from_state`` docstring and enforced by tests
</success_criteria>

<output>
Create `.planning/quick/260926-fph-add-two-analysis-checkers-that-yield-unc/260926-fph-SUMMARY.md` when done
</output>
