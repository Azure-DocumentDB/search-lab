import pytest

from search_lab.ranking import exact_reference, latency_stats, lexical_score, recall, rrf


def test_independent_exact_geometry_and_ties():
    docs = [
        {"_id": "opposite", "embedding": [-1, 0]},
        {"_id": "side", "embedding": [0, 1]},
        {"_id": "same", "embedding": [3, 0]},
        {"_id": "diagonal", "embedding": [1, 1]},
    ]
    result = exact_reference(docs, [2, 0], 3)
    assert [r[0] for r in result] == ["same", "diagonal", "side"]
    assert result[0][1] == 1
    assert result[1][1] == pytest.approx(0.70710678118)
    assert result[2][1] == 0


def test_labels_empty_and_missing_are_not_perfect():
    assert recall(["a", "b"], ["a", "c"]) == 0.5
    assert recall([], ["a"]) == 0
    assert recall(["a"], []) is None
    assert recall(["a", "a"], ["a", "b"]) == 0.5


def test_keyword_transparent_tokens_not_substrings():
    assert lexical_score("Rain rain jacket", "rain jacket") == 2
    assert lexical_score("Brainstorming", "rain") == 0
    assert lexical_score("a.*", ".*") == 0


def test_rrf_is_actual_rank_fusion():
    def row(id):
        return {"document": {"_id": id}, "score": 1000}

    result = rrf([row("a"), row("b")], [row("b"), row("c")], 3)
    assert [r["document"]["_id"] for r in result] == ["b", "a", "c"]
    assert result[0]["score"] == pytest.approx(1 / 61 + 1 / 62)


def test_percentiles_hand_computed_not_random():
    assert latency_stats([100, 1, 3, 2]) == {"n": 4, "median_ms": 2.5, "p95_ms": 100}
    assert latency_stats([]) == {"n": 0, "median_ms": None, "p95_ms": None}
