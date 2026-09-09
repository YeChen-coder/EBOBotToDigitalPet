GROUPS=[]
def group(zh,en,rows,nz,ne): GROUPS.append(dict(title=[zh,en],rows=rows,note=[nz,ne]))
# name, default, explanation in Chinese and English, configuration class
group('模型与回答','Model and output',[
('OPENAI_REALTIME_MODEL','gpt-realtime-2.1','Realtime 模型名；当前 Mini。更换后重建 Assistant，需账号支持。','Realtime model ID; currently Mini. Recreate Assistant and verify account access.','A'),
('OPENAI_REALTIME_VOICE','marin','声音名称或 voice_... ID；当前 verse。首次发声后不能在同一 Session 换声音。','Voice name or voice_... ID; currently verse. A voice cannot change after first audio in the same Session.','A'),
('OPENAI_REALTIME_OUTPUT_SPEED','1.0','语速 0.25–1.5；大于 1 较快。它不是生成速度。','Speech speed 0.25–1.5; above 1 is faster playback, not faster generation.','A'),
('OPENAI_REALTIME_OUTPUT_MODALITY','audio','audio 或 text。text 不会经当前扬声器路径发声。','audio or text. text produces no speaker audio through this path.','A'),
('OPENAI_REALTIME_REASONING_EFFORT','','空或 minimal low medium high xhigh；支持程度因模型而异。','Blank or minimal, low, medium, high, xhigh; support depends on model.','A'),
('OPENAI_REALTIME_MAX_OUTPUT_TOKENS','inf','本地校验 inf 或整数 1–4096；每次回答上限，不是月度额度。','Local validation: inf or integer 1–4096. Per-response cap, not a monthly quota.','A'),
('OPENAI_REALTIME_INCLUDE_TRANSCRIPTION_LOGPROBS','false','布尔值；要求转写概率信息，不会自动新增识别准确率门控。','Boolean; requests transcription log probabilities, without adding an automatic confidence gate.','A')],
'模型页最大输出能力与当前 API 字段、本地校验范围是不同层。voice 内置集合见正文与代码；不要把更换声音理解为克隆任意人的声音。',
'Model-page capacity, API-field limits and local validation are different layers. Built-in voices are enumerated in the code. Selecting a voice does not clone an arbitrary person.')

group('输入转写','Input transcription',[
('OPENAI_INPUT_TRANSCRIPTION_MODEL','gpt-transcribe','非空。当前系统依赖转写来记录和触发回答，不能整体关闭。','Required. The current system depends on transcription for records and response gating.','A'),
('OPENAI_INPUT_TRANSCRIPTION_DELAY','','空或 minimal low medium high xhigh；项目说明限定用于 gpt-realtime-whisper。','Blank or minimal, low, medium, high, xhigh. Project notes limit this setting to gpt-realtime-whisper.','A'),
('OPENAI_INPUT_TRANSCRIPTION_KEYWORDS_JSON','[]','字符串数组，如 ["EBO","药盒"]；提示词汇，不是唤醒词检测器。','String array, e.g. ["EBO","药盒"]. Vocabulary hints, not a wake-word detector.','A'),
('OPENAI_INPUT_TRANSCRIPTION_LANGUAGE','','单语言提示，如 zh 或 en；不会改写本地中文偏向过滤。','Single language hint such as zh or en; does not change the Chinese-oriented local filter.','A'),
('OPENAI_INPUT_TRANSCRIPTION_LANGUAGES_JSON','[]','候选语言字符串数组，如 ["zh","en"]；检查所选转写模型兼容性。','Candidate language array such as ["zh","en"]; verify support for the transcription model.','A'),
('OPENAI_INPUT_TRANSCRIPTION_PROMPT','','转写专用提示，帮助处理词汇背景；不是机器人角色 Prompt。','Transcription-specific text for vocabulary/context, separate from the assistant persona.','A')],
'关键词、语言、自由文本提示并非所有转写模型都通用。先确认输入配置被服务端接受，再用含目标词汇的一句话验证。',
'Keywords, languages and free-text hints are not universally supported by every transcription model. Confirm server acceptance and test an utterance containing the target vocabulary.')

