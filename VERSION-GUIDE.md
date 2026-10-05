# 版本导航 / Version guide

2026-10-04

## 中文

| 分支 | 定位 | 业务运行 | Diagnostic Agent / Dashboard |
|---|---|---|---|
| [`main`](https://github.com/YeChen-coder/EBOBotToDigitalPet/tree/main) | 完整版本，也是项目故事的主入口 | 本地 Docker 或已配置的 AWS ECS/Fargate；互斥运行 | 本地/云端控制、健康检查、有限恢复、两级诊断与转写记录 |
| [`frigate`](https://github.com/YeChen-coder/EBOBotToDigitalPet/tree/frigate) | Frigate 版；独立扩展分支，不是 main | Frigate/MQTT、新家庭会话、语音优先与个人记忆；当前针对本地 | 已更新本地诊断和会话控制；**新版 AWS 端尚未迁移完成或验证** |

`main` 的业务源码恢复自 Frigate 改造前的完整公开版本 `878696f`，保留本地、云端和 Diagnostic Agent 的整体能力。部署仍需自己的账号、设备密钥、API Key、AWS 服务与权限；默认示例先配置本地，云端按 AWS 说明接入。诊断容器、Host Bridge 和 Dashboard 运行在本机，云端业务使用 ECS/Fargate。

`frigate` 完整保留此前上传的 Frigate 源码、测试、设计文档和中英文图解。它的 AWS 待办只属于该分支，不能解释成 main 的旧版 AWS 功能尚未实现。

- main：[中文完整版本技术介绍](https://github.com/YeChen-coder/EBOBotToDigitalPet/blob/main/ebo-ai-home/docs/COMPLETE-VERSION-INTRO.zh-CN.md)、[English overview](https://github.com/YeChen-coder/EBOBotToDigitalPet/blob/main/ebo-ai-home/docs/COMPLETE-VERSION-INTRO.en.md)
- Frigate：[中文技术介绍（7 图）](https://github.com/YeChen-coder/EBOBotToDigitalPet/blob/frigate/ebo-ai-home/docs/TECHNICAL-INTRO.zh-CN.md)、[English overview (7 diagrams)](https://github.com/YeChen-coder/EBOBotToDigitalPet/blob/frigate/ebo-ai-home/docs/TECHNICAL-INTRO.en.md)
- 精确旧快照：[`archive/pre-frigate-2026-10-03`](https://github.com/YeChen-coder/EBOBotToDigitalPet/tree/archive/pre-frigate-2026-10-03)，保持 `878696f` 不变。

## English

**`main` is the complete local/cloud + Diagnostic Agent edition and the main development-story entry point.** Its application source comes from the complete pre-Frigate public version at `878696f`. With your configuration, the Dashboard supports local Docker or AWS ECS/Fargate operation, safe switching, deterministic recovery, model diagnosis, and transcript viewing. Diagnostic containers, the Host Bridge, and the Dashboard run locally; the cloud application runs on ECS/Fargate. Credentials, deployed services, and IAM permissions must be supplied by each installation.

**`frigate` is the separately maintained Frigate edition, not main.** It preserves the Frigate/MQTT stack, audio-first family sessions, personal memory, updated local diagnostics, tests, and illustrated documentation. Its new AWS Dashboard migration is unfinished. That limitation belongs to the Frigate edition and does not negate the existing AWS capabilities in main.

Use the edition-specific links above. The exact pre-Frigate archive remains unchanged. Older dated documents and journal passages describe their recorded stages; these branch labels determine which source tree to use today.
