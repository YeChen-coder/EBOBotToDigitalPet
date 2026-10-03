# Specter 框架迁移到 EBO

2026-09-30：当前本地项目使用 `specter-ebo-v2`。参考项目为 `SpecterSaysHi`。只迁移源代码和框架，不导入参考项目的记忆、人脸照片、猫逻辑、数字人或视频输出。

## 数据流与保留内容

```text
EBO → EBO Engine → RTSP 视频 → Frigate person / face recognition
                       │                  │
                       │             MQTT 身份触发
                       │                  ▼
                       └→ RTSP 音频 → 爸爸 / 妈妈会话 ← Dashboard 手动开启
                                         │
                        WebRTC AEC / 降噪 + VAD / 最终转写门控
                                         │
                         Realtime Agent + 按需 Frigate 图像
                                         │
                      EBO Engine 24 kHz PCM → EBO 扬声器
                      （连接失败时保留原 WAV URL 回退）
                                         │
                  会话总结 → 对应父母记忆 → 定期整理
```

主提示词仍是当前项目 `.env` 的 `EBO_ASSISTANT_INSTRUCTIONS`，迁移没有替换它的内容；代码补充会话生命周期、图像上下文、公开问题搜索和当前父母记忆。原 Home Assistant 与 EBO Engine 设备接口保留。

`presence.py`、`visual.py`、`session_memory.py`、`echo.py` 来自 Specter 框架；`conversation.py` 将其 SDK 会话、VAD、AEC、播放队列和图像策略适配到 EBO。`ebo_transport.py` 保留当前项目的 Engine 协议和落盘格式。机器人无法提供 Specter 的本地 PortAudio 扬声器回调，AEC 参考和 SDK 截断位置改用 Engine 的实际 `played_ms` 进度。

| 原逻辑 | 当前逻辑 |
|---|---|
| 本地运动门控选帧 | Frigate 实时摄像头图像，开场和检测到说话时更新 |
| 转写文字决定是否请求回答 | 恢复 gpt-transcribe 最终转写门控，VAD 仅分段，自动回复关闭 |
| 独立 live 转写 | 恢复 gpt-live-transcribe 独立记录，不触发回复 |
| 长期连接、轮换交接、断线日志恢复 | 默认有效语音唤起或手动开启有限会话；已确认的家庭身份会话结束后保存总结 |
| 旧 Engine AEC / 本地确认插话逻辑 | 保留 WebRTC AEC / 降噪，但默认轮流说话；本地插话为实验选项，服务端及 SDK 自动打断关闭 |
| 共享动态交接记忆 | 爸爸、妈妈分别保存会话总结和结构化长期记忆 |

## 身份与会话

人脸库名称为 **爸爸 / 妈妈**，内部稳定 ID 为 `father / mother`。Frigate 只追踪 `person`，使用独立数据库和人脸目录。默认不因识别人脸自动问候；有效语音才唤起会话。近期唯一的人脸分数至少 0.90、人物面积至少 40000 像素时可作为家庭身份提示，其余使用临时家人会话。若显式开启主动问候，原一次问候、25 秒离场和 90 秒冷却规则仍适用。保留消息和非人物事件不触发。

一次仅有一个会话。Dashboard 在开启前明确选择爸爸或妈妈；另一人靠近时不会覆盖正在进行的会话，之后可以重新检查仍在场的身份。记忆归属于本次会话选择的身份；没有声纹鉴别，多人同时讲话时无法自动分辨每句话属于谁。

默认空闲 600 秒结束、会话最长 2700 秒；手动结束、语音结束和服务停止也会关闭连接。空会话不生成记忆。断线后回到待机并记录故障，不把旧逐字稿重新注入另一会话。

## 父母照片录入

照片尚未提供，当前显示“待录入照片”，可先手动使用。将每个人的照片分别放到本机目录，再执行：

```powershell
.\scripts\register-parent-faces.ps1 -User father -PhotoDirectory 'C:\ParentPhotos\爸爸'
.\scripts\register-parent-faces.ps1 -User mother -PhotoDirectory 'C:\ParentPhotos\妈妈'
```

