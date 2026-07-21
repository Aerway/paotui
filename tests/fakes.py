"""Agent 契约测试使用的模型替身。"""

from collections.abc import Iterator
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGenerationChunk


class FakeToolCallingModel(FakeMessagesListChatModel):
    """支持工具绑定且可按顺序返回消息的假模型。"""

    error: Exception | None = None

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FakeToolCallingModel":
        """假模型不需要真正绑定工具。"""
        return self

    def _generate(self, *args: Any, **kwargs: Any) -> Any:
        if self.error is not None:
            raise self.error
        return super()._generate(*args, **kwargs)

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """以 AIMessageChunk 形式返回预设消息，覆盖真实流式事件形状。"""
        result = self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        message = result.generations[0].message
        if not isinstance(message, AIMessage):
            raise TypeError("假模型只支持 AIMessage 响应")
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content=message.content,
                id=message.id,
                tool_calls=message.tool_calls,
                chunk_position="last",
            )
        )
