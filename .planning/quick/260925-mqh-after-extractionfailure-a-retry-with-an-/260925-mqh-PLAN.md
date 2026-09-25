---
phase: 260925-mqh-after-extractionfailure-a-retry-with-an-
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - config.yaml
  - src/compliance/config/settings.py
  - src/compliance/config/__init__.py
  - src/compliance/models/claim.py
  - src/compliance/preprocessing/document.py
  - src/compliance/preprocessing/claim_batch.py
  - tests/test_config/test_settings.py
  - tests/test_preprocessing/test_extraction_failure.py
  - tests/test_models/test_claim.py
  - tests/test_workflows/test_pipeline.py
autonomous: true
requirements: []

estimate:
  tokens: 26000
  raw_tokens: 26000
  tasks: 2
  confidence: low

must_haves:
  truths:
    - "When ExtractionFailure marks Docling OCR faulty and ocr_retry.enabled is true, DocumentReader retries once via config-driven Ollama vision model on the resolved PNG path"
    - "When the retry text passes ExtractionFailure, DocumentData uses the retried text/fields and metadata.faulty_extraction is false (HITL only if low confidence still applies)"
    - "When the retry text is still faulty (or the vision call fails), metadata keeps faulty_extraction=true and human_in_the_loop=true"
    - "retry_used / retry_model are recorded on DocumentMetaData; branch logs cover retry start, success, and still-faulty"
    - "Model name, enable flag, and prompt live in config.yaml — no hardcoded model strings in source"
  artifacts:
    - path: "config.yaml"
      provides: "ocr_retry.enabled, model, prompt"
      contains: "ocr_retry:"
    - path: "src/compliance/config/settings.py"
      provides: "OcrRetryConfig on AppConfig"
      contains: "class OcrRetryConfig"
    - path: "src/compliance/preprocessing/document.py"
      provides: "DocumentReader post-ExtractionFailure vision retry"
      contains: "ocr_retry"
    - path: "src/compliance/models/claim.py"
      provides: "DocumentMetaData.retry_used / retry_model"
      contains: "retry_used"
    - path: "tests/test_preprocessing/test_extraction_failure.py"
      provides: "Unit tests with mocked vision chat_fn"
  key_links:
    - from: "ExtractionFailure.evaluate (first Docling pass)"
      to: "DocumentReader._retry_ocr_with_vision (or private helper)"
      via: "faulty=true AND ocr_retry.enabled"
    - from: "retry markdown/text"
      to: "DocumentPreprocessor.preprocess → ExtractionFailure.evaluate → DocumentMetaData"
      via: "same _to_model path as Docling"
    - from: "load_config().ocr_retry"
      to: "DocumentReader(..., ocr_retry=..., retry_chat_fn=...)"
      via: "claim_batch._build_claim_bundle wiring"
---

<objective>
After `ExtractionFailure` flags unusable Docling OCR, automatically retry once with a config-driven expensive vision model; adopt the retry when it clears the failure gate, otherwise keep HITL.

Purpose: Recover claim images where Docling returns empty/`_none_`/figure-noise garbage (e.g. claim 5) without expanding into a second OCR stack.
Output: `ocr_retry` config + `DocumentReader` retry path + metadata fields + mocked unit tests.
</objective>

<execution_context>
@~/.claude/gsd-core/workflows/execute-plan.md
@~/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@src/compliance/preprocessing/document.py
@src/compliance/preprocessing/extraction_failure.py
@src/compliance/preprocessing/claim_batch.py
@src/compliance/preprocessing/extractor.py
@src/compliance/models/claim.py
@src/compliance/config/settings.py
@src/compliance/branch_log.py
@config.yaml
@tests/test_preprocessing/test_extraction_failure.py
@tests/test_config/test_settings.py

## Plan notes — what "expensive model" means here
- This codebase has **no Docling model/VLM knob** today (`DocumentConverter` is fixed; confidence comes from Docling scores only).
- **Chosen approach (simplest existing pattern):** after `ExtractionFailure` says faulty, re-extract markdown/plain text from the **resolved PNG** via **Ollama vision** (`ollama.chat` with multimodal `images`), using `config.yaml` `ocr_retry.model` + `ocr_retry.prompt` — same injectable `chat_fn` seam as `InformationExtractor` / `CaseClassifier`.
- Do **not** introduce a second Docling pipeline or a new top-level package. Prefer private helpers on `DocumentReader` (and optional tiny local helper in `document.py` if needed). `ExtractionFailure` remains the sole quality gate for both passes.
- PDF: resolve path may be PDF (Benford-style passthrough). Retry only when `resolved.suffix` is an image Docling already consumed as PNG (`.png` after FormatConverter). For PDF sources, log `branch=ocr_retry outcome=SKIP reason=pdf` and keep the Docling result (no sprawling PDF→image conversion in this quick task).
- Claude's discretion: default `ocr_retry.enabled: true` in `config.yaml` with a clearly named vision model (e.g. `llava` or `llama3.2-vision` — pick one string in config only); vision call exceptions → treat as still-faulty (keep original Docling DocumentData + HITL), log WARNING; one retry max; do not recurse.
</context>

