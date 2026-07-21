"""读配置并校验。"""

import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    provider: Literal["openai", "anthropic"] = "openai"
    name: str
    api_key: str | None = None
    base_url: str | None = None
    temperature: float | None = None


class SearchToolConfig(BaseModel):
    enabled: bool = True
    backend: Literal["ddgs", "tavily"] = "ddgs"
    max_results: int = 8


class FetchToolConfig(BaseModel):
    enabled: bool = True
    max_chars: int = 20_000


class FilesToolConfig(BaseModel):
    enabled: bool = True


class ShellToolConfig(BaseModel):
    enabled: bool = True
    allowed_commands: list[str] = Field(
        default_factory=lambda: [
            "ls",
            "cat",
            "head",
            "tail",
            "grep",
            "find",
            "wc",
            "date",
            "uname",
        ]
    )
    timeout_seconds: int = 60
    allow_all: bool = False


class TaskToolConfig(BaseModel):
    enabled: bool = True
    max_concurrency: int = 2
    timeout_seconds: int = 600


class ToolsConfig(BaseModel):
    search: SearchToolConfig = Field(default_factory=SearchToolConfig)
    fetch: FetchToolConfig = Field(default_factory=FetchToolConfig)
    files: FilesToolConfig = Field(default_factory=FilesToolConfig)
    shell: ShellToolConfig = Field(default_factory=ShellToolConfig)
    task: TaskToolConfig = Field(default_factory=TaskToolConfig)


class StorageConfig(BaseModel):
    dir: str = ".paotui"


class AppConfig(BaseModel):
    model: ModelConfig
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)


_ENV_VALUE = re.compile(r"^\$(?:([A-Za-z_][A-Za-z0-9_]*)|\{([A-Za-z_][A-Za-z0-9_]*)\})$")


def _expand_environment_values(value: Any, location: str = "") -> Any:
    """展开值里单独写的环境变量。"""
    if isinstance(value, dict):
        return {
            key: _expand_environment_values(
                item, f"{location}.{key}" if location else str(key)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _expand_environment_values(item, f"{location}[{index}]")
            for index, item in enumerate(value)
        ]
    if not isinstance(value, str):
        return value

    match = _ENV_VALUE.fullmatch(value)
    if not match:
        return value

    variable_name = match.group(1) or match.group(2)
    environment_value = os.environ.get(variable_name)
    if environment_value is None:
        raise ValueError(f"配置项“{location}”引用的环境变量“{variable_name}”未设置")
    return environment_value


def load_config(path: str | Path | None = None) -> AppConfig:
    """读 YAML 配置。"""
    dotenv_path = Path.cwd() / ".env"
    if dotenv_path.is_file():
        load_dotenv(dotenv_path=dotenv_path)

    config_path = Path(path) if path is not None else Path.cwd() / "config.yaml"
    if not config_path.is_file():
        raise FileNotFoundError(
            "没找到 config.yaml，先复制 config.example.yaml 改一份（以后也可以用 paotui init 生成）"
        )

    with config_path.open(encoding="utf-8") as config_file:
        raw_config = yaml.safe_load(config_file)
    return AppConfig.model_validate(_expand_environment_values(raw_config))
