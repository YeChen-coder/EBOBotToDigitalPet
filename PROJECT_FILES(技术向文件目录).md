# 项目代码与中英文文档 / Project and bilingual documents

**本目录对应 `main`：完整的本地／云端＋Diagnostic Agent 版本。** 项目源码在 [`ebo-ai-home/`](ebo-ai-home/)，根目录中英文 README 保留整个开发故事。[版本导航 / Version guide](VERSION-GUIDE.md)。

**This index describes `main`, the complete local/cloud + Diagnostic Agent edition.** Source lives in `ebo-ai-home`; the root Chinese and English READMEs retain the development story.

## main：完整版本 / Complete edition

- [中文技术介绍：本地、云端与 Diagnostic Agent（5 图）](ebo-ai-home/docs/COMPLETE-VERSION-INTRO.zh-CN.md)
- [English: Local, Cloud and Diagnostic Agent (5 diagrams)](ebo-ai-home/docs/COMPLETE-VERSION-INTRO.en.md)
- [中文本地部署说明](ebo-ai-home/README.zh-CN.md)
- [English project overview and setup](ebo-ai-home/README.md)
- [Diagnostic Agent 操作说明 / Operating guide, Chinese](ebo-ai-home/ops/diagnostics/README.zh-CN.md)
- [Dashboard：本地／云端／停止 / Runtime control, Chinese](ebo-ai-home/ops/diagnostics/HEALTH-REPORT.zh-CN.md)
- [AWS ECS/Fargate 接入 / Integration, Chinese](ebo-ai-home/ops/diagnostics/AWS.zh-CN.md)
- [公开副本与隐私 / Public snapshot and privacy](ebo-ai-home/PUBLIC_SNAPSHOT.md)

本分支业务源码恢复自完整公开版本 `878696f`；云端运行、监控与切换需要配置自己的 AWS 服务和读取／控制权限。诊断服务和 Dashboard 仍在本地运行。

Application source comes from the complete public version at `878696f`. Cloud operation and switching require your AWS services and reading/control permissions. Diagnostics and the Dashboard still run locally.

## frigate：独立的 Frigate 版，不是 main / Separate Frigate edition

分支：[`frigate`](https://github.com/YeChen-coder/EBOBotToDigitalPet/tree/frigate)。包含 Frigate/MQTT、新语音会话、身份与个人记忆，以及更新后的本地 Diagnostic Agent。**该分支新版 AWS Dashboard 尚未完成迁移或验证；这是 Frigate 版的边界。**

The `frigate` branch contains Frigate/MQTT, new voice sessions, identity and personal memory, and updated local diagnostics. **Its new AWS Dashboard migration is unfinished.** This limitation belongs to that edition, not main's existing AWS integration.

- [Frigate 中文技术介绍（7 图）](https://github.com/YeChen-coder/EBOBotToDigitalPet/blob/frigate/ebo-ai-home/docs/TECHNICAL-INTRO.zh-CN.md)
- [Frigate English overview (7 diagrams)](https://github.com/YeChen-coder/EBOBotToDigitalPet/blob/frigate/ebo-ai-home/docs/TECHNICAL-INTRO.en.md)
- [Frigate 详细文档目录 / Detailed document index](https://github.com/YeChen-coder/EBOBotToDigitalPet/blob/frigate/PROJECT_FILES%28%E6%8A%80%E6%9C%AF%E5%90%91%E6%96%87%E4%BB%B6%E7%9B%AE%E5%BD%95%29.md)
- [Frigate 版本说明与 AWS 待办 / Release and AWS work](https://github.com/YeChen-coder/EBOBotToDigitalPet/blob/frigate/ebo-ai-home/docs/RELEASE-2026-10-03.md)

## 历史深入参考 / Earlier detailed references

- [中文：架构与音视频技术详解（Word）](ebo-ai-home/docs/EBO_架构与音视频技术详解_中文版.docx)
- [English: Architecture and Media Technology (Word)](ebo-ai-home/docs/EBO_Architecture_and_Media_Technology_English.docx)

这两份旧版 Word 各含 61 页、30 幅图解与 104 条参数说明，对应 2026-09-08 的基础实现。完整版本的诊断与 AWS 演进请结合上面的 main 技术介绍、操作文档和根目录开发日记阅读。

Each earlier Word edition contains 61 pages, 30 diagrams and 104 parameter records for the base implementation reviewed on 2026-09-08. Use the main introductions, operating documentation and development journals above for subsequent diagnostics and AWS work.
