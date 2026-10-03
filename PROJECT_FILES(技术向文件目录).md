# 项目代码与中英文文档 / Project and bilingual documents

完整项目位于 [`ebo-ai-home/`](ebo-ai-home/)，包含语音助手、EBO Engine、Frigate/MQTT、Home Assistant、Diagnostic Agent、测试和部署脚本。根目录的 `README.md`、`README_zh.md` 是开发日记。

The project lives in [`ebo-ai-home/`](ebo-ai-home/): the voice assistant, EBO Engine, Frigate/MQTT, Home Assistant, Diagnostic Agent, tests, and deployment scripts. Root `README.md` and `README_zh.md` are development journals.

## 最新技术介绍 / Current technical introductions

**2026-10-03 · Frigate / `specter-ebo-v2`。** 中英文分开，每份包含 7 张图，简要介绍整体架构、语音流程、会话、身份与记忆、故障诊断、权限边界和 AWS 待办。

**2026-10-03 · Frigate / `specter-ebo-v2`.** Separate Chinese and English editions, each with seven diagrams covering architecture, speech, sessions, identity and memory, diagnosis, permissions, and remaining AWS work.

- [中文：新版技术介绍（7 张图）](ebo-ai-home/docs/TECHNICAL-INTRO.zh-CN.md)
- [English: Current Technical Overview (7 diagrams)](ebo-ai-home/docs/TECHNICAL-INTRO.en.md)
- [版本更新与 AWS 待办 / Release status and AWS work](ebo-ai-home/docs/RELEASE-2026-10-03.md)

**新版 Diagnostic Dashboard 的 AWS 端尚未完成迁移与验证，当前默认只管理本地。** 旧版完整保留在 [`archive/pre-frigate-2026-10-03`](https://github.com/YeChen-coder/EBOBotToDigitalPet/tree/archive/pre-frigate-2026-10-03)。

**The new Diagnostic Dashboard's AWS side is not migrated or validated; current runtime control defaults to local scope.** The previous version is preserved on the archive branch above.

## 部署与诊断 / Setup and diagnostics

- [中文本地部署说明](ebo-ai-home/README.zh-CN.md)
- [English local setup](ebo-ai-home/README.md)
- [Diagnostic Agent 操作说明 / Operating guide, Chinese](ebo-ai-home/ops/diagnostics/README.zh-CN.md)
- [中文：Diagnostic Agent 当前实现设计（Word）](ebo-ai-home/docs/Diagnostic_Agent_当前实现设计说明.docx)
- [English: Diagnostic Agent Current Implementation Design (Word)](ebo-ai-home/docs/Diagnostic_Agent_Current_Implementation_Design.docx)
- [中文：Host Bridge 权限分离设计（Word）](ebo-ai-home/docs/Diagnostic_Agent_HostBridge_权限分离设计详解.docx)
- [English: Host Bridge Permission Separation Design (Word)](ebo-ai-home/docs/Diagnostic_Agent_HostBridge_Permission_Separation_Design_Guide.docx)
- [公开副本与隐私说明 / Public snapshot and privacy](ebo-ai-home/PUBLIC_SNAPSHOT.md)

## 旧版深入参考 / Earlier detailed references

- [中文版：架构与音视频技术详解（可编辑 Word）](ebo-ai-home/docs/EBO_架构与音视频技术详解_中文版.docx)
- [English: Architecture and Media Technology (editable Word)](ebo-ai-home/docs/EBO_Architecture_and_Media_Technology_English.docx)

这两份旧版 Word 各含 61 页、30 幅图解与 104 条参数说明，描述的是 2026-09-08 核对的实现。它们用于了解历史设计；当前 Frigate 架构、语音优先行为和 AWS 状态请先看上面的新版技术介绍。

Each earlier Word edition contains 61 pages, 30 diagrams, and 104 parameter records for the implementation reviewed on 2026-09-08. Use them for historical detail; start with the current introductions for the Frigate architecture, audio-first behavior, and AWS status.
