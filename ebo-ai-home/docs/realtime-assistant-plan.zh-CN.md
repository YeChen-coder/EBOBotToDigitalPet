# EBO Realtime 助手：技术选择与落地计划

## 结论

不要让 GPT 充当运动检测器，也不要按固定频率把视频帧全部上传。务实的链路是：

```text
EBO / Agora
    │
    ▼
ebo-engine ── RTSP(H.264 + Opus) ──┬──► Home Assistant 摄像头
                                   │
                                   ▼
                         realtime-assistant
                         ├─ FFmpeg 解码音频 → Realtime VAD
                         ├─ FFmpeg 低帧率抽图
                         ├─ OpenCV 本地运动门控
                         └─ 只上传有价值的 JPEG
                                   │
                                   ▼
                         GPT-Realtime-2.1
                                   │ PCM 回复
                                   ▼
                         WAV → EBO talkback
```

这等于把 LLM Vision 从运行链路中拿掉。Home Assistant 仍然负责 UI、实体和家庭自动化，
但实时多模态会话由独立服务持有。

## 为什么这样选

1. `gpt-realtime-2.1` 接收文字、音频和图片，但不直接接收视频。因此正确做法本来就是在本地选帧，
   再把 JPEG 作为 `input_image` 事件加入会话。模型的官方页面也明确标注 Video 不支持。
2. OpenAI Realtime 的服务端 VAD 会过滤空音频，并按说话轮次自动产生回复；没有必要先上另一套语音识别。
3. Frigate 的成熟设计也是“廉价运动检测先筛一遍，再运行更贵的目标检测”。本项目先复用这一原则，
   而不立刻引入完整 NVR、MQTT、数据库和专用推理硬件。
4. 仅靠像素变化会把机器人转头、自动曝光、昼夜切换误判成运动。因此本服务把大面积画面变化视为
   `scene_reset`，重新学习背景，不上传这一帧；小范围运动还必须连续出现多帧才触发。
5. Realtime 每次响应都会再次使用会话历史。服务在新视觉帧进入前删除旧视觉项，只保留最新有效画面，
   并将会话输入窗口限制在 8k token，避免旧图片持续污染上下文和成本。

相关官方资料：

