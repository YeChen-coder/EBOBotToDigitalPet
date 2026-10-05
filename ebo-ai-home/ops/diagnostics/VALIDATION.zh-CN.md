# 第一版验收记录

> **分支：`frigate`（Frigate 版，不是 main）。** 本分支的新架构当前针对本地，新版 AWS Dashboard 尚未完成迁移；完整的本地／云端＋Diagnostic Agent 版本在 [`main`](https://github.com/YeChen-coder/EBOBotToDigitalPet/tree/main)。[版本导航](../../../VERSION-GUIDE.md)。

**历史验收记录。** 本文中的 AWS 结果对应旧版部署，不代表 2026-10-03 Frigate / `specter-ebo-v2` 已完成云端迁移。新版 Diagnostic Dashboard 的 AWS 端尚未完成；当前公开配置只管理本地。新版 269 项测试及待办见 [发布验证与 AWS 状态](../../docs/RELEASE-2026-10-03.md)。

2026-09-09，多伦多时间。所有改动位于 `feature/diagnostic-agent`，集中在 `ops/diagnostics/`。

| 检查 | 结果 |
|---|---|
| 离线故障与接口测试 | 26 项通过 |
| 实际 Docker 重启后恢复 | 专用 fixture 容器重启 1 次，模型任务 0 次 |
| 实际 Docker 重启仍失败 | 专用 fixture 容器重启 1 次，诊断提交 1 次（测试替身，不调用模型） |
| 真实 Codex SDK 任务 | ChatGPT 登录已识别；实际读取源码快照，工具成功 1 次、失败 0 次，返回结构化中文诊断 |
| 沙箱边界 | 快照读取成功、写入可写数据卷被沙箱拒绝、工具访问本容器 HTTP 被拒绝 |
| 本地通知 | 安装测试提示已由宿主机通知入口接受并执行；不保证 Windows 勿扰下用户可见 |
| 业务状态 | 初始 Engine、Assistant、HA 检查正常；随后另一个已获授权的云迁移任务停止本地 Engine/Assistant，已保留停用状态 |
| 隔离 | 3 个独立诊断容器；无业务模块导入；无 Docker socket；私有数据未同步至发布副本 |

## 真实 SDK 验证

成功任务 `smoke-21497f2d-2892-4ed6-ad7c-ab76d8f57e2c`，读取 `/workspace/snapshot.json`，确认快照 commit 为 `88b97a8e3c38469797d5e2eb89bc819bc6b30d1d`。这是合成检查，不是线上故障排查，不作为业务恢复证据。

验证中先发现精简镜像缺少系统 CA，补齐后模型连接成功；继而发现默认 bubblewrap 需要 Docker 禁止的嵌套命名空间，使用 SDK 支持的 Landlock 兼容路径后只读工具成功。镜像仍保留普通用户、cap_drop ALL、no-new-privileges 和 Docker 默认 seccomp。

## 当前启用范围

- Watcher 正式模式：固定规则监控、适用故障有限恢复、复检失败后 Codex 排查、本地提示。
- Docker guardian：当前用户登录会话内运行，确认引擎持续失效后尝试恢复一次。
- 一线 API 与 Telegram 已实现配置入口，未配置、未进行真实网络调用测试。
- 未对真实 EBO 做破坏性故障注入；未实际重启 Docker Desktop，guardian 用注入故障的离线测试验证。
- 第一版 AI 只读分析并提出建议，不自动改代码、部署或操作机器人。

## 并行云迁移及配置重载修复

23:18:39（多伦多时间），另一个任务「调研 AWS Fargate 诊断架构」执行 `docker stop --time 30 ebo-ai-home-realtime-assistant ebo-ai-home-ebo-engine`，准备单实例切换到云端。Docker 事件包含两个容器的 SIGTERM、stop、exit 0；本诊断操作审计为空，guardian 无重启记录。

本地两个目标已标记维护停用，避免与云端 Engine 争抢机器人。此版本尚未接入云端 ECS/CloudWatch 探针，不宣称正在监控云端业务。Home Assistant 和本地诊断系统继续运行。

以上是首次交付时的状态；后续 AWS 接入见文末记录。

依据这次事件修正规则：不再仅凭退出码 0 推断用户主动停机；只有显式 maintenance 才抑制故障，未知的正常退出会进入诊断和通知。

发现 Windows 任务停止包装 PowerShell 后可能遗留 Node 监听进程。计划任务改为直接托管 Node，清理了经 token 验证的旧监听进程；配置切换现在直接重启实际辅助进程。

## 2026-09-10 AWS 接入验收

- 44 项离线测试通过，包含 18 项新增 AWS/多目标用例：账户绑定、root 拒绝、分页空页/截断、旧 Task/过期健康拒绝、ECS 自愈窗口、替换风暴、完整 Task ARN 重检、并发去重、IAM 策略边界、监控失效零模型、独立目标故障与缓存复检。
- 使用已有临时 AWS 登录，仅运行显式的单次只读检查，没有把 root 配置交给后台进程。
- `ca-central-1 / ebo-cloud-lab`：期望和实际运行 Task 均为 1，Task 与两个容器健康；当前 Task `ed926789fe5041f9a28b18686430f492`。
- 真实健康日志采集成功：Engine robot_count=1；Assistant Realtime、视频、音频及真实源音频正常。日志按当前 Task 的完整流名称读取，未把旧 Task 日志作为健康证据。
- 真实证据采集成功：有界 CloudWatch 日志分类、CPU/内存统计、最近停止 Task 查询；采集错误为空。日志类别为空表示窗口内没有匹配的固定类别，不代表服务从未发生任何错误。
- AWS Task 替换流程使用离线测试验证；没有停止真实云 Task、强制部署、增加副本或启动本地 Engine。未为测试产生付费模型任务。
- 新 Watcher/诊断服务镜像已构建，宿主机适配器已重载。本地 Engine/Assistant 保持维护停用，HA 继续监控。
- 两项真实 Docker 恢复回归再次通过：测试容器可恢复故障为实际重启 1 次、模型任务 0 次；持续故障为实际重启 1 次、模拟诊断提交 1 次。仅操作自动创建并清理的 fixture 容器。
- 云端长期后台身份仍待用户选择；已生成只读/执行 IAM 策略，尚未创建新身份或授予权限。云目标暂设 maintenance=true，不能把单次 AWS 采集成功说成已经持续后台监控。Task 自动替换开关关闭。

以上为 AWS 接入初次交付状态；用户授权后的更新如下。

## AWS 只读身份与两级 Codex 验收

- 用户已授权创建 AWS 身份。创建 IAM 用户 `ebo-diagnostics-reader`，仅内联策略 `EboDiagnosticsRead`，无控制台登录配置、附加策略或组。凭据保存到用户目录 `.aws/ebo-diagnostics`，目录移除继承权限，只允许当前用户和 SYSTEM；没有放入 Git、镜像或模型环境。
- 首次新凭据验证遇到 IAM 传播延迟；重试后真实 ECS、当前 Task 的健康日志、CPU/内存与停止任务采集全部成功，collectionErrors/evidenceErrors 均为空。后台配置使用此专用身份，不再依赖临时 root 登录。
- IAM policy simulation 对 `ecs:StopTask`、`ecs:UpdateService`、`iam:CreateUser`、`secretsmanager:GetSecretValue` 均返回 implicitDeny。未授予主动云恢复权限；现阶段 ECS 自愈失败后诊断并通知。
- 一线/高级共用官方 SDK 0.154.0 worker 实现，但分别部署容器、任务卷和登录卷。一线为 `gpt-5.6-luna / low`，高级当前默认为 `gpt-5.6-sol / high`。
- 真实两级合成测试任务 `smoke-ddd459f5-17ae-4cca-baa4-9cba06e05b86`：Luna 成功只读访问源码快照，返回 inconclusive；Astra 接收一线结果继续调查并返回结构化报告。两级工具分别成功 1 次与 2 次、失败均为 0。此次是合成连接测试，不是实际事故或恢复证明。
- 53 项离线测试通过，新增可选 Codex/API/禁用分流、不同模型/推理配置、升级条件、取消传播、观察模式取消已有诊断、报告列表边界。原 API 适配代码保留；没有配置 API Key，未进行真实 API 调用。
- 已加入 `scripts/diagnostics.ps1` 统一命令和 `USAGE.zh-CN.md` 操作手册。模型结论不改变实际故障状态；一线明确定位可省略高级调用，仍由 Watcher 保留故障并通知，直到真实复检通过。
- 统一 status、reports、report 命令已真实运行并成功展示两级中文报告；pause/resume 已验证切换 observationOnly。云端持续采样已观察到 `aws_business_healthy`，本地 HA 为 `http_ready`，两个旧本地业务目标仍为维护停用，没有未关闭故障。
- 最终检查时 HA 被置于 Docker 的 `paused` 状态，并非退出；本诊断动作审计为空，没有执行 pause 或停止 HA。补充规则：显式 paused 抑制诊断，unpause 后自动恢复探测；保留用户当前暂停状态。新增回归后共 54 项测试通过。

## 2026-09-10 互斥环境与采样费用

- 用户明确业务只在本地或 AWS 其中一边运行，云模式包括 HA 在内的三个本地业务容器均无需运行。已加入必填 `runtimeEnvironment: local|aws`，当前真实配置设为 `aws`；删除旧 Engine/Assistant 的临时维护标记，由环境选择统一控制。
- AWS 模式只创建 AWS 适配器、只观测 `cloud-ebo`；local 模式只观测本地三个业务容器，不创建 AWS 采样适配器。宿主机取证/恢复接口拒绝非当前环境目标；切换后取消旧环境诊断，保留预算和历史，不记为恢复。
- 本地任意容器明确 `unhealthy` 会报故障，任意目标被暂停/维护时整体不再宣称全部健康。非当前环境被排除的目标不参与聚合。
- 61 项离线测试全部通过，新增覆盖环境选择及错值拒绝、AWS 模式忽略三个本地容器、本地每个容器的健康要求、排除目标拒绝动作和取证、旧任务取消/预算保留、宿主机配置不一致、频率命令校验和缓存时间联动。
- 真实 Docker fixture 两项回归通过：可恢复故障为重启 1 次、模型 0 次；持续故障为重启 1 次、模拟诊断提交 1 次。没有中断真实 EBO，也没有调用付费模型。
- 专用 AWS 只读身份测量一轮：8 次 API、104,861 字节紧凑 JSON、4.44 秒墙钟时间；云业务健康、采集错误为空。730 小时每分钟采样外推为 4.277 GiB/月，仅按加拿大区首档出站 $0.09/GB 折算约 $0.385，未计免费额度与协议/故障取证，不是实际账单。
- 新 Watcher 镜像与宿主机已重载；真实状态为 `runtimeEnvironment=aws`、activeTargets=[cloud-ebo]、excludedTargets=[engine,assistant,homeassistant]，云业务 healthy，无未关闭事故。本次没有启动/停止业务部署、修改 IAM 或 AWS 资源。
