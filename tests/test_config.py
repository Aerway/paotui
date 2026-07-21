from pathlib import Path

import pytest

from paotui.config import load_config


def test_loads_complete_config_and_expands_environment_variables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
model:
  provider: openai
  name: test-model
  api_key: $MODEL_KEY
  base_url: ${MODEL_URL}
  temperature: 0.3
tools:
  search:
    enabled: false
    backend: tavily
    max_results: 3
  fetch:
    enabled: false
    max_chars: 100
  files:
    enabled: false
  shell:
    enabled: false
    allowed_commands: [pwd]
    timeout_seconds: 5
    allow_all: true
  task:
    enabled: false
    max_concurrency: 4
    timeout_seconds: 30
storage:
  dir: .test-paotui
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("MODEL_KEY", "test-key")
    monkeypatch.setenv("MODEL_URL", "https://example.test")

    config = load_config(config_path)

    assert config.model.api_key == "test-key"
    assert config.model.base_url == "https://example.test"
    assert config.model.temperature == 0.3
    assert config.tools.search.backend == "tavily"
    assert config.tools.shell.allowed_commands == ["pwd"]
    assert config.tools.task.max_concurrency == 4
    assert config.storage.dir == ".test-paotui"


def test_uses_defaults_for_missing_sections(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("model:\n  name: test-model\n", encoding="utf-8")

    config = load_config(config_path)

    assert config.model.provider == "openai"
    assert config.tools.search.max_results == 8
    assert config.tools.fetch.max_chars == 20_000
    assert config.tools.files.enabled is True
    assert config.tools.shell.allowed_commands[0] == "ls"
    assert config.tools.task.timeout_seconds == 600
    assert config.storage.dir == ".paotui"


def test_rejects_missing_environment_variable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("model:\n  name: $MISSING_MODEL_NAME\n", encoding="utf-8")
    monkeypatch.delenv("MISSING_MODEL_NAME", raising=False)

    with pytest.raises(ValueError, match="MISSING_MODEL_NAME"):
        load_config(config_path)


def test_requires_config_file_in_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError, match="没找到 config.yaml"):
        load_config()


def test_keeps_partial_environment_interpolation_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("model:\n  name: model-$MODEL_NAME\n", encoding="utf-8")
    monkeypatch.setenv("MODEL_NAME", "kept")

    config = load_config(config_path)

    assert config.model.name == "model-$MODEL_NAME"
