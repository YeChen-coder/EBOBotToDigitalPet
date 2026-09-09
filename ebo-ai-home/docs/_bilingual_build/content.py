"""Paired source content: section identifiers and facts are shared by both editions."""
SECTIONS=[]
def add(n,zh,en,az,ae,nz,ne,pairs,ref,kind='flow'):
    SECTIONS.append(dict(n=n,title=[zh,en],analogy=[az,ae],nodes=[nz.split('|'),ne.split('|')],paras=pairs,ref=ref,kind=kind))

add(1,'先认识这位机器人助手','Meet the robot assistant',
'把机器人想成有眼睛、耳朵和嘴巴的小伙伴，把电脑想成翻译员，把模型想成远方接电话的朋友。',
'Think of the robot as eyes, ears and a mouth, the computer as a translator, and the model as a friend answering a call far away.',
'机器人\n看 听 说|设备云\n连接和传输|本地电脑\n翻译与筛选|OpenAI\n理解与回答',
'Robot\nSee hear speak|Device cloud\nConnect transport|Local computer\nAdapt and filter|OpenAI\nUnderstand reply',[
('这套系统让家人通过 EBO 的麦克风和扬声器与 AI 交谈，并让 AI 参考摄像头最近一次筛选出来的画面。它不是把完整的大模型装进机器人。机器人提供物理感知和播放，Windows 电脑上的服务连接设备与模型。电脑可以和机器人处于不同地点，只要双方所需的互联网连接可用。',
'This system lets a family talk to AI through EBO’s microphone and speaker. The AI can also use the latest camera image selected by the local software. A complete large model is not installed inside the robot. The robot senses and plays sound; services on a Windows computer connect it to the model. The computer and robot can be in different places, provided their required internet connections work.'),
('本书从一段声音和一张画面的旅程开始，再解释流式播放、多轮对话、记忆、Prompt 和参数。每一个技术词第一次出现时都给出日常类比，但类比只是帮助理解：真正的转换格式、代码位置和限制仍会写清。中英文版按同一组章节、图号、参数和示例排列。',
'The guide follows a sound and an image through the system, then explains streaming playback, multiple conversation turns, memory, prompts and configuration. Everyday analogies introduce unfamiliar terms, while the actual formats, code locations and limits remain explicit. Both editions follow the same sections, figure numbers, parameters and examples.'),
('当前工程的主链路是 ebo-engine 与 realtime-assistant。Home Assistant 提供面板、设备实体和手动操作；旧的 LLM Vision 单帧实验仍保留，但不是实时语音助手的必经通道。模型没有自动驾驶闭环；能描述画面，不等于能安全控制机器人移动。',
'The main path uses ebo-engine and realtime-assistant. Home Assistant supplies dashboards, device entities and manual controls. The older LLM Vision single-image experiment remains available, but the realtime voice assistant does not have to pass through it. There is no autonomous driving loop: describing a scene does not establish safe movement control.'),
('全文中的“本地”指运行 Docker 的电脑，“机器人端”指 EBO 机身。两者不要混为一谈。设备云与模型云也分开命名，避免误以为所有云服务都负责同一件事。',
'Throughout the guide, “local” means the computer running Docker; “robot side” means the EBO hardware. These are separate locations. The device cloud and model cloud are named separately because they perform different jobs.')], 'S1 S2')

add(2,'四个地点和三种信息','Four locations and three kinds of information',
'同一条公路上可以走快递车、客车和指挥车；路线相似，装的东西和处理方式却不同。',
'Delivery vans, buses and command vehicles can share a road while carrying different things and following different rules.',
'EBO 机器人|Enabot 与 Agora|本地 Engine 与 Assistant|OpenAI Realtime',
'EBO robot|Enabot and Agora|Local Engine and Assistant|OpenAI Realtime',[
('控制信息是“打开摄像头”“唤醒”“停止”等短消息。视频是连续的画面，音频是连续的声音样本。控制面负责建立和管理会话；媒体面搬运音视频。控制命令成功，并不能证明摄像头已经有新画面；必须再检查媒体时间戳。',
'Control information consists of short messages such as open camera, wake and stop. Video contains successive pictures; audio contains successive sound samples. The control plane establishes and manages sessions, while the media plane transports sound and pictures. A successful control command does not prove that fresh camera frames are arriving; media timestamps must also be checked.'),
('Enabot 云负责账号登录、设备发现以及取得连接机器人需要的会话信息。Agora 的 RTM 处理实时消息，RTC 处理实时音视频。Engine 像一个经过身份验证的软件端点，加入设备相关的频道并接收机器人媒体，而不是由 OpenAI 直接登录 EBO 账号。',
'Enabot cloud handles account login, device discovery and the session information needed to connect. Agora RTM carries realtime messages; RTC carries realtime audio and video. Engine acts as an authenticated software endpoint that joins the relevant channels and receives robot media. OpenAI does not log in to the EBO account.'),
('本地代码能证明的是 SDK 如何加入频道、接收回调和发送数据。云服务内部究竟经过哪台中继服务器、如何选择网络路径，不在本项目控制范围内。本书把 Agora 画成“连接与媒体传输网络”，不把未知的内部节点画成已经确认的服务器流程。云端转运媒体也不等于云端替你做场景理解或永久录像。',
'The local code establishes how the SDK joins channels, receives callbacks and sends data. The internal relay servers and route selection of the cloud service are outside this project’s control. Agora is therefore shown as a connection and media network, rather than as an invented sequence of confirmed internal servers. Transporting media is not the same as understanding scenes or permanently recording them.'),
('输入方向是机器人 → 设备网络 → 本地处理 → OpenAI。回答方向是 OpenAI → 本地处理 → Agora → 机器人扬声器。视频和语音共享会话背景，但并不是把一个带音轨的视频文件反复上传和下载。',
'Input travels robot → device network → local processing → OpenAI. Replies travel OpenAI → local processing → Agora → robot speaker. Images and speech share conversation context, but the system does not repeatedly upload and download a complete video file with a soundtrack.')], 'S2 S3 S4', 'lanes')

