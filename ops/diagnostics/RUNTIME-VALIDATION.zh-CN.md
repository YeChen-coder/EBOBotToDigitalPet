# 统一运行控制验收 · 2026-09-15

## 自动验证

`node --test test/*.test.mjs`：86 项通过。

覆盖三种模式的执行顺序、失败时禁止启动另一边、双端停止的独立尝试、切换/自动恢复互斥、停止请求中断健康等待、重启后保留选择、主动停止不触发诊断、限次恢复、STOPPING 任务不算停止、自动扩缩容冲突拒绝、AWS 账号核对和精确命令限制、页面同源与 CSRF 校验、过期数据不显示健康、模型失败与建议展示。PowerShell 入口通过语法检查。

## 本机安装与实机核验

- Host Bridge 提供 `http://127.0.0.1:8179/` 统一页面；已通过浏览器检查布局和实时状态。
- Watcher 与 diagnostic-service 镜像已更新；四个诊断容器均 running / healthy。
- `EBO Diagnostics Host Bridge`、`EBO Diagnostics Health Report` 两个既有计划任务均运行。
- 经用户明确授权，安装 `EboRuntimeControl` 角色和指定 ECS 服务控制策略；未创建新的长期访问密钥。
- 按原来的云端选择执行：三个本地业务容器全部 exited，RestartPolicy 为 no。
- ECS 服务保持 desiredCount=1、runningCount=1、pendingCount=0，原 Task 未被替换。
- 刷新/重启 Bridge 后仍保留云端选择，本地未自动重新启动。

## 验证边界和当前故障

没有为了测试而将实际云端业务切换到本地或全部停止；这两条路径的顺序、错误处理和命令约束通过注入依赖的自动测试验证。真实 AWS 控制身份执行指定服务 UpdateService 已成功。

云端 Task / Docker 容器 HEALTHY 不代表应用功能正常。实机功能检查未通过：`source_audio_status=no_source_packets`、`source_audio_ok=false`，虽然实时连接和音视频传输标志为 true。控制器没有把切换标记为完全成功，保留 `runtime_health_timeout`，Watcher 继续诊断所选云端目标。页面明确显示“云端运行 · 功能检查未通过”及源音频原因。

此前及本次实际模型诊断任务存在 execution_failed/provider_failed；报告现明确呈现一线、高级阶段失败，不把任务结束当作故障恢复。本次功能改造不声称已修复设备源音频或模型执行失败。
