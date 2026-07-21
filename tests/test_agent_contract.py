from pathlib import Path

import pytest
from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from paotui.agent import open_sync_agent
from paotui.config import AppConfig
from paotui.events import (
    DoneEvent,
    ErrorEvent,
    TokenEvent,
    ToolEvent,
    run_stream_async,
    run_stream_sync,
)
from tests.fakes import FakeToolCallingModel


@tool
def echo(text: str) -> str:
    """原样返回输入文本。"""
    return text


def build_test_agent() -> object:
    model = FakeToolCallingModel(
        responses=[
            AIMessage(
                content="工具前文本",
                tool_calls=[{"name": "echo", "args": {"text": "你好"}, "id": "echo-1"}],
            ),
            AIMessage(content="最终答案"),
        ]
    )
    return create_agent(model, [echo], checkpointer=InMemorySaver())


def test_sync_stream_reports_tool_calls_and_final_answer() -> None:
    agent = build_test_agent()
    assert {"model", "tools"}.issubset(agent.get_graph().nodes)

    events = list(run_stream_sync(agent, "请回显", "sync-tool"))

    tool_events = [event for event in events if isinstance(event, ToolEvent)]
    token_text = "".join(event.text for event in events if isinstance(event, TokenEvent))

    assert [(event.name, event.status) for event in tool_events] == [
        ("echo", "start"),
        ("echo", "end"),
    ]
    assert token_text == "工具前文本最终答案"
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].text == "最终答案"


def test_same_thread_keeps_conversation_history() -> None:
    agent = build_test_agent()
    thread_id = "continued-thread"
    config = {"configurable": {"thread_id": thread_id}}

    list(run_stream_sync(agent, "第一轮", thread_id))
    first_count = len(agent.get_state(config).values["messages"])
    list(run_stream_sync(agent, "第二轮", thread_id))
    second_count = len(agent.get_state(config).values["messages"])

    assert second_count > first_count


@pytest.mark.asyncio
async def test_async_stream_matches_sync_contract() -> None:
    events = [event async for event in run_stream_async(build_test_agent(), "请回显", "async-tool")]

    assert [(event.name, event.status) for event in events if isinstance(event, ToolEvent)] == [
        ("echo", "start"),
        ("echo", "end"),
    ]
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].text == "最终答案"


def test_stream_returns_error_event_instead_of_raising() -> None:
    model = FakeToolCallingModel(
        responses=[AIMessage(content="不会使用")], error=RuntimeError("模型故障")
    )
    agent = create_agent(model, checkpointer=InMemorySaver())

    events = list(run_stream_sync(agent, "你好", "error-thread"))

    assert len(events) == 1
    assert isinstance(events[0], ErrorEvent)
    assert events[0].message == "模型故障"


def test_sync_agent_context_manager_opens_database(tmp_path: Path) -> None:
    config = AppConfig.model_validate(
        {
            "model": {"name": "test-model", "api_key": "test-key"},
            "storage": {"dir": str(tmp_path / "storage")},
        }
    )

    with open_sync_agent(config) as agent:
        assert agent is not None

    assert (tmp_path / "storage" / "paotui.db").is_file()
