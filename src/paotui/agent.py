"""Agent 的构建入口。

CLI 只使用 open_sync_agent 与同步 stream；server 只使用 open_async_agent 与
astream。两套入口绝不混用，避免在错误的执行模型中使用 SQLite checkpoint。
"""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from paotui.config import AppConfig
from paotui.models import create_chat_model
from paotui.prompts import build_system_prompt
from paotui.tools import get_tools


def build_agent(config: AppConfig, *, checkpointer: Any = None) -> Any:
    """构造已编译的 agent 图。"""
    return create_agent(
        create_chat_model(config),
        get_tools(config),
        system_prompt=build_system_prompt(config),
        checkpointer=checkpointer,
    )


@contextmanager
def open_sync_agent(config: AppConfig) -> Iterator[Any]:
    """在同步 SQLite checkpoint 生命周期内构造 agent。"""
    storage_dir = Path(config.storage.dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    database_path = storage_dir / "paotui.db"

    with SqliteSaver.from_conn_string(str(database_path)) as saver:
        saver.setup()
        try:
            saver.conn.execute("PRAGMA journal_mode=WAL")
            saver.conn.execute("PRAGMA busy_timeout=5000")
        except Exception:
            pass
        yield build_agent(config, checkpointer=saver)


@asynccontextmanager
async def open_async_agent(config: AppConfig) -> AsyncIterator[Any]:
    """在异步 SQLite checkpoint 生命周期内构造 agent。"""
    storage_dir = Path(config.storage.dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    database_path = storage_dir / "paotui.db"

    async with AsyncSqliteSaver.from_conn_string(str(database_path)) as saver:
        await saver.setup()
        try:
            await saver.conn.execute("PRAGMA journal_mode=WAL")
            await saver.conn.execute("PRAGMA busy_timeout=5000")
            await saver.conn.commit()
        except Exception:
            pass
        yield build_agent(config, checkpointer=saver)
