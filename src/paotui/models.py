"""聊天模型的创建入口。"""

from typing import Any

from langchain_openai import ChatOpenAI

from paotui.config import AppConfig, ModelConfig


def _model_options(model_config: ModelConfig) -> dict[str, Any]:
    if model_config.api_key is None:
        raise ValueError("模型 API Key 未配置，请在配置文件里填写 api_key")

    options: dict[str, Any] = {
        "model": model_config.name,
        "base_url": model_config.base_url,
        "api_key": model_config.api_key,
    }
    if model_config.temperature is not None:
        options["temperature"] = model_config.temperature
    return options


def create_chat_model(config: AppConfig) -> Any:
    """根据配置构造聊天模型，不会在这里发起网络请求。"""
    model_config = config.model
    options = _model_options(model_config)

    if model_config.provider == "openai":
        return ChatOpenAI(**options)

    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as error:
        raise ImportError('要用 anthropic 得先装：uv pip install "paotui[anthropic]"') from error
    return ChatAnthropic(**options)
