# EBO + Home Assistant + GPT Realtime（本机隔离部署）

本目录是一个独立 Docker Compose 项目，项目名和网络名都固定为 `ebo-ai-home`。它不会复用其他项目的容器、网络、数据库或配置目录。

播放器静音只影响当前浏览器，不关闭助手的声音来源。全局麦克风开关和真实音频接收状态见[音频开关与健康检查](docs/audio-listen-health.zh-CN.md)。

## 三者的关系

```text
EBO HOME 账号 / Enabot Cloud
             │ Agora 控制、音视频
             ▼
      ebo-engine（设备适配器）
             │ HTTP API + RTSP（视频 + 音频）
             ├──────────────────────► Home Assistant（实体、自动化、面板）
             │
             ▼
 realtime-assistant（本地运动门控 + 音频桥）
             │ 只发送有效图片 + 说话音频
             ▼
      GPT-Realtime-2.1 ──► EBO 扬声器
```

- `ebo-engine` 只负责把 EBO 的专有云协议翻译成 HTTP、RTSP 和 Home Assistant 实体。
- Home Assistant 是编排层：持有摄像头实体、按钮、自动化和家庭界面。
- `realtime-assistant` 是新的多模态运行层：读取品牌无关的 RTSP，在本地过滤空镜，再维护 Realtime 音频/图片会话。LLM Vision 只作为旧的手动单帧实验保留，不再是助手依赖。
- 视觉模型只负责“看懂画面”。机器人移动属于独立控制能力；默认不让模型直接驱动电机，避免误动作。需要自主移动时，应再加限速、活动区域、人工确认和急停等策略层。

## 当前状态

- Home Assistant 2026.8.3 正在本机容器中运行，管理员账号已创建。
- LLM Vision 1.7.1 通过只读 bind mount 安装，不会写回上游仓库；OpenAI Provider 已配置为 `gpt-4o-mini`。
- 已从连接的 Android 手机确认官方 App 是 `prod_cn` 构建，并只在本机私有目录中提取对应的中国区生产密钥。
- EBO Engine 已登录中国区云端并发现一台在线的 EBO Air 2S；实测输出 H.264 1280×720 25fps RTSP 和 Opus 音频。
- Home Assistant 已创建 `EBO 示例设备` 设备和 28 个实体；视觉入口是 `camera.ebo`。
- 已增加标准扬声器实体 `media_player.ebo_speaker`：Home Assistant TTS
  和未来的 AI 对话只调用通用 `media_player` 接口，不直接依赖 EBO 的 `talk` 协议。
- “AI 小伙伴”面板已有“3. 测试 EBO 说话”按钮；实测可从待机状态自动唤醒音频会话、
  等待连接完成，再播放中文 TTS。持续监听、语音识别和轮流对话尚未开启。
- 已完成端到端实测：HA 从 EBO 抓取 100239 字节 JPEG，LLM Vision 成功让 OpenAI 返回中文场景描述。
- 已增加独立的 `realtime-assistant` 服务：本地运动检测选帧、Realtime 音频/图片输入、旧图片清理、成本窗口限制、流式 EBO 扬声器回复、回声感知插话和健康检查均已实现。
- 已补上 RTSP 抽帧回退：EBO 的快照端点不可用时，摄像头实体仍能为 LLM Vision 提供标准 JPEG。
- `.env`、Home Assistant 的 `.storage`/数据库、媒体快照和 EBO 数据均被 `.gitignore` 排除。
- 从 Android 手机提取的 APK、反编译代码和临时分析结果统一放在 `private/`，整个目录不会进入版本控制。

当前官方手机 App 已被临时停止进程，以免与 EBO Engine 争抢同一控制会话；在手机上重新点开 App 即可恢复使用。

## Realtime 助手

完整技术选择、成本策略、运动检测调参和后续 Frigate 升级条件见
[Realtime 助手计划](docs/realtime-assistant-plan.zh-CN.md)。最短启动方式：

