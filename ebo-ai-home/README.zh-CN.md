# EBO 家庭助手：Specter 会话框架

> **分支：`frigate`（Frigate 版，不是 main）。** 本分支的新架构当前针对本地，新版 AWS Dashboard 尚未完成迁移；完整的本地／云端＋Diagnostic Agent 版本在 [`main`](https://github.com/YeChen-coder/EBOBotToDigitalPet/tree/main)。[版本导航](../VERSION-GUIDE.md)。

**2026-10-03 发布状态：本地 Frigate / 新会话框架与 Diagnostic Agent 已更新；新版 Diagnostic Dashboard 的 AWS 端尚未完成迁移与验证。** 公开示例使用 `runtimeControlScope=local`，云端运行被禁用。旧版完整保存在 [`archive/pre-frigate-2026-10-03`](https://github.com/YeChen-coder/EBOBotToDigitalPet/tree/archive/pre-frigate-2026-10-03)，见 [版本更新说明](docs/RELEASE-2026-10-03.md)。

当前项目将 SpecterSaysHi 的身份触发、Frigate 图像、Realtime 会话、AEC/降噪、VAD 和个人记忆框架接到 EBO。主 Prompt 保留当前 `.env` 的 `EBO_ASSISTANT_INSTRUCTIONS`；模型语音通过原 EBO Engine PCM 接口返回机器人，保留 WAV 回退。

```text
EBO → Engine RTSP → Frigate 人脸 / MQTT → 爸爸或妈妈的有限会话
             └→ 音频 → WebRTC AEC / 降噪 → Realtime Agent
Frigate 按需图像 ──────────────────────────┘
                 Realtime 音频 → Engine → EBO 扬声器
                 会话结束 → 各自总结与长期记忆
```

不使用猫逻辑或视频输出，未迁移 Specter 的任何实际记忆或人脸数据。原 Home Assistant 集成和设备控制保留。图像保留 Frigate 最新单帧更新；音频使用待机语音核查唤起、主转写回复门控和独立 live 转写。默认轮流说话，播放和播完后 800 ms 屏蔽输入；本地插话仅作实验选项。Realtime 自动回复与自动打断均关闭。原运动图像门控、长期连接轮换与交接恢复仍不使用。

## 日常使用

在此目录运行：

```powershell
.\scripts\start-ebo-home.ps1 -RebuildAllServices
Invoke-RestMethod http://127.0.0.1:8099/health
```

本地服务包括 Home Assistant、EBO Engine、Frigate、Mosquitto 和 Realtime Assistant。日常双击桌面的“一键开启 EBO 项目.cmd”（仓库入口为 `scripts/start-ebo-home.cmd`）：自动启动 Docker、检查配置、同步 `.env` 的账号连接设置并保留 Engine 手动调整的音视频选项、更新诊断源码快照、构建业务和诊断镜像、重新创建容器、启动本地服务和恢复两个后台计划任务。完成后检查音视频、Home Assistant、Frigate 和诊断容器健康，并打开 Home Assistant。两个桌面脚本设置 `runtimeControlScope=local`，不查询、启动或停止 AWS 服务；云端暂未迁移，后续启用时需另行配置。

每次都会执行构建检查；Docker 缓存会复用未修改的依赖层，代码或依赖变化会构建对应层。重新创建容器会加载 `.env`、Compose 和挂载配置文件的修改。关停使用桌面的“一键关停 EBO 项目.cmd”，或运行 `scripts/stop-ebo-home.ps1`；配置和持久化数据保留。构建或健康检查失败时窗口会显示错误，不会显示启动成功。

- [Dashboard](http://127.0.0.1:8179)：使用“暂停 AI 助手 / 恢复 AI 助手”在家人通话时控制 AI 发声和唤醒；也可选“爸爸”或“妈妈”手动开启/结束一轮会话。暂停状态会保留，详见 [AI 助手开关](docs/assistant-pause.zh-CN.md)。
- [Home Assistant](http://127.0.0.1:8123)：原设备、摄像头和控制面板。
- [Frigate](https://127.0.0.1:8973)：本项目独立的人脸库，使用它自己的登录账号。

待机持续本地检测语音，完整话语经主转写核查有效后开启会话并回答第一句话；默认不因人脸靠近自动问候。身份未确认时使用临时家人会话，不读写父母记忆；唯一近期识别到的父母可提供身份提示，手动开启可明确选择。默认空闲 10 分钟结束会话并回到听音待机，一个时刻只开一个会话。`standby` 时没有 Realtime 连接是正常的，仅完整候选语音调用转写，源音视频、Frigate 和 MQTT 仍受监测。

```powershell
.\scripts\register-parent-faces.ps1 -User father -PhotoDirectory 'C:\ParentPhotos\爸爸'
.\scripts\register-parent-faces.ps1 -User mother -PhotoDirectory 'C:\ParentPhotos\妈妈'
```

完整行为、实现映射、照片操作、验证与剩余现场验证见 [Specter 迁移说明](docs/specter-migration.zh-CN.md)，当前参数见 [`.env` 说明](docs/realtime-session-env.zh-CN.md)。旧框架文档保留为历史参考。

## 配置与持久化

本机已有账号和设备配置。新部署先复制 `.env.example`，填写自己的 EBO 账号、App 密钥、API Token、主机 IP、地区与 OpenAI Key，再运行 `scripts/prepare-ebo.ps1` 生成 `ebo-data/options.json`。EBO HOME App 与 Engine 使用同账号时可能争用控制会话。

只修改 Prompt 或助手参数后运行 `scripts/reload-ebo-assistant-prompt.ps1`；它重建助手容器并检查监听与媒体。修改代码或依赖需重新构建镜像。新音频处理在 Assistant 中执行，Engine 的 Agora AEC、降噪和 AGC 默认关闭。

| 宿主机目录 | 内容 |
|---|---|
| `assistant-data/memory-v2/father`、`mother` | 当前父母各自的会话总结和长期记忆，首次为空 |
| `assistant-data/transcripts.jsonl` | 当前 Realtime 转写，含 `user_id` |
| `assistant-data/replies`、`assistant_outputs.jsonl` | 原格式回答音频、文字和索引 |
| `frigate-data`、`frigate-media` | 独立 Frigate 模型、数据库、人脸照片 |
| `ebo-data` | 原 Engine 配置、设备状态与滚动日志 |
| `homeassistant-config` | 原 Home Assistant 数据 |

`.env`、上述家庭运行数据及 `private/` 已排除版本控制。旧家庭转写/录音保留为历史，新会话不读取旧交接日志。原代码和修改前配置备份在 `private/refactor-before-specter/`。

## 诊断

`ops/diagnostics` 同步了新健康合同、Frigate/MQTT 目标、代码快照、诊断 Prompt 与会话控制。待机和等待照片不触发错误恢复，麦克风真实关停或源音频停流仍显示异常。播放器静音与全局麦克风区别见 [音频健康说明](docs/audio-listen-health.zh-CN.md)。

本次部署针对本地。AWS 保留原服务和历史，但旧版任务为 0；Dashboard 暂不允许开启旧架构云端，须完成对应云端迁移后才能使用。

```powershell
node ops/diagnostics/scripts/setup.mjs
# 在 ops/diagnostics 目录启动诊断容器：
docker compose up -d --build
```

现有宿主机 Bridge 与健康报告计划任务继续提供本地页面。暂停服务请使用 Dashboard“全部停止”；关闭浏览器不会停止项目。
