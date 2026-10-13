"""Independent exhaustive cosine reference and honest application keyword/RRF ranking."""

import math
import re


def tokens(text):
    return list(dict.fromkeys(re.findall(r"[\w]+", text.lower(), flags=re.UNICODE)))[:40]


def lexical_score(text, query):
    words = set(tokens(text))
    return float(len(words.intersection(tokens(query))))


def exact_reference(docs, query, k):
    """Brute force ALL eligible vectors. Never reuses database scores or ordering."""
    qn = math.sqrt(math.fsum(x * x for x in query))
    scores = []
    for d in docs:
        v = d["embedding"]
        vn = math.sqrt(math.fsum(x * x for x in v))
        score = math.fsum(a * b for a, b in zip(query, v, strict=True)) / (qn * vn)
        scores.append((d["_id"], score))
    return sorted(scores, key=lambda pair: (-pair[1], pair[0]))[:k]


def recall(ids, relevant):
    return len(set(ids) & set(relevant)) / len(set(relevant)) if relevant else None


def rrf(keyword, vector, k):
    scores, docs = {}, {}
    for rows in (keyword, vector):
        for rank, row in enumerate(rows, 1):
            key = row["document"]["_id"]
            scores[key] = scores.get(key, 0.0) + 1 / (60 + rank)
            docs[key] = row["document"]
    return [
        {"document": docs[key], "score": score}
        for key, score in sorted(scores.items(), key=lambda p: (-p[1], p[0]))[:k]
    ]


def latency_stats(samples):
    """Median and nearest-rank p95; measured client milliseconds, never synthetic."""
    ordered = sorted(samples)
    n = len(ordered)
    if not n:
        return {"n": 0, "median_ms": None, "p95_ms": None}
    middle = n // 2
    return {
        "n": n,
        "median_ms": ordered[middle] if n % 2 else (ordered[middle - 1] + ordered[middle]) / 2,
        "p95_ms": ordered[math.ceil(0.95 * n) - 1],
    }