流式声音、降级路径和插话截断的实现说明见
[EBO 流式语音与插话打断](docs/streaming-barge-in.zh-CN.md)。

```powershell
# 先在 .env 中设置 OPENAI_API_KEY
docker compose --profile assistant up -d --build
docker compose logs -f realtime-assistant
```

打开 `http://localhost:8099/health` 可检查 Realtime、视频和音频是否在流动。默认
`EBO_VISUAL_MODE=context`，运动画面只更新对话的视觉上下文，不会见到任何移动就主动说话。

每个由 VAD 提交的用户语音回合默认使用 `gpt-transcribe` 生成最终转写，并持久化到宿主机
`assistant-data/transcripts.jsonl`。这是 UTF-8 JSON Lines 文件，每行包含本地时间、Realtime
语音 item ID、识别语言和 transcript；Docker 重建与 Session 轮换不会删除它。`/health` 中的
`input_transcription_configured`、`user_transcripts_received` 和 `last_user_transcript_at` 可确认
转写是否启用及最近是否收到结果。该文件包含家庭对话明文，请按敏感数据保护。

模型完成的每段语音回答会持久化到宿主机 `assistant-data/replies/`：同名 `.wav` 是声音，
同名 `.txt` 是回答文字；`assistant-data/assistant_outputs.jsonl` 是包含时间、Realtime response/item
ID 和两个文件路径的总索引。它们不会因 60 分钟 Session 轮换、服务重启或容器重建而删除。
`/health` 中的 `output_audio_dir`、`output_audio_files_persisted`、`assistant_outputs_persisted` 和
`last_assistant_output_at` 可确认落盘状态。程序不自动清理这些家庭录音和明文，磁盘占用会持续增长，
需要由使用者自行确定保留与备份策略。

单个 Realtime Session 最长 60 分钟，但 assistant 作为服务可以长期运行：它默认在第 55 分钟等待
说话和回复结束；空会话直接重连，有真实对话时先用不发声的 out-of-band 文本响应生成一份精简交接记忆，
再把这份记忆随原 prompt 注入新 Session。网络意外断线时，程序使用指数退避自动重连，并从持久化
JSONL 中取最近 15 分钟内已经完成的用户/助手文字回合注入新 Session；若最近一张运动选帧也在这个
时间范围内且视觉模式为 `context`，会一并重新放入新 Session。正在传输但尚未完成的音频或回答无法
跨断线恢复。`/health` 中的
`realtime_session_age_seconds`、`realtime_session_refresh_in_seconds`、
`realtime_session_rollovers`、`handoff_memory_present`、`reconnect_memory_present` 和
`unplanned_realtime_reconnects` 可以观察这一过程。

实际注入新 Session 的两段动态记忆现在单独记录在宿主机
`assistant-data/logs/session-memory.jsonl`，包括带时区时间、启动/轮换/断线重连原因、
摘要原文、断线逐字记录原文以及发送/服务端确认状态。只在会话配置时记录一次正文，
普通音频、图片、回答请求不会重复记。默认每份最多 1 MiB，保留当前文件和 3 份备份，
合计最多 4 MiB。查看方式、状态含义及 `.env` 调整见
[动态记忆日志说明](docs/session-memory-log.zh-CN.md)。

OpenAI Realtime 当前可调的模型、语音、推理、输出长度、输入转写、Prompt 模板、上下文截断、工具和
Tracing 参数都已接入 `.env`。完整变量表、范围、JSON 写法及哪些音频协议字段有意固定，见
[Realtime Session `.env` 参数说明](docs/realtime-session-env.zh-CN.md)。常用的模型侧参数是：

