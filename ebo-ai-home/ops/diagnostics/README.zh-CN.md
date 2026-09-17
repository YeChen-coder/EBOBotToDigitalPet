# EBO 独立监控与诊断

**日常入口：[运行与诊断 Dashboard](http://127.0.0.1:8179)**。同一页面选择「云端运行 / 本地运行 / 全部停止」，查看实际状态、切换进度、故障处理和诊断建议。操作说明见 [统一页面与权限配置](HEALTH-REPORT.zh-CN.md)。

固定恢复优先：异常持续确认 → 适用的有限恢复 → 功能复检。恢复成功零模型调用；没有适用恢复流程、恢复失败或短期反复故障时才进入诊断。

AWS ECS/Fargate 接入已实现，配置、身份与恢复规则见 [AWS 接入说明](AWS.zh-CN.md)。顶层 `runtimeEnvironment` 必须为 `local` 或 `aws`，互斥选择业务环境；两边复用诊断流程并保留各自历史。频率、开销和切换方法见 [采样说明](SAMPLING.zh-CN.md)。

日常启动、状态查看、模型切换、暂停和报告阅读见 [操作手册](USAGE.zh-CN.md)。

自动更新的 Agent 自身健康、历史事件及各级处理结果见 [状态页说明](HEALTH-REPORT.zh-CN.md)，本机输出为 `local/health-report/index.html`。

## 部署边界

| 单元 | 职责 | 可访问的数据与权限 |
|---|---|---|
| watcher 容器 | 探测、固定规则、恢复预算、复检、通知 | 健康接口、限定宿主机操作入口；无 SDK |
| diagnostic-service 容器 | 任务持久化、可选 Codex/API 初查、高级 provider 调度 | 筛选后的证据；无 Docker 权限 |
| codex-triage 容器 | 轻量 Codex SDK 初查，默认 Luna / low | 专用任务卷和登录卷，允许源码快照；无 AWS/Docker 权限 |
| codex-worker 容器 | Codex SDK 只读深入排查 | 专用代码快照、独立 Codex 登录和任务卷；无 Docker socket |
| Windows host bridge | 检查限定容器、重启限定服务、本地提示、Docker guardian | 当前用户的 Docker 权限；无模型调用 |

所有诊断容器属于独立 Compose 项目 `ebo-diagnostics`。业务 Compose 不变。四个容器为普通用户、只读根文件系统、独立数据卷，设置 CPU/内存/PID 上限。

控制网络连接 Watcher 与诊断服务，分析网络连接诊断服务与 worker。网络拆分不能代替授权：HTTP 作业和宿主机操作入口都要求独立随机 token。宿主机 8177 监听供 Docker Desktop 访问；应由主机防火墙限制在本机/Docker 网络。仅 Watcher 的健康入口在本机 8178 发布。模型子进程不会继承 bridge、diagnostic 或 worker HTTP token。

## 快速启动（Windows + Docker Desktop + Node 22）

在本目录运行：

```powershell
npm.cmd ci --ignore-scripts
node scripts/setup.mjs
docker compose build
powershell.exe -NoProfile -File scripts/install-host-task.ps1
docker compose up -d --wait
powershell.exe -NoProfile -File scripts/use-local-codex-login.ps1
node --env-file=.env scripts/status.mjs
```

`setup.mjs` 创建随机内部 token、`config.local.json` 和只含允许源码的 `local/source`。它不会覆盖已有配置，不复制 `.env`、家庭对话、录音、HA 数据或 Git 历史。源码快照带 commit 和生成时间；修改业务源码后再次执行 setup 刷新。

默认先观察，既不执行恢复也不调用模型/通知。完成验证后：

```powershell
powershell.exe -NoProfile -File scripts/set-mode.ps1 -Mode active
```

维护、主动停机、关闭 Docker Desktop **之前**进入维护模式，避免 guardian 把计划停机当故障：

```powershell
powershell.exe -NoProfile -File scripts/set-mode.ps1 -Mode maintenance
# 维护完成后重新执行 -Mode active
```

只暂停主动处理但继续观察用 `-Mode observe`。更新配置后需要重启 Watcher 和宿主机任务；`set-mode.ps1` 会完成两者。环境变量变化需 `docker compose up -d` 重建对应运维容器。

## 第一版固定规则

默认每 10 秒检查，连续异常 60 秒才确认；启动宽限 90 秒；重启后等待最多 120 秒，连续正常 30 秒才关闭；同一目标 30 分钟内不重复执行恢复。以上可配置。

- Engine：检查进程存活；其真实源音频由 Assistant 的健康接口提供。尚不宣称完整验证 Engine 控制/视频全部功能。
- Assistant：检查 Realtime、视频、RTSP 音频与上游收包/解码状态。仅确认媒体卡住/连接异常且未主动关麦时，允许重启 Assistant 一次。
- HA：检查 HTTP 可达性；未启用登录后的 HA 功能探针。
- 主动关麦、配置停用不触发语音恢复，也不会开麦；视频或 Realtime 的独立故障仍可诊断。
- 接口失联无法确认隐私状态时不盲目重启，升级诊断。
- 容器退出先依靠业务已有的 `unless-stopped`；持续退出、启动失败升级诊断。退出码 0 只说明正常退出，不能证明主动停用；计划停机必须显式设置全局或目标的 maintenance。未知停止会诊断/通知，不盲目拉起。
- 滚动窗口中 Docker restart count 增长至少 3 次时识别重启风暴，直接升级。
- OOM、磁盘满、鉴权失败等没有普遍安全的重启解法；不执行自动清盘、修改配置或循环重启。
- Docker 整体不可用由宿主机 guardian 在确认后执行一次 `docker desktop restart --detach`。恢复失败本地通知。当前仅实现 Windows Docker Desktop 后端。

## 诊断能力与可替换接口

执行器遵守同一 HTTP job 协议（内部 Bearer token）：

| 方法 | 路径 | 语义 |
|---|---|---|
| POST | `/jobs` | 提交幂等任务；同一 id 返回现有状态 |
| GET | `/jobs/{id}` | 查询 queued/running/completed/failed/cancelled |
| POST | `/jobs/{id}/cancel` | 取消排队任务或中止执行 |
| GET | `/health` | 存活检查，不返回凭证 |

请求：`id`、`schemaVersion: 1`、`target`、`symptom`、`evidence`、`timeoutSeconds`。结果包含结构化诊断、证据引用、建议及用量。执行器必须遵守取消与期限；默认一个执行任务、最多 8 个排队任务，最多保留 100 个完成报告。

`ADVANCED_PROVIDER_URL` 指向兼容执行器。第一版为 `codex-worker`，固定 SDK 0.154.0；后续接其他 AI 时新增适配器和镜像即可。Watcher 不认识模型名或 SDK。

`.env` 的 `TRIAGE_PROVIDER` 可选 `codex`、`api`、`disabled`。默认 Codex SDK 一线使用 `TRIAGE_CODEX_MODEL=gpt-5.6-luna`、推理 `low`。原 OpenAI Responses API 代码保留，选择 `api` 后使用 `TRIAGE_API_KEY` 与 `TRIAGE_MODEL`；缺失配置、超时或失败会升级。`ESCALATION_POLICY=on-inconclusive` 表示一线给出明确诊断时直接生成报告，否则升级；设为 `always` 则每次初查后都进入高级阶段。两级都只读，模型不能关闭故障；真实健康仍异常时 Watcher 保留故障并通知。

Codex 只读源码及证据，权限配置为 read-only、approval never、禁用代理工具网络和 web search。模型服务连接仍需网络。第一版 AI 不自动写补丁、不部署、不重启业务；确定性的操作桥负责已批准的恢复手册。

本机 Docker 不支持 worker 内的嵌套用户命名空间，因此固定 SDK 使用官方 `use_legacy_landlock` 兼容路径；没有开启 privileged 或解除容器 seccomp。升级 SDK 时必须重新运行 `docker compose exec -T codex-worker node src/sandbox-check.mjs`，验证可读快照、拒绝写入、拒绝工具网络。该兼容选项已标记 deprecated，未来升级需要重新确认支持情况。

高级阶段默认 `CODEX_MODEL=gpt-5.6-sol`、`CODEX_REASONING_EFFORT=high`；模型、推理强度和阶段超时均可调整。凭证可以用独立 `CODEX_API_KEY`，也可通过脚本仅复制现有 `auth.json` 到两个独立私有卷。该脚本不复制宿主机 hooks、技能、任务、配置；登录失效时需重新导入或专门登录。不要将凭证打进镜像或代码库。

## 证据与通知

健康快照使用字段白名单；重启前采集最近 10 分钟最多 200 行日志，并转换为有限事件类别。原始日志中的凭证/对话不出宿主机操作桥。事件提取是辅助线索，不能凭某一行 ERROR 判故障，也不保证覆盖所有错误；需要扩展时增加明确事件码和采集规则。

未解决事件持续 300 秒、或诊断已结束但复检仍异常时通知。诊断卡住不阻塞通知。每次成功通知去重；失败 30 秒后重试。恢复后发送恢复消息。模型输出不能关闭故障。

默认本地托盘提示和系统声音，由当前用户的登录会话执行，并保存 `local/host/alerts.jsonl`。Windows 勿扰/用户注销可能影响可见性；API 成功仅证明系统已接受提示，不证明用户看到。配置 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID` 后增加 Telegram。任一渠道成功即视为已投递，其他渠道不单独补发。

查看：`node --env-file=.env scripts/status.mjs`；容器日志：`docker compose logs --tail 100`。完整诊断报告保存在 diagnostic-data/worker-data 卷，Watcher's `/state` 通过 token 返回当前事件和结果。报告只保留最近 100 个；宿主机提示/操作记录需按使用情况归档。

## 验证与限制

```powershell
npm.cmd test
node test/docker.integration.mjs
# 会调用一次真实模型：仅对代码快照索引进行合成检查
docker compose exec -T diagnostic-service node src/smoke-provider.mjs
```

Docker 集成测试只创建并重启带随机名称的 `ebo-diag-fixture-*` 容器，结束时删除自己创建的测试容器，绝不操作 EBO 业务项目。

宿主机任务在当前用户登录时启动；用户注销或电脑断电时它不保证运行。覆盖这些情况需要独立设备心跳。诊断源码快照不包含运行时私有配置，因此模型对配置问题可能只能提出下一步人工检查。

停止运维系统：先切换维护模式，`Stop-ScheduledTask -TaskName 'EBO Diagnostics Host Bridge'`，再 `docker compose down`（不加 `-v`，保留记录）。移除开机任务使用 `Unregister-ScheduledTask -TaskName 'EBO Diagnostics Host Bridge'`。

参考：[Codex SDK](https://learn.chatgpt.com/docs/codex-sdk)、[Docker 重启策略](https://docs.docker.com/engine/containers/start-containers-automatically/)。
