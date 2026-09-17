# 采样、费用与运行环境

核对日期：2026-09-10。当前业务运行在 AWS ca-central-1；Watcher 和诊断容器仍运行在本地电脑。

## 采样是否就是部署验收里的证据

数据来源相同，采集范围不同。云项目的 `cloud/部署验收记录.md` 是一次部署的历史记录；其 `cloud/diagnostic.py collect --minutes 30` 按需下载两个应用日志组、Container Insights 性能日志、ECS 快照、最近停止 Task 和 CPU/内存统计，保存 JSONL、SQLite 等文件。

本项目后台不会读取该 Markdown，也不会反复下载那些静态证据文件。它直接调用 AWS：

| 场景 | 拉取内容 | 模型调用 |
|---|---|---|
| 正常巡检 | STS 确认账户；ECS Service/Task/容器状态；当前 Task 两个日志流中的 `health.snapshot` | 无 |
| 固定规则确认故障 | 上述状态，加限定窗口内日志分类、最近停止 Task、CPU/内存 `GetMetricStatistics` | 先等待 ECS 自愈或执行已授权的有限恢复；持续异常才诊断 |
| 诊断升级 | 已筛选的证据传给一线和高级 provider | 按配置；当前为两级 Codex |

日常不读取 Container Insights 的 performance 日志组，不轮询 212 个指标，不运行 Logs Insights 查询或 Live Tail。当前是有界回看：每轮重新读取最近 10 分钟的健康事件，再选最新一条；并非增量流，因此少量历史数据会重复传输。故障证据不会将自由文本原始日志交给模型。

## 当前频率与各个时间参数

配置位于本目录 `config.local.json`；它被 Git 忽略。

| 配置/来源 | 当前值 | 实际含义 |
|---|---|---|
| 顶层 `pollSeconds` | 10 秒 | Watcher 本地检查周期；云模式通常读取宿主机缓存，并非每 10 秒请求 AWS |
| `targets[id=cloud-ebo].aws.pollSeconds` | 60 秒 | AWS 完整健康采样的目标启动间隔；受宿主机循环、请求耗时和调度影响，不是精确时钟 |
| 云项目 `cloud/runtime.py` 的健康输出循环 | 15 秒 | 云端容器生成健康日志的周期；与本地读取周期分开 |
| `aws.logWindowSeconds` | 600 秒 | 每次读日志回看多久，不是采样周期；也用于故障证据/指标窗口 |
| `aws.maxLogPages` | 3 | 每个容器日志流最多读 3 页，每页最多 200 条；分页可能返回空页 |
| `aws.snapshotMaxAgeSeconds` | 180 秒 | ECS/健康采样缓存的最大年龄，至少为 AWS 周期的 2 倍 |
| `aws.healthMaxAgeSeconds` | 180 秒 | 云端健康事件的最大年龄；包含日志上传延迟，不能拿旧日志证明健康 |
| `confirmSeconds` | 60 秒 | 持续故障确认窗口；云端还必须拿到后续新样本，重复读缓存不算确认 |
| `aws.selfHealingSeconds` | 300 秒 | ECS 部署/调度/容器异常先等待原生自愈的窗口 |

采样不是即时报警。60 秒轮询下，正常新故障可能要等接近一轮才被看见，再加日志传输和固定确认时间；ECS 自愈类故障还会先经过其等待窗口。改慢轮询会同时拉长确认与恢复验证延迟。

在 PowerShell 中进入 `ebo-ai-home\ops\diagnostics` 后：

```powershell
# 将云端采样改为每 120 秒一次；同时保证缓存有效期至少 240 秒，并重载宿主机与 Watcher
.\scripts\diagnostics.ps1 sampling -Seconds 120

# 恢复当前每分钟一次
.\scripts\diagnostics.ps1 sampling -Seconds 60

# 用当前配置做一轮只读测量：只输出次数和数据量，不输出原始日志、不调用模型
.\scripts\diagnostics.ps1 sampling-cost
```

也可手动改 `config.local.json` 的相应字段，然后执行 `.\scripts\diagnostics.ps1 reload`。有多个 AWS 目标时，`sampling` 命令调整所有已启用 AWS 目标；只调整其中一个时手动编辑。允许 AWS 周期 30–3600 秒。命令不会自动缩短已有缓存有效期；如果从很慢改回很快并希望更早报告缓存过期，可手动将 `snapshotMaxAgeSeconds` 改回合适值，例如 60 秒轮询配 180 秒缓存。

当前保留 60 秒。为了节约不到一美元的读取流量而明显延迟故障发现，收益有限。需要降低日志写入或 Enhanced 监控费用，应另外修改云端遥测配置；仅降低本地采样频率不会降低那些费用。

## 实测增量费用

2026-09-10 12:15:58 UTC，使用独立只读身份测量一轮，业务健康且无采集错误：

