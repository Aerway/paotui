from pathlib import Path

from paotui.config import AppConfig
from paotui.tools import get_tools


def make_config(
    *,
    files_enabled: bool = True,
    shell_enabled: bool = True,
    search_enabled: bool = True,
    fetch_enabled: bool = True,
) -> AppConfig:
    """创建只关注工具开关的应用配置。"""
    return AppConfig.model_validate(
        {
            "model": {"name": "test-model"},
            "tools": {
                "files": {"enabled": files_enabled},
                "shell": {"enabled": shell_enabled},
                "search": {"enabled": search_enabled},
                "fetch": {"enabled": fetch_enabled},
            },
        }
    )


def test_get_tools_assembles_all_enabled_tools(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    names = {item.name for item in get_tools(make_config())}

    assert names == {
        "read_file",
        "write_file",
        "edit_file",
        "list_dir",
        "grep_files",
        "run_shell",
        "web_search",
        "web_fetch",
        "task",
    }


def test_get_tools_can_disable_file_tools(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    names = {item.name for item in get_tools(make_config(files_enabled=False))}

    assert {"read_file", "write_file", "edit_file", "list_dir", "grep_files"}.isdisjoint(names)
    assert "run_shell" in names


def test_get_tools_can_disable_shell_tool(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    names = {item.name for item in get_tools(make_config(shell_enabled=False))}

    assert "run_shell" not in names
    assert {"read_file", "write_file", "edit_file", "list_dir", "grep_files"}.issubset(names)


def test_get_tools_can_disable_search_and_fetch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    names = {
        item.name
        for item in get_tools(make_config(search_enabled=False, fetch_enabled=False))
    }

    assert "web_search" not in names
    assert "web_fetch" not in names
