# bili-study：技术栈与工程约束

## 文档信息

| 项目 | 内容 |
|---|---|
| 文档性质 | 项目 Constitution：技术选择、目标架构和工程约束的唯一权威来源 |
| 当前状态 | 阶段九 Local API 与 Chrome/Edge 扩展已完成验收；阶段十学习助手 MVP 实施中 |
| 最后更新 | 2026-08-25 |

> 产品行为以 [`mission.md`](./mission.md) 为准。表中“计划采用”表示已经完成技术决策但尚无可交付实现，不得据此声称对应功能可用。

## 一、技术目标

技术方案按以下优先级演进：

1. 保持 V1 字幕提取、登录、导出和安全边界稳定，不因 V2 发生回归。
2. 在 Windows 上以一个本地 Python 服务复用字幕、模型、存储和安全能力。
3. 浏览器扩展保持薄前端，不接触 Bilibili Cookie、模型 API Key 或字幕签名 URL。
4. 所有 AI 结论都能引用稳定字幕 cue 与时间戳，并能在本地验证。
5. 个人笔记与可重建生成物分离，任何重试、升级和重建不得破坏用户内容。
6. 长字幕完整分块处理，任务可缓存、可恢复、可诊断，不依赖单次长连接。
7. 默认自动化测试不联网、不读取真实凭据、不调用真实模型。
8. 新依赖按阶段引入；未进入当前阶段的数据库、向量或 UI 能力不得提前混入运行时。

## 二、技术选择与实现状态

| 领域 | 选择 | 状态 | 用途与约束 |
|---|---|---|---|
| Python | Python 3.12+ | 已实现 | 字幕核心、本地应用、服务和存储 |
| 项目管理 | uv | 已实现 | 环境、依赖、运行、构建和工具安装 |
| Python 构建 | Hatchling，`src/` 布局 | 已实现 | 继续发布标准 wheel/sdist |
| 现有 CLI | Typer | 已实现 | `bili-subtitle`、认证和参数校验 |
| 新 CLI | Typer，新增 `bili-study` 入口 | 已实现并扩展 | 已提供 `extract/auth/library/config/transcript/guide/chapter/note/plugin/serve` |
| Bilibili HTTP | HTTPX 同步 Client | 已实现 | 单会话、固定超时、手动安全重定向和测试替身 |
| 凭据 | keyring / Windows Credential Manager | 已实现并扩展 | 现有 Cookie 继续复用；模型 Key 使用独立服务槽位 |
| 字幕与文件 | dataclasses、Decimal、JSON、pathlib、原子写入 | 已实现 | 原始 JSON、忠实 SRT、manifest 和 Windows 路径安全 |
| 本地 API | FastAPI、Pydantic、Uvicorn | 已实现 | 只绑定 loopback，提供版本化 JSON/OpenAPI 接口 |
| 本地状态 | 标准库 SQLite | 阶段八已实现 | 库注册、Transcript、任务、缓存、个人内容索引和 schema migration；FTS 后续实现 |
| 云端模型 | OpenAI-compatible Chat Completions | 阶段八已完成 | 用户自备 HTTPS URL、模型与 Credential Manager Key；适配器与领域隔离 |
| 向量检索 | SQLite FTS5 + 可替换向量端口 | 后续计划 | 首个实现计划锁定 `sqlite-vec`，不属于插件原型 |
| 扩展框架 | WXT、TypeScript、React、Manifest V3 | 已实现 | Chrome/Edge 侧栏、内容脚本、后台脚本和构建 |
| JavaScript 工具 | Node.js 24、npm lockfile | 已实现 | `npm ci` 提供可重现依赖和 CI |
| Python 测试 | pytest、respx、pytest-cov | 已实现并扩展 | 保持不低于 90% 的分支覆盖率 |
| Python 质量 | Ruff、strict Pyright | 已实现并扩展 | 新 Python 代码继续遵守现有门禁 |
| 扩展测试 | Vitest、Playwright | 已实现 | 状态/组件单测与模拟视频页端到端测试 |
| Markdown | 标准 Markdown、YAML frontmatter、双链、Mermaid | 部分实现 | 已实现生成/个人 Markdown 分离和原子发布；Mermaid 属后续阶段 |