```dotenv
OPENAI_REALTIME_MODEL=gpt-realtime-2.1-mini
OPENAI_REALTIME_VOICE=marin
OPENAI_REALTIME_OUTPUT_SPEED=1.0
OPENAI_REALTIME_REASONING_EFFORT=
OPENAI_REALTIME_MAX_OUTPUT_TOKENS=inf
OPENAI_REALTIME_TRUNCATION_TYPE=retention_ratio
OPENAI_REALTIME_RETENTION_RATIO=0.8
OPENAI_REALTIME_POST_INSTRUCTIONS_TOKENS=8000
```

`OPENAI_REALTIME_REASONING_EFFORT` 留空表示采用模型默认值；需要明确控制时可填
`minimal`、`low`、`medium`、`high` 或 `xhigh`。并非每个 Realtime 模型都支持所有档位。

EBO 侧的桥接进程也会持续重试。DNS、登录或临时云端错误不再被误判为音视频崩溃，因此网络恢复后
仍会以 A/V 模式重新连接；只有底层进程连续被信号杀死时才保护性降级到 control-only。当前常驻助手
建议设置 `EBO_AUTO_WAKE=true`，RTSP 读取失败时最多每分钟请求一次唤醒并打开摄像头。健康检查不再只看
OpenAI WebSocket：视频帧或音频超过 20 秒没有更新时，`media_ok`/`ok` 会变为 `false`，Docker 容器也会
标为 unhealthy，方便准确发现“连接看似正常但媒体已停”的状态。

通常无需修改以下默认值；需要测试时可以在 `.env` 调整：

```dotenv
REALTIME_SESSION_REFRESH_SECONDS=3300
REALTIME_SESSION_HARD_DEADLINE_SECONDS=3540
REALTIME_HANDOFF_TIMEOUT_SECONDS=20
REALTIME_HANDOFF_MEMORY_CHARS=4000
REALTIME_RECONNECT_MEMORY_MAX_AGE_SECONDS=900
EBO_AUTO_WAKE=true
EBO_MEDIA_STALE_AFTER_SECONDS=20
EBO_MEDIA_STARTUP_GRACE_SECONDS=45
OPENAI_INPUT_TRANSCRIPTION_MODEL=gpt-transcribe
EBO_TRANSCRIPT_PATH=/data/transcripts.jsonl
EBO_OUTPUT_AUDIO_DIR=/data/replies
EBO_ASSISTANT_TRANSCRIPT_PATH=/data/assistant_outputs.jsonl
```

麦克风降噪和回合检测也全部由 `.env` 控制：

```dotenv
REALTIME_INPUT_NOISE_REDUCTION=far_field
REALTIME_TURN_DETECTION_TYPE=server_vad
REALTIME_VAD_THRESHOLD=0.65
REALTIME_VAD_PREFIX_PADDING_MS=300
REALTIME_VAD_SILENCE_DURATION_MS=650
REALTIME_VAD_IDLE_TIMEOUT_MS=0
REALTIME_SEMANTIC_VAD_EAGERNESS=auto
REALTIME_VAD_CREATE_RESPONSE=false
REALTIME_VAD_INTERRUPT_RESPONSE=true
```

`REALTIME_INPUT_NOISE_REDUCTION` 可设为 `off`、`near_field` 或 `far_field`。EBO 在房间中通常属于
远场麦克风，正常使用时可选择 `far_field`；单独验证 Engine AEC 时应暂设为 `off`，避免把下游降噪
误认为 AEC 效果。`server_vad` 下，背景声音仍误触发时可将
`REALTIME_VAD_THRESHOLD` 按 `0.05` 逐步提高；若开始漏掉轻声讲话则调低。`prefix` 负责补回句首，
`silence` 决定停顿多久算一句话结束，通常不要同时大幅修改。若切换到 `semantic_vad`，则使用
`REALTIME_SEMANTIC_VAD_EAGERNESS`（`low`、`medium`、`high` 或 `auto`），数值型 server VAD 参数
不会发送。修改 `.env` 后必须重建 `realtime-assistant` 容器。服务端确认后的实际值可直接在
`/health` 的 `input_noise_reduction` 和 `turn_detection` 查看。

