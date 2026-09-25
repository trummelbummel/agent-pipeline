# Roadmap

## Milestones

- 🔄 **v1.0 Claim Preprocessing** — Parse claim folders into structured processed.json

## Phases

- [x] **Phase 01: Claim Preprocessing Pipeline** `profiles: []` (completed 2026-09-25)
  Plans: 01-01, 01-02, 01-03
  Goal: Parse all 25 insurance claim folders into structured processed.json via Reader/Preprocessor ABCs, FormatConverter→PNG→Docling, and InformationExtractor
  Success criteria:
  - All 25 claims produce valid processed.json
  - DocumentData (person, date, + arbitrary fields) from Docling path
  - Config externalized; mypy + pytest pass

## Progress

| Phase | Plans | Status | Completed |
|-------|-------|--------|-----------|
| 01 | 3/3 | Complete    | 2026-09-25 |