add(3,'电脑里的三个服务','Three services on the computer',
'Docker 像给三个小工人各分一间工作室；他们共用同一台电脑，但有各自的工具和工作。',
'Docker gives three workers separate workshops on the same computer, each with its own tools and responsibilities.',
'Home Assistant\n面板与自动化|ebo-engine\n设备协议适配|realtime-assistant\n音视频与模型桥接|宿主机目录\n保存配置和记录',
'Home Assistant\nUI and automation|ebo-engine\nDevice adapter|realtime-assistant\nMedia and model bridge|Host folders\nKeep settings and records',[
('容器是带着依赖一起运行的软件环境，镜像是制造这个环境的配方，Compose 是同时安排多个容器的清单。compose.yaml 固定项目名 ebo-ai-home，并让三个服务使用 ebo-ai-home-network。容器之间用服务名找到彼此，例如 ebo-engine，不必记住会变化的 IP。',
'A container runs software with its dependencies. An image is the recipe for that environment, and Compose describes how several containers run together. compose.yaml fixes the project name to ebo-ai-home and connects the services through ebo-ai-home-network. Containers locate one another by service names such as ebo-engine instead of depending on changing IP addresses.'),
('ebo-engine 含设备登录、Agora SDK、内部消息总线、HTTP API、FFmpeg 和 MediaMTX。realtime-assistant 含 OpenCV 运动检测、FFmpeg 采集、WebSocket 模型会话、扬声器流、日志与健康接口。把它们拆开，可以在不改变模型逻辑的情况下替换摄像头适配器，也可单独重建助手来应用 Prompt。',
'ebo-engine contains device login, the Agora SDK, an internal message bus, an HTTP API, FFmpeg and MediaMTX. realtime-assistant contains OpenCV motion detection, FFmpeg capture, the model WebSocket session, speaker streaming, logs and health endpoints. This separation allows a camera adapter to be replaced without rewriting the model logic, or the assistant alone to be recreated for prompt changes.'),
('Home Assistant 是家庭控制入口。设备集成把机器人状态转换成摄像头、按钮、传感器和扬声器实体。实体是统一名字和接口，例如一个 camera 实体；它不是另一个摄像头。Engine 内部的 MQTT 是组件之间的消息胶水，当前原生 HA 集成主要走 HTTP，而不是要求另外部署一个家庭 MQTT 服务器。',
'Home Assistant is the household control interface. Its integration turns robot state into camera, button, sensor and speaker entities. An entity is a standard name and interface, not another physical device. MQTT inside Engine connects its internal components. The current native HA integration mainly uses HTTP and does not require a separate household MQTT server.'),
('挂载目录把容器里的 /data 对应到电脑上的 assistant-data 或 ebo-data。重新创建容器通常保留这些目录里的记录，但进程内存会消失。depends_on 表示启动依赖，不保证 Engine 的媒体已经就绪；启动脚本和健康检查还必须等待实际连接和数据。',
'Mounted folders map /data inside a container to assistant-data or ebo-data on the computer. Recreating a container normally preserves those files, but loses process memory. depends_on establishes a startup dependency; it does not guarantee that Engine media is ready. Startup scripts and health checks must still wait for actual connections and data.')], 'S1 S2 S5','cards')

add(4,'机器人怎样连到电脑','How the robot connects to the computer',
'先找到朋友的电话号码，再进入同一个通话房间，最后才能听见和看见对方。',
'First find the contact details, then enter the same call, and only then can sound and pictures arrive.',
'账号与区域\nEnabot 登录|设备发现\n取得频道信息|Agora RTM\n控制与状态|Agora RTC\n音频和视频',
'Account and region\nEnabot login|Device discovery\nChannel information|Agora RTM\nControl and state|Agora RTC\nAudio and video',[
('Engine 用 EBO 账号、区域对应的云地址、应用协议密钥完成登录和请求签名。payload_key 和 sign_key 服务于设备厂商协议；OPENAI_API_KEY 服务于 OpenAI；EBO_API_TOKEN 保护本地适配器接口。三类凭据作用不同，不能互换，文档只写变量名，不写密钥值。',
'Engine uses the EBO account, the regional cloud address and application protocol keys to log in and sign requests. payload_key and sign_key belong to the vendor protocol; OPENAI_API_KEY authenticates OpenAI calls; EBO_API_TOKEN protects local adapter interfaces. These credentials have different purposes and are not interchangeable. This guide lists their names, never their secret values.'),
('登录后，桥接程序取得设备与频道信息，加入 Agora 消息和媒体会话。摄像头和监听通道打开后，SDK 持续回调新画面和麦克风声音。本地程序订阅或接收这些回调，再喂给后续处理链。它不是每说一句话就重新登录一次。',
'After login, the bridge obtains device and channel information and joins Agora messaging and media sessions. With camera and listening enabled, the SDK continuously delivers camera frames and microphone audio through callbacks. Local software passes those callbacks to the next processing stages. It does not log in again for every spoken sentence.'),
('“回调”可以理解成门铃：有新包裹时 SDK 通知你的程序。回调线程不能被慢速编码或网络发送长时间堵住，否则新数据会排队，越积越旧。代码用独立线程、队列和丢弃过期视频帧控制延迟。登录成功、RTC 已连接、最近确有媒体，分别是不同层次的状态。',
'A callback is like a doorbell: the SDK alerts your program when a new package arrives. Slow encoding or network operations must not block that callback thread for long, or newer data will queue behind increasingly old data. The code uses separate threads, queues and video-frame dropping to limit delay. Successful login, connected RTC and recently received media are three different states.'),
('官方手机 App 可能争用同一控制会话；设备待机、网络断开或凭据过期也会影响媒体。常驻助手支持失败后重试和自动唤醒，但这些机制不能替代稳定供电、网络和正确账号配置。当前 options.json 的待机时间为 0，表示不按闲置分钟数自动待机。',
'The official phone app may compete for the same control session. Standby, network loss and expired credentials can also interrupt media. The assistant supports retries and automatic wake requests, but these do not replace power, connectivity and valid account settings. The current options.json sets the idle standby interval to 0, disabling that automatic idle timeout.')], 'S3 S5 S6')

