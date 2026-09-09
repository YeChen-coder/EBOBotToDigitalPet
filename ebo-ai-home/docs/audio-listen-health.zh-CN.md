# 播放器静音、全局麦克风与音频健康

## 日常怎么用

- 播放器扬声器按钮只控制当前浏览器播放，静音不影响 Assistant 和其他观看者。
- Audio 设置中的“机器人麦克风上传（全局隐私开关）”会关闭机器人向 Engine 上传声音，Assistant 和共享这条流的观看者都听不到。
- 本地解除静音不会自动打开全局麦克风；页面会提醒你到 Audio 设置明确开启。
- 全局开关改用独立的 `microphone/set` 接口，写入 `ebo-data/ui_choices.json`。没有保存值时默认开启；明确关闭后跨容器重启保留。面板关闭全局麦克风时会弹出确认说明。
- 旧 `listen/set` 已停用：HTTP 返回 409 并提醒刷新，MQTT 只记录拦截，不下发机器人命令。旧页面或旧版 HA 开关都不能通过它关麦；也不能通过它解除明确的隐私关麦。
- 部署后刷新控制面板。HTML/API 增加 no-store，HA 默认仪表盘 iframe 更新版本参数，移除容易误认成本机静音的全局开关行。
- 原生 HA 集成的全局开关已改名并改用新接口；已载入内存的旧集成需重载/重启 HA 后才使用新版。在此之前旧开关会明确报操作失败而不改变麦克风。可直接使用 EBO 面板 Audio 的新隐私开关，无需重启 HA。

全局开关控制的是向 Engine 的传音，不是硬件断电，不保证约束厂商 App 等独立连接。

## 为什么以前关麦后还显示 healthy

Engine 在缺少声音时会补静音，防止 FFmpeg 等待音频导致视频卡住。旧检查只确认 RTSP 音频字节是否到达，因此补静音也会让它显示正常。

现在两层检查分别是：

```text
机器人 → Agora 收包及解码 → Engine 音频源状态
                              ↓ MQTT，每 5 秒
                         /api/robots（鉴权）
                              ↓ Assistant，每 5 秒读取
RTSP 音视频是否流动 ──────→ /health 综合判断
```

新检查要求最近 20 秒内接收字节增长且有解码回调。它不依赖说话音量，不会因为家里安静但仍正常收包就报警。单有解码回调、没有新音频包不算正常，因为 SDK 可能继续输出丢包补偿声音。此检查证明传输/解码活动，不保证声音清晰、转写正确，也无法检测机器人固件持续发出的静音包。

## 在哪里看

打开 `http://localhost:8099/health`。

| 字段 | 含义 |
|---|---|
| `audio_streaming` | RTSP 音频字节在到达，可能是补静音 |
| `transport_media_ok` | 原有音视频流检查 |
| `source_audio_ok` | Engine 上游收包及解码检查 |
| `source_audio_status` | 见下表 |
| `engine_audio_health` | 收包、解码时间及累计字节/码率，不含录音 |
| `engine_audio_error` | 读取诊断失败的异常类型，不含凭证 |
| `ok` | 模型连接、传输及音频源检查全部通过 |

| 状态 | 意义 |
|---|---|
| `receiving` | 最近有上游音频包和解码回调 |
| `muted` | 全局麦克风关闭，不自动开启 |
| `disabled` | Engine 音频功能配置关闭 |
| `disconnected` | RTC 未连接 |
| `no_source_packets` | 尚无音频包，或超过 20 秒没有新包 |
| `no_decoded_pcm` | 有音频包但没有新鲜解码回调 |
| `source_stale` | 读取后收包/解码证据过期 |
| `monitor_stale` | 诊断心跳或 Assistant 读取状态超过 20 秒未刷新 |
| `monitor_error` | 接口不可达、旧 Engine 缺少新字段或返回格式错误 |

每次健康查询都重新检查时间，MQTT retained 的旧状态不能无限维持绿色。若设备采用长时间不发包的静音优化，会显示未确认源音频，不能单凭此断定硬件故障。

全局关麦时 Assistant 会显示 unhealthy，表示语音助手当前不可用，不会因此自动重启。诊断监控只读，不自动开麦或唤醒设备。既有视频断流恢复仍保留，重连和启动重试会尊重明确的全局关麦。

Engine 状态变化记录到宿主机 `ebo-data/logs/ebo-engine.log`，前缀 `[audio-health]`。Assistant 状态变化写到容器日志，前缀 `Engine source audio status`。相同状态不反复刷屏。

## 修复范围

2026-09-07 19:53:52（多伦多时间），面板发出 `listen/set=off`。中间音频曾恢复，但次日 04:35 重连再次按关闭状态发送命令，之后音频字节持续不增长；同期视频 Broken pipe 后已重建。

本次拆分本地播放与全局关麦、增加源音频诊断并保留隐私开关。不更改模型、Prompt、VAD、AEC 或插话参数，不删除录音及对话记录。Engine 和 Assistant 需一起构建部署；仅更新 Assistant 会显示 monitor_error。Home Assistant 无需重建。

## 2026-09-08 验证记录

- Engine：106 项离线测试通过，1 项需云端凭证的测试跳过。
- Assistant：50 项离线测试通过。
- Node：面板内联 JavaScript 语法检查通过；实际 toggleListen 函数在模拟 DOM 中静音/取消静音均未发送全局命令，全局关闭时给出提醒。
- 两个镜像构建并部署完成，Home Assistant 未重建；未清除持久化数据。
- 11:34 左右（多伦多时间）：listen=true 已保存；source_audio_status=receiving、source_audio_ok=true、ok=true；上游码率约 73 kbps，字节数持续增长。
- 三秒 RTSP 采样只在内存统计，平均 -68.2 dB、峰值 -31.2 dB，不再是修复前的全静音。未把采样另外存盘或注入模型。
- 尚需现场家人说一句明确的话，确认真实人声转写、回答和机器人播放的端到端效果；收包正常不等于这项实机验收已经完成。

## 同日二次修复：旧控件仍能关麦

11:35:58 用户操作 Home Assistant 后，旧 `listen/set=off` 再次到达服务端。仅修改播放器 JavaScript 不能覆盖已经打开的旧页面及原生 HA Listen 实体，首次修复范围不完整。日志没有来源身份，不能据此确定这次具体是哪一个页面控件。

二次修复把全局开关迁移到 `microphone/set`，同时在 HTTP 和 MQTT 两层禁用旧 `listen/set`，避免依赖用户是否刷新。旧 HTTP 命令明确返回 409（不是假装成功），新全局隐私关闭需在面板确认。新增 API 鉴权、拦截、转发、缓存及旧 MQTT 回归测试。

验证：Engine 115 项通过、1 项跳过；面板 JavaScript 语法、播放器静音隔离和全局隐私确认测试通过。11:42:14 在已部署真实服务重放 `listen/set=off`，得到 HTTP 409，前后 `listen` 都为 true；日志出现 `blocked legacy listen/set; no microphone change`，随后健康状态仍为 receiving/ok=true。只重建 Engine，未重启 Home Assistant 或 Assistant。