<interfaces>
Existing seams to reuse:
- `ExtractionFailure.evaluate(raw_text) -> ExtractionFailureResult` — gate for both passes
- `DocumentReader._to_model(processed, source_file=...)` — builds `DocumentMetaData` / HITL
- `log_branch_decision(logger, branch=..., outcome=..., reason=..., **fields)`
- `ChatFn` / `response_content` in `src/compliance/llm/chat.py`; default `ollama.chat`
- `BenfordConfig` optional-section pattern on `AppConfig` (mirror for `OcrRetryConfig`)

New / extended surface:
- `OcrRetryConfig(enabled: bool, model: str, prompt: str)` on `AppConfig.ocr_retry`
- `DocumentMetaData.retry_used: bool = False`, `retry_model: NanStr = _MISSING`
- `DocumentReader.__init__(..., ocr_retry: OcrRetryConfig | None = None, retry_chat_fn: ChatFn | None = None)`
- Private helper producing retry text from PNG path (messages include `images: [str(path)]` per Ollama multimodal API); public `read()` orchestrates Docling → evaluate → maybe retry → re-preprocess → `_to_model`
</interfaces>

<tasks>

<task type="tracer" tdd="true">
  <name>Task 1: Faulty Docling → vision retry success clears faulty_extraction</name>
  <files>config.yaml, src/compliance/config/settings.py, src/compliance/config/__init__.py, src/compliance/models/claim.py, src/compliance/preprocessing/document.py, src/compliance/preprocessing/claim_batch.py, tests/test_preprocessing/test_extraction_failure.py, tests/test_config/test_settings.py, tests/test_models/test_claim.py, tests/test_workflows/test_pipeline.py</files>
  <read_first>
    - src/compliance/preprocessing/document.py (read / _to_model / ExtractionFailure gate)
    - src/compliance/preprocessing/extraction_failure.py
    - src/compliance/preprocessing/extractor.py (chat_fn injection)
    - src/compliance/preprocessing/claim_batch.py (DocumentReader construction ~393)
    - src/compliance/models/claim.py (DocumentMetaData)
    - src/compliance/config/settings.py (BenfordConfig mirror)
    - config.yaml
    - tests/test_preprocessing/test_extraction_failure.py (_mock_converter + HITL test)
    - tests/test_config/test_settings.py (tmp yaml fixtures — add ocr_retry)
    - tests/test_workflows/test_pipeline.py (inline config writers — add ocr_retry)
  </read_first>
  <behavior>
    - test_faulty_extraction_invokes_vision_retry_and_clears_faulty: Docling returns figure-noise garbage; injectable retry_chat_fn returns substantive certificate text; result.metadata.faulty_extraction is False, retry_used is True, retry_model matches config, human_in_the_loop is False when confidence above threshold; retry_chat_fn called exactly once
    - test_load_config_reads_ocr_retry_section: load_config("config.yaml") exposes ocr_retry.enabled, non-empty model, non-empty prompt
  </behavior>
  <action>
    Add top-level `ocr_retry:` to `config.yaml` with `enabled`, `model` (vision model name only in YAML), and `prompt` instructing the model to OCR/transcribe the document image into clean markdown/plain text (no commentary).

    Add `OcrRetryConfig` to `settings.py`, attach as `AppConfig.ocr_retry` (default `OcrRetryConfig`-safe defaults only if tests need absent section; prefer **required** section like classification once added to repo config — update every minimal test YAML that calls `load_config` so validation still passes). Export from `config/__init__.py` if other configs are exported there.

    Extend `DocumentMetaData` with `retry_used: bool = False` and `retry_model: NanStr = _MISSING`. Keep existing JSON artifact fields intact.

    Extend `DocumentReader`: accept optional `ocr_retry` + injectable `retry_chat_fn` (default `ollama.chat`). In `read()`, after first Docling preprocess + `_to_model`, when `metadata.faulty_extraction` and `ocr_retry is not None` and `ocr_retry.enabled` and resolved path is PNG/image: log `branch=ocr_retry outcome=START`; call private helper that invokes `_retry_chat(model=ocr_retry.model, messages=[... prompt + images=[str(resolved)] ...])`; take `response_content`; build a docling-like payload `{text, confidence: _MISSING or prior, has_signature: prior}`; `preprocessor.preprocess` → `_to_model`; set `retry_used=True` and `retry_model=ocr_retry.model` on the returned metadata (mutate via model_copy or rebuild metadata in helper). If retry clears faulty, log `outcome=SUCCESS`. Wire `ocr_retry=config.ocr_retry` in `claim_batch` DocumentReader construction.

    Prefer editing `read` / small private helpers on `DocumentReader` over new modules. Do not change `ExtractionFailure` thresholds API beyond existing constructor.

    Write the success-path unit test with MagicMock `retry_chat_fn` (no live Ollama). Add config load assertion.
  </action>
  <verify>
    <automated>pytest tests/test_preprocessing/test_extraction_failure.py::test_faulty_extraction_invokes_vision_retry_and_clears_faulty tests/test_config/test_settings.py::test_load_config_reads_ocr_retry_section -x</automated>
  </verify>
  <done>One end-to-end faulty→retry-success path works with mocked vision chat; config.ocr_retry loads; metadata.retry_used/retry_model set; claim_batch can construct DocumentReader with ocr_retry.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Retry still-faulty keeps HITL; disabled/skip paths + branch logs</name>
  <files>src/compliance/preprocessing/document.py, tests/test_preprocessing/test_extraction_failure.py</files>
  <read_first>
    - src/compliance/preprocessing/document.py (Task 1 retry path)
    - tests/test_preprocessing/test_extraction_failure.py
    - src/compliance/branch_log.py
  </read_first>
  <behavior>
    - test_faulty_extraction_retry_still_faulty_keeps_hitl: Docling garbage; retry_chat_fn returns more garbage/`_none_`; metadata.faulty_extraction True, human_in_the_loop True, retry_used True
    - test_faulty_extraction_retry_invoked_when_enabled: assert retry_chat_fn called once on faulty path when enabled
    - test_clean_extraction_skips_retry: substantive Docling text; retry_chat_fn never called; retry_used False
    - test_ocr_retry_disabled_skips_chat: faulty Docling but ocr_retry.enabled False; retry_chat_fn never called; HITL remains True
  </behavior>
  <action>
    Finish edge paths on `DocumentReader`: when retry text still fails `ExtractionFailure`, keep faulty + HITL, log `branch=ocr_retry outcome=STILL_FAULTY reason=...` at WARNING with failure reasons (no raw OCR dump / no PII). When vision `retry_chat_fn` raises, catch at the DocumentReader boundary, log `outcome=ERROR`, keep the original Docling DocumentData (still faulty HITL), set `retry_used=True` and `retry_model` so operators see an attempt was made.

    When `enabled` is false or `ocr_retry` is None, skip with `outcome=SKIP`. PDF resolved paths: `outcome=SKIP reason=pdf` without calling chat.

    Expand `tests/test_preprocessing/test_extraction_failure.py` with the behaviors above (mock converter + mock retry_chat_fn only). Keep existing `test_document_reader_marks_faulty_extraction_as_hitl` valid — either inject `ocr_retry` disabled or pass `enabled=False` so prior assertion still holds without requiring a mock chat.
  </action>
  <verify>
    <automated>pytest tests/test_preprocessing/test_extraction_failure.py tests/test_config/test_settings.py -x</automated>
  </verify>
  <done>Retry failure keeps HITL; success/disabled/clean paths covered; branch decisions logged; no live vision calls in tests.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| claim image files → DocumentReader / ollama vision | Untrusted scanned documents (PII) leave the host into the local LLM runtime |
