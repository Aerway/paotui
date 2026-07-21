from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from paotui.tools import files as files_module
from paotui.tools.files import make_file_tools


def make_tools(root: Path) -> dict[str, object]:
    """按名称取出测试用文件工具。"""
    return {item.name: item for item in make_file_tools(root)}


def invoke(tools: dict[str, object], name: str, **arguments: str) -> str:
    """调用工具并取得字符串结果。"""
    return tools[name].invoke(arguments)  # type: ignore[union-attr]


def test_read_write_and_edit_file_round_trip(tmp_path: Path) -> None:
    tools = make_tools(tmp_path)

    assert "已写入" in invoke(tools, "write_file", path="notes/a.txt", content="第一版")
    assert invoke(tools, "read_file", path="notes/a.txt") == "第一版"
    assert "已修改" in invoke(
        tools, "edit_file", path="notes/a.txt", old_string="第一", new_string="第二"
    )
    assert invoke(tools, "read_file", path="notes/a.txt") == "第二版"


def test_read_file_stops_after_maximum_characters(tmp_path: Path) -> None:
    tools = make_tools(tmp_path)
    (tmp_path / "large.txt").write_text("甲" * 50_001, encoding="utf-8")

    result = invoke(tools, "read_file", path="large.txt")

    assert result.startswith("甲" * 50_000)
    assert "内容已截断" in result


def test_write_and_edit_wait_for_file_lock(tmp_path: Path, monkeypatch) -> None:
    tools = make_tools(tmp_path)
    (tmp_path / "notes.txt").write_text("旧内容", encoding="utf-8")
    resolved = Event()
    original_resolve = files_module._resolve_in_root

    def mark_resolved(root: Path, path_text: str) -> Path:
        resolved.set()
        return original_resolve(root, path_text)

    monkeypatch.setattr(files_module, "_resolve_in_root", mark_resolved)

    for name, arguments in (
        ("write_file", {"path": "new.txt", "content": "新内容"}),
        ("edit_file", {"path": "notes.txt", "old_string": "旧", "new_string": "新"}),
    ):
        resolved.clear()
        files_module._FILE_LOCK.acquire()
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(invoke, tools, name, **arguments)
                assert resolved.wait(timeout=1)
                assert not future.done()
                files_module._FILE_LOCK.release()
                assert future.result(timeout=1).startswith("已")
        finally:
            if files_module._FILE_LOCK.locked():
                files_module._FILE_LOCK.release()


def test_edit_file_requires_exactly_one_match(tmp_path: Path) -> None:
    tools = make_tools(tmp_path)
    (tmp_path / "text.txt").write_text("甲 甲", encoding="utf-8")

    assert "出现 0 次" in invoke(
        tools, "edit_file", path="text.txt", old_string="不存在", new_string="乙"
    )
    assert "出现 2 次" in invoke(
        tools, "edit_file", path="text.txt", old_string="甲", new_string="乙"
    )


def test_paths_outside_root_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    tools = make_tools(root)
    outside = tmp_path / "outside.txt"
    outside.write_text("外部", encoding="utf-8")

    assert invoke(tools, "read_file", path="../outside.txt") == "错误：只能操作工作目录内的文件"
    assert (
        invoke(tools, "read_file", path=str(outside)) == "错误：只能操作工作目录内的文件"
    )


def test_symlink_escape_is_rejected_for_read_and_write(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("秘密", encoding="utf-8")
    (root / "escape").symlink_to(outside, target_is_directory=True)
    tools = make_tools(root)

    assert (
        invoke(tools, "read_file", path="escape/secret.txt")
        == "错误：只能操作工作目录内的文件"
    )
    assert (
        invoke(tools, "write_file", path="escape/new.txt", content="不能写")
        == "错误：只能操作工作目录内的文件"
    )
    assert invoke(tools, "grep_files", pattern="秘密") == "未找到匹配内容"


def test_grep_limit_and_list_dir_output(tmp_path: Path) -> None:
    tools = make_tools(tmp_path)
    (tmp_path / "a.txt").write_text("needle\nother\n", encoding="utf-8")
    (tmp_path / "many.txt").write_text("".join("needle\n" for _ in range(101)), encoding="utf-8")
    (tmp_path / "folder").mkdir()

    listing = invoke(tools, "list_dir")
    assert "a.txt（" in listing
    assert "folder/" in listing

    results = invoke(tools, "grep_files", pattern="needle")
    result_lines = results.splitlines()
    assert result_lines[0] == "a.txt:1:needle"
    assert sum(1 for line in result_lines if ":" in line) == 100
    assert "命中已截断" in results
