from dataclasses import replace

import pytest

from search_lab.config import Config


@pytest.fixture
def config(tmp_path):
    return Config(
        database="searchlab_disposable_test",
        endpoint="https://unit.openai.azure.com",
        deployment="search-embedding",
        model_version="1",
        host="unit.mongocluster.cosmos.azure.com",
        state_dir=tmp_path,
        api_key="unit-test-placeholder",
    )


@pytest.fixture
def paid(config):
    return replace(config, paid=True, max_calls=2)
