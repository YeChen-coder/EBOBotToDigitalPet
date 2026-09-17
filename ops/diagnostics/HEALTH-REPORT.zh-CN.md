# EBO 统一运行与诊断页面

日常只使用一个入口：**http://127.0.0.1:8179**。也可运行 `powershell.exe -NoProfile -File scripts/diagnostics.ps1 dashboard`。

## 三个选择

| 选择 | 执行顺序 | 完成标准 |
|---|---|---|
| 云端运行 | 禁用本地三个业务容器的自动重启并停止 → Fargate 服务 desiredCount=1 | 本地停止；云端 Task、容器及音视频功能健康 |
| 本地运行 | Fargate 服务 desiredCount=0 → 等待所有 Task 完全退出 → 启动本地三个容器 | 云端无运行、等待或退出中的 Task；本地 Home Assistant、Engine、Assistant 健康 |
| 全部停止 | 尝试停止本地与云端，即使其中一边失败也继续处理另一边 | 两边均确认停止；无法连接不算停止成功 |

点击即执行，选择写入 `local/host/runtime.json`，重启后保留。切换期间显示具体步骤，不允许并发切换或自动恢复干扰；切换失败不会自动退回原模式启动另一边。重试只需再点同一个按钮。重启打断切换时保留失败记录，必须在页面重试核验。

“全部停止”在切换期间仍可点击：请求会立即记住，阻止后续启动，并中断功能健康等待；正在执行的单个 Docker/AWS 操作先收尾，再串行停止两边，避免并发启停互相抵消。

首次升级继承原监控环境，不擅自启停；首次点击后开始实际约束运行位置。每 60 秒核对两边状态，发现非目标环境又被外部启动会再次停止它。活动环境的功能故障继续走原 Diagnostic Agent；启动后的功能验证超时也会继续诊断。停止/切换不触发无意义模型请求。监控容器、Bridge 和本页面仍保持运行，以便随时重新启动项目。

首页先显示你的选择、实际运行位置、下一步；最近事件显示原因、已做的操作、复检结论和模型建议。底部展开技术证据，包含完整模型摘要、证据、建议和历史审计。状态失效会明确显示未知，不继续显示旧绿色。

## 云端控制权限（一次性）

AWS 只读身份不能执行启停。`local/aws-host.json` 的每个云端连接需设置 `controlProfile` 和 `allowRuntimeControl: true`。它们独立于故障自动替换所用的 `actionProfile/allowTaskReplacement`。宿主机配置及凭据不会发给浏览器或诊断模型。

生成最小范围策略：`node scripts/aws-policies.mjs`。控制策略在 `local/iam/cloud-ebo-control.json`，仅含指定 ECS 服务的 UpdateService、该集群必要的任务读取和区域内扩缩容只读检查。运行时命令进一步只允许配置的集群/服务、desiredCount=0 或 1；不允许任意 AWS 命令、部署或任务定义修改。

此机器已有独立诊断读用户时，可先运行 `node scripts/provision-runtime-control.mjs` 生成可审阅方案；经用户授权再运行 `node scripts/provision-runtime-control.mjs --execute`。脚本通过现有安装用身份创建受限角色，让诊断读用户 AssumeRole，不创建新密钥。完成后重启 Host Bridge。遇到 AWS 登录过期，先恢复安装身份登录再重试；不要把 root/管理员身份写入运行时 controlProfile。

如果服务还有未暂停的动态或定时自动扩缩容，控制器会拒绝切换并说明原因，以免服务停止后又被规则拉起。若任务列表分页超出安全上限或状态无法完整读取，同样不会把它当作已停止。

Fargate Task 完全停止后不再运行这部分计算；CloudWatch 日志、镜像、网络等独立资源可能仍收费。本功能不删除数据、镜像、服务或网络。

已确认的活动环境若被意外停止，在 `autoRecovery` 启用且非观察/维护模式时，控制器会重新遵循先停另一边再启动的顺序恢复；整个恢复窗口最多尝试一次，并写入切换记录。选择“全部停止”时不会触发这类恢复。应用功能卡住仍使用原有的限次诊断与恢复策略。

