from __future__ import annotations

import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


PROJECT = Path(__file__).resolve().parents[1]
DESKTOP = Path.home() / "Desktop"
OUTPUT = DESKTOP / "EBO 家庭助手完整工作原理（图解版）.docx"
BUILD = PROJECT / "docs" / "_build_ebo_guide"
ASSETS = BUILD / "assets"
BUILD.mkdir(parents=True, exist_ok=True)
ASSETS.mkdir(parents=True, exist_ok=True)


# compact_reference_guide preset, with one named CJK override:
# Microsoft YaHei is used for all Chinese glyphs; Latin text uses the same family for consistency.
NAVY = "17324D"
BLUE = "2E74B5"
SKY = "DCEEFF"
TEAL = "1B7F79"
MINT = "DDF4EA"
ORANGE = "E68A2E"
PEACH = "FCE8D3"
PURPLE = "7656A8"
LAVENDER = "EDE5FA"
RED = "B84040"
ROSE = "F8DEDE"
GOLD = "B17A00"
YELLOW = "FFF3C4"
INK = "243444"
MUTED = "637587"
LIGHT = "F4F7FA"
GRID = "D7E0E8"
WHITE = "FFFFFF"
FONT_NAME = "Microsoft YaHei"


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (PROJECT / ".env").read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$", line)
        if match:
            values[match.group(1)] = match.group(2).strip()
    return values


ENV = read_env()
EFFECTIVE = {
    "model": ENV.get("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1"),
    "voice": ENV.get("OPENAI_REALTIME_VOICE", "marin"),
    "transcription": ENV.get("OPENAI_INPUT_TRANSCRIPTION_MODEL", "gpt-transcribe"),
    "noise": ENV.get("REALTIME_INPUT_NOISE_REDUCTION", "off"),
    "vad_type": ENV.get("REALTIME_TURN_DETECTION_TYPE", "server_vad"),
    "vad_threshold": ENV.get("REALTIME_VAD_THRESHOLD", "0.55"),
    "prefix": ENV.get("REALTIME_VAD_PREFIX_PADDING_MS", "300"),
    "silence": ENV.get("REALTIME_VAD_SILENCE_DURATION_MS", "650"),
    "idle": ENV.get("REALTIME_VAD_IDLE_TIMEOUT_MS", "0"),
    "create_response": ENV.get("REALTIME_VAD_CREATE_RESPONSE", "false"),
    "interrupt": ENV.get("REALTIME_VAD_INTERRUPT_RESPONSE", "true"),
    "visual_mode": ENV.get("EBO_VISUAL_MODE", "context"),
    "auto_wake": ENV.get("EBO_AUTO_WAKE", "false"),
    "motion_fps": ENV.get("MOTION_FPS", "2"),
    "motion_threshold": ENV.get("MOTION_THRESHOLD", "25"),
    "motion_min": ENV.get("MOTION_MIN_AREA_RATIO", "0.003"),
    "motion_max": ENV.get("MOTION_MAX_CHANGE_RATIO", "0.55"),
    "motion_confirm": ENV.get("MOTION_CONFIRM_FRAMES", "2"),
    "motion_cooldown": ENV.get("MOTION_COOLDOWN_SECONDS", "12"),
    "image_width": ENV.get("REALTIME_IMAGE_WIDTH", "768"),
    "image_quality": ENV.get("REALTIME_IMAGE_QUALITY", "75"),
    "refresh": ENV.get("REALTIME_SESSION_REFRESH_SECONDS", "3300"),
    "hard_deadline": ENV.get("REALTIME_SESSION_HARD_DEADLINE_SECONDS", "3540"),
    "handoff_timeout": ENV.get("REALTIME_HANDOFF_TIMEOUT_SECONDS", "20"),
    "memory_chars": ENV.get("REALTIME_HANDOFF_MEMORY_CHARS", "4000"),
    "reconnect_age": ENV.get("REALTIME_RECONNECT_MEMORY_MAX_AGE_SECONDS", "900"),
    "media_stale": ENV.get("EBO_MEDIA_STALE_AFTER_SECONDS", "20"),
    "startup_grace": ENV.get("EBO_MEDIA_STARTUP_GRACE_SECONDS", "45"),
}
PROMPT = ENV.get("EBO_ASSISTANT_INSTRUCTIONS", "（当前 .env 中没有填写 Prompt）")


FONT_REGULAR_PATHS = [
    Path(r"C:\Windows\Fonts\msyh.ttc"),
    Path(r"C:\Windows\Fonts\msyh.ttf"),
    Path(r"C:\Windows\Fonts\simhei.ttf"),
]
FONT_BOLD_PATHS = [
    Path(r"C:\Windows\Fonts\msyhbd.ttc"),
    Path(r"C:\Windows\Fonts\msyhbd.ttf"),
    *FONT_REGULAR_PATHS,
]
FONT_REGULAR = next(path for path in FONT_REGULAR_PATHS if path.exists())
FONT_BOLD = next(path for path in FONT_BOLD_PATHS if path.exists())


def pil_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REGULAR), size=size)


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for raw in text.split("\n"):
        if not raw:
            lines.append("")
            continue
        current = ""
        for char in raw:
            trial = current + char
            if current and draw.textbbox((0, 0), trial, font=font)[2] > max_width:
                lines.append(current)
                current = char
            else:
                current = trial
        if current:
            lines.append(current)
    return lines


def text_center(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str,
                size: int = 28, color: str = INK, bold: bool = True, padding: int = 22) -> None:
    font = pil_font(size, bold)
    lines = wrap_text(draw, text, font, box[2] - box[0] - padding * 2)
    line_height = int(size * 1.38)
    total = line_height * len(lines)
    y = box[1] + (box[3] - box[1] - total) / 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        width = bbox[2] - bbox[0]
        draw.text((box[0] + (box[2] - box[0] - width) / 2, y), line,
                  fill=hex_rgb(color), font=font)
        y += line_height


def rounded_box(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str,
                fill: str, outline: str = BLUE, size: int = 27, radius: int = 24) -> None:
    shadow = (box[0] + 7, box[1] + 8, box[2] + 7, box[3] + 8)
    draw.rounded_rectangle(shadow, radius=radius, fill=(219, 226, 233))
    draw.rounded_rectangle(box, radius=radius, fill=hex_rgb(fill), outline=hex_rgb(outline), width=4)
    text_center(draw, box, label, size=size)


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int],
          label: str = "", color: str = MUTED, width: int = 6, label_offset: int = -34) -> None:
    draw.line([start, end], fill=hex_rgb(color), width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    length = 18
    wing = 0.6
    p1 = (end[0] - length * math.cos(angle - wing), end[1] - length * math.sin(angle - wing))
    p2 = (end[0] - length * math.cos(angle + wing), end[1] - length * math.sin(angle + wing))
    draw.polygon([end, p1, p2], fill=hex_rgb(color))
    if label:
        font = pil_font(21, True)
        bbox = draw.textbbox((0, 0), label, font=font)
        x = (start[0] + end[0]) / 2 - (bbox[2] - bbox[0]) / 2
        y = (start[1] + end[1]) / 2 + label_offset
        pad = 8
        draw.rounded_rectangle((x - pad, y - 3, x + bbox[2] - bbox[0] + pad, y + 30),
                               radius=8, fill=hex_rgb(WHITE))
        draw.text((x, y), label, fill=hex_rgb(color), font=font)


def canvas(title: str, subtitle: str = "") -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (1400, 760), hex_rgb(WHITE))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((20, 20, 1380, 740), radius=30, fill=hex_rgb(LIGHT), outline=hex_rgb(GRID), width=3)
    draw.text((60, 48), title, fill=hex_rgb(NAVY), font=pil_font(38, True))
    if subtitle:
        draw.text((62, 102), subtitle, fill=hex_rgb(MUTED), font=pil_font(22, False))
    return image, draw


