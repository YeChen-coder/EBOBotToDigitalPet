# EBO 插话判断、回声处理与音频链路专项交接

> 更新时间：2026-09-02（America/Toronto）
> 项目根目录：`C:\Projects\ebo-ai-home`
> 当前 Git HEAD：`7e5f8f7 feat: support echo-aware barge-in`

## 1. 给下一位 ChatGPT/Codex 的任务

你只负责以下范围：

- 修复机器人播放模型语音时的错误插话判断。
- 研究并实现可靠的声学回声消除或回声感知判断。
- 修复与插话直接相关的音频状态、日志、测试和诊断工具。
- 保持流式播放、回答持久化和 OpenAI Realtime 上下文截断正确。

不要顺手改视频运动检测、Prompt、模型选择、Home Assistant、Session 轮换或其他功能。确需扩大范围前先向用户说明原因。

建议新会话直接使用下面这段话：

```text
请阅读：
C:\Projects\ebo-ai-home\docs\barge-in-echo-handoff.zh-CN.md

你在这个会话中只负责 EBO 的插话判断、声学回声处理和相关音频链路。
先复核文档中的现场证据和代码，不要直接调一个阈值就宣布完成。
先给出务实的技术选择和分阶段测试办法，经确认后再修改、测试、部署和提交。
不要破坏流式播放、WAV/文字持久化、response.cancel 与 conversation.item.truncate 的正确顺序。
```

## 2. 当前用户可见故障

家人的反馈是：

- 大声对机器人说话后，机器人似乎只“哼”一下。
- 几乎听不清回答，像是刚开始说就停了。

现场诊断结论：OpenAI 确实生成了有声音的回答，EBO Engine 也建立了播放流，但本地 `BargeInGate` 在播放开始约 280–800 ms 后把当前回答误判为被人插话，并执行停止、取消和截断。

这不是模型没有生成语音，也不是持久化 WAV 为空。

## 3. 2026-09-02 的现场证据

第三次提交部署后，当时共观察到：

- `manual_responses_requested = 8`
- `barge_in_count = 13`
- `speaker_stream_failures = 15`
- 新产生的 8 条回答全部为 `interrupted = true`
- 没有一条新回答完整播放
- Assistant、Realtime、视频和输入音频本身均处于连接状态

八条输出的脱敏统计如下：

| 本地时间 | 模型已生成 | Engine 已播放 | 结果 |
|---|---:|---:|---|
| 07:10:37 | 5200 ms | 400 ms | interrupted |
| 08:44:31 | 800 ms | 700 ms | interrupted |
| 08:44:37 | 800 ms | 300 ms | interrupted |
| 08:44:46 | 800 ms | 800 ms | interrupted |
| 08:44:51 | 800 ms | 280 ms | interrupted |
| 08:44:57 | 3200 ms | 320 ms | interrupted |
| 08:50:49 | 800 ms | 500 ms | interrupted |
| 08:50:54 | 2600 ms | 280 ms | interrupted |

典型误触发日志：

```text
barge-in confirmed: speech=300ms echo=0.012 residual=0.200 played=280ms
barge-in confirmed: speech=300ms echo=0.060 residual=0.000 played=280ms
barge-in confirmed: speech=220ms echo=0.031 residual=0.000 played=300ms
```

特别值得注意：多次 `residual=0.000` 仍触发了插话。即使算法自己的残余语音判断认为没有独立人声，另一个过于宽松的条件仍允许打断。

持久化 WAV 的音量检查结果证明这些文件不是静音或损坏数据：

- 平均音量约为 `-20.0` 至 `-26.7 dB`
- 峰值约为 `-2.5` 至 `-8.7 dB`

最近一条可用于核对的文件：

```text
assistant-data\replies\reply-resp_EJeiT2A3AKTUAaoqQ21g5.wav
```

它包含约 2.6 秒模型输出，但元数据显示机器人只播放了约 280 ms。

## 4. 只看音频时的系统结构

### 4.1 家人说话的输入路径

```text
家人声音
  ↓
EBO 麦克风
  ↓ Agora RTC（Engine 侧观察到 8 kHz 单声道）
EBO Engine / RTSP 音频
  ↓ FFmpeg 转为 24 kHz、单声道、PCM16
Realtime Assistant（每次读取约 100 ms）
  ├─ 机器人未说话：发送给 OpenAI input_audio_buffer
  └─ 机器人正在说话：不直接发给 OpenAI，先交给 BargeInGate
```

入口代码：

- `realtime-assistant/app.py` 的 `MediaCapture.audio_loop()`，约第 2174 行。
- 机器人说话期间的分支在约第 2191 行。