## 命令行与安装

```powershell
# 三种模式与页面使用同一份状态，无需重新创建 Watcher
powershell.exe -NoProfile -File scripts/diagnostics.ps1 environment -Environment aws
powershell.exe -NoProfile -File scripts/diagnostics.ps1 environment -Environment local
powershell.exe -NoProfile -File scripts/diagnostics.ps1 environment -Environment stopped

# 代码升级后更新监控容器，并重启宿主机控制服务
docker compose build watcher diagnostic-service
docker compose up -d --no-deps --force-recreate watcher diagnostic-service
powershell.exe -NoProfile -File scripts/restart-host-task.ps1
```

`diagnostics.ps1 stop` 仍是关闭诊断基础设施，**不是**停止业务；停业务用页面“全部停止”或 `environment -Environment stopped`。`configure.mjs environment` 仅用于初次安装的默认监控配置，不覆盖已保存的运行选择。旧 `scripts/start-ebo-home.ps1` 现会请求同一控制器先停云端，不能绕过运行选择直接启动本地。

## 合并对话转录

统一 Dashboard 的“对话转录”区域合并 `/ebo-cloud/assistant` 中两个 conversation 事件，以及本地 `assistant-data/transcripts.jsonl`、`assistant-data/assistant_outputs.jsonl`。对话内容仅展示时间、正文和“家人 / EBO”说话方，时间按浏览器所在时区显示。不会读取 WAV，也不会把原始对话交给诊断模型。

最新对话组在上，组内按时间从上往下读。旧日志没有明确的问答关联 ID，因此仅把同一来源、同一会话内相距不超过两分钟的用户消息和后续回复放在一组；这是阅读分组，不保证因果配对。单独的发言和回复仍保留。云端分块的长回复在各块到齐后自动拼接；重叠拉取、进程重启和本地文件重写按消息标识去重。

### 同步和费用控制