def save_diagram(name: str, image: Image.Image) -> Path:
    path = ASSETS / f"{name}.png"
    image.save(path, format="PNG", optimize=True)
    return path


def diagram_big_picture() -> Path:
    image, draw = canvas("一眼看懂：这是一个会看、会听、会说的机器人助手", "箭头就是消息走过的路")
    rounded_box(draw, (65, 250, 285, 490), "EBO 机器人\n摄像头 + 麦克风\n轮子 + 扬声器", PEACH, ORANGE, 27)
    rounded_box(draw, (350, 215, 650, 525), "Docker 小区\n\nEBO Engine\nHome Assistant\nRealtime Assistant", SKY, BLUE, 22)
    rounded_box(draw, (750, 250, 990, 490), "OpenAI\nRealtime 模型\n思考 + 生成声音", LAVENDER, PURPLE, 22)
    rounded_box(draw, (1060, 250, 1335, 490), "你和家人\n\n看控制面板\n听 EBO 回答\n用手机遥控", MINT, TEAL, 22)
    arrow(draw, (285, 330), (350, 330), "画面 + 声音")
    arrow(draw, (650, 330), (750, 330), "图片 + 语音")
    arrow(draw, (990, 430), (650, 430), "回答声音", label_offset=12)
    arrow(draw, (1060, 330), (990, 330), "说话")
    draw.text((430, 650), "最重要：Home Assistant 不直接喂模型；Realtime Assistant 才负责模型会话。",
              fill=hex_rgb(RED), font=pil_font(25, True))
    return save_diagram("01_big_picture", image)


def diagram_docker_neighborhood() -> Path:
    image, draw = canvas("Docker 小区：三个房子，共用一条内部小路", "内部小路叫 ebo-ai-home-network；房子用服务名互相找")
    draw.rounded_rectangle((55, 155, 1345, 650), radius=28, fill=hex_rgb("EAF1F7"), outline=hex_rgb(BLUE), width=5)
    draw.text((85, 176), "Docker bridge network：ebo-ai-home-network", fill=hex_rgb(BLUE), font=pil_font(24, True))
    rounded_box(draw, (100, 275, 420, 535), "homeassistant\n\n网页和实体\n端口 8123", MINT, TEAL, 27)
    rounded_box(draw, (540, 245, 860, 565), "ebo-engine\n\nEBO 翻译官\nHTTP 8098\nRTSP 8554", PEACH, ORANGE, 27)
    rounded_box(draw, (980, 275, 1300, 535), "realtime-assistant\n\n选帧 + 音频桥\n健康页 8099", LAVENDER, PURPLE, 25)
    arrow(draw, (540, 360), (420, 360), "HTTP 状态 / 命令")
    arrow(draw, (420, 455), (540, 455), "RTSP 画面")
    arrow(draw, (860, 350), (980, 350), "RTSP 视频 + 音频")
    arrow(draw, (980, 470), (860, 470), "HTTP 唤醒 / 播放")
    return save_diagram("02_docker_neighborhood", image)


def diagram_engine() -> Path:
    image, draw = canvas("EBO Engine：把机器人专用语言翻译成大家会用的语言", "它是唯一真正懂 Enabot 云协议的容器")
    rounded_box(draw, (60, 250, 280, 500), "Enabot 云端\n账号登录\n设备发现\n临时令牌", SKY, BLUE, 26)
    rounded_box(draw, (375, 185, 740, 565), "ebo-engine\n\nRTM：控制消息\nRTC：视频和音频\nFFmpeg：重新编码\nMediaMTX：发布 RTSP\nPanel/API：给 HA 和助手用", PEACH, ORANGE, 25)
    rounded_box(draw, (850, 180, 1115, 350), "标准出口 A\nHTTP JSON API\n状态 + 命令", MINT, TEAL, 25)
    rounded_box(draw, (850, 400, 1115, 570), "标准出口 B\nRTSP\nH.264 + Opus", LAVENDER, PURPLE, 25)
    rounded_box(draw, (1190, 260, 1340, 490), "EBO\n机器人", YELLOW, GOLD, 28)
    arrow(draw, (280, 375), (375, 375), "HTTPS")
    arrow(draw, (740, 275), (850, 275), "状态/命令")
    arrow(draw, (740, 485), (850, 485), "媒体流")
    arrow(draw, (1190, 330), (1115, 330), "Agora RTC/RTM")
    return save_diagram("03_engine", image)


def diagram_home_assistant() -> Path:
    image, draw = canvas("Home Assistant：像家里的总控制面板", "它会展示、轮询和发命令，但不持有 Realtime 会话")
    rounded_box(draw, (70, 245, 330, 520), "浏览器 / 手机\n\n看摄像头\n按按钮\n看传感器", SKY, BLUE, 27)
    rounded_box(draw, (480, 180, 850, 585), "Home Assistant 容器\n\n每 10 秒 GET /api/robots\n抓取 /api/snapshot\nPOST /api/cmd\n显示摄像头、传感器和按钮\n显示扬声器", MINT, TEAL, 21)
    rounded_box(draw, (1030, 245, 1300, 520), "ebo-engine\n\nHTTP API\nRTSP 摄像头", PEACH, ORANGE, 27)
    arrow(draw, (330, 370), (480, 370), "网页 / WebSocket")
    arrow(draw, (850, 295), (1030, 295), "GET 状态 / 快照")
    arrow(draw, (1030, 455), (850, 455), "JSON / JPEG")
    draw.text((405, 650), "旧 LLM Vision 只是可选实验，不在常驻 Realtime 主链路里。",
              fill=hex_rgb(RED), font=pil_font(25, True))
    return save_diagram("04_home_assistant", image)


def diagram_video() -> Path:
    image, draw = canvas("视频路线：很多画面进来，只有少数有用画面出去", "模型不接收视频文件；程序把视频变成一张张候选 JPEG")
    boxes = [
        ((40, 280, 240, 470), "EBO 摄像头\n原始画面", PEACH, ORANGE),
        ((285, 280, 485, 470), "ebo-engine\nH.264 + Opus\nRTSP", SKY, BLUE),
        ((530, 280, 730, 470), "FFmpeg\n每秒取 2 帧\n变成 JPEG", MINT, TEAL),
        ((775, 280, 975, 470), "OpenCV\n本地运动门", YELLOW, GOLD),
        ((1020, 280, 1220, 470), "缩到 768px\n质量 75", LAVENDER, PURPLE),
        ((1245, 280, 1370, 470), "送给\n模型", ROSE, RED),
    ]
    for box, label, fill, outline in boxes:
        rounded_box(draw, box, label, fill, outline, 20)
    for left, right in zip(boxes, boxes[1:]):
        arrow(draw, (left[0][2], 375), (right[0][0], 375))
    draw.text((430, 585), "空镜、轻微噪点、转头造成的整幅变化都会被挡在本机。",
              fill=hex_rgb(TEAL), font=pil_font(27, True))
    return save_diagram("05_video", image)