## 三、目标架构

```text
交互层
  ├── bili-subtitle 兼容 CLI（已实现）
  ├── bili-study CLI（`extract|auth` 已实现，学习命令计划）
  ├── loopback Local API（已实现）
  └── Chrome/Edge Side Panel（已实现）
          ↓
应用编排层
  ├── 现有输入、认证和字幕提取流程
  ├── Transcript 构建与 revision 管理
  ├── 学习指南、章节详情和复述反馈任务
  ├── 个人笔记与 Markdown 发布
  └── 库、缓存、任务与恢复
          ↓
领域层
  ├── 视频、分集、字幕轨道与 cue
  ├── TranscriptRevision 与 EvidenceRef
  ├── StudyGuide、ChapterDetail 与 GuidingQuestion
  └── PersonalNote、Reflection 与结构化结果
          ↓
基础设施层
  ├── Bilibili HTTP / Credential Manager（已实现）
  ├── OpenAI-compatible 模型适配器
  ├── SQLite repository 与 migration
  ├── 本地任务 worker 与缓存
  └── JSON/SRT/manifest/Markdown 安全发布
```

### 依赖方向

- 领域层只依赖标准库，不导入 Typer、FastAPI、Pydantic、HTTPX、keyring、SQLite 扩展、WXT 或 React。
- 应用层依赖 Protocol 定义的字幕、模型、repository、时钟、任务和导出端口。
- CLI、本地 API 和扩展是同级入口，不互相承载业务规则。
- FastAPI/Pydantic DTO 必须在 API 边界映射为领域模型，不把 Pydantic 模型传播到领域层。
- 扩展通过生成的 TypeScript API 类型调用本地服务，不复制 Python 业务校验。
- 现有字幕适配器继续独占平台接口与签名 URL；扩展不得自行抓字幕或读取网页 Cookie。

### 包与目录演进

- `src/bili_subtitle/` 继续承载已完成的字幕核心和兼容入口。
- V2 新应用编排放入 `src/bili_study/`，通过稳定端口复用字幕核心，不复制实现。
- `extension/` 作为独立 npm workspace 保存 WXT 扩展，不把 Node 依赖加入 Python wheel。
- 同一发行构建已暴露 `bili-study` 和兼容 `bili-subtitle` 两个控制台入口，并通过旧 distribution 卸载迁移与隔离安装验证。

## 四、V2 核心数据契约

### Transcript revision

`TranscriptRevision` 至少包含：

- 不可变 revision ID 和 schema version。
- BVID、aid、P 序号、CID、标题和规范视频 URL。
- 字幕轨道的当前平台 ID、语言、显示名称和人工/AI 类型。
- 原始字幕 SHA-256 和有序 cue 集合。
- 每个 cue 的稳定局部 ID、开始/结束毫秒和原文。

平台字幕轨道数值 ID 可能轮换，不能单独充当长期身份。引用必须同时携带 revision ID 与 cue ID；字幕内容变化后生成新 revision，不在旧 revision 上原地改写引用。

### 学习数据

- `StudyGuide`：来源 revision、输出语言、生成指纹、学习目标和有序章节。
- `Chapter`：稳定章节 ID、标题、起止时间和引导问题；大纲阶段不包含直接答案。
- `ChapterDetail`：总结、关键点、术语、易遗漏细节和 `EvidenceRef`。
- `GuidingQuestion`：问题、用于本地校验但初始隐藏的证据引用。
- `PersonalNote`：稳定 ID、来源、时间戳、类型、Markdown 正文和创建/更新时间。
- `Reflection`：问题、用户回答或复述、已覆盖/遗漏/可能误解及证据。

所有公开 JSON 和持久文档携带 schema version。迁移必须前向执行并有备份/回滚边界；可重建缓存允许删除重建，个人笔记不得依赖破坏性数据库迁移才能读取。

