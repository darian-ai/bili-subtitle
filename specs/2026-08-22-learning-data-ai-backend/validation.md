# 阶段八：学习数据与 AI 后端验证及合并标准

## 自动化质量门禁

在仓库根目录运行项目当前锁定的同步、测试、覆盖率、Ruff、格式、strict Pyright、构建、归档和隔离安装命令。全部命令必须返回 `0`，分支覆盖率不得低于仓库既有 90% 门槛，`git diff --check` 必须通过。

默认测试必须封锁外网，不读取真实 Credential Manager、Bilibili 凭据、API Key、字幕或个人知识库；所有 Provider 与平台交互使用固定响应或内存替身。待合并提交的 Windows GitHub Actions 必须执行等价门禁并成功。

## Transcript 与证据矩阵

| 场景 | 期望结果 |
|---|---|
| 短字幕 | 单个或少量分块覆盖首尾全部 cue |
| 超长字幕 | Map/Reduce 覆盖全部分块和视频尾部，不静默截断 |
| revision 内容变化 | 产生新 hash/revision，旧缓存不命中 |
| 合法 EvidenceRef | 精确解析到当前 revision 的 cue 与时间范围 |
| 越界、倒序或跨 revision 引用 | 校验失败，不发布对应生成内容 |
| 空、重叠或异常 cue | 按领域规则明确拒绝或规范化，不产生模糊证据 |

使用首 cue、末 cue、相邻边界、Unicode 和极长单 cue 固定夹具证明序列化往返稳定，且生成内容中的每个引用均可解析。

## Provider 与生成矩阵

- 固定响应覆盖成功、认证失败、配额限制、超时、连接失败、非 JSON、schema 错误、引用错误、超大响应和未知异常。
- 结构或引用失败最多进行一次受控修复；修复仍失败时返回稳定错误，不发布半有效指南。
- 首次远端生成显示 Provider、模型及上传字幕说明；用户取消后无 HTTP 请求、无任务和无缓存记录。
- 同一 Transcript、Provider、模型、语言、prompt/schema version 和参数命中缓存；任一指纹字段变化均失效。
- 字幕中的伪系统指令、URL 或秘密诱导只作为内容处理，不能改变工具、文件、网络或输出约束。
- usage 存在时准确记录；不存在时标记未知，不推测精确 token 或费用。

## 存储、迁移与恢复

- 新知识库创建、重名、无权限目录、非法/过长路径和注册表损坏具有明确结果。
- migration 从每个受支持旧 schema 前滚成功；备份可验证，迁移失败时原库保持可恢复。
- 外键、事务和任务状态转换由测试保护；进程中断后任务可识别为可恢复或失败，不伪装完成。
- Transcript 和生成缓存可重建；个人笔记删除或覆盖不属于自动恢复/清理操作。
- 数据库、配置和 Markdown 均不包含 API Key、Cookie、二维码密钥或字幕签名 URL。

## Markdown 与个人内容

- 个人笔记具有稳定 ID、有效 YAML frontmatter、UTF-8 Markdown 和来源时间戳。
- 重新生成指南、切换模型、清理缓存或更新 Transcript 均不得修改或删除个人笔记。
- 生成 Markdown 可由结构化记录逐字节重建；重复发布确定，发布失败保留旧文件并清理临时文件。
- 文件名净化、保留名、大小写冲突、路径预算和原子替换继续符合 Windows 策略。
- 输出只使用标准 Markdown、frontmatter、双链和时间戳链接，不要求 Obsidian 专用插件。

## CLI 与错误边界

- 每个阶段八命令覆盖成功、用户输入错误、预期端口故障、Ctrl+C 和未知异常；退出码、stdout/stderr 和无 traceback 契约稳定。
- CLI 只组合端口和渲染结果；领域/应用层不得依赖 Typer、HTTPX、keyring 或具体 SQLite/文件系统适配器。
- 未注册的 `serve`、插件、Embedding、复习、测验和跨视频命令返回参数错误，不显示伪成功占位。
- `bili-study extract|auth` 与 `bili-subtitle` 的帮助、固定响应行为、输出字节和 `0|1|2` 退出码继续通过阶段七等价矩阵。

## 秘密与隐私审计

用唯一 API Key、Cookie、签名 URL、远端响应正文和字幕文本金丝雀扫描 stdout、stderr、异常、日志、配置、SQLite、Markdown、缓存键、测试快照和发行归档。秘密不得出现；字幕正文仅可存在于明确的本地 Transcript/用户批准的生成输入，不得进入日志或缓存键。

真实 Provider 验收只记录脱敏的 Provider 类型、模型、测试场景、结果、usage 是否可用和时间，不提交 Key、请求/响应正文、真实字幕或个人笔记。

## 范围与依赖审计

- 新依赖必须符合 Tech Stack、Apache-2.0 兼容政策并同步更新锁文件和许可证清单。
- 不得引入 FastAPI、Uvicorn、浏览器扩展、WXT、React、向量库、Embedding SDK、媒体下载、ASR、OCR 或访问控制绕过能力。
- 阶段七 ADR、发行元数据、双入口、归档内容和隔离安装门禁继续通过。
- README/CHANGELOG 只描述真实可用的阶段八 CLI 后端，不声称 Local API、浏览器插件或 MVP 已完成。

## 可合并与阶段完成条件

- [`requirements.md`](./requirements.md) 的全部契约具有实现、自动化测试或审计证据。
- [`plan.md`](./plan.md) 的八组任务全部完成，工作区不存在无关改动。
- 全量 V1/阶段七回归、Transcript/证据、Provider、缓存、迁移、Markdown、秘密、构建和安装门禁全部通过。
- 至少完成一次脱敏真实 OpenAI-compatible Provider 的短字幕与超长字幕验收，并证明视频尾部及证据引用有效。
- 待合并提交的 Windows CI 成功，记录提交哈希和 CI 链接。
- 仅在以上条件全部满足后更新三份 Constitution 并把阶段八标记为已完成；该结论不表示阶段九 Local API 或浏览器原型已经开始。
