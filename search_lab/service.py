"""Measured retrieval and evaluation. No mock results or generated performance numbers."""

import time

import pymongo

from .config import LabError
from .database import INDEX, Database
from .dataset import materialize
from .embeddings import Embeddings
from .ranking import exact_reference, latency_stats, recall, rrf


class Lab:
    def __init__(self, config):
        self.c = config
        self.embeddings = Embeddings(config)
        self.db = Database(config)
        self.records = None
        self.queries = None
        self.vectors = None
        self.version = None

    def load(self, allow_new=False):
        if self.records is None:
            self.records, self.queries, self.vectors, self.version = materialize(self.embeddings, allow_new=allow_new)

    def ready(self):
        self.load()
        self.db.ready(self.records)

    def close(self):
        self.db.close()

    def search(self, text, filters, k):
        with pymongo.timeout(45):
            return self._search(text, filters, k)

    def _search(self, text, filters, k):
        self.ready()
        query = self.embeddings.get([text])[0]
        start = time.perf_counter()
        keyword = self.db.keyword(text, filters, 16)
        keyword_ms = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        vector = self.db.vector(query, filters, 16)
        vector_ms = (time.perf_counter() - start) * 1000
        hybrid = rrf(keyword, vector, k)
        return {
            "keyword": keyword[:k],
            "vector": vector[:k],
            "hybrid": hybrid,
            "latency_ms": {"keyword": keyword_ms, "vector": vector_ms},
            "dataset_version": self.version,
            "inspection": {
                "index": INDEX,
                "query": {
                    "path": "embedding",
                    "dimensions": 1536,
                    "service_candidate_k": 16,
                    "display_k": k,
                    "exact_post_filters": filters,
                    "vectors_redacted": True,
                },
                "keyword": "Managed DB escaped token regex; application unique-token-overlap rank (not BM25).",
                "hybrid": "Application RRF (constant 60) over keyword and vector ranks; not native hybrid.",
                "filtering": "All 16 service vector candidates fetched, then exact metadata postfilter. Tiny-lab only.",
            },
        }

    def evaluate_case(self, case_id, k=3, repeats=3):
        with pymongo.timeout(45):
            return self._evaluate_case(case_id, k, repeats)

    def _evaluate_case(self, case_id, k, repeats):
        self.ready()
        case = next((q for q in self.queries if q["id"] == case_id), None)
        if case is None:
            raise LabError("Unknown evaluation case.")
        text, query = case["text"], self.vectors[case_id]
        samples = {"keyword": [], "vector": []}
        first = {}
        rows = {}
        for iteration in range(repeats + 1):
            for mode in ("keyword", "vector"):
                start = time.perf_counter()
                result = self.db.keyword(text, {}, 16) if mode == "keyword" else self.db.vector(query, {}, 16)
                elapsed = (time.perf_counter() - start) * 1000
                if iteration == 0:
                    first[mode] = elapsed
                else:
                    samples[mode].append(elapsed)
                rows[mode] = result
        rows["hybrid"] = rrf(rows["keyword"], rows["vector"], k)
        exact = [key for key, _ in exact_reference(self.records, query, k)]
        metrics = {}
        for mode, result in rows.items():
            ids = [r["document"]["_id"] for r in result[:k]]
            metrics[mode] = {
                "ids": ids,
                "label_recall_at_k": recall(ids, case["relevant"]),
                "returned_on_no_answer": len(ids) if not case["relevant"] else None,
            }
        metrics["vector"]["exact_reference_recall_at_k"] = recall(metrics["vector"]["ids"], exact)
        return {
            "case": case,
            "k": k,
            "metrics": metrics,
            "exact_reference_ids": exact,
            "latency": {
                mode: dict(latency_stats(values), first_observed_ms=first[mode]) for mode, values in samples.items()
            },
            "conditions": "One first-observed request excluded; then sequential warm-client requests. Server cache/cold state unknown.",
            "timing_source": "Python perf_counter; managed DB request + cursor materialization + application ranking/filtering; embeddings excluded.",
            "dataset_version": self.version,
        }
