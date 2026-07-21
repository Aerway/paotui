from pathlib import Path

from paotui.config import ShellToolConfig
from paotui.tools.shell import make_shell_tool


def invoke(tool: object, command: str) -> str:
    """调用 shell 工具并取得字符串结果。"""
    return tool.invoke({"command": command})  # type: ignore[union-attr]


def test_allowed_command_returns_exit_code_and_output(tmp_path: Path) -> None:
    tool = make_shell_tool(ShellToolConfig(allowed_commands=["echo"]), tmp_path)

    result = invoke(tool, "echo hello")

    assert "exit code: 0" in result
    assert "hello" in result


def test_unallowed_command_lists_allowed_commands(tmp_path: Path) -> None:
    tool = make_shell_tool(ShellToolConfig(allowed_commands=["echo"]), tmp_path)

    result = invoke(tool, "pwd")

    assert result.startswith("错误：")
    assert "echo" in result


def test_shell_syntax_is_rejected_even_before_execution(tmp_path: Path) -> None:
    tool = make_shell_tool(ShellToolConfig(allowed_commands=["echo"]), tmp_path)

    for command in ("echo hi | cat", "echo a; echo b", "echo $HOME"):
        assert invoke(tool, command) == "错误：不支持 shell 语法，只能执行单条命令"


def test_timeout_returns_error(tmp_path: Path) -> None:
    tool = make_shell_tool(
        ShellToolConfig(allowed_commands=["sleep"], timeout_seconds=1), tmp_path
    )

    assert invoke(tool, "sleep 5") == "错误：命令超时（1s）"


def test_large_command_output_is_limited_while_reading(tmp_path: Path) -> None:
    output_path = tmp_path / "large-output.txt"
    output_path.write_text("x" * 1_000_000, encoding="utf-8")
    tool = make_shell_tool(ShellToolConfig(allowed_commands=["cat"]), tmp_path)

    result = invoke(tool, "cat large-output.txt")

    assert "输出过大已终止" in result
    assert "输出已截断" in result
    assert len(result) < 25_000


def test_allow_all_bypasses_allowlist_but_not_shell_syntax(tmp_path: Path) -> None:
    tool = make_shell_tool(ShellToolConfig(allowed_commands=[], allow_all=True), tmp_path)

    assert "exit code: 0" in invoke(tool, "pwd")
    assert invoke(tool, "echo hi | cat") == "错误：不支持 shell 语法，只能执行单条命令"


def test_command_uses_given_working_directory(tmp_path: Path) -> None:
    (tmp_path / "visible.txt").write_text("内容", encoding="utf-8")
    tool = make_shell_tool(ShellToolConfig(allowed_commands=["ls"]), tmp_path)

    assert "visible.txt" in invoke(tool, "ls")
