from content import add

add(16,'声音怎样从电脑回到机器人','Returning sound from the computer to the robot',
'大水杯里的水先换成机器人能接的小杯子，再按固定节奏递过去。',
'Transfer sound into the smaller cups the robot accepts, and pass them at a steady pace.',
'Assistant PCM24|内网 WebSocket\nstart 与二进制声音|Engine 重采样\n24 kHz 到 8 kHz|20 ms 一帧\nAgora 到 EBO 扬声器',
'Assistant PCM24|Internal WebSocket\nstart plus binary audio|Engine resampling\n24 kHz to 8 kHz|One frame per 20 ms\nAgora to EBO speaker',[
('Assistant 连接 ws://ebo-engine:8200/talk，先发送 start JSON，声明 token、node、stream_id、rate=24000、channels=1、format=pcm16。Engine 核对这些字段并返回 ready，随后声音使用 WebSocket 二进制消息传输，不再套一次 Base64。start 是开始协议，不是声音本身。',
'Assistant connects to ws://ebo-engine:8200/talk and sends a start JSON message declaring token, node, stream_id, rate=24000, channels=1 and format=pcm16. Engine validates these fields and returns ready. Audio then travels as binary WebSocket messages without another Base64 wrapper. The start message initiates the protocol; it contains no sound samples.'),
('PcmStream 用带连续状态的重采样器把 24 kHz 降到 8 kHz。连续状态保留相邻块之间的换算关系，避免把每块当独立文件转换。输出按 20 ms 分帧：8000 × 0.020 × 2 = 320 字节。最后不足一帧时补零，end 只表示不再有输入，队列仍要播放完。',
'PcmStream uses a stateful resampler to convert 24 kHz to 8 kHz. Preserving state maintains continuity across chunks instead of treating each as an independent file. Output is framed into 20 ms pieces: 8000 × 0.020 × 2 = 320 bytes. A final incomplete frame is zero-padded. end means no further input, but queued audio still needs to drain.'),
('桥接发送循环按实时节奏把 8 kHz PCM 帧交给 Agora 音轨，Agora 再负责网络媒体传输，机器人端接收并播放。不能把整段几秒音频瞬间塞进需要实时节奏的接口。当前 Engine 每台机器人只保留一条活动流，新流会停止旧流。',
'The bridge sends 8 kHz PCM frames to an Agora audio track at a realtime pace. Agora transports the media and the robot receives and plays it. Several seconds of audio cannot simply be pushed instantly into an interface that expects realtime pacing. Engine keeps one active stream per robot; a new stream stops the previous one.'),
('本地 8200 端口仅在 Docker 网络暴露，compose.yaml 没有把它映射给宿主机。WSS 是 Assistant 到 OpenAI 的加密连接；ws 是两个本地容器之间的连接。模型从来没有直接向机器人发一个 WAV 下载地址，主路径必须经过本地格式适配和 Agora。',
'Port 8200 is exposed only inside the Docker network; compose.yaml does not publish it on the host. WSS is the encrypted Assistant-to-OpenAI connection, whereas ws is the connection between the local containers. In the main path, the model does not send a WAV download URL directly to the robot. Local format adaptation and Agora transport remain necessary.')], 'S2 S3 S9')

add(17,'三种进度和总延迟','Three progress clocks and total latency',
'厨师做完、服务员送出、客人吃到，是三个不同时间。',
'The cook finishing, the waiter serving and the guest receiving are three different moments.',
'模型已生成\ngenerated_ms|Engine 已送出\nplayed_ms|网络与机器人缓冲|人实际听见\n需要实机验证',
'Model generated\ngenerated_ms|Engine submitted\nplayed_ms|Network and robot buffers|Person hears it\nRequires physical validation',[
('generated_ms 由生成 PCM 字节数换算。played_ms 在当前 Engine 实现中由成功送出播放帧的数量乘以 20 ms 得到，并通过 progress 大约每累计 100 ms 回报。这个名字容易让人误以为有机器人扬声器的精确听感回执；实际上它是发送侧进度代理，不包含完整的最后网络延迟与硬件播放延迟。',
'generated_ms is calculated from generated PCM length. In the current Engine, played_ms counts frames successfully submitted by the playback loop and multiplies by 20 ms. progress reports it roughly every additional 100 ms. Despite its name, this is a sender-side playback proxy, not an exact acknowledgment of sound physically heard from the robot; final network and hardware delay remain outside it.'),
('假设模型生成了 5 秒语音，Engine 只送出 400 ms 就收到停止命令：磁盘 WAV 可以有很多内容，人却只听到开头。这解释了为什么“WAV 有声音”“模型已完成”和“家人完整听见”是三种不同证据。这个例子用于说明机制，不是当前实时性能测量。',
'Suppose the model generates 5 seconds of speech but Engine submits only 400 ms before receiving stop. The saved WAV can contain substantial audio while the listener hears only the beginning. This explains why a non-silent WAV, a completed model response and a fully heard reply are different kinds of evidence. The numbers illustrate the mechanism, not a current performance measurement.'),
('从你说完到它开口，总时间由媒体上行、VAD 静音判断、转写与过滤、模型首块生成、预缓冲、本地连接、设备网络与扬声器缓冲共同决定。部分处理可以重叠，不能机械地把所有最大值相加。应给每段打时间戳并看首声时间和完整回答时间两个指标。',
'Time from your final word to the robot’s first sound includes media uplink, VAD silence detection, transcription and filtering, model first-audio generation, prebuffering, local connection, device-network transport and speaker buffering. Some stages overlap, so summing every worst-case value is misleading. Timestamp the stages and distinguish first-sound latency from full-reply completion time.'),
('降低模型推理档位、缩短 VAD 静音或减少预缓冲，都可能改善某一段速度，同时影响理解、轮流说话或连续播放。更快不必然更好，应一次改一组相关参数，用同样的说话方式比较。',
'Lower reasoning effort, shorter VAD silence or a smaller prebuffer may speed up one stage while changing comprehension, turn-taking or playback continuity. Faster is not automatically better. Change one related parameter group at a time and compare using the same spoken test.')], 'S2 S3 S9','timeline')

