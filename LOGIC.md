# Claim Denial Logic

## Preprocessing Pipeline

Raw claim folders under `data/raw/claim N/` are transformed into a mirrored tree under `data/preprocessed/` (plus optional predictions under `data/results/`). That preprocessed tree is the input shape for the claim-analysis LangGraph (`ClaimPipeline`). Run via `make preprocess` / `python src/main.py --mode preprocess`. All paths, formats, models, and artifact filenames come from `config.yaml`.

### Inputs (per claim folder)


| Source                      | Typical files                            | Role                                                               |
| --------------------------- | ---------------------------------------- | ------------------------------------------------------------------ |
| Description letter          | `description.txt`                        | Free-text claim narrative (often multilingual)                     |
| Ground truth                | `answer.json`                            | Labelled decision (training/eval only; not used by analysis graph) |
| Booking / internal markdown | `supporting1.md`, `internal *.md`, etc.  | Structured booking evidence as key/value markdown                  |
| Raster / PDF documents      | `.webp`, `.jpg`, `.jpeg`, `.png`, `.pdf` | Medical certs, boarding passes, booking scans                      |


Missing optional files are allowed: absent fields become `np.nan` / empty lists so the claim still produces a valid bundle.

### Step-by-step

1. **Discover claims**
  Scan `preprocessing.data_dir` for claim folders (`claim 1` …). Soft-fail per claim: one bad folder is logged and the batch continues.
2. **Classify files in the folder**
  Partition paths into answer JSON, description text, markdown bookings, and document images/PDFs using configured `document_formats`.
3. **Read ground truth** (`AnswerReader`)
  Parse `answer.json` into typed `GroundTruth` (APPROVE / DENY / UNCERTAIN + reason).
4. **Read markdown bookings** (`MarkdownReader`)
  Normalize / translate keys and map into `BookingData` (name, booking_ref, price, origin/destination, dates, …). Unknown keys are dropped with a warning.
5. **Extract description booking fields** (`DescriptionReader` + `InformationExtractor`)
  Send `description.txt` to the local LLM (`extraction.model`, default `qwen2.5:7b`) with the `BookingData` JSON schema and `extraction.prompt`.
   Output: structured `description_booking` plus retained raw `description_text` (needed later by classifiers / Checker).
   LLM failures leave booking fields empty (`np.nan`) but keep raw text when possible.
6. **Process supporting documents** (`DocumentReader`) — for each configured image/PDF:
  - **Format convert** — raster formats → PNG via `FormatConverter` (PNG passthrough; PDF skipped for Pillow conversion and passed to Docling).
  - **Optional Benford forensics** — DCT Benford on PNG when `benford.enabled` (default **off** for this synthetic dataset). Non-conformity → early `DocumentData` with DENY / fraud and **no Docling**.
  - **Docling OCR** — PNG/PDF → markdown `raw_text` plus person/date and extensible `fields`; confidence vs `confidence_threshold` may set `human_in_the_loop`.
  - **ExtractionFailure check** — flag unusable OCR (too short / too few words per `extraction_failure`).
  - **Optional OCR retry** — when `ocr_retry.enabled`, one vision-model pass (`ocr_retry.model`, default `Maternion/LightOnOCR-2:1b`) on the PNG if Docling is weak: `faulty_extraction`, low `extraction_probability` (below `confidence_threshold`), and/or `human_in_the_loop` (per `on_`* flags). Preprocess only — analysis never re-runs OCR. Never recurses.
  - **Optional signature verify** — when Docling’s figure classifier leaves `has_signature: false` and `ocr_retry.on_missing_signature` is on, Ultralytics YOLO (`ocr_retry.signature_model`, default `tech4humans/yolov8s-signature-detector`) detects handwritten signatures on the PNG. On any box ≥ `signature_confidence`, metadata is updated (`has_signature: true`, `signature_verify_used: true`). Not an Ollama call — LightOn stays OCR-text-only.
7. **Assemble** `ClaimBundle`
  Typed in-memory record: claim id, ground truth, markdown bookings, description booking + raw text, Docling documents, source file inventory.
8. **Write mirrored preprocessed artifacts** (`PreprocessingPipeline`)
  Under `preprocessed_dir/claim N/` (names from `preprocessing.artifacts`):

  | Artifact                  | Contents                                                  |
  | ------------------------- | --------------------------------------------------------- |
  | `description.txt`         | Original claim letter text                                |
  | `answer.json`             | Ground-truth decision (copied/serialized)                 |
  | `supporting_document.md`  | Docling-extracted document text (markdown sections)       |
  | `supporting_documents.md` | Booking / internal markdown fields as markdown            |
  | `document_metadata.json`  | Per-document confidence, signature flag, faulty OCR, HITL |
  | `*.png`                   | Converted (or original) document rasters when applicable  |

9. **Optional predicted answer**
  When document decisions imply an early deny (e.g. Benford fraud), write `predicted_answer.json` under `results_dir/claim N/` — separate from preprocessed inputs.



### Output shape for analysis

`ClaimPipeline` (`make analyze`) reads the **preprocessed** tree, not raw:

- `description.txt` → coverage / reason classifiers
- `supporting_document.md` (and related text) → document-type classifiers + Checker
- Paths stay config-rooted (`preprocessed_dir`, `results_dir`); analysis stages `analysis_result.json` + `predicted_answer.json` + `run_manifest.json` under `results_dir/.staging/{run_id}/{claim}/` and promotes them atomically (manifest last). Analysis never writes back into `preprocessed_dir`.

Preprocessing therefore turns heterogeneous claim folders into a uniform, text-first layout so the LangGraph only needs filesystem reads + LLM classify/check steps.

