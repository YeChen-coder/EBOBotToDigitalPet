# 动态记忆日志

这份日志回答两个问题：新会话实际带上了什么记忆，以及服务器是否确认了这份会话配置。

## 在哪里看

宿主机文件夹：

```text
C:\Projects\ebo-ai-home\assistant-data\logs
```

当前文件是 `session-memory.jsonl`，用记事本或文本编辑器即可打开，不需要 Docker 命令。
文件使用 UTF-8，每行是一条 JSON 记录；中文直接可读，文字内部的换行保存为 `\n`，双引号
保存为 `\"`。JSON 解析后会还原成原来的文本。

容器是 `ebo-ai-home-realtime-assistant`，容器内路径为 `/data/logs/session-memory.jsonl`。
Compose 已把宿主机 `assistant-data` 挂载到容器 `/data`，所以重建容器和会话轮换不会清除日志。

## 什么时机会记

每次连接建立并发送 `session.update` 时，追加一条 `memory_injection`：

- `at`：带时区的本地时间，例如 `2026-09-07T14:30:00-0400`。
- `injection_id`：本次配置的唯一编号，与发送事件的 `event_id` 相同。
- `reason`：`startup` 是进程启动，`session_rotation` 是定时换会话，`unexpected_reconnect` 是意外断线后重新连接。
- `handoff_memory`：本次真正拼进 instructions 的上一会话摘要。
- `reconnect_memory`：本次真正拼进 instructions 的断线前逐字记录。
- `status`：`sent` 表示本地 WebSocket 发送成功；`send_failed` 表示本地发送失败。

两段原文取自同一次 instructions 拼接所使用的字符串，已经经过现有字数限制及时间筛选，
日志不会另外改写或截短它们。字段为 `""` 表示这次没有注入这一类记忆。
启动时没有动态记忆也留一条简短记录，用于区分“没有记忆”和“日志没有运行”。

随后追加一条很短的 `memory_confirmation`，使用相同的 `injection_id`，不再复制记忆正文：

| `status` | 含义 |
|---|---|
| `confirmed` | 收到 `session.updated`，而且返回的完整 instructions 与发送的字符串完全一致；记录中还包含服务端 `session_id`。 |
| `instructions_mismatch` | 收到确认事件，但返回的 instructions 不同，需要排查。 |
| `rejected` | 服务端错误明确关联到这次配置的 event ID；只记录简短错误代码。 |
| `unconfirmed` | 连接关闭前没有拿到可以核对的 instructions，无法确定服务器是否应用了配置。 |

只有 `sent`、没有后续确认记录时，不能推断服务器已经应用了配置。例如进程被强行终止就可能出现这种情况。
普通音频分块、视频图片、`response.create` 和重复确认事件不会产生记忆日志。

示例（为方便阅读进行了缩进，内容为虚构示例；实际每条占一行）：

```json
{
  "at": "2026-09-07T14:30:00-0400",
  "event": "memory_injection",
  "injection_id": "mem_example",
  "reason": "unexpected_reconnect",
  "status": "sent",
  "handoff_memory": "用户正在寻找红球。",
  "reconnect_memory": "用户: 找到了吗？\n助手: 还没有。"
}
```

同一份摘要若确实被再次注入另一个新 Session，会再次出现一次正文。这样每次注入都能独立核查，
不依赖可能已经轮换删除的旧记录。会话内的正常请求不会因此重复记录。

## 大小与轮换

已在实际 `.env` 及 `.env.example` 中加入：

```dotenv
EBO_MEMORY_LOG_PATH=/data/logs/session-memory.jsonl
EBO_MEMORY_LOG_MAX_BYTES=1048576
EBO_MEMORY_LOG_BACKUP_COUNT=3
```

按实际 UTF-8 字节数计算。下一条记录会超过 1 MiB 时，先轮换再写，记录不会被从中间拆开：

```text
session-memory.jsonl     当前正在写入
session-memory.jsonl.1   最近一份旧日志
session-memory.jsonl.2   更早的一份
session-memory.jsonl.3   最早保留的一份
```

再轮换时会覆盖最旧的 `.3`。默认这四个文件合计最多 4 MiB。旧内容被覆盖后不能从这组日志找回。
这是按大小轮换，低频运行时可能保留很久，不是按天自动删除。

`MAX_BYTES` 可设为 262144 到 16777216；`BACKUP_COUNT` 可设为 1 到 20，不能设为 0 来关闭限制。
下限确保现有两段最大长度记忆能够完整放入单条记录。改 `.env` 后使用现有的
“应用 EBO Prompt 修改”脚本重建 Assistant 配置即可；第一次安装本功能需要构建包含新代码的镜像。
如果改小容量或备份数量，之前已经存在的旧备份不会立即被重新切分或清除；上面的 4 MiB 上限对应默认配置下生成的文件。

日志写入失败不会中断语音服务，`/health` 的 `memory_log_last_error` 会显示错误。
`memory_log_path`、`memory_log_records_written`、`memory_log_last_written_at` 可以检查实际路径与最近写入状态，
其中条数是本次进程启动后的成功写入次数。下一次写入成功会清除错误状态。

本功能从部署后开始记录，不会补造之前没有保存的摘要。记录的是实际注入时的内容，
不是“摘要已生成但尚未发送”的备份，也不是模型的内部思考。
这里只对新记忆日志做容量轮换；现有家庭录音、回答文字与转写文件继续使用原来的保存规则。
日志包含家庭对话原文，保存在已被 Git 排除的 `assistant-data` 目录。
