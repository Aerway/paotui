import sys

import pytest
from langchain_openai import ChatOpenAI

from paotui.config import AppConfig
from paotui.models import create_chat_model


def test_creates_openai_chat_model() -> None:
    config = AppConfig.model_validate(
        {"model": {"provider": "openai", "name": "test-model", "api_key": "test-key"}}
    )

    model = create_chat_model(config)

    assert isinstance(model, ChatOpenAI)


def test_requires_api_key() -> None:
    config = AppConfig.model_validate({"model": {"name": "test-model"}})

    with pytest.raises(ValueError, match="api_key"):
        create_chat_model(config)


def test_explains_how_to_install_anthropic_support(monkeypatch: pytest.MonkeyPatch) -> None:
    config = AppConfig.model_validate(
        {"model": {"provider": "anthropic", "name": "test-model", "api_key": "test-key"}}
    )
    monkeypatch.setitem(sys.modules, "langchain_anthropic", None)

    with pytest.raises(ImportError, match="uv pip install"):
        create_chat_model(config)