## 五、AI 生成与证据策略

### Provider 配置

- 首个 Provider 使用可配置的 HTTPS base URL、chat model、输出语言和上下文预算。
- `bili-study config provider set` 通过隐藏输入读取 API Key；Key 只写 Credential Manager。
- 非秘密配置原子写入 `%APPDATA%\bili-study\config.json`。
- 优先使用兼容接口提供的 JSON Schema/JSON mode；能力不足时使用 JSON 提示与本地严格解析。
- Provider 特有字段只存在于适配器层，领域和应用流程不绑定具体厂商。

### 两阶段生成

1. 规范化字幕按完整 cue 边界分块；默认每块最多 12,000 个 Unicode 字符或 8 分钟内容，以先达到者为准，相邻块只重叠一个完整 cue。
2. Map 阶段只返回候选章节、目标、引导问题和 cue 引用。
3. Reduce 阶段合并重叠章节并形成覆盖完整时间范围的有序大纲。
4. 用户展开章节后，详情任务只读取该章节及相邻边界 cue，生成详细学习内容。
5. 用户提交回答或复述后，反馈任务只读取问题对应证据和必要上下文。
6. 结构解析或引用校验失败最多允许一次修复请求；仍失败则保留任务失败状态，不渲染未验证内容。

不得为适配模型上下文直接截断视频尾部。模型返回的 cue ID、时间范围、章节顺序和来源必须在应用层验证。

### 缓存与成本

- 缓存键由 Transcript SHA-256、Provider、模型、输出语言、schema/prompt version 和生成参数组成，不包含 Key 或字幕正文。
- 相同生成指纹默认复用结果；显式重新生成创建新结果，不覆盖个人内容。
- 记录请求数量、Provider 返回的 token usage、耗时和缓存命中；未返回 usage 时只标记未知，不自行伪造精确费用。
- 后续 Embedding 单独配置模型和缓存；首个插件原型不得提前要求向量依赖。

### Prompt injection 边界

- 字幕、标题、个人笔记和模型历史输出全部视为不可信数据。
- 系统提示明确禁止执行字幕中的指令，不为模型提供网络、文件或系统工具。
- 结构化输出经过 schema、枚举、长度、cue 引用和时间范围校验后才能进入持久层。
- 不把简单转义或字符串替换当作唯一防护。

## 六、本地服务与浏览器扩展

### Local API

- 服务固定绑定 `127.0.0.1`，默认端口 `8765`；允许用户改端口，不允许通过公开参数绑定局域网地址。
- 除最小健康检查外，API 需要配对后的 Bearer token。
- `bili-study plugin pair` 生成五分钟有效、单次使用的配对码；配对记录绑定扩展 Origin。
- 校验 Host、Origin、Authorization、Content-Type、请求大小和 schema；禁止通配 CORS。
- 长字幕和模型生成使用持久 job；API 返回 `202 + job_id`，扩展轮询状态，不依赖浏览器保持长连接。
- 首期使用单 worker 串行执行 Bilibili 与模型任务，避免平台压力和并发写入冲突。
- OpenAPI 是扩展接口的唯一来源；生成 TypeScript 类型后由 CI 检查无漂移。

计划公开的 V2 API：

```text
GET  /api/v1/health
POST /api/v1/pair
GET  /api/v1/libraries
POST /api/v1/videos/inspect
POST /api/v1/study-guides
GET  /api/v1/jobs/{job_id}
GET  /api/v1/study-guides/{guide_id}
POST /api/v1/study-guides/{guide_id}/chapters/{chapter_id}/details
POST /api/v1/notes
GET  /api/v1/sources/{source_id}/notes
POST /api/v1/reflections
```

### 扩展职责

