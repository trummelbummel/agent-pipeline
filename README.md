# Compliance Take home

Insurance claim preprocessing and analysis pipeline (FastAPI + Ollama). Paths, models, and artifact names come from `config.yaml`.

- **Repository:** [https://github.com/theresaf/compliance/](https://github.com/theresaf/compliance/)
- **Policy reference:** `[policy.md](policy.md)`
- **Dataset notes:** `[takehome_readme.md](takehome_readme.md)`

## Setup

```bash
make install
```

Installs Ollama (if needed), syncs the Python env with `uv`, and pulls every model named in `config.yaml`.

### Image OCR failure-mode tools (`ocr_retry`)

Docling is the primary OCR. Two optional tools run only for **specific Docling failure modes** (never on every image):


| Tool                                              | Config                                               | Failure mode it fixes                                                                                                                                                                                                                      |
| ------------------------------------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `**Maternion/LightOnOCR-2:1b**` (Ollama vision)   | `ocr_retry.model`                                    | **Weak / unusable text** — Docling output is too short, low-confidence, or HITL-flagged (`on_faulty_extraction` / `on_low_confidence` / `on_human_in_the_loop`). Re-transcribes the PNG so downstream classifiers are not fed junk OCR.    |
| **YOLO** `tech4humans/yolov8s-signature-detector` | `ocr_retry.signature_model` + `on_missing_signature` | **Signature false negatives** — Docling’s figure classifier left `has_signature: false` on medical/hospital scans that still show a handwritten signature (e.g. claims 12, 16). Detects signature boxes only; it does **not** re-OCR text. |


**Published benchmarks** (why these models — not Docling replacements for every page):


| Model                                         | Benchmark                                                                                               | Headline numbers                                                                                                                                                      | Source                                                                                                                             |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| LightOnOCR-2-1B (`Maternion/LightOnOCR-2:1b`) | [OlmOCR-Bench](https://huggingface.co/datasets/allenai/olmOCR-bench)                                    | **83.2** overall (SOTA among reported systems at ~1B params); strong on tables **89.0**, multi-column **84.8**, long/tiny text **91.4**; weaker on old scans **42.2** | [LightOnOCR-2-1B card](https://huggingface.co/lightonai/LightOnOCR-2-1B) / [tech report](https://huggingface.co/papers/2601.14251) |
| YOLOv8s signature detector                    | [tech4humans/signature-detection](https://huggingface.co/datasets/tech4humans/signature-detection) test | **[mAP@0.5](mailto:mAP@0.5) 94.5%**, [mAP@0.5](mailto:mAP@0.5):0.95 **67.4%**, precision **94.7%**, recall **89.7%**, F1 **92.2%**                                    | [model card](https://huggingface.co/tech4humans/yolov8s-signature-detector)                                                        |


**Impact on this take-home batch** (Docling + these failure-mode tools; see `[LOGIC.md](LOGIC.md#evaluation-ground-truth-vs-predicted)`):


| Pipeline stage                                          | Evaluator accuracy / macro F1 | What changed                                          |
| ------------------------------------------------------- | ----------------------------- | ----------------------------------------------------- |
| Coverage `"False"` abstention (before signature verify) | **48%** / ≈0.46               | Many true DENYs never reached signature/healthy gates |
| After YOLO signature verify                             | **68%** / ≈0.64               | Recovered signature FNs; +20 pts vs prior             |
| Current (identity edit-distance + suspicious dating; departure UNCERTAIN off) | **~76%** / ≈0.70              | Soft accuracy 19/25; HITL 7/18                        |


LightOn still cannot fix every garbled medical scan (e.g. claim **5** OCR remains weak); YOLO removes the dominant Docling signature-miss DENYs but does not re-OCR text.

### YOLO signature detection (`HF_TOKEN`)

When Docling leaves `has_signature: false` and `ocr_retry.on_missing_signature` is on, preprocess runs **Ultralytics YOLO** (`tech4humans/yolov8s-signature-detector`). That HuggingFace repo is **gated** — there is **no silent fallback**. Missing weights / auth / `ultralytics` raises `SignatureDetectionError` and stops the claim.

Login alone is not enough: you must also be **authorized** on the model page.

1. Log in to Hugging Face in the browser as the **same account** you will use for the CLI token.
2. Open [tech4humans/yolov8s-signature-detector](https://huggingface.co/tech4humans/yolov8s-signature-detector) and **accept the agreement / request access** while that user is logged in. Until you are on the authorized list, downloads return **403** even with a valid token.
3. Authenticate the CLI (preferred):

```bash
hf auth login --force
```

   Or export a **read** token before `make preprocess` / `make analyze`:

```bash
export HF_TOKEN=hf_...   # or HUGGING_FACE_HUB_TOKEN
```

   Note: `HUGGINGFACE_TOKEN` is **not** read by `huggingface_hub` — use `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN`, or map it: `export HF_TOKEN="$HUGGINGFACE_TOKEN"`.

Or set `ocr_retry.signature_model` in `config.yaml` to a **local `.pt` path** (no HuggingFace download). To disable YOLO entirely: `ocr_retry.on_missing_signature: false`.

List targets anytime:

```bash
make help
```

## Where to put batch data

Batch mode reads **raw claim folders** under the config `data_dir` (default: `data/raw`).

```text
data/raw/
  claim 1/
    description.txt          # required — claim narrative
    answer.json              # ground truth (needed for evaluation)
    supporting1.md           # optional text/markdown support
    booking confirmation.png # optional image (webp/jpg/jpeg/png/pdf)
  claim 2/
    ...
```

Rules:

- Folder names must start with `claim` (e.g. `claim 1`, `claim 10`) so batch discovery finds them.
- Put **new** claims under `data/raw/` the same way, or change `preprocessing.data_dir` in `config.yaml`.
- Do **not** hand-edit `data/preprocessed/` or `data/results/` for input — those are pipeline outputs.


| Path (defaults)      | Role                                                                                           |
| -------------------- | ---------------------------------------------------------------------------------------------- |
| `data/raw/`          | Input claims for batch preprocess / analyze / evaluate                                         |
| `data/preprocessed/` | Mirrored artifacts after `make preprocess`                                                     |
| `data/results/`      | Predictions (`predicted_answer.json`), analysis (`analysis_result.json`), evaluation artifacts |


## Batch pipeline (make)

Run from the repo root. Models are pulled as needed before each stage.

```bash
# 1) Raw → preprocessed (+ optional predicted_answer.json)
make preprocess

# 2) Analyze preprocessed claims → evaluate (metrics + confusion matrix)
make analyze

# 3) Re-score only (predictions already on disk)
make evaluation
```

`make analyze` runs analysis on existing preprocessed data (run `make preprocess` first), then `make evaluation`. To analyze without eval:

```bash
uv run python src/main.py --config config.yaml --mode analyze
```

Single claim (same orchestration as the API):

```bash
uv run python src/main.py --config config.yaml --mode analyze --claim-id "claim 1"
```

Override config path or Ollama host if needed:

```bash
make analyze CONFIG=config.yaml
make analyze OLLAMA_HOST=127.0.0.1:11434
```

## Evaluation

`make analyze` already ends with evaluation. To re-score without re-running the pipeline (predictions in `data/results/claim N/predicted_answer.json`, ground truth in each raw `answer.json`):

```bash
make evaluation
```

Writes under `data/results/` (names from `config.yaml` → `evaluation:`):


| Artifact                                 | Default filename               |
| ---------------------------------------- | ------------------------------ |
| Metrics (accuracy, F1, confusion matrix) | `evaluation_metrics.json`      |
| Confusion matrix JSON                    | `confusion_matrix.json`        |
| Confusion matrix plot                    | `evaluation_visualization.png` |


Evaluation pairs **predictions** in `results_dir` with **answers** in `data_dir` by claim folder name.

## API server

```bash
make serve
```

Pulls all config models, then starts FastAPI on `http://127.0.0.1:8000` (OpenAPI docs at `/docs`).


| Method | Path                 | Purpose                                          |
| ------ | -------------------- | ------------------------------------------------ |
| `POST` | `/claims`            | Multipart submit → writes `data/raw/{claim_id}/` |
| `GET`  | `/claims/{claim_id}` | Preprocess + analyze one claim → decision JSON   |
| `GET`  | `/claims`            | List processed claims from `data/results/`       |


```bash
HOST=0.0.0.0 PORT=8080 RELOAD=0 make serve
```

## Tests & quality

```bash
make test              # fast lane: unit tests + import smoke + branch-coverage floor (integration deselected)
make test-integration  # opt-in only: needs provisioned data/raw + local Ollama; never runs in CI
make check             # lock + pre-commit + mypy
```

`make test` is the fast lane: unit tests plus public-package import smoke, with a branch coverage floor (`fail_under = 90` in `[tool.coverage.report]`). pyproject `addopts` deselects `integration`-marked tests for every bare pytest run (make, tox, CI) and uses `--strict-markers`. `make test-integration` is the only integration lane — it needs a provisioned `data/raw` and local Ollama, and it never runs in CI. In CI, the `fast-lane` job (import smoke, then mypy, then `make test` on py3.12) gates the py3.10–3.14 matrix, while `quality` (`make check`) runs in parallel.

## Algorithm design choices

**Goal:** similar claim types get the same classification stages, the same checkers, and the same deny/approve precedence — so decisions stay consistent across the batch.

### Why a typed graph (not a free-form agent)

1. **Coverage first, then a fixed branch** — After `classify_coverage`, edges are hard-coded. Trip cancellation always runs reason → cancel-document → checker; personal effects and missed departure each have one document stage then the same checker sink. The LLM does not invent a different procedure per claim.
2. **Shared `run_checker` sink** — Every document path joins one checker node. Gates that apply only to some docs (identity, signature on medical/hospital) are config-gated inside that node, not separate ad-hoc agents.
3. **One decision fold** — `_decision_from_state` applies a single ordered policy to the same flags (missing doc → identity → signature → healthy → contradicts → unclear → approve). Same flags ⇒ same decision and explanation string.
4. **LLM where it fits** — Models classify labels and run boolean checks; routing and precedence stay deterministic so “be consistent” is structural, not prompt-only.

### Cost management decisions

**Principle:** run free / cheap / deterministic steps first; call a model only when those miss or the cheap OCR path is unusable. All models run locally via Ollama. Analysis never re-runs OCR — it reads preprocessed text + metadata only.

**Preprocess OCR ladder** (per image/PDF, escalate only as needed):


| Step | Method                                             | Cost                    | When it runs                                                                                                                                                                                     |
| ---- | -------------------------------------------------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1    | Pillow format → PNG                                | free                    | Always (PDF passthrough)                                                                                                                                                                         |
| 2    | DCT **Benford** forensics                          | free / CPU              | Optional (`benford.enabled`; default **off** — too sensitive on synthetic take-home images)                                                                                                      |
| 3    | **Docling** layout + OCR                           | cheap (local)           | Primary text + `has_signature` from figure classification                                                                                                                                        |
| 4    | **ExtractionFailure**                              | free                    | Always after Docling — too short / too few words → `faulty_extraction` + HITL                                                                                                                    |
| 5    | Vision **OCR retry** (`Maternion/LightOnOCR-2:1b`) | one vision call         | **Text failure mode:** Docling weak/faulty (`faulty_extraction`, low conf, and/or HITL via `ocr_retry.on_`*) — re-OCR the image for usable markdown/text                                         |
| 6    | **YOLO signature detect**                          | one Ultralytics predict | **Signature failure mode:** Docling `has_signature: false` + `on_missing_signature` — detect handwritten signature boxes (not text). Needs `HF_TOKEN` or local `.pt` — **errors if unavailable** |


**Analysis: deterministic gates before any checker LLM:**


| Gate                            | Deterministic / cheap check                                                                           | Model only if…                                                     |
| ------------------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| Claim **containment**           | NFKC + casefold substring: claim text ⊆ document text                                                 | Containment miss                                                   |
| **Identity** (medical/hospital) | Booking `**name`** → full-name or **all tokens** in OCR (order-independent; strips `(partner)` notes) | Containment miss → LLM **name extraction** + lowercased Levenshtein ≤ `identity_max_edit_distance` |
| **Signature** (medical/hospital)| Read `has_signature` from `document_metadata.json` (Docling and/or vision verify above)               | No analysis-time vision call                                                                       |
| **Missing documentation**       | Classified doc code ∈ `required_documents` for that coverage/reason                                   | Config set-membership — not an LLM                                                                 |
| Graph routing / deny fold       | Hard-coded edges + ordered `_decision_from_state`                                                     | Never — topology is free                                                                           |


`contradicts` stays LLM-only (no reliable cheap proxy yet). Medical semantics (healthy, suspicious dating, identity, signature, authenticity, incomplete) are skipped on non-medical branches.

**Error-driven cheap checks** (accuracy first, then avoid unnecessary model spend):

- **Identity extract + edit distance** — the original full-text identity LLM (`match` / `mismatch` / `unclear`) was too brittle on OCR name noise; names are extracted then compared with Levenshtein (see below).
- `**Maternion/LightOnOCR-2:1b` OCR retry** — after empty / junk Docling text caused wrong document class → false `missing_documentation` (e.g. claim **5**). Vision re-OCR only when `ExtractionFailure` / low conf / HITL fire — fixes the **text** failure mode, not signatures.
- **YOLO signature detect** — after Docling figure-classifier false negatives on clear medical certs (claims **12**, **16**, …). Runs only when metadata said `has_signature: false` — fixes the **signature** failure mode; does not replace LightOn for text. Needs `HF_TOKEN` (or a local `.pt`); failure raises — no soft skip.
- **Benford default off** — deterministic fraud gate flagged almost all synthetic images; keeping it on would “save” model calls by early DENY but destroy accuracy on this dataset.

Full write-up, denial rules, and eval notes: `[LOGIC.md](LOGIC.md)`.

### Routing accuracy depends on preprocessing and the model

The coverage / reason / document **routing layer** only sees what preprocessing produced:

- OCR quality (`supporting_document.md`, confidence, signature metadata)
- Optional vision OCR retry when Docling is weak
- The **model** and **prompt** for each classifier stage in `config.yaml`

Garbage OCR → wrong document class → wrong branch or a false `missing_documentation` DENY. Improving routing therefore means fixing preprocess + prompts/models, not only the LangGraph edges.

### Numeric class codes (not long label strings)

Every classifier returns **numeric codes** (`"1"`, `"2"`, …) plus `**"False"`** when none of the positive classes apply or the model is uncertain (do not guess). Human-readable meanings live in `label_names` and in the prompt mapping. Config `other_label` is set to `"False"` (the previous `"None"` abstain token was removed) so routing and HITL share one abstention label.

That avoids accuracy loss when the model mangles a long English label token (extra words, translation drift, casing). The graph and `required_documents` key off the short codes; semantic names are resolved only when writing `analysis_result.json`.

### Identity checker: extract names + edit distance (not LLM match)

On cancellation medical/hospital docs, `identity_check` compares the booking passenger name to the OCR patient/subject name. The first version asked an LLM to return `match` / `mismatch` / `unclear` over the full booking + OCR text; that needed more accuracy on slight OCR / spelling variants (e.g. Piccirilly vs PICCIRILLI), so the check was redesigned:

1. Normalize (NFKC, casefold), strip parenthetical notes.
2. **Deterministic containment** — full booking name in OCR, or **all name tokens** present (order-independent); many clean OCR cases match with no LLM call. **Skipped** when the booking name has a role note such as `(partner)` / `(spouse)` (passenger is not assumed to be the patient).
3. On a miss (or after a skipped containment), the LLM **only extracts** names (`{"name": "..."}` / `{"name": null}`) from booking and document text — it does not decide identity.
4. Lowercased **Levenshtein** distance (full string and token-wise) ≤ `checking.identity_max_edit_distance` (default `3` in `config.yaml`) → match; no usable patient name → unclear; otherwise mismatch.

Mismatch → DENY; unclear patient field → UNCERTAIN; non-medical paths skip identity entirely.

Skipping `(partner)` containment does **not** skip the extract + edit-distance path: claim **6** can still **DENY** when the extracted passenger name mismatches the patient (and/or authenticity fires) if far-departure UNCERTAIN did not short-circuit first.

### Human-in-the-loop (`human_in_the_loop`)

Low-quality or abstaining cases are flagged so a **human operator** can review instead of trusting an automatic APPROVE/DENY. The boolean is written on:

- `document_metadata.json` (preprocess)
- `analysis_result.json` (analysis)
- `**predicted_answer.json**` (prediction — union of preprocess + analysis flags)

**What sets `human_in_the_loop: true`:**


| Stage                     | Trigger                                                                                                                                                                             |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Preprocess / OCR**      | Docling confidence below `preprocessing.confidence_threshold`                                                                                                                       |
| **Preprocess / OCR**      | `ExtractionFailure` — OCR text too short / too few words (`extraction_failure` rules)                                                                                               |
| **Preprocess / YOLO**      | Signature verify ran and max box confidence is missing or below `ocr_retry.signature_confidence` → HITL; score stored as `signature_probability`                                    |
| **Preprocess**            | Flag stored per document in `document_metadata.json` (may trigger optional `ocr_retry`); early `predicted_answer.json` (e.g. Benford DENY) copies HITL when any document is flagged |
| **Analyze / load**        | Any preprocessed document already has `human_in_the_loop: true` → carried into graph state                                                                                          |
| **Analyze / classifiers** | Any stage returns `**"False"`** (none of the positive classes / abstain) → HITL on analysis + prediction; metadata entries flipped to `true` on persist                             |
| **Analyze / checkers**    | Any checker path that resolves to **UNCERTAIN** (suspicious dating, far departure when enabled, `identity_unclear`, OCR failure) → HITL on analysis + prediction + metadata      |


Coverage-only `"False"` also routes to persist-only **UNCERTAIN** (`coverage_false_label`) and sets HITL. Checker **DENY** outcomes do not set HITL by themselves.

HITL is a **backup for weak OCR and signature detection**, not a label-error flag: many soft-correct DENYs still carry HITL when Docling confidence is low or YOLO cannot confirm ink above `signature_confidence`. With a **stronger OCR / vision model**, fewer pages would trip those preprocess gates, so an **expected reduction in `human_in_the_loop: true`** tags (without changing the DENY/APPROVE policy).

### When the pipeline returns `UNCERTAIN`

`_decision_from_state` emits **UNCERTAIN** (not APPROVE/DENY) in these cases — in order:

1. **Preprocess OCR failure** — `ocr_read_failure` / `ocr_failure` on document metadata.
2. **Coverage abstention** — coverage classifier returns `"False"` (none of the trip-cancellation / PE / missed-departure classes, or the model will not guess) → persist only, **no** reason/document/checkers (`coverage_false_label`).
3. **Far departure (optional)** — medical/hospital path when `|departure − today|` exceeds `checking.departure_uncertain_within_days` **and** `checking.departure_uncertain_enabled` is true (default **`false`** — gate exists but is off on this run).
4. **Suspicious dating** — OCR document dates look implausible vs booking/current date (`checker_suspicious_dating`: absolute month delta ≥ `suspicious_dating_max_month_delta` for future or issue/stamp-cued dates; only OCR dates within `suspicious_dating_consider_within_years` of today are considered — farther dates treated as DOB and ignored). Fires **before** DENY checkers.
5. **Identity unclear** — on a medical/hospital cancellation doc, booking vs OCR identity returns `unclear` (no usable patient/subject name field) **and** no hard DENY rule fired earlier (`identity_unclear`).

Date UNCERTAIN flags sit above DENY so a fired proximity/dating gate cannot fall through to signature/identity deny. With departure UNCERTAIN disabled, far-trip medical claims (e.g. claim **6**) can still reach identity/authenticity and DENY.

**HITL on UNCERTAIN:** every analysis **UNCERTAIN** (coverage abstention, suspicious dating, far departure, identity unclear, OCR failure) sets `human_in_the_loop: true` on `analysis_result.json`, `predicted_answer.json`, and `document_metadata.json`. Low OCR confidence / faulty extraction can also flag HITL even when the decision is DENY or APPROVE. That is intentional: **UNCERTAIN + human review is a desirable operating mode** for claims automation — the system should refuse to invent an APPROVE/DENY when evidence is thin, and hand the case to an operator instead of silently deciding.

### Analysis graph (checkers per branch)

```
START → load_artifacts → classify_coverage
                              │
  ┌───────────────────────────┼───────────────────────────┐
  │                           │                           │
  ▼                           ▼                           ▼
Trip cancellation        Personal Effects         Missed departure
  │                           │                           │
  classify_reason             │                           │
  │                           │                           │
  classify_cancel_document  classify_pe_document  classify_missed_document
  │                           │                           │
  └─────────────┬─────────────┴─────────────┬─────────────┘
                ▼                           │
          run_checker ◄─────────────────────┘
                │
                ▼
             persist → END

  other / unknown (False) ──► persist only (UNCERTAIN + HITL; no checkers)
```


| Branch                        | Checkers / gates                                                                                                                                                                                                |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Trip cancellation**         | `missing_documentation` (by reason); `containment` (info only); `contradicts`; `identity_check` / `identity_unclear` + `signature_check` **only** for medical certificate / hospital admission; `healthy_check` |
| **Personal Effects**          | `missing_documentation` (PE proof); `containment` (info); `contradicts`; `healthy_check`; identity & signature **skipped**                                                                                      |
| **Missed departure**          | `missing_documentation` (incident/booking); `containment` (info); `contradicts`; `healthy_check`; identity & signature **skipped**                                                                              |
| **other / unknown (`False`)** | none → **UNCERTAIN** + `human_in_the_loop`                                                                                                                                                                      |


### Preprocessing vs analysis


| Stage                              | Role                                                                                                                                                     |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Preprocess** (`make preprocess`) | Heterogeneous raw folders → uniform text + metadata under `data/preprocessed/` (OCR, optional vision retry; Benford off by default for synthetic images) |
| **Analyze** (`make analyze`)       | LangGraph on preprocessed text (no second OCR) → evaluation; run `make preprocess` first                                                                 |
| **Evaluate** (`make evaluation`)   | Re-score `predicted_answer.json` vs raw `answer.json` (also runs at end of `make analyze`)                                                               |


Prompts, label codes, `required_documents`, and checker models live in `[config.yaml](config.yaml)`.

## Fraud detection (Benford’s Law)

Optional image forensics run in **preprocessing** (before Docling), controlled by `benford.enabled` in `config.yaml` (default `**false`** for this take-home).

### Algorithm

Natural image / scan quantisation often follows **Benford’s Law**: the first significant digits (1–9) of many real-world magnitudes are not uniform — digit d appears with probability \log_{10}(1 + 1/d).

The pipeline’s `BenfordLawChecker`:

1. Load the document as **grayscale** PNG (after format conversion).
2. Split into blocks (`benford.block_size`, default 8) and apply a **2-D DCT** per block.
3. Take the **first significant digit** of each non-zero coefficient.
4. Compare the observed digit histogram to Benford’s expected curve with a **χ²** statistic.
5. If χ² > `benford.chi_squared_threshold` (default `15.51`) → **non-conformity**.

On non-conformity, `DocumentReader` early-returns a deny-style document (`DENY` / fraud) **without** running Docling, and may write an early `predicted_answer.json` under `results_dir`.

Re-enable for real scans:

```yaml
benford:
  enabled: true
  block_size: 8
  chi_squared_threshold: 15.51
```

## Results

### Claim decision quality (latest eval)

On the take-home set (`make analyze` → `make evaluation`; see `[LOGIC.md](LOGIC.md#error-analysis--remaining-errors-post-signature-verify)`):


| Metric                                                              | Latest           |
| ------------------------------------------------------------------- | ---------------- |
| Evaluator accuracy (includes GT `acceptable_decision` soft matches) | **~76%** (19 / 25) |
| Macro F1                                                            | **~0.70**        |
| Exact label match                                                   | **15 / 25**      |
| `human_in_the_loop` true / false                                    | **7 / 18**       |


**How to read this (desirable behaviour, not raw accuracy alone):**

- **DENY accuracy is high** — clear deny evidence (missing docs, healthy certs, identity mismatch, unsigned medical/hospital, authenticity) usually lands DENY when the coverage path runs.
- **APPROVE is conservative** — the pipeline rarely invents APPROVE. On this matrix there are **0** GT-UNCERTAIN → predicted APPROVE cases; remaining soft misses are mostly GT-APPROVE → DENY/UNCERTAIN or GT-UNCERTAIN → DENY (timing/dating gates do not always fire before identity/authenticity/signature DENYs).
- **UNCERTAIN + HITL is a feature** — coverage abstention (`"False"`) and low OCR confidence set `human_in_the_loop` so an operator reviews. HITL does **not** cover every soft miss: only 2 of 6 soft misses are HITL-flagged (see Error analysis).

Charts: `[data/results/evaluation_visualization.png](data/results/evaluation_visualization.png)`. Per-claim breakdown: `[LOGIC.md](LOGIC.md#evaluation-ground-truth-vs-predicted)`.

### Error analysis

Soft misses on the latest run (6): **5, 6, 12, 16, 19, 24**.

- **Claims 12 and 24 — ground truth label is wrong; true label is DENY.** The signature is either missing or so faint that it cannot be confirmed automatically and would need human verification. A predicted DENY is the correct outcome, so these count as errors only because of the GT label. Both are **HITL false** (OCR confidence mid/high, ~0.74–0.84).
- **Claim 5 — bad handwriting, routed to human in the loop.** The handwriting is poor enough that OCR will always get some characters wrong. Lowering the name-comparison threshold to tolerate those errors would raise the false positive rate for identity matches on every other claim. The threshold is therefore left as is, and this case is left to human-in-the-loop review (**HITL true**, confidence ~0.56; incomplete-document DENY path).
- **Claim 6 — timing UNCERTAIN off → identity / authenticity DENY.** Far-departure UNCERTAIN is disabled (`departure_uncertain_enabled: false`), so the claim reaches checkers. Booking name carries a `(partner)` role note (containment skipped), but extract + edit-distance still compares passenger vs patient and can **mismatch**; authenticity can also fire. Result: GT UNCERTAIN → predicted DENY (**HITL false**, confidence ~0.78).
- **Claim 16 — suspicious dating overfire.** `checker_suspicious_dating` (month-delta gate) returns UNCERTAIN on a GT APPROVE. OCR confidence is high (~0.84); with the checker-UNCERTAIN → HITL rule this case is flagged for review on re-analyze.
- **Claim 19 — beyond the models used in this take-home.** Authenticity (and related) DENY on a hard scan; **HITL true** (confidence ~0.65). Realistically needs a stronger model for this kind of document.

**HITL coverage of soft misses.** OCR-low soft misses (**5**, **19**) are HITL from preprocess. Checker **DENY** soft misses (**6**, **12**, **24**) stay HITL false (DENY does not auto-flag). Checker **UNCERTAIN** soft misses (e.g. **16** suspicious dating) now set HITL on analysis.

### Important improvement paths

Under take-home constraints, classifiers and OCR run as **small local Ollama models on a MacBook Air** (e.g. `qwen2.5:7b` text, `Maternion/LightOnOCR-2:1b` vision). That keeps the assignment reproducible offline, but it is also the main quality ceiling:

1. **Stronger OCR / vision models** — many remaining errors are still OCR: mangled patient names, missed ink signatures, empty/junk Docling text that pushes coverage to `"False"` or wrong document types. A stronger document OCR stack (cloud or larger local vision) would recover text and signatures that LightOn+Docling miss and would shrink both false UNCERTAIN abstentions and false DENYs.
2. **Stronger text models for coverage / checkers** — fewer spurious coverage-`"False"` routes and tighter healthy/contradicts judgements.
3. **Tune dating / timing gates** — suspicious dating is on (`suspicious_dating_max_month_delta`); far-departure UNCERTAIN exists but is off (`departure_uncertain_enabled: false`). Claim **6** still soft-misses via identity/authenticity DENY when timing does not short-circuit; claim **16** shows suspicious-dating overfire on GT APPROVE.

Until those land, **prefer UNCERTAIN + HITL over a wrong APPROVE** — that is the intended safety posture of this design.

### Fraud detection (Benford) on this dataset

We wired a DCT-based Benford's Law check into `DocumentReader` (PNG-first, before Docling). On non-conformity the pipeline early-returns `DENY` / reason `fraud` and writes `predicted_answer.json` under `results_dir` (default `data/results/`).

**Outcome on this dataset:** fraud detection does **not** work as expected. Every claim image in `data/` is synthetic / fabricated for the take-home. Quantisation / DCT coefficient distributions on fake imagery systematically deviate from Benford's curve, so the chi-squared gate flags almost all files as fraud — **too sensitive on synthetic data**.

**Config:** Benford is controlled by `benford.enabled` in `config.yaml` (default `false` for this project). Re-enable for real scanned certificates/photos where coefficient statistics are more meaningful (see [Fraud detection](#fraud-detection-benfords-law) above).

**Takeaway:** keep Benford as an optional real-data forensic signal; do not use it as a default deny rule against generated take-home imagery.

More eval detail (per-claim GT vs predicted): `[LOGIC.md](LOGIC.md#evaluation-ground-truth-vs-predicted)`.

## Config tips

Edit `[config.yaml](config.yaml)` for:

- `preprocessing.data_dir` / `preprocessed_dir` / `results_dir`
- `document_formats` (allowed image/PDF extensions)
- Ollama `model` names under `extraction`, `classification`, `checking`, `analysis`, `ocr_retry`
- `analysis.required_documents` / identity & signature required codes (which checkers apply on which docs)
- `checking.identity_max_edit_distance` (Levenshtein threshold after name extraction)
- `checking.departure_uncertain_enabled` / `departure_uncertain_within_days` (far-departure UNCERTAIN; default off)
- `checking.suspicious_dating_max_month_delta` / `suspicious_dating_consider_within_years` (dating UNCERTAIN gate)
- `benford.enabled` for optional DCT fraud check
- `preprocessing.confidence_threshold` / `extraction_failure` / `ocr_retry` (HITL and OCR quality)

`make evaluation` writes `human_in_the_loop_true` / `human_in_the_loop_false` into `data/results/evaluation_metrics.json` (and the evaluation PNG footer).
