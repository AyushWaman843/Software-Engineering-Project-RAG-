"""Shared test setup."""

import openai
import pytest

# config.py loads the developer's .env on import, and so does webdriver_manager (via scraper):
# its load_dotenv() walks up from the venv, which sits inside the repo. Import both now, during
# collection, so that can never happen mid-test after the fixture below has cleared the environment.
import config  # noqa: F401
import scraper  # noqa: F401

# Variables from .env that change LLM behaviour or spend; tests set what they need themselves.
_LLM_ENV = (
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "DEEPSEEK_MAX_TOKENS",
    "DEEPSEEK_JSON_MODE",
    "RAG_FULL_TEXT_MAX_CHARS",
    "RAG_EVIDENCE_BUDGET_CHARS",
    "RAG_TOP_K",
    "RAG_EVIDENCE_CHECKS",
    "CONFIDENCE_REFINEMENT_ENABLED",
)


def _no_real_client(*args, **kwargs):
    raise AssertionError("A test tried to create a real OpenAI client; install a fake instead.")


@pytest.fixture(autouse=True)
def _never_call_the_real_llm(monkeypatch):
    """
    A real DEEPSEEK_API_KEY in .env must never make a test spend money: the key is removed,
    and constructing a real client fails. Tests that need an LLM install a fake client.
    """
    for name in _LLM_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(openai, "OpenAI", _no_real_client)