add(5,'视频怎样变成电脑能用的直播','Turning robot video into a local stream',
'机器人寄来一种特殊压缩的画册，电脑先打开画册，再换成更多播放器会读的版本。',
'The robot sends a specially packed picture book. The computer unpacks it and repacks it into a form more players can read.',
'机器人编码画面\n经 Agora 到达|SDK 解码\nI420 YUV 原始帧|FFmpeg 编码\nH264|MediaMTX\n发布 RTSP',
'Encoded robot video\nArrives via Agora|SDK decode\nRaw I420 YUV frames|FFmpeg encode\nH264|MediaMTX\nPublish RTSP',[
('编码把画面压缩成便于传输的数据，解码把压缩数据还原成像素。H.265 与 H.264 是视频编码格式，RTSP 是访问媒体流的协议；它们不是同一种东西。就像“饼干口味”与“快递方式”属于不同层次。MediaMTX 是本地媒体分发服务，不是 OpenAI。',
'Encoding compresses pictures for transport; decoding reconstructs their pixels. H.265 and H.264 are video coding formats. RTSP is a protocol for accessing a media stream. They describe different layers, like a biscuit recipe and a delivery method. MediaMTX is the local media distribution service, not OpenAI.'),
('ebo_video.py 记录了一个实际适配原因：SDK 的 H.265 编码帧接收路径曾发生底层崩溃，而解码后的视频观察器可以提供 YUV。当前程序因此接收 I420 原始画面，再由 FFmpeg 的 libx264 重新编码为 H.264。这里“云端到本地”之后确实有解码和再编码，代价是 CPU 使用和额外延迟。',
'ebo_video.py records a concrete compatibility problem: the SDK’s encoded H.265 frame path crashed, while its decoded video observer could supply YUV. The implementation therefore receives raw I420 pictures and uses FFmpeg libx264 to encode them again as H.264. This is real decoding and re-encoding after media reaches the computer, with CPU and latency costs.'),
('I420 把亮度 Y 和两组颜色信息 U、V 分开存放。内存每一行可能有额外填充，stride 指一行实际占用的字节数。_pack_plane 去掉这些填充，避免 FFmpeg 把边缘垃圾字节误当图像。1280×720 的 I420 单帧约 1.38 MB，若每秒 25 帧则原始数据约 34.56 MB/s，所以不能把压缩流与原始帧的带宽混为一谈。',
'I420 stores brightness Y and two color components U and V in separate planes. Memory rows may contain padding; stride is the actual byte distance between rows. _pack_plane removes padding so FFmpeg does not interpret stray bytes as pixels. A 1280×720 I420 picture is about 1.38 MB; at 25 frames per second, raw data is about 34.56 MB/s. Raw-frame bandwidth is therefore very different from compressed-stream bandwidth.'),
('当前 Engine 配置是最高 720 高度、目标 20 fps、2500 kbps 码率上限、ultrafast 编码预设。目标帧率不保证每秒真的产出这么多帧。CPU 忙时保留最新待编码帧并覆盖旧帧，优先减少看旧画面的时间。',
'Current Engine settings use a maximum height of 720, a 20 fps target, a 2500 kbps bitrate cap and the ultrafast encoder preset. A target is not a guarantee of measured output. If the CPU falls behind, the latest pending picture replaces the older one, prioritizing a fresher view over preserving every frame.')], 'S4 S6')

add(6,'为什么观看直播和给模型看图是两回事','Watching live video and showing images to AI',
'人可以看整本翻页动画，模型在这条链路里收到的是挑选过的几张照片。',
'A person can watch the whole flipbook. In this implementation, the model receives selected photographs.',
'本地 RTSP\nH264 与 Opus|人看直播\nHA 或浏览器|Assistant 抽帧\n默认每秒 2 张|运动门通过\nJPEG 给模型',
'Local RTSP\nH264 and Opus|Human live view\nHA or browser|Assistant sampling\nDefault 2 per second|Motion gate accepts\nJPEG to model',[
('Home Assistant 摄像头实体和浏览器预览可以消费 Engine 提供的媒体。浏览器 WebRTC/WHEP 预览、HLS 回退和 RTSP 访问是不同的播放路径；哪条可达还取决于端口映射和网络。Assistant 则直接读取 Docker 网络内的 RTSP，不需要先打开 HA 面板，也不读取屏幕上的画面。',
'The Home Assistant camera entity and browser preview can consume media from Engine. WebRTC/WHEP preview, HLS fallback and RTSP access are separate playback paths; reachability depends on ports and networking. Assistant reads RTSP directly inside Docker. It does not require an open HA dashboard and does not capture the picture from your screen.'),
('Assistant 的一个 FFmpeg 进程只取视频，按 MOTION_FPS=2 输出 JPEG 序列。另一个进程只取音频。JPEG 序列从 pipe:1 进入程序内存；程序寻找 JPEG 起止标记，拼出完整图片再交给 OpenCV。管道像连接两个工人的小传送带，不要求先在磁盘保存录像文件。',
'One Assistant FFmpeg process extracts video as a JPEG sequence at MOTION_FPS=2. A separate process extracts audio. JPEG bytes flow into program memory through pipe:1; the program finds the JPEG start and end markers and reconstructs each picture for OpenCV. A pipe is a conveyor belt between programs, so a recording does not have to be saved to disk first.'),
('每秒检查两张，不等于每秒上传两张。运动检测、连续确认和冷却期进一步减少上传。通过后才缩小到不超过 768 像素宽，按 JPEG 质量 75 压缩，再作为 input_image 写入 Realtime 会话。当前模型支持图片输入；本项目没有把 RTSP 视频地址当作原生视频输入交给模型。[O1]',
'Checking two pictures per second does not mean uploading two per second. Motion detection, repeated confirmation and a cooldown reduce uploads further. An accepted picture is reduced to at most 768 pixels wide, JPEG-encoded at quality 75 and inserted as input_image in the Realtime session. The selected model supports image input; this project does not give the model an RTSP URL as native video input. [O1]'),
('这能节省图片处理成本，但模型会错过未采样或未触发的变化。安静不动的场景可能没有新的图片，旧图也不一定代表现在。当前语音提问并不会额外触发一张即时快照；“你看见我了吗”仍依赖最近已成功送入的画面。',
'This reduces image processing cost, but the model can miss changes between samples or changes rejected by the gate. A still scene may produce no new image, and an older image may no longer describe the present. A spoken question does not itself request a fresh snapshot in the current code; “Can you see me?” still depends on the most recent successfully inserted picture.')], 'S2 S4 S7','branch')

