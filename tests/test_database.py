from dataclasses import replace

import pytest

from search_lab.config import LabError
from search_lab.database import INDEX, Database
from search_lab.dataset import fixtures


class Cursor(list):
    def limit(self, n):
        return self[:n]


class Collection:
    def __init__(self, docs, indexes):
        self.docs = docs
        self.catalog = indexes
        self.writes = []
        self.database = self

    def find(self, query, projection=None):
        return Cursor(self.docs)

    def list_indexes(self):
        return self.catalog

    def command(self, command):
        self.writes.append(command)
        self.catalog = [INDEX]

    def bulk_write(self, operations, ordered):
        self.writes.append(operations)
        for op in operations:
            if not any(d["_id"] == op._filter["_id"] for d in self.docs):
                self.docs.append(op._doc["$setOnInsert"])
        return type("Result", (), {"upserted_count": 16, "matched_count": 0})()


def records():
    docs, _ = fixtures()
    return [dict(d, embedding=[1.0] + [0.0] * 1535, dataset_version="test", source="self", license="MIT") for d in docs]


def db(config, collection):
    obj = Database.__new__(Database)
    obj.c = replace(config, consent=config.database + "/catalog_v1")
    obj.collection = collection
    return obj


def test_missing_index_still_validates_entire_existing_catalog(config):
    docs = records()
    edited = dict(docs[0], title="User edited; preserve me")
    collection = Collection([edited], [])
    with pytest.raises(LabError, match="user edits preserved"):
        db(config, collection).seed(docs)
    assert collection.writes == []
    assert collection.docs == [edited]


def test_missing_index_on_complete_compatible_catalog_repaired(config):
    docs = records()
    collection = Collection(list(docs), [])
    db(config, collection).seed(docs)
    assert collection.writes[0] == {"createIndexes": "catalog_v1", "indexes": [INDEX]}
    for op in collection.writes[1]:
        assert set(op._doc) == {"$setOnInsert"}


def test_conflicting_unrelated_index_blocks_all_writes(config):
    collection = Collection([], [{"name": "ttl", "key": {"expires": 1}, "expireAfterSeconds": 1}])
    with pytest.raises(LabError):
        db(config, collection).seed(records())
    assert not collection.writes