group('降噪与 VAD 数值','Noise reduction and numeric VAD settings',[
('REALTIME_INPUT_NOISE_REDUCTION','off','off near_field far_field；off 发 null。降低噪声不等于消除扬声器回声。','off, near_field or far_field; off sends null. Noise reduction is not speaker echo cancellation.','A'),
('REALTIME_TURN_DETECTION_TYPE','server_vad','server_vad 或 semantic_vad；当前不支持 null 手动提交模式。','server_vad or semantic_vad. No null/manual-commit mode is implemented.','A'),
('REALTIME_VAD_THRESHOLD','0.55','0–1；当前 0.5。调高更保守，可能漏轻声；不是麦克风音量旋钮。','0–1; currently 0.5. Higher is more conservative and may miss quiet speech; not microphone volume.','A'),
('REALTIME_VAD_PREFIX_PADDING_MS','300','0–5000 ms；保留触发前音频，减少句首缺字。','0–5000 ms; retains pre-detection audio to preserve initial syllables.','A'),
('REALTIME_VAD_SILENCE_DURATION_MS','650','100–10000 ms；越短越快接话，但更容易切断停顿。','100–10000 ms; shorter starts replies sooner but may cut into pauses.','A'),
('REALTIME_VAD_IDLE_TIMEOUT_MS','0','0 不发送；否则 5000–30000 ms。与设备待机无关。','0 omits the field; otherwise 5000–30000 ms. Separate from robot standby.','A')],
'先保持 prefix 和 silence 不变，只用小步长调 threshold 来判断背景噪声误触发与轻声漏检的平衡。这里列出的范围是 Config.validate 的范围。',
'Keep prefix and silence unchanged while adjusting threshold in small steps to compare noise triggers with missed quiet speech. These ranges come from Config.validate.')

group('回合策略与声学处理','Turn policy and acoustic processing',[
('REALTIME_SEMANTIC_VAD_EAGERNESS','auto','auto low medium high；仅 semantic_vad 时发送。','auto, low, medium or high; sent only for semantic_vad.','A'),
('REALTIME_VAD_CREATE_RESPONSE','false','false 等最终转写过滤；true 由服务端自动回答并绕过该触发策略。','false waits for final transcript filtering; true lets the server respond automatically.','A'),
('REALTIME_VAD_INTERRUPT_RESPONSE','true','本地插话启用时实际强制 false；否则发送该值。','Forced to false when local interruption is enabled; otherwise sent as configured.','A'),
('EBO_AGORA_AEC_ENABLED','false','布尔；当前 true。控制 Engine Agora AEC，不改固件。','Boolean; currently true. Controls Engine Agora AEC, not firmware.','A'),
('EBO_AGORA_NOISE_SUPPRESSION_ENABLED','false','布尔；Engine 降噪。独立于 OpenAI 输入降噪。','Boolean; Engine noise suppression, independent of OpenAI input noise reduction.','A'),
('EBO_AGORA_AGC_ENABLED','false','布尔；自动增益可能提高轻声也放大噪声，需逐项实测。','Boolean; automatic gain can amplify quiet speech and noise, requiring isolated testing.','A')],
'VAD 参数应用到 Assistant；三个 Agora 音频开关用 apply-ebo-audio-settings.ps1。处理链挂载成功与实际回声效果是两项验收。',
'VAD settings apply to Assistant. Use apply-ebo-audio-settings.ps1 for the Agora switches. Filter attachment and actual echo reduction require separate validation.')

