from dataclasses import replace

import pytest

from search_lab.config import LabError, validate_endpoint, validate_uri
from search_lab.database import INDEX, catalog_compatible, filters_query


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://a.openai.azure.com",
        "https://evil.test",
        "https://a.openai.azure.com.evil.test",
        "https://a.openai.azure.com:444",
        "https://user:pass@a.openai.azure.com",
        "https://a.openai.azure.com/path",
        "https://a.openai.azure.com?x=y",
        "https://a.openai.azure.com/#fragment",
        "https://127.0.0.1",
    ],
)
def test_endpoint_fail_closed(endpoint):
    with pytest.raises(LabError):
        validate_endpoint(endpoint)


@pytest.mark.parametrize(
    "uri",
    [
        "mongodb://localhost/test",
        "mongodb+srv://a:b@evil.test",
        "mongodb+srv://a:b@unit.mongocluster.cosmos.azure.com/?tls=false",
        "mongodb+srv://a:b@unit.mongocluster.cosmos.azure.com/?proxyHost=evil.test",
        "mongodb+srv://a:b@unit.mongocluster.cosmos.azure.com/?tls=true&tls=true",
        "mongodb+srv://a:b@unit.mongocluster.cosmos.azure.com/production",
        "mongodb+srv://a:b@unit.mongocluster.cosmos.azure.com/?authMechanism=PLAIN",
    ],
)
def test_database_fail_closed(uri):
    with pytest.raises(LabError):
        validate_uri(uri)


def test_native_valid():
    uri = "mongodb+srv://user:password@unit.mongocluster.cosmos.azure.com/?tls=true&retryWrites=false"
    assert validate_uri(uri) == uri


def test_scoped_consent(config):
    with pytest.raises(LabError):
        config.validate(writes=True)
    assert replace(config, consent=config.database + "/catalog_v1").validate(writes=True)
    with pytest.raises(LabError):
        replace(config, database="production").validate()


def test_entire_index_catalog_checked():
    assert catalog_compatible([dict(INDEX, v=2)])
    assert not catalog_compatible([{"name": "_id_", "key": {"_id": 1}}])
    for bad in [
        dict(INDEX, partialFilterExpression={"region": "north"}),
        {"name": "ttl", "key": {"created": 1}, "expireAfterSeconds": 2},
        dict(INDEX, cosmosSearchOptions=dict(INDEX["cosmosSearchOptions"], numLists=2)),
    ]:
        with pytest.raises(LabError):
            catalog_compatible([INDEX, bad])


def test_filter_is_equality_not_operator():
    assert filters_query({"category": "office", "region": None}) == {"category": {"$eq": "office"}}