add(18,'流式播放失败时怎样降级','Fallback when streaming playback fails',
'小杯传水的通道坏了，就先装成整瓶再递过去，但可能要等更久。',
'If the small-cup route fails, prepare a whole bottle and send it through the fallback route, with a longer wait.',
'正常 PCM 流|连接或播放失败|保留完整 WAV\n通过本地 HTTP 提供|Engine talk URL\n下载 解码 再推送',
'Normal PCM stream|Connection or playback failure|Keep complete WAV\nServe over local HTTP|Engine talk URL\nFetch decode and transmit',[
('当本地流失败且回答没有被插话打断，Assistant 的 finalize 逻辑退回 WAV URL。WAV 由 Assistant 提供 HTTP 下载，Engine 的旧 talk 接口取到文件，再通过其音频路径送到机器人。降级仍要用 Agora 回到机器人，不是电脑扬声器代替 EBO 发声。',
'If the local stream fails and the reply was not intentionally interrupted, Assistant’s finalization falls back to a WAV URL. Assistant serves the WAV over HTTP; Engine’s older talk interface fetches it and sends it through its audio path to the robot. This fallback still uses Agora to reach the robot, rather than playing through the computer’s speaker.'),
('旧路径要先有完整 WAV，所以比真正逐块播放更晚开口。若前面已经播放一部分，随后整段回退播放，可能重复听到开头。当前实现没有根据用户真实听感精确剪掉 WAV 前缀；因此不要把自动降级理解成无缝续播保证。',
'The older path requires a complete WAV and therefore starts later than genuine incremental playback. If some audio already played before failure, replaying the whole WAV can repeat the beginning. The current implementation does not trim the WAV prefix based on exact listener experience, so automatic fallback is not a guarantee of seamless continuation.'),
('协议区分 end 和 stop。end 要求播放剩余队列；stop 要求丢弃未播放队列并停止。插话属于 stop，不能随后又用 WAV 把被打断的话完整补播。代码用 interrupted 标记阻止这种错误恢复。每条流用 stream_id 识别，避免新旧播放状态混在一起。',
'The protocol distinguishes end from stop. end drains the remaining queue; stop discards queued sound and stops. Interruption is a stop and must not be followed by replaying the entire interrupted answer as a WAV. The interrupted flag prevents that fallback. stream_id identifies each stream so old and new playback state can be distinguished.'),
('健康字段 speaker_stream_failures 和 speaker_stream_fallbacks 分别记录失败与降级次数。少数失败可能仍有回退声音；持续增加则说明应该检查内网流连接、Engine talk 能力和媒体会话。不要只凭“最终出声了”就判断主路径一直正常。',
'speaker_stream_failures and speaker_stream_fallbacks count failures and fallbacks separately. A failed attempt may still produce fallback audio; repeated growth indicates a need to inspect the internal stream connection, Engine talk capability and media session. Eventually hearing sound does not prove the primary path stayed healthy.')], 'S2 S3 S9','branch')

add(19,'回声为什么会让机器人打断自己','Why echo can make the robot interrupt itself',
'你拿着电话大声外放，麦克风又听到自己的话；机器人也会遇到这件事。',
'A microphone can hear the sound coming from its own loudspeaker, just as a speakerphone can hear itself.',
'模型声音|EBO 扬声器|房间反射与延迟|EBO 麦克风\n回声再次进入系统',
'Model audio|EBO speaker|Room reflections and delay|EBO microphone\nEcho re-enters the system',[
('机器人麦克风既能听见家人，也能听见自己的扬声器。后者经房间反射、延迟、编码和音量变化后，未必还与原始波形高度相似。若把“像语音”直接当成真人插话，就会刚说几个字又停下，甚至把自己的回答当成新的用户问题。',
'The robot microphone hears both family members and the robot speaker. Reflections, delay, codecs and volume changes can make the returned speaker sound look quite different from the original waveform. Treating anything speech-like as human interruption can stop a reply after a few words or turn the robot’s own answer into another user question.'),
('当前 EBO_BARGE_IN_ENABLED=false。Speaker 播放期间 input_muted 为真，麦克风仍被采集和计时，但普通路径不把它送入 OpenAI；关闭插话时也不会让本地插话门接管。因此得到较简单的轮流说话行为，代价是机器人说话时可能听不到家人的新话。它不是可靠全双工电话。',
'EBO_BARGE_IN_ENABLED is currently false. During Speaker playback, input_muted is true: microphone capture and timing continue, but the ordinary path does not forward audio to OpenAI. With interruption disabled, the local interruption gate does not take over either. This produces simpler turn-taking, at the cost of potentially missing speech while the robot talks. It is not a reliable full-duplex phone.'),
('AEC 是声学回声消除，尝试利用播放参考削弱扬声器回声；降噪抑制背景干扰；AGC 自动调整增益；VAD 决定像不像语音。这四个作用不同。当前 Engine AEC=true，Engine 降噪与 AGC=false，OpenAI 输入降噪=off，便于把回声链路与其他处理区分。',
'AEC, acoustic echo cancellation, uses a playback reference to reduce speaker echo. Noise suppression reduces background interference; AGC adjusts gain; VAD detects speech activity. They have different jobs. Current Engine AEC is true, Engine noise suppression and AGC are false, and OpenAI input noise reduction is off, keeping echo processing separate from the other processors.'),
('Engine 的 AEC 开关控制容器内 Agora SDK 的处理，不是刷写机器人固件。滤镜返回成功只证明处理链已挂接，不能证明真实房间里的回声已消除。特别是扬声器在远端机器人而 SDK 在电脑上，参考同步和回声路径必须用真实空房间与真人同时说话测试验证。',
'The Engine AEC switch controls processing inside the container’s Agora SDK; it does not modify robot firmware. A successful filter return code proves attachment, not effective echo removal in a real room. Because the speaker is on the remote robot while the SDK runs on the computer, reference timing and echo-path behavior need physical empty-room and simultaneous-speech tests.')], 'S2 S3 S13','loop')

