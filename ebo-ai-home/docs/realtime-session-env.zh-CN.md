# 当前 Realtime / Specter 框架 `.env` 参数

此表对应 `specter-ebo-v2`，图像使用 Frigate，音频使用待机唤起、转写回复门控与默认轮流说话。完整示例为项目根目录 `.env.example`。参数修改后需重建容器；Prompt/参数可用 `scripts/reload-ebo-assistant-prompt.ps1`，代码/依赖需 `docker compose --profile assistant up -d --build`。

## 模型与 Prompt

| 参数 | 默认值 / 含义 |
|---|---|
| `OPENAI_API_KEY` | 必填，仅本机保存 |
| `EBO_ASSISTANT_INSTRUCTIONS` | 原 EBO 主 Prompt；按身份补充对应记忆和会话规则 |
| `OPENAI_REALTIME_MODEL` | `gpt-realtime-2.1-mini` |
| `OPENAI_REALTIME_VOICE` | `marin` |
| `OPENAI_REALTIME_OUTPUT_SPEED` | `1.0`，范围 0.25–1.5 |
| `OPENAI_INPUT_TRANSCRIPTION_MODEL` | `gpt-transcribe`，最终转写决定回复，并用于记录与总结 |
| `OPENAI_INPUT_TRANSCRIPTION_DELAY` / `KEYWORDS_JSON` / `LANGUAGE` / `LANGUAGES_JSON` / `PROMPT` | 恢复读取对应 OPENAI_INPUT_TRANSCRIPTION 前缀参数，默认空或 [] |
| `OPENAI_LIVE_TRANSCRIPTION_ENABLED` / `MODEL` / `DELAY` / `LANGUAGES_JSON` / `PROMPT` | 恢复对应完整前缀参数，默认 true / gpt-live-transcribe / low / ["zh"] / 空 |
| `OPENAI_RESEARCH_MODEL` | `gpt-5.4-mini`，公开问题搜索 |
| `OPENAI_RESEARCH_TIMEOUT_SECONDS` | `90` |
| `EBO_TRACE_ENABLED` | `false` |
| `OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA` | `false` |

固定使用 24 kHz、单声道 PCM16，输出音频。主会话工具为公开问题搜索和结束会话。主转写与独立 live 转写配置已恢复。原自定义 raw tools、Prompt 模板 JSON、推理/truncation 参数没有迁入。独立 live 转写只记录，不触发回复或插话。

## 音频与回合

| 参数 | 默认值 / 含义 |
|---|---|
| `EBO_AEC_ENABLED` | `true`，WebRTC AEC 与降噪 |
| `EBO_AEC_DELAY_MS` | `0`，范围 0–500，AEC 延迟 |
| `EBO_AEC_WARMUP_MS` | `500`，播放开始后的 AEC 预热窗口 |
| `EBO_BARGE_IN_ENABLED` | `false`，默认轮流说话；设 true 才启用实验性本地插话 |
| `EBO_VOICE_WAKE_ENABLED` | `true`，待机语音核查通过后开启会话 |
| `EBO_PLAYBACK_TAIL_MS` | `800`，实际播放结束后的回声屏蔽窗口（200..5000） |
| `EBO_PROACTIVE_GREETING_ENABLED` | `false`，默认人脸只辅助身份，不自动开启会话 |
| `EBO_BARGE_IN_CONFIRM_MS` / `PREROLL_MS` / `VAD_MODE` | 恢复完整 EBO_BARGE_IN 前缀参数，默认 300 / 500 / 2 |
| `EBO_BARGE_IN_ECHO_CORRELATION` / `RESIDUAL_RATIO` | 0.65 / 0.45 |
| `EBO_SERVER_NOISE_REDUCTION` | `far_field`，也支持 `near_field`、`off` |
| `REALTIME_VAD_THRESHOLD` | `0.65`，范围大于 0 小于 1 |
| `EBO_VAD_PREFIX_PADDING_MS` | `300` |
| `EBO_VAD_SILENCE_DURATION_MS` | `650` |
| `EBO_AGORA_AEC_ENABLED` | `false`，原 Engine 处理关闭 |
| `EBO_AGORA_NOISE_SUPPRESSION_ENABLED` | `false` |
| `EBO_AGORA_AGC_ENABLED` | `false` |

