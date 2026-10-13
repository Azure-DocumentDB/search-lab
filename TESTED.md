# Verification record — 2026-10-12

**Release status: HOLD. Private review only; not an all-gates-pass release.**
Real managed Azure evaluation, local HTTP and safety probes passed.
**Real browser: NOT VERIFIED. Cloud application hosting: NOT VERIFIED.**
There is no claim of a rendered UI, cloud deployment, scalable ANN benchmark,
production relevance or abstention on unanswerable queries.

## Exact revision and evidence boundary

- Tested application source: `c728d3fb23a1356ca12f4e275892b23184559fad`.
- Independent source review passed with documented limitations at that revision;
  it did not approve browser or cloud-hosting gates.
- This record and README status are documentation-only changes after that source
  revision. The PR's actual head is checked separately by CI; offline CI is not
  browser or cloud evidence.
- Verification date: 2026-10-12 America/Los_Angeles (some timestamps use
  2026-10-13 UTC). Local toolchain: Python 3.12.13 and Node 24.21.0.

## Passed: offline checks

Rerun without cloud/model calls using the existing pinned environment:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
node --test tests/dom.test.js
.venv/bin/ruff check --no-cache search_lab tests
git diff --check
```

- **50 Python tests passed**, with one Starlette/httpx TestClient deprecation
  warning; **4 DOM tests passed**; lint and whitespace checks passed.
- Tests cover independent exact-cosine/recall/RRF math, strict API schemas,
  endpoint/auth boundaries, immutable seeding, budget/cache safety and DOM text
  handling. Explicit doubles and a tiny DOM adapter are not live-service or
  rendered-browser substitutes.
- Saved audits recorded **0 vulnerabilities** among 30 runtime and 57 full
  development dependencies. The documentation reviewer inspected those saved
  results, not a fresh advisory service response. CI performs a fresh runtime
  dependency audit.

## Passed: managed Azure seed/readiness and evaluation

The retained seed rerun exited 0 at the tested revision: **0 inserted,
16 existing**. It checked record compatibility and the actual index catalog.
The saved result describes `lab_ivf_cos`, `embedding: cosmosSearch`,
`vector-ivf`, `COS`, **1536 dimensions**, **numLists=1**. The preserved rerun
record does not independently retain the initial insertion-count output; it
must not be presented as a captured first-seed `inserted: 16` result.

The real `--evaluate` run exited 0 (wrapper elapsed 4.1 seconds). All **8 cases**
completed, **K=3**, with one first-observed request plus **3 warm-client samples
per method/case**. Dataset version:

```text
75f2190f9eef355d413856ba238b83191d7af83e07216a01240d7eea3407a032
```

### Observed quality, not fabricated expectations

Synthetic label recall@3 by case, in **keyword / vector / application RRF** order:

- q1 rain protection: **0 / 1 / 1**.
- q2 train-ride phone charging: **1 / 1 / 1**.
- q3 weighing flour: **1 / 1 / 1**.
- q4 desk reading light: **0 / 1 / 0**.
- q5 quiet work (two relevant records): **1 / 1 / 1**.
- q6 hot soup: **1 / 1 / 1**.
- q7 antibiotics and q8 ship engine: label recall **null** (no relevant catalog
  labels), and **each method returned 3 results in each case**. The sample does
  not identify answerability or abstain; a nonempty result is not a correct answer.

Over the six answerable synthetic cases, mean label recall was **0.667 keyword,
1.000 vector, 0.833 RRF**. RRF did not improve every query (q4 regressed versus
vector). Vector recall against the **independent exhaustive cosine top-3** was
**1.0 for all eight cases**. The one-list index and all-16-candidate retrieval
make this a small correctness/conformance result, **not** evidence of scalable
ANN recall, robust production relevance or algorithm superiority.

### Observed timings

Across the eight cases, per-case warm-client median ranges were **15.04–19.94 ms
keyword** and **38.05–41.55 ms vector**; per-case p95 ranges were
**16.86–21.81 ms keyword** and **38.90–49.34 ms vector**. These are ranges of the
recorded per-case summaries, not pooled percentiles. First-observed requests were
reported separately (18.33–34.10 ms keyword; 35.57–68.92 ms vector).

Timing uses Python `perf_counter`: managed DB retrieval, cursor materialization
and application ranking/filtering, excluding embeddings and readiness validation.
At **n=3**, nearest-rank p95 is the maximum. Requests were sequential with a
warm client; **server cache/cold state is unknown**. This is a tiny teaching run,
not a latency benchmark or filtered-retrieval benchmark.

## Passed: real local HTTP and safety probes

The retained HTTP probe reported PASS for actual managed readiness, eight labeled
queries, semantic vector results, the three distinct modes and sanitized inspector,
security headers, exact metadata filtering, honest no-answer metrics, actual
requested timing sample counts, strict validation and cross-origin rejection.
An uncached query with paid embeddings disabled failed rather than substituting
results. That probe left the cache and model-call count unchanged.

The separate safety probe reported PASS for readiness of all 16 managed records,
refusal to seed over a synthetic user edit, no record mutation on that refusal,
restoration of the synthetic edit, and durable budget rejection before a new
model request. These are real API/database/ledger checks, **not rendered UI
proof**. They do not prove visual stale-card clearing after success then 503.

## Model spending and evidence limits

The observed persisted ledger is **2 attempted model requests**, under the
operator-authorized **cap of 5** (different from the README's example cap of 4):

1. One seed batch of **24 vectors** (16 catalog records + 8 query texts).
2. One original uncached custom HTTP query.

**Paid generation is now disabled.** The later HTTP and safety probes added
**0** requests and observed the ledger still at **2**. Do not describe the whole
run as making no model calls. A call cap is not a token or dollar budget, and
failed/ambiguous attempts count. The remaining cap is not permission to spend.
No model request was made by the documentation/PR reviewer.

The ledger establishes the count, not the provider model's deployment version or
an isolated custom-query increment-and-repeat trace. The runtime requires
`text-embedding-3-small` and a version-bound 1536-dimensional cache; independent
control-plane verification of deployment **version 1** and a preserved explicit
custom-query increment/repeat trace are not present in this reviewed evidence
set. Keep these narrow evidence gaps open rather than infer them from success.
No embedding cache or raw-vector dump is included in this record.

## Explicitly incomplete release gates

1. **Browser — NOT VERIFIED.** Supported navigation policy blocked local access;
   approval for `127.0.0.1` was requested, and no bypass was attempted. Actual
   rendering, source/filter/RRF interactions, UI evaluation to 8/8,
   keyboard/focus, narrow viewport, console/network review, and success-then-503
   stale-card clearing remain unverified. CLI 8/8 is not UI 8/8.
2. **Cloud application hosting — NOT VERIFIED.** Local app + real managed Azure
   DB is the verified execution boundary. No App Service URL, cloud ingress
   restriction proof or off-IP denial is claimed. App Service allocation was
   blocked elsewhere in this verification run by quota 0, with 0 plans created;
   optional hosting confirmation flags are not access-control evidence.
3. Retain the seed/model provenance gaps above and the remaining
   [operator verification gates](VERIFICATION.md). Publication and owned-resource
   cleanup remain operator-controlled; restored test data is not proof that all
   Azure resources were deleted.

## Retained evidence

Sanitized records are retained outside this repository in the 2026-10-12 sample
verification workspace: `search-seed.json` / `.log`, `search-evaluate.json` /
`.log`, `search-http.json`, `search-safety-proof.json`, the small
`embedding-budget.json` ledger, saved offline/audit logs, and the independent
source review. This document summarizes those records without credentials,
environment files, endpoint secrets, or embedding vectors. Private review/CI
success does not authorize publication while required gates remain incomplete.
