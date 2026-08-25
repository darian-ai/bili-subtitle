# CHANGELOG

## 0.2.0-alpha（候选）

- 新增只监听 `127.0.0.1` 的 FastAPI Local API、版本化 OpenAPI、生成的 TypeScript client，以及 Chrome/Edge 双构建漂移门禁。
- 新增五分钟单次配对码、扩展 Origin 绑定 Bearer、Host/CORS/Content-Type/schema/正文大小/速率/并发限制。
- 新增单 worker 持久 job、合法状态转换和服务重启恢复；失败响应使用稳定脱敏分类。
- 新增 WXT + React Manifest V3 侧栏，覆盖 BV/P/播放时间、轨道选择、主动大纲、章节跟随、按需详情、时间戳笔记、复述反馈和证据跳转。
- 优化首次生成：预算内字幕单次生成轻量大纲，长字幕才使用 Map/Reduce；新增持久阶段进度、章内证据修复和按章练习。
- 侧栏改为大纲、练习、笔记多页面导航及独立章节详情页，正文调整为 18px，并响应用户调整后的面板宽度。
- 新增 Vitest、Playwright 模拟视频页和 Chrome/Edge 构建；真实浏览器脱敏验收和待合并 CI 完成前不发布该版本。

## 0.2.0.dev1

- 新增版本化 Transcript、稳定 cue ID、EvidenceRef 与完整视频证据校验。
- 新增命名知识库、SQLite migration、生成缓存、个人 Markdown 笔记与可重建指南发布。
- 新增用户自备 OpenAI-compatible Provider 配置；API Key 仅写入 Windows Credential Manager。
- 新增完整字幕 Map/Reduce 大纲、一次结构修复、按需章节详情、usage/耗时记录和 Prompt injection 边界。
- 根据真实 Provider 验收将生成提示契约升级为 v2，使合法 JSON 的 schema/证据错误也进入一次受控修复，并确保 SQLite 连接确定性释放。
- 新增 `library`、`config provider`、`transcript`、`guide`、`chapter` 与 `note` 命令；Local API 和浏览器扩展仍未实现。

## 0.1.1

- distribution 改名为 `bili-study`，同一发行包提供新 `bili-study extract|auth` 与兼容 `bili-subtitle`。
- 采用 Apache-2.0，加入完整依赖许可证清单与离线漂移检查。
- 无效输入在凭据和网络 I/O 前校验，区分登录取消与提取取消，并在 CLI 边界脱敏未知异常。
- 增加应用层导出端口及四项 Accepted ADR；未加入 Local API、AI、知识库或插件能力。

## 2026-08-21

- 完成阶段二输入与元数据流程，支持解析 BV、av、常见 Bilibili 视频 URL 和受限 `b23.tv` 短链，并按 URL `p`、`--page` 与 `--all-pages` 规则选择有序分集。
- 引入 HTTPX 元数据适配器及视频、分集和分类错误领域模型，CLI 可输出安全、稳定的投稿与 CID 纯文本摘要。
- 新增脱敏离线 HTTP、输入解析、分集选择和 CLI 测试，总覆盖率达到 97.03%，并通过 Ruff、Pyright 与 Windows GitHub Actions `Quality` 检查。

## 2026-08-20

- 建立 `mission.md`、`tech-stack.md` 与 `roadmap.md` 项目 Constitution，明确 V1 产品边界、技术架构和阶段验收顺序。
- 搭建阶段一 Python 项目骨架，配置 uv、Hatchling、Typer CLI 与 `auth` 占位命令，并通过 pytest 覆盖率、Ruff、Pyright 和 Windows GitHub Actions 质量门禁。
- 在 feature spec 与 `roadmap.md` 中记录阶段一本地检查及 Windows CI 验证结果，并将阶段状态更新为已完成。
- 添加 `AGENTS.md` 本机代理指引和 `update-changelog` skill，规范代理使用与 changelog 维护流程。
