"""临时子助手工具测试。"""

import asyncio
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from paotui.config import AppConfig
from paotui.tools import get_tools
from paotui.tools import task as task_module
from tests.fakes import FakeToolCallingModel


def make_config(*, enabled: bool = True, timeout_seconds: int = 600) -> AppConfig:
    """创建 task 工具测试配置。"""
    return AppConfig.model_validate(
        {
            "model": {"name": "test-model"},
            "tools": {"task": {"enabled": enabled, "timeout_seconds": timeout_seconds}},
        }
    )


async def test_task_returns_subagent_result(monkeypatch) -> None:
    model = FakeToolCallingModel(responses=[AIMessage(content="子任务完成")])
    monkeypatch.setattr(task_module, "create_chat_model", lambda _config: model)

    result = await task_module.make_task_tool(make_config()).ainvoke({"description": "完成子任务"})

    assert "子任务完成" in result


async def test_task_returns_timeout_error(monkeypatch) -> None:
    class SlowFakeToolCallingModel(FakeToolCallingModel):
        async def _agenerate(self, *args: Any, **kwargs: Any) -> Any:
            await asyncio.sleep(5)
            return await super()._agenerate(*args, **kwargs)

    model = SlowFakeToolCallingModel(responses=[AIMessage(content="不会返回")])
    monkeypatch.setattr(task_module, "create_chat_model", lambda _config: model)

    result = await task_module.make_task_tool(make_config(timeout_seconds=1)).ainvoke(
        {"description": "会超时的子任务"}
    )

    assert result == "错误：子任务超时（1s）"


def test_task_supports_sync_agent_stream(monkeypatch) -> None:
    child_model = FakeToolCallingModel(responses=[AIMessage(content="子任务完成")])
    monkeypatch.setattr(task_module, "create_chat_model", lambda _config: child_model)
    parent_model = FakeToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {"description": "完成子任务"},
                        "id": "task-1",
                    }
                ],
            ),
            AIMessage(content="终答正确"),
        ]
    )
    agent = create_agent(
        parent_model,
        [task_module.make_task_tool(make_config())],
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "sync-task"}}

    list(agent.stream({"messages": [("user", "请完成子任务")]}, config))

    assert agent.get_state(config).values["messages"][-1].content == "终答正确"


def test_get_tools_excludes_task_for_subagent_and_includes_it_for_parent(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config = make_config()

    assert "task" not in {item.name for item in get_tools(config, with_task=False)}
    assert "task" in {item.name for item in get_tools(config)}


def test_get_tools_respects_task_switch(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert "task" not in {item.name for item in get_tools(make_config(enabled=False))}