add(7,'运动检测只是在找哪里变了','Motion detection asks what changed',
'把两张房间照片叠在一起找不同，而不是已经认出“这是妈妈”或“这是一只猫”。',
'Compare two room pictures to find differences; this does not already identify a person or a cat.',
'缩到 320 宽\n灰度与模糊|与背景相减\n亮度差超过 25|清理小噪点\n找最大变化区域|确认与冷却\n决定是否送图',
'Resize to width 320\nGrayscale and blur|Subtract background\nDifference above 25|Clean small speckles\nFind largest region|Confirm and cool down\nDecide whether to send',[
('MotionGate 先把图片缩到 320 像素宽、转成灰度，再用 5×5 高斯模糊压掉细小抖动。它保留一个缓慢更新的背景，用当前图减去背景，亮度差大于阈值的像素变成白点。黑白遮罩只标出变化，不表示变化对象的名字或意义。',
'MotionGate resizes a picture to 320 pixels wide, converts it to grayscale and applies a 5×5 Gaussian blur to reduce small fluctuations. It keeps a slowly updated background and subtracts it from the current picture. Pixels whose brightness difference exceeds the threshold become white. This black-and-white mask marks change, not the object’s identity or meaning.'),
('形态学开运算去掉孤立小点，随后膨胀把相邻变化连接起来；程序找轮廓并计算最大轮廓面积占比。MOTION_MIN_AREA_RATIO=0.003 表示最大变化区域要达到约 0.3%。它不是人物识别置信度，也不是说只有 0.3% 的像素变化才发送。',
'Morphological opening removes isolated speckles, then dilation connects nearby changes. The program finds contours and measures the largest contour as a fraction of picture area. MOTION_MIN_AREA_RATIO=0.003 requires a largest changed region of roughly 0.3%. It is not a person-detection confidence score, nor does it mean that exactly 0.3% of all pixels must change.'),
('若整体变化比例达到 0.55，程序认为可能转头、移动或突然开灯，重设背景并重新预热。初始化预热 6 帧，背景更新权重 0.03。通常还需连续 2 帧满足运动条件，并与上次发送间隔至少 12 秒。2 fps 下预热约 3 秒只是理想采集节奏的估算，场景重置会重新开始。',
'If the overall changed fraction reaches 0.55, the program treats this as a possible camera move or abrupt lighting change, resets the background and warms up again. Warmup uses 6 frames and background updates have weight 0.03. Normally, motion must persist for 2 qualifying frames and at least 12 seconds must have passed since the last upload. About 3 seconds of warmup at 2 fps is an ideal-rate estimate; a scene reset starts it again.'),
('降低面积阈值可能看见更小的动作，也更容易被电视、窗帘和树影触发。延长冷却期减少上传，却增加漏掉短事件的可能。门控的价值是便宜地筛选画面；需要“只看人或宠物”时才需要增加真正的类别检测器。',
'Lowering the area threshold can detect smaller movements but also increases triggers from televisions, curtains or shadows. A longer cooldown reduces uploads but can miss short events. The gate is a low-cost picture selector. Restricting events to people or pets would require an actual object classifier.')], 'S7')

