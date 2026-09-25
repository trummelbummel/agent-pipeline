# M001: Claim Preprocessing Pipeline

**Vision:** Parse all 25 insurance claim folders into structured `processed.json` files via extensible Reader/Preprocessor ABCs — AnswerReader, MarkdownReader, DescriptionReader (LLM InformationExtractor), and DocumentReader (FormatConverter → PNG, then Docling) — producing typed ClaimBundle outputs for downstream agents and rules engines.

## Success Criteria

- All 25 claim folders produce a valid `processed.json`
- Reader ABC + Preprocessor ABC; four concrete readers (answer, markdown, description, document)
- FormatConverter in preprocessing.py converts configured formats to PNG before Docling
- Markdown keys normalized/translated to canonical BookingData; missing fields = `np.nan`
- Docling extracts text from PNG-normalized documents and maps to extensible DocumentData (person, date, + arbitrary fields)
- DescriptionReader uses InformationExtractor (model + prompt from config) targeting BookingData
- Claims with missing optional files produce valid output with `np.nan` / empty lists
- All config values externalized to `config.yaml`
- pytest passes on 5+ representative claims; mypy passes on all new source files

## Slices

- [x] **S01: Pydantic models and config** `risk:medium` `depends:[]`
  > After this: Import ClaimBundle / BookingData / DocumentData / GroundTruth; load config with Docling formats, LLM model, and extraction prompt

- [x] **S02: Reader/Preprocessor ABCs + FormatConverter + Answer + Markdown** `risk:medium` `depends:[S01]`
  > After this: FormatConverter turns webp/jpg → PNG; AnswerReader and MarkdownReader return typed models with key translation and np.nan defaults

- [ ] **S03: Docling DocumentReader + InformationExtractor + pipeline** `risk:high` `depends:[S01,S02]`
  > After this: Run full pipeline on all 25 claims; DocumentReader applies FormatConverter then Docling; show processed.json for claim 16 and claim 1

## Boundary Map

Not provided.
<!-- gsd:state-version=4:0 -->
