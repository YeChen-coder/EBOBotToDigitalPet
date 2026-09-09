# OpenAI Realtime Session 的 `.env` 参数

本项目把 OpenAI 当前 `session.update` 中适合 EBO 常驻助手的行为参数暴露为环境变量。字段依据：

- [Realtime client events：`session.update`](https://developers.openai.com/api/reference/resources/realtime/client-events)
- [Realtime conversations](https://developers.openai.com/api/docs/guides/realtime-conversations)
- [Voice activity detection](https://developers.openai.com/api/docs/guides/realtime-vad)

修改项目根目录的 `.env` 后，双击桌面的 `应用 EBO Prompt 修改.cmd`，或者运行
`scripts/reload-ebo-assistant-prompt.ps1`。环境变量只在容器创建时读取，所以必须重新创建
`realtime-assistant` 容器；不需要重启 Home Assistant 或 EBO Engine。

## 模型、回答与语音

| `.env` 变量 | 默认值 | 可用值与作用 |
|---|---:|---|
| `OPENAI_REALTIME_MODEL` | `gpt-realtime-2.1` | Realtime 模型名称；当前实机 `.env` 可单独选择 Mini。 |
| `OPENAI_REALTIME_VOICE` | `marin` | 内置 voice 名称，或 `voice_...` 自定义 Voice ID。一个 Session 首次产生音频后不能再换 Voice。 |
| `OPENAI_REALTIME_OUTPUT_SPEED` | `1.0` | 输出语速，范围 `0.25` 到 `1.5`；只能在两次回答之间调整。 |
| `OPENAI_REALTIME_OUTPUT_MODALITY` | `audio` | `audio` 会说话并产生文字 transcript；`text` 只输出文字，EBO 不会发声。 |
| `OPENAI_REALTIME_REASONING_EFFORT` | 空 | 空值采用模型默认值；可设 `minimal`、`low`、`medium`、`high`、`xhigh`。模型不一定支持所有档位。 |
| `OPENAI_REALTIME_MAX_OUTPUT_TOKENS` | `inf` | `inf` 或 `1` 到 `4096`；这是每次回答的上限，包含工具调用。 |
| `OPENAI_REALTIME_INCLUDE_TRANSCRIPTION_LOGPROBS` | `false` | 是否要求输入转写事件附带 logprobs。 |

`EBO_ASSISTANT_INSTRUCTIONS` 仍是直接发给 Session 的角色 Prompt。它不是新变量，但属于
`session.instructions`，会继续和视觉规则、轮换记忆、断线恢复记录合并。

## 输入转写

| `.env` 变量 | 默认值 | 可用值与作用 |
|---|---:|---|
| `OPENAI_INPUT_TRANSCRIPTION_MODEL` | `gpt-transcribe` | 输入转写模型。 |
| `OPENAI_INPUT_TRANSCRIPTION_DELAY` | 空 | `minimal`/`low`/`medium`/`high`/`xhigh`；当前只适用于 `gpt-realtime-whisper`。 |
| `OPENAI_INPUT_TRANSCRIPTION_KEYWORDS_JSON` | `[]` | JSON 字符串数组，例如 `["EBO","药盒"]`；适用于 `gpt-transcribe`、`gpt-live-transcribe`。 |
| `OPENAI_INPUT_TRANSCRIPTION_LANGUAGE` | 空 | 单一 ISO-639-1 语言提示，例如 `zh`。 |
| `OPENAI_INPUT_TRANSCRIPTION_LANGUAGES_JSON` | `[]` | 候选语言 JSON 数组，例如 `["zh","en"]`。 |
| `OPENAI_INPUT_TRANSCRIPTION_PROMPT` | 空 | 给转写模型的自由文本提示；不同转写模型的支持情况不同。 |

输入转写在这个项目中不能整体关闭：它既用于保存家人说话的文字，也用于过滤空白或低信息音频后再决定
是否创建回答。

## 降噪与回合检测

已有变量全部保留：

| `.env` 变量 | 作用 |
|---|---|
| `REALTIME_INPUT_NOISE_REDUCTION` | `off`、`near_field` 或 `far_field`。 |
| `REALTIME_TURN_DETECTION_TYPE` | `server_vad` 或 `semantic_vad`。 |
| `REALTIME_VAD_THRESHOLD` | Server VAD 激活阈值，范围 `0` 到 `1`。 |
| `REALTIME_VAD_PREFIX_PADDING_MS` | Server VAD 检出说话前补回的音频。 |
| `REALTIME_VAD_SILENCE_DURATION_MS` | Server VAD 将沉默判作回合结束的时长。 |
| `REALTIME_VAD_IDLE_TIMEOUT_MS` | Server VAD 空闲后主动回应；`0` 关闭，否则官方范围是 `5000` 到 `30000`。 |
| `REALTIME_SEMANTIC_VAD_EAGERNESS` | `auto`、`low`、`medium` 或 `high`。 |
| `REALTIME_VAD_CREATE_RESPONSE` | 是否由 OpenAI 在检测到回合结束后直接创建回答。默认 `false`，由本地转写过滤后创建。 |
| `REALTIME_VAD_INTERRUPT_RESPONSE` | 是否由云端检测到说话便取消回答；启用本地回声感知插话时会强制为 `false`。 |

不能把 `turn_detection` 设为 `null`：当前 EBO 是常开麦克风而不是按键说话，程序没有关闭 VAD 后所需的
手动 commit 控制面。

## OpenAI Prompt 模板

| `.env` 变量 | 默认值 | 作用 |
|---|---:|---|
| `OPENAI_REALTIME_PROMPT_ID` | 空 | OpenAI Dashboard 中保存的 Prompt ID。空值表示不用服务器 Prompt。 |
| `OPENAI_REALTIME_PROMPT_VERSION` | 空 | 可选的固定版本。 |
| `OPENAI_REALTIME_PROMPT_VARIABLES_JSON` | `{}` | 一行 JSON 对象，例如 `{"city":"Toronto"}`。 |

直接提供的 `EBO_ASSISTANT_INSTRUCTIONS` 会覆盖服务器 Prompt 中与它重叠的 Session 字段。填写 Version
或 Variables 时必须同时填写 Prompt ID。

## 上下文与成本

| `.env` 变量 | 默认值 | 可用值与作用 |
|---|---:|---|
| `OPENAI_REALTIME_TRUNCATION_TYPE` | `retention_ratio` | `auto`、`disabled` 或 `retention_ratio`。`disabled` 在超过窗口时直接报错。 |
| `OPENAI_REALTIME_RETENTION_RATIO` | `0.8` | `retention_ratio` 模式下每次裁剪后保留的比例，范围 `0` 到 `1`。 |
| `OPENAI_REALTIME_POST_INSTRUCTIONS_TOKENS` | `8000` | Prompt 之后允许保留的会话 token 上限，不能高于模型窗口扣除最大输出后的容量。 |

当前默认值继续保持此前为了成本采用的 `retention_ratio: 0.8` 和 `post_instructions: 8000`。

## 工具与 Tracing（高级）

| `.env` 变量 | 默认值 | 作用 |
|---|---:|---|
| `OPENAI_REALTIME_PARALLEL_TOOL_CALLS` | 空 | 空值采用服务器默认；也可设 `true` 或 `false`。 |
| `OPENAI_REALTIME_TOOLS_JSON` | `[]` | 完整的一行 `session.tools` JSON 数组。 |
| `OPENAI_REALTIME_TOOL_CHOICE` | 空 | `none`、`auto`、`required`，或强制指定工具的一行 JSON 对象。 |
| `OPENAI_REALTIME_TRACING` | `off` | `off`、`auto`，或包含 `workflow_name`、`group_id`、`metadata` 的一行 JSON 对象。 |

这些字段会原样交给 OpenAI。当前程序没有本地 Function Tool 执行器：如果在 `TOOLS_JSON` 中声明
本地 function，模型可以提出调用，但程序不会执行并回传结果。远端 MCP 还涉及授权和审批策略，配置前应
单独做安全设计。Tracing 一旦在某个 Session 开启，该 Session 内不能再关闭；修改 `.env` 后的新 Session
会使用新配置。

## 有意固定的协议参数

下面几个官方字段没有开放，因为它们不是纯“模型偏好”，而是当前音频管线的协议：

- Session `type` 固定为 `realtime`。
- 输入和输出固定为 24 kHz、单声道 PCM；Assistant、WAV 持久化、8 kHz Agora 重采样都依赖它。
- 输入转写保持启用。
- `turn_detection` 保持启用。

把这些字段随意改成 PCMU、PCMA 或 `null` 会让收到的字节与现有解码、播放、回合创建逻辑不一致，
因此没有为了“看起来参数更多”而暴露一个会静默破坏机器人的开关。
