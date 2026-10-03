# Diagnostic Agent 操作手册

**2026-10-03 当前版本：本地 `specter-ebo-v2` 已更新；新版 Diagnostic Dashboard 的 AWS 端尚未迁移完成或验证。** 公开配置为 `runtimeEnvironment=local`、`runtimeControlScope=local`，只管理本地五个业务服务；云端启动请求被拒绝，本地启停不查询或启停 AWS。旧 AWS 适配器、文档和历史实测保留作迁移参考，不能证明新版云端可用。详见 [版本说明与 AWS 待办](../../docs/RELEASE-2026-10-03.md)。

日常使用 [统一运行与诊断页面](http://127.0.0.1:8179)。当前只启停本地业务，支持 AI 暂停/恢复与父母会话控制；首次本地安装不需要 AWS 启停权限。见 [统一页面说明](HEALTH-REPORT.zh-CN.md)。

这是一套后台监控系统。正常时不需要打开 Codex 对话，也不会持续调用模型。Watcher 定期采样；固定规则确认故障且等待自愈/有限恢复无效后，才启动诊断。

## 当前公开版本的配置边界

| 项目 | 当前设置 |
|---|---|
| 业务环境 | `runtimeEnvironment=local`、`runtimeControlScope=local`；本地管理 |
| 云端监控 | 新版 AWS 端尚未迁移完成；旧版采样记录为历史参考 |
| AWS 身份 | 本地部署无需 AWS 运行控制身份；旧身份配置留在宿主机 |
| 本地业务 | Engine、Assistant、Home Assistant、Frigate、Mosquitto 纳入本地健康判断 |
| 一线诊断 | Codex SDK，`gpt-5.6-luna`，推理 `low` |
| 高级诊断 | Codex SDK，`gpt-5.6-sol`，推理 `high` |
| 升级条件 | 一线无法确定原因、失败、超时、被禁用或 API 未配置时升级；可改为每次升级 |
| 通知 | 本地提示/声音；Telegram 尚未配置 |

四个独立容器：Watcher、诊断调度、一线 Codex、高级 Codex。两个模型共用同一套 worker 代码，但有不同模型参数、任务队列、数据卷和登录卷。AWS 凭据只由宿主机读取，不交给任何模型。

采样范围、费用实测、各个时间参数和本地/云端切换，见 [采样、费用与环境说明](SAMPLING.zh-CN.md)。旧版云端每分钟采样约 105 KB、整月约 4.3 GiB 是历史实测，不代表新版本地或新版 AWS 开销；模型只在故障诊断时使用。

## 平时怎么开和看

打开 PowerShell，先进入目录：

```powershell
cd <repository>\ops\diagnostics
```

然后执行需要的命令：

```powershell
# 启动整套诊断系统并进入正式监控；先确保 Docker Desktop 正在运行
.\scripts\diagnostics.ps1 start

# 查看四个容器、各监控目标与当前故障
.\scripts\diagnostics.ps1 status

# 查看最近诊断报告列表
.\scripts\diagnostics.ps1 reports

# 把下方 ID 替换成列表里的实际 ID，阅读中文诊断报告
.\scripts\diagnostics.ps1 report -Id 实际报告ID
```

`start` 只启动本地运维容器与辅助任务，不会启动旧本地 Engine，也不会部署或重启云端业务。平时无需反复 start。已安装当前 Windows 用户登录时启动的宿主机任务，运维容器使用 `unless-stopped`；电脑必须开机、登录、联网且 Docker Desktop 已运行。手动 stop 后，下次用 start 恢复。

统一 Dashboard 还显示两个独立花销监测：OpenAI API 组织本月至今费用，以及 AWS 账号本月至今基础设施费用和最近入账日。页面刷新只读取本机缓存，不直接请求供应商。OpenAI 每 15 分钟最多同步一次；AWS Cost Explorer 每 6 小时最多同步一次（每个分页请求当前收费 0.01 美元，因此正常上限约为每月 1.20 美元）。当前月数据可能延迟或仍是预估值，不能代替最终发票。

状态含义：`healthy`=探测正常；`grace`=启动/部署/自愈等待中；`suppressed`=维护、停用或有意关闭功能；`fault`=有异常。故障阶段 `monitoring_failed` 表示拿不到可靠监控数据，并不证明业务挂了。若没有诊断报告，可能是一直健康，或固定恢复已经成功，这是正常行为。

## 暂停和停止

```powershell
# 继续采样，但暂停自动恢复、模型诊断和通知；已有模型任务会收到取消
.\scripts\diagnostics.ps1 pause

# 恢复正式模式
.\scripts\diagnostics.ps1 resume

# 停止本地诊断容器与宿主机任务，保留配置、凭据、故障历史和报告
.\scripts\diagnostics.ps1 stop
```

这些命令不停止云端业务，不改变机器人开麦状态。`resume` 不改变业务环境，也不清除单目标 `maintenance`。只想暂停当前环境的某个目标时，修改 `config.local.json` 对应目标的 `maintenance`，再执行 reload。

## 调整频率与切换业务环境

```powershell
# 当前 60 秒，可改为 120 秒；自动检查缓存有效期并重载监控进程
.\scripts\diagnostics.ps1 sampling -Seconds 120

# 实际切换运行位置，或停止两边业务（三选一）
# 历史云端操作：新版迁移并验证后才可启用；当前本地作用域会拒绝此请求
# .\scripts\diagnostics.ps1 environment -Environment aws
.\scripts\diagnostics.ps1 environment -Environment local
.\scripts\diagnostics.ps1 environment -Environment stopped

# 单次只读测量当前采样数据量
.\scripts\diagnostics.ps1 sampling-cost
```

当前环境命令与 Dashboard 均只管理本地五个业务容器，停止模式只停止本地业务。旧版的跨环境切换与双容器 Fargate 布局是历史实现，迁移完成前不适用于新版。本机诊断四容器继续运行，用来保留控制入口和检查结果。手动编辑频率：顶层 `pollSeconds` 控制 Watcher 本地检查；云目标 `aws.pollSeconds` 才控制 AWS 请求间隔。修改采样文件后执行 `reload` 生效。

## 怎么换模型或切回原 API

编辑本目录 `.env`。当前可调参数：

```dotenv
TRIAGE_PROVIDER=codex
TRIAGE_CODEX_MODEL=gpt-5.6-luna
TRIAGE_CODEX_REASONING_EFFORT=low
TRIAGE_TIMEOUT_SECONDS=90

CODEX_MODEL=gpt-5.6-sol
CODEX_REASONING_EFFORT=high
CODEX_TIMEOUT_SECONDS=300

ESCALATION_POLICY=on-inconclusive
```

一线模型和高级模型可任意分别更换为当前账号支持的模型；例如把高级模型改为 `gpt-5.6-sol`，不用改代码。推理强度可选 `low/medium/high/xhigh/max` 等，但必须被所选模型支持；此版本不开放自动子代理的 ultra 模式。无效模型/权限会显示任务失败，不会静默换成其他模型。

一线保留原 API：

```dotenv
TRIAGE_PROVIDER=api
TRIAGE_API_KEY=填自己的API密钥
TRIAGE_MODEL=填API支持的模型名称
```

改成 `TRIAGE_PROVIDER=disabled` 则直接使用高级诊断。API 配置不会因切回 Codex 而被删除。API 路径目前是 OpenAI Responses 协议，其他厂商协议需要对应适配器。

`ESCALATION_POLICY=on-inconclusive` 可以节省高级模型调用：一线已明确定位时直接出报告并由 Watcher 通知，故障仍保持打开，直到实际复检恢复。若希望即使一线已经定位，也总让高级模型复核，改成 `always`。

改完 `.env` 或监控配置后执行：

```powershell
.\scripts\diagnostics.ps1 reload
```

reload 会重建运维容器，进行中的诊断会中断，历史与恢复预算保留。升级源代码后用 `docker compose build` 再 reload。不要把 `.env`、`local/` 或 AWS 凭据提交到 Git。

总诊断时限由 `config.local.json` 的 `diagnosisSeconds` 控制（当前 300 秒）。一线最多使用总时限的三分之一，且不超过 `TRIAGE_TIMEOUT_SECONDS`；余下时间留给高级诊断。因此两个阶段各自的最大秒数不会简单相加。需要更深入排查时同时调整总时限和高级超时；队列自身最高 600 秒。

## 登录、通知与 AWS 权限

如果模型报告 `credentials_not_configured` 或登录过期，先在电脑上重新登录 Codex，然后执行：

```powershell
.\scripts\diagnostics.ps1 login
```

只复制登录文件，不复制本机全部 Codex 配置和任务。也可以在 `.env` 设置 `CODEX_API_KEY` 后 reload。两级使用当前账号的 Codex 额度，不是免费离线模型。

Telegram：填写 `.env` 的 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`，再 reload。通知只含故障摘要，不发送家庭对话或原始日志。当前 Windows 勿扰设置可能隐藏本地提示，报告仍保留在诊断系统中。

AWS 凭据保存在 `%USERPROFILE%\.aws\ebo-diagnostics`，不在业务项目或镜像内；目录仅当前用户与 SYSTEM 可访问。宿主机 `local/aws-host.json` 引用此位置。该 IAM 用户没有控制台密码，只有读取策略；访问密钥需按使用周期轮换，撤销后 Watcher 会报告监控失效。

OpenAI 花销监测必须使用单独的组织管理员 API Key；普通项目 Key、`CODEX_API_KEY` 和 Codex 登录都不具备读取组织账单的权限。在 `.env` 填写 `OPENAI_ADMIN_KEY` 后执行 `reload`。Key 只由本机 Host Bridge 读取，不会进入浏览器、诊断容器、报告或账单缓存。AWS 花销监测复用专用只读身份，并额外需要全局只读权限 `ce:GetCostAndUsage`；生成的 reader policy 已包含该权限。Dashboard 展示的是整个 OpenAI 组织与整个 AWS 账号，而不是单个模型、ECS 服务或任务的归因费用。

不熟悉 `.env` 时，在本目录运行 `powershell.exe -NoProfile -File scripts/configure-openai-billing.ps1 -OpenAdminKeysPage`。脚本会打开官方 Admin Keys 页面，以隐藏输入方式接收创建后只显示一次的 `sk-admin-...`，写入本机 `.env`、重启 Host Bridge，并验证 Dashboard 是否成功读到账单；密钥不会打印到屏幕。

当前云端自动替换关闭：先交给 ECS 自愈；若仍异常，诊断和通知。未来要开启 Task 替换，需要独立的执行身份，并同时配置 `actionProfile`、`allowTaskReplacement=true` 和目标 `restartOnStall=true`，详见 [AWS 接入说明](AWS.zh-CN.md)。不需要改两级模型代码。

## 自动运行逻辑

1. Watcher 按固定函数检查资源与业务健康，不调用模型。
2. 暂态问题先等待；适用的固定恢复成功并经持续复检确认后结束，零模型调用。
3. 持续异常进入一线；一线没有明确结论、失败或超时，进入高级诊断。
4. 模型提供原因、证据和建议；持续故障通知你。两级当前都只读，不会按模型输出修改业务代码、部署或开麦。
5. 实际健康恢复后关闭故障；“模型说没问题”不能关闭故障。

这里只监控已实现的健康能力，容器健康和音频输入正常不能证明机器人扬声器一定成功播放。

模型选择依据 [OpenAI 官方 Codex 模型说明](https://learn.chatgpt.com/docs/models)，SDK 接入依据 [Codex SDK 文档](https://learn.chatgpt.com/docs/codex-sdk)。实际可用性以当前账号和集成测试为准。
