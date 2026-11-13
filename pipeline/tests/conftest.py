import pytest

from arxiv_digest.config import load_config


@pytest.fixture
def cfg():
    return load_config()