def diagram_motion_gate() -> Path:
    image, draw = canvas("运动门：像一个很谨慎的门卫", "先便宜地判断，再决定要不要花模型的钱")
    rounded_box(draw, (70, 210, 290, 350), "刚启动？\n先看 6 帧学习背景", SKY, BLUE, 23)
    rounded_box(draw, (70, 440, 290, 580), "画面大变 ≥ 55%？\n当作转头/光变\n重学背景", ROSE, RED, 22)
    rounded_box(draw, (420, 210, 670, 350), "最大变化块\n< 0.3%？\n太小，不发", MINT, TEAL, 23)
    rounded_box(draw, (420, 440, 670, 580), "连续 2 帧都有？\n不是一闪而过", YELLOW, GOLD, 23)
    rounded_box(draw, (800, 210, 1050, 350), "距离上次发送\n≥ 12 秒？", LAVENDER, PURPLE, 23)
    rounded_box(draw, (800, 440, 1050, 580), "通过！\n得到一张有效图片", PEACH, ORANGE, 23)
    rounded_box(draw, (1160, 310, 1340, 485), "Realtime\n只保留\n最新一张", SKY, BLUE, 19)
    arrow(draw, (290, 280), (420, 280), "不是大变")
    arrow(draw, (545, 350), (545, 440), "变化够大")
    arrow(draw, (670, 510), (800, 510), "确认")
    arrow(draw, (925, 350), (925, 440), "冷却结束")
    arrow(draw, (1050, 510), (1160, 400), "上传")
    return save_diagram("06_motion_gate", image)


def diagram_audio_input() -> Path:
    image, draw = canvas("听的路线：声音被切成很多个 100 毫秒小积木", "先持续送音频，再由服务端 VAD 找到一句话的边界")
    rounded_box(draw, (45, 265, 245, 475), "EBO 麦克风\n8 kHz 来源", PEACH, ORANGE, 25)
    rounded_box(draw, (290, 265, 510, 475), "RTSP Opus\n音频轨", SKY, BLUE, 25)
    rounded_box(draw, (555, 245, 805, 495), "FFmpeg\n24 kHz\n单声道 PCM16\n每块 100ms", MINT, TEAL, 24)
    rounded_box(draw, (850, 220, 1090, 520), "Realtime 输入\nfar_field 降噪\nserver_vad\nthreshold 0.65", LAVENDER, PURPLE, 24)
    rounded_box(draw, (1140, 265, 1350, 475), "gpt-transcribe\n一句话文字", YELLOW, GOLD, 19)
    for a, b in [((245, 370), (290, 370)), ((510, 370), (555, 370)), ((805, 370), (850, 370)), ((1090, 370), (1140, 370))]:
        arrow(draw, a, b)
    draw.text((325, 600), "EBO 正在播放自己的回答时，麦克风上行暂时静音，避免它听见自己。",
              fill=hex_rgb(RED), font=pil_font(25, True))
    return save_diagram("07_audio_input", image)


def diagram_noise_filter() -> Path:
    image, draw = canvas("为什么 create_response=false 反而更聪明？", "VAD 负责切句；程序等转写出来，再判断这句话值不值得回答")
    rounded_box(draw, (80, 290, 310, 470), "VAD 说：\n这里像一句话结束了", SKY, BLUE, 24)
    rounded_box(draw, (405, 235, 710, 525), "先看最终转写\n\n空白？不答\n很短的拉丁碎片？不答\n中文 / 数字 / 完整句？通过", YELLOW, GOLD, 23)
    rounded_box(draw, (820, 180, 1080, 350), "像“uh”“mm”\n或空声音", ROSE, RED, 24)
    rounded_box(draw, (820, 440, 1080, 610), "有效问题\n或有效中文", MINT, TEAL, 24)
    rounded_box(draw, (1180, 440, 1350, 610), "发送\nresponse.\ncreate", LAVENDER, PURPLE, 18)
    arrow(draw, (310, 380), (405, 380), "转写完成")
    arrow(draw, (710, 310), (820, 265), "丢掉")
    arrow(draw, (710, 450), (820, 525), "保留")
    arrow(draw, (1080, 525), (1180, 525), "请模型回答")
    return save_diagram("08_noise_filter", image)


def diagram_prompt_layers() -> Path:
    image, draw = canvas("模型收到的 Prompt 不是一张纸，而是四层小书包", "每次建立 Realtime Session 时，把需要的层叠在一起")
    rounded_box(draw, (80, 180, 520, 295), "第 1 层：角色 Prompt\n（来自 .env）", PEACH, ORANGE, 21)
    rounded_box(draw, (80, 325, 520, 440), "第 2 层：视觉规则（图片不算用户说话）", SKY, BLUE, 25)
    rounded_box(draw, (80, 470, 520, 585), "第 3 层：55 分钟轮换交接记忆（有时才有）", MINT, TEAL, 24)
    rounded_box(draw, (80, 615, 520, 710), "第 4 层：断网前 15 分钟已完成对话（有时才有）", LAVENDER, PURPLE, 22)
    rounded_box(draw, (760, 255, 1260, 585), "最终 instructions\n\n角色 + 边界 + 近期记忆\n\n送进 session.update\n模型用它决定“我是谁、怎么说、什么不能做”", YELLOW, GOLD, 27)
    for y in (238, 382, 527, 662):
        arrow(draw, (520, y), (760, 420), "加入")
    return save_diagram("09_prompt_layers", image)


def diagram_realtime_packet() -> Path:
    image, draw = canvas("送进 Realtime 的三种东西", "它们都走同一条加密 WebSocket，但事件类型不同")
    rounded_box(draw, (60, 165, 520, 285), "文字规则\nsession.update · instructions", PEACH, ORANGE, 19)
    rounded_box(draw, (60, 325, 520, 445), "声音小块\ninput_audio_buffer.append\nBase64 PCM", SKY, BLUE, 17)
    rounded_box(draw, (60, 485, 520, 605), "运动选图\nconversation.item.create\nJPEG", MINT, TEAL, 18)
    rounded_box(draw, (850, 205, 1310, 575), f"{EFFECTIVE['model']}\n\n输出：audio\n声音：{EFFECTIVE['voice']}\n窗口保留：80%\nPrompt 后预算：8000 tokens", LAVENDER, PURPLE, 21)
    arrow(draw, (520, 225), (850, 300), "WSS / JSON")
    arrow(draw, (520, 385), (850, 385), "WSS / JSON")
    arrow(draw, (520, 545), (850, 470), "WSS / JSON")
    return save_diagram("10_realtime_packet", image)


def diagram_output() -> Path:
    image, draw = canvas("说的路线：模型声音先存档，再让 EBO 播放", "当前是可靠的半双工：先收完整段，再播放")
    rounded_box(draw, (45, 250, 255, 485), "Realtime\n音频 delta\n24 kHz PCM", LAVENDER, PURPLE, 25)
    rounded_box(draw, (310, 250, 520, 485), "Assistant\n收齐一段回答", SKY, BLUE, 25)
    rounded_box(draw, (575, 220, 820, 515), "持久化\nreply-xxx.wav\nreply-xxx.txt\nJSONL 索引", MINT, TEAL, 25)
    rounded_box(draw, (875, 250, 1085, 485), "POST /api/cmd\ntalk =\nWAV 地址", PEACH, ORANGE, 20)
    rounded_box(draw, (1140, 250, 1350, 485), "ebo-engine\n转 PCM\nAgora 发给扬声器", YELLOW, GOLD, 23)
    for a, b in [((255, 367), (310, 367)), ((520, 367), (575, 367)), ((820, 367), (875, 367)), ((1085, 367), (1140, 367))]:
        arrow(draw, a, b)
    draw.text((420, 620), "播放时：麦克风上行暂停到“声音时长 + 1.5 秒”。",
              fill=hex_rgb(RED), font=pil_font(26, True))
    return save_diagram("11_output", image)


