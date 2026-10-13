# Synthetic catalog and judgments

All 16 records and eight queries were authored for this sample and are licensed
under the repository MIT license. They describe fictional products, not offers,
reviews or recommendations. No scraped text, external images or third-party data.
Source: `data/catalog.json`; author: Azure DocumentDB sample contributors (2026).

The six answerable queries have explicit human-authored *synthetic* relevance
labels. Two no-answer cases deliberately have an empty label set. These are a
teaching fixture, not representative relevance judgments or a product benchmark.
An empty label set has undefined recall, reported as `null`, not a fabricated 1.
The UI reports returned results on those queries: nearest-neighbor search is not
an answerability classifier, so do not mistake a high score for confidence.

Embeddings are generated only with operator consent using the same real Azure
OpenAI text-embedding-3-small v1 deployment for catalog and queries. They are not
included in git. Content hash, deployment endpoint, model, version and dimensions
bind the local materialization; changing any requires a new disposable DB.