group('流式播放与插话','Speaker streaming and interruption',[
('EBO_TALK_STREAM_URL','ws://ebo-engine:8200/talk','内网流地址；改端口要与 Engine 同步。','Internal streaming endpoint; coordinate port changes with Engine.','A'),
('EBO_STREAM_PREBUFFER_MS','200','0–2000 ms；增大会延后开口并缓冲到达抖动。','0–2000 ms; larger values delay start and absorb arrival jitter.','A'),
('EBO_STREAM_CONNECT_TIMEOUT_SECONDS','10','1–60 秒；本地 WebSocket 建连等待。','1–60 seconds; local WebSocket connection timeout.','A'),
('EBO_BARGE_IN_ENABLED','true','布尔；当前 false。启用有历史回声误触发风险，见第 20 章。','Boolean; currently false. Historical echo false triggers are explained in section 20.','A'),
('EBO_BARGE_IN_CONFIRM_MS','300','至少 200，且被 20 整除；更长确认窗口一般更慢触发。','At least 200 and divisible by 20; a longer confirmation window generally delays triggering.','A'),
('EBO_BARGE_IN_PREROLL_MS','500','至少等于 confirm；保留插话句首，可能同时保留回声。','At least confirm; retains the start of speech and may retain echo too.','A')],
'默认值不是本机当前启用值。不要因为表中默认 true 就误认为当前可边说边听。',
'A default is not the currently enabled setting. The true default must not be read as evidence of working simultaneous listening.')

group('插话判据与视觉采样','Interruption criteria and visual sampling',[
('EBO_BARGE_IN_VAD_MODE','2','0 1 2 3；WebRTC VAD 模式，较高通常更严格。','0, 1, 2 or 3; WebRTC VAD mode, generally more aggressive at higher levels.','A'),
('EBO_BARGE_IN_ECHO_CORRELATION','0.65','0–1；当前算法低相关度可以单独触发，不能当成熟 AEC 使用。','0–1; low correlation alone can trigger in the current heuristic; not a mature AEC control.','A'),
('EBO_BARGE_IN_RESIDUAL_RATIO','0.45','0–1；回声相减后独立语音帧比例门槛，不是剩余音量百分比。','0–1; residual speech-frame fraction threshold, not remaining audio volume.','A'),
('MOTION_FPS','2','本地每秒检查帧数。增加会提高 CPU 与采样频度；没有对应的严格范围校验。','Local frames checked per second. More increases CPU and sampling frequency; no dedicated strict range validation.','A'),
('MOTION_THRESHOLD','25','灰度差阈值；越低越容易把小变化当运动。','Grayscale difference threshold; lower values detect smaller differences.','A'),
('MOTION_MIN_AREA_RATIO','0.003','最大变化区域占比门槛，默认约 0.3%；越低越敏感。','Largest changed-region fraction threshold; default about 0.3%. Lower is more sensitive.','A')],
'运动参数虽然能从 .env 读取，并非全部具有严格范围校验。应使用有意义的正值或比例，并通过日志观察 quiet、confirming、scene_reset 等结果。',
'Motion values are readable from .env but do not all have strict range validation. Use meaningful rates and fractions, then inspect quiet, confirming and scene_reset decisions.')

group('选图和图片大小','Image selection and image size',[
('MOTION_MAX_CHANGE_RATIO','0.55','整体变化达到该比例即重设背景，常见于转头或开灯。','Resets background when overall change reaches this fraction, as with camera movement or lights.','A'),
('MOTION_CONFIRM_FRAMES','2','连续合格帧数；更高减少偶发触发，但更慢。','Consecutive qualifying frames; higher reduces isolated triggers but responds later.','A'),
('MOTION_COOLDOWN_SECONDS','12','两次发送的最短间隔；不是定时强制拍照周期。','Minimum interval between sends; not a forced periodic snapshot schedule.','A'),
('REALTIME_IMAGE_WIDTH','768','上传图片最大宽度，保持比例，不放大小图；越大体积通常越大。','Maximum uploaded width, preserving aspect ratio and not upscaling smaller images. Larger usually means more data.','A'),
('REALTIME_IMAGE_QUALITY','75','JPEG 质量。常用有效区间 0–100；过低会损失细节。','JPEG quality; normally 0–100. Very low values lose detail.','A'),
('EBO_VISUAL_MODE','context','context 只供背景；announce 在选图被接受后主动请求回答。','context supplies background; announce requests a reply after an image is accepted.','A')],
'这些是给模型看图的参数，不是 Engine 输出直播的 fps、码率或分辨率。两层分别调整，才能知道节省的是 CPU、局域网流量还是模型图片用量。',
'These control model images, not Engine livestream fps, bitrate or resolution. Tune the layers separately to identify savings in CPU, local-network traffic or image usage.')

