# API Coverage — ollama (classification)

> Full coverage by default. Opt-outs are explicit, reasoned decisions.
>
> Phase 02 reuses the existing local `ollama.chat` client already integrated by
> Phase 01 `InformationExtractor`. No new external API vendor is introduced.

| capability | decision | reason |
|---|---|---|
| chat (sync, format=json) | INTEGRATE | CaseClassifier.classify uses chat with JSON format for labels + probabilities |
| chat streaming | OPT-OUT | classify returns a single ClassificationResult; streaming not needed |
| generate | OPT-OUT | chat API is sufficient; generate would duplicate the seam |
| embeddings | OPT-OUT | not needed for label classification this phase |
| list / show / pull models | OPT-OUT | operator/ops concern; model name comes from config.yaml only |
| create / delete / copy models | OPT-OUT | out of scope for claim classification |
| ps / running models | OPT-OUT | not needed for classify path |
| blob / push / pull blob | OPT-OUT | not needed for classify path |