### 4.2 模型回答的输出路径

```text
OpenAI response.output_audio.delta（24 kHz PCM16）
  ↓
Realtime Assistant Speaker
  ↓ 预缓冲 200 ms
ws://ebo-engine:8200/talk
  ↓ audioop.ratecv：24 kHz → 8 kHz
EBO Engine：每 20 ms 发送一个 Agora PCM 帧
  ↓
EBO 扬声器
```

关键代码：

- `realtime-assistant/app.py`
  - `Speaker.stream_delta()`：约第 983 行
  - `Speaker._stream_worker()`：约第 1036 行
  - `Speaker.interrupt()`：约第 1228 行
  - `RealtimeClient.handle_barge_in()`：约第 1808 行
- `ha-enabot/ebo/pcm_talk.py`
  - 24 kHz → 8 kHz 转换、队列和 WebSocket 协议
- `ha-enabot/ebo/ebo_bridge.py`
  - `_audio_tx_loop()`：向 Agora 发送 20 ms 帧
  - `_activate_pcm_stream()`：启动一条机器人播放流

## 5. 当前插话算法

配置位于项目 `.env`：

```env
EBO_BARGE_IN_ENABLED=true
EBO_BARGE_IN_CONFIRM_MS=300
EBO_BARGE_IN_PREROLL_MS=500
EBO_BARGE_IN_VAD_MODE=2
EBO_BARGE_IN_ECHO_CORRELATION=0.65
EBO_BARGE_IN_RESIDUAL_RATIO=0.45
EBO_STREAM_PREBUFFER_MS=200
EBO_STREAM_CONNECT_TIMEOUT_SECONDS=10
```

`BargeInGate` 当前做法：

1. 保留最近 500 ms 麦克风音频。
2. 把 24 kHz 输入用 `samples[::3]` 简单抽取到 8 kHz。
3. 使用 WebRTC VAD mode 2，对 20 ms 帧判断是否像语音。
4. 300 ms 窗口中，只要至少 200 ms 被 VAD 判断为语音，就进入回声判断。
5. 用“模型生成的 24 kHz 原始输出”与麦克风最近 300 ms 做最多 500 ms 延迟搜索和归一化相关。
6. 尝试按最佳相关结果减去回声，计算残余语音比例。
7. 当前确认条件是：

```python
enough_speech = speech_ms >= 200
independent = (
    correlation < echo_correlation
    or residual >= residual_ratio
)
trigger = enough_speech and independent
```

代码位置：`realtime-assistant/app.py` 的 `BargeInGate`，约第 570–707 行。

## 6. 已确认的问题

### 6.1 `OR` 条件过于宽松

只要相关度低于 0.65，即使残余语音比例为 0，也会触发。真实房间里的机器人回声经过扬声器、空气、麦克风、RTC、编码/重采样后，与原始数字 PCM 很难保持 0.65 以上的直接相关，因此“低相关”不能单独作为真人存在的证据。

WebRTC VAD 只能回答“这像不像语音”，不能回答“这是家人的声音还是机器人自己的声音”。机器人播放的语音自然会被 VAD 判断为语音。

### 6.2 回声参考点不理想

当前参考是 Assistant 中尚未经过 Engine 重采样和实际发送的 24 kHz 模型音频，并用 `played_ms` 推测哪一段已播放。

更可靠的 far-end reference 应当来自 Engine 实际发送给 Agora 的 8 kHz、20 ms 帧，并带有单调时钟时间戳或连续帧序号。当前只有累计 `played_ms`，没有把实际发送帧反馈给回声处理器。

### 6.3 时钟、队列和声学路径未建模

现有算法需要同时面对：

- Assistant 预缓冲。
- Docker/WebSocket 队列。
- Engine 24 kHz → 8 kHz 重采样状态。
- Agora 发送和机器人内部播放延迟。
- 扬声器到麦克风的房间脉冲响应。
- 自动增益、噪声抑制或设备端处理带来的波形变化。

简单滑动相关只能覆盖固定延迟，不能稳定处理这些滤波、增益和漂移。

### 6.4 误触发会形成自激循环

一旦机器人自己的声音被判定为插话：

1. 当前模型回答被取消。
2. 已播放位置之后的模型上下文被截断。
3. 500 ms 麦克风预录被发给 OpenAI。
4. 这段预录可能主要是机器人自己的回声。
5. OpenAI 把回声当成新的家人输入并生成下一条回答。
6. 新回答再次被自己的回声打断。

这可以解释为什么 8 次正式回答对应 13 次插话事件，以及短时间内连续出现多条 0.8 秒输出。

### 6.5 `speaker_stream_failures` 大多是误计数

