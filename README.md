# Search lab

**Words versus meaning, with evidence.** A Python 3.12 / FastAPI / vanilla-web
application for **managed Azure DocumentDB**, not the open-source server.
Run the application locally against your Azure cluster; there is no local database,
Docker database substitute, static-result fallback, or LLM answer generator.

Compare keyword, vector and optional application RRF result cards. Inspect sources
and sanitized query/index settings. Evaluate eight explicitly labeled synthetic
queries using label recall@K, an independent brute-force cosine reference, and
repeated actual managed-service request latency.

## Verification status — private review, not release-ready

[Exact tested revision, measured results and limitations](TESTED.md): **50 Python
and 4 DOM tests passed**, plus actual managed Azure eight-case evaluation, local
HTTP and safety probes. **Real browser: NOT VERIFIED** (navigation policy blocked);
cloud application hosting is not verified. The persisted embedding ledger records
**2 attempted requests under cap 5**, and new paid generation is now disabled.
CLI/API results do not prove rendered UI behavior; publication remains on hold.

## What this teaches (and doesn't)

- **Keyword:** managed Mongo query with escaped token regex, then application
  unique-token-overlap ranking. This is **not full-text search or BM25**.
- **Vector:** managed `cosmosSearch`, IVF / COS / 1536 dimensions / `numLists=1`.
  HNSW is intentionally not offered without a supported, proven implementation.
- **Hybrid:** actual application reciprocal-rank fusion (RRF constant 60) over
  both ranked lists. This is **not native hybrid search** and does not require a
  private-preview text API.
- **Filters:** exact category and region equality. We deliberately fetch all 16
  vector candidates and postfilter, rather than guessing tier-specific prefilter
  syntax. This is useful for this tiny experiment, **not scalable filtered ANN**.
- **Scores are ranking signals, not confidence.** Do not compare the magnitudes of
  token overlap, service cosine scores and RRF scores.
- **Evaluation:** synthetic labels are a teaching fixture, not benchmark truth.
  No-answer recall is undefined (`null`); returned results are reported instead.
  Search does not determine answerability.
- **Latency:** real `perf_counter` measurements, no random numbers. One
  first-observed request is excluded, followed by three sequential warm-client
  requests. Median/p95 (nearest-rank) report n=3; p95 at this n is the maximum.
  **Server cache/cold state is unknown**. Timings include cursor materialization
  and application ranking/filtering, but not embeddings or readiness validation.
  There is no claimed “cold-cache benchmark”.

## Prerequisites