add(20,'打开插话后会执行哪些动作','What happens when local interruption is enabled',
'先确认是真的有人插嘴，再让机器人停下，并告诉模型刚才只讲到了哪里。',
'Confirm a real interruption, stop the speaker and tell the model how far the previous reply got.',
'麦克风预录\n500 ms|本地 VAD 与回声比较\n确认真人插话|停止流与取消生成|截断模型音频历史\n回送预录后等待新回答',
'Microphone preroll\n500 ms|Local VAD and echo check\nConfirm interruption|Stop stream and cancel generation|Truncate model audio history\nSend preroll then await new reply',[
('可选 BargeInGate 用最近 500 ms 麦克风 PCM 保住插话句首；内部按 20 ms 语音帧判断，默认确认窗口 300 ms，并要求至少约 200 ms 像人声。代码还把麦克风与播放参考做延迟搜索、相关性比较，并检查减去参考后的残余语音。它是启发式门控，不是成熟 AEC 的同义词。',
'The optional BargeInGate retains 500 ms of microphone PCM to preserve the beginning of an interruption. It evaluates 20 ms speech frames within a default 300 ms confirmation window and requires roughly 200 ms of speech-like audio. It also searches delay against playback reference, compares correlation and checks residual speech after subtracting the reference. This is heuristic gating, not another name for a mature AEC system.'),
('当前代码的条件包含“相关度低于 0.65 或残余语音比例达到 0.45”。2026-09-02 的专项记录指出：纯回声也可能因相关度低而触发，甚至 residual=0 仍然打断。这个 OR 条件就是关键局限之一，因此本地插话当前保持关闭，文档不把这个功能写成已经通过实机可靠性验收。',
'The current condition includes correlation below 0.65 OR residual speech fraction at least 0.45. The focused 2026-09-02 incident note reports that echo alone could pass through low correlation, even with residual=0. This OR condition is a key limitation. Local interruption is currently kept off; the feature should not be described as having passed reliable real-device acceptance.'),
('触发后依次停止 Engine 流；若模型仍在生成则 response.cancel；发送 conversation.item.truncate，以 Engine 的 played_ms 为 audio_end_ms；再把预录音频追加给 OpenAI，并等待新语音最终转写通过过滤。cancel 阻止继续生成，truncate 修正对话历史，两者缺一就可能“停了嘴但模型仍以为已经说完”。',
'After a trigger, the program stops the Engine stream, sends response.cancel if generation is still active, and sends conversation.item.truncate using Engine played_ms as audio_end_ms. It then appends preroll audio to OpenAI and waits for validated final transcription. cancel stops generation; truncate corrects conversation history. Without both roles, the speaker may stop while the model still assumes the full reply was delivered.'),
('因为 played_ms 是发送侧代理，截断点仍只是近似。预录也可能保留回声；关闭插话则避免这类误触发但会漏听同时讲话。重新启用前，至少分别验证纯回声不打断、真人插话能打断、不会重复创建回答、被打断的 WAV 与元数据记录正确。',
'Because played_ms is a sender-side proxy, the truncation point is approximate. Preroll can also contain echo. Disabling interruption avoids these triggers but sacrifices simultaneous listening. Before re-enabling it, verify separately that pure echo does not interrupt, real speech does, responses are not duplicated and interrupted WAV metadata remains correct.')], 'S2 S9 S13')

add(21,'上下文窗口和费用控制','Context windows and cost controls',
'小书包装不下无限多的本子，装满时要挑出旧纸页；书包大小也不是钱包余额。',
'A schoolbag cannot hold unlimited notebooks. Older pages may need to go, and bag size is not the same as money left to spend.',
'角色与工具 instructions|不断增长的对话条目|post_instructions\n当前 8000 tokens|触发裁剪\n保留比例 0.8',
'Instructions and tools|Growing conversation items|post_instructions\nCurrent 8000 tokens|Truncation boundary\nRetain ratio 0.8',[
('token 是模型处理内容的计量单位，不等于一个中文字、一个英文词或一个音频字节。文字、音频和图片都可能占用模型上下文或产生计费。当前 gpt-realtime-2.1-mini 模型页列出 128000 上下文与 32000 最大输出，但本项目自己的显式整数输出校验仍限制在 1 到 4096；两种上限不能混写。[O1]',
'A token is a unit used by the model, not one Chinese character, English word or audio byte. Text, audio and images can occupy context or incur charges. The current gpt-realtime-2.1-mini model page lists a 128000 context window and 32000 maximum output, while this project still validates explicit integer output limits only from 1 to 4096. These are different limits. [O1]'),
('当前会话使用 retention_ratio，post_instructions=8000 为 instructions 后的对话内容设置上下文预算；不是留给回答的 8000 字，也不是总费用上限。到裁剪边界时保留比例 0.8，意味着为接下来的新内容腾出空间，而不是每一轮都固定丢掉 20%。',
'The session uses retention_ratio and post_instructions=8000 to budget conversation content after instructions. This is not 8000 characters reserved for an answer and is not a spending cap. A retention ratio of 0.8 leaves room for future content when truncation occurs; it does not discard a fixed 20% on every turn.'),
('max_output_tokens=inf 表示没有用一个显式整数压低这个字段，不表示无限长度、无限上下文或不花钱。输入图片只保留最近一张，语音转写后过滤、控制回答长度和上下文预算可以影响用量；但当前代码没有“达到某金额自动关机”的费用熔断器。',
'max_output_tokens=inf means the field is not lowered to an explicit integer; it does not mean infinite output, infinite context or free use. Keeping the latest image, filtering transcribed turns, limiting answer length and budgeting context influence usage. The current code has no circuit breaker that stops the service after a currency amount is spent.'),
('truncation=disabled 会让超出输入容量成为错误，而不是自动得到永久记忆。降低预算有利于控制持续对话的体积，却更早丢掉旧细节。磁盘保存的文本也不会因存在于电脑上就自动成为模型上下文；必须有重新注入的代码路径。',
'truncation=disabled turns an over-capacity conversation into an error rather than permanent memory. A lower budget constrains ongoing context size but drops older details sooner. Text saved on disk does not automatically become model context merely because it exists on the computer; a reinjection path is required.')], 'S2 S14','stack')