Engine 日志显示流通常经历了正常的：

```text
[talk-stream] ready: stream_xxx
[talk-stream] released stream_xxx at 280 ms
```

没有发现对应的 Agora `send error`。Assistant 主动发送 `stop` 后，Engine 返回 `stopped` 并关闭 WebSocket；Assistant 随后又尝试 `recv()`，把正常关闭记录为 `Connection to remote host was lost`。

因此 15 次 `speaker_stream_failures` 主要是插话停止后的状态机/指标错误，不足以证明 Engine 播放链路独立故障。修复时应让客户端收到 `stopped` 后立即正常结束，不能再进入下一轮 `recv()`，也不应触发 WAV fallback。

## 7. OpenAI Realtime 不能破坏的协议约束

本项目通过 WebSocket 使用 Realtime API。OpenAI 官方文档明确说明：WebSocket 客户端负责本地音频播放，因此发生插话时客户端必须：

1. 停止本地播放。
2. 记录实际已经播放的音频长度。
3. 取消仍在生成的回答。
4. 用 `conversation.item.truncate` 删除模型上下文中用户没有听到的后半段。

官方说明：

- <https://developers.openai.com/api/docs/guides/realtime-conversations#interruption-and-truncation>

本项目使用应用自己的回声确认，所以 Session 中设置：

```json
{
  "interrupt_response": false
}
```

不要在本地确认之前让服务端自动取消回答。确认真人插话之后，当前代码的核心顺序需要保留：

```text
Engine stop
→ response.cancel（若模型仍在生成）
→ conversation.item.truncate(audio_end_ms = Engine 实际 played_ms)
→ input_audio_buffer.append(500 ms preroll)
→ 后续正常收音、commit/转写
→ 只创建一次新 response
```

需要专门测试重复事件、`response.done` 与本地插话并发、以及生成已完成但播放未完成的情况。

## 8. 建议的务实处理顺序

### 阶段 A：先恢复可用性

在研究期间，建议先将：

```env
EBO_BARGE_IN_ENABLED=false
```

然后只重建 `realtime-assistant`。这会保留边生成边播放、语音输入和持久化，只暂时关闭机器人说话期间的插话能力。

未经用户授权不要直接修改当前 `.env`；文档编写时该值仍为 `true`。

### 阶段 B：先建立可观测性，再选算法

不要只根据线上 `correlation` 数字继续盲调阈值。增加可由环境变量开启的短时诊断录制，至少同步保存：

- near-end：EBO 麦克风收到的 PCM。
- far-end generated：模型生成的 24 kHz PCM。
- far-end rendered：Engine 实际发送给 Agora 的 8 kHz、20 ms 帧。
- 单调时钟、帧序号、WebSocket 收发时间、`played_ms`。
- 每个 20 ms 帧的 VAD、相关度、残余比例和最终决策。

隐私和磁盘要求：

- 默认关闭诊断录音。
- 明确开启后才保存。
- 文件轮转并限制总容量。
- 不得提交任何家庭录音、转写或 `.env`。
- 诊断目录必须加入 `.gitignore`。

### 阶段 C：建立带标签的现场样本

至少采集以下场景，并明确标注 ground truth：

1. 空房间，机器人连续说 30 段话。
2. 机器人说话，电视或家电在背景发声。
3. 家人在近距离正常音量插话。
4. 家人在远距离、大声和小声插话。
5. 家人从机器人第一句话开始前后连续讲话。
6. 不同房间位置、机器人音量和地面材质。
7. 连续两次插话，以及插话后保持沉默。

### 阶段 D：技术选择优先级

优先研究成熟的声学回声消除（AEC），而不是继续只用 VAD + 波形相关：

1. **WebRTC Audio Processing / AEC3**：首选研究方向。它需要同步的 far-end render reference 和 near-end capture，能够适应声学路径变化。
2. **SpeexDSP echo canceller**：如果 Python/C++ 集成和部署更简单，可作为较轻量备选，但仍需要准确的播放参考与时序。
3. **Engine 侧处理**：因为 Engine 掌握实际发送的 8 kHz 帧，AEC 或参考帧时间戳放在 Engine 附近通常比 Assistant 仅凭 `played_ms` 推算更可靠。
4. **WebRTC VAD / Silero VAD**：只作为“是否有语音”的一层，不能单独区分回声与真人。
5. **RNNoise/一般降噪**：主要处理稳态噪声，不等同于声学回声消除，不能把它当作 AEC 替代品。

可以做一个保守的短期版本验证链路，但不能把它当最终方案：