- 使用 Manifest V3、WXT、TypeScript 和 React，首期只构建 Chrome/Edge 侧栏。
- Content script 只读取受支持视频页的 URL、当前 P、HTML video 当前时间和播放跳转能力。
- Side panel 显示连接/认证/任务状态、轨道选择、学习大纲、章节详情、引导问题、个人笔记和复述反馈。
- 默认全局 panel 在运行时禁用；后台只为普通 Bilibili 视频配置带 `tabId` 的 panel，应用状态按 `tabId + library + BV/P` 隔离并以本地 workspace 为恢复真源。
- Background/service worker 负责本地 API 通信和页面上下文转发，不保存模型或 Bilibili 凭据。
- Bilibili SPA 导航后重新识别上下文；页面不受支持时清楚禁用学习操作。
- 默认只跟随高亮当前章节，不自动暂停、不主动弹题、不在用户点击前发起模型请求。

## 七、本地存储与 Markdown

### 应用状态

- `%APPDATA%\bili-study\config.json`：非秘密配置和已注册知识库路径。
- `%LOCALAPPDATA%\bili-study\`：SQLite、Transcript、任务、生成缓存和可重建索引。
- Windows Credential Manager：Bilibili 会话和按 Provider 区分的模型 API Key。
- 知识库目录：用户可阅读的生成 Markdown 与个人 Markdown 笔记。

SQLite 使用编号 migration、外键和事务。迁移前创建可验证备份；任务与缓存表可以重建，个人 Markdown 不以 SQLite 作为唯一副本。

### 知识库目录

```text
知识库/
├── generated/
│   └── videos/
├── notes/
├── reviews/
└── .bili-study.json
```

- `.bili-study.json` 只保存 schema version、库 UUID 和非秘密元数据。
- `generated/` 中的 AI 内容带来源 revision、生成指纹和“可重建”标记。
- `notes/` 中个人笔记使用独立文件、稳定 ID、YAML frontmatter 和 Markdown 正文。
- 重新生成、`--force`、模型切换和索引重建只影响可重建内容。
- 所有路径继续使用 V1 的 Windows 文件名净化、长度预算和同目录原子发布策略。

## 八、网络、可靠性与隐私

- Bilibili 请求继续使用同一个同步 HTTPX Client、登录会话和安全重定向规则。
- 模型请求使用独立 HTTPX Client、明确连接/读取/总超时和稳定错误分类。
- 只对限流、连接中断和明确服务端瞬时失败做有界退避；认证、配额、结构和内容校验失败不盲目重试。
- 用户首次云端生成前显示 Provider、模型和将上传字幕的说明；取消时不创建模型任务。
- 插件、本地 API、日志和异常不回显完整远端响应、Prompt、字幕正文、个人笔记或凭据。
- Local API 不开放局域网监听，不提供关闭认证的生产选项。
- 服务中断后恢复持久任务状态；不能确认是否完成的外部请求标记为可重试失败，不自动重复收费请求。

## 九、测试与质量门禁

### Python

- 保持现有 208 项 V1 回归及不低于 90% 的分支覆盖率。
- 新增 Transcript/revision、引用、分块、缓存、migration、个人笔记保护和模型结构校验测试。
- 使用 respx 固定 OpenAI-compatible 响应；默认 socket 封锁继续覆盖 Bilibili 和模型域名。
- FastAPI 测试覆盖配对过期、token、Origin/CORS、请求限制、job 生命周期、重启恢复和错误脱敏。
- strict Pyright、Ruff lint、Ruff format 和 `git diff --check` 继续作为门禁。

### Extension

- Vitest 覆盖状态机、API client、章节跟随、笔记状态和安全渲染。
- Playwright 使用本地模拟视频页和假 Local API 覆盖配对、SPA 导航、当前时间、点击跳转和服务断开。
- Node.js 24 与 npm lockfile 进入 Windows CI；执行 `npm ci`、lint、typecheck、unit、e2e 和 Chrome/Edge 构建。
- 扩展不得依赖真实 Bilibili 页面完成默认 CI。

### AI 评测

- 使用历史、科学和通用知识等脱敏字幕固定集，不保存真实账号或投稿数据。
- 机器断言覆盖 cue 引用存在、时间范围合法、完整视频覆盖、初始问题不含答案和无证据拒答。
- Prompt injection 固定集证明字幕无法改变系统规则。
- 模型文字质量采用人工 rubric 验收，不使用不可维护的逐字 golden 输出。

### 真实人工验收

- 在 Chrome 与 Edge 验证短视频、长视频、多 P、人工字幕、AI 字幕、多轨道和无字幕。
- 验证服务启动、配对、模型配置、生成、按需详情、笔记恢复、复述反馈和时间戳跳转。
- 人工记录只保留环境、命令形态、耗时范围和通过/失败结论，不记录标题、BV、账号、字幕、笔记、Prompt 或 Key。

## 十、交付与兼容

- V1 继续通过 uv 构建、wheel/sdist 校验和隔离 `uv tool install` 验证。
- V2 Python 发行必须同时安装 `bili-study` 与兼容 `bili-subtitle` 命令。
- 首个扩展原型只提供仓库内构建产物和 Chrome/Edge“加载已解压扩展”说明。
- 扩展商店发布前必须另行完成固定扩展 ID、权限最小化、隐私说明、升级迁移和安全审计。
- 项目已采用 Apache-2.0；许可证文件、包元数据、40 项锁定依赖审计和离线漂移门禁已完成。
- 首期不构建独立 EXE，不运营中心化服务，不要求 FFmpeg。

## 十一、禁止或延后采用

- 不把 yutto、BBDown、yt-dlp、FFmpeg、ASR 或 OCR 作为运行时依赖。
- 不在扩展中保存 API Key、Cookie、二维码密钥或字幕签名 URL。
- 不让扩展直接调用 Bilibili 字幕接口或模型 API。
- 不允许模型自动调用网络、文件、Shell 或浏览器工具。
- 不默认自动暂停、上传、生成、索引或答题。
- 首个插件原型不引入向量数据库、知识图谱、消息队列、云端账号或跨设备同步。
- 后续 `sqlite-vec` 仍处于 pre-v1 时必须锁定版本并通过抽象端口隔离；索引随时可删除重建。
- 不复制不兼容许可证项目的实现代码；新增依赖必须通过许可证与归档审计。

## 十二、变更记录

| 日期 | 变更 |
|---|---|
| 2026-08-25 | 阶段九完成技术验收：Local API、OpenAPI/client、持久 job、WXT/React 双浏览器构建、真实 Chrome/Edge 脱敏闭环及 Windows CI 全部通过。 |
| 2026-08-24 | 阶段九工程接入 FastAPI/Uvicorn loopback 服务、Pydantic/OpenAPI、SQLite job、生成 TypeScript client，以及 WXT/React Chrome/Edge 双构建；真实浏览器验收与 CI 待完成。 |
| 2026-08-24 | 阶段八技术验收完成：OpenAI-compatible DeepSeek 合成短/长字幕真实调用验证 Map/Reduce、完整证据覆盖和 usage；提示契约升级为 v2，SQLite 连接确定性释放，最终 Windows CI 全绿。 |
| 2026-08-22 | 阶段八工程、离线门禁与 Windows CI 完成：版本化学习领域、SQLite migration/任务/缓存、Provider/Key、证据化两阶段生成和 Markdown 发布接入 `0.2.0.dev1`；真实 Provider 待验收。 |
| 2026-08-22 | 阶段七技术基线完成：双 CLI、导出端口、异常边界、Apache-2.0、依赖审计、归档和隔离迁移门禁已实现；阶段八/九组件仍为计划采用。 |
| 2026-08-21 | 批准 V2 目标架构：`bili-study` CLI、FastAPI loopback 服务、WXT/React Chrome/Edge 侧栏、OpenAI-compatible 模型、版本化 Transcript/证据、SQLite 状态和可移植 Markdown；新增技术均标记为计划采用。 |
| 2026-08-20 | 固化 V1 字幕提取技术栈、架构边界、安全策略、测试方案与交付方式。 |
