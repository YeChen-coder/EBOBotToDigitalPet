# EBO 流式语音与插话打断

## 为什么这样做

OpenAI Realtime 会连续产生 24 kHz 单声道 PCM16 音频。旧实现必须先等整段回答完成、写成
WAV，再把 URL 交给 EBO，因此回答越长，开口越慢。新实现把每个音频增量立即送进 Docker
内网 WebSocket；完整 WAV、文字和 JSONL 记录仍然保留，便于回看和排障。

## 正常播放路径

```text
OpenAI response.output_audio.delta
              │ 24 kHz PCM16
              ▼
Assistant 预缓冲 200 ms
              │ ws://ebo-engine:8200/talk（token 鉴权）
              ▼
EBO Engine 24 kHz → 8 kHz
              │ 每 20 ms 一帧
              ▼
Agora RTC → EBO 扬声器
```

Engine 只在 Docker 网络内暴露 8200，不映射到宿主机或家庭局域网。每台机器人只保留一条
活动流，新流会停止旧流。Engine 回报 `ready`、`progress`、`done`、`stopped` 和实际
`played_ms`。如果流连接失败，Assistant 自动退回原有的 WAV URL `talk` 接口。

## 插话路径

机器人说话时，麦克风不直接送给 OpenAI，而是进入本地 `BargeInGate`：

1. 保留最近 500 ms 原始麦克风 PCM。
2. WebRTC VAD 检查最近 300 ms，要求至少 200 ms 像人声。
3. 把麦克风与 Engine 已确认播放的机器人声音做最多 500 ms 延迟搜索和相关性比较。
4. 只有相关度低于 `0.65`，或回声抵消后的独立语音帧比例达到 `0.45`，才确认插话。

确认后按顺序执行：

```text
停止 Engine 流
  → response.cancel（回答仍在生成时）
  → conversation.item.truncate(audio_end_ms = Engine 实际 played_ms)
  → 把 500 ms 预录送回 OpenAI
  → 等最终输入转写通过既有过滤
  → 只创建一次新回答
```

启用本地插话时，Realtime 会强制使用 `interrupt_response=false`，防止云端 VAD 在本地回声
判定完成前擅自取消。被打断的回答仍有 WAV 和文字记录，JSONL 会包含 `interrupted`、
`generated_ms`、`played_ms`、`stream_id` 和 `streamed`。

## 配置与观察

所有阈值都在项目根目录 `.env` 中。修改后用桌面的重建脚本重建 Assistant 容器。
`http://localhost:8099/health` 会显示流状态、实际播放时长、降级次数、失败次数、打断次数、
最近一次回声相关度和残余语音比例。

官方中断与截断流程：
https://developers.openai.com/api/docs/guides/realtime-conversations#interruption-and-truncation