add(22,'为什么运行一小时左右要换会话','Why the service rotates its conversation session',
'接电话的朋友要换班，先写交接纸条，新同事才知道刚才聊到了哪里。',
'A worker changes shifts and writes a handoff note so the next worker knows where the conversation left off.',
'0 到 55 分钟\n正常会话|55 分钟后\n等待输入和生成空闲|不发声地生成摘要\n最多等 20 秒|59 分钟硬截止前\n新连接注入记忆',
'0 to 55 minutes\nNormal session|After 55 minutes\nWait for input and generation idle|Generate silent summary\nWait up to 20 seconds|By 59 minute deadline\nReconnect with memory',[
('当前 Realtime 会话最长 60 分钟的约束通过主动轮换适配。[O2] 服务本身可以长期运行：默认 3300 秒也就是 55 分钟开始考虑轮换，3540 秒也就是 59 分钟硬截止。换的是模型连接，不是要求家人重启机器人或整台电脑。',
'The current 60-minute Realtime session limit is handled by planned rotation. [O2] The service itself can run continuously: it begins considering rotation at 3300 seconds, or 55 minutes, with a hard deadline at 3540 seconds, or 59 minutes. It changes the model connection rather than requiring a robot or computer restart.'),
('如果本轮没有实际对话，可以直接换连接。有对话时，程序等待输入说话和普通回答生成不忙，再请求 conversation=none、output_modalities=[text] 的内部摘要，最多 600 输出 tokens，提示最多 1200 汉字；摘要字符串再受 handoff_memory_chars=4000 的本地字符上限限制。这几个限额不是同一个单位。',
'A session with no actual dialogue can reconnect directly. Otherwise the program waits until input speech and normal response generation are idle, then requests an internal summary with conversation=none and output_modalities=[text]. It caps the request at 600 output tokens, asks for at most 1200 Chinese characters and later caps the stored string at handoff_memory_chars=4000. These limits use different units.'),
('内部摘要作为 out-of-band 文本结果使用，不应由扬声器朗读，也不作为正常用户聊天回答加入默认对话。新连接把摘要追加到基础 Prompt。若 20 秒内没有新摘要，就使用先前已有记忆继续轮换；到硬截止即使忙也强制更换，所以边界附近可能丢失未完成片段。',
'The summary is an out-of-band text result: it should not be spoken or inserted as an ordinary reply in the default conversation. The new connection appends it to the base prompt. If no fresh summary arrives within 20 seconds, rotation proceeds with prior memory. The hard deadline forces rotation even while busy, so unfinished material near that boundary can be lost.'),
('忙碌判断查看输入语音与模型生成状态，并没有把“机器人队列全部播放完”作为完整独立条件。摘要也只是压缩信息，可能遗漏细节或沿用误解。它不是复制旧 Session，也不是对整个家庭历史进行完整检索。',
'The busy check tracks input speech and model generation; it does not independently guarantee that every robot playback queue has drained. A summary is compressed information and may omit detail or preserve an earlier misunderstanding. It is not a copy of the old Session or a complete search through household history.')], 'S2 S15','timeline')

