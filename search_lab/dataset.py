"""Content-addressed, model-space-bound dataset; all validations precede DB writes."""

import json
from pathlib import Path

from .config import LabError
from .embeddings import digest

DATA = Path(__file__).resolve().parent.parent / "data"
CATEGORIES = ("outdoors", "office", "kitchen", "travel")
REGIONS = ("north", "south")


def fixtures():
    docs = json.loads((DATA / "catalog.json").read_text())
    queries = json.loads((DATA / "queries.json").read_text())
    if len(docs) != 16 or len(queries) != 8:
        raise LabError("Fixture size changed; version the dataset explicitly.")
    ids = set()
    for d in docs:
        if (
            set(d) != {"_id", "title", "text", "category", "region", "price"}
            or not isinstance(d["_id"], str)
            or d["_id"] in ids
            or d["category"] not in CATEGORIES
            or d["region"] not in REGIONS
            or not isinstance(d["title"], str)
            or not isinstance(d["text"], str)
            or not 1 <= len(d["text"]) <= 400
            or type(d["price"]) is not int
            or d["price"] < 0
        ):
            raise LabError("Invalid catalog fixture.")
        ids.add(d["_id"])
    qids = set()
    for q in queries:
        if (
            q["id"] in qids
            or not isinstance(q["text"], str)
            or not 1 <= len(q["text"]) <= 600
            or not isinstance(q["relevant"], list)
            or not set(q["relevant"]).issubset(ids)
        ):
            raise LabError("Invalid query judgments.")
        qids.add(q["id"])
    return docs, queries


def document_text(doc):
    return doc["title"] + ". " + doc["text"]


def materialize(embedder, allow_new=False):
    docs, queries = fixtures()
    version = digest({"docs": docs, "queries": queries, "space": embedder.space})
    values = embedder.get([document_text(d) for d in docs] + [q["text"] for q in queries], allow_new=allow_new)
    records = [
        dict(d, embedding=v, dataset_version=version, source="Self-authored synthetic catalog", license="MIT")
        for d, v in zip(docs, values[: len(docs)], strict=True)
    ]
    query_vectors = {q["id"]: v for q, v in zip(queries, values[len(docs) :], strict=True)}
    return records, queries, query_vectors, version