def diagram_conversation() -> Path:
    image, draw = canvas("一次完整对话，就像一列小火车", "从家人说话，到 EBO 发出回答")
    labels = [
        ("1", "家人说话", PEACH, ORANGE),
        ("2", "PCM 小块上行", SKY, BLUE),
        ("3", "VAD 切句", MINT, TEAL),
        ("4", "转写完成", YELLOW, GOLD),
        ("5", "有效性检查", LAVENDER, PURPLE),
        ("6", "模型回答", ROSE, RED),
        ("7", "WAV + TXT 落盘", MINT, TEAL),
        ("8", "EBO 扬声器播放", PEACH, ORANGE),
    ]
    x = 45
    centers = []
    for number, label, fill, outline in labels:
        box = (x, 285, x + 145, 465)
        rounded_box(draw, box, f"{number}\n{label}", fill, outline, 20, 20)
        centers.append((x + 145, 375))
        x += 170
    for i in range(len(centers) - 1):
        arrow(draw, centers[i], (centers[i + 1][0] - 145, 375), width=4)
    draw.text((245, 570), "如果最近有一张有效图片，它早已静静放在会话里，模型回答时可以一起参考。",
              fill=hex_rgb(BLUE), font=pil_font(25, True))
    return save_diagram("12_conversation", image)


def diagram_session() -> Path:
    image, draw = canvas("60 分钟限制：换车厢，不是让整个助手下班", "程序常驻，只轮换 OpenAI WebSocket Session")
    draw.line((100, 385, 1300, 385), fill=hex_rgb(BLUE), width=10)
    marks = [(100, "0 分钟\n建立 Session"), (620, "55 分钟\n准备交接"), (1020, "说话中？\n等这一轮结束"), (1300, "59 分钟\n最晚强制换")]
    for x, label in marks:
        draw.ellipse((x - 24, 361, x + 24, 409), fill=hex_rgb(WHITE), outline=hex_rgb(BLUE), width=6)
        text_center(draw, (x - 125, 430, x + 125, 550), label, 22, INK, True)
    rounded_box(draw, (300, 160, 560, 300), "空 Session\n直接重连\n不花钱做摘要", MINT, TEAL, 23)
    rounded_box(draw, (720, 160, 1030, 300), "有真实对话\n生成 ≤600 tokens\n内部交接记忆", YELLOW, GOLD, 23)
    rounded_box(draw, (1010, 585, 1325, 700), "新 Session：\n原 Prompt + 交接记忆", LAVENDER, PURPLE, 22)
    arrow(draw, (1160, 550), (1160, 585), "换连接")
    return save_diagram("13_session", image)


def diagram_reconnect() -> Path:
    image, draw = canvas("断网恢复：两条链路各自重新站起来", "Docker 容器不必重建；程序自己循环重试")
    rounded_box(draw, (70, 180, 400, 330), "Realtime WebSocket 断开", ROSE, RED, 25)
    rounded_box(draw, (70, 445, 400, 595), "EBO 云 / RTSP 断开", ROSE, RED, 25)
    rounded_box(draw, (520, 160, 850, 350), "1 / 2 / 4 / 8 / 16 / 20 秒\n指数退避重连\n清掉半截输出音频", SKY, BLUE, 24)
    rounded_box(draw, (520, 425, 850, 615), "桥接进程每 15 秒重试\n普通 DNS 错误保留 A/V\n必要时每分钟唤醒 EBO", PEACH, ORANGE, 23)
    rounded_box(draw, (1010, 250, 1330, 530), "恢复后\n\n最近 15 分钟完成对话\n最近有效视觉帧\n重新放进新 Session", MINT, TEAL, 24)
    arrow(draw, (400, 255), (520, 255), "自动")
    arrow(draw, (400, 520), (520, 520), "自动")
    arrow(draw, (850, 255), (1010, 350), "联网后")
    arrow(draw, (850, 520), (1010, 430), "媒体回来")
    return save_diagram("14_reconnect", image)


def diagram_storage() -> Path:
    image, draw = canvas("哪些记忆住在硬盘里？", "容器像可以换掉的盒子；宿主机文件夹才是不会随盒子消失的抽屉")
    rounded_box(draw, (60, 190, 370, 610), "容器（可重建）\n\nhomeassistant\nebo-engine\nrealtime-assistant\n\n程序和临时内存", SKY, BLUE, 26)
    rounded_box(draw, (530, 150, 900, 650), "Windows 宿主机抽屉\n\nhomeassistant-config/\nebo-data/\nassistant-data/\n  transcripts.jsonl\n  assistant_outputs.jsonl\n  replies/*.wav\n  replies/*.txt", MINT, TEAL, 24)
    rounded_box(draw, (1060, 230, 1330, 570), "重建后仍在\n\n录音回答\n回答文字\n家人语音转写\nHA 配置\nEBO 设置", YELLOW, GOLD, 25)
    arrow(draw, (370, 400), (530, 400), "Docker volume / bind mount")
    arrow(draw, (900, 400), (1060, 400), "保留下来")
    return save_diagram("15_storage", image)


def diagram_scripts() -> Path:
    image, draw = canvas("桌面上的两个按钮，各做一件不同的事", "一个负责电脑开机后的整套启动；一个只让新 Prompt 生效")
    rounded_box(draw, (90, 190, 590, 600), "启动 EBO 家庭助手.cmd\n\n启动/等待 Docker Desktop\n检查 .env\n启动 3 个容器\n检查 HA + Realtime + 视频 + 音频\n成功后打开 Home Assistant", MINT, TEAL, 25)
    rounded_box(draw, (810, 190, 1310, 600), "应用 EBO Prompt 修改.cmd\n\n只 force-recreate realtime-assistant\n明确 --no-deps\n不动 HA\n不动 ebo-engine\n等新 Session 和媒体恢复", LAVENDER, PURPLE, 25)
    draw.text((400, 660), "两者都不会删除持久化 WAV、转写或 Home Assistant 配置。",
              fill=hex_rgb(RED), font=pil_font(26, True))
    return save_diagram("16_scripts", image)


def diagram_boundaries() -> Path:
    image, draw = canvas("安全边界：这个“大脑”现在故意不会做什么", "能力少一点，但更可控")
    rounded_box(draw, (90, 180, 610, 335), "不会因为看到移动就主动说话\n当前 visual_mode = context", MINT, TEAL, 24)
    rounded_box(draw, (90, 420, 610, 575), "不会把所有视频帧都上传\n本地运动门先过滤", SKY, BLUE, 24)
    rounded_box(draw, (790, 180, 1310, 335), "不会让模型直接开车 / 转向\n电机控制没有开放给 Realtime", ROSE, RED, 24)
    rounded_box(draw, (790, 420, 1310, 575), "不会在断网时继续云端思考\n只能等网络恢复后重连", YELLOW, GOLD, 24)
    draw.text((370, 650), "LLM Vision 也不在主链路中；它只是保留的旧实验入口。",
              fill=hex_rgb(PURPLE), font=pil_font(26, True))
    return save_diagram("17_boundaries", image)