- [GPT-Realtime-2.1 模型能力与价格](https://developers.openai.com/api/docs/models/gpt-realtime-2.1)
- [Realtime WebSocket 服务端连接](https://developers.openai.com/api/docs/guides/realtime-websocket)
- [Realtime 音频、图片和事件流程](https://developers.openai.com/api/docs/guides/realtime-conversations)
- [Realtime VAD](https://developers.openai.com/api/docs/guides/realtime-vad)
- [Realtime 成本与删除旧会话项](https://developers.openai.com/api/docs/guides/realtime-costs)
- [Frigate 的运动检测门控](https://docs.frigate.video/configuration/motion_detection/)

## 当前 MVP 的行为

- 视频只在本地以 2 fps 做运动判断；通过门控后缩到 768px、JPEG quality 75，再上传一张。
- 默认 `EBO_VISUAL_MODE=context`：图片只更新上下文，不会因为有人走过就主动讲话。
- 设成 `announce` 后，每次通过冷却期的视觉事件都会主动产生语音，适合门口提醒，不适合陪伴模式。
- RTSP 中的音频被转换成 24 kHz 单声道 PCM，持续送到 Realtime，由服务端 VAD 切分说话轮次。
- Realtime 返回的 PCM 先落成临时 WAV，再通过 ebo-engine 已有的 `talk` URL 通道播放。
- 播放期间暂停麦克风上行，避免 EBO 把自己的回复再次收进去。这是可靠的半双工方案。
- `/health` 提供连接、最近帧、最近音频、最近运动和错误状态，例如 `http://localhost:8099/health`。

## 60 分钟 Session 的处理

Realtime 的 60 分钟是单个 Session 的硬上限，不应靠心跳规避。长期助手采用“服务长驻、连接轮换”：

1. 第 55 分钟开始轮换，但若用户或模型正在说话，先等待当前轮次结束。
2. 没有真实对话的空 Session 直接重连，不调用模型生成交接内容。
3. 有真实对话时，在旧 Session 内创建不加入默认 conversation、只输出文字的 out-of-band response，
   将已确认事实、偏好、当前任务和未决事项压缩成交接记忆；新 Session 把它附加到原 instructions。
4. 第 59 分钟是紧急截止线。若一直无法进入空闲状态则强制换连接，避免被服务端在第 60 分钟突然切断。
5. 非计划网络断线使用指数退避重连；计划内轮换立即重连，不继承故障退避等待。

官方文档说明空连接目前不收费，而且 server VAD 会过滤空音频；因此稀疏环境没有必要为了省连接成本
频繁开关 Session。真正产生费用的是 Response 使用的输入/输出 token。这个设计只在确实存在对话时
多产生一次很短的交接文本。

## 运行

在 `.env` 中至少补充：

```dotenv
OPENAI_API_KEY=sk-...
OPENAI_REALTIME_MODEL=gpt-realtime-2.1
OPENAI_REALTIME_VOICE=marin
EBO_VISUAL_MODE=context
EBO_AUTO_WAKE=false
```

然后运行：

```powershell
.\scripts\prepare-ebo.ps1
docker compose --profile assistant up -d --build
docker compose logs -f realtime-assistant
```

`EBO_AUTO_WAKE=false` 是隐私和电池优先的默认值。EBO 睡眠后 RTSP 会消失，助手也就无法听见或看见。
如果接受摄像头会被常驻服务重新唤醒，将其设为 `true`。另一种方式是把
`ebo-data/options.json` 的 `standby_after_minutes` 设为 `0`，保持会话常开。

## 调参顺序

先保持默认值实测一天，只在误报或漏报时调整：

| 环境变量 | 默认值 | 作用 |
|---|---:|---|
| `MOTION_THRESHOLD` | 25 | 像素亮度变化阈值；越大越不敏感 |
| `MOTION_MIN_AREA_RATIO` | 0.003 | 最大运动块占画面的最小比例 |
| `MOTION_CONFIRM_FRAMES` | 2 | 连续多少帧才确认运动 |
| `MOTION_COOLDOWN_SECONDS` | 3 | 两张上传图片之间的最短间隔 |
| `MOTION_MAX_CHANGE_RATIO` | 0.55 | 超过该比例视为转头/光变并重置背景 |
| `REALTIME_IMAGE_WIDTH` | 768 | 上传图片宽度 |
| `REALTIME_IMAGE_QUALITY` | 75 | JPEG 质量 |

如果树影、电视画面或宠物导致大量误报，下一步不是继续堆 OpenCV 规则，而是接入 Frigate：
由 Frigate 在本地确认 `person`/`cat`/`dog` 等目标后，把事件快照交给本服务。只有在本机有合适的
OpenVINO、Coral 或 GPU 推理能力时才值得做这一步；CPU 目标检测只适合测试。

## 已知边界与后续阶段

1. **EBO 麦克风是 best-effort。** 现有适配器已经能从 RTSP 输出 Opus，但设备端是否打开麦克风仍受
   Enabot 会话状态影响。健康接口中的 `last_audio_at` 可以区分“Realtime 有问题”和“上游没有音频”。
2. **当前是半双工回复。** ebo-engine 的 talkback 接口接收 URL，所以必须等一轮语音生成完再播放。
   如果需要真正可打断的低延迟全双工，下一阶段应在 ebo-engine 增加一个持续 PCM/Opus 输入端点，
   并实现回声消除；这比在 HTTP WAV 上做技巧性流式传输更可靠。
3. **机器人运动时视觉会降级。** 大画面变化会被重置而不是上传。机器人停稳后，背景模型会重新建立。
4. **工具调用暂不开放电机。** 等语音与视觉稳定后，可以只增加白名单 Home Assistant 工具（查询传感器、
   开灯、播报）；移动、回充等动作应单独加速度限制、区域限制和人工确认。
5. **用量验证。** 在 OpenAI Realtime Playground/Logs 中用真实家庭对话跑一段样本，观察图片、音频和
   历史输入的 token 用量，再决定是否切换到 `gpt-realtime-2.1-mini`。不要在没有测量前为了省钱降级。