- 本地每 30 秒检查文件变化；页面每 15 秒读取本机缓存。
- 云端模式每 5 分钟检查；本地或全部停止模式每 30 分钟检查云端尾部。每轮最多两页，每页最多 200 条匹配事件，分页进度持久化。
- 新增的转录采集使用只读 `FilterLogEvents`，不使用 Logs Insights 扫描查询或 Live Tail。正常连续云端运行最多约 576 次请求/日，非云端模式最多约 96 次/日；另有每天 600 次硬上限，失败调用也计入，重启和刷新网页不重置额度。这个上限只针对新增转录采集，不含已有健康诊断调用。
- AWS 限流或读取失败自动退避，保留已读取内容；额度按 UTC 日期重置。以上是请求数量预算，不是金额保证，实际费用取决于账户、区域及 AWS 当期计费规则：[CloudWatch 定价](https://aws.amazon.com/cloudwatch/pricing/)。原有日志写入与存储费用仍按原配置发生。
- 首次从最近一天开始，然后在每轮剩余额度内向前补齐最近 7 天；每次先检查新日志，再继续历史分页。界面会提示历史尚未同步完毕，空分页也会继续跟随 token，不能把空页当成没有对话。[AWS 分页说明](https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_FilterLogEvents.html)。
- 增量拉取回看 10 分钟以处理通常的延迟写入；晚于这个窗口到达的历史事件可能无法补收。本机离线时不采集；恢复后继续检查点，但最多回看保留期。

合并缓存保留最近 30 天、最多 20,000 条消息；本地首次读取各文件末尾最多 8 MiB。页面初始显示 50 组，可逐步展开到最近 500 组。达到边界时提示保留范围，不删除原始文件或 CloudWatch 日志。缓存写入被 Git 忽略的 `local/host/conversations.json`，由本机 Dashboard 读取；它包含对话正文，不属于不含正文的诊断证据。

技术配置可在 `config.local.json` 的 `conversationLogs` 对象覆盖 `localSeconds`、`cloudSeconds`、`idleCloudSeconds`、`bootstrapDays`、`retentionDays`、`overlapSeconds`、`maxPagesPerPoll`、`dailyRequestLimit` 和 `maxMessages`，修改后重启 Host Bridge。默认无需额外设置。

### 实际验证（2026-09-16）

102 项自动化测试通过，涵盖倒序分组、组内时序、跨来源隔离、空分页、增量同步、预算、退避、并发去重、长消息跨页拼接、本地文件重写和只读接口。

08:32 UTC 的实际缓存包含本地 1,017 条、云端 111 条，共 1,128 条非空转录，形成 660 个阅读组；两端读取均无错误，没有待拼接消息。检查确认组间倒序、组内正序、消息标识不重复，接口没有输出原始日志元数据。连续读取页面接口三次，云端请求数保持 106 次不变。最近一条已收录云端消息为 2026-09-14 19:05 UTC，最新时间窗口已检查完成；更早的首次历史回填仍按预算在后台继续。

已在实际 Dashboard 核对消息气泡和“显示更早的对话”按钮，原运行模式保持云端。

## 详细报告和留存

`local/health-report/index.html` 是只读技术快照；统一页面内可展开查看。旧文件顶部也有返回统一页面的链接。

- `index.html`：业务健康、Agent 自身健康、当前 ECS Task、历史事件、各级模型任务与最近一次云端一天审计。
- `latest.json`：当前完整结构化报告，包含生成时间和检查失败项。
- `incidents.json`：观察到的历史事件归档，保留原始事件 ID。
- `jobs-history.json`：诊断调度、一线 Codex、高级 Codex 的任务与结果归档；安装 smoke 测试单独标识。
- `samples-YYYY-MM-DD.jsonl`：报告器启动后的每分钟摘要，按 UTC 日期分文件，不是原 Watcher 的每 10 秒采样全集。
- `cloud-day.json`、`cloud-ebo-*-health.jsonl`：单次 AWS 过去 24 小时审计及筛选后的健康事件，不含原始家庭对话。
- `audit-2026-09-12.zh-CN.md`：本次人工核查结论。

自动更新由独立 Windows 任务 `EBO Diagnostics Health Report` 运行，登录时启动，每轮完成后等待 60 秒。它读取本机状态和 Docker 持久化任务，不发通知、不触发模型、不操作云端，也不重复执行全天 AWS 扫描。容器关闭时仍可输出异常状态。HTML 每 30 秒重载，报告超过 180 秒会醒目显示“过期”，此时不能把上次绿色状态当成当前健康。

在本目录安装或重装报告任务：

```powershell
powershell.exe -NoProfile -File scripts/install-health-report-task.ps1
Get-ScheduledTask -TaskName 'EBO Diagnostics Health Report'
```

临时刷新一份报告：`node --env-file=.env scripts/health-report.mjs`。重新审计 AWS 最近 24 小时：`node scripts/audit-cloud-day.mjs`，随后等待报告器下一轮更新。AWS 审计会发只读请求；不会因打开页面自动运行。

停止报告器：`Stop-ScheduledTask -TaskName 'EBO Diagnostics Health Report'`。禁止下次登录自动启动：`Disable-ScheduledTask -TaskName 'EBO Diagnostics Health Report'`。不影响原 Diagnostic Agent。

当前业务状态来自 Watcher 的功能探针。Agent 自身检查包含 Watcher 心跳时效、宿主机接口、运行模式、环境一致性、四个容器状态、诊断服务和 Worker HTTP、凭据文件存在、任务积压、云端缓存时效。**没有新模型请求时，无法确认账号额度、凭据有效性以及完整模型执行链路当前一定可用**；页面明确显示这个验证边界。

9 月 12 日之前的旧 Watcher 关闭记录只有时间、事件 ID 和结果；缺失的原因及 Task 身份不会被猜测补齐。升级后关闭记录增加原因、Task ID、最后阶段、动作和诊断提交信息。原 Watcher 仍保留最近 100 个关闭事件，报告器会另行累计它实际读到的记录。报告器启动前的历史本地采样无法恢复；启用后的分钟采样也不是无遗漏的事件流。

报告器和原 Agent 都依赖本机供电与用户登录。日志按天持续保留，没有自动删除；需要时可人工归档这些本地文件。输出目录被 Git 忽略。