add(8,'一张图片如何进入模型的记忆','How an image enters conversation context',
'白板上先贴稳新照片，再取下旧照片；不要旧的拿掉了，新的却没贴上。',
'Pin the new photo securely before removing the old one from the noticeboard.',
'JPEG 转 Base64|发送 item.create\n新图暂时待确认|收到 item.added\n新图已接受|删除旧图片条目\n保留最近一张',
'JPEG to Base64|Send item.create\nNew image pending|Receive item.added\nNew image accepted|Delete old image item\nKeep the latest image',[
('Base64 是把二进制图片写成可放进 JSON 的文本编码，类似把特殊符号换成约定好的字母。它不是加密，也不是再次压缩，通常会增加约三分之一的数据大小。真正的网络加密由发往 OpenAI 的 WSS 连接提供。JPEG 数据放在 data:image/jpeg;base64,... 字段中。',
'Base64 expresses binary image bytes as text that can be placed inside JSON. It is a representation, not encryption or additional compression, and usually adds about one third to the size. The WSS connection to OpenAI supplies network encryption. The JPEG is placed in a data:image/jpeg;base64,... field.'),
('Assistant 创建一条 role=user、content=input_image 的会话消息，ID 使用 img_ 加 28 个十六进制字符，总长 32。虽然协议角色写 user，这张图不是家人主动说的一句话；附加视觉 Prompt 会明确把它当成内部观察，避免模型每次都说“我收到图片了”。',
'Assistant creates a conversation message with role=user and content=input_image. Its ID is img_ plus 28 hexadecimal characters, totaling 32. Although the protocol role is user, the image is not a new sentence spoken by a family member. Additional visual instructions describe it as internal observation, discouraging repeated “image received” responses.'),
('代码区分 pending 和 accepted。服务端确认新 item.added 后，才发送 conversation.item.delete 删除上一张。前一张仍在等待确认时，新的发送机会会被跳过；相关错误会释放待确认状态。这样兼顾接口限制、上下文成本与顺序，但没有承诺每次选中的图片都最终送达。',
'The code separates pending and accepted images. Only after the server confirms item.added does it send conversation.item.delete for the preceding image. A new upload opportunity is skipped while an earlier image is awaiting confirmation, and relevant errors release that pending state. This manages protocol limits, context cost and ordering, without guaranteeing delivery of every selected picture.'),
('context 模式只更新图片背景；announce 模式在图片被接受后主动请求回答。删除旧图只改变当前会话的可用视觉条目，不代表删除本地日志、云服务全部数据或已经写出的回答。只有最近一张图也意味着不能可靠地比较几分钟前后所有动作。',
'In context mode, the image only updates background context. In announce mode, acceptance also triggers a response. Deleting an old image changes the current conversation’s available visual items; it does not erase local logs, all provider data or answers already produced. Keeping only the latest image also prevents reliable comparison of every action across several minutes.')], 'S2 S8')

add(9,'声音怎样变成一串数字','Turning sound into numbers',
'每隔很短时间量一下声音有多大，把测量结果排成一列，就得到声音的数字版本。',
'Measure the sound level at very short intervals and place the measurements in order to obtain digital audio.',
'声波\n空气振动|采样\n每秒测量次数|PCM16\n每个数 2 字节|按顺序播放\n还原声音',
'Sound wave\nAir vibration|Sampling\nMeasurements per second|PCM16\n2 bytes per sample|Ordered playback\nReproduce sound',[
('采样率是每秒记录多少个声音数值，单位 Hz。8000 Hz 就是每秒 8000 个样本；24000 Hz 就是每秒 24000 个。单声道只有一条声音序列；立体声有两条。PCM16 用有符号 16 位整数表示每个样本，也就是 2 字节；s16le 说明这些整数按小端顺序存储。',
'Sample rate is the number of sound measurements recorded each second, in hertz. 8000 Hz means 8000 samples per second; 24000 Hz means 24000. Mono has one sequence, while stereo has two. PCM16 stores each sample as a signed 16-bit integer, or 2 bytes. s16le means that those integers use little-endian byte order.'),
('PCM 是容易加工但体积较大的原始声音表示。Opus 是适合传输的压缩编码；WAV 是带格式头的文件容器，可以装 PCM。JSON 和 Base64 又是消息封装方式。把这几层混在一起，就会误把“把 PCM 写进 WAV”说成“提高音质”或把“Base64 编码”说成“语音压缩”。',
'PCM is a relatively large, easy-to-process representation of sound. Opus is a compressed codec suited to transport. WAV is a file container with a format header that can hold PCM. JSON and Base64 package messages. Confusing these layers leads to mistakes such as calling a PCM-to-WAV wrapper an audio-quality improvement, or describing Base64 as audio compression.'),
('换采样率叫重采样。机器人侧观察到的 8 kHz 麦克风音频经过 RTSP 的 Opus 路径，最终被 Assistant 转为 24 kHz，以匹配当前 Realtime PCM 接口。把 8 kHz 升到 24 kHz 并不会凭空找回原来没有录到的高频细节；只是把时间格子换成接口要求的密度。',
'Changing sample rate is called resampling. Robot microphone audio observed at 8 kHz passes through the RTSP Opus path and is converted by Assistant to 24 kHz for the current Realtime PCM interface. Upsampling from 8 kHz to 24 kHz cannot recover high-frequency details that were never recorded. It changes the sample grid to match the required interface.'),
('计算很直观：24,000 样本/秒 × 2 字节 × 1 声道 = 48,000 字节/秒。100 ms 是十分之一秒，所以一块输入 PCM 是 4,800 字节。这里只计算 PCM 本体，不包括 JSON、Base64、网络包头、重传或模型 token 费用。',
'The arithmetic is straightforward: 24,000 samples/second × 2 bytes × 1 channel = 48,000 bytes/second. A 100 ms input block is one tenth of a second, or 4,800 bytes. This counts PCM only, excluding JSON, Base64, packet headers, retransmission and model token charges.')], 'S2 S4 S9','samples')

