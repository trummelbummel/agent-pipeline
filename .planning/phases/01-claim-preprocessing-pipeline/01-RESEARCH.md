# M001 Research — Claim Preprocessing Pipeline

## Architecture (locked — D004/D005/D006)

```
src/compliance/
  models/claim.py          # Pydantic schemas (maximal fields, missing → np.nan)
  config/settings.py       # load_config() → preprocessing + extraction settings
  preprocessing/
    reader.py              # Reader ABC
    preprocessing.py       # Preprocessor ABC + FormatConverter (→ PNG)
    answer.py              # AnswerReader + AnswerPreprocessor
    markdown.py            # MarkdownReader + MarkdownPreprocessor (key normalize/translate)
    description.py         # DescriptionReader + DescriptionPreprocessor
    document.py            # DocumentReader (Docling) + DocumentPreprocessor
    extractor.py           # InformationExtractor (LLM → Pydantic)
    pipeline.py            # discover claim folders, dispatch readers, write processed.json
```

- **Reader ABC** (`reader.py`): extensible; each subclass `read(path) -> PydanticModel`, calling its Preprocessor.
- **Preprocessor ABC** (`preprocessing.py`): format-specific normalization before model construction.
- **FormatConverter** (`preprocessing.py`): converts configured document formats to PNG **before** Docling; PNG inputs pass through unchanged.
- **InformationExtractor**: `(model_schema, llm_model, prompt)` from config; extracts structured fields from free text into a target Pydantic model (used by DescriptionReader against the BookingData schema).

## Data Structure Analysis

### Claim folder layout
Each `data/claim N/` folder contains a variable set of files:

| File | Count | Format | Reader |
|------|-------|--------|--------|
| `description.txt` | 25/25 | Free-text customer letter | DescriptionReader + InformationExtractor |
| `answer.json` | 25/25 | Ground truth JSON | AnswerReader |
| `supporting1.md` / `internal *.md` | 18+7/25 | Markdown key-value booking | MarkdownReader |
| Remaining docs (`.webp/.jpg/.jpeg/.png`, and any other configured format) | ~22 images | Binary docs | DocumentReader (Docling) |

`hospital admission1.md` (claim 8) is medical narrative in markdown — treat as MarkdownReader input with sparse booking fields, or route via DocumentReader if listed under document formats; prefer MarkdownReader for `.md` consistency and leave medical free-text for InformationExtractor/Docling path when format is non-`.md`.

### answer.json schema variants
- Minimal: `{"decision": "APPROVE"}`
- Standard: `{"decision": "DENY", "explanation": "..."}`
- Uncertain: `{"decision": "UNCERTAIN", "explanation": "...", "acceptable_decision": "DENY"}`

Maximal GroundTruth fields: `decision`, `explanation`, `acceptable_decision`. Missing → `np.nan`.

### Markdown booking keys (maximal BookingData after translation)

Canonical English fields observed across all `.md` files (helpers translate Spanish/aliases → these):

| Canonical field | Source aliases |
|-----------------|----------------|
| `current_date` | `Current date is`, etc. |
| `name` | `Name`, `Nombre`, `Claimant`, `Patient Name` |
| `booking_ref` | `Booking Ref`, `Booking Reference`, `Referencia de Reserva` |
| `price` | `Price`, `Precio`, `Ticket Price`, `Ticket Cost` |
| `operator` | `Operator`, `Operador`, `Airline` |
| `service` | `Flight`, `Flight Number`, `Train`, `Tren`, `Event`, `Hotel`, `Hotel Name` |
| `departure` | `Departure`, `Salida`, `Event Date`, `Check-in`, `Check-in Date`, `Date` |
| `origin` | `From`, `Desde`, `Origin` |
| `destination` | `To`, `Hacia`, `Destination`, `Location` |
| `seat` | `Seat`, `Asiento` |
| `fare_type` | `Fare Type`, `Tipo de Tarifa`, `Class`, `Ticket Type`, `Room Type` |
| `booked_on` | `Booked on`, `Reservado el`, `Registered on`, `Date of Booking`, `Payment Date` |
| `check_out` | `Check-out`, `Check-out Date` |
| `guests` | `Guests` |
| `venue` | `Venue` |
| `bib_number` | `Bib Number` |
| `booking_platform` | `Booking Platform` |
| `cancellation` | `Cancellation` |

Missing fields fill with `np.nan`. Key normalization: strip bold markers, lower-case, collapse whitespace, map via translation table.

### DocumentReader (Docling) — PNG-first
1. Match file suffix against config `document_formats`.
2. **FormatConverter.to_png(path)** (`preprocessing.py`) — convert webp/jpg/jpeg/… → PNG (in-memory or temp PNG path); already-PNG passes through. Applied **before** Docling.
3. Docling `DocumentConverter` runs on the PNG.
4. Map extracted text into an extensible **`DocumentData`** Pydantic model (D008) — not medical-specific:
   - **Core:** `person` (str | float = np.nan), `date` (str | float = np.nan)
   - **Pipeline:** `raw_text`, `confidence`, `human_in_the_loop`
   - **Arbitrary:** `fields: dict[str, Any] = {}` for any other extracted key/value (diagnosis, facility, seat, airline, signature, …); optionally `model_config = ConfigDict(extra='allow')` so unknown top-level keys are retained
5. Low confidence → flag `human_in_the_loop=True` (threshold in config).

PDF (if listed in formats): either convert first page(s) to PNG via FormatConverter or pass through — document the chosen branch in FormatConverter; default for image formats is always PNG-first.

### DescriptionReader
- Reads free text; Preprocessor invokes `InformationExtractor` with **BookingData** as the target schema (same model as MarkdownReader).
- LLM model name + extraction prompt live in `config.yaml`.

## Dependencies needed
- `Pillow` — used by FormatConverter to convert configured formats → PNG
- `docling` — text extraction from PNG (after FormatConverter)
- `numpy` — `np.nan` defaults for missing fields
- `pydantic` — already present
- LLM client per chosen stack (model name from config; wire in InformationExtractor)

## Key design decisions
- D001: Preprocessing first milestone, output intermediate `processed.json` per claim
- D002: ~~Tesseract + Pillow OCR~~ — **superseded by D005 (Docling)**; Pillow retained only for FormatConverter
- D003: Config externalized to config.yaml
- D004: Reader + Preprocessor ABC pattern; Answer / Description / Markdown readers
- D005: Docling for remaining multi-format documents (after PNG conversion)
- D006: InformationExtractor (LLM + Pydantic schema + config prompt) for description.txt
- D007: FormatConverter in preprocessing.py converts to PNG before Docling
- D008: Extensible DocumentData (person, date, + arbitrary fields) — not MedicalDocument
