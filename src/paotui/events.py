"""CLI 和 SSE 共用的事件。"""

import json
from collections.abc import AsyncIterator, Iterator
from contextlib import aclosing, closing
from typing import Any, Literal

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from pydantic import BaseModel


class TokenEvent(BaseModel):
    """一段模型输出。"""

    type: Literal["token"] = "token"
    text: str


class ToolEvent(BaseModel):
    """工具开始或结束。"""

    type: Literal["tool"] = "tool"
    name: str
    status: Literal["start", "end"]
    detail: str


class DoneEvent(BaseModel):
    """正常跑完。"""

    type: Literal["done"] = "done"
    text: str


class ErrorEvent(BaseModel):
    """运行报错。"""

    type: Literal["error"] = "error"
    message: str


StreamEvent = TokenEvent | ToolEvent | DoneEvent | ErrorEvent


def _message_text(message: Any) -> str:
    text = getattr(message, "text", "")
    return text if isinstance(text, str) else ""


def _shorten(value: Any) -> str:
    return str(value)[:200]


def _tool_call_detail(tool_call: dict[str, Any]) -> str:
    try:
        arguments = json.dumps(tool_call.get("args", {}), ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        arguments = str(tool_call.get("args", {}))
    return _shorten(arguments)


def _update_events(update: dict[str, Any]) -> tuple[list[ToolEvent], bool]:
    """从节点更新里找工具事件；有工具调用就清空文本缓存。"""
    events: list[ToolEvent] = []
    has_tool_calls = False

    for state_update in update.values():
        if not isinstance(state_update, dict):
            continue
        messages = state_update.get("messages", [])
        for message in messages:
            if isinstance(message, AIMessage) and message.tool_calls:
                has_tool_calls = True
                for tool_call in message.tool_calls:
                    events.append(
                        ToolEvent(
                            name=tool_call["name"],
                            status="start",
                            detail=_tool_call_detail(tool_call),
                        )
                    )
            elif isinstance(message, ToolMessage):
                events.append(
                    ToolEvent(
                        name=message.name or "工具",
                        status="end",
                        detail=_shorten(_message_text(message)),
                    )
                )

    return events, has_tool_calls


def run_stream_sync(agent: Any, user_text: str, thread_id: str) -> Iterator[StreamEvent]:
    """同步跑 agent，产出流事件。"""
    text_buffer = ""
    inputs = {"messages": [HumanMessage(user_text)]}
    config = {"configurable": {"thread_id": thread_id}}

    try:
        with closing(agent.stream(inputs, config, stream_mode=["messages", "updates"])) as stream:
            for mode, payload in stream:
                if mode == "messages":
                    message_chunk, _metadata = payload
                    if isinstance(message_chunk, AIMessageChunk):
                        text = _message_text(message_chunk)
                        if text:
                            text_buffer += text
                            yield TokenEvent(text=text)
                elif mode == "updates" and isinstance(payload, dict):
                    tool_events, has_tool_calls = _update_events(payload)
                    for event in tool_events:
                        yield event
                    if has_tool_calls:
                        text_buffer = ""
    except Exception as error:
        yield ErrorEvent(message=str(error))
        return

    yield DoneEvent(text=text_buffer)


async def run_stream_async(agent: Any, user_text: str, thread_id: str) -> AsyncIterator[StreamEvent]:
    """异步跑 agent，产出流事件。"""
    text_buffer = ""
    inputs = {"messages": [HumanMessage(user_text)]}
    config = {"configurable": {"thread_id": thread_id}}

    try:
        async with aclosing(
            agent.astream(inputs, config, stream_mode=["messages", "updates"])
        ) as stream:
            async for mode, payload in stream:
                if mode == "messages":
                    message_chunk, _metadata = payload
                    if isinstance(message_chunk, AIMessageChunk):
                        text = _message_text(message_chunk)
                        if text:
                            text_buffer += text
                            yield TokenEvent(text=text)
                elif mode == "updates" and isinstance(payload, dict):
                    tool_events, has_tool_calls = _update_events(payload)
                    for event in tool_events:
                        yield event
                    if has_tool_calls:
                        text_buffer = ""
    except Exception as error:
        yield ErrorEvent(message=str(error))
        return

    yield DoneEvent(text=text_buffer)