add(10,'麦克风声音怎样送到 OpenAI','Sending microphone audio to OpenAI',
'像用小水杯连续传水，不等整桶装满才出发。',
'Pass water continuously in small cups instead of waiting for a whole bucket to fill.',
'EBO 麦克风\nAgora 接收 PCM|Engine FFmpeg\nOpus 48 kHz|本地 RTSP\nAssistant 解码到 24 kHz|100 ms 一块\ninput_audio_buffer.append',
'EBO microphone\nAgora PCM received|Engine FFmpeg\nOpus at 48 kHz|Local RTSP\nAssistant decodes to 24 kHz|100 ms blocks\ninput_audio_buffer.append',[
('Engine 的监听回调收到机器人麦克风 PCM，并把声音交给视频管道的音频输入。FFmpeg 用 libopus、48 kHz 单声道、24 kbps、10 ms Opus 帧发布音轨。选择 Opus 是为了兼容浏览器 WebRTC 音轨；源麦克风窄带这一事实并未因 48 kHz 编码而改变。早期注释中的 AAC 不是当前编码命令。',
'Engine’s listening callback receives robot microphone PCM and feeds the video pipeline’s audio input. FFmpeg publishes an audio track using libopus, 48 kHz mono, 24 kbps and 10 ms Opus frames. Opus was chosen for browser WebRTC audio compatibility. Encoding at 48 kHz does not change the narrowband nature of the original microphone. Older comments mentioning AAC do not describe the current command.'),
('Assistant 的音频 FFmpeg 以 RTSP over TCP 连接，忽略视频，把音轨解码并重采样为 24 kHz 单声道 s16le。audio_loop 每次读取约 100 ms。机器人没说话时，append_audio 将这些字节转成 Base64，放入 input_audio_buffer.append，经一条长期保持的 OpenAI WebSocket 连续发送。',
'Assistant’s audio FFmpeg connects using RTSP over TCP, ignores video, decodes the audio track and resamples it to 24 kHz mono s16le. audio_loop reads roughly 100 ms at a time. While the robot is not speaking, append_audio Base64-encodes these bytes into input_audio_buffer.append events and sends them through a persistent OpenAI WebSocket.'),
('当前代码没有在普通监听阶段先用本地 VAD 只挑出人声再上传。普通监听 PCM 会持续发给云端，由云端降噪、VAD 与转写辅助判断。因此运动门节省的是图片上传，不能据此声称所有背景音都不会离开电脑。机器人播放时才走专门的静音或本地插话分支。',
'During ordinary listening, the current code does not first use local VAD to upload speech alone. Listening PCM is sent continuously, with cloud noise reduction, VAD and transcription helping determine turns. The motion gate reduces image uploads; it does not establish that background sound never leaves the computer. Speaker playback activates the separate mute or local interruption branch.'),
('当 RTSP 结束或失败时，采集循环清理 FFmpeg，等待约 3 秒后重试；允许自动唤醒时最多每分钟请求一次唤醒和打开摄像头。某些静音帧用于维持媒体时间轴，因此“有音频字节”也不等于“已经听清真人讲话”。',
'If RTSP ends or fails, the capture loop cleans up FFmpeg and retries after about 3 seconds. With automatic wake enabled, it requests wake and camera activation at most once per minute. Silence frames may maintain the media timeline, so receiving audio bytes does not prove that a real person was heard clearly.')], 'S2 S3 S4')

add(11,'系统怎样知道你说完一句话','How the system detects the end of a turn',
'等别人停下来再接话，但停多久才算说完，需要一个规则。',
'Wait for the other person to pause before answering, but decide how long a pause counts as finishing.',
'保留句首\n300 ms|检测说话\n当前阈值 0.5|检测停顿\n650 ms|提交语音回合\n等待最终转写',
'Keep the beginning\n300 ms padding|Detect speech\nCurrent threshold 0.5|Detect a pause\n650 ms|Commit audio turn\nWait for final transcript',[
('VAD 是语音活动检测，判断某一段声音是否像人在说话。server_vad 使用声音活动阈值和静音时长来划分回合。当前 threshold=0.5，prefix_padding_ms=300，silence_duration_ms=650。前缀补偿帮助保留触发前的句首；静音时长越短越快接话，也越容易在你思考时抢话。',
'VAD means voice activity detection: deciding whether sound resembles speech. server_vad uses an activity threshold and silence duration to mark turns. Current settings are threshold=0.5, prefix_padding_ms=300 and silence_duration_ms=650. Prefix padding helps retain the beginning before detection. Shorter silence makes replies start sooner but can cut into a thoughtful pause.'),
('阈值不是“音量百分比”。调高通常使检测更保守，调低通常更容易触发；它也不是声纹识别，不能判断是谁在说话、是不是在对机器人说话。semantic_vad 则使用语义完成度来判断停顿，切换后发送 eagerness，数值型 server VAD 参数不再随会话发送。',
'The threshold is not a percentage of microphone volume. Raising it generally makes detection more conservative, while lowering it increases sensitivity. VAD is not speaker identification and does not know who is speaking or whether the robot is being addressed. semantic_vad instead uses semantic completeness to assess pauses. In that mode, the code sends eagerness and omits the numeric server VAD settings.'),
('检测到 speech_stopped，不等于机器人立刻回答。当前 create_response=false，程序要等输入转写完成并通过过滤，才显式发送 response.create。这样能过滤一些误触发，但增加了等待转写的延迟。如果改为 true，就让服务端自动创建回答，代码会跳过自己的转写后请求逻辑。',
'speech_stopped does not immediately make the robot answer. With create_response=false, the program waits for completed input transcription and a local filter before explicitly sending response.create. This can reject some false triggers but adds transcription waiting time. Setting it to true enables server-created responses, and the code skips its own post-transcription response request.'),
('idle_timeout_ms=0 在本项目表示不发送空闲超时字段。它与机器人几分钟后进入待机不是一个参数。当前未启用本地插话，服务端 interrupt_response=true；若启用本地回声感知插话，代码会把实际发出的 interrupt_response 强制设为 false，让本地门控先决定是否打断。',
'idle_timeout_ms=0 means this project omits the idle timeout field. It is different from the robot’s standby timer. Local interruption is currently disabled, so server interrupt_response is true. Enabling local echo-aware interruption forces the transmitted interrupt_response to false so that the local gate decides whether to interrupt first.')], 'S2 S10')

