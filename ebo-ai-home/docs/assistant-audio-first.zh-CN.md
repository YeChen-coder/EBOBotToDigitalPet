# Assistant 优先使用音频，图像可降级和恢复

> **分支：`frigate`（Frigate 版，不是 main）。** 本分支的新架构当前针对本地，新版 AWS Dashboard 尚未完成迁移；完整的本地／云端＋Diagnostic Agent 版本在 [`main`](https://github.com/YeChen-coder/EBOBotToDigitalPet/tree/main)。[版本导航](../../VERSION-GUIDE.md)。

日期：2026-10-01，America/Toronto。

## 行为

- 麦克风来源真实、音频接收正常时，手动启动和语音唤醒不再要求 Frigate、图像或人脸 MQTT 正常。当前会话不会因为图片获取失败结束。
- Frigate 和机器人真实源画面健康时，沿用原来的图片尺寸、压缩、语音开始时取图、服务器确认后替换上一张图片的流程。
- 图片获取总等待上限为 2 秒；上传和删除操作各有 1 秒上限。失败时清理旧视觉上下文，之后的语音仍可请求回答。每个会话最多一个取图任务，超时后的旧结果不再送入会话。
- 图像请求相关的服务器错误及 SDK 错误只记录视觉故障；音频或整体 Realtime 连接错误仍正常报告失败。
- 语音触发在没有可靠人脸画面时使用 guest 身份，不凭旧人脸事件读取个人记忆。自动人脸问候仍要求新画面和 MQTT；手动选择的家人身份维持原逻辑。

## 音频通道

```text
机器人 / Agora 麦克风 PCM
  ├─ 独立、鉴权的 /listen WebSocket → Assistant 24kHz PCM → 原语音会话
  └─ 原视频 FFmpeg 混流 → RTSP / WebRTC / HLS，供观看端使用

机器人 / Agora 视频 → 原视频 FFmpeg → Frigate → 可选会话图片
```

`/listen` 复用 Engine 已有容器内部的 8200 端口，与原来的 `/talk` 共存。需要相同的 API token 和机器人 node，输出 24kHz、单声道 PCM16。默认从 `EBO_TALK_STREAM_URL` 的主机和端口推导，也可设置 `EBO_AUDIO_STREAM_URL`。

音频接收不等待首张视频帧，不依赖 FFmpeg、MediaMTX 或 Frigate。慢客户端只保留有限的新音频，不阻塞 Agora 回调和其他客户端。只转发当前 RTC observer、当前机器人和开启的麦克风数据；全局麦克风关闭仍阻止接收，AI 暂停状态仍持久化。

关闭摄像头只停止视频发布，不停止独立音频接收和 talkback。重新开启视频时，健康的麦克风连接不因缺视频帧被重建。视频恢复继续请求关键帧和轻量唤醒；音频来源也失败时仍有带间隔限制的 RTC 重建。

这是本地容器之间的未压缩 PCM 通道，并没有降低 EBO 到 Agora 的视频带宽，也没有关闭原视频功能。

## 健康与诊断

健康协议升级为版本 3，明确 `visual_required=false`。`ok` 和启动条件取决于真实源音频、音频接收和会话状态；视频、Frigate、MQTT 仍分别呈现状态。视频缺失时诊断显示“语音就绪，摄像头暂不可用”，不因此重启 Assistant。诊断保留对版本 2 和旧服务的原有判定。

## 验证

- Assistant 完整测试 102 项通过，包括无视频手动启动、取图失败和超时后继续回应、图片恢复后确认和替换、图片错误隔离、音频 socket 重连及 AI 暂停。
- Engine 完整测试 134 项通过，1 项需要云凭据的测试跳过；最后增加开启摄像头不重建健康音频的回归后，相关 68 项通过。包括真实 WebSocket 鉴权、多接收者、无视频的 PCM 接收，以及旧 observer / 错误机器人 / 麦克风关闭不能转发音频。
- 诊断完整测试 128 项通过，包含版本 3 无图像健康、音频丢失仍报错，以及版本 2 行为兼容。

实机验证记录保存在 `ops/diagnostics/local/audio-first-20261001/`，不保存家庭音频或图片。

实机已部署：主动关闭视频发布 50 秒，25/25 个两秒采样均保持真实源音频、独立音频接收和 Assistant 健康正常。Frigate 在此期间确实失去视频，旧画面被拒绝；重新开启视频后约 18 秒恢复 Frigate 新画面，取得有效的 768×432 JPEG。恢复过程中音频仍正常，日志没有因此重建 RTC。AI 始终保持用户手动暂停状态，没有启动真实模型会话或播放测试语音。

## 边界与回退

机器人、网络或 Agora 会话本身完全不可用时，无法继续传输真实音频。视频恢复优先避免中断健康音频，不承诺所有机器人端的视频故障都能在不重建 RTC 的情况下恢复。

部署前的 Engine 和 Assistant 镜像分别保留为 `ebo-ai-home/ebo-engine:before-audio-first-20261001` 和 `ebo-ai-home/realtime-assistant:before-audio-first-20261001`。此次保留用户手动暂停 AI 的状态。