group('上下文与会话轮换','Context and session rotation',[
('OPENAI_REALTIME_TRUNCATION_TYPE','retention_ratio','auto disabled retention_ratio；disabled 超限会报错。','auto, disabled or retention_ratio; disabled errors when capacity is exceeded.','A'),
('OPENAI_REALTIME_RETENTION_RATIO','0.8','0–1；仅 retention_ratio 模式使用，裁剪发生时保留比例。','0–1; used in retention_ratio mode, as the retained fraction when truncation occurs.','A'),
('OPENAI_REALTIME_POST_INSTRUCTIONS_TOKENS','8000','本地要求非负；还受模型输入容量限制，不是费用金额。','Must be nonnegative locally and fit model input capacity; not a currency amount.','A'),
('REALTIME_SESSION_REFRESH_SECONDS','3300','至少 60 秒并小于硬截止；开始等待空闲并准备交接。','At least 60 seconds and below hard deadline; starts idle waiting and handoff.','A'),
('REALTIME_SESSION_HARD_DEADLINE_SECONDS','3540','必须大于刷新时间且小于 3600 秒；忙时也可能强制轮换。','Above refresh and below 3600 seconds; can force rotation while busy.','A'),
('REALTIME_HANDOFF_TIMEOUT_SECONDS','20','1–120 秒；等待新摘要的最长时间，超时使用原有记忆。','1–120 seconds; timeout waiting for a new summary, falling back to prior memory.','A')],
'按 55 分钟和 59 分钟提前轮换，是会话时长适配，不是模型只能记住 55 分钟。上下文容量、时间限制和日志保留时间必须分开。',
'Rotation at 55 and 59 minutes adapts to session duration. It does not mean the model remembers exactly 55 minutes. Context capacity, session age and log retention are separate limits.')

group('恢复和媒体健康','Recovery and media health',[
('REALTIME_HANDOFF_MEMORY_CHARS','4000','500–16000 字符；用于摘要字符串上限和逐字恢复选择预算。','500–16000 characters; caps summaries and budgets selected reconnect text.','A'),
('REALTIME_RECONNECT_MEMORY_MAX_AGE_SECONDS','900','0–86400 秒；0 关闭近期文字恢复窗口；不是完整历史库。','0–86400 seconds; 0 disables the recent-text window. Not a full history database.','A'),
('EBO_AUTO_WAKE','true','Compose 默认 true，裸 Config 默认 false；失败时最多每分钟唤醒一次。','Compose defaults true; bare Config defaults false. Wake requests are limited to about once per minute.','A'),
('EBO_MEDIA_STALE_AFTER_SECONDS','20','5–300 秒；视频或音频过期后媒体状态失败。','5–300 seconds; stale video or audio fails media health.','A'),
('EBO_MEDIA_STARTUP_GRACE_SECONDS','45','0–300 秒；启动期间媒体检查宽限。','0–300 seconds; grace period for media checks during startup.','A')],
'意外断线的逐字恢复需要此前同进程连接被识别为有对话的非计划断线。容器首次启动不会自动等同于这种恢复情形。',
'Transcript recovery follows an unexpected disconnection with dialogue in the same process. Initial container startup is not automatically treated as that recovery case.')