add(12,'转写和回答模型分别做什么','Transcription and answering have different jobs',
'一个人听懂并回答，另一个人把听到的话记在本子上；本子还能帮助判断要不要接话。',
'One listener understands and answers; another writes down what was heard. The notes also help decide whether to answer.',
'语音回合|Realtime 理解音频|gpt-transcribe\n完成文字记录|本地文字过滤\n通过才请求回答',
'Audio turn|Realtime understands audio|gpt-transcribe\nCompleted written record|Local transcript filter\nRequest reply if accepted',[
('当前回答模型是 gpt-realtime-2.1-mini，输入转写模型是 gpt-transcribe。Realtime 可以直接处理音频；本项目不是把转写文字再发到另一个普通聊天接口、最后再调用独立 TTS 的三段流水线。输入转写是并行的辅助结果，但这里又被用作回答触发的门槛。',
'The current answering model is gpt-realtime-2.1-mini and the transcription model is gpt-transcribe. Realtime handles audio directly. This project does not send the transcript to a separate ordinary chat endpoint and then call a separate TTS service. Input transcription is an auxiliary result, but this implementation also uses it to decide when to request an answer.'),
('最终转写会先保存到 transcripts.jsonl，再进入 _is_actionable_transcript。空白被拒绝；含中文或数字通常通过；被标为中文的结果也通过。若只含不超过 3 个拉丁词且总长不超过 24 字符，当前规则会拒绝。这是面向中文家庭场景的粗略过滤，不是通用的语义判断。',
'Completed transcription is first saved to transcripts.jsonl and then passed to _is_actionable_transcript. Blank text is rejected; Chinese characters or digits generally pass; results labeled Chinese also pass. A result containing at most 3 Latin words and at most 24 characters is rejected by the current rule. This is a coarse filter for a Chinese-speaking household, not a universal semantic test.'),
('例如“你好”可以通过，而 “Hello” 或 “How are you” 可能被当成低信息碎片。制作英文版说明书不会把机器人改成英语助手。若将来实际要支持英语对话，除了 Prompt 和转写语言，还要修改或重新评估这条本地过滤规则；仅把说明书翻译成英文不会改变任何运行行为。',
'For example, “你好” passes, while “Hello” or “How are you” may be treated as low-information fragments. Producing an English guide does not change the robot into an English-speaking assistant. Actual English support would require reviewing this local filter as well as the prompt and transcription language. Translating the guide changes no runtime behavior.'),
('程序按输入 item_id 去重，防止同一完成事件反复触发回答。它并没有可靠识别电视、家人互相说话和真正对机器人的提问。Prompt 可以表达偏好，但不能创造代码里不存在的说话对象识别能力。转写有错时，日志记录和后续恢复记忆也可能带着同样的错误。',
'Input item_id values are deduplicated so that a repeated completion event does not repeatedly request a reply. The program does not reliably distinguish television, family-to-family speech and questions directed at the robot. A prompt can express the intended behavior, but cannot create an addressee detector absent from the code. Transcription errors can also enter logs and later recovery context.')], 'S2 S11','branch')

add(13,'多轮对话不是每句话重新开始','Multiple turns share conversation context',
'聊天像在同一本小本子上接着写；“它是什么颜色”要看前面说过“杯子”。',
'Conversation continues in the same notebook: “What color is it?” depends on an earlier mention of a cup.',
'会话配置\n角色与声音|用户第一轮\n这个杯子叫什么|助手第一轮\n回答杯子问题|用户第二轮\n它是什么颜色',
'Session settings\nRole and voice|User turn one\nAsk about the cup|Assistant turn one\nAnswer about the cup|User turn two\nWhat color is it',[
('Session 是一次 Realtime 连接对应的会话环境，含模型、声音、音频格式、Prompt 等配置；conversation 是该环境里的对话条目序列；item 是一条消息或内容单元；response 是一次生成过程。一个 response 可以分成许多音频 delta。把这些都叫“一轮”会让日志难以理解。',
'A Session is the Realtime environment associated with a connection, including model, voice, audio format and prompt settings. A conversation is its sequence of items. An item is a message or content unit; a response is a generation operation. One response can produce many audio deltas. Calling all of these a “turn” makes logs difficult to interpret.'),
('同一连接里，先前保留的用户语音、助手回答与最新图片为后续问题提供背景。程序不在每次讲话后重建 Session，也不需要每轮手动拼出整个历史列表。这就是本项目的 multi-turn：后一句可以依赖前一句，但只依赖当前上下文里仍然存在的信息。',
'Within one connection, retained user audio, assistant replies and the latest image provide context for later questions. The program does not rebuild the Session after every utterance or manually resend the whole history list each turn. This is the project’s multi-turn behavior: later speech can depend on earlier speech, as long as the relevant information remains in context.'),
('上下文不是永久记忆。图片被替换、旧条目被截断、网络断线或容器重建，都可能改变模型能参考什么。用户说“那个”而对应图片已过时，或者关键名词已被裁掉，模型仍可能答错。设计上需要明确承认不确定，而不是声称机器人一直完整记得。',
'Context is not permanent memory. Image replacement, truncation, network loss and container recreation can change what the model can reference. A pronoun may refer to an outdated picture or a noun already removed from context. The model can therefore still answer incorrectly. The design should acknowledge uncertainty rather than claim complete continuous memory.'),
('response_id 标识回答，item_id 标识对话条目，stream_id 标识本地扬声器播放流。一个回答可以对应不同层的这些 ID。排查“模型生成了但没听到”时，必须把生成、播放和持久化索引关联起来，而不能只看一条文本回答存在。',
'response_id identifies a reply, item_id identifies a conversation item and stream_id identifies the local speaker stream. The same reply can carry identifiers at each layer. Diagnosing “the model answered but nobody heard it” requires linking generation, playback and persisted indexes, not merely finding a text answer.')], 'S2 S8 S11')

