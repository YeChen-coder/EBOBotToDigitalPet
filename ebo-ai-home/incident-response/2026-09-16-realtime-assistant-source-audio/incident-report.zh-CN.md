# Real-time Assistant 机器人源音频中断事件报告

## 事件摘要

- 日期：2026-09-16
- 状态：已修复并完成现场验证
- 受影响目标：本地 `ebo-engine` 与 `realtime-assistant` 之间的机器人麦克风输入链路
- Watcher 故障码：`container_unhealthy`
- 内部关联 ID：已从公开报告中移除
- 用户影响：视频、OpenAI Realtime 会话和 Assistant 进程仍在运行，但机器人麦克风音频没有进入 Assistant，因此现场语音无法被可靠听取、转写或响应。
- 数据处理：排查没有读取录音、家庭对话转写或凭据。

## 结论

这不是“现场没人说话”造成的正常静音，也不是容器进程退出。机器人麦克风在 RTC 重连前持续正常传输；视频短暂中断触发整套 Agora RTC 会话重建后，视频恢复了，但机器人没有恢复发布麦克风音频轨道。旧代码的音频恢复计时从 RTC 连接建立时开始，而机器人在主要重试已经执行后才加入；主要重试因此发生得太早。机器人加入后的延迟重试只重新订阅音频，没有重新发送机器人开麦命令，导致源音频永久停留在 `no_source_packets`。

本次修复将恢复动作绑定到“机器人实际加入 RTC”事件，并按有界退避同时重复“开麦 + 订阅”，直至收到真实 PCM。恢复线程受当前 RTC、当前音频 observer、连接状态和全局麦克风隐私开关约束，不会操作已过期会话，也不会打开用户主动关闭的麦克风。

## 故障时间线

公开报告保留因果顺序，但省略家庭设备的实际时钟时间和原始生产计数：

| 阶段 | 事件 |
|---|---|
| 正常基线 | 初始 RTC 会话收到机器人音频轨道；源音频进入 `receiving`，并在较长时间内保持稳定。 |
| 触发 | Realtime Assistant 检测到 RTSP 不可用，调用 EBO wake 与 camera/on；Engine 判断视频未在流动并开始强制重建 RTC。 |
| 第一轮重连 | 新 RTC/RTM 会话在机器人加入前建立。Engine 报告 `no_source_packets`；旧 watchdog 重试过早，PCM 仍然缺失。 |
| 第二轮重连 | 视频恢复逻辑再次重建 RTC；watchdog 又一次在机器人加入前执行。 |
| 机器人重新加入 | 开麦和订阅调用返回成功，但旧的延迟逻辑只重试订阅；之后没有音频轨道回调、网络字节增长或 PCM。 |
| 部分恢复 | 视频恢复，但源音频仍为零，因此 Docker Health 正确保持 `unhealthy`。 |
| 修复 | 完整测试通过后构建修复版 Engine 镜像，并且只重建 `ebo-engine`。 |
| 验证 | 源音频恢复为 `receiving`；连续采样显示接收字节单调增长、码率稳定在预期范围、PCM 时间戳持续更新，Assistant 与 Docker Health 均恢复健康。 |
| 关闭 | Watcher 后续采样返回 `healthy`，事件以 `outcome=recovered` 关闭。 |

## 检测与诊断

Docker Desktop 的绿色状态只表示容器进程在运行。Compose healthcheck 会读取 Assistant `/health` 的顶层 `ok`；该值要求 Realtime 连接、视频/音频传输和机器人源音频同时正常。因此容器可以是 `running`，同时 Docker Health 为 `unhealthy`。

故障期间的关键状态是：

```text
realtime_connected=true
video_streaming=true
audio_streaming=true
transport_media_ok=true
source_audio_ok=false
source_audio_status=no_source_packets
received_bytes=0
last_packet_at=null
last_pcm_at=null
ok=false
```

`audio_streaming=true` 只表示 Assistant 的 FFmpeg 音频处理管道仍有输出，可能包含静音填充；`source_audio_ok` 独立确认机器人上游是否真的在传输。安静房间仍会发送编码音频包，因此不会正常地产生持续数小时的 `no_source_packets`。

## 根因分析

### 触发事件

