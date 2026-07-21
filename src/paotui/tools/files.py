"""工作目录里的文件工具。"""

import os
import re
import threading
from pathlib import Path

from langchain_core.tools import tool

_MAX_READ_CHARS = 50_000
_MAX_LIST_ITEMS = 200
_MAX_GREP_MATCHES = 100
_MAX_GREP_FILE_SIZE = 1_000_000
_SKIPPED_DIRECTORIES = {".git", ".venv", "__pycache__", ".paotui", "node_modules"}
_FILE_LOCK = threading.Lock()


def _resolve_in_root(root: Path, path_text: str) -> Path:
    """解析路径，连同软链接也得还在工作目录内。"""
    resolved_root = root.resolve()
    candidate = Path(path_text)
    resolved_path = (candidate if candidate.is_absolute() else resolved_root / candidate).resolve(
        strict=False
    )
    if not resolved_path.is_relative_to(resolved_root):
        raise ValueError("错误：只能操作工作目录内的文件")
    return resolved_path


def _truncate(text: str, limit: int, message: str) -> str:
    """文本太长就截断。"""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n（{message}）"


def make_file_tools(root: Path) -> list:
    """给指定工作目录建文件工具。"""
    resolved_root = root.resolve()

    @tool
    def read_file(path: str) -> str:
        """读取工作目录里的文本文件。

        path 可以是相对路径，也可以是目录内绝对路径。按 UTF-8 读取，解不开的字符替换；最多返回 50000 个字符。
        """
        try:
            target = _resolve_in_root(resolved_root, path)
            if not target.exists():
                return f"错误：文件不存在：{path}"
            if target.is_dir():
                return f"错误：指定路径是目录：{path}"
            with target.open(encoding="utf-8", errors="replace") as file:
                content = file.read(_MAX_READ_CHARS + 1)
            return _truncate(content, _MAX_READ_CHARS, "内容已截断，仅显示前 50000 个字符")
        except ValueError as error:
            return str(error)
        except OSError as error:
            return f"错误：读取文件失败：{error}"

    @tool
    def write_file(path: str, content: str) -> str:
        """写文本到工作目录，父目录没有会创建。

        path 是相对目标路径；content 是按 UTF-8 写入的完整文本。
        """
        try:
            target = _resolve_in_root(resolved_root, path)
            with _FILE_LOCK:
                if target.exists() and target.is_dir():
                    return f"错误：指定路径是目录：{path}"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            return f"已写入：{target.relative_to(resolved_root)}（{len(content)} 个字符）"
        except ValueError as error:
            return str(error)
        except OSError as error:
            return f"错误：写入文件失败：{error}"

    @tool
    def edit_file(path: str, old_string: str, new_string: str) -> str:
        """替换工作目录里的一段文本。

        path 是目标路径；old_string 必须刚好出现一次；new_string 是替换后的文本。
        """
        try:
            target = _resolve_in_root(resolved_root, path)
            with _FILE_LOCK:
                if not target.exists():
                    return f"错误：文件不存在：{path}"
                if target.is_dir():
                    return f"错误：指定路径是目录：{path}"
                content = target.read_text(encoding="utf-8", errors="replace")
                occurrences = content.count(old_string)
                if occurrences != 1:
                    return f"错误：待替换内容出现 {occurrences} 次，必须恰好出现一次"
                target.write_text(content.replace(old_string, new_string, 1), encoding="utf-8")
            return f"已修改：{target.relative_to(resolved_root)}"
        except ValueError as error:
            return str(error)
        except OSError as error:
            return f"错误：修改文件失败：{error}"

    @tool
    def list_dir(path: str = ".") -> str:
        """列出工作目录里的目录。

        path 是相对目录路径，默认是工作目录；最多 200 项。目录名带 /，文件名显示字节大小。
        """
        try:
            target = _resolve_in_root(resolved_root, path)
            if not target.exists():
                return f"错误：目录不存在：{path}"
            if not target.is_dir():
                return f"错误：指定路径不是目录：{path}"
            entries = sorted(target.iterdir(), key=lambda entry: entry.name)
            lines = []
            for entry in entries[:_MAX_LIST_ITEMS]:
                if entry.is_dir():
                    lines.append(f"{entry.name}/")
                else:
                    lines.append(f"{entry.name}（{entry.stat().st_size} 字节）")
            if len(entries) > _MAX_LIST_ITEMS:
                lines.append(f"（目录项已截断，仅显示前 {_MAX_LIST_ITEMS} 项）")
            return "\n".join(lines) if lines else "（空目录）"
        except ValueError as error:
            return str(error)
        except OSError as error:
            return f"错误：列目录失败：{error}"

    @tool
    def grep_files(pattern: str, path: str = ".") -> str:
        """用 Python 正则搜工作目录里的文本文件。

        pattern 是正则表达式；path 是起始文件或目录，默认是工作目录。返回“相对路径:行号:行内容”，最多 100 条。跳过隐藏目录、常见依赖目录和大于 1MB 的文件。
        """
        try:
            regex = re.compile(pattern)
        except re.error as error:
            return f"错误：正则表达式无效：{error}"

        try:
            target = _resolve_in_root(resolved_root, path)
            if not target.exists():
                return f"错误：路径不存在：{path}"

            if target.is_file():
                file_paths = [target]
            elif target.is_dir():
                file_paths = []
                for directory, directory_names, file_names in os.walk(target):
                    directory_names[:] = [
                        name
                        for name in sorted(directory_names)
                        if not name.startswith(".") and name not in _SKIPPED_DIRECTORIES
                    ]
                    file_paths.extend(Path(directory) / name for name in sorted(file_names))
            else:
                return f"错误：无法搜索该路径：{path}"

            matches = []
            for file_path in file_paths:
                try:
                    safe_file_path = _resolve_in_root(resolved_root, str(file_path))
                    if safe_file_path.stat().st_size > _MAX_GREP_FILE_SIZE:
                        continue
                    with safe_file_path.open(encoding="utf-8", errors="replace") as file:
                        for line_number, line in enumerate(file, start=1):
                            if regex.search(line):
                                relative_path = safe_file_path.relative_to(resolved_root)
                                matches.append(
                                    f"{relative_path}:{line_number}:{line.rstrip(chr(13) + chr(10))}"
                                )
                                if len(matches) == _MAX_GREP_MATCHES:
                                    matches.append(
                                        f"（命中已截断，仅显示前 {_MAX_GREP_MATCHES} 条）"
                                    )
                                    return "\n".join(matches)
                except (OSError, ValueError):
                    continue
            return "\n".join(matches) if matches else "未找到匹配内容"
        except ValueError as error:
            return str(error)
        except OSError as error:
            return f"错误：搜索文件失败：{error}"

    return [read_file, write_file, edit_file, list_dir, grep_files]
