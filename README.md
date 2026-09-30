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


| Pipeline stage                                          | Metric set | Accuracy / macro F1 | What changed                                          |
| ------------------------------------------------------- | ---------- | ------------------- | ----------------------------------------------------- |
| Coverage `"False"` abstention (before signature verify) | legacy soft | **48%** / ≈0.46    | Many true DENYs never reached signature/healthy gates |
| After YOLO signature verify                             | legacy soft | **68%** / ≈0.64    | Recovered signature FNs; +20 pts vs prior             |
| Current GT-first evaluator (`make analyze`) | `raw` / `policy` | **72%** / ≈0.64 · **80%** / ≈0.76 | Full coverage (25/25); HITL 16/9 (OCR/YOLO-only); hard policy misses ↓ to 5 |


LightOn still cannot fix every garbled medical scan (e.g. claim **5** OCR remains weak); YOLO removes the dominant Docling signature-miss DENYs but does not re-OCR text. See [Results](#results) for the current `raw`/`policy` breakdown.

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
| `data/results/`      | Predictions (`predicted_answer.json`), analysis (`analysis_result.json`), commit marker (`run_manifest.json`), evaluation artifacts |


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

`make analyze` already ends with evaluation. To re-score without re-running the pipeline:

```bash
make evaluation
```

The evaluated population is discovered from the **ground-truth tree** (`preprocessing.data_dir`): every claim folder whose `answer.json` is readable and whose decision is in `evaluation.labels` enters the denominator. A claim with ground truth and **no prediction** (no results folder, or a results folder without `predicted_answer.json`) is counted as **incorrect**, not skipped. `coverage_rate` is `n_scored / n_ground_truth` — the scored share of that population.

Two named metric sets are reported over that same population:

- **`raw`** — exact decision equality (`prediction == ground_truth`).
- **`policy`** — also credits a prediction equal to a non-nan `acceptable_decision`, remapped onto the true label for the matrix.

Accuracy and macro F1 for each named set are derived from one confusion matrix whose columns are the configured labels **plus** the unscored column (`evaluation.unscored_label`, default `NO_PREDICTION`). Predictions with no ground-truth folder are reported as unmatched and appear in no metric.

Writes under `data/results/` (names from `config.yaml` → `evaluation:`):


| Artifact                                 | Default filename               |
| ---------------------------------------- | ------------------------------ |
| Metrics (population, raw/policy, outcomes) | `evaluation_metrics.json`    |
| Confusion matrix JSON (both named matrices) | `confusion_matrix.json`     |
| Confusion matrix plot (raw matrix)       | `evaluation_visualization.png` |


The metrics JSON carries a `population` block (including `coverage_rate`), per-claim `outcomes`, and both named metric blocks. Pairing is ground-truth-driven; predictions without a ground-truth folder are unmatched.

## API server

```bash
make serve
```

Pulls all config models, then starts FastAPI on `http://127.0.0.1:8000` (OpenAPI docs at `/docs`).


| Method | Path                          | Purpose                                                                 |
| ------ | ----------------------------- | ----------------------------------------------------------------------- |
| `POST` | `/claims`                     | Multipart submit → writes `data/raw/{claim_id}/`                        |
| `POST` | `/claims/{claim_id}/analysis` | Preprocess + analyse one claim under a per-claim lock → decision JSON   |
| `GET`  | `/claims/{claim_id}`          | Read the published decision from `data/results/` (never writes or LLMs) |
| `GET`  | `/claims`                     | List processed claims from `data/results/`                              |


Analysis is synchronous and triggered only by `POST /claims/{claim_id}/analysis`. The decision GET is a pure read of the published generation: it never writes artifacts and never calls OCR or the LLM. It returns `404` (`analysis_not_found`) when nothing has been analysed yet, and `409` with a reason code (`invalid_json`, `run_id_missing`, `run_id_mismatch`, or `artifact_missing`) when the stored generation is unparseable or disagrees with its `run_manifest.json`. The analysis POST holds an exclusive per-claim lock keyed on `claim_id` alone, so a second concurrent request for the same claim is refused with `409` (`analysis_in_progress`) rather than queued or duplicated; a repeat POST after completion re-runs the analysis. `GET /claims` stays `200` when an artifact is unreadable and reports the reason per item under `errors` (same reason codes). **Breaking change:** clients that previously called the decision GET to produce a decision must now call the analysis POST first.

`POST /claims` intake is bounded by `api.upload.max_file_bytes` (25 MiB per part) and `api.upload.max_request_bytes` (50 MiB total) in `config.yaml`. A request whose declared `Content-Length` already exceeds the total cap is refused before the multipart body is parsed. A part or request that streams past either cap returns `413` with `file_too_large` or `request_too_large`, and leaves no claim folder under `data_dir`.

Claim ids must be single path segments. A claim directory that is a symlink is rejected rather than followed (analysis POST returns `422`; CLI `--claim-id` exits `1`). Batch discovery skips such entries with a warning instead of processing them. Configured artifact filenames under `preprocessing.artifacts` and `evaluation` must be plain basenames — otherwise config load fails.

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

1. **Coverage first, then a fixed branch** — After `classify_coverage`, the winner is chosen once (highest probability among selected labels; ties by configured label order) and mapped through **named** `analysis.coverage.branches` (`"1"` → cancellation, `"2"` → personal_effects, `"3"` → missed_departure). Edges are then hard-coded. Trip cancellation always runs reason → cancel-document → checker; personal effects and missed departure each have one document stage then the same checker sink. Reordering the labels list cannot silently remap a code to another branch.
2. **Shared `run_checker` sink** — Every document path joins one checker node. An explicit per-coverage **rule set** gates medical semantics (healthy, suspicious dating, identity, signature, incomplete, departure); non-medical PE / missed / police / jury paths skip those checks and record them as `checker_skipped`.
3. **One decision fold** — `compliance.policy.decision.decision_from_state` folds typed `CheckOutcome` values (`PASS` \| `VIOLATION` \| `ABSTAIN` \| `ERROR`) with one ordered policy: OCR failure / coverage abstention / dating UNCERTAIN → hard VIOLATION DENY (missing doc, identity, signature, healthy, contradicts; incomplete only when OCR is clean) → incomplete VIOLATION alone under OCR HITL → UNCERTAIN → checker ERROR UNCERTAIN → APPROVE. Soft incomplete never masks unsigned / other hard DENYs. Same outcomes ⇒ same decision and explanation. Analysis policy lives in `compliance/policy/`; `ClaimPipeline` is thin LangGraph orchestration over it.
4. **LLM where it fits** — Models classify labels and run boolean checks; routing and precedence stay deterministic so “be consistent” is structural, not prompt-only. Checker chat transport failures retry via `checking.transport_retry`, then record `ERROR` (claim still gets UNCERTAIN instead of being skipped).

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
| **Missing documentation**       | Classified doc code ∈ `required_documents` for that coverage/reason. On **missed-departure**, if the claim description **mentions medical**, only `missed_departure_medical_codes` are acceptable (booking/incident alone → DENY) | Config set-membership — not an LLM                                                                 |
| Graph routing / deny fold       | Hard-coded edges + ordered `decision_from_state` (incl. OCR-aware incomplete soft polarity)           | Never — topology is free                                                                           |


`contradicts` stays LLM-only (no reliable cheap proxy yet). Medical semantics (healthy, suspicious dating, identity, signature, incomplete, departure) run when the rule set marks them applicable:

- **Cancellation** — when classified document codes hit `identity_required_codes` / `signature_required_codes` (medical certificate / hospital admission)
- **Missed departure** — when classified codes hit `missed_departure_medical_codes` (`"3"`)
- **PE / non-medical cancel / non-medical missed** — skipped (`checker_skipped`)

Separately, on missed-departure a **medical mention in the description** narrows *acceptable* docs to those medical codes even if the classified doc is only booking/incident → `checker_missing_documentation` DENY (claim-**2** shape). That does not by itself open the medical gated checkers.

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

Every classifier returns **numeric codes** (`"1"`, `"2"`, …) plus `**"False"`** when none of the positive classes apply or the model is uncertain (do not guess). Human-readable meanings live in `label_names` and in the prompt mapping. Config `other_label` is set to `"False"` (the previous `"None"` abstain token was removed) so routing shares one abstention label (UNCERTAIN; not HITL by itself).

Coverage routing uses an explicit `analysis.coverage.branches` map (not list position). Config load **fails hard** on unknown keys, duplicate labels, and broken `required_documents` / taxonomy cross-refs.

That avoids accuracy loss when the model mangles a long English label token (extra words, translation drift, casing). The graph and `required_documents` key off the short codes; semantic names are resolved only when writing `analysis_result.json`.

### Identity checker: extract names + edit distance (not LLM match)

On cancellation medical/hospital docs, `identity_check` compares the booking passenger name to the OCR patient/subject name. The first version asked an LLM to return `match` / `mismatch` / `unclear` over the full booking + OCR text; that needed more accuracy on slight OCR / spelling variants (e.g. Piccirilly vs PICCIRILLI), so the check was redesigned:

1. Normalize (NFKC, casefold), strip parenthetical notes.
2. **Deterministic containment** — full booking name in OCR, or **all name tokens** present (order-independent); many clean OCR cases match with no LLM call. **Skipped** when the booking name has a role note such as `(partner)` / `(spouse)` (passenger is not assumed to be the patient).
3. On a miss (or after a skipped containment), the LLM **only extracts** names (`{"name": "..."}` / `{"name": null}`) from booking and document text — it does not decide identity.
4. Lowercased **Levenshtein** distance (full string and token-wise) ≤ `checking.identity_max_edit_distance` (default `3` in `config.yaml`) → match; no usable patient name → **DENY** (unverifiable); otherwise mismatch.

Mismatch or unextractable patient name → DENY (`VIOLATION`); unparseable extraction or transport failure → UNCERTAIN (`ERROR` / `checker_error:identity`). Non-medical paths skip identity entirely.

Skipping `(partner)` containment does **not** skip the extract + edit-distance path: claim **6** can still **DENY** when the extracted passenger name mismatches the patient if far-departure UNCERTAIN did not short-circuit first.

### Human-in-the-loop (`human_in_the_loop`)

HITL is **only** for uncertain **OCR or YOLO signature** detection — not for classifier abstention or analysis UNCERTAIN/DENY outcomes. The boolean is written on:

- `document_metadata.json` (preprocess owns this file)
- `analysis_result.json` / `predicted_answer.json` (carry preprocess HITL; `human_in_the_loop_source` is `preprocess_metadata` or `none`)

Analysis publishes `analysis_result.json` + `predicted_answer.json` atomically under a `run_id` with `run_manifest.json` as the commit marker; a prediction that disagrees with its manifest is not scored.

**What sets `human_in_the_loop: true`:**


| Stage                 | Trigger                                                                                                                                          |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Preprocess / OCR**  | Docling confidence below `preprocessing.confidence_threshold`                                                                                    |
| **Preprocess / OCR**  | `ExtractionFailure` — OCR text too short / too few words (`extraction_failure` rules)                                                            |
| **Preprocess / OCR**  | OCR read/retry hard failure (`ocr_failure` / `ocr_read_failure`)                                                                                 |
| **Preprocess / YOLO** | Signature verify ran and found no boxes → HITL; any box score → `has_signature` (score stored as `signature_probability`) |
| **Analyze / load**    | Any preprocessed document already has `human_in_the_loop: true` → carried into analysis + prediction (`human_in_the_loop_source=preprocess_metadata`) |


**Not HITL:** coverage/document `"False"`, far departure, suspicious dating, `identity_unclear`, checker `ERROR`, or other analysis UNCERTAIN/DENY paths. Those stay machine decisions without forcing operator review.

HITL is a backup for weak OCR and signature detection. Stronger OCR / vision models should reduce `human_in_the_loop: true` without changing the DENY/APPROVE/UNCERTAIN policy.

### When the pipeline returns `UNCERTAIN`

`decision_from_state` emits **UNCERTAIN** (not APPROVE/DENY) in these cases — in order:

1. **Preprocess OCR failure** — `ocr_read_failure` / `ocr_failure` on document metadata.
2. **Coverage abstention** — coverage classifier returns `"False"` (none of the trip-cancellation / PE / missed-departure classes, or the model will not guess) → persist only, **no** reason/document/checkers (`coverage_false_label`).
3. **Far departure** — medical/hospital path when an **upcoming** departure is strictly more than `checking.departure_uncertain_within_days` ahead of reference today **and** `checking.departure_uncertain_enabled` is true (default **on**; past flights continue through checkers). Ranks before identity DENY.
4. **Suspicious dating** — OCR document dates look implausible vs booking/current date (`checker_suspicious_dating`: absolute month delta ≥ `suspicious_dating_max_month_delta` for future or issue-cued dates; only OCR dates within `suspicious_dating_consider_within_years` of today are considered; birth/DOB cues from `checking.dob_cues` drop a date even inside that window; bare image `Stamp` labels are ignored unless listed under `issue_date_cues`). Issue/care wording comes from config vocabularies (`checking.issue_date_cues`, `checking.care_window_cues`) — accent-insensitive phrase match, not a mega-regex. Medical-gated; fires **before** DENY checkers.
5. **Incomplete + OCR HITL (alone)** — `checker_incomplete_document` VIOLATION when preprocess already flagged OCR/YOLO uncertainty **and** no hard DENY remains → **UNCERTAIN** (not DENY). Clean OCR keeps incomplete as DENY (e.g. claim 7). Unsigned / identity / healthy / contradicts still **DENY** and strip incomplete from the explanation under OCR HITL (soft incomplete must not mask signature DENY).
6. **Checker ERROR** — malformed LLM checker output, or chat transport failure after `checking.transport_retry` retries → **UNCERTAIN** `checker_error:<modes>` (a genuine hard `VIOLATION` from another checker still wins DENY). Containment ERROR is record-only.
7. **Identity ERROR** — on a medical/hospital cancellation doc, identity extraction failed (`ERROR`) and no hard DENY rule fired earlier (`checker_error:identity` / legacy `identity_unclear`).

Date UNCERTAIN flags sit above DENY so a fired proximity/dating gate cannot fall through to signature/identity deny. Far-departure is **enabled** for upcoming flights beyond `departure_uncertain_within_days` (past flights continue through checkers).

**HITL vs UNCERTAIN:** analysis UNCERTAIN (coverage abstention, dating gates, checker `ERROR`, identity unclear) does **not** by itself set HITL. HITL remains only when preprocess OCR/YOLO already flagged uncertainty (see above). OCR failure still sets both UNCERTAIN and HITL because preprocess owns that flag.

### Analysis graph (checkers per branch)

LangGraph topology (coverage → document stage → shared checker sink):

```
START → load_artifacts → classify_coverage
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
          ▼                   ▼                   ▼
   Trip cancellation    Personal Effects    Missed departure
          │                   │                   │
   classify_reason            │                   │
          │                   │                   │
   classify_cancel_doc  classify_pe_doc   classify_missed_doc
          │                   │                   │
          └─────────┬─────────┴─────────┬─────────┘
                    ▼                   │
              run_checker ◄─────────────┘
                    │
                    ▼
               persist → END

  coverage "False" ──► persist only (UNCERTAIN coverage_false_label;
                       no reason/doc/checkers; HITL only if OCR/YOLO flagged)
```

Inside `run_checker` (policy engine — rule set, date gates, then LLM / metadata checks; missing-doc is decided later in the fold):

```
run_checker
  │
  ├─ rule_set_for_claim(branch, classified document codes)
  │     cancellation_medical        — cancel doc ∈ identity/signature required codes
  │     cancellation_non_medical    — police / jury / other non-medical cancel docs
  │     missed_departure_medical    — missed doc ∈ missed_departure_medical_codes
  │     missed_departure_non_medical— incident report / proof of booking
  │     personal_effects_non_medical— PE proof only
  │
  ├─ if departure / suspicious_dating in rule_set.applicable:
  │     departure_within_days?  ──yes──► flag UNCERTAIN (skip LLM checkers)
  │     suspicious_dating?      ──yes──► flag UNCERTAIN (skip LLM checkers)
  │
  ├─ always when LLM checkers run:
  │     containment · contradicts
  │
  ├─ if in rule_set.applicable:
  │     identity · signature (preprocess has_signature) · healthy · incomplete
  │
  └─ decision_from_state (precedence):
        1. OCR failure            → UNCERTAIN
        2. coverage False         → UNCERTAIN coverage_false_label
        3. departure_within_days  → UNCERTAIN
        4. suspicious_dating      → UNCERTAIN
        5. hard VIOLATION DENY:
             missing_documentation | identity | signature | healthy
             | incomplete (clean OCR only) | contradicts
             (soft incomplete never masks signature / other hard DENYs)
        6. incomplete + OCR HITL (alone) → UNCERTAIN checker_incomplete_document
        7. checker ERROR          → UNCERTAIN checker_error:<modes>
        8. identity_unclear       → UNCERTAIN
        9. else                   → APPROVE checker_consistent
```


| Branch / rule set | What runs | Notable deny / uncertain rules |
| ----------------- | --------- | ------------------------------ |
| **Trip cancellation · medical** (`cancellation_medical`) | `containment`; `contradicts`; gated: `departure` / `suspicious_dating` (UNCERTAIN early-exit) then `identity` / `signature` / `healthy` / `incomplete` | Missing doc vs `cancellation_by_reason`; incomplete DENY if OCR clean, else UNCERTAIN under OCR HITL |
| **Trip cancellation · non-medical** (police / jury / …) | `containment`; `contradicts` only — medical semantics in `checker_skipped` | Missing doc vs reason-mapped acceptable codes |
| **Personal Effects** (`personal_effects_non_medical`) | `containment`; `contradicts` — medical semantics **skipped** | PE `missing_documentation`; cannot DENY solely for healthy/dating/identity/signature |
| **Missed departure · medical** (`missed_departure_medical`) | Same gated medical set as cancellation medical when document code ∈ `missed_departure_medical_codes` | Full medical deny / dating path |
| **Missed departure · non-medical** (`missed_departure_non_medical`) | `containment`; `contradicts` only — healthy/identity/signature/incomplete/dating **skipped** | Acceptable docs = incident / booking / medical. **If description mentions medical**, acceptable narrows to medical codes only → booking/incident alone **DENY** `checker_missing_documentation` (claim **2**) |
| **other / unknown (`False`)** | none → persist only | **UNCERTAIN** `coverage_false_label` (HITL only if OCR/YOLO already flagged) |

`checker_missing_documentation` is computed in the decision fold from classified codes vs `required_documents` (plus the missed-departure medical-mention narrowing above) — it is not an LLM checker.

Each claim that reaches `run_checker` records `checker_rule_set` and `checker_skipped` in `analysis_result.json`.


### Preprocessing vs analysis


| Stage                              | Role                                                                                                                                                     |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Preprocess** (`make preprocess`) | Heterogeneous raw folders → uniform text + metadata under `data/preprocessed/` (OCR, optional vision retry; Benford off by default for synthetic images) |
| **Analyze** (`make analyze`)       | LangGraph on preprocessed text (no second OCR) → evaluation; run `make preprocess` first                                                                 |
| **Evaluate** (`make evaluation`)   | Re-score `predicted_answer.json` vs raw `answer.json` (also runs at end of `make analyze`)                                                               |


Prompts, label codes, `analysis.coverage.branches`, `required_documents`, and checker models live in `[config.yaml](config.yaml)`. Policy logic lives in `src/compliance/policy/`.

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

From `make analyze` / `evaluation_metrics.json` (GT-first population; latest scored run):


| Metric | Value |
| ------ | ----- |
| Population / coverage | **25 / 25** scored (`coverage_rate` **1.0**) |
| **`raw`** accuracy / macro F1 | **72%** (18 / 25) / **≈0.64** |
| **`policy`** accuracy / macro F1 | **80%** (20 / 25) / **≈0.76** |
| `human_in_the_loop` true / false | **16 / 9** (scored predictions; OCR/YOLO-only) |


These figures are **in-sample**: the same 25 claims drove the error analysis and the threshold tweaks, so they are not a held-out result. A false APPROVE is worse than a false DENY, which is why perfect DENY recall with leftover signature false DENYs is the acceptable shape.

`raw` = exact label match. `policy` also credits a non-nan GT `acceptable_decision` (this run: soft credits on **20**, **23** — both `acceptable_decision=DENY`). Re-score without re-analysis:

```bash
make evaluation
```

**How to read this (desirable behaviour, not raw accuracy alone):**

- **DENY accuracy is high** — clear deny evidence (missing docs, healthy medical certs, identity mismatch, unsigned medical/hospital) usually lands DENY when the medical path runs.
- **APPROVE is conservative** — the pipeline rarely invents APPROVE. Non-medical evidence cannot be denied solely for medical semantics (healthy / dating / identity / signature).
- **Missed-departure medical mention** — a medical cue in the claim text requires a medical supporting doc; booking/incident alone DENYs `checker_missing_documentation` (claim **2**).
- **Incomplete is OCR-aware** — incomplete VIOLATION + preprocess OCR/YOLO HITL → UNCERTAIN (not DENY), e.g. claim **19**; clean OCR still DENYs incomplete.
- **HITL is OCR/YOLO only** — coverage abstention, dating gates, and checker `ERROR` stay machine UNCERTAIN without forcing review; low OCR / uncertain signature still set HITL.
- **Dating gate recovered** — claim **13** now fires `checker_suspicious_dating` → UNCERTAIN (matches GT; was a prior hard miss).

Charts: `[data/results/evaluation_visualization.png](data/results/evaluation_visualization.png)`. Per-claim breakdown: `[LOGIC.md](LOGIC.md#evaluation-ground-truth-vs-predicted)`.

### Error analysis

**`raw` misses (7):** **5, 12, 16, 19, 20, 23, 24**. Of those, **20** and **23** are **`policy` credits** (`acceptable_decision=DENY`). **Hard policy misses (5):** **5, 12, 16, 19, 24**. All five hard misses carry preprocess **HITL true** (OCR/YOLO).

| Claim | GT → pred | Explanation (artifact) | Residual mode | Possible fixes |
| ----- | --------- | ---------------------- | ------------- | -------------- |
| **5** | APPROVE → **DENY** | `identity_check` (OCR names garbled; containment ABSTAIN; incomplete also VIOLATION) | Identity FN on weak OCR | Stronger primary/retry OCR; keep extract+edit-distance but lower false DENY when HITL (e.g. identity ABSTAIN→UNCERTAIN under OCR HITL); DSPy name-extract prompts |
| **12** | APPROVE → **DENY** | `signature_check` + `checker_contradicts` (`has_signature=false`, YOLO used, `sig_p=nan`) | Signature FN + contradicts FP | Domain fine-tune / second-pass signature detect on medical scans; stronger contradicts prompt or require higher confidence before VIOLATION; HITL already set — operator review |
| **16** | APPROVE → **DENY** | `signature_check` only (`has_signature=false`, YOLO used, low `sig_p≈0.10`) | Signature FN (low-conf / no-accept box) | Treat low YOLO score as UNCERTAIN+HITL instead of hard DENY; calibrate `signature_probability` on held-out; vision “signed?” check when YOLO empty/low |
| **19** | APPROVE → **UNCERTAIN** | `checker_incomplete_document` alone under OCR HITL | Soft-incomplete overfire | Stronger OCR so incomplete checker sees full fields; tighten incomplete prompt; held-out threshold on when incomplete may fire under HITL |
| **24** | UNCERTAIN → **DENY** (`acceptable=APPROVE`) | `signature_check` (`has_signature=false`, `sig_p=nan`) | Signature FN (hard; soft-APPROVE GT) | Same as **16**/signature column; soft policy already wants APPROVE — signature false negative is the blocker |
| **20** | UNCERTAIN → **DENY** | `identity_check` + `signature_check` | Soft-ok DENY (`acceptable=DENY`) | No hard fix required for policy metric; still HITL — useful for threshold/signature calibration on val |
| **23** | UNCERTAIN → **DENY** | `signature_check` | Soft-ok DENY (`acceptable=DENY`) | Same as **20** — policy credit; residual still teaches signature FN rate |

**Fixed since prior write-up (not misses):** **13** dating UNCERTAIN via cues; **14** coverage routes and healthy DENY.

**HITL on hard misses:** **5, 12, 16, 19, 24** (all). No machine-only hard misses in this run.

### Important improvement paths

Under take-home constraints, classifiers and OCR run as **small local Ollama models on a MacBook Air** (e.g. `qwen2.5:7b` text, `Maternion/LightOnOCR-2:1b` vision). That keeps the assignment reproducible offline, but it is also the main quality ceiling:

1. **Stronger OCR / vision models** — remaining hard misses are dominated by **OCR + signature**: mangled patient names (**5**), incomplete fields under HITL (**19**), missed ink (**12**, **16**, **24**). A stronger document OCR stack (and/or signature domain fine-tune) would shrink false DENYs and HITL volume.
2. **Stronger text models for coverage / checkers** — tighter `contradicts` / `incomplete` / identity-extract judgements (claim **12** dual deny; **19** incomplete). Coverage `"False"` abstention is largely fixed on this batch but remains a risk under weak OCR.
3. **Tune dating / timing gates + held-out thresholds** — suspicious dating recovered claim **13** via cue lists. Signature / identity / incomplete behaviour still needs **val sweeps + held-out lock** (`identity_max_edit_distance`, YOLO score→UNCERTAIN vs DENY, incomplete under HITL).
4. **Cue-list maintenance vs LLM date-role extraction** — lexical vocabularies in `config.yaml` are fine while small. If they grow into a multilingual catalogue, prefer extracting structured `issue_date` / `care_start` / `care_end` with an LLM and comparing roles deterministically. Tradeoff: that fallback is **non-deterministic** (model/prompt drift) versus today’s stable phrase match. Same story for `analysis.medical_mention_cues`. Still hardcoded elsewhere (candidates for the same pattern): Docling `_PERSON_KEYS` / `_DATE_KEYS` in `document.py`, figure-noise tokens in `extraction_failure.py`, markdown field aliases.

Until those land, **prefer UNCERTAIN over a wrong APPROVE**; reserve HITL for OCR/YOLO uncertainty so operators are not flooded.

### Fraud detection (Benford) on this dataset

We wired a DCT-based Benford's Law check into `DocumentReader` (PNG-first, before Docling). On non-conformity the pipeline early-returns `DENY` / reason `fraud` and writes `predicted_answer.json` under `results_dir` (default `data/results/`).

**Outcome on this dataset:** fraud detection does **not** work as expected. Every claim image in `data/` is synthetic / fabricated for the take-home. Quantisation / DCT coefficient distributions on fake imagery systematically deviate from Benford's curve, so the chi-squared gate flags almost all files as fraud — **too sensitive on synthetic data**.

**Config:** Benford is controlled by `benford.enabled` in `config.yaml` (default `false` for this project). Re-enable for real scanned certificates/photos where coefficient statistics are more meaningful (see [Fraud detection](#fraud-detection-benfords-law) above).

**Takeaway:** keep Benford as an optional real-data forensic signal; do not use it as a default deny rule against generated take-home imagery.

More eval detail (per-claim GT vs predicted): `[LOGIC.md](LOGIC.md#evaluation-ground-truth-vs-predicted)`.

## Future work

This take-home established a library of **primitive operators** — coverage / reason / document classifiers, deterministic gates (dating, departure, signature, missing docs), and LLM checkers (identity, healthy, incomplete, contradicts) — wired into a typed LangGraph. Building those nodes and the branch topology was necessarily **manual**: the hard problem was inventing reliable operators and folding them into a fixed decision order.

That manual phase does not scale for sequencing. Hand-tuning which nodes run where from error analysis alone will keep chasing residual misses. Future work should treat the graph as something to **search and score against a ground-truth dataset** (in the spirit of agent gyms / environment-driven optimization):

1. **Scale the dataset and hold out for generalization** — today’s numbers are on **N ≈ 25** claims that also drove error analysis and config/threshold iteration, so reported `raw` / `policy` gains can overfit this batch. Collect **more labeled samples** and keep a locked **held-out** split (tune / search / threshold-fit only on train+val; report once on test). That is also how to **set and validate thresholds** properly — `identity_max_edit_distance`, dating month deltas, coverage / signature probability cutoffs, OCR confidence / HITL floors — by sweeping on val and confirming the chosen values do not degrade held-out accuracy or false-DENY rate.
2. **Optimize graph structure with grammar-guided genetic programming (TPOT’s algorithm family, not TPOT itself)** — The algorithm family is applicable. [TPOT](https://github.com/EpistasisLab/tpot) itself is not the same search. Genetic programming over a typed operator set, scored on held-out labels, is the right idea for this graph. TPOT’s sklearn pipelines are only the analogy.

   TPOT evolves three things at once: which operators appear, in what order, and with which hyperparameters. It keeps the individuals that score best on held-out data. Those three genes map onto this system:

   | TPOT gene | Claim-graph counterpart |
   | --- | --- |
   | Which operators | Which classifiers, gates, and checkers run |
   | Order | Which coverage branch they sit on, and what they may skip |
   | Hyperparameters | Edit distance, signature threshold, month delta, HITL polarity |
   | Fitness | `policy` accuracy and false-DENY rate on held-out claims |

   What does not transfer is the representation. TPOT assumes a tree of tabular estimators and cheap deterministic cross-validation. This graph is branching control-flow (a dating gate that fires skips later DENYs), so legality has to be a grammar — coverage before checkers, medical gates only on medical branches, decision precedence fixed or narrowly mutable — not TPOT’s sklearn primitive set. Each candidate is also expensive and noisy (LLM nodes), so fitness needs frozen preprocess artifacts, temperature 0 or repeated trials, and enough claims that a one-claim swing is not the signal. Keep the fittest legal graphs.
3. **Optimize individual module prompts with DSPy + GEPA** — treat each classifier / checker prompt as its own task, trained on labeled (or synthetic) examples with [DSPy](https://dspy.ai/) and the **GEPA** optimizer (`dspy.GEPA`, Genetic-Pareto), so node quality is tuned independently of graph search. GEPA is the default prompt-optimization path here (not MIPROv2 / BootstrapFewShot unless comparing). The EA then composes already-strong operators rather than compensating for weak prompts by topology alone.
4. **Human-diagnose irreducible residuals** — after the best graph is selected, inspect remaining errors via `analysis_result.json`: classifier probability margins that want thresholds, abstention patterns, checker outcomes that never fire when GT says they should, or failure modes the current module set does not represent. That is where a person goes deep — new operators, cue lists, OCR/HITL policy, or dataset/label fixes.

The intended loop: **grow + split data → DSPy-tune operators → fit thresholds on val → evolve the graph → evaluate once on held-out GT → human-diagnose residuals from structured artifacts → add or retune primitives → search again.** Operators stay explicit and auditable; pipeline construction becomes data-driven rather than one-off redesign from each error table.

## Config tips

Edit `[config.yaml](config.yaml)` for:

- `api.upload.max_file_bytes` / `max_request_bytes` (multipart intake caps; defaults 25 MiB / 50 MiB)
- `preprocessing.data_dir` / `preprocessed_dir` / `results_dir`
- `document_formats` (allowed image/PDF extensions)
- Ollama `model` names under `extraction`, `classification`, `checking`, `analysis`, `ocr_retry`
- `analysis.coverage.branches` (named label → branch map; unknown keys / bad cross-refs fail at load)
- `analysis.required_documents` / identity & signature required codes (which medical checkers apply on which docs)
- `checking.transport_retry` (checker chat retries before `ERROR` → UNCERTAIN)
- `checking.identity_max_edit_distance` (Levenshtein threshold after name extraction)
- `checking.departure_uncertain_enabled` / `departure_uncertain_within_days` (upcoming far-departure UNCERTAIN; default on)
- `checking.suspicious_dating_max_month_delta` / `suspicious_dating_consider_within_years` (dating UNCERTAIN gate; medical-gated)
- `checking.issue_date_cues` / `care_window_cues` / `dob_cues` (dating lexical vocabulary; keep small or plan LLM date-role extraction)
- `analysis.medical_mention_cues` (missed-departure medical-narrative narrowing)
- `evaluation.unscored_label` (matrix column for missing predictions; default `NO_PREDICTION`)
- `benford.enabled` for optional DCT fraud check
- `preprocessing.confidence_threshold` / `extraction_failure` / `ocr_retry` (HITL and OCR quality)

`make evaluation` writes population / `raw` / `policy` metrics and HITL counts into `data/results/evaluation_metrics.json` (and the evaluation PNG footer). HITL counts are over **scored** predictions only.