server VAD 固定 `create_response=false`、`interrupt_response=false`，仅用于主转写分段。SDK 的 VAD 自动停止播放/取消/截断分支也已关闭。旧 `REALTIME_VAD_CREATE_RESPONSE` 和 `REALTIME_VAD_INTERRUPT_RESPONSE` 无法重新开启自动行为；实际 .env 也设为 false。本地插话确认参数已恢复，`REALTIME_INPUT_NOISE_REDUCTION` 仍由当前 `EBO_SERVER_NOISE_REDUCTION` 替代。查询 `/health` 的 `turn_detection`、`input_noise_reduction` 可查看会话建立后服务端确认值；待机未建立过会话时为空。

## 身份、图像和会话

| 参数 | 默认值 / 含义 |
|---|---|
| `EBO_USERS_JSON` | `.env.example` 内爸爸 `father` / 妈妈 `mother`，含 `id`、`face_name`、`display_name` |
| `EBO_FRIGATE_URL` | `http://frigate:5000`，容器内部 |
| `EBO_CAMERA_NAME` | `ebo`，与 Frigate config 对应 |
| `EBO_MQTT_HOST` / `EBO_MQTT_PORT` | `mosquitto` / `1883` |
| `EBO_PROACTIVE_GREETING_ENABLED` | `true` |
| `EBO_VISUAL_ENABLED` | `true` |
| `EBO_MIN_FACE_SCORE` / `EBO_MIN_PERSON_AREA` | `0.90` / `40000` |
| `EBO_ABSENCE_SECONDS` / `EBO_COOLDOWN_SECONDS` | `25` / `90` |
| `EBO_SESSION_IDLE_SECONDS` | Compose 默认 `600` |
| `EBO_SESSION_MAX_SECONDS` | `2700`，范围 30–3300，不小于 idle |
| `REALTIME_IMAGE_WIDTH` / `REALTIME_IMAGE_QUALITY` | `768` / `75` |
| `EBO_ASSISTANT_CONTROL_TOKEN` | 留空使用 `EBO_API_TOKEN`；浏览器不接触此值 |

图像仅在开场和说话开始时加入上下文；新图收到服务端确认再清旧图，不因图像主动请求回答。旧 `EBO_VISUAL_MODE`、运动 ROI 和图片响应参数退出运行路径。

## 记忆

| 参数 | 默认值 / 含义 |
|---|---|
| `EBO_MEMORY_ROOT` | `/data/memory-v2`，绝对目录，每个身份独立子目录 |
| `EBO_REALTIME_MEMORY_MAX_CHARS` | `6000` |
| `EBO_MEMORY_MODEL` / `EBO_MEMORY_TIMEOUT_SECONDS` | `gpt-5.4-mini` / `45` |
| `EBO_LONG_TERM_MEMORY_MODEL` / `EBO_LONG_TERM_MEMORY_TIMEOUT_SECONDS` | `gpt-6-sol` / `120` |
| `EBO_MEMORY_CONSOLIDATION_HOURS` | `24` |

保留 Specter 的总结、结构化记忆和过期策略，不导入它的记忆内容。旧 `REALTIME_HANDOFF_*`、`REALTIME_RECONNECT_MEMORY_*`、`EBO_MEMORY_LOG_*` 不再读取。

## EBO 传输与健康

`EBO_RTSP_URL=rtsp://ebo-engine:8554/ebo` 同时接 Frigate 视频和 Assistant 音频；`EBO_API_URL=http://ebo-engine:8098`、`EBO_NODE=ebo`、`EBO_API_TOKEN` 保留当前设备接口。`EBO_TALK_STREAM_URL=ws://ebo-engine:8200/talk`、`EBO_STREAM_PREBUFFER_MS=200`、`EBO_STREAM_CONNECT_TIMEOUT_SECONDS=10` 保留流式 PCM；`EBO_ASSISTANT_AUDIO_URL=http://realtime-assistant:8099/audio` 保留 WAV 回退。

`EBO_AUTO_WAKE=true`，`EBO_MEDIA_STALE_AFTER_SECONDS=20`、`EBO_MEDIA_STARTUP_GRACE_SECONDS=90`。健康判断同时检查 Frigate、MQTT、RTSP 和 Engine 真正的麦克风来源；正常待机不要求 OpenAI 连接。

持久化路径：`EBO_TRANSCRIPT_PATH=/data/transcripts.jsonl`（gate）、`EBO_LIVE_TRANSCRIPT_PATH=/data/live_transcripts.jsonl`（live）、`EBO_OUTPUT_AUDIO_DIR=/data/replies`、`EBO_ASSISTANT_TRANSCRIPT_PATH=/data/assistant_outputs.jsonl`。Compose 将 `/data` 映射到宿主机 `assistant-data`。不要把这些数据放进诊断代码快照。