DIAGRAMS = {
    "big": diagram_big_picture(),
    "docker": diagram_docker_neighborhood(),
    "engine": diagram_engine(),
    "ha": diagram_home_assistant(),
    "video": diagram_video(),
    "motion": diagram_motion_gate(),
    "audio": diagram_audio_input(),
    "noise": diagram_noise_filter(),
    "prompt": diagram_prompt_layers(),
    "packet": diagram_realtime_packet(),
    "output": diagram_output(),
    "conversation": diagram_conversation(),
    "session": diagram_session(),
    "reconnect": diagram_reconnect(),
    "storage": diagram_storage(),
    "scripts": diagram_scripts(),
    "boundaries": diagram_boundaries(),
}


def set_run(run, size: float | None = None, color: str = INK, bold: bool | None = None,
            italic: bool | None = None) -> None:
    run.font.name = FONT_NAME
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), FONT_NAME)
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), FONT_NAME)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), FONT_NAME)
    if size is not None:
        run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(color)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def shade_cell(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_margins(cell, top=100, start=140, bottom=100, end=140) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for tag, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{tag}"))
        if node is None:
            node = OxmlElement(f"w:{tag}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_table_geometry(table, widths_dxa: list[int], indent_dxa: int = 120) -> None:
    total = sum(widths_dxa)
    table.autofit = False
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.first_child_found_in("w:tblW")
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(total))
    tbl_w.set(qn("w:type"), "dxa")
    tbl_ind = tbl_pr.first_child_found_in("w:tblInd")
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), str(indent_dxa))
    tbl_ind.set(qn("w:type"), "dxa")
    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths_dxa:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        grid.append(col)
    for row in table.rows:
        for index, cell in enumerate(row.cells):
            tc_w = cell._tc.get_or_add_tcPr().first_child_found_in("w:tcW")
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                cell._tc.get_or_add_tcPr().append(tc_w)
            tc_w.set(qn("w:w"), str(widths_dxa[index]))
            tc_w.set(qn("w:type"), "dxa")
            set_cell_margins(cell)


def set_repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    tr_pr.append(header)


def add_page_number(paragraph) -> None:
    run = paragraph.add_run()
    fld_char1 = OxmlElement("w:fldChar")
    fld_char1.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld_char2 = OxmlElement("w:fldChar")
    fld_char2.set(qn("w:fldCharType"), "end")
    run._r.extend([fld_char1, instr, fld_char2])
    set_run(run, 9, MUTED)


def setup_document() -> Document:
    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)

    normal = doc.styles["Normal"]
    normal.font.name = FONT_NAME
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_NAME)
    normal.font.size = Pt(11)
    normal.font.color.rgb = RGBColor.from_string(INK)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.25

    for name, size, color, before, after in (
        ("Heading 1", 16, BLUE, 18, 10),
        ("Heading 2", 13, BLUE, 14, 7),
        ("Heading 3", 12, NAVY, 10, 5),
    ):
        style = doc.styles[name]
        style.font.name = FONT_NAME
        style._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_NAME)
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True

    for name in ("List Bullet", "List Number"):
        style = doc.styles[name]
        style.font.name = FONT_NAME
        style._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_NAME)
        style.font.size = Pt(11)
        style.paragraph_format.left_indent = Inches(0.375)
        style.paragraph_format.first_line_indent = Inches(-0.188)
        style.paragraph_format.space_after = Pt(4)
        style.paragraph_format.line_spacing = 1.25

    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    header.paragraph_format.space_after = Pt(0)
    run = header.add_run("EBO 家庭助手 · 图解工作原理")
    set_run(run, 9, MUTED)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer.paragraph_format.space_before = Pt(0)
    run = footer.add_run("第 ")
    set_run(run, 9, MUTED)
    add_page_number(footer)
    run = footer.add_run(" 页")
    set_run(run, 9, MUTED)
    return doc


def add_paragraph(doc: Document, text: str, bold_prefix: str | None = None,
                  color: str = INK, size: float = 11, align=None, after: float = 6) -> None:
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    p.paragraph_format.space_after = Pt(after)
    if bold_prefix and text.startswith(bold_prefix):
        run = p.add_run(bold_prefix)
        set_run(run, size, color, True)
        run = p.add_run(text[len(bold_prefix):])
        set_run(run, size, color)
    else:
        run = p.add_run(text)
        set_run(run, size, color)


def add_bullets(doc: Document, items: list[str]) -> None:
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        run = p.add_run(item)
        set_run(run, 11, INK)


def add_callout(doc: Document, label: str, text: str, fill: str = YELLOW, accent: str = GOLD) -> None:
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    set_table_geometry(table, [9360])
    cell = table.cell(0, 0)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    shade_cell(cell, fill)
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(label + "  ")
    set_run(run, 11, accent, True)
    run = p.add_run(text)
    set_run(run, 11, INK)
    doc.add_paragraph().paragraph_format.space_after = Pt(1)


def add_figure(doc: Document, path: Path, caption: str) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(4)
    p.add_run().add_picture(str(path), width=Inches(5.95))
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_before = Pt(0)
    cap.paragraph_format.space_after = Pt(8)
    run = cap.add_run(caption)
    set_run(run, 9, MUTED, False, True)


def new_chapter(doc: Document, title: str, subtitle: str, diagram: Path | None = None,
                caption: str = "") -> None:
    p = doc.add_paragraph(style="Heading 1")
    p.paragraph_format.left_indent = Inches(0)
    p.paragraph_format.first_line_indent = Inches(0)
    p.paragraph_format.page_break_before = True
    p.paragraph_format.keep_with_next = True
    run = p.add_run(title)
    set_run(run, 16, BLUE, True)
    sub = doc.add_paragraph()
    sub.paragraph_format.space_after = Pt(8)
    sub.paragraph_format.keep_with_next = diagram is not None
    run = sub.add_run(subtitle)
    set_run(run, 11.5, MUTED)
    if diagram:
        add_figure(doc, diagram, caption)


def add_key_value_table(doc: Document, rows: list[tuple[str, str, str]]) -> None:
    table = doc.add_table(rows=1, cols=3)
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.style = "Table Grid"
    set_table_geometry(table, [2700, 2100, 4560])
    headers = ("开关 / 参数", "当前值", "像五岁小孩一样解释")
    for index, text in enumerate(headers):
        cell = table.rows[0].cells[index]
        shade_cell(cell, "E8EEF5")
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(text)
        set_run(run, 9.5, NAVY, True)
    set_repeat_table_header(table.rows[0])
    table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
    for name, value, meaning in rows:
        row = table.add_row()
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        cells = row.cells
        for index, text in enumerate((name, value, meaning)):
            cells[index].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            p = cells[index].paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if index == 1 else WD_ALIGN_PARAGRAPH.LEFT
            run = p.add_run(text)
            set_run(run, 9.2, INK, index == 0)
    set_table_geometry(table, [2700, 2100, 4560])


doc = setup_document()

# Editorial cover pattern, adapted to the compact_reference_guide palette.
for _ in range(5):
    doc.add_paragraph().paragraph_format.space_after = Pt(10)
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("EBO 家庭助手")
set_run(run, 34, NAVY, True)
p.paragraph_format.space_after = Pt(8)
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("从机器人到 GPT Realtime 的完整图解")
set_run(run, 20, BLUE, True)
p.paragraph_format.space_after = Pt(18)
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("把每个容器、每条线、每段声音和每张图片都讲清楚")
set_run(run, 12.5, MUTED)
p.paragraph_format.space_after = Pt(36)
add_callout(doc, "阅读方法", "先看图，再读图下面的三五句话。把 Docker 想成一个装着三间小屋的盒子。", SKY, BLUE)
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("当前系统快照 · 2026-08-31 · 本机 Docker Compose 部署")
set_run(run, 10, MUTED, False, True)

