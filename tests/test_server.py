"""HTTP SSE 服务测试。"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from sse_starlette.sse import AppStatus

import paotui.agent as agent_module
from paotui.config import AppConfig
from paotui.server import create_app
from tests.fakes import FakeToolCallingModel


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig.model_validate(
        {
            "model": {"name": "test-model", "api_key": "test-key"},
            "storage": {"dir": str(tmp_path / ".paotui-test")},
        }
    )


def _use_fake_model(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_module,
        "create_chat_model",
        lambda _config: FakeToolCallingModel(responses=[AIMessage(content="收到")]),
    )


def _parse_sse(text: str) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    for block in text.replace("\r\n", "\n").strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        events.append((fields["event"], fields["data"]))
    return events


@pytest.fixture(autouse=True)
def _reset_sse_exit_event() -> None:
    """避免不同 TestClient 的事件循环复用 SSE 库的全局事件。"""
    AppStatus.should_exit_event = None
    yield
    AppStatus.should_exit_event = None


def test_health_returns_service_identity(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _use_fake_model(monkeypatch)

    with TestClient(create_app(_config(tmp_path))) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "name": "paotui"}


def test_chat_streams_meta_and_final_answer(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _use_fake_model(monkeypatch)

    with TestClient(create_app(_config(tmp_path))) as client:
        response = client.post("/api/chat", json={"message": "  你好  "})

    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert events[0][0] == "meta"
    assert json.loads(events[0][1])["thread_id"]
    assert any(event_type in {"token", "done"} for event_type, _data in events[1:])
    done_data = next(data for event_type, data in events if event_type == "done")
    assert json.loads(done_data)["text"] == "收到"


def test_chat_rejects_empty_and_too_long_messages(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _use_fake_model(monkeypatch)

    with TestClient(create_app(_config(tmp_path))) as client:
        empty_response = client.post("/api/chat", json={"message": "  \n\t"})
        long_response = client.post("/api/chat", json={"message": "x" * 10_001})

    assert empty_response.status_code == 400
    assert long_response.status_code == 400


def test_chat_rejects_running_thread(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _use_fake_model(monkeypatch)

    with TestClient(create_app(_config(tmp_path))) as client:
        client.app.state.active_threads.add("busy-thread")

        response = client.post(
            "/api/chat", json={"message": "继续", "thread_id": "busy-thread"}
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "该会话正在处理中，等它跑完再发"


def test_chat_returns_specified_thread_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _use_fake_model(monkeypatch)

    with TestClient(create_app(_config(tmp_path))) as client:
        response = client.post("/api/chat", json={"message": "你好", "thread_id": "my-thread"})

    events = _parse_sse(response.text)
    assert json.loads(events[0][1]) == {"thread_id": "my-thread"}
