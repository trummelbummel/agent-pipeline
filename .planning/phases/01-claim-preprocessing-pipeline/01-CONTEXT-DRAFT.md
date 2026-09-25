# M001 Context — Claim Preprocessing Pipeline

## Decisions
- D001: First milestone is preprocessing pipeline; output intermediate processed.json per claim
- D002: Superseded by D005 — do not use Tesseract/Pillow
- D003: All config externalized to config.yaml under `preprocessing` / `extraction` keys
- D004: Extensible Reader ABC + Preprocessor ABC (`reader`/`preprocessing` modules). Child readers: AnswerReader, DescriptionReader, MarkdownReader. Preprocessor invoked inside each Reader (e.g. MarkdownPreprocessor normalizes/translates keys)
- D005: DocumentReader uses Docling for remaining claim files; formats from config; map to extensible DocumentData (person, date, + arbitrary fields); confidence → human_in_the_loop
- D006: InformationExtractor(Pydantic model, LLM model from config, prompt from config) extracts BookingData fields from description.txt
- D007: FormatConverter in preprocessing.py converts configured formats → PNG **before** Docling runs
- D008: DocumentData is type-agnostic and extensible (not medical-only)

## Requirements
- R001: Parse all 25 claim folders into structured JSON
- R002: FormatConverter → PNG, then Docling text extraction from multi-format claim documents (formats from config)
- R003: Pydantic schemas with maximal fields; missing values = np.nan
- R004: Graceful handling of missing optional files
- R005: Config externalization (paths, Docling formats, LLM model, extraction prompt, confidence threshold)
- R006: InformationExtractor fills BookingData-shaped fields from description free text

## Slice Plan
- S01: Pydantic maximal models + config loader (Docling formats, LLM, prompts) (~75min)
- S02: Reader/Preprocessor ABCs + FormatConverter (→ PNG) + AnswerReader + MarkdownReader (~100min)
- S03: DocumentReader (FormatConverter then Docling) + InformationExtractor + DescriptionReader + pipeline (~140min)

## Key Data Facts
- 25 claim folders; answer.json has 3 schema variants
- Markdown keys need translation (EN + ES aliases → canonical BookingData)
- Remaining files: webp/jpg/jpeg/png (+ configurable); FormatConverter → PNG, then Docling extracts text
- File presence varies per claim — missing → np.nan / empty lists

## Dependencies to Add
- Pillow (FormatConverter), docling, numpy; LLM client as required by InformationExtractor