add(23,'意外断线与重启能恢复什么','What reconnection and restart can recover',
'电话突然断了，拿最近的笔记接着聊；还没记下来的半句话可能已经丢了。',
'After a dropped call, use recent notes to continue. A half-sentence never written down may be lost.',
'网络意外断线|指数退避重连|读取近期完成文字\n默认 15 分钟|新会话加入背景\n可重送近期图片',
'Unexpected network loss|Reconnect with backoff|Read completed recent text\nDefault last 15 minutes|New session gets context\nMay reinsert recent image',[
('意外重连与计划交接不同。断线时不能假定旧连接还能生成摘要。程序从 transcripts.jsonl 与 assistant_outputs.jsonl 读取最近 900 秒内完成的文字，按时间排序，优先保留最新内容并受字符预算限制，再把这些记录标为历史背景放进新连接。',
'Unexpected reconnection differs from a planned handoff: after a failure, the old connection cannot be assumed able to summarize. The program reads completed text from transcripts.jsonl and assistant_outputs.jsonl within the last 900 seconds, sorts it by time, prioritizes recent content within a character budget and adds it as historical background to the new connection.'),
('同一进程还缓存最近运动选帧；在时效范围内且 visual_mode=context 时，意外重连可重新注入这张图。缓存并不是磁盘中的完整图像数据库。普通音频块和正在生成但未完成的回答不会逐字节补传恢复。指数退避延长连续失败后的重试间隔，避免网络故障时一直紧密重拨。',
'The same process also caches the latest motion-selected image. If it is recent enough and visual_mode=context, unexpected reconnection can reinsert it. This cache is not a complete on-disk image database. Ordinary audio blocks and unfinished generated replies are not restored byte-for-byte. Exponential backoff increases retry spacing after repeated failures instead of continually redialing at full speed.'),
('容器重建后，磁盘文件仍在，但进程中的交接摘要、图片和状态标记已丢失。当前启动路径不会仅因为旧日志存在就无条件把它们全读回：逐字恢复受 unplanned_reconnect 分支控制。不要把“持久化文件保留”解释成“重启后自动完整恢复对话”。',
'After container recreation, files remain but process-held summaries, images and state flags disappear. The current startup path does not unconditionally reload old logs just because they exist; transcript reinjection is controlled by the unplanned_reconnect branch. Persistent files must not be mistaken for automatic complete conversation recovery after restart.'),
('恢复的助手文字还可能包含被打断回答中人未实际听到的部分，因为恢复读取的是保存的 transcript，而不是严格按听感重新对齐的文本。排查续聊混乱时，要检查 interrupted、generated_ms 与 played_ms，以及记忆日志实际注入了什么。',
'Recovered assistant text can include parts of an interrupted reply the person did not actually hear, because recovery reads the saved transcript rather than text aligned to confirmed listening. To investigate confused continuation, examine interrupted, generated_ms and played_ms together with the actual contents of the memory-injection log.')], 'S2 S15 S16')

add(24,'哪些数据留在电脑上','What is stored on the computer',
'桌上的临时纸条和锁进柜子的本子，保存时间不一样，也不是同一个记忆。',
'A note on the desk and a notebook in a cabinet survive for different lengths of time; they are not the same memory.',
'transcripts.jsonl\n家人文字|replies WAV 与 TXT\n模型生成声音和文字|assistant_outputs.jsonl\n回答索引与播放元数据|logs session-memory.jsonl\n实际注入的动态记忆',
'transcripts.jsonl\nUser text|replies WAV and TXT\nGenerated audio and text|assistant_outputs.jsonl\nReply index and playback data|logs session-memory.jsonl\nInjected dynamic memories',[
('JSONL 是每行一个 JSON 对象：适合持续追加，一条记录坏了也可以单独检查其他行。用户转写文件记录时间、item_id、语言和 transcript。助手索引记录 response/item ID、声音和文字文件路径，并关联流式播放和打断元数据。WAV 保存的是生成声音，不是房间里重新录下的实际扬声器声音。',
'JSONL stores one JSON object per line, making it suitable for appending records and inspecting lines independently. User transcription includes time, item_id, language and transcript. The assistant index stores response/item IDs and audio/text paths, together with streaming and interruption metadata. A WAV contains generated sound, not a room recording of the physical speaker.'),
('session-memory.jsonl 单独记录新会话实际追加的交接摘要和断线记录，以及发送、确认、拒绝或不一致状态。sent 表示本地发送动作，confirmed 表示服务端回传的 instructions 与发送值相符。confirmed 仍不证明模型在每一句回答里正确使用了全部记忆。',
'session-memory.jsonl separately records the handoff and reconnection text actually added to a new session, with sent, confirmed, rejected or mismatch states. sent refers to the local send operation; confirmed means the server’s returned instructions match the submitted value. Confirmation does not prove that every later reply uses all memory correctly.'),
('默认动态记忆日志每份 1 MiB，保留当前文件和 3 份备份，约 4 MiB；Engine 主日志默认每份 10 MiB 加 5 份备份。用户转写、助手输出索引、WAV 和 TXT 没有自动保留期限清理，磁盘占用会增长。原始输入 PCM 未由当前 Assistant 全程写成录音文件。',
'Dynamic memory logs default to 1 MiB each, with the current file plus 3 backups, about 4 MiB. Engine logs default to 10 MiB each plus 5 backups. User transcripts, output indexes, WAVs and TXTs have no automatic age-based deletion and continue consuming disk. The current Assistant does not archive all incoming PCM as continuous microphone recordings.'),
('24 kHz 单声道 PCM16 回答每小时约 172.8 MB，WAV 头只增加很小开销；这是累计生成一小时声音的大小估算，不是每天必定产生的量。备份、删除和保留期限应围绕这些实际文件设计，删除日志与删除模型上下文是两种操作。',
'One accumulated hour of 24 kHz mono PCM16 reply audio is about 172.8 MB, plus small WAV headers. This is a size estimate for one hour of generated speech, not a guaranteed daily volume. Backup and retention procedures should address these files directly. Deleting logs and deleting model context are separate operations.')], 'S2 S16','cards')

