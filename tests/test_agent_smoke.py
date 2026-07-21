
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

import paotui.agent as agent_module
from paotui.config import AppConfig
from paotui.events import DoneEvent, ToolEvent, run_stream_sync
from tests.fakes import FakeToolCallingModel


def test_agent_runs_file_tool_and_returns_final_answer(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    model = FakeToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {"path": "report.md", "content": "报告内容"},
                        "id": "write-report",
                    }
                ],
            ),
            AIMessage(content="报告写好了"),
        ]
    )
    monkeypatch.setattr(agent_module, "create_chat_model", lambda _config: model)
    config = AppConfig.model_validate(
        {
            "model": {"name": "test-model"},
            "tools": {"shell": {"allowed_commands": ["echo"]}},
        }
    )

    agent = agent_module.build_agent(config, checkpointer=InMemorySaver())
    events = list(run_stream_sync(agent, "写一份报告", "smoke-test"))

    tool_events = [event for event in events if isinstance(event, ToolEvent)]
    assert [(event.name, event.status) for event in tool_events] == [
        ("write_file", "start"),
        ("write_file", "end"),
    ]
    assert isinstance(events[-1], DoneEvent)
    assert events[-1].text == "报告写好了"
    assert (tmp_path / "report.md").read_text(encoding="utf-8") == "报告内容"
    assert {item.name for item in agent_module.get_tools(config)} == {
        "read_file",
        "write_file",
        "edit_file",
        "list_dir",
        "grep_files",
        "run_shell",
        "web_search",
        "web_fetch",
        "task",
    }