- 不再允许“低相关”单独触发真人插话。
- 要求残余语音达到阈值，并增加连续性/能量优势条件。
- 播放启动后给参考环形缓冲一个短暂建立期。
- 添加触发后的 debounce，禁止同一输入产生多次取消。
- 插话预录在确认前绝不能送入 OpenAI。

单纯把 `0.65` 改成更低数字并不充分，因为缺少带标签的数据，而且当前参考信号本身尚未对齐实际播放点。

## 9. 验收标准

### 9.1 不误打断

- 空房间连续播放至少 30 条长回答，误打断为 0。
- 普通家居噪声和电视声音不得造成连续自激回答。
- 机器人自己的声音不得被作为新用户输入转写。

### 9.2 真插话有效

- 家人插话达到确认条件后，Engine 停声延迟目标不超过 100 ms。
- 总体感知延迟需要单独报告：确认窗口本身与停声执行时间不能混为一谈。
- 500 ms 预录必须保住家人第一个音节。
- 插话内容只生成一次新回答。

### 9.3 上下文正确

- `played_ms` 必须来自 Engine 实际成功发送的 20 ms 帧，不得用模型生成时长代替。
- `conversation.item.truncate.audio_end_ms` 必须等于或保守地不超过实际播放时长。
- 家人未听到的模型后半段不能继续留在 Realtime conversation 中。

### 9.4 播放和持久化不回归

- 第一段音频仍在 `response.output_audio.done` 之前开始播放。
- 完整回答继续保存完整 WAV 和文字。
- 真插话继续保存部分 WAV，并记录 `interrupted/generated_ms/played_ms/stream_id`。
- 流接口真正失败时仍能走完整 WAV URL fallback。
- 主动 `stop` 不得计为 `speaker_stream_failures`。

## 10. 建议补充的测试

现有单元测试只用理想化的正弦波证明相关算法在合成条件下成立，无法代表真实房间。

下一版至少应增加：

- 非线性增益、带通滤波、重采样和混响后的纯回声样本。
- far-end 与 near-end 时钟轻微漂移。
- 参考帧到达晚于/早于 `played_ms` 状态更新。
- 纯回声且相关度低于 0.65 时不得触发。
- `residual=0` 时无论相关度多低都不得触发。
- 真人与回声同时存在时应触发。
- `stopped` 后 WebSocket 正常关闭不得计为失败。
- 一个误触发/重复事件不能创建多个回答。
- 生成完成但还没播放完时插话，仍正确更新持久化元数据。

相关现有测试：

```text
realtime-assistant/tests/test_app.py
ha-enabot/ebo/tests/test_pcm_talk.py
```

## 11. 调试位置和命令

健康状态：

```text
http://localhost:8099/health
```

重点字段：

```text
speaker_stream_status
speaker_stream_played_ms
speaker_stream_failures
speaker_stream_fallbacks
barge_in_count
last_barge_in_speech_ms
last_barge_in_echo_correlation
last_barge_in_residual_ratio
last_error
```

容器日志：

```powershell
cd C:\Projects\ebo-ai-home
docker compose logs --since 2h --no-color realtime-assistant
docker compose logs --since 2h --no-color ebo-engine
```

输出元数据与音频：

```text
assistant-data\assistant_outputs.jsonl
assistant-data\replies\reply-*.wav
assistant-data\replies\reply-*.txt
assistant-data\transcripts.jsonl
```

日志时区注意：Assistant 日志显示宿主机本地时间；Engine 的短时间戳曾表现为 UTC。例如 Engine 的 `12:44` 对应 Assistant 的本地 `08:44`。

## 12. 修改和提交边界

开始前：

```powershell
git status --short
git log -3 --oneline
```

当前基线提交：

```text
7e5f8f7 feat: support echo-aware barge-in
79b5353 feat: stream realtime audio to EBO speaker
d84d5cd chore: checkpoint current EBO assistant
```

不要覆盖用户的 `.env`、录音、运行数据或无关改动。代码改完后需要：

1. 跑 Assistant 和 Engine 的相关单元测试。
2. 构建两个受影响镜像。
3. 先做无机器人或合成回放测试。
4. 再做实机“纯回声”和“真人插话”测试。
5. 检查健康页、日志、WAV、文字和 JSONL 元数据。
6. 只有验收后才部署和提交。

## 13. 当前最重要的结论

当前第三次提交不适合继续以 `EBO_BARGE_IN_ENABLED=true` 长期运行。主要故障是本地回声判断误触发，不是 OpenAI 音频生成失败。修复应围绕“取得实际播放参考、建立同步诊断数据、使用成熟 AEC 或更可靠的双讲检测”展开，而不是继续孤立地调整一个相关度阈值。
