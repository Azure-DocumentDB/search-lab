import json
from dataclasses import replace

import httpx
import pytest

from search_lab.config import LabError
from search_lab.embeddings import Embeddings, vector

V = [1.0] + [0.0] * 1535


def good(request):
    body = json.loads(request.content)
    assert request.url.host == "unit.openai.azure.com"
    assert request.url.params["api-version"] == "2024-10-21"
    assert body["dimensions"] == 1536
    return httpx.Response(
        200,
        json={
            "model": "text-embedding-3-small",
            "data": [{"index": i, "embedding": V} for i in range(len(body["input"]))],
        },
    )


def test_consent_cache_and_persistent_budget(config, paid):
    with pytest.raises(LabError, match="disabled"):
        Embeddings(config).get(["new query"])
    embed = Embeddings(paid, httpx.MockTransport(good))
    assert embed.get(["a", "a", "b"]) == [V, V, V]
    assert json.loads((config.state_dir / "embedding-budget.json").read_text())["attempted_calls"] == 1
    # Cached embeddings available without paid consent, even in a fresh process object.
    assert Embeddings(config).get(["a"]) == [V]
    embed.get(["c"])
    with pytest.raises(LabError, match="cap reached"):
        Embeddings(paid).get(["d"])


@pytest.mark.parametrize("code", [302, 401, 429, 500])
def test_failure_charged_no_cache_no_retry(paid, code):
    calls = []

    def fail(req):
        calls.append(req)
        return httpx.Response(code, headers={"location": "https://evil.test"})

    with pytest.raises(LabError):
        Embeddings(paid, httpx.MockTransport(fail)).get(["a"])
    assert len(calls) == 1
    assert not (paid.state_dir / "embeddings.json").exists()
    assert json.loads((paid.state_dir / "embedding-budget.json").read_text())["attempted_calls"] == 1


def test_different_model_space_rejected(paid):
    Embeddings(paid, httpx.MockTransport(good)).get(["a"])
    with pytest.raises(LabError, match="incompatible"):
        Embeddings(replace(paid, deployment="changed")).get(["a"])


@pytest.mark.parametrize("v", [[0.0] * 1536, [True] * 1536, [float("nan")] * 1536, [1.0], [float("inf")] * 1536])
def test_invalid_vector(v):
    with pytest.raises(LabError):
        vector(v)


def test_read_only_dataset_load_never_calls_model_even_when_paid(paid):
    calls = []

    def transport(request):
        calls.append(request)
        return good(request)

    with pytest.raises(LabError, match="--seed"):
        Embeddings(paid, httpx.MockTransport(transport)).get(["uncached"], allow_new=False)
    assert calls == []
    assert not (paid.state_dir / "embedding-budget.json").exists()


def test_missing_ledger_does_not_silently_reset_budget(paid):
    embed = Embeddings(paid, httpx.MockTransport(good))
    embed.get(["a"])
    (paid.state_dir / "embedding-budget.json").unlink()
    assert embed.get(["a"]) == [V]
    with pytest.raises(LabError, match="without its budget ledger"):
        embed.get(["b"])


def test_wrong_model_rejected(paid):
    def wrong(request):
        return httpx.Response(200, json={"model": "different-model", "data": [{"index": 0, "embedding": V}]})

    with pytest.raises(LabError, match="different model"):
        Embeddings(paid, httpx.MockTransport(wrong)).get(["a"])
    assert not (paid.state_dir / "embeddings.json").exists()


def test_retry_after_is_preserved_safely(paid):
    def throttled(request):
        return httpx.Response(429, headers={"Retry-After": "60"})

    with pytest.raises(LabError, match="60 seconds"):
        Embeddings(paid, httpx.MockTransport(throttled)).get(["a"])