new_chapter(doc, "第 1 章：先认识这五位小伙伴", "如果只记住这一章，也能知道整个系统大概在做什么。", DIAGRAMS["big"], "图 1 · 整套系统的最短故事")
add_bullets(doc, [
    "EBO 机器人：真的眼睛、耳朵、嘴巴和轮子。",
    "Enabot 云端：官方 App 和机器人本来就使用的远程中转站。",
    "EBO Engine：翻译官，把品牌私有协议翻译成 HTTP 和 RTSP。",
    "Home Assistant：家里的控制面板，展示摄像头、按钮和状态。",
    "Realtime Assistant：把声音持续送给模型，本地挑选值得看的图片，并处理模型回答。",
    "OpenAI Realtime：理解 Prompt、声音和最近图片，产生回答文字与回答声音。",
])
add_callout(doc, "一句话", "EBO Engine 管“接机器人”，Realtime Assistant 管“接模型”，Home Assistant 管“给人看和按”。")

new_chapter(doc, "第 2 章：三个 Docker 容器怎样互相找到", "它们住在同一条 Docker 内部网络里，不需要记住会变化的 IP。", DIAGRAMS["docker"], "图 2 · Docker 内部网络和服务名")
add_paragraph(doc, "在 Docker 小区里，`ebo-engine` 就像门牌号。Realtime Assistant 使用 `rtsp://ebo-engine:8554/ebo` 拉流，也使用 `http://ebo-engine:8098` 发控制命令。")
add_bullets(doc, [
    "Home Assistant 对外开 8123：人在浏览器里访问。",
    "EBO Engine 对外开 8098、8554-8557、8189-8192：API、RTSP 和低延迟 WebRTC。",
    "Realtime Assistant 对外开 8099：健康检查和给 EBO 下载回答 WAV。",
    "三个容器都有 unless-stopped 重启策略；Docker Desktop 启动后会自动回来。",
])

new_chapter(doc, "第 3 章：EBO Engine 这个翻译官里面有什么", "机器人讲的是 Enabot + Agora 的专用语言；其他程序更喜欢标准协议。", DIAGRAMS["engine"], "图 3 · EBO Engine 的输入、内部处理和标准出口")
add_bullets(doc, [
    "先用 EBO 账号登录云端，发现机器人并取得会过期的 Agora 令牌。",
    "RTM 通道传控制和状态，例如唤醒、摄像头、音量和移动命令。",
    "RTC 通道传视频和音频。机器人视频解码后重新编码为 H.264，麦克风成为 Opus 音频轨。",
    "MediaMTX 把它们发布为 RTSP；Panel/API 再把状态和命令做成简单 HTTP JSON。",
    "容器内部还有只绑定 127.0.0.1 的 MQTT 小总线，仅供 bridge 与 panel 互相传话；Home Assistant 当前不直接使用这个 MQTT。",
])
add_callout(doc, "断网小秘密", "普通 DNS、登录或云端失败会继续保留音视频模式重试；只有连续的底层信号崩溃才保护性降级。", PEACH, ORANGE)

new_chapter(doc, "第 4 章：Home Assistant 到底做什么", "它是显示器和遥控器，不是当前 Realtime 大脑。", DIAGRAMS["ha"], "图 4 · Home Assistant 与 EBO Engine 的来回通信")
add_bullets(doc, [
    "每 10 秒通过 HTTP GET /api/robots 读取机器人状态。",
    "抓取静态图时优先 GET /api/snapshot；失败才从 RTSP 抽一帧。",
    "按按钮、改音量或播放媒体时，通过 HTTP POST /api/cmd 发 JSON 命令，并携带私有 Token。",
    "摄像头直播源仍是 RTSP；Home Assistant 自己负责把它展示成 camera 实体。",
    "标准 media_player 扬声器实体会把一个音频 URL 交给 EBO Engine 播放。",
])
add_callout(doc, "别混淆", "LLM Vision 还留在项目里做旧的单帧实验，但常驻语音助手完全不依赖它。", ROSE, RED)

new_chapter(doc, "第 5 章：视频怎样从摄像头走到模型", "视频很密、图片很贵，所以要在本机先筛选。", DIAGRAMS["video"], "图 5 · 视频处理主路线")
add_bullets(doc, [
    f"FFmpeg 当前按每秒 {EFFECTIVE['motion_fps']} 帧抽取候选画面。",
    "OpenCV 先把图缩到 320 像素宽、转灰度并模糊，便宜地比较背景变化。",
    f"通过运动门后才缩放到最多 {EFFECTIVE['image_width']} 像素宽，以 JPEG quality {EFFECTIVE['image_quality']} 上传。",
    "上传形式不是视频，而是 conversation.item.create 中的 input_image（Base64 data URL）。",
    "新图片被 Realtime 确认后，程序删除上一张图片 item，因此会话只保留最新有效视觉上下文。",
])

new_chapter(doc, "第 6 章：本地运动检测如何挡住空镜", "它不认识“人”或“猫”，只看画面哪些地方真的变了。", DIAGRAMS["motion"], "图 6 · 当前运动门的逐级判断")
add_paragraph(doc, "这个门卫的目标不是完美识别物体，而是用几乎免费的计算挡住大量没价值的图片。机器人转头或灯突然亮起会让整幅画面大变；这类情况被当作 scene_reset，而不是上传一张模糊图。")
add_callout(doc, "当前阈值", f"亮度差 {EFFECTIVE['motion_threshold']}；最小运动块 {EFFECTIVE['motion_min']}；整幅变化上限 {EFFECTIVE['motion_max']}；连续 {EFFECTIVE['motion_confirm']} 帧；冷却 {EFFECTIVE['motion_cooldown']} 秒。")

new_chapter(doc, "第 7 章：声音怎样进入模型", "声音不是等有人说话才开始录；它一直以小块流动，由 VAD 找句子。", DIAGRAMS["audio"], "图 7 · 麦克风音频输入路线")
add_bullets(doc, [
    "EBO Engine 请求机器人打开麦克风，并把音频放进 RTSP 的 Opus 轨。",
    "Realtime Assistant 的 FFmpeg 把它统一成 24 kHz、单声道、16-bit PCM。",
    "每 100 毫秒一个小块，通过 input_audio_buffer.append 发送。",
    f"OpenAI 输入降噪当前是 {EFFECTIVE['noise']}，适合房间里的远场麦克风。",
    f"server_vad threshold={EFFECTIVE['vad_threshold']}；保留句首 {EFFECTIVE['prefix']} ms；安静 {EFFECTIVE['silence']} ms 算一句结束。",
    "输入转写模型 gpt-transcribe 在一句结束后返回最终文字，并写进 transcripts.jsonl。",
])

new_chapter(doc, "第 8 章：背景噪声为什么不一定让它回答", "当前设计把“切句”和“决定回答”拆成两步。", DIAGRAMS["noise"], "图 8 · 转写后的第二道低成本过滤")
add_paragraph(doc, f"当前 REALTIME_VAD_CREATE_RESPONSE={EFFECTIVE['create_response']}。这表示 server VAD 只负责发现一句话结束，不直接叫模型回答。程序等最终转写出来，再检查它是否像一句有信息的话。")
add_bullets(doc, [
    "空白转写：忽略。",
    "只有 1-3 个很短的拉丁词、总长度不超过 24：通常当作噪声碎片忽略。",
    "包含中文、数字、被识别为中文，或更完整的句子：发送 response.create。",
    f"interrupt_response={EFFECTIVE['interrupt']}：家人开始说话时，允许打断正在进行的模型回复。",
])
add_callout(doc, "小心", "过滤是在转写完成后发生，所以转写本身仍可能产生少量成本；它主要省掉误触发的模型回答。", ROSE, RED)

