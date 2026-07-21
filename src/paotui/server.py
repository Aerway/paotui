"""给本机或内网客户端使用的 HTTP SSE 服务。

这个服务不做鉴权，CLI 默认绑定 127.0.0.1；若要暴露到更大网络，调用方需要先补上
合适的访问控制。
"""

import json
from contextlib import asynccontextmanager, suppress
from typing import AsyncIterator
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from paotui.agent import open_async_agent
from paotui.config import AppConfig
from paotui.events import run_stream_async


class ChatRequest(BaseModel):
    """聊天接口的请求内容。"""

    message: str
    thread_id: str | None = None


def create_app(config: AppConfig) -> FastAPI:
    """按配置创建 SSE 服务。"""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with open_async_agent(config) as agent:
            app.state.agent = agent
            app.state.active_threads: set[str] = set()
            yield

    app = FastAPI(lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        """返回服务存活状态。"""
        return {"status": "ok", "name": "paotui"}

    @app.post("/api/chat")
    async def chat(request: Request, body: ChatRequest) -> EventSourceResponse:
        """启动一次 agent 运行，并把过程转换为 SSE。"""
        message = body.message.strip()
        if not message:
            raise HTTPException(status_code=400, detail="消息不能为空")
        if len(message) > 10_000:
            raise HTTPException(status_code=400, detail="消息不能超过 10000 个字符")

        thread_id = body.thread_id or uuid4().hex[:8]
        active_threads: set[str] = request.app.state.active_threads
        if thread_id in active_threads:
            raise HTTPException(status_code=409, detail="该会话正在处理中，等它跑完再发")
        active_threads.add(thread_id)

        async def event_stream() -> AsyncIterator[dict[str, str]]:
            stream = run_stream_async(request.app.state.agent, message, thread_id)
            try:
                yield {
                    "event": "meta",
                    "data": json.dumps({"thread_id": thread_id}, ensure_ascii=False),
                }
                async for event in stream:
                    yield {"event": event.type, "data": event.model_dump_json()}
            finally:
                with suppress(Exception):
                    await stream.aclose()
                active_threads.discard(thread_id)

        return EventSourceResponse(event_stream())

    return app
