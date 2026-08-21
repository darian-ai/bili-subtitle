# 阶段八：学习数据与 AI 后端需求

## 文档信息

| 项目 | 内容 |
|---|---|
| Feature | Learning Data and AI Backend |
| 工作分支 | `feature/learning-data-ai-backend` |
| 上游规格 | [`mission.md`](../mission.md)、[`tech-stack.md`](../tech-stack.md)、[`roadmap.md`](../roadmap.md) |
| 状态 | 工程实现与离线验收完成；待真实 Provider 验收及合并 CI |
| 日期 | 2026-08-22 |

## 背景与目标

阶段七已经建立 V2 的兼容、许可、安全和架构基线。本阶段把现有字幕提取结果提升为可持久、可引用、可分块且可供后续学习界面复用的单视频知识来源，并使用用户自备的 OpenAI-compatible Provider 生成真实学习内容。

本阶段只交付 CLI 与应用后端能力，不交付 Local API、浏览器扩展、跨视频检索、复习系统或公开 MVP。所有生成内容必须可追溯到当前 Transcript revision 的合法 cue；个人笔记不得被重新生成覆盖。

## 范围

- 定义版本化 `TranscriptRevision`、cue、`EvidenceRef`、`StudyGuide`、章节、问题、个人笔记和复述模型。
- 创建命名知识库注册、标准库 SQLite migration、任务状态、生成记录和可重建缓存。
- 提供 Provider 非秘密配置命令；API Key 仅保存于 Windows Credential Manager。
- 实现 OpenAI-compatible Chat 适配器、超时和稳定错误分类，不记录 Key、字幕正文或远端响应秘密。
- 使用覆盖完整 cue 范围的 Map/Reduce 生成大纲，并按需生成章节详情。
- 对结构化输出执行 schema、cue 范围和证据引用校验；仅允许一次受控结构修复。
- 分离个人 Markdown 笔记与可重建 AI Markdown，提供安全、确定性的发布。
- 保持 `bili-study extract|auth` 与 `bili-subtitle` 的阶段七兼容契约。

## 核心契约

### Transcript 与证据

- 每个 revision 具有稳定 ID、来源 BV/P/轨道身份、创建时间、规范化 cue 集合、原始内容 SHA-256 和 schema version。
- cue 保留稳定序号、开始/结束时间和文本；不得为适配模型上下文而丢弃视频尾部或静默截断。
- `EvidenceRef` 必须引用当前 revision 中存在的连续 cue 范围，并可解析为确定的时间范围。
- revision 变更后，旧生成物保留来源身份但不得冒充当前有效证据；缓存键必须包含 transcript hash。

### 学习内容

- `StudyGuide` 至少包含覆盖完整视频的有序章节；章节边界与摘要必须具有合法证据。
- 章节详情按用户明确请求生成，包含总结、关键点、术语、易遗漏细节、引导问题及证据。
- 问题和反馈不得给出无法通过证据校验的事实性结论；模型输出中的指令不得改变系统安全边界。
- 同一生成指纹默认命中缓存；显式重新生成创建新生成记录，不覆盖个人笔记。

### Provider 与秘密

- Provider 配置包含名称、HTTPS base URL、chat model、输出语言、上下文预算和非秘密生成参数。
- API Key 使用独立 Credential Manager 槽位；不得进入配置、SQLite、Markdown、日志、异常或命令历史。
- 首次发送字幕前必须明确展示 Provider、模型及上传范围并要求用户确认；取消不创建远端任务。
- 超时、认证、配额、网络、结构和引用错误采用稳定分类；未知错误在 CLI 边界脱敏。

### 本地存储与发布

- 配置位于 `%APPDATA%\bili-study`，SQLite、任务和缓存位于 `%LOCALAPPDATA%\bili-study`，知识库位于用户选择的目录。
- SQLite 使用编号 migration、外键和事务；迁移前创建可验证备份，失败时保持旧数据库可恢复。
- 个人笔记使用稳定 ID、YAML frontmatter 和独立 Markdown 文件，是不可覆盖的用户资产。
- AI Markdown 可由结构化数据库记录重建；发布使用临时文件与原子替换，不留下伪成功结果。

## CLI 最小表面

实现阶段八所需的最小命令面，最终名称以现有 Typer 命令约定保持一致：

```text
bili-study library create|list|show
bili-study config provider set|show|clear
bili-study transcript import|show
bili-study guide generate|show
bili-study chapter generate
bili-study note add|list
```

命令必须支持脚本化退出码和脱敏错误。不得注册 `serve`、插件、Embedding、跨视频问答、复习、测验或导图占位命令。

## 不在范围内

- FastAPI、Uvicorn、Local API、配对码、Bearer token 和 OpenAPI client。
- Chrome/Edge 扩展、WXT、React、浏览器时间跳转和侧栏交互。
- Embedding、向量库、跨视频搜索/问答、批量收藏夹或 UP 主同步。
- 间隔复习、Anki、测验、导图、桌面端、云同步和扩展商店发布。
- 项目托管 API Key、中心化账号、计费或绕过平台访问控制。

## 完成条件

- [`validation.md`](./validation.md) 的自动化、固定响应、存储、秘密和回归门禁全部通过。
- 短字幕与超长字幕均覆盖全部 cue，所有公开证据均能映射到当前 revision。
- Provider 故障稳定分类，默认测试不访问真实网络、Credential Manager 或 Bilibili。
- 重新生成不覆盖个人笔记，缓存命中和失效可由测试证明。
- 阶段七命令、发行、许可证和 V1 全量回归继续通过。

