"""CLI 与 SSE 共用的 agent 流事件。"""

import json
from collections.abc import AsyncIterator, Iterator
from contextlib import aclosing, closing
from typing import Any, Literal

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from pydantic import BaseModel


class TokenEvent(BaseModel):
    """模型生成的一段文本。"""

    type: Literal["token"] = "token"
    text: str


class ToolEvent(BaseModel):
    """工具调用的开始或结束。"""

    type: Literal["tool"] = "tool"
    name: str
    status: Literal["start", "end"]
    detail: str


class DoneEvent(BaseModel):
    """一次正常运行完成。"""

    type: Literal["done"] = "done"
    text: str


class ErrorEvent(BaseModel):
    """一次运行出错。"""

    type: Literal["error"] = "error"
    message: str


StreamEvent = TokenEvent | ToolEvent | DoneEvent | ErrorEvent


def _message_text(message: Any) -> str:
    """从消息内容中取出可展示的文本。"""
    text = getattr(message, "text", "")
    return text if isinstance(text, str) else ""


def _shorten(value: Any) -> str:
    """把事件详情限制在适合界面展示的长度。"""
    return str(value)[:200]


def _tool_call_detail(tool_call: dict[str, Any]) -> str:
    """格式化工具调用参数。"""
    try:
        arguments = json.dumps(tool_call.get("args", {}), ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        arguments = str(tool_call.get("args", {}))
    return _shorten(arguments)


def _update_events(update: dict[str, Any]) -> tuple[list[ToolEvent], bool]:
    """从图节点更新中提取工具事件和是否应清空文本缓冲区。"""
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
    """同步运行 agent，并转换为统一流事件。"""
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
    """异步运行 agent，并转换为统一流事件。"""
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
