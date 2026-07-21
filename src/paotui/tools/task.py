"""临时子助手工具。"""

import asyncio
import threading
from contextvars import ContextVar
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool

from paotui.config import AppConfig
from paotui.models import create_chat_model
from paotui.prompts import build_subagent_prompt

_MAX_RESULT_CHARS = 20_000
_TASK_DESCRIPTION = (
    "把一个可以独立完成的子任务交给一个临时小助手去做，返回它的执行结果。"
    "description 要把任务背景和要求写完整，因为小助手看不到当前对话"
)


def _message_text(message: Any) -> str:
    text = getattr(message, "text", "")
    if isinstance(text, str):
        return text
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else str(content)


def _truncate_result(text: str) -> str:
    """子任务结果太长就截断。"""
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return f"{text[:_MAX_RESULT_CHARS]}\n（结果已截断，仅显示前 {_MAX_RESULT_CHARS} 个字符）"


def make_task_tool(config: AppConfig):
    """建一个带并发上限的临时子助手工具。"""
    semaphore = threading.Semaphore(config.tools.task.max_concurrency)
    sync_semaphore_held: ContextVar[bool] = ContextVar(
        "sync_semaphore_held", default=False
    )

    async def _run_task(description: str) -> str:
        semaphore_already_held = sync_semaphore_held.get()
        if not semaphore_already_held:
            await asyncio.to_thread(semaphore.acquire)

        from paotui.tools import get_tools

        try:
            child = create_agent(
                create_chat_model(config),
                get_tools(config, with_task=False),
                system_prompt=build_subagent_prompt(config),
            )
            try:
                result = await asyncio.wait_for(
                    child.ainvoke({"messages": [HumanMessage(description)]}),
                    timeout=config.tools.task.timeout_seconds,
                )
            except asyncio.TimeoutError:
                return f"错误：子任务超时（{config.tools.task.timeout_seconds}s）"
            except Exception as error:
                return f"错误：子任务执行失败（{error}）"

            messages = result.get("messages", [])
            if not messages:
                return ""
            return _truncate_result(_message_text(messages[-1]))
        finally:
            if not semaphore_already_held:
                semaphore.release()

    def run_task_sync(description: str) -> str:
        """给同步工具调用用。"""
        with semaphore:
            token = sync_semaphore_held.set(True)
            try:
                return asyncio.run(_run_task(description))
            finally:
                sync_semaphore_held.reset(token)

    return StructuredTool.from_function(
        func=run_task_sync,
        coroutine=_run_task,
        name="task",
        description=_TASK_DESCRIPTION,
    )