group('Prompt 模板与工具','Stored prompts and tools',[
('EBO_ASSISTANT_INSTRUCTIONS','built-in','基础角色全文，当前值见 Prompt 附录；空时使用代码中文默认。','Base persona text; current value is in the prompt appendix. Blank uses the built-in Chinese default.','A'),
('OPENAI_REALTIME_PROMPT_ID','','服务器保存的 Prompt ID；空表示不引用。','Server-stored prompt ID; blank means no stored prompt reference.','A'),
('OPENAI_REALTIME_PROMPT_VERSION','','可选固定版本；需同时提供 ID。','Optional pinned version; requires a prompt ID.','A'),
('OPENAI_REALTIME_PROMPT_VARIABLES_JSON','{}','JSON 对象，需 ID；用于模板变量替换。','JSON object for template variables; requires an ID.','A'),
('OPENAI_REALTIME_PARALLEL_TOOL_CALLS','','空或布尔值；不会自动创建本地工具执行器。','Blank or boolean; does not create a local tool executor.','A'),
('OPENAI_REALTIME_TOOLS_JSON','[]','JSON 对象数组；默认显式清空工具。声明不等于执行。','Array of tool objects; empty list explicitly clears tools. Declaration is not execution.','A'),
('OPENAI_REALTIME_TOOL_CHOICE','','空 none auto required 或 JSON 对象；当前无完整本地函数执行链。','Blank, none, auto, required or JSON object; no complete local function execution chain.','A'),
('OPENAI_REALTIME_TRACING','off','off auto 或 JSON 对象；控制模型侧 tracing，不代替本地文件日志。','off, auto or a JSON object; model-side tracing, separate from local file logs.','A')],
'直接发送的 Session 字段会覆盖存储 Prompt 的重叠字段。填模板并不会绕过本地附加视觉规则、工具数组或音频格式。',
'Direct Session fields override overlapping stored-prompt fields. A stored prompt does not bypass locally appended visual rules, tool arrays or audio formats.')

group('持久化路径与日志大小','Persistence paths and log sizes',[
('EBO_TRANSCRIPT_PATH','/data/transcripts.jsonl','用户最终转写；必须非空。','Completed user transcripts; required nonempty path.','A'),
('EBO_OUTPUT_AUDIO_DIR','/data/replies','回答 WAV 与 TXT 目录；必须非空。','Reply WAV and TXT directory; required nonempty path.','A'),
('EBO_ASSISTANT_TRANSCRIPT_PATH','/data/assistant_outputs.jsonl','助手回答总索引与流元数据。','Assistant output index and stream metadata.','A'),
('EBO_MEMORY_LOG_PATH','/data/logs/session-memory.jsonl','动态记忆注入与确认日志，必须非空。','Dynamic memory injection/confirmation log; must be nonempty.','A'),
('EBO_MEMORY_LOG_MAX_BYTES','1048576','262144–16777216 字节；单文件轮转大小，默认 1 MiB。','262144–16777216 bytes per rotating file; default 1 MiB.','A'),
('EBO_MEMORY_LOG_BACKUP_COUNT','3','1–20 份备份；另有当前文件。','1–20 backups, plus the current file.','A'),
('EBO_HOST_LOG_PATH','/data/logs/ebo-engine.log','Engine 输出日志；对应宿主 ebo-data。','Engine output log, mounted under host ebo-data.','A'),
('EBO_HOST_LOG_MAX_BYTES','10485760','Engine 单份日志默认 10 MiB。','Engine log size, default 10 MiB per file.','A'),
('EBO_HOST_LOG_BACKUP_COUNT','5','Engine 历史日志份数，不含当前文件。','Engine backup count, excluding the current file.','A')],
'路径按容器内名称填写，必须仍位于合适的挂载中才随重建保留。日志轮转不会清理 replies 的 WAV。',
'Use container paths and keep them within appropriate mounts for persistence across recreation. Log rotation does not delete reply WAVs.')

