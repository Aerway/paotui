from pathlib import Path

from langchain_core.messages import AIMessage
from typer.testing import CliRunner

import paotui.agent as agent_module
from paotui.cli import app
from tests.fakes import FakeToolCallingModel

runner = CliRunner()


def _write_config(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        """model:
  name: test-model
  api_key: test-key
storage:
  dir: .paotui-test
""",
        encoding="utf-8",
    )


def _use_fake_model(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_module,
        "create_chat_model",
        lambda _config: FakeToolCallingModel(responses=[AIMessage(content="你好呀")]),
    )


def test_init_creates_templates_without_overwriting(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    config_path = tmp_path / "config.yaml"
    env_path = tmp_path / ".env"
    assert "model:" in config_path.read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY" in env_path.read_text(encoding="utf-8")

    config_path.write_text("保留这个标记", encoding="utf-8")
    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    assert config_path.read_text(encoding="utf-8") == "保留这个标记"
    assert "跳过不覆盖" in result.output


def test_run_displays_answer_and_writes_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    _use_fake_model(monkeypatch)

    result = runner.invoke(app, ["run", "打个招呼"])

    assert result.exit_code == 0
    assert "你好呀" in result.output

    output_path = tmp_path / "out.md"
    result = runner.invoke(app, ["run", "打个招呼", "-o", str(output_path)])

    assert result.exit_code == 0
    assert output_path.read_text(encoding="utf-8") == "你好呀"


def test_run_reports_missing_default_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["run", "打个招呼"])

    assert result.exit_code == 1
    assert "没找到 config.yaml" in result.output


def test_chat_displays_answer(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    _use_fake_model(monkeypatch)

    result = runner.invoke(app, ["chat"], input="随便聊聊\nexit\n")

    assert result.exit_code == 0
    assert "你好呀" in result.output
