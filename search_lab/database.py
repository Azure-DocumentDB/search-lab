"""Only managed Azure DocumentDB; insert-only seeding, exact filters, IVF COS."""

import math
import re
import time

import certifi
from azure.identity import AzureCliCredential
from pymongo import MongoClient, UpdateOne
from pymongo.auth_oidc import OIDCCallback, OIDCCallbackResult
from pymongo.errors import OperationFailure

from .config import COLLECTION, DIMENSIONS, LabError
from .dataset import document_text
from .embeddings import vector
from .ranking import lexical_score, tokens

INDEX = {
    "name": "lab_ivf_cos",
    "key": {"embedding": "cosmosSearch"},
    "cosmosSearchOptions": {"kind": "vector-ivf", "numLists": 1, "similarity": "COS", "dimensions": DIMENSIONS},
}


class Callback(OIDCCallback):
    def __init__(self, credential):
        self.credential = credential

    def fetch(self, context):
        if context.version != 1 or context.timeout_seconds <= 0:
            raise LabError("Unsupported OIDC context.")
        start = time.monotonic()
        try:
            token = self.credential.get_token("https://ossrdbms-aad.database.windows.net/.default")
        except Exception:
            raise LabError("Azure CLI database token failed; no fallback.") from None
        remaining = token.expires_on - time.time()
        if (
            not isinstance(token.token, str)
            or not token.token
            or remaining <= 30
            or time.monotonic() - start >= context.timeout_seconds
        ):
            raise LabError("OIDC token expired or acquisition exceeded deadline.")
        return OIDCCallbackResult(access_token=token.token, expires_in_seconds=remaining)


def catalog_compatible(indexes):
    found = False
    for idx in indexes:
        if idx.get("name") == "_id_" and idx.get("key") == {"_id": 1}:
            if set(idx) - {"v", "ns", "name", "key"}:
                raise LabError("Unexpected primary-key index properties; no writes.")
            continue
        # A dedicated tiny lab collection must not contain unknown/partial/TTL/other indexes.
        extras = set(idx) - {"v", "ns", "name", "key", "cosmosSearchOptions", "background"}
        if (
            extras
            or idx.get("name") != INDEX["name"]
            or idx.get("key") != INDEX["key"]
            or idx.get("cosmosSearchOptions") != INDEX["cosmosSearchOptions"]
            or any(isinstance(v, bool) for v in idx.get("cosmosSearchOptions", {}).values())
        ):
            raise LabError("Incompatible index catalog; no writes. Use a new disposable database.")
        found = True
    return found


def filters_query(filters):
    return {k: {"$eq": v} for k, v in filters.items() if v is not None}


def public_doc(doc):
    return {k: doc[k] for k in ("_id", "title", "text", "category", "region", "price", "source", "license")}


class Database:
    def __init__(self, config):
        self.c = config.validate()
        self.credential = None
        options = dict(
            tls=True,
            tlsCAFile=certifi.where(),
            retryWrites=False,
            tlsAllowInvalidCertificates=False,
            tlsAllowInvalidHostnames=False,
            connectTimeoutMS=10000,
            serverSelectionTimeoutMS=15000,
            socketTimeoutMS=20000,
            timeoutMS=25000,
            maxPoolSize=3,
            appname="managed-documentdb-search-lab",
        )
        if config.auth_mode == "oidc":
            self.credential = AzureCliCredential(process_timeout=10)
            options.update(
                authMechanism="MONGODB-OIDC",
                authSource="$external",
                authMechanismProperties={"OIDC_CALLBACK": Callback(self.credential)},
            )
            if config.username:
                options["username"] = config.username
            uri = f"mongodb+srv://{config.host}/"
        else:
            uri = config.uri
            options.update(authMechanism="SCRAM-SHA-256", authSource="admin")
        self.client = MongoClient(uri, **options)
        self.collection = self.client[config.database][COLLECTION]

    def close(self):
        self.client.close()
        if self.credential:
            self.credential.close()

    def indexes(self):
        try:
            return list(self.collection.list_indexes())
        except OperationFailure as e:
            if e.code == 26:
                return []
            raise

    def validate_records(self, expected, allow_missing=False):
        existing = list(self.collection.find({}).limit(17))
        known = {d["_id"]: d for d in expected}
        if len(existing) > len(expected):
            raise LabError("Unexpected catalog data; no writes. Use a new disposable database.")
        for d in existing:
            if d.get("_id") not in known or d != known[d["_id"]]:
                raise LabError(
                    "Catalog differs from immutable materialization; user edits preserved, use a new database."
                )
        if not allow_missing and len(existing) != len(expected):
            raise LabError("Catalog not fully seeded. Run the scoped --seed command first.")
        return existing

    def seed(self, records):
        self.c.validate(writes=True)
        # Full materialization + full existing catalog validation before index OR document mutation.
        if len(records) != 16 or len({d["_id"] for d in records}) != 16:
            raise LabError("Invalid seed membership.")
        for d in records:
            vector(d["embedding"])
        self.validate_records(records, allow_missing=True)
        present = catalog_compatible(self.indexes())
        if not present:
            self.collection.database.command({"createIndexes": COLLECTION, "indexes": [INDEX]})
            if not catalog_compatible(self.indexes()):
                raise LabError("Index not yet visible; no cleanup. Retry seed later.")
        result = self.collection.bulk_write(
            [UpdateOne({"_id": d["_id"]}, {"$setOnInsert": d}, upsert=True) for d in records], ordered=True
        )
        self.validate_records(records)
        return {"inserted": result.upserted_count, "existing": result.matched_count, "index": INDEX}

    def ready(self, records):
        self.validate_records(records)
        if not catalog_compatible(self.indexes()):
            raise LabError("Required IVF index missing. Run scoped --seed to validate and repair safely.")

    def keyword(self, text, filters, k):
        ts = tokens(text)
        if not ts:
            return []
        predicate = filters_query(filters)
        pattern = r"\b(?:" + "|".join(re.escape(t) for t in ts) + r")\b"
        predicate["$or"] = [
            {"title": {"$regex": pattern, "$options": "i"}},
            {"text": {"$regex": pattern, "$options": "i"}},
        ]
        candidates = list(self.collection.find(predicate, {"embedding": 0}).limit(17))
        rows = [{"document": public_doc(d), "score": lexical_score(document_text(d), text)} for d in candidates]
        return sorted((r for r in rows if r["score"] > 0), key=lambda r: (-r["score"], r["document"]["_id"]))[:k]

    def vector(self, query, filters, k):
        vector(query)
        # The complete 16-record tiny corpus is requested, then exact metadata filters applied.
        # This avoids guessing tier-specific prefilter support. Not scalable ANN filtered search.
        pipeline = [
            {"$search": {"cosmosSearch": {"vector": query, "path": "embedding", "k": 16}, "returnStoredSource": True}},
            {"$project": {"document": "$$ROOT", "score": {"$meta": "searchScore"}}},
        ]
        rows = list(self.collection.aggregate(pipeline))
        if len(rows) != 16 or len({r["document"]["_id"] for r in rows}) != 16:
            raise LabError("Vector index is not fully serving the 16-record corpus; retry after indexing completes.")
        result = []
        for row in rows:
            score, doc = row.get("score"), row["document"]
            if type(score) not in (int, float) or not math.isfinite(score):
                raise LabError("Service returned an invalid score.")
            if all(doc.get(key) == value for key, value in filters.items() if value is not None):
                result.append({"document": public_doc(doc), "score": score})
        return result[:k]