---



## Analysis Pipeline

`ClaimPipeline` (LangGraph `StateGraph`) classifies each preprocessed claim and writes structured results. Run via `make analyze` (always runs `make preprocess` first, then `make evaluation` after analysis) / `python src/main.py --mode analyze` or `--mode both`. It reads only from `preprocessed_dir`, never from raw claim folders, and never re-runs OCR. Stage labels, prompts, and models live under `analysis:` and `checking:` in `config.yaml`. Labels are numeric codes (`"1"`, `"2"`, …); human-readable meanings are in each stage’s prompt mapping.

### Inputs (per claim folder under `data/preprocessed/`)


| Artifact                  | Used for                                                                |
| ------------------------- | ----------------------------------------------------------------------- |
| `description.txt`         | Coverage classifier; cancellation-reason classifier; Checker claim text |
| `supporting_document.md`  | Document-type classifiers; Checker reference text                       |
| `supporting_documents.md` | Loaded into state (booking/internal markdown); optional for later steps |


Missing optional files become empty strings where allowed; required description / supporting-document reads fail the claim (soft-fail in batch).

### Why this graph structure (consistency across similar claim types)

The analysis graph is a **typed decision tree with a shared checker sink**, not a free-form agent that invents steps per claim. That choice is deliberate:

1. **Same coverage ⇒ same path** — Once coverage is classified, edges are fixed. Every trip-cancellation claim runs reason → cancel-document → checker; every personal-effects claim runs PE-document → checker. Similar claims cannot silently take different node sequences.
2. **Shared checkers, gated by type** — All document branches call the same `run_checker` node. Which gates fire (identity, signature, required-doc set) depends only on config maps for the labels already chosen on that path — not on ad-hoc LLM planning.
3. **One decision fold** — `decision_from_state` applies a single ordered policy to the same flag vocabulary. Same failed flags ⇒ same APPROVE / DENY / UNCERTAIN explanation string, so outcomes stay comparable across the batch.
4. **LLM for classification and boolean checks only** — Routing and deny precedence stay deterministic. Consistency comes from **topology + config + shared decision function**, not from asking the model to “be consistent.”
5. **Cost: cheap / deterministic first** — See [Cost management](#cost-management-cheapdeterministic-before-models). Models run only when substring / token gates miss or Docling OCR is unusable; analysis never re-OCRs.



### Cost management (cheap/deterministic before models)

Escalate only when a free or cheaper step fails or is flagged weak. All LLMs/vision models are local (Ollama).

**Preprocess (per document)**

1. Pillow convert → PNG (PDF passthrough).
2. Optional DCT **Benford** (`benford.enabled`, default **off** on this synthetic set — was too sensitive and would early-DENY without Docling).
3. **Docling** OCR + layout; signature hint from figure classification (`has_signature`).
4. Deterministic **ExtractionFailure** (min chars / min words) → `faulty_extraction` / HITL.
5. Optional **LightOnOCR** text retry when `ocr_retry` triggers match: faulty extraction, low confidence, and/or HITL.
6. Optional **YOLO signature detect** when Docling left `has_signature: false` (`on_missing_signature`).

**Analyze (Checker / gates)**


| Check                   | Free / deterministic first                    | Model fallback                                  |
| ----------------------- | --------------------------------------------- | ----------------------------------------------- |
| Containment             | Normalized claim ⊆ document                   | Containment LLM                                 |
| Identity                | Booking name full-string or all tokens in OCR | Identity LLM (`match` / `mismatch` / `unclear`) |
| Signature               | Metadata `has_signature` (preprocess only)    | — (no analysis OCR)                             |
| Missing doc             | Doc code ∈ `required_documents`               | —                                               |
| Routing / decision fold | Graph edges + ordered deny reasons            | —                                               |


`contradicts` is LLM-only. Medical semantics (healthy, suspicious dating, identity, signature, authenticity, incomplete) are skipped on non-medical branches.

These cheap gates were tightened after eval failures that were **not** model-routing bugs: OCR spelling/order variants on identity, empty Docling text → wrong doc class, and Docling signature false negatives (vision verify / OCR retry only when those cheap signals fire). Detail: [Evaluation](#evaluation-ground-truth-vs-predicted).

### Graph topology (nodes + checkers per branch)

Coverage’s **primary** semantic class routes every claim onto one fixed path. Codes in config stay numeric; the diagram uses `label_names`. Checker boxes list what `run_checker` / the decision fold actually evaluate on that path (`—` = gate skipped).

```
START
  │
  ▼
load_artifacts
  │
  ▼
classify_coverage
  │
  │
  ├─ Trip cancellation or rescheduling
  │         │
  │         ▼
  │   classify_reason
  │         │
  │         ▼
  │   classify_cancel_document
  │         │
  │         ▼
  │   run_checker ─────────────────────────────────────────────┐
  │   • missing_documentation (required_documents[reason])     │
  │   • containment (informational only)                       │
  │   • contradicts                                            │
  │   • identity_check / identity_unclear                      │
  │       (only if doc ∈ identity_required_codes:              │
  │        medical certificate / hospital admission)           │
  │   • signature_check (same medical/hospital codes)          │
  │   • healthy_check (same medical/hospital codes)            │
  │   • suspicious_dating (same medical/hospital codes)        │
  │         │                                                  │
  │         ▼                                                  │
  │                                                              │
  ├─ Personal Effects                                            │
  │         │                                                    │
  │         ▼                                                    │
  │   classify_pe_document                                       │
  │         │                                                    │
  │         ▼                                                    │
  │   run_checker ─────────────────────────────────────────────┤
  │   • missing_documentation (PE required_documents)          │
  │   • containment (informational only)                       │
  │   • contradicts                                            │
  │   • identity_check — skipped (not cancellation medical)    │
  │   • signature_check — skipped                              │
  │   • healthy_check — skipped                                │
  │   • suspicious_dating — skipped                            │
  │         │                                                  │
  │         ▼                                                  │
  │                                                              │
  ├─ Missed Departure or Missed Connection                       │
  │         │                                                    │
  │         ▼                                                    │
  │   classify_missed_document                                   │
  │         │                                                    │
  │         ▼                                                    │
  │   run_checker ─────────────────────────────────────────────┤
  │   • missing_documentation (missed required_documents)      │
  │   • containment (informational only)                       │
  │   • contradicts                                            │
  │   • identity_check — skipped                               │
  │   • signature_check — skipped                              │
  │   • healthy_check — skipped                                │
  │   • suspicious_dating — skipped                            │
  │         │                                                  │
  │         ▼                                                  │
  │                                                              │
  └─ other / unknown (False)                                     │
            │                                                    │
            │   (no reason / document / checker nodes)           │
            │   decision = UNCERTAIN (coverage_false_label) + HITL│
            ▼                                                    │
         persist ◄───────────────────────────────────────────────┘
            │
            ▼
           END
```


| Coverage route                        | Nodes                                                | Checkers / gates on that path                                                                                                                                                                                                 |
| ------------------------------------- | ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Trip cancellation or rescheduling     | reason → cancel document → **run_checker** → persist | **missing_documentation**; **containment** (info); **contradicts**; **identity** / **signature** / **healthy_check** / **suspicious_dating** only for medical certificate / hospital admission                               |
| Personal Effects                      | PE document → **run_checker** → persist              | **missing_documentation** (PE proof); **containment** (info); **contradicts**; identity / signature / healthy_check / suspicious_dating **skipped**                                                                          |
| Missed Departure or Missed Connection | missed document → **run_checker** → persist          | **missing_documentation** (incident / booking); **containment** (info); **contradicts**; identity / signature / healthy_check / suspicious_dating **skipped**                                                                |
| other / unknown (`False`)             | persist only                                         | **No checkers** → **UNCERTAIN** (`coverage_false_label`) + `human_in_the_loop`                                                                                                                                                |


**How the graph enforces consistency**

1. **Hard routing, not free-form LLM decisions** — After coverage, edges are fixed. A medical cancellation never invents a PE document stage; a PE claim never runs cancellation-reason classification.
2. **Shared sinks** — All document branches converge on `run_checker` then `persist`. Containment / contradicts / healthy use the same checker node; only *which* gates fire (identity, signature, required docs) depends on coverage + classified document type from config.
3. **Config-tied gates on the same path** — `required_documents`, `identity_required_codes`, and `signature_required_codes` are looked up from the labels produced on that path. Two claims with the same coverage + reason + document type hit the same acceptability set and the same identity/signature rules.
4. **Deterministic decision fold** — `compliance.policy.decision.decision_from_state` applies one ordered policy (missing doc → identity mismatch → signature → healthy → contradicts → identity unclear → approve). Same flag pattern → same APPROVE / DENY / UNCERTAIN.

So consistency comes from **topology + shared decision function**, not from asking the LLM to “be consistent.” Similar cases that classify the same way walk the same edges and face the same rules.

### Step-by-step

1. **Discover claims** (`ClaimPipeline.run`)
  Scan `preprocessing.preprocessed_dir` for claim folders. Soft-fail per claim: one failure is logged (claim name + exception type only — no letter/OCR payloads) and the batch continues.
2. **Load artifacts** (`load_artifacts`)
  Read `description.txt`, `supporting_document.md`, and optional `supporting_documents.md` into `ClaimAnalysisState` (`compliance.policy.state`). Claim folder names are validated as a single safe path segment.
3. **Classify coverage** (`classify_coverage`)
  `CaseClassifier` on `description_text` with `analysis.coverage`:

  | Code      | Meaning                                                                                    |
  | --------- | ------------------------------------------------------------------------------------------ |
  | `"1"`     | Trip cancellation / rescheduling                                                           |
  | `"2"`     | Personal Effects                                                                           |
  | `"3"`     | Missed Departure / Missed Connection                                                       |
  | `"False"` | Confident that none of the coverage classes apply → persist only; sets `human_in_the_loop` |
  | `"False"` | None of the classes apply / uncertain — persist only + HITL                                |

4. **Route after coverage**
  - `"1"` → cancellation reason → cancellation document → Checker
  - `"2"` → personal-effects document → Checker
  - `"3"` → missed-departure document → Checker
  - `"False"` / unknown → persist only (empty reason/document lists; no checker keys; HITL)
5. **Cancellation branch only — reason** (`classify_reason`)
  Classifier on `description_text` with `analysis.cancellation_reason`:

  | Code      | Meaning                                         |
  | --------- | ----------------------------------------------- |
  | `"1"`     | Jury duty                                       |
  | `"2"`     | Medical emergency (needs medical report)        |
  | `"3"`     | Theft / criminal incident (needs police report) |
  | `"4"`     | Other specified personal emergencies            |
  | `"False"` | Confident that none of the reason classes apply |
  | `"False"` | None of the reason classes apply / uncertain    |

6. **Document-type classifiers** (one path runs, on `supporting_document_text`)

  | Branch           | Config stage                | Codes                                                                                                 |
  | ---------------- | --------------------------- | ----------------------------------------------------------------------------------------------------- |
  | Cancellation     | `cancellation_document`     | `"1"` medical certificate · `"2"` police report · `"3"` jury summon letter · `"4"` hospital admission |
  | Personal Effects | `personal_effects_document` | `"1"` proof of theft/loss/damage                                                                      |
  | Missed Departure | `missed_departure_document` | `"1"` incident/delay documentation · `"2"` proof of booking                                           |

   Unmatched → `"False"` (`other_label`, same abstention token).
7. **Checker** (`run_checker`) — skipped on coverage-other path
  Boolean checks via `Checker` (`checking.model`, default `qwen2.5:7b`). Claim text = `description.txt`; reference = `supporting_document.md`.
  - **Containment** — is the claim present in / entailed by the document? (informational only; does **not** drive DENY)
  - **Contradicts** — does the claim contradict the document? → can DENY
  - **Identity** (`identity_check`) — only when classified doc is medical certificate / hospital admission (`identity_required_codes`). Extracts booking `**name`**, lowercases/normalizes, and **matches without LLM** if the full name or all name tokens are contained in `supporting_document.md`. Otherwise LLM: patient/subject only (ignore doctor/facility). **mismatch → DENY**; **unclear patient field → UNCERTAIN**; skipped on non-medical docs
  - **Signature** (`signature_check`) — for classified **medical certificate** or **hospital admission**, require `has_signature: true` in `document_metadata.json`. **False → DENY**
  - **Healthy** (`healthy_check`) — only on medical certificate / hospital admission codes (`signature_required_codes`). Does `supporting_document.md` assert the patient is healthy / fit / clinically well? **True → DENY** (e.g. claim 10 “CLÍNICAMENTE SANA”)
  - Every claim that reaches `run_checker` records `checker_rule_set` (which medical rule set ran) and `checker_skipped` (gated checks that did not run); a skipped check records no result.
8. **Missing documentation (decision rule)** — after document classification
  Compare classified document codes (excluding abstention `"False"`) to the acceptable set from `analysis.required_documents` for this claim’s coverage / cancellation reason
   `checker_missing_documentation = true` when the classified set is empty **or** has no overlap with the acceptable set.

  | Coverage / reason                                 | Acceptable document codes (config)                   |
  | ------------------------------------------------- | ---------------------------------------------------- |
  | Cancellation · Jury duty (`"1"`)                  | `"3"` jury summon letter                             |
  | Cancellation · Medical emergency (`"2"`)          | `"1"` medical certificate · `"4"` hospital admission |
  | Cancellation · Theft / criminal (`"3"`)           | `"2"` police report                                  |
  | Cancellation · Other personal emergencies (`"4"`) | `"1"` · `"2"` · `"3"` (any cancellation doc)         |
  | Personal Effects                                  | `"1"` proof of theft, loss, or damage                |
  | Missed Departure / Connection                     | `"1"` incident/delay doc · `"2"` proof of booking    |

   Multiple cancellation reasons → union of their acceptable codes. Document only `"False"` / abstention → missing.
9. **Derive decision** (`decision_from_state`) → written into `analysis_result.json` and `predicted_answer.json`
  1. Coverage = `"False"` / unknown → **UNCERTAIN** (`coverage_false_label`) + HITL; skip checkers below
  2. Missing documentation → **DENY** (`checker_missing_documentation`)
  3. Identity **mismatch** on a medical/hospital doc → **DENY** (`identity_check`)
  4. `signature_check` is **False** (classified type is medical certificate or hospital admission and `document_metadata.json` has `has_signature: false`) → **DENY** (`signature_check`)
  5. `healthy_check` is **True** (`supporting_document.md` asserts healthy / fit / not ill) → **DENY** (`healthy_check`)
  6. `checker_contradicts` → **DENY** (`checker_contradicts`; keys can appear comma-joined)
  7. Identity **unclear** (no clear patient field on OCR) → **UNCERTAIN** (`identity_unclear`)
  8. Else → **APPROVE** (`checker_consistent`)
    ntainment failure is **not** a deny reason. Identity runs only for `identity_required_codes` (medical certificate / hospital admission). `signature_check` uses preprocessing metadata (e.g. claim 18 hospital admission with `has_signature: false`). `healthy_check` reads the medical OCR only (claims 10, 14, 22). Further denial-rule checkers (authenticity, dating): see [Denial-rule checkers](#denial-rule-checkers).
10. **Persist** (`persist`)
  Stage `analysis_result.json` + `predicted_answer.json` under `results_dir/.staging/{run_id}/{claim}/`, fsync, promote with `os.replace`, then rename `run_manifest.json` last as the commit marker. Analysis never writes back into `preprocessed_dir`. HITL provenance is recorded as `human_in_the_loop_source` on the published analysis artifacts. Per-claim failures in a batch are recorded at `results_dir/.runs/{run_id}.json`.



### Output shape

```json
{
  "claim_id": "claim 16",
  "coverage_labels": ["Trip cancellation or rescheduling"],
  "coverage_label_codes": ["1"],
  "reason_labels": ["Medical emergency"],
  "reason_label_codes": ["2"],
  "document_labels": ["medical certificate"],
  "document_label_codes": ["1"],
  "checker_containment": true,
  "checker_contradicts": false,
  "identity_check": true,
  "document_has_signature": true,
  "signature_check": true,
  "checker_missing_documentation": false,
  "human_in_the_loop": false,
  "decision": "APPROVE",
  "decision_explanation": "checker_consistent"
}
```

- `*_labels` are semantic names from `config.analysis.*.label_names`; `*_label_codes` keep the numeric classifier codes.
- `reason_labels` / `document_labels` (and their codes) are empty lists when that stage did not run.
- Checker keys (including `checker_missing_documentation`) are **omitted** when coverage routed to persist-only (no document/Checker nodes).
- `human_in_the_loop` is true when preprocess OCR already flagged review **or** any classifier returned `"False"`.
- On DENY, `decision_explanation` lists violated keys (e.g. `checker_missing_documentation`, `checker_contradicts`, or both comma-joined). Same string → `predicted_answer.json` `explanation`.

Analysis derives `APPROVE` / `DENY` / `UNCERTAIN` into both artifacts under `results_dir`. Ground truth remains in preprocessed `answer.json` for eval only.

---



## Denial-rule checkers

Classification (coverage / reason / document type) does **not** encode deny reasons. After document classification, `run_checker` evaluates claim narrative against supporting evidence and sets boolean flags. A later decision step (or reviewer) can turn any `true` into DENY or UNCERTAIN.


| Denial rule (see [Summary of Denial Rules](#summary-of-denial-rules)) | Example claims | Checker flag                                  | What it verifies                                                                                                                                                                                                                                                                                              | Primary inputs                                               |
| --------------------------------------------------------------------- | -------------- | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| No medical / supporting document                                      | 1, 2, 21, 25   | `checker_missing_documentation`               | Classified document type is missing (`None`) or **not in the acceptable set** for this claim’s coverage / cancellation reason (`analysis.required_documents` in config). E.g. medical emergency requires medical certificate; jury duty requires jury summon letter. Not “claim letter not contained in OCR”. | `document_labels` + coverage/reason codes                    |
| Document contradicts claim (healthy cert)                             | 10, 14, 22     | `checker_healthy_contradiction`               | Certificate states patient is healthy / fit / able to travel, contradicting an illness-based claim. Complements generic `checker_contradicts` when that mode is too broad                                                                                                                                     | description + supporting document                            |
| Identity unverifiable                                                 | 4, 15          | `identity_check` (False) / `identity_unclear` | Passenger **name** in `supporting_documents.md` vs patient/subject on `supporting_document.md`. Runs only for cancellation medical/hospital docs (`identity_required_codes`). **mismatch → DENY**; **unclear patient field → UNCERTAIN**; ignore doctor/facility names.                                       | supporting_documents + supporting_document                   |
| Document not authentic / wrong format                                 | 7, 8, 18       | `checker_document_not_authentic`              | Wrong format or authenticity concerns from text/signals: text-only “medical” doc, photo instead of certificate, photoshopped stamp/signature cues. Complements optional Benford in preprocessing (off for synthetic data)                                                                                     | supporting document (+ metadata); **not** Benford-by-default |
| Incomplete document                                                   | 17, 20         | `signature_check` (False)                     | Medical certificate / hospital admission without `has_signature: true` in `document_metadata.json` → **DENY**. (Broader incomplete-field checks still Phase 07.)                                                                                                                                              | `document_labels` + `document_metadata.json`                 |
| Suspicious dating                                                     | 13, 20, 23     | `checker_suspicious_dating`                   | Timestamps inconsistent or implausible (e.g. stamp year far from claim/booking dates). Evaluated on medical documents only (`signature_required_codes`). May map to **UNCERTAIN** rather than hard DENY downstream                                                                                          | description, supporting document, optional booking dates     |




### Baseline vs specialized contradiction

- `checker_contradicts` — generic: does the claim narrative contradict the reference text for any reason?
- `checker_healthy_contradiction` — rule-specific: medical text asserts health / fitness in conflict with a sickness/hospitalization claim (claims 10, 14, 22). Prefer this flag when deciding on the “healthy certificate” deny path.



### How flags combine with classification

Typical deny / uncertain triggers (illustrative — decision policy may refine):

1. `checker_missing_documentation` → DENY when classified doc type ∉ acceptable set for coverage/reason (`required_documents`).
2. `checker_healthy_contradiction` (or strong `checker_contradicts` on a medical path) → DENY.
3. `checker_identity_unverifiable` → DENY.
4. `checker_document_not_authentic` → DENY.
5. `checker_incomplete_document` → DENY (or UNCERTAIN if policy softens).
6. `checker_suspicious_dating` → UNCERTAIN preferred; DENY acceptable per dataset notes.
7. Failed **containment** is informational only — it does **not** mean missing documentation (a medical cert rarely contains the claim letter).

Config: each mode’s prompt (and shared `checking.model`) lives in `config.yaml` under `checking:`; acceptable document codes under `analysis.required_documents`.

---



## Denial Categories



### 1. Missing Documentation

Medical or supporting documentation was not provided at all.


| Claim | Reason                                                           |
| ----- | ---------------------------------------------------------------- |
| 1     | Medical document missing                                         |
| 2     | Medical document missing; missed medical appointment not covered |
| 21    | No supporting documentation provided                             |
| 25    | Medical document missing                                         |




### 2. Document Proves Health (Not Illness)

The submitted medical certificate states the claimant is healthy, contradicting the claim.


| Claim | Reason                                           |
| ----- | ------------------------------------------------ |
| 10    | Medical certificate states the person is healthy |
| 14    | Medical document states the patient is healthy   |
| 22    | Medical certificate states the person is healthy |




### 3. Identity Mismatch / Redaction

The claimant's identity cannot be verified from the submitted documents.


| Claim | Reason                                                  |
| ----- | ------------------------------------------------------- |
| 4     | Name is redacted                                        |
| 15    | Name is obscured and visible initials do not correspond |




### 4. Document Authenticity / Format Issues

The document format or appearance raises concerns about validity.


| Claim | Reason                                                                   |
| ----- | ------------------------------------------------------------------------ |
| 7     | Suspicious: stamp/signature appears photoshopped, missing discharge date |
| 8     | Medical document is in text form — must be denied                        |
| 18    | A picture is attached instead of the medical certificate                 |




### 5. Incomplete Document Content

Required fields (signature, dates, condition details) are missing or contradictory.


| Claim | Reason                                                                 |
| ----- | ---------------------------------------------------------------------- |
| 17    | Documentation states claimant is in good condition + lacks a signature |




### 6. Suspicious Timestamps

Document dating is inconsistent or implausible.


| Claim | Decision                    | Reason                                           |
| ----- | --------------------------- | ------------------------------------------------ |
| 13    | UNCERTAIN (DENY acceptable) | Suspicious dating on document (17/11/2023 stamp) |
| 23    | UNCERTAIN (DENY acceptable) | Weird dating (2016 in the bottom)                |




### 7. Missing Signature

The medical certificate lacks a required signature.


| Claim | Decision                    | Reason                                  |
| ----- | --------------------------- | --------------------------------------- |
| 20    | UNCERTAIN (DENY acceptable) | No signature on the medical certificate |




## Cross-Document Association (Approval Example)



### Claim 16 — Train Refund Due to Hospitalization (APPROVED)

Piccirilli Francesca requested a refund for a train ticket she couldn't use because she was hospitalized. Three data sources corroborate the claim:


| Data Point           | description.txt               | internal train data.md               | Italian_medical_1.jpg           |
| -------------------- | ----------------------------- | ------------------------------------ | ------------------------------- |
| **Person**           | (implicit claimant)           | Piccirilly Francesca                 | PICCIRILLI FRANCESCA            |
| **Date of incident** | 14 aprile 2017                | Departure: 2017-04-14                | Admitted: 14-04-2017            |
| **Hospital**         | Ospedale Renzetti di Lanciano | —                                    | P.O. "Renzetti", ASL 2 Lanciano |
| **Location**         | Lanciano                      | Departure: Pescara Centrale (nearby) | Lanciano (CH)                   |


**Associations verified:**

1. **Name match** — Train booking: "Piccirilly Francesca" vs. hospital certificate: "PICCIRILLI FRANCESCA" (minor spelling variation, likely booking typo)
2. **Date match** — All three sources reference **14 April 2017**: the description says she was hospitalized that day, the train was booked for 17:10 departure that day, and the hospital certificate confirms admission on 14-04-2017
3. **Hospital match** — Description names "Ospedale Renzetti di Lanciano"; certificate is from "P.O. Renzetti" under "Azienda Sanitaria Locale N. 2 Lanciano" — same facility
4. **Geographic consistency** — Train departs from Pescara Centrale; Lanciano is ~60km from Pescara in Abruzzo — consistent with someone living in Lanciano who had a Pescara departure

The medical certificate serves as supporting evidence for why the ticket went unused. All documents corroborate each other → claim **APPROVED**.

## Data Source Analysis: `description.txt` vs `supporting1.md`

Checked 5 claims (1, 3, 5, 6, 19) to determine whether `supporting1.md` extracts structured information from `description.txt`.

**Conclusion:** `supporting1.md` **is NOT an extraction of** `description.txt`**.** They are **separate data sources**:

- `description.txt` — the customer's claim letter (narrative: reason, hospital, dates, circumstances)
- `supporting1.md` — the company's internal booking/ticket record (structured: passenger name, booking ref, operator, route, fare, departure time)



### Overlap and Gaps


| Field             | In description.txt | In supporting1.md          |
| ----------------- | ------------------ | -------------------------- |
| Customer name     | Yes (narrative)    | Yes (structured)           |
| Travel date       | Yes (narrative)    | Yes (structured departure) |
| Medical reason    | Yes                | **No**                     |
| Hospital / doctor | Yes                | **No**                     |
| Diagnosis         | Yes                | **No**                     |
| Booking reference | **No**             | Yes                        |
| Operator / route  | Sometimes vague    | Yes (exact)                |
| Fare / price      | **No**             | Yes                        |
| Seat / class      | **No**             | Yes                        |
| Booking date      | **No**             | Yes                        |




### Per-Claim Detail

**Claim 1 — Thomas Becker**

- `description.txt`: Daughter's severe allergic reaction, couldn't check in at Ganga Vatika Boutique Hotel, Rishikesh, March 25, 2024
- `supporting1.md`: Nearly empty — only contains "Current date is: 2024-04-25", no booking data at all

**Claim 3 — Evelyne Kacou Meitiale**

- `description.txt`: Hospitalized, had surgery, couldn't travel
- `supporting1.md`: Internal booking — AF703, Air France, ABJ→CDG, departure 2011-08-13, name reordered as "Kacou Meitiale Evelyne"

**Claim 5 — Olivier Bayante**

- `description.txt`: Acute illness at work on October 31st, missed flight to Palermo
- `supporting1.md`: Booking — AZ88124933, LIN→PMO, departure Nov 1. Medical reason absent.

**Claim 6 — Marta Rojas Valbuena / Jorge Velosa Ruiz**

- `description.txt`: Partner Jorge hospitalized at Clínica Reina Sofía on July 22, flight to Miami on Aug 15
- `supporting1.md`: Booking — BOG→MIA, departure 2017-08-15, name "Marta Isabel Rojas Valbuena". Hospital details absent.

**Claim 19 — Marcos Junes**

- `description.txt`: Gastroenteritis, 72h rest prescribed, missed train on September 20, 2013
- `supporting1.md`: Booking — TRN-22450119, Buenos Aires→Mar del Plata, departure 2013-09-20. Medical reason absent.



### Key Takeaway

The two files share **customer name** and **travel date** as common keys for cross-referencing, but serve different purposes. The description provides the *reason* for the claim; the supporting data provides the *booking evidence* that a trip was actually booked. Neither is derived from the other.

## Summary of Denial Rules

A claim is denied when any of these conditions are met:

1. **No medical document** (claims 1, 2, 21, 25) — the claim has no medical certificate or supporting evidence attached → `checker_missing_documentation`
2. **Document contradicts claim** (claims 10, 14, 22) — the medical certificate says the patient is healthy → `checker_healthy_contradiction` (see also generic `checker_contradicts`)
3. **Identity unverifiable** (claims 4, 15) — the name on the medical document is redacted, obscured, or does not match the claimant → `checker_identity_unverifiable`
4. **Document not authentic** (claims 7, 8, 18) — signs of tampering (photoshopped elements), wrong format (text-only, photo instead of certificate) → `checker_document_not_authentic`
5. **Incomplete document** (claim 17) — missing required fields such as signature, discharge date, or diagnosis → `checker_incomplete_document`
6. **Suspicious dating** (claims 13, 20, 23) — timestamps on the document are inconsistent or implausible (may result in UNCERTAIN rather than outright DENY) → `checker_suspicious_dating`

Full checker inputs and how flags combine with classification: [Denial-rule checkers](#denial-rule-checkers).

## Evaluation: Ground Truth vs Predicted

The evaluated population is discovered from **`data_dir`** (ground-truth claim folders whose `answer.json` is readable and whose decision is in `evaluation.labels`). A missing or invalid prediction with ground truth present is counted **incorrect** (matrix column = `evaluation.unscored_label`); invalid ground truth is excluded from the denominator and counted separately; predictions with no ground-truth folder are unmatched. `coverage_rate` = scored / ground-truth population.

Two named metric sets share that population: **`raw`** (exact decision equality) and **`policy`** (also credits non-nan `acceptable_decision`, remapped onto the true label). Accuracy and macro F1 are derived from one confusion matrix per named set (rows = labels, columns = labels + unscored column; accuracy = trace / total).

Per-claim comparison from `answer.json` (ground truth) vs `predicted_answer.json` / `analysis_result.json` (pipeline). Labels are `APPROVE` / `DENY` / `UNCERTAIN`. Pred reasons are `decision_explanation`. A claim whose prediction disagrees with its `run_manifest.json` is counted as incorrect rather than scored.

**Code note:** the deterministic ``multiple_document_dates`` UNCERTAIN early-exit was **removed** (it fired on normal medical forms that mention birth + issue / date ranges). Date UNCERTAIN gates that remain: ``departure_within_days`` and ``checker_suspicious_dating``. Re-run ``make analyze`` + ``make evaluation`` to refresh metrics below after this change.

**Last measured batch** (under the previous **results-first** population and acceptable-credited accuracy — before ground-truth-first SR-006 and before removing multi-date; YOLO + Phase 07 authenticity/incomplete/suspicious dating): evaluator **17 / 25 (68%)**, macro F1 **≈0.59**. Charts: [evaluation_visualization.png](data/results/evaluation_visualization.png), [analysis_stats_visualization.png](data/results/analysis_stats_visualization.png). Re-run `make analyze` + `make evaluation` to measure under the current ground-truth-first `raw` / `policy` metrics.

Confusion (last measured):

| GT \\ Pred | APPROVE | DENY | UNCERTAIN |
| ---------- | ------- | ---- | --------- |
| APPROVE    | 2       | 1    | 4         |
| DENY       | 0       | 12   | 1         |
| UNCERTAIN  | 0       | 2    | 3         |

**YOLO (preprocess):** ran on **14** Docling-absent docs; **flipped 3** → `has_signature=true` (claims **11**, **18**, **19**).

### Per-claim results (last measured batch)

Rows that were decided only by ``multiple_document_dates`` are marked **stale** — those decisions will change after re-analyze.

| Claim | GT | Pred | Pred reason | Compared values | Match | HITL | YOLO | Notes |
| ----- | -- | ---- | ----------- | --------------- | ----- | ---- | ---- | ----- |
| 1 | DENY | DENY | missing_documentation | wrong / absent medical type | ✓ | | ran | |
| 2 | DENY | DENY | healthy_check | healthy / unfit path | ✓ | ✓ | ran | |
| 3 | APPROVE | APPROVE | checker_consistent | medical; identity + signature OK | ✓ | | | |
| 4 | DENY | DENY | identity + authenticity + incomplete | redacted / mismatch | ✓ | | | |
| 5 | APPROVE | DENY | identity + authenticity + incomplete | Italian OCR `Bongiorno Oliciero` | ✗ | ✓ | | current hard miss |
| 6 | UNCERTAIN | DENY | authenticity + incomplete | flight ~2 weeks out; `departure_within_days=false` | ✗ | | | current hard miss |
| 7 | DENY | DENY | identity + incomplete | unverifiable name | ✓ | | | |
| 8 | DENY | DENY | missing_documentation | wrong type / None | ✓ | ✓ | | |
| 9 | APPROVE | UNCERTAIN | ~~multiple_document_dates~~ | issue + range end | ✗ | | | **stale** — gate removed |
| 10 | DENY | DENY | healthy_check | OCR asserts healthy | ✓ | | | |
| 11 | APPROVE | APPROVE | checker_consistent | **YOLO flipped** | ✓ | | **flip** | |
| 12 | APPROVE | UNCERTAIN | ~~multiple_document_dates~~ | birth + admission + issue | ✗ | | ran | **stale** — gate removed |
| 13 | UNCERTAIN | UNCERTAIN | ~~multiple_document_dates~~ | may still UNCERTAIN via `checker_suspicious_dating` | ✓ | | | **re-check** |
| 14 | DENY | DENY | healthy_check | fit / sports-camp cert | ✓ | | | |
| 15 | DENY | UNCERTAIN | ~~multiple_document_dates~~ | birth + Eing/Ausg | ✗ | | ran | **stale** — gate removed |
| 16 | APPROVE | UNCERTAIN | ~~multiple_document_dates~~ | birth + ricovero; suspicious dating also true | ✗ | | ran | **stale** / may become suspicious-dating UNCERTAIN |
| 17 | DENY | DENY | signature + healthy | unsigned + healthy | ✓ | | ran | |
| 18 | DENY | UNCERTAIN | identity_unclear | picture-as-doc (`acceptable=UNCERTAIN`); **YOLO flipped** | ~ | ✓ | **flip** | |
| 19 | APPROVE | UNCERTAIN | ~~multiple_document_dates~~ | exam dates; YOLO flipped | ✗ | ✓ | **flip** | **stale** — gate removed |
| 20 | UNCERTAIN | DENY | identity + signature | unreadable name + unsigned (`acceptable=DENY`) | ~ | | ran | |
| 21 | DENY | DENY | missing_documentation | no supporting doc | ✓ | ✓ | | |
| 22 | DENY | DENY | signature + healthy + authenticity | healthy / unsigned | ✓ | | ran | |
| 23 | UNCERTAIN | DENY | identity + signature + authenticity | weird dating GT (`acceptable=DENY`) | ~ | | ran | |
| 24 | UNCERTAIN | DENY | signature + authenticity | soft-APPROVE timing (`acceptable=APPROVE`) | ✗ | | ran | current hard miss |
| 25 | DENY | DENY | missing_documentation | booking screenshot | ✓ | ✓ | ran | |

Match key: **✓** same label · **~** pred equals GT `acceptable_decision` · **✗** hard mismatch.

### Remaining hard misses (not caused by removed multi-date gate)

| Claim | GT → Pred | Root cause |
| ----- | --------- | ---------- |
| **5** | APPROVE → DENY | Italian OCR identity fail + authenticity/incomplete stack |
| **6** | UNCERTAIN → DENY | Authenticity/incomplete overfire; `departure_within_days` silent |
| **24** | UNCERTAIN → DENY | Unsigned + authenticity on soft-APPROVE timing |

Soft-only: **18**, **20**, **23**.

### Failure buckets (active)

#### A. Authenticity / incomplete overfire

| Claim | Outcome | Notes |
| ----- | ------- | ----- |
| **4**, **7**, **22**, **23**~ | ✓ / ~ | Reasonable on suspicious docs |
| **5** | ✗ | Stacks on OCR identity fail |
| **6** | ✗ | Should be UNCERTAIN (timing), not DENY |
| **24** | ✗ | Soft-APPROVE timing case |

#### B. YOLO signature verify

| Claim | Flip? | Impact |
| ----- | ----- | ------ |
| **11** | yes | APPROVE held |
| **18** | yes | Soft UNCERTAIN via `identity_unclear` |
| **19** | yes | Was multi-date UNCERTAIN — re-analyze |
| **12**, **16**, **24**, … | ran, absent | Still unsigned |

#### C. Timing — claim **6**

`departure_within_days` still **0** fires this batch. Need a real UNCERTAIN path for “flight still weeks out.”

### Working paths

| Signal | Claims | Notes |
| ------ | ------ | ----- |
| `healthy_check` | 2, 10, 14 | Stable when reached |
| `identity_check` | 4, 7, 20~, 23~ | True mismatches; **5** OCR FP |
| `signature_check` | 17, 20~, 22, 23~, 24✗ | Mix TP / FN |
| `checker_missing_documentation` | 1, 8, 21, 25 | Mostly TP |
| authenticity / incomplete | 4✓, 5✗, 6✗, 7✓, 22✓, 23~, 24✗ | Phase 07 |
| `departure_within_days` | — | **0** fires |
| `checker_suspicious_dating` | (re-check **13**, **16**) | Remains after multi-date removal |

### Takeaway

1. **`multiple_document_dates` removed** — overfired on birth + issue / date ranges; do not restore without role filtering.
2. **Authenticity / incomplete** still over-deny **5**, **6**, **24**.
3. **YOLO** helps (**11**, **18**); unsigned FNs remain on some medical scans.
4. **Re-run analyze + evaluation** to measure accuracy without the multi-date gate (expect claims **9**, **12**, **15**, **19** to change; **13**/**16** may still UNCERTAIN via suspicious dating).

## Results: Benford's Law Image Forensics

We wired a DCT-based Benford's Law check into `DocumentReader` (PNG-first, before Docling). On non-conformity the pipeline early-returns `DENY` / reason `fraud` and writes `predicted_answer.json` under `results_dir` (default `data/results/`).

**Outcome on this dataset:** fraud detection does **not** work as expected. Every claim image in `data/` is synthetic / fabricated for the take-home. Quantisation / DCT coefficient distributions on fake imagery systematically deviate from Benford's curve, so the chi-squared gate flags almost all files as fraud — **too sensitive on synthetic data**.

**Config:** Benford is controlled by `benford.enabled` in `config.yaml` (default `false` for this project). Re-enable for real scanned certificates/photos where coefficient statistics are more meaningful:

```yaml
benford:
  enabled: true
  block_size: 8
  chi_squared_threshold: 15.51
```

**Takeaway:** keep Benford as an optional real-data forensic signal; do not use it as a default deny rule against generated take-home imagery.