## 启动顺序

Windows 主机重启后，也可以直接双击桌面上的 `启动 EBO 家庭助手.cmd`。它会启动并等待
Docker Desktop，检查 `.env`，启动本节涉及的三个容器，并验证 Home Assistant、Realtime、视频和
音频全部正常；失败时会显示容器状态和最近日志。实际逻辑保存在 `scripts/start-ebo-home.ps1`，桌面上的
`EBO 家庭助手启动说明.txt` 说明了完整流程。

只修改 `.env` 中的 `EBO_ASSISTANT_INSTRUCTIONS` 或其他 Assistant 参数后，可以双击桌面上的
`应用 EBO Prompt 修改.cmd`。它只会使用 `--no-deps --force-recreate` 重建 `realtime-assistant`，不会
重启 Home Assistant 或 EBO Engine，也不会重建镜像；随后会等待 Realtime、视频和音频全部恢复。
实际逻辑位于 `scripts/reload-ebo-assistant-prompt.ps1`，桌面上的 `EBO Prompt 修改生效说明.txt`
解释了完整流程。

### EBO Engine 的 AEC、降噪与自动增益

Agora Server SDK 内的三项音频处理可在宿主机 `.env` 中独立开关：

```dotenv
EBO_AGORA_AEC_ENABLED=true
EBO_AGORA_NOISE_SUPPRESSION_ENABLED=false
EBO_AGORA_AGC_ENABLED=false
```

每项都接受 `true/false`、`1/0`、`yes/no` 或 `on/off`。首轮声学验证建议只开 AEC，同时设置：

```dotenv
REALTIME_INPUT_NOISE_REDUCTION=off
EBO_BARGE_IN_ENABLED=false
```

这样可以先判断 Agora AEC 自身是否削弱了机器人扬声器被机器人麦克风再次收回的声音。AEC 有效后，
再依次开启 Engine 降噪、最后开启 AGC。这里的开关只控制容器内的 Agora Server SDK APM，不会修改
或刷写 EBO 固件；SDK 返回成功代表处理链已经挂载，最终效果仍要通过空房间 A/B 和真人同时插话测试确认。

修改这些开关后，在项目目录运行：

```powershell
.\scripts\apply-ebo-audio-settings.ps1
```

脚本会校验开关、构建最新 Engine 镜像，只重建 `ebo-engine` 与 `realtime-assistant`，等待 RTC、视频、
机器人麦克风 PCM 和 custom talk-stream 恢复，并确认远端音轨的 Agora APM filter 返回 `0`。
Home Assistant 不会被重启。直接修改 `.env` 而不重建相关容器不会生效。

1. 启动基础 Home Assistant：

   ```powershell
   docker compose up -d homeassistant
   ```

2. 打开 `http://localhost:8123`，创建 Home Assistant 管理员账号。
3. 从自己的 EBO HOME APK 取得与 App flavor 一致的 `payload_key` 和 `sign_key`，将它们连同 EBO 邮箱、密码写入 `.env`。本机已完成此步骤，当前为中国区 `prod_cn`。
4. 生成 EBO 私有配置并启动设备适配器：

   ```powershell
   .\scripts\prepare-ebo.ps1
   docker compose --profile ebo up -d
docker compose logs -f ebo-engine
```

EBO Engine 的相同输出还会持久化到宿主机：

```text
ebo-data\logs\ebo-engine.log
```

容器重建后文件仍保留。默认每个文件最大 10 MB，并保留
`ebo-engine.log.1` 到 `ebo-engine.log.5` 五个历史文件；这些值可通过 `.env` 中的
`EBO_HOST_LOG_MAX_BYTES` 和 `EBO_HOST_LOG_BACKUP_COUNT` 调整。日志目录属于运行数据，已被
`.gitignore` 排除，不会被提交到 Git。

