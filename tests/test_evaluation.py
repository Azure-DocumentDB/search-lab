from unittest.mock import patch

import pytest

from search_lab.service import Lab


def row(key):
    return {"document": {"_id": key}, "score": 0.9}


class MeasuredDB:
    def __init__(self):
        self.keyword_calls = 0
        self.vector_calls = 0

    def keyword(self, text, filters, k):
        self.keyword_calls += 1
        return [row("side")]

    def vector(self, query, filters, k):
        self.vector_calls += 1
        # Deliberately wrong ranking; expected value must not come from these rows.
        return [row("side"), row("best")]


def test_evaluation_uses_independent_reference_and_actual_clock():
    lab = Lab.__new__(Lab)
    lab.ready = lambda: None
    lab.db = MeasuredDB()
    lab.queries = [{"id": "q1", "text": "unit query", "relevant": ["best"]}]
    lab.vectors = {"q1": [1, 0]}
    lab.records = [{"_id": "best", "embedding": [1, 0]}, {"_id": "side", "embedding": [0, 1]}]
    lab.version = "unit"
    # Hand-set clock in test only: each successive measured duration is one millisecond.
    with patch("search_lab.service.time.perf_counter", side_effect=[x / 1000 for x in range(16)]):
        result = lab.evaluate_case("q1", k=1, repeats=3)
    assert result["exact_reference_ids"] == ["best"]
    assert result["metrics"]["vector"]["exact_reference_recall_at_k"] == 0
    assert result["metrics"]["vector"]["label_recall_at_k"] == 0
    assert lab.db.vector_calls == lab.db.keyword_calls == 4
    for latency in result["latency"].values():
        assert latency["n"] == 3
        assert latency["median_ms"] == pytest.approx(1)
        assert latency["p95_ms"] == pytest.approx(1)
    assert "Server cache/cold state unknown" in result["conditions"]
