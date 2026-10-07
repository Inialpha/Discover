from pathlib import Path
import pytest
from discover.config import Settings


@pytest.fixture
def settings():
    return Settings(qloo_api_key="secret-test-key", qloo_base_url="https://mock.invalid", qloo_timeout=5, qloo_retries=1,
                    llm_api_key=None, llm_base_url=None, llm_model=None, llm_timeout=5)


@pytest.fixture
def examples():
    return Path(__file__).resolve().parents[2] / "entity_examples"