add(25,'健康检查到底检查什么','What health checks actually establish',
'电话显示已接通还不够，还要确认画面和声音真的继续过来。',
'A connected-call icon is not enough; new pictures and sound must still be arriving.',
'Realtime 已连接|视频时间未过期|音频时间未过期|组合判断 ok\nDocker 定期检查',
'Realtime connected|Fresh video timestamp|Fresh audio timestamp|Combined ok state\nDocker checks periodically',[
('http://localhost:8099/health 返回 JSON 状态。视频和音频通常分别要求最近 20 秒内有更新；启动有 45 秒宽限期。realtime_connected、media_ok、video_streaming、audio_streaming 帮助区分云模型问题与设备媒体问题。单独 WebSocket 连接正常并不够。',
'http://localhost:8099/health returns JSON status. Video and audio normally each need an update within 20 seconds, with a 45-second startup grace period. realtime_connected, media_ok, video_streaming and audio_streaming distinguish model-connection failures from device-media failures. A working WebSocket alone is insufficient.'),
('2026-09-08 的只读检查返回 ok=true、Realtime 与音视频状态为真，确认 VAD 阈值 0.5、静音 650 ms、输入降噪为空即关闭。这是某一时刻的服务状态，不是全天可用率、端到端听感或 AEC 效果测试。视频仍在更新也不保证最近已经有选帧被模型接受。',
'A read-only check on 2026-09-08 returned ok=true, connected Realtime and active audio/video, with VAD threshold 0.5, silence 650 ms and null input noise reduction, meaning off. This is a point-in-time service check, not all-day availability, listening-quality validation or an AEC test. Fresh video also does not guarantee a recent selected image was accepted by the model.'),
('更细的检查应看 input_transcription_configured、user_transcripts_received、visual_context_items_added、speaker_stream_status、speaker_stream_played_ms 和 last_error。累计计数告诉你进程启动后的活动量，时间戳告诉你最近一次事件，二者不能互相替代。日志和健康字段也不完全等于实际音频内容。',
'More detailed checks include input_transcription_configured, user_transcripts_received, visual_context_items_added, speaker_stream_status, speaker_stream_played_ms and last_error. Counters describe activity since process start, while timestamps show when the latest event happened. They serve different purposes, and neither is equivalent to inspecting the actual audio.'),
('Compose 每 30 秒执行一次健康命令，超时 5 秒、重试 3 次。unhealthy 是状态标签；restart: unless-stopped 主要处理进程退出，并不意味着一标红就自动重启容器。媒体采集与模型连接自己的重试逻辑才负责许多在线恢复。',
'Compose runs a health command every 30 seconds, with a 5-second timeout and 3 retries. unhealthy is a status label. restart: unless-stopped mainly handles process exit; it does not mean an unhealthy label automatically restarts the container. Capture and model-connection retry loops perform much of the online recovery.')], 'S1 S2 S17')

add(26,'参数从文件到真正生效要经过什么','How configuration becomes effective',
'改了食谱纸，还要让厨师拿到新纸；旧锅里已经做好的菜不会自动变味。',
'Editing the recipe is not enough; the cook must receive it. A meal already cooking does not change itself.',
'.env 中写值|Compose 传入容器|Config 读取并校验|session.update\n服务端确认实际配置',
'Write .env values|Compose injects variables|Config reads and validates|session.update\nServer confirms configuration',[
('本书参数表区分 A、B、C 三类。A 类已接入 Compose 的 .env 值，可通过重新创建相关容器应用。B 类由 ebo-data/options.json 或启动脚本管理，不能保证只在 .env 增加同名变量就生效。C 类是代码常量或当前未由 Compose 转发的高级设置，需要改代码或部署映射。',
'The parameter catalog distinguishes A, B and C. A values are wired from .env through Compose and apply when the relevant container is recreated. B values are managed by ebo-data/options.json or startup scripts, so adding a similarly named .env variable is insufficient. C values are code constants or advanced settings not forwarded by Compose; they need code or deployment changes.'),
('Assistant 参数使用 scripts/reload-ebo-assistant-prompt.ps1 应用；它校验后只重新创建 Assistant。仅 docker compose restart 会用旧容器环境，不能作为可靠的 .env 更新方式。改变 Engine AEC、降噪、AGC 时使用 scripts/apply-ebo-audio-settings.ps1，它会构建 Engine 并重建 Engine 和 Assistant。',
'Apply Assistant settings through scripts/reload-ebo-assistant-prompt.ps1, which validates and recreates Assistant alone. docker compose restart reuses the old container environment and is not a reliable way to apply .env changes. For Engine AEC, noise suppression and AGC, use scripts/apply-ebo-audio-settings.ps1, which builds Engine and recreates Engine and Assistant.'),
('Engine run.sh 的优先级是 options.json、旧 panel.json 回退、内置默认。prepare-ebo.ps1 会重新生成 options.json，并把部分媒体值写回脚本默认值；因此不要在不检查差异的情况下用它刷新已经调好的视频参数。当前待机为 0，而 prepare 脚本默认写 5 分钟，就是需要注意的差异。',
'Engine run.sh prioritizes options.json, then legacy panel.json fallback, then built-in defaults. prepare-ebo.ps1 regenerates options.json and writes several media fields from script defaults. Do not use it to refresh tuned video settings without checking the differences. Current standby is 0, whereas the preparation script writes 5 minutes by default, illustrating this risk.'),
('修改前记下旧值，一次改一个目的明确的小组，应用后看容器日志和 health 确认，并用固定一句话或固定动作比较。JSON 参数必须是合法 JSON，空字符串和 [] 不总是同一语义。参数表里的范围首先是本地校验范围，模型是否支持还要看实际 session.updated 或错误。',
'Record previous values, change one purposeful group at a time, apply it, inspect logs and health, then compare using a repeatable utterance or movement. JSON settings must contain valid JSON; blank and [] do not always have the same meaning. Listed ranges primarily describe local validation. Model support still needs confirmation through session.updated or an error.')], 'S1 S2 S5 S12')