group('Engine 配置文件中的媒体参数','Media settings in Engine configuration',[
('video','true','打开视频接收。','Enable video reception.','B'),
('audio','true','打开监听；当前也是可用的双向音频基础。','Enable listening; also supplies the current two-way audio foundation.','B'),
('talk','false','单独 talk 开关；false 不等于禁止 custom PCM，audio=true 且发送器就绪仍可激活流。','Separate talk switch. false does not forbid custom PCM when audio=true and the sender is ready.','B'),
('video_max_height','720','最高输出高度，0 保留原始高度；影响编码 CPU。','Maximum output height; 0 keeps native height. Affects encoding CPU.','B'),
('video_fps','20','目标编码帧率，通过丢帧控制；不是模型检查帧率。','Target encoding fps, controlled by frame dropping; not model sampling fps.','B'),
('video_bitrate','2500','kbps 编码上限，0 不限；不等于固定每秒都用这么多。','Encoding cap in kbps; 0 uncapped. Not a guarantee of constant traffic.','B'),
('video_preset','ultrafast','FFmpeg x264 预设；更慢预设通常增加 CPU。','FFmpeg x264 preset; slower presets generally use more CPU.','B'),
('audio_codec','8','设备 Agora 音频 payload 模式；不要误当作采样率或随意更换。','Device Agora audio payload mode; not sample rate and not a casual tuning knob.','B'),
('standby_after_minutes','5','分钟，当前 0 不自动待机；prepare 脚本默认 5。','Minutes; current 0 disables automatic idle standby. Preparation defaults to 5.','B')],
'修改 ebo-data/options.json 后按 Engine 启动流程应用。run.sh 会把这些字段转为 EBO_VIDEO_FPS 等进程变量；仅在 .env 新增同名变量不保证生效。',
'Apply changes to ebo-data/options.json through the Engine startup workflow. run.sh turns these fields into variables such as EBO_VIDEO_FPS; adding names to .env alone is not sufficient.')

group('连接地址与凭据位置','Connections and credential locations',[
('OPENAI_API_KEY','required','OpenAI 凭据，只写名称不公开值；Assistant 必填。','OpenAI credential; value omitted. Required by Assistant.','A'),
('EBO_API_TOKEN','required','本地 API 与 PCM 流鉴权，两端必须匹配。','Local API and PCM-stream token; must match on both sides.','A'),
('EBO_EMAIL / EBO_PASSWORD','required','Enabot 账号；prepare 读取并写入私有 options.json。','Enabot account; preparation writes it into private options.json.','B'),
('EBO_PAYLOAD_KEY / EBO_SIGN_KEY','required','与 App 区域构建匹配的设备协议密钥。','Device protocol keys matching the app region/build.','B'),
('EBO_REGION / EBO_CLOUD_HOST','GB / EU host','prepare 使用的区域与云地址；当前区域 CN，不能混用区域凭据。','Region and cloud host used by preparation; current region CN. Do not mix regional credentials.','B'),
('EBO_TALK_STREAM_PORT','8200','Engine 内网端口；改动要同步 Assistant URL 和 Compose 暴露规则。','Engine internal port; coordinate Assistant URL and Compose exposure.','A'),
('TZ','America/Toronto','容器时间显示；时间戳对照需保留时区。','Container timezone; preserve timezone when comparing timestamps.','A'),
('robot_id / mcp / log_level','0 / false / info','options.json：设备选择、MCP 开关和 Engine 日志级别。','options.json: device selection, MCP switch and Engine log verbosity.','B')],
'不要把整份 .env、options.json 或健康历史中的家庭文字直接作为公开排障附件。变量位置可共享，实际凭据应留在私有配置中。',
'Do not publish complete .env, options.json or household text as troubleshooting attachments. Share variable locations while keeping actual credentials private.')