new_chapter(doc, "第 9 章：模型真正收到的 Prompt", "你写的 Prompt 是第一层；程序还会加上视觉边界和必要的短期记忆。", DIAGRAMS["prompt"], "图 9 · 每次 Session 建立时的 instructions 组成")
add_paragraph(doc, "当前 .env 中的角色 Prompt：", color=NAVY, size=12, after=4)
add_callout(doc, "原文", PROMPT, PEACH, ORANGE)
add_paragraph(doc, "在 visual_mode=context 下，程序还会追加这些意思：图片只是内部感知，不是用户发言；不要因为收到图片就主动回答；优先回答最近语音；只有被问到时才自然描述；不要泄露图片注入或运动检测机制；不要回答空白噪声；通常只说一两句。")

new_chapter(doc, "第 10 章：Realtime Session 里装了什么", "Prompt、声音和图片走同一条 WSS 长连接，但它们是不同事件。", DIAGRAMS["packet"], "图 10 · session.update、音频事件和图片事件")
add_bullets(doc, [
    f"模型：{EFFECTIVE['model']}。",
    f"输出模态：audio；声音：{EFFECTIVE['voice']}；输出格式：24 kHz PCM。",
    f"输入转写：{EFFECTIVE['transcription']}；噪声抑制：{EFFECTIVE['noise']}；回合检测：{EFFECTIVE['vad_type']}。",
    "truncation.type=retention_ratio，retention_ratio=0.8：窗口需要裁剪时一次保留 80%。",
    "token_limits.post_instructions=8000：留给 Prompt 之后的会话内容最多 8000 tokens。",
    f"视觉模式：{EFFECTIVE['visual_mode']}，所以图片进入上下文但不会自己触发回答。",
])

new_chapter(doc, "第 11 章：模型回答怎样从云端回到 EBO 嘴巴", "回答声音先完整收齐并保存，再交给机器人播放。", DIAGRAMS["output"], "图 11 · 回答音频、持久化和 EBO talkback")
add_bullets(doc, [
    "Realtime 连续返回 response.output_audio.delta，Assistant 把 PCM 小片段拼起来。",
    "response.output_audio.done 后写成 24 kHz 单声道 WAV。",
    "回答文字由 response.output_audio_transcript.done 写成同名 TXT，并追加 JSONL 索引。",
    "Assistant 对 EBO Engine 发 POST /api/cmd，命令 talk 的 payload 是该 WAV 的内部 HTTP URL。",
    "EBO Engine 用 FFmpeg 读 URL、转换成机器人需要的 PCM，再通过 Agora RTC 音频发送器推给扬声器。",
    "因为 talk 接口使用完整 URL，而不是持续音频流，所以当前不是完全流式全双工。",
])

new_chapter(doc, "第 12 章：一次真实对话的完整顺序", "把前面所有零件串成一列火车。", DIAGRAMS["conversation"], "图 12 · 从家人开口到 EBO 播放的事件时间线")
add_callout(doc, "视觉在旁边", "图片不是每轮语音都重新拍。最近一次通过运动门的图片会留在 Session 中，直到下一张有效图片替换它。", SKY, BLUE)
add_paragraph(doc, "如果模型正在说话时家人又开口，interrupt_response=true 允许新语音打断旧回答。被取消的回答缓存会被清掉，防止半截 PCM 混入下一段 WAV。")

new_chapter(doc, "第 13 章：60 分钟 Session 限制怎样被藏起来", "对家人来说助手长期在线；程序只是在后台换一条模型连接。", DIAGRAMS["session"], "图 13 · 55 分钟准备、59 分钟最后期限")
add_bullets(doc, [
    f"第 {int(float(EFFECTIVE['refresh'])) // 60} 分钟开始准备轮换。",
    "有人或模型正在说话时先等这一轮结束。",
    "从未发生真实对话的空 Session 直接换连接，不额外请求摘要。",
    "有对话时发一个 conversation=none 的纯文字响应，最多 600 tokens，压缩事实、偏好、任务和未决事项。",
    f"摘要最多保留 {EFFECTIVE['memory_chars']} 个字符，等待最多 {EFFECTIVE['handoff_timeout']} 秒。",
    f"第 {int(float(EFFECTIVE['hard_deadline'])) // 60} 分钟是紧急截止线，避免撞到 60 分钟硬断开。",
])

new_chapter(doc, "第 14 章：断网以后怎样自己回来", "网络回来时，不要求你手动重启容器。", DIAGRAMS["reconnect"], "图 14 · OpenAI 与 EBO 两边各自的恢复循环")
add_bullets(doc, [
    "Realtime WebSocket 使用 1、2、4、8、16、20 秒封顶的指数退避重连。",
    "意外断线会丢弃尚未完成的模型 PCM，避免坏音频。",
    f"重连后读取最近 {int(float(EFFECTIVE['reconnect_age'])) // 60} 分钟内已经落盘的用户/助手文字；context 模式还会重发最近有效运动帧。",
    "EBO bridge 普通退出每 15 秒重试；DNS 和登录失败不会再永久关闭 A/V。",
    f"EBO_AUTO_WAKE={EFFECTIVE['auto_wake']}：RTSP 不可用时最多每分钟请求一次唤醒和 camera/set on。",
    f"超过 {EFFECTIVE['media_stale']} 秒没有新视频或音频，健康状态变 false；容器启动前 {EFFECTIVE['startup_grace']} 秒是宽限期。",
])
add_callout(doc, "做不到的事", "断网期间不能调用云端模型；断线瞬间尚未完成的输入音频或回答无法恢复，只恢复已经完成并落盘的内容。", ROSE, RED)

new_chapter(doc, "第 15 章：哪些数据重建容器后还在", "容器可以换，数据抽屉不能跟着扔。", DIAGRAMS["storage"], "图 15 · Docker 容器与 Windows 持久化目录")
add_bullets(doc, [
    "homeassistant-config/：Home Assistant 设置、实体和数据库。",
    "ebo-data/：EBO Engine 的 options、Token、面板状态等。",
    "assistant-data/transcripts.jsonl：家人每个完成语音回合的文字。",
    "assistant-data/assistant_outputs.jsonl：模型回答的时间、ID、WAV/TXT 路径索引。",
    "assistant-data/replies/：每段回答的 WAV 和同名 TXT。",
    "程序不会自动清理家庭录音和明文，因此磁盘占用会持续增长。",
])

new_chapter(doc, "第 16 章：桌面脚本在做什么", "你不需要记 Docker 命令，只需要选对按钮。", DIAGRAMS["scripts"], "图 16 · 完整启动与 Prompt 重载的区别")
add_bullets(doc, [
    "电脑重启后：双击“启动 EBO 家庭助手.cmd”。",
    "只改了 .env Prompt 或 Assistant 参数：双击“应用 EBO Prompt 修改.cmd”。",
    "Prompt 脚本使用 --no-deps --force-recreate，只替换 realtime-assistant。",
    "两个脚本都会等待健康检查；失败时把状态和最近日志留在窗口。",
])

