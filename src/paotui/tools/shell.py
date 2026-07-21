"""限制命令执行的工具。"""

import shlex
import subprocess
import threading
from pathlib import Path

from langchain_core.tools import tool

from paotui.config import ShellToolConfig

_UNSUPPORTED_SHELL_CHARACTERS = set("|&;<>`$\n\r")
_MAX_OUTPUT_CHARS = 10_000
_MAX_CAPTURE_BYTES = 200_000


def _truncate_output(text: str) -> str:
    """输出太长就截断。"""
    if len(text) <= _MAX_OUTPUT_CHARS:
        return text
    return f"{text[:_MAX_OUTPUT_CHARS]}\n（输出已截断，仅显示前 {_MAX_OUTPUT_CHARS} 个字符）"


def make_shell_tool(shell_config: ShellToolConfig, root: Path):
    """给指定工作目录建受限命令工具。"""
    resolved_root = root.resolve()

    @tool
    def run_shell(command: str) -> str:
        """在工作目录里执行一条不含 shell 语法的命令。

        command 是完整命令，按空格和引号拆参数。只跑一条；不能用管道、重定向、变量或命令连接。默认只准配置里允许的命令。
        """
        if any(character in command for character in _UNSUPPORTED_SHELL_CHARACTERS):
            return "错误：不支持 shell 语法，只能执行单条命令"

        try:
            argv = shlex.split(command)
        except ValueError as error:
            return f"错误：命令解析失败：{error}"
        if not argv:
            return "错误：命令不能为空"

        command_name = Path(argv[0]).name
        if not shell_config.allow_all and command_name not in shell_config.allowed_commands:
            allowed = "、".join(shell_config.allowed_commands)
            return f"错误：不允许执行命令“{command_name}”，允许的命令：{allowed}"

        try:
            process = subprocess.Popen(
                argv,
                shell=False,
                cwd=resolved_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            return f"错误：命令不存在：{command_name}"
        except OSError as error:
            return f"错误：执行命令失败：{error}"

        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        output_too_large = threading.Event()

        def read_output(stream, chunks: list[bytes]) -> None:
            captured_size = 0
            while chunk := stream.read(8192):
                remaining = _MAX_CAPTURE_BYTES - captured_size
                if remaining > 0:
                    chunks.append(chunk[:remaining])
                captured_size += len(chunk)
                if captured_size > _MAX_CAPTURE_BYTES:
                    output_too_large.set()
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    return

        assert process.stdout is not None
        assert process.stderr is not None
        stdout_reader = threading.Thread(target=read_output, args=(process.stdout, stdout_chunks))
        stderr_reader = threading.Thread(target=read_output, args=(process.stderr, stderr_chunks))
        stdout_reader.start()
        stderr_reader.start()

        timed_out = False
        try:
            process.wait(timeout=shell_config.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            process.wait()
        finally:
            stdout_reader.join()
            stderr_reader.join()

        if timed_out:
            return f"错误：命令超时（{shell_config.timeout_seconds}s）"

        stdout = b"".join(stdout_chunks).decode("utf-8", errors="replace")
        stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")
        if output_too_large.is_set():
            stderr = f"{stderr}\n（输出过大已终止）"

        return (
            f"exit code: {process.returncode}\n"
            f"stdout:\n{_truncate_output(stdout)}\n"
            f"stderr:\n{_truncate_output(stderr)}"
        )

    return run_shell