- STS `GetCallerIdentity` 1 次；ECS `DescribeServices`、`ListTasks`、`DescribeTasks` 各 1 次；Logs `FilterLogEvents` 4 次（两条日志流含分页）。共 8 次请求。
- 返回对象转为紧凑 JSON 共 104,861 字节，约 102.4 KiB；墙钟耗时 4.44 秒，包括网络等待和 AWS CLI 启动，不等于占满 CPU 4.44 秒。
- 按 730 小时/月、60 秒一轮：43,800 轮、约 350,400 次总请求，其中日志读取约 175,200 次；返回对象约 4.277 GiB/月。请求数随分页、运行 Task 数和故障变化。

| 项目 | 本采样增加的费用 |
|---|---|
| Fargate CPU/内存 | 无新增 Task、规格或容器，不增加现有算力预留费用 |
| 现有健康日志写入、保存、Enhanced 指标 | 已由云端生成；本次只读采样不增加这些已有写入/指标系列费用 |
| 正常状态/日志读取 | 当前公开价目没有单列 `FilterLogEvents` 按次费用；此实现也不使用按扫描量收费的 Logs Insights。不要把全部 8 次请求套用指标 API 价格 |
| AWS 到本机的出站流量 | 假设免费额度已用完，Canada (Central) 首档 $0.09/GB，按返回对象估算约 $0.385/月 |
| 故障 CPU/内存查询 | 每次证据采集 2 个 `GetMetricStatistics` 请求；归入标准 Requests 的每月 100 万免费额度，超额按 $0.01/千次；故障取证还会增加日志流量 |
| 模型 | 正常采样零调用；故障诊断另按所选 Codex 账户额度或 API 用量计算 |

正常后台读取可先按 **约 $1/月以内** 预留；这是当前数据量下的工程估算，不是账单或硬上限，不含模型、原有云服务和高频事故取证。协议头、实际传输编码、响应大小变化均可能使计费字节与这里的 JSON 代理值不同。若账户仍有免费出站额度，流量这部分可能为零；100 GB 免费互联网出站额度跨服务共享，不能把全部额度留给采样计算。

按相同数据量外推：30 秒轮询约 8.55 GiB/月、$0.77；120 秒约 2.14 GiB/月、$0.19；300 秒约 0.86 GiB/月、$0.08。均未扣免费额度、未含协议和故障取证。

依据：[CloudWatch 定价](https://aws.amazon.com/cloudwatch/pricing/)、[CloudWatch 计费操作说明](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch_billing.html)、[互联网出站与共享 100 GB 额度](https://aws.amazon.com/ec2/pricing/on-demand/)、[ECS 定价](https://aws.amazon.com/ecs/pricing/)。区域单价核对云项目当日缓存的 AWS Price List，publicationDate 为 2026-08-31（CloudWatch）；加拿大区 DataTransfer-Out 首档为 $0.090/GB。`sampling-cost` 是 payload 测量工具，不会读取或证明实际账单。

## 让程序知道业务跑在哪里

顶层 `runtimeEnvironment` 必须显式填写 `local` 或 `aws`，缺失、拼错、`auto`、`both` 均拒绝启动。当前真实配置为 `aws`；示例默认 `local`。

| 配置 | 纳入业务健康判断 | 排除 |
|---|---|---|
| `local` | 本地 Engine、Realtime Assistant、Home Assistant 三个容器及相应健康探针 | AWS 目标；宿主机不创建 AWS 采样适配器 |
| `aws` | Fargate Task 内 Engine、Realtime Assistant 两个业务容器及健康日志 | 本地三个业务容器，包括 Home Assistant |

`targets` 中保留两边配置，环境选择器只激活其中一边；本地模式不运行 AWS 后台采样。状态显示当前环境、实际监控目标和排除目标。单目标维护仍是临时覆盖，不等于健康；本地某个容器被 pause 时显示 suppressed，整体不能显示全部健康。

```powershell
.\scripts\diagnostics.ps1 environment -Environment aws
.\scripts\diagnostics.ps1 environment -Environment local
.\scripts\diagnostics.ps1 status
```

环境命令修改的是**监控范围**，会重载诊断进程，不负责搬迁业务或启动/停止两边部署。切换业务时，先停止旧环境业务并确认停止，再切换监控环境、启动新环境；本地启动时包括 HA，云端运行时本地 HA 也不需要开。不能在云 Engine 仍运行时启动本地同一账号副本。选择器不会根据某一边离线自动回退到另一边，也不是跨云/本地的部署锁。

旧环境进行中的诊断会收到取消，历史与恢复次数仍保留，结束原因标记为“停止监控，未验证恢复”；宿主机拒绝对非当前环境的目标取证或重启。云端与 Watcher 的环境配置短暂不一致时显示监控配置异常，不用模型猜故障原因。

**业务环境不等于诊断系统所在环境。** 即使选择 `aws`，本机四个诊断容器和宿主机辅助进程仍需要运行；本地三个业务容器不需要运行。Docker guardian 仍用于保护本地诊断设施。当前未将诊断系统部署至云端，电脑断电/离线时本地系统无法继续采样或通知。
