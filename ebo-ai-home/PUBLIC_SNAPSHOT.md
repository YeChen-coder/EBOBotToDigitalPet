# 公开副本与配置 / Public snapshot and configuration

本目录是从本机当前工作文件制作的公开项目副本，包含上传时尚未提交的源码和测试修改。远端仓库原有文件及历史保持不变。本机项目的旧 Git 历史不导入，避免把曾经提交的本机资料一并公开。

上传内容包括核心源码、定制的上游集成及许可证、测试、Docker/Compose 定义、PowerShell 脚本、Home Assistant 示例、技术说明、两份中英文 Word 和文档编写源码。

下列内容保留在本机，不属于公开副本：真实 `.env`、账号与设备密钥、`ebo-data/options.json`、Home Assistant 登录和实例存储、录音、对话转写、回复音频、数据库、运行日志、私人媒体，以及重复的文档排版检查产物。旧版手册及其家庭摄像头/账号截图也未上传；请使用本目录中的两份新 Word 文档。

## 使用自己的配置

1. 按 [README.zh-CN.md](README.zh-CN.md) 安装运行环境，从本目录运行脚本。
2. 将 `.env.example` 复制为 `.env`，只在本机填写账号、密钥、区域和主机地址。示例中的 IP 地址是占位示例。
3. Home Assistant 示例实体使用 `camera.ebo`、`button.ebo_wake` 等通用名称。根据自己的实际实体 ID 修改 `homeassistant-config` 下的仪表盘、自动化及适配器。
4. 使用旧版 LLM Vision 单帧功能时，在 `input_text.ai_vision_provider` 填写自己创建的 provider 配置项 ID；公开副本默认留空。主 Realtime 语音链路不依赖这个 ID。

`.gitignore` 用于防止今后意外加入运行数据；它不能自动检查任意源码或图片中的敏感内容，提交前仍应检查实际改动。

## 文档源码

最终 Word 可直接编辑，不需要运行生成脚本。`docs/_bilingual_build/` 保留编写源码；重新生成需要自行提供文档模板（`EBO_DOC_TEMPLATE`）、Python 依赖以及本机配置。可选渲染步骤还需要 Microsoft Word、Poppler 和文档渲染工具目录（`EBO_DOCUMENTS_SKILL_DIR`、`EBO_POPPLER_BIN`）。专有模板、工具安装和私人配置未打包。旧版生成脚本可能需要自行提供已脱敏的界面截图。

---

This is a public snapshot of the current local working files, including source and test changes that had not yet been committed locally. Existing remote files and history are preserved. Old local Git history is not imported, to avoid publishing historical private material.

Included: core source, customized upstream integrations with their licenses, tests, Docker/Compose definitions, PowerShell scripts, Home Assistant examples, technical notes, both editable Word editions and document-authoring sources.

Excluded: real `.env` files, account/device credentials, Engine options, Home Assistant authentication and instance storage, recordings, transcripts, generated reply audio, databases, logs, private media and repetitive document QA outputs. The older guide and household/account screenshots remain local; use the two new Word editions.

Copy `.env.example` to `.env` and supply your own values locally. Replace generic Home Assistant entity IDs with those in your installation. The legacy LLM Vision provider ID is intentionally blank and must be configured if that optional path is used. The main Realtime audio path does not require it.

The Word files can be edited directly. Rebuilding the bilingual documents requires your own template via `EBO_DOC_TEMPLATE`, Python dependencies and local configuration; optional rendering also needs Word, Poppler and renderer locations via `EBO_DOCUMENTS_SKILL_DIR` and `EBO_POPPLER_BIN`. Proprietary templates and installed tooling are not included. Legacy guide builders may require your own sanitized screenshots.