5. 在 Home Assistant 添加 `EBO` 集成。第一台机器人填写：

   - Node：`ebo`
   - Name：自定义，例如 `EBO 示例设备`
   - RTSP：`rtsp://ebo-engine:8554/ebo`
   - API：`http://ebo-engine:8098`
   - Token：`.env` 中的 `EBO_API_TOKEN`

   多台机器人依次使用 8555、8556、8557。

6. 在 `.env` 中设置 `OPENAI_API_KEY`，启动 Realtime 助手：

   ```powershell
   docker compose --profile assistant up -d --build
   docker compose logs -f realtime-assistant
   ```

LLM Vision 不再是运行依赖。若还想保留旧的手动单帧对照测试，可另行在 Home Assistant 中配置它；
Realtime 助手不会读取其 Provider、记忆或时间线。

## 旧的单帧入口（可选）

`homeassistant-config/packages/ai_camera_adapter.yaml` 保留了两个旧脚本，方便手动比较或回归测试：

- `script.ai_camera_describe`：品牌无关的视觉入口。只依赖所选的 `camera.*` 实体和 LLM Vision Provider，结果写入 `input_text.ai_last_description`。
- `script.ebo_ai_look_and_describe`：很薄的 EBO 包装层，只负责唤醒机器人，等待视频恢复，再调用上面的通用脚本。

`homeassistant-config/packages/ai_audio_adapter.yaml` 提供品牌无关的声音出口：

- `script.ai_speak`：接收文字，通过所选 TTS 引擎生成声音，再发送给所选 `media_player`。
- `script.ai_speaker_test`：播放一句短中文，供面板按钮验证扬声器链路。
- `input_select.ai_audio_output`：声音输出设备；以后可以换成普通摄像头扬声器或独立智能音箱。
- `input_text.ai_tts_engine`：TTS 引擎入口；当前测试使用 Home Assistant 的 Google Translate TTS，
  后续可替换为 OpenAI 或其他 TTS，而不修改对话流程。

摄像头与模型分别通过两个 Helper 解耦：

- `input_select.ai_camera_source`：当前视觉来源。
- `input_text.ai_vision_provider`：当前 LLM Vision Provider 的配置条目 ID。

以后换普通 RTSP、ONVIF 或其他品牌摄像头时，只需让 Home Assistant 产生新的 `camera.*` 实体，把该实体加入 `input_select.ai_camera_source`，随后继续调用 `script.ai_camera_describe`。EBO 控制脚本可以保留、停用或删除，不会影响视觉层。

当前脚本设置 `expose_images: false`、`store_in_timeline: false` 和 `use_memory: false`：只有主动触发时的一帧会发送给 OpenAI，不会额外保存到 LLM Vision 时间线或媒体目录。

Home Assistant 左侧还有独立的 `AI 小伙伴` 面板，配置文件是 `homeassistant-config/dashboards/ai-playmate.yaml`。面板同时提供通用摄像头分析和 EBO 唤醒后分析两个按钮，并显示最新中文结果。它属于展示层；删除或替换这个面板不会影响底层摄像头、LLM Vision 或脚本。

## 需要手机配合的步骤

EBO 仓库不附带官方 App 的两个 crypto 常量。请仅从你自己的 Android 手机/App 副本提取，不要把值发到公开聊天或提交到 Git。完整上游说明位于 `ha-enabot/ebo/docs/GET-APP-KEYS.md`。

此外，EBO HOME App 与该适配器使用同一个账号时通常只能保留一个控制会话；调试时先彻底退出手机 App。

## 常用命令

```powershell
docker compose ps
docker compose logs -f homeassistant
docker compose --profile ebo logs -f ebo-engine
docker compose stop
docker compose start
```

停止不会删除数据。若移动到父母家的常驻电脑，修改 `.env` 的 `EBO_HOST_IP` 后重新运行 `prepare-ebo.ps1`。