add(27,'工具调用和机器人移动的边界','Tool calls and the boundary around movement',
'告诉朋友“你可以开灯”并不会给他开关；还要真的装好开关线路。',
'Telling a friend “you can switch on the light” does not give them a switch; the wiring must exist.',
'模型提出 function call|本地验证参数|执行真实设备命令|返回 function_call_output\n模型继续回答',
'Model proposes function call|Local argument validation|Execute real device command|Return function_call_output\nModel continues',[
('图中是完整工具调用所需要的流程，不是当前已接通的移动能力。当前 Config 可以把 tools、tool_choice 和 parallel_tool_calls 发送给 Realtime；但 app.py 没有完整的函数调用执行器，把模型函数调用映射为机器人动作并返回工具结果。默认 tools=[] 还会显式清空存储 Prompt 可能附带的工具。',
'The diagram shows the workflow a complete tool integration would require, not movement capability already connected here. Config can send tools, tool_choice and parallel_tool_calls to Realtime, but app.py has no complete executor mapping model function calls to robot actions and returning results. The default tools=[] also explicitly clears tools that a stored prompt might supply.'),
('因此 OPENAI_REALTIME_TOOLS_JSON 是接口配置入口，不是“加一段 JSON 就让机器人自动驾驶”的开关。tool_choice=required 如果没有可用工具和执行链，会造成不适合当前语音助手的行为或接口错误。模型自己说“我已经移动了”也不构成动作证据。',
'OPENAI_REALTIME_TOOLS_JSON is an API configuration surface, not an “enable autonomous driving with JSON” switch. tool_choice=required without usable tools and an execution chain can produce unsuitable behavior or API errors. A model saying “I moved” is not evidence that movement occurred.'),
('Home Assistant 按钮和 Engine 控制 API 可以提供人工移动或设备控制，这与模型自治是另一条路径。若未来连接电机工具，至少需要明确执行器、参数约束、结果回执和停止机制，再用真实位置及障碍信息验证动作。那是新增功能，不是本说明书已经完成的工作。',
'Home Assistant buttons and Engine control APIs provide a separate manual-control path. Connecting motor tools in the future would require an explicit executor, argument limits, result reporting and stopping behavior, followed by validation against physical position and obstacles. That would be new functionality, not work already completed by this guide.'),
('同理，LLM Vision 的旧单帧分析可帮助测试摄像头和视觉服务，却不承担 Realtime 的多轮语音状态。不要把另一个组件“支持”的功能自动算成主助手“已经接好”的能力。',
'Similarly, the older LLM Vision single-image analysis can test the camera and vision provider, but does not manage Realtime voice conversation state. A feature supported by another component is not automatically a capability already integrated into the main assistant.')], 'S1 S2 S5','flow')

add(28,'现实限制如何变成架构取舍','How real constraints shaped the architecture',
'搭积木要看手里有什么形状；接口、硬件和网络决定哪些积木能直接接上。',
'Building blocks must fit. Interfaces, hardware and networks determine which pieces can connect directly.',
'设备协议与编码限制|标准化 HTTP RTSP PCM|成本与延迟折中|可观察状态与降级\n保留可维护性',
'Device protocol and codec limits|Standard HTTP RTSP PCM interfaces|Cost and latency tradeoffs|Observable state and fallback\nKeep the system maintainable',[
('设备依赖 Enabot/Agora，所以本地部署仍然依赖互联网设备服务。用 Engine 隔离这部分专有协议，使 Assistant 使用相对通用的 RTSP 和 PCM。代价是增加一层服务、鉴权和故障点；收益是以后换摄像头或机器人时不必重写所有模型逻辑。',
'Because the device depends on Enabot/Agora, local deployment still relies on internet device services. Engine isolates the proprietary protocol while Assistant uses relatively standard RTSP and PCM. This adds a service layer, authentication and failure points, but makes later camera or robot replacement less likely to require rewriting all model logic.'),
('视频采用解码后再编码，解决 SDK 编码帧路径和播放兼容问题，消耗更多 CPU。麦克风在 RTSP 中用 Opus，又解回 PCM，方便复用媒体入口但引入编解码与重采样开销。回复降到 8 kHz 适配设备，牺牲高频细节；不能靠 Prompt 恢复硬件和链路丢失的信息。',
'Video decoding and re-encoding work around the SDK encoded-frame path and playback compatibility issues, at a CPU cost. Microphone audio is encoded as Opus in RTSP and decoded back to PCM, reusing the media input but adding codec and resampling overhead. Replies are reduced to 8 kHz for the device, sacrificing high-frequency detail. A prompt cannot restore information lost in hardware or transport.'),
('选帧与最近一图降低视觉负担，却减少连续观察能力。等待最终转写降低部分误回答，却增加首声延迟且偏向中文。关闭插话减少回声误中断，却牺牲同时听说。定期摘要支持长时间运行，却无法无损保留全部历史。这些都是有代价的工程选择。',
'Frame selection and one-image context reduce visual load but weaken continuous observation. Waiting for final transcription rejects some unwanted replies but adds first-sound latency and favors Chinese. Disabling interruption reduces echo-triggered stops but sacrifices simultaneous listening. Periodic summaries support long operation but cannot preserve all history losslessly. Each is a tradeoff with a cost.'),
('目前项目保留 WAV、文字、索引和动态记忆日志，使问题可追溯；代价是磁盘增长和家庭记录管理。未来优化应先量出瓶颈，再决定减少编解码、增加视觉类别识别、改进回声同步或实现真正工具执行，而不是仅把模型换大就期待全部问题消失。',
'WAVs, text, indexes and memory logs make failures traceable, at the cost of growing storage and managing household records. Future optimization should measure bottlenecks before reducing codec stages, adding object classification, improving echo-reference timing or building a real tool executor. Merely selecting a larger model cannot be expected to solve every issue.')], 'S1 S2 S3 S4 S13','cards')

