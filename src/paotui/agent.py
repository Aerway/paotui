"""Agent 怎么建。

CLI 用 open_sync_agent 和 stream；server 用 open_async_agent 和 astream。
SQLite saver 分同步、异步两套，别混用。
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
    """建好一个能直接跑的 agent。"""
    return create_agent(
        create_chat_model(config),
        get_tools(config),
        system_prompt=build_system_prompt(config),
        checkpointer=checkpointer,
    )


@contextmanager
def open_sync_agent(config: AppConfig) -> Iterator[Any]:
    """给 CLI 用：开着 sqlite 存档的同步 agent。"""
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
    """给 server 用：开着 sqlite 存档的异步 agent。"""
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