脚本只读挂载照片目录，临时容器上传到本项目内部 Frigate API。图片须有可识别的人脸，支持 JPG、PNG、WebP，每张最多 12 MiB。API 拒绝照片时会明确失败；已成功注册的照片保留，可重试剩余照片。也可登录 [本项目 Frigate 人脸库](https://127.0.0.1:8973) 管理；使用此独立 Frigate 实例的账号，首次密码见它的启动日志。未发布无登录的 5000 端口。

照片录入后等待最多 30 秒，Dashboard 更新照片数。识别模型阈值和面积阈值需结合真实照片、EBO 摄像头视角、距离和光线验证；没有照片时不能宣称实际身份识别通过。

## 记忆与历史

记忆首次为空，位于 `assistant-data/memory-v2/father/` 与 `mother/`，各自有 `sessions.json` 和 `long_term.json`。每次有实质用户内容的会话生成不超过 25 个英语词的一句总结；问候、关闭会话等纯控制内容不保存。长期记忆分稳定、中期、短期，按 Specter 规则过期、去重和整理，默认 6 条新总结或 24 小时触发整理。

原 `assistant-data/logs/session-memory.jsonl`、旧转写与回答文件仅保留为历史，不作为新记忆输入。主转写写 `transcripts.jsonl`（source=gate），独立转写写 `live_transcripts.jsonl`（source=live）；回答继续写 `assistant_outputs.jsonl` 和 `replies/`，均保留 `user_id` 供 Dashboard 区分身份。这些家庭数据均排除版本控制。诊断模型证据仅含状态、计数和允许的事件类别，不读取记忆正文或照片；Dashboard 沿用家庭转写查看能力。

## 诊断与 Dashboard

[本地 Dashboard](http://127.0.0.1:8179) 增加身份选择、开启/结束会话、照片数、Frigate/MQTT、源音频和记忆整理状态。待机时 `realtime_connected=false` 是正常行为；只有监听器、Frigate 视频、MQTT、RTSP 音频与 Engine 真实源音频均正常，`ok` 才为 true。

Diagnostic Agent 增加 Frigate/MQTT 两个独立目标，按健康协议 v2 识别待机、连接和保存记忆状态。Frigate、MQTT 或源音频故障不会被当成 OpenAI 断线反复重启助手。只读代码快照更新为新模块，既有故障历史保留；过去切换失败但当前两侧库存和功能健康均被重新确认时，可通过只读核验恢复状态，不重复执行启停。

本次只部署本机。已有 AWS 服务仍是旧架构且任务为 0；Dashboard 禁止启动它，避免切回旧逻辑并关闭正常本地服务。未来迁移云端时，需要部署完整新服务、网络、持久化及健康合同，验证后给对应 AWS target 设置 `architecture: "specter-ebo-v2"`。只修改这个标识不会完成云端迁移。

## 启动与验证

```powershell
docker compose --profile assistant up -d --build
Invoke-RestMethod http://127.0.0.1:8099/health
node ops/diagnostics/scripts/setup.mjs
```

模型参数见 [当前 `.env` 参数说明](realtime-session-env.zh-CN.md)。只更新 Prompt/参数后可运行 `scripts/reload-ebo-assistant-prompt.ps1`；改代码/依赖需要重新构建。

自动化验证：36 项 Python 框架、身份、图像、记忆、控制与音频传输测试，以及 120 项 Node 诊断/Dashboard 测试。可选在线测试为 `tests/smoke_realtime.py`、`tests/smoke_pipeline.py`、`tests/smoke_memory.py`；需先 `docker cp` 到 `/app/` 再执行。连接测试无声验证服务端配置与图像接收；音频测试生成但不播放语音、不采集麦克风，只向 EBO 发一秒静音 PCM；记忆测试只使用虚构文字和临时文件。临时目录结束即删除，不写父母记忆。

本次已通过实际模型连接、Prompt 保留、自动 VAD/插话、图像确认、语音生成、Linux AEC 初始化、EBO 静音 PCM 播放，以及记忆总结和长期整理模型调用。真实父母辨认与房间声学插话效果仍需照片及现场验证。诊断容器和新诊断规则测试正常；健康报告仍保留此前模型诊断失败的历史告警，本次没有重新执行真实故障诊断任务。

参考接口：[OpenAI VAD](https://developers.openai.com/api/docs/guides/realtime-vad)、[Realtime 图像会话](https://developers.openai.com/api/docs/guides/realtime-conversations)、[Frigate 人脸识别](https://docs.frigate.video/configuration/face_recognition/)。


## 2026-09-30 夜间：恢复音频门控

实用日志发现一次播放截断，尚不能确定声音来源。现已恢复迁移前音频流程：`gpt-transcribe` 最终转写通过旧过滤规则后手动请求回答；`gpt-live-transcribe`（low、zh）独立记录。播放期间只由本地 300 ms 语音确认和回声相关性/残余语音判断决定插话，保留 500 ms 开头音频。Realtime 的 `create_response`、`interrupt_response` 均固定 false，SDK 的 VAD 自动取消/截断分支也屏蔽，避免它绕过本地判断。待机不新开转写连接，独立转写随对应父母会话结束。

图像仍是当前 Frigate 单帧确认后替换，不恢复运动图像 append 逻辑。诊断日志新增 VAD、门控忽略、手动回复、真实本地插话和回应完成事件；本地插话计数不再统计 SDK 的观察事件。


## 2026-09-30：待机语音唤起与近距离回声约束

此节取代上节关于默认插话及待机音频的说明。默认 `EBO_BARGE_IN_ENABLED=false`，机器人生成/播放期间丢弃输入，实际播放结束后再屏蔽 800 ms；两路转写都不接收这段回声。AEC 保留，但不作为避免自我唤起的前提。实验性本地插话需显式开启。

待机使用本地 WebRTC VAD 分段（至少 300 ms 语音、700 ms 静音结束、300 ms 预留），完整候选通过 `gpt-transcribe` 文件转写与文本过滤后才开 Realtime 会话。候选音频仅保存在内存；最长 30 秒，超长话语不截成多个自动唤起请求。首次话语作为用户文本加入新会话，独立 live 通道也转写该原始语音；只请求一次回答，不重复问候。接入时后续音频最多暂存 10 秒。

默认关闭人脸主动问候，Frigate 仍提供当前单帧和身份提示。身份无法确认时用临时 guest 会话，不读写父母记忆；唯一近期可见且符合阈值的人脸仅是身份提示，不是声纹认证。语音唤起不依赖视频或 MQTT 在线，但要求真实麦克风源健康，不自动越过设备静音。

双路转写不能判断声源是谁，也不能证明一句有效中文是在向机器人说话。无唤醒词时电视、人之间的交谈仍可能唤起；若现场出现这种误唤起，应进一步增加明确唤醒词。默认轮流说话意味着播放时无法语音插话，可使用界面结束会话。
