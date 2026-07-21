"""装配工具。"""

from pathlib import Path

from paotui.config import AppConfig
from paotui.tools.fetch import make_fetch_tool
from paotui.tools.files import make_file_tools
from paotui.tools.search import make_search_tool
from paotui.tools.shell import make_shell_tool
from paotui.tools.task import make_task_tool


def get_tools(config: AppConfig, *, with_task: bool = True) -> list:
    """按配置取启用的工具。"""
    root = Path.cwd()
    tools = []
    if config.tools.files.enabled:
        tools.extend(make_file_tools(root))
    if config.tools.shell.enabled:
        tools.append(make_shell_tool(config.tools.shell, root))
    if config.tools.search.enabled:
        tools.append(make_search_tool(config.tools.search))
    if config.tools.fetch.enabled:
        tools.append(make_fetch_tool(config.tools.fetch))
    if config.tools.task.enabled and with_task:
        tools.append(make_task_tool(config))
    return tools