group('高级地址与部署映射','Advanced addresses and deployment wiring',[
('EBO_RTSP_URL','rtsp://ebo-engine:8554/ebo','Config 支持，但当前 Compose 未转发；改配置映射后才可用环境覆盖。','Supported by Config but not forwarded by current Compose; add deployment wiring before overriding.','C'),
('EBO_API_URL','http://ebo-engine:8098','同上，设备 HTTP API 根地址。','Same wiring limitation; device HTTP API root.','C'),
('EBO_NODE','ebo','同上；需与 Engine 节点一致。','Same wiring limitation; must match the Engine node.','C'),
('EBO_ASSISTANT_AUDIO_URL','http://realtime-assistant:8099/audio','WAV 回退给 Engine 下载的内部地址，不是公网分享地址。','Internal WAV fallback URL fetched by Engine, not a public sharing URL.','C'),
('EBO_ASSISTANT_PORT','8099','HTTP 监听端口；Compose 映射与健康命令也需同步。','HTTP listening port; also update Compose mapping and health command.','C'),
('LOG_LEVEL','INFO','Assistant 日志级别；当前 Compose 未转发。','Assistant log level; not forwarded by current Compose.','C'),
('EBO_VIDEO_SRC_FPS','25','Engine 对源帧节奏的假设；修改会影响时间戳与关键帧间隔。','Engine source-timing assumption; changes affect timestamps and keyframe spacing.','C'),
('EBO_AUDIO_RATE','8000','机器人音频采样率假设，必须与协议和帧长共同调整。','Robot audio-rate assumption; must agree with protocol and frame sizes.','C')],
'“代码支持环境变量”与“当前部署已经传进去”是两个条件。compose.yaml 没有 env_file 自动把全部 .env 注入容器。',
'Code accepting an environment variable and deployment forwarding it are separate conditions. compose.yaml does not use env_file to inject every .env entry automatically.')

group('有意固定的算法和协议常量','Deliberately fixed algorithm and protocol constants',[
('PCM input and output','24000 Hz mono PCM16','Assistant、API 声音、WAV 与回放换算共同依赖；改格式必须改整条链。','Shared by Assistant, API audio, WAVs and timing math; format changes require coordinated code edits.','C'),
('Input read block','100 ms / 4800 B','MediaCapture.audio_loop；更改影响采集与本地插话的时间粒度。','MediaCapture.audio_loop; changes affect capture and local interruption timing.','C'),
('PcmStream output frame','8000 Hz / 20 ms / 320 B','pcm_talk.py；末帧补零，队列最多 500 帧约 10 秒。','pcm_talk.py; final frame zero-padded, queue capped at 500 frames, about 10 seconds.','C'),
('Motion working image','320 px / blur 5x5','低分辨率灰度工作图与模糊核；不是上传图片大小。','Low-resolution grayscale working picture and blur kernel, not upload size.','C'),
('Motion warmup and background','6 frames / alpha 0.03','重设背景后重新预热，影响适应环境的速度。','Warmup restarts after background reset; controls adaptation speed.','C'),
('Handoff request','600 tokens / 1200 Chinese chars','请求上限与 Prompt 要求；之后仍受 4000 字符配置限制。','Request cap and prompt request, followed by the configurable character cap.','C'),
('Reconnect and heartbeat','1–20 s / 20 s ping / 10 s timeout','退避逐次倍增，上限 20 秒；稳定连接 30 秒可重置退避。','Backoff doubles to 20 seconds; 30 seconds of stable connection resets it.','C'),
('Image ID and pending slot','32 chars / 1 pending','img_ 加 28 字符；同一时间仅一张待确认。','img_ plus 28 characters; one pending image at a time.','C')],
'其他固定值包括 3 秒媒体重试、60 秒唤醒限频、JPEG 解析缓冲约 4 MB、Opus 48 kHz 单声道 24 kbps 10 ms、单槽最新视频帧策略。这些应通过代码修改和针对性验证调整。',
'Other constants include 3-second capture retries, 60-second wake throttling, roughly 4 MB JPEG parsing protection, Opus 48 kHz mono at 24 kbps with 10 ms frames, and the latest-frame slot. Change these through code with targeted validation.')