1. Python **3.12**, [uv](https://docs.astral.sh/uv/), and Node 22+ for the DOM tests.
   macOS/Linux are supported (`fcntl` protects the durable call budget).
2. A managed Azure DocumentDB cluster with vector search, connectivity/firewall
   access, and permission to create one disposable database/collection/index.
3. Azure OpenAI deployment of **text-embedding-3-small, model version 1**, 1536
   dimensions. The backend uses API `2024-10-21`.
4. `az login` for the default explicit Azure CLI authentication. Configure a
   database Microsoft Entra principal with appropriate data-plane permissions.
   No broad credential-chain fallback is used. Native DB credentials and an Azure
   OpenAI API key are explicit alternatives below.

The application does not create Azure resources, estimate your subscription's
prices, enable previews, or delete anything. Database and hosting charges continue
until you explicitly manage those resources yourself.

## Install and verify before connecting to Azure

```bash
uv sync --frozen
uv run python -m pytest -q
node --test tests/dom.test.js
uv run ruff check search_lab tests
uv run pip-audit --disable-pip --no-deps -r requirements.txt
```

`uv.lock` and exported `requirements*.txt` pin transitive dependencies with hashes.
Alternatively: `python3.12 -m venv .venv` then
`.venv/bin/pip install --require-hashes -r requirements.txt`.
CI is read-only, actions are SHA-pinned, and no cloud secrets are needed by tests.
Unit/HTTP/DOM tests use explicit test doubles; they **do not count as Azure or
browser end-to-end evidence**. See [VERIFICATION.md](VERIFICATION.md).

## Configure (backend process environment only)

The sample never loads `.env` files. Do not put secrets in source, URLs, browser
storage, command-line arguments, transcripts or screenshots. Set secret values
using your operator's protected environment/secret injection mechanism.

```bash
export MONGO_AUTH_MODE=oidc
export MONGO_HOST='<cluster>.mongocluster.cosmos.azure.com'
export MONGO_DATABASE='searchlab_disposable_my_run'
# Optional, if required by your configured Entra principal:
# export MONGO_OIDC_USERNAME='<principal-name>'
export AZURE_OPENAI_ENDPOINT='https://<resource>.openai.azure.com'
export AZURE_OPENAI_DEPLOYMENT='search-embedding'
export AZURE_OPENAI_MODEL_VERSION=1
export SEARCH_LAB_STATE_DIR='.state'
```

Native alternative: set `MONGO_AUTH_MODE=connection-string` and inject
`MONGO_CONNECTION_STRING` as a secret containing a `mongodb+srv://` URI for an
Azure `*.mongocluster.cosmos.azure.com` host. Unset `MONGO_HOST` and
`MONGO_OIDC_USERNAME`. Verified TLS, SCRAM-SHA-256, auth source `admin` and
`retryWrites=false` are enforced; unknown URI options (including proxy, alternate
TLS or auth settings) are rejected. URI credentials must be percent-encoded.

Azure OpenAI uses Azure CLI with the fixed cognitive-services scope unless
`AZURE_OPENAI_API_KEY` is injected. Embedding endpoints must match
`https://<resource>.openai.azure.com` on 443. No redirects, environment proxies,
custom CA environment overrides, arbitrary token destinations or fallback models.
The deployment must actually be the documented version; the API response model
is checked, and operator-declared version is bound into the cache identity.

## Explicit one-time paid preparation + insert-only seed

Read the fixtures first: [catalog](data/catalog.json), [queries](data/queries.json),
[data source/license](data/README.md). All 24 texts are original MIT-licensed
synthetic content. There are no external images.

```bash
# Consent to this specific disposable namespace, not arbitrary DB writes:
export SEARCH_LAB_WRITE_CONSENT="${MONGO_DATABASE}/catalog_v1"
# Consent to paid embeddings. Calls are capped persistently, including failures:
export SEARCH_LAB_ALLOW_PAID_EMBEDDINGS=true
export SEARCH_LAB_MAX_EMBEDDING_CALLS=4
uv run python -m search_lab --seed
```

The first seed submits **one batch of 24 texts** (16 records + 8 query embeddings).
The four-call lifetime cap leaves at most three calls for uncached custom queries.
There are no automatic retries. The ledger is atomically charged **before** each
call; failed/ambiguous calls count. A file lock prevents parallel overspending
within one shared state directory. Cached text is free to reuse. Raising the cap
is a deliberate operator action; deleting/moving the state directory resets its
ledger and is **not** an idempotent way to retry.

Seeding validates all local records and the entire existing collection/index
catalog before any DB mutation. It uses stable IDs and `$setOnInsert`, never
replace/delete/update existing content. A missing index on a compatible full
catalog can be created safely. Unknown records, user edits, foreign indexes, TTL
or partial indexes fail closed. Partial insert-only progress is resumable. Do not
run concurrent writers while seeding; this small sample is not a distributed
migration protocol.

The materialization is bound to fixture content, endpoint, deployment, model,
version and dimensions. For changed data/model/deployment use a **new state
directory AND new disposable database**. Back up the small `.state` directory
(embeddings and budget ledger together) if moving the application. It contains
query text hashes/vectors, not API keys; custom query embeddings may be sensitive.

## Start the interactive lab

```bash
# Disable new model spending after seeding, if only using the eight preset queries:
export SEARCH_LAB_ALLOW_PAID_EMBEDDINGS=false
unset SEARCH_LAB_WRITE_CONSENT
uv run python -m search_lab
# Open http://127.0.0.1:8765
```

The UI itself never seeds or mutates the DB. Choose a preset or enter a custom
query, select exact filters and K, compare methods, inspect a source card, enable
application RRF, and run bounded evaluation. Uncached custom queries require
re-enabling the explicit paid gate and having remaining budget. Presets work from
the seed cache. No cached/static **results** are substituted on failure: the UI
clears stale results and reports a sanitized 503 error.

```bash
# Same evaluator without the browser; actual service requests only:
uv run python -m search_lab --evaluate > evaluation.json
```

One evaluation is eight cases × two methods × four requests = **64 retrieval
requests**, plus per-case catalog/index validation. The HTTP endpoint caps repeats
at five, applies a 45-second cumulative database deadline per case/search, and handles one operation at a time. RRF is local rank fusion, not another
DB request. The small n and synthetic corpus must accompany any reported metrics.

## Security and optional Azure hosting

Default binding is **127.0.0.1**; remote clients and unexpected Host values are
rejected. POSTs require a same-origin custom header; supplied Origin must match.
Inputs use strict enums/bounds and never accept Mongo operators or pipelines.
The browser receives no keys, URIs, raw vectors or Azure endpoint. This is an
**operator-local app**, not authentication suitable for general-public mutation.
Local programs run by your user are within this trust boundary.

An explicit App Service compatibility mode is provided for an operator to prove
separately; **no deployment is claimed verified by the offline tests**. Use one
Python 3.12 Linux worker, zip the source/data/static files and hash-locked
`requirements.txt`, enable dependency installation, and set startup:

```text
python -m search_lab --port 8000
```

Before allowing non-loopback binding, configure and verify Azure App Service
access restrictions with **allow rules for exact operator IPs and default deny**
(and HTTPS-only). Then set:

```text
SEARCH_LAB_HOSTING=appservice
SEARCH_LAB_IP_RESTRICTIONS_CONFIRMED=true
SEARCH_LAB_OPERATOR_IPS=<operator-ip>/32
SEARCH_LAB_STATE_DIR=/home/search-lab-state
```

`WEBSITE_HOSTNAME` must be the platform-provided exact `*.azurewebsites.net` host.
The app binds 0.0.0.0 only in this mode. **Platform IP restrictions, not these
configuration strings, authenticate ingress.** The code does not trust forwarded
IP headers or assert that configuration proves Azure restrictions. Do not use this
mode without verifying the deny rule externally. Single instance/worker only;
copy the seed state cache and ledger intact before starting. CLI authentication
is normally unavailable in App Service, so inject native DB credentials and the
Azure OpenAI key securely, or do not deploy. Entra managed-identity hosting is not
implemented. Never deploy a public unrestricted instance. No unverified Bicep is
included.

## Layout and architecture

```text
Browser (no secrets)
  -> same-origin FastAPI operator boundary
    -> exact schema + bounded operation lock
      -> managed Azure DocumentDB: regex keyword / IVF cosine
      -> local RRF + exhaustive cosine reference + timed evaluation
      -> Azure OpenAI (only uncached text, explicit consent, durable cap)
         -> version-bound local embedding cache
```

- `config.py`: managed-host and transport validation.
- `embeddings.py`: fixed Azure embedding API, cache, durable budget.
- `dataset.py`: original fixtures and model-space materialization.
- `database.py`: explicit auth, immutable seed, index catalog, managed queries.
- `ranking.py`: transparent lexical/RRF, independent exact cosine, metrics.
- `service.py`: retrieval orchestration and measured evaluation.
- `app.py` / `static/`: operator boundary and accessible responsive UI.

### Assumptions and limits

Azure public-cloud suffixes only; no sovereign/private endpoint aliases. Python
3.12, macOS/Linux; one operator instance; 16 immutable records. IVF's tiny one-list
index is intentionally simple, not an algorithm-performance shootout. Full-corpus
validation each operation is safety overhead excluded from timed retrieval.
Changes made by another DB writer during a request are outside the experiment's
snapshot guarantee: keep the disposable namespace dedicated. There is no automatic
production-resource cleanup, pagination, persistent evaluation history or answer
generation. Contributions should preserve honest labels and independent tests.