add(14,'Prompt 如何决定角色和说话方式','How prompts shape character and speech',
'Prompt 像给演员的角色卡：它指导怎么说话，却不会给演员凭空增加摄像头或驾驶证。',
'A prompt is an actor’s role card: it guides speech but does not provide new senses or control capabilities.',
'基础角色 Prompt|视觉上下文规则|上轮交接摘要|断线前逐字记录\n合并到 instructions',
'Base role prompt|Visual context rules|Previous handoff summary|Recent reconnect transcript\nCombined in instructions',[
('当前 EBO_ASSISTANT_INSTRUCTIONS 设定会说话的金毛狗陪伴角色、普通话、温暖放松的声音、日常一两句话，并允许家人明确要求时讲完整故事。它也约束人物称呼、旧画面真实性、收费问题和历史记忆的解释。完整原文与逐条英文释义放在附录，两版保留同一个运行 Prompt。',
'The current EBO_ASSISTANT_INSTRUCTIONS defines a talking golden-retriever companion, Mandarin speech, a warm relaxed delivery and short everyday replies, while allowing a complete story when explicitly requested. It also covers names, image freshness, payment questions and history handling. The appendix contains the exact original and a matched English explanation. Both editions preserve the same runtime prompt.'),
('在 context 模式，代码还追加 VISUAL_CONTEXT_INSTRUCTIONS：图片是感知背景，不要仅因收到图片回答，优先回应有效语音，通常说一两句。定时换会话时可再追加事实性摘要；意外重连时可追加近期文字记录，并说明这些是背景而非指令。',
'In context mode, the code adds VISUAL_CONTEXT_INSTRUCTIONS: images are perceptual background, receiving an image alone should not trigger speech, valid speech has priority, and replies are usually one or two sentences. Planned rotation can add a factual summary; unexpected reconnection can add recent transcripts, explicitly labeled background rather than instructions.'),
('这些文字会被拼入同一个 instructions 字段，不是四个独立权限等级。基础 Prompt 允许长故事，而附加规则又强调一两句，存在需要协调的表达张力。改变人设或措辞不能保证模型永远服从；输出 token 上限、语音速度、回合门控和实际工具能力仍由参数及代码约束。',
'These texts are concatenated into the same instructions field, not four separate authority levels. The base prompt permits long stories while the appended rule emphasizes one or two sentences, creating wording that may need coordination. Changing the character or phrasing does not guarantee obedience. Token limits, output speed, turn gating and tool capability remain controlled by parameters and code.'),
('提示词要区分“风格”与“事实”。“像金毛狗一样热情”是角色风格，“我刚走到厨房”是可验证动作；没有执行记录就不该把后者当事实。修改 Prompt 后需要重新创建 Assistant 容器，进程不会自动监视 .env 文件变化。',
'A prompt should distinguish style from facts. “Be enthusiastic like a golden retriever” is style; “I just went to the kitchen” is an action claim. Without execution evidence, the latter should not be treated as fact. Applying a prompt change requires recreating the Assistant container; the process does not watch .env for edits.')], 'S2 S12','stack')

add(15,'模型回复如何一小段一小段回来','How model audio arrives in small pieces',
'厨师做好第一小盘就端出来，你可以先吃，不必等整桌菜全部做完。',
'Serve the first small plate as soon as it is ready instead of waiting for the entire meal.',
'response.create\n请求回答|output_audio.delta\n声音增量不断到达|本地累计与预缓冲\n达到 200 ms|启动扬声器流\n边生成边送出',
'response.create\nRequest a reply|output_audio.delta\nAudio pieces arrive|Accumulate and prebuffer\nReach 200 ms|Start speaker stream\nGenerate and send together',[
('模型产生 response.output_audio.delta 事件，每个事件里有 Base64 编码的 24 kHz 单声道 PCM16。Assistant 解码后同时做两件事：累计完整生成音频，交给 Speaker.stream_delta 逐块传送。delta 是协议增量，不保证刚好是一句话、一个词或固定 100 ms。',
'The model emits response.output_audio.delta events containing Base64-encoded 24 kHz mono PCM16. Assistant decodes each event, accumulates the generated audio and passes the same bytes to Speaker.stream_delta for delivery. A delta is a protocol increment, not necessarily a sentence, word or fixed 100 ms block.'),
('默认先积累 200 ms 音频再启动本地播放工作线程。缓冲像一个小蓄水池，吸收网络到达速度的不均匀。缓冲更大可能更稳，却会晚开口；更小可能更快，但断续风险更高。200 ms 只是一段本地预缓冲，不能解释成“总响应延迟只有 200 ms”。',
'By default, 200 ms of audio is accumulated before the local playback worker starts. This small reservoir absorbs uneven arrival timing. A larger buffer may be steadier but delays the first sound; a smaller one may start sooner but is more vulnerable to gaps. The 200 ms setting is only local prebuffering, not a promise of 200 ms total response latency.'),
('output_audio.done 表示模型这一段音频生成结束，随后程序发送本地 end 标记，并完成 WAV 保存。机器人此时可能仍在播放队列中的声音。response.done、音频生成结束、文字转写完成和机器人播放完毕，不能当作同一个时刻。',
'output_audio.done means generation of that audio output has ended. The program then sends a local end marker and completes WAV persistence. The robot may still be playing queued sound. response.done, completed audio generation, completed transcript and completed speaker playback are not the same instant.'),
('文本增量 response.output_audio_transcript.delta 是伴随声音的文字记录，不是让本地另一个 TTS 去读的脚本。当前主路径直接把模型生成的声音送回机器人。只有旧的手动 Home Assistant TTS 路径才属于另一类播放入口。',
'response.output_audio_transcript.delta provides the accompanying written transcript; it is not a script for another local TTS engine. The main path sends model-generated audio directly back to the robot. The older manual Home Assistant TTS path is a separate playback entry.')], 'S2 S9')