| config.yaml → OcrRetryConfig | Operator-controlled enable flag, model name, prompt |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-260925-mqh-01 | Information Disclosure | ocr_retry chat messages / logs | medium | mitigate | Log only branch/outcome/reason/file/model; never log full OCR text, image bytes, or prompt payloads containing document content |
| T-260925-mqh-02 | Denial of Service | vision retry on every faulty page | low | mitigate | Single retry max; `enabled` flag; skip PDF; injectable chat_fn for tests |
| T-260925-mqh-03 | Tampering | vision response treated as OCR | medium | mitigate | Re-run ExtractionFailure on retry text before clearing faulty/HITL; unusable retry keeps HITL |
| T-260925-mqh-SC | Tampering | npm/pip/cargo installs | low | accept | No new package installs — reuse ollama already in project |
</threat_model>

<verification>
pytest tests/test_preprocessing/test_extraction_failure.py tests/test_config/test_settings.py -x
</verification>

<success_criteria>
- ExtractionFailure remains the gate for Docling and vision-retry text
- Expensive path = config-driven Ollama vision re-OCR of PNG (not a second Docling model)
- Success clears faulty; failure keeps HITL; disabled/clean skip retry
- `retry_used` / `retry_model` on DocumentMetaData; branch logs for START/SUCCESS/STILL_FAULTY/SKIP/ERROR
- Unit tests mock `retry_chat_fn` — no live Ollama required
</success_criteria>

<output>
Create `.planning/quick/260925-mqh-after-extractionfailure-a-retry-with-an-/260925-mqh-SUMMARY.md` when done
</output>