add(29,'跟着一次完整对话走一遍','Follow one complete conversation',
'把每个工人拿到的东西写出来，就知道一句话究竟走了多远。',
'List what each worker receives to see exactly how a single conversation travels.',
'家人挥手并问\n你看到什么|设备媒体到本地\n选图与音频上行|模型结合上下文\n生成声音小块|电脑适配与 Agora\n机器人说出回答',
'Family waves and asks\nWhat do you see|Device media reaches computer\nImage selection and audio upload|Model uses context\nGenerates audio chunks|Local adaptation and Agora\nRobot speaks the reply',[
('假设家人走进房间并挥手。摄像头媒体经 Agora 到达 Engine，SDK 解码画面、FFmpeg 发布 RTSP。Assistant 每秒检查两张图，在预热完成、变化区域合格、连续确认和冷却条件满足时，压缩并发出一张 JPEG。只有服务端接受后，这张图才成为已确认的最近视觉背景。',
'Suppose someone enters the room and waves. Camera media reaches Engine through Agora; the SDK decodes pictures and FFmpeg publishes RTSP. Assistant checks two pictures per second and sends a compressed JPEG only after warmup, sufficient motion, repeated confirmation and cooldown conditions are satisfied. It becomes the confirmed latest visual context only after server acceptance.'),
('家人说“你看到什么”。麦克风声音经 Engine 的 Opus 音轨进入本地 RTSP，Assistant 转成 24 kHz PCM，约每 100 ms 上行一次。server_vad 判断停顿，输入转写完成后中文过滤通过，Assistant 发送 response.create。图片和语音不保证精确时间同步，所以回答要承认只参考最近画面。',
'The person asks “What do you see?” Microphone sound passes through Engine’s Opus track into RTSP; Assistant converts it to 24 kHz PCM and uploads roughly every 100 ms. server_vad detects the pause, the final Chinese transcription passes the local filter, and Assistant sends response.create. Image and speech are not guaranteed to be precisely synchronized, so the answer must refer honestly to the latest picture.'),
('模型根据角色、对话和图像生成回复声音。Assistant 收到增量、积累 200 ms、连接本地 talk 流；Engine 把 24 kHz 换成 8 kHz，按 20 ms 向 Agora 提交；EBO 接收播放。当前关闭插话，播放过程中机器人麦克风数据不会按普通路径继续送给模型。',
'The model generates reply audio using the prompt, conversation and image. Assistant receives deltas, accumulates 200 ms and opens the local talk stream. Engine converts 24 kHz to 8 kHz and submits 20 ms frames to Agora for EBO playback. With local interruption disabled, microphone data during playback is not forwarded through the ordinary path to the model.'),
('音频生成和播放状态分别更新，WAV、TXT 和索引保存。家人再问“它是什么颜色”，如果所指对象仍在保留的对话和图片背景中，模型就可以续聊。若期间断线、图片过时或历史被裁剪，它并没有无条件知道“它”指什么；这时应说明不确定或请家人补充。',
'Generation and playback state update separately, and WAV, TXT and index records are saved. If the person next asks “What color is it?”, the model can continue when the referent remains in retained conversation and image context. After disconnection, stale imagery or truncation, the referent is not guaranteed. The assistant should acknowledge uncertainty or ask for clarification.')], 'S1 S2 S3 S4','lanes')

add(30,'出现问题时从哪一层开始查','Where to start when something goes wrong',
'水龙头没水，先沿管道找哪一段断了，不必把整座房子拆掉。',
'If the tap runs dry, trace the pipe to the broken segment instead of rebuilding the whole house.',
'容器和设备状态|视频与音频是否新鲜|转写与 response 是否发生|扬声器流与 WAV\n定位生成还是传输问题',
'Container and device state|Fresh video and audio|Transcription and response events|Speaker stream and WAV\nSeparate generation from delivery',[
('看不到画面时，先看 Engine 的 RTC 与视频更新，再看 RTSP 和 HA 摄像头入口。模型说没看见时，还要看 visual_context_items_added 和最近接受图片时间；HA 有画面并不证明模型刚收到图片。场景静止、冷却中和 scene_reset 都可能让选帧暂时不发送。',
'For missing video, check Engine RTC and fresh frames before RTSP and the HA camera entry. If the model says it cannot see, also inspect visual_context_items_added and the latest accepted-image time. Video on the dashboard does not prove the model recently received a picture. Stillness, cooldown and scene_reset can all suppress image uploads.'),
('不回应语音时，依次检查 audio_streaming、转写是否配置、是否有新的用户转写、是否被本地低信息过滤、manual_responses_requested 是否增加。若只说一两个英文词不回应，应考虑中文偏向的过滤。若在机器人说话时插嘴被忽略，首先考虑当前插话关闭这一已知行为。',
'For missing replies, inspect audio_streaming, transcription configuration, new user transcripts, local low-information filtering and manual_responses_requested in that order. Short English utterances may hit the Chinese-oriented filter. If speech during a robot reply is ignored, first consider the known behavior that local interruption is disabled.'),
('有完整 WAV 却没声音时，查看 speaker_stream_status、failures、fallbacks、played_ms，并核对 Engine talk 与 Agora 状态。只哼一下就停，要检查是否意外开启插话、interrupted 是否为真，以及是否重现回声误触发。WAV 正常能排除一部分生成问题，不能排除最后播放链路故障。',
'For a complete WAV with no audible reply, examine speaker_stream_status, failures, fallbacks and played_ms, then Engine talk and Agora state. A brief grunt followed by silence calls for checking whether interruption was enabled, interrupted is true or echo false triggers returned. A valid WAV rules out some generation failures, not failures in the final playback path.'),
('调试记录至少保留发生时间和时区、改动前后参数、对应 response_id、相关日志与同一条音频结果。不要把旧文档中的历史故障当成当前实测，也不要因某次 health 为真就删除重要证据。本书附录提供参数位置和代码函数，便于沿着同一条链继续追查。',
'For debugging, record time and timezone, before/after settings, the matching response_id, relevant logs and the corresponding audio result. Do not treat historical incidents as current measurements, or discard evidence because one health check passed. The appendices identify configuration locations and code functions for tracing the same path further.')], 'S2 S13 S17')