RTSP 视频中断。Assistant 的媒体恢复调用 wake 与 camera/on，Engine 因视频未在流动而重建 Agora RTC 会话。

### 直接原因

RTC 重建后，机器人没有重新开始发布麦克风媒体。SDK 的订阅状态曾变为 subscribed，但没有出现音频轨道订阅回调、首个远程音频帧、网络字节增长或 PCM 回调。

### 软件促成因素

1. 音频 watchdog 在 RTC 连接创建时启动，而不是在机器人真正加入时启动。
2. 第二次重连后 watchdog 在机器人加入前重试，因此关键重试发生得太早。
3. `on_user_joined` 只发送一次开麦命令。
4. 旧的 2.5 秒延迟重试只调用 `subscribe_audio`，没有再次发送 `OP_AUDIO_LISTEN`。
5. 视频恢复后，Assistant 的 RTSP 恢复逻辑停止；源音频监控按隐私设计只报告异常，不会盲目自动开麦。
6. Docker `restart: unless-stopped` 不会因 `unhealthy` 自动重启；Watcher 对 `container_unhealthy` 也按不可自动恢复处理。

### 已排除

- 不是“无人说话”：故障前安静时音频包仍持续增长。
- 不是持续性麦克风硬件故障：同一台机器人在事件前较长时间内以预期码率稳定发送音频。
- 不是 OpenAI Realtime 断线：Realtime 会话持续连接并按计划轮换。
- 不是视频长期不可用：视频已经恢复并继续正常流动。
- 不是全局隐私静音：`listen=true`，状态不是 `muted`。

## 修复内容

修改文件：

- `ha-enabot/ebo/ebo_bridge.py`
- `ha-enabot/ebo/tests/test_audio_health.py`

实施内容：

1. 新增有界重试序列 `2.5s, 5s, 10s, 20s, 30s`。
2. 从 `on_user_joined` 启动恢复，而不是从 RTC 连接创建时启动。
3. 每次重试同时执行：
   - 重新发送 `OP_AUDIO_LISTEN {type: 1, open: 1}`；
   - 重新执行 `subscribe_audio` 与 `subscribe_all_audio`。
4. 一旦收到真实 PCM，立即停止重试。
5. RTC 或 observer 已被替换时停止旧恢复线程，防止跨会话操作。
6. 连接停止、音频功能关闭或用户全局关闭麦克风时立即停止，不突破隐私边界。
7. 重试总次数有上限，不制造无限命令或重连循环。
8. 保留原健康检查语义，没有通过放宽 `ok` 条件掩盖故障。

## 测试与验证

### 自动化测试

- 聚焦音频健康与功能测试：47 项通过。
- EBO Engine 完整测试套件：117 项通过，1 项按设计跳过。
- 测试环境：与生产镜像一致的 Python 3.11 容器。
- 新增覆盖：
  - 机器人加入后重复开麦与重复订阅；
  - 收到 PCM 后停止重试；
  - 用户主动静音后不执行恢复；
  - RTC/observer 换代后旧线程不再操作。

### 构建与现场验证

- `ebo-ai-home/ebo-engine:0.26.100` 镜像构建成功。
- 仅重建 `ebo-engine`；Home Assistant 未重启。
- 四次连续现场采样均显示 `receiving`、网络字节单调增长、码率稳定在预期范围、PCM 时间戳持续更新、`Assistant ok=true`，且 Docker 状态健康。

这些相互独立的信号共同证明源音频真实恢复，而不是静音填充导致的假阳性。公开报告省略实际时钟时间和原始计数。

## 后续建议

1. 将 `audio-recovery` 尝试次数和最近成功时间加入健康接口，方便后续报告直接展示恢复过程。
2. 为“RTC 先连接、机器人延迟加入”增加更高层的集成场景测试；本次已增加纯逻辑回归测试。
3. 保留严格源音频健康检查，不应仅以容器 Running、视频正常或 FFmpeg 有输出判断语音功能健康。

## 回滚说明

如新恢复逻辑出现意外行为，可回退本次代码提交，重新构建 `ebo-engine` 并只重建该容器。回滚不会修改 Home Assistant 配置、家庭录音、转写或机器人隐私设置。
