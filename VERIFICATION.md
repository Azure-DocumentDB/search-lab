# Verification gates

## Offline gate (reproducible)

- `uv sync --frozen`
- `uv run python -m pytest -q`: security, endpoint/URI rejection, HTTP schemas,
  no-secret errors, permanent budget/cache/failure tests, independent geometry,
  hand-computed metrics, insert-only and missing/conflicting index checks.
- `node --test tests/dom.test.js`: DOM rendering, empty states, source inspection,
  literal text/XSS safety, no-answer rendering, labels and progress semantics.
- `uv run ruff check search_lab tests`
- `uv run pip-audit --disable-pip --no-deps -r requirements.txt`

DOM adapter tests are not a real browser and never claimed as live UI proof.

## Required live operator gate (must be recorded before publication)

1. Install against the exact reviewed commit; record SHA, Python version and
   dependency audit result. Provision/authorize real managed Azure DocumentDB and
   real Azure OpenAI text-embedding-3-small v1. Never use OSS/local substitutes.
2. Authorize one exact disposable namespace and a small model-call cap. Run seed,
   record inserted count 16, IVF index properties and successful second seed with
   inserted count 0. Keep secrets outside all evidence.
3. Run `--evaluate`; save actual results with case count, K, sample count, cache
   conditions and timing source. Report synthetic label recall independently from
   exact-reference recall; don't suppress no-answer results.
4. In a real browser open the actual running app (local app + real Azure DB is
   valid). Compare a preset, view cards and a selected source, use exact category
   and region filters, enable actual RRF, inspect sanitized query/index properties.
5. Explicitly permit one new paid embedding, search an uncached natural-language
   query, verify one ledger increment then no increment when repeating it.
6. Run all eight evaluation cases through the UI, verify progress reaches 8/8,
   metrics and no-answer displays. Inspect keyboard focus, narrow/mobile layout,
   no horizontal overflow and console/network errors.
7. Verify unavailable service produces clear 503 and no stale/static cards; no
   secrets/endpoints/vectors reach the browser. Verify malformed filters rejected.
8. If using optional App Service mode, prove exact operator-IP allow/default deny
   restrictions and HTTPS first, then the same real browser flows; record the
   hosting proof separately. The environment's confirmation flag is not evidence.

No Azure execution or actual browser proof is implied by checked-in unit tests.