new_chapter(doc, "当前参数总表（第十七章）", "这是 2026-08-31 这台机器真正使用的有效值。")
add_key_value_table(doc, [
    ("模型", EFFECTIVE["model"], "使用哪一个 Realtime 大脑"),
    ("声音", EFFECTIVE["voice"], "EBO 说话时的声音"),
    ("输入转写", EFFECTIVE["transcription"], "把家人说话变成文字"),
    ("输入降噪", EFFECTIVE["noise"], "把房间远处声音当作远场麦克风处理"),
    ("VAD 类型", EFFECTIVE["vad_type"], "由服务器判断一句话何时开始和结束"),
    ("VAD 阈值", EFFECTIVE["vad_threshold"], "越高越不容易把小声音当成讲话"),
    ("句首 / 句尾", f"{EFFECTIVE['prefix']} / {EFFECTIVE['silence']} ms", "补回句首；安静多久算说完"),
    ("自动回答 / 打断", f"{EFFECTIVE['create_response']} / {EFFECTIVE['interrupt']}", "先看转写再决定回答；允许新话打断旧回答"),
    ("视觉模式", EFFECTIVE["visual_mode"], "图片只当背景，不因图片主动说话"),
    ("自动唤醒", EFFECTIVE["auto_wake"], "媒体断开时允许程序尝试唤醒摄像头"),
    ("运动采样率", EFFECTIVE["motion_fps"], "每秒检查几张候选画面"),
    ("最小运动面积", EFFECTIVE["motion_min"], "变化块至少占画面 0.3%"),
    ("最大变化比例", EFFECTIVE["motion_max"], "整幅大变当作转头或光变"),
    ("连续确认帧", EFFECTIVE["motion_confirm"], "连续两帧才相信"),
    ("图片冷却时间", EFFECTIVE["motion_cooldown"], "两张上传图片至少间隔 12 秒"),
    ("图片宽度 / 质量", f"{EFFECTIVE['image_width']} / {EFFECTIVE['image_quality']}", "控制图片大小和费用"),
    ("窗口 / 内容预算", "0.8 / 8000", "窗口裁剪保留 80%；Prompt 后留 8000 tokens"),
    ("计划轮换", f"{EFFECTIVE['refresh']} 秒", "55 分钟左右主动换连接"),
    ("硬截止", f"{EFFECTIVE['hard_deadline']} 秒", "59 分钟左右强制换连接"),
    ("重连记忆", f"{EFFECTIVE['reconnect_age']} 秒", "意外断线后最多回看 15 分钟完成对话"),
    ("媒体过期", f"{EFFECTIVE['media_stale']} 秒", "这么久没新视频/音频就判定不健康"),
])

new_chapter(doc, "第 18 章：端口像不同颜色的门", "端口只是电脑上一扇有编号的小门。")
add_key_value_table(doc, [
    ("8123", "Home Assistant → 浏览器", "人打开控制面板"),
    ("8098", "HA / Assistant → EBO Engine", "Token 保护的 HTTP JSON 状态与命令"),
    ("8099", "浏览器 / EBO Engine → Assistant", "健康 JSON；下载回答 WAV"),
    ("8101", "本机 → EBO Panel", "只绑定 localhost 的调试/控制面板"),
    ("8554-8557", "EBO Engine → HA / Assistant", "RTSP：H.264 视频 + Opus 音频"),
    ("8189-8192 TCP/UDP", "浏览器 ↔ MediaMTX", "局域网低延迟 WebRTC/WHEP"),
    ("443 / WSS", "Assistant ↔ OpenAI", "加密 Realtime 事件、Base64 音频和图片"),
    ("Enabot / Agora", "EBO Engine ↔ 云端 / 机器人", "登录、RTM 控制、RTC 音视频"),
])
add_callout(doc, "Docker 内部 DNS", "容器之间用 homeassistant、ebo-engine、realtime-assistant 这些服务名，而不是容易变化的容器 IP。", SKY, BLUE)

new_chapter(doc, "第 19 章：安全边界和现在还没有的能力", "有些“不做”是故意的。", DIAGRAMS["boundaries"], "图 17 · 当前系统的四条重要边界")
add_bullets(doc, [
    "模型没有电机工具，因此不能自己移动、回充或巡逻。",
    "手机官方 App 与 EBO Engine 可能竞争同一个控制会话；主链路会继续按日志和重试逻辑自恢复。",
    "当前 talkback 是整段 WAV 播放，没有真正的实时回声消除。",
    "OpenCV 运动门不认识人物类别；树影、电视或宠物仍可能触发。需要类别识别时才值得引入 Frigate。",
    "Prompt、语音转写和回答文字属于家庭敏感数据；不要上传 .env 或 assistant-data 到公开仓库。",
])

new_chapter(doc, "第 20 章：出问题时按这张小检查表", "从最外层向里找，不需要一上来就重建全部容器。")
for number, (title, detail) in enumerate([
    ("Docker Desktop 绿了吗？", "没有 Docker，三个小屋都不存在。双击完整启动脚本。"),
    ("三个容器都 Running 吗？", "完整启动脚本会显示 homeassistant、ebo-engine、realtime-assistant。"),
    ("Home Assistant 8123 能打开吗？", "打不开先看 Home Assistant 日志，不要先怪模型。"),
    ("8099/health 的 realtime_connected 是 true 吗？", "false 多半是网络、API Key 或 OpenAI 连接。"),
    ("video_streaming / audio_streaming 是 true 吗？", "false 多半在 EBO、云端、RTC 或 RTSP 这一段。"),
    ("刚改 Prompt 吗？", "双击“应用 EBO Prompt 修改.cmd”，只重建 Assistant。"),
], start=1):
    p = doc.add_paragraph(style="List Number")
    run = p.add_run(title + " ")
    set_run(run, 11, NAVY, True)
    run = p.add_run(detail)
    set_run(run, 11, INK)
add_callout(doc, "健康的定义", "Realtime 已连接，而且最近 20 秒内视频和音频都在更新，才算 ok=true。", MINT, TEAL)

new_chapter(doc, "附录：这份文档对应的代码位置", "想继续深挖时，可以从这些文件开始。")
add_bullets(doc, [
    "compose.yaml：三个容器、端口、网络、环境变量和数据挂载。",
    "realtime-assistant/app.py：运动门、音频输入、Prompt、Realtime 事件、Session 轮换、持久化与健康检查。",
    "ha-enabot/ebo/run.sh：EBO Engine 启动、内部 MQTT 和桥接进程监督。",
    "ha-enabot/ebo/ebo_bridge.py：Enabot/Agora 控制、音频、状态和 talkback。",
    "ha-enabot/ebo/ebo_video.py：YUV 视频、FFmpeg H.264 与 MediaMTX RTSP/WebRTC。",
    "ha-enabot/ebo/panel.py：HTTP API、Panel、快照、WHEP/WHIP 代理。",
    "ha-enabot/ebo/ha_integration/custom_components/ebo/：Home Assistant 实体和 10 秒协调器。",
    "scripts/start-ebo-home.ps1：电脑重启后的完整启动。",
    "scripts/reload-ebo-assistant-prompt.ps1：只让 .env Prompt / Assistant 参数生效。",
])
add_paragraph(doc, "这份图解描述的是 2026-08-31 当前本机代码与配置。以后修改 .env 或程序后，参数和行为可能变化。", color=MUTED, size=9.5, align=WD_ALIGN_PARAGRAPH.CENTER, after=0)

doc.core_properties.title = "EBO 家庭助手完整工作原理（图解版）"
doc.core_properties.subject = "EBO、Home Assistant、Docker 与 OpenAI Realtime 的端到端架构说明"
doc.core_properties.author = "EBO AI Home 项目"
doc.core_properties.keywords = "EBO, Home Assistant, Docker, OpenAI Realtime, 图解"
doc.save(OUTPUT)
print(OUTPUT)
