# 跑腿 paotui

跑腿（paotui）是一个轻量的 agent 助手：会搜网页、读网页、读写文件、跑命令，还能派个临时「小弟」去干子任务。提供终端 CLI 和本机 HTTP SSE 服务两种用法，会话存在本地 SQLite 里，随时可以续聊。

## 能干啥

跑腿有下面九个工具，模型会按需要调用；每一项都能在 `config.yaml` 里单独开关：

1. `web_search`：搜公开网页，给出标题、链接和摘要。默认用免费的 `ddgs`，也可以换成 Tavily。
2. `web_fetch`：把一个公开网页抓下来，尽量提取成 Markdown 正文，方便接着读。
3. `read_file`：读工作目录里的文本文件。
4. `write_file`：在工作目录里新建或完整写入文本文件。
5. `edit_file`：精确替换文件中的一段文字，待替换内容必须刚好出现一次。
6. `list_dir`：列出工作目录里的目录内容。
7. `grep_files`：用正则在工作目录的文本文件中找内容。
8. `run_shell`：在工作目录里跑一条受限命令。
9. `task`：把能独立完成的小事交给临时“小弟”，等它把结果带回来。

它有两种用法：

- CLI：在终端里问问题、连续聊天，或者把最终回答写进文件。
- HTTP：启动本机服务后，别的程序可以通过 SSE 接收实时输出。

会话会保存在 SQLite 里。CLI 的 `--thread` 和 HTTP 的 `thread_id` 都可以拿来续聊；不传时会自动生成一个短会话编号。

## 快速开始

需要 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
git clone <仓库地址> paotui
cd paotui
uv sync
```

生成本地配置。已有同名 `config.yaml` 或 `.env` 时，`init` 会跳过，不会覆盖。

```bash
uv run paotui init
```

然后打开 `.env`，填入：

```dotenv
DEEPSEEK_API_KEY=你的密钥
```

默认配置用的是 DeepSeek。想换别家也行：改 `config.yaml` 里的 `model` 段，填成支持工具调用的 OpenAI Chat Completions 兼容端点即可。

问一次问题，并把最终答案保存成文件：

```bash
uv run paotui run "帮我查查 XXX" -o report.md
```

打开持续聊天：

```bash
uv run paotui chat
```

启动时会打印当前会话号。下次用它续聊：

```bash
uv run paotui chat --thread xxx
```

`run` 也支持同样的 `--thread xxx`；需要使用别处的配置文件时，三个命令都可以加 `--config 路径`。

## 配置说明

`paotui init` 生成的 `config.yaml` 与 [config.example.yaml](config.example.yaml) 一样。配置值写成 `$变量名` 或 `${变量名}` 时，会从环境变量和当前目录的 `.env` 读取。

| 段 | 字段 | 说明 |
| --- | --- | --- |
| `model` | `provider` | `openai` 或 `anthropic`。`openai` 指 OpenAI Chat Completions 兼容且支持工具调用的端点；用 `anthropic` 前要安装 extra：`uv sync --extra anthropic`。 |
| `model` | `name`、`api_key`、`base_url`、`temperature` | 模型名、密钥、服务地址和可选温度。示例里是 `deepseek-chat`、`$DEEPSEEK_API_KEY` 与 `https://api.deepseek.com`。 |
| `tools.search` | `enabled`、`backend`、`max_results` | 网页搜索开关、搜索后端和最多结果数。后端是 `ddgs` 或 `tavily`；Tavily 需要安装 `paotui[tavily]` 并设置 `TAVILY_API_KEY`。 |
| `tools.fetch` | `enabled`、`max_chars` | 网页正文抓取开关和返回正文的最大字符数。 |
| `tools.files` | `enabled` | 五个工作目录文件工具的总开关。 |
| `tools.shell` | `enabled`、`allowed_commands`、`timeout_seconds`、`allow_all` | 命令工具开关、允许命令名单、超时秒数，以及是否放行所有命令。示例名单是 `ls`、`cat`、`head`、`tail`、`grep`、`find`、`wc`、`date`、`uname`。 |
| `tools.task` | `enabled`、`max_concurrency`、`timeout_seconds` | 子任务开关、并发上限和每个子任务的超时秒数。 |
| `storage` | `dir` | SQLite 会话记录目录；默认是 `.paotui`，数据库文件名是 `paotui.db`。 |

除了把工具设为 `enabled: false`，也可以只改参数。例如默认搜索最多返回 8 条，抓取最多返回 20000 个字符，shell 超时 60 秒，子任务最多并发 2 个、单个超时 600 秒。

## HTTP 服务

启动服务：

```bash
uv run paotui serve
```

默认监听 `127.0.0.1:8000`。存活检查：

```bash
curl http://127.0.0.1:8000/health
```

它会返回：

```json
{"status":"ok","name":"paotui"}
```

聊天接口是 `POST /api/chat`。请求体为 `{"message":"..."}`，也可以带上 `thread_id` 续聊：

```bash
curl -N http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"帮我查查 XXX","thread_id":"xxx"}'
```

响应是 SSE 流，事件含义如下：

| 事件 | 说明 |
| --- | --- |
| `meta` | 本次请求实际使用的 `thread_id`，未传时可用它继续下一轮。 |
| `token` | 模型刚生成的一小段文本。 |
| `tool` | 工具调用的开始或结束，带工具名、状态和简短参数/结果信息。 |
| `done` | 本次正常结束，带最终文本。 |
| `error` | 本次执行出错，带错误信息。 |

空消息会返回 400；消息超过 10000 个字符也会返回 400。同一个 `thread_id` 同时只能跑一条请求，撞上时会返回 409，等上一条结束再发。


## 开发

```bash
make install
make test
make lint
make format
```

测试全离线，不需要模型密钥。

## License

[MIT](LICENSE)
