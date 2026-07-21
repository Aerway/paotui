"""命令行入口。"""

from collections.abc import Iterable
from pathlib import Path
from uuid import uuid4

import typer
from rich.console import Console
from rich.text import Text

from paotui.agent import open_sync_agent
from paotui.config import AppConfig, load_config
from paotui.events import DoneEvent, ErrorEvent, StreamEvent, TokenEvent, ToolEvent, run_stream_sync

CONFIG_TEMPLATE = """# 跑腿的配置文件。复制成 config.yaml 再改。
# 模型：任何 OpenAI Chat Completions 兼容、支持工具调用的服务都行
model:
  provider: openai        # openai（兼容端点都算）或 anthropic（要装 paotui[anthropic]）
  name: deepseek-chat
  api_key: $DEEPSEEK_API_KEY   # $VAR 会从环境变量/.env 里取
  base_url: https://api.deepseek.com
  # temperature: 0.7

tools:
  search:
    enabled: true
    backend: ddgs         # ddgs（免费，不保证稳定）或 tavily（要 TAVILY_API_KEY）
    max_results: 8
  fetch:
    enabled: true
    max_chars: 20000
  files:
    enabled: true
  shell:
    enabled: true
    allowed_commands: [ls, cat, head, tail, grep, find, wc, date, uname]
    timeout_seconds: 60
    allow_all: false      # 开了就啥命令都能跑，后果自负
  task:
    enabled: true
    max_concurrency: 2
    timeout_seconds: 600

storage:
  dir: .paotui            # 会话记录（sqlite）放这
"""

ENV_TEMPLATE = """# 默认示例走 DeepSeek，填入自己的密钥。
DEEPSEEK_API_KEY=

# 可选：使用其他 OpenAI 兼容服务时填这个。
OPENAI_API_KEY=

# 可选：使用 Anthropic 前先安装 paotui[anthropic]。
ANTHROPIC_API_KEY=

# 可选：作为搜索的备用服务。
TAVILY_API_KEY=
"""


app = typer.Typer(
    help="跑腿：会搜网页、读网页、写文件、跑命令的小助手",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def _new_thread_id() -> str:
    """生成短会话 ID，方便续聊。"""
    return uuid4().hex[:8]


def _print_error(message: str) -> None:
    console.print(Text(message, style="red"))


def _load_config_or_exit(path: Path | None) -> AppConfig:
    """加载配置；常见错误直接显示给用户。"""
    try:
        return load_config(path)
    except (FileNotFoundError, ValueError) as error:
        _print_error(str(error))
        raise typer.Exit(code=1) from error


def render_events(events: Iterable[StreamEvent]) -> str:
    """把事件打印到终端，返回最后的回答。"""
    for event in events:
        if isinstance(event, TokenEvent):
            console.print(event.text, end="", markup=False, highlight=False)
            console.file.flush()
        elif isinstance(event, ToolEvent):
            if event.status == "start":
                console.print(Text(f"→ {event.name} {event.detail}", style="dim"))
            else:
                console.print(Text(f"✓ {event.name}"))
        elif isinstance(event, DoneEvent):
            console.print()
            return event.text
        elif isinstance(event, ErrorEvent):
            _print_error(event.message)
            raise typer.Exit(code=1)

    return ""


@app.command()
def run(
    question: str = typer.Argument(..., help="想让跑腿做的事"),
    output: Path | None = typer.Option(None, "-o", "--output", help="把最终回答存到文件"),
    thread: str | None = typer.Option(None, "--thread", help="会话编号，可用来续聊"),
    config: Path | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """问一件事。"""
    app_config = _load_config_or_exit(config)
    thread_id = thread or _new_thread_id()

    with open_sync_agent(app_config) as agent:
        answer = render_events(run_stream_sync(agent, question, thread_id))

    if output is not None:
        output.write_text(answer, encoding="utf-8")
        console.print(f"已保存到 {output}")


@app.command()
def chat(
    thread: str | None = typer.Option(None, "--thread", help="会话编号，可用来续聊"),
    config: Path | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """进聊天模式。"""
    app_config = _load_config_or_exit(config)
    thread_id = thread or _new_thread_id()
    console.print(f"当前会话：{thread_id}（输入 exit、quit、q 或 Ctrl-D 退出）")

    with open_sync_agent(app_config) as agent:
        while True:
            try:
                question = input("你：")
            except (EOFError, KeyboardInterrupt):
                console.print("\n再见。")
                return

            if not question.strip():
                continue
            if question.strip().lower() in {"exit", "quit", "q"}:
                console.print("再见。")
                return
            render_events(run_stream_sync(agent, question, thread_id))


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="监听地址"),
    port: int = typer.Option(8000, "--port", help="监听端口"),
    config: Path | None = typer.Option(None, "--config", help="配置文件路径"),
) -> None:
    """启动 HTTP 服务。"""
    app_config = _load_config_or_exit(config)

    import uvicorn

    from paotui.server import create_app

    uvicorn.run(create_app(app_config), host=host, port=port)


@app.command()
def init() -> None:
    """写出配置模板。"""
    for filename, content in (("config.yaml", CONFIG_TEMPLATE), (".env", ENV_TEMPLATE)):
        path = Path.cwd() / filename
        if path.exists():
            console.print(f"{filename} 已存在，跳过不覆盖。")
            continue
        path.write_text(content, encoding="utf-8")
        console.print(f"已生成 {filename}")

    console.print("下一步：去 .env 填 key，然后 paotui run 试试。")
