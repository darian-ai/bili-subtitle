# 阶段十：视频学习助手 MVP 需求

## 文档信息

| 项目 | 内容 |
|---|---|
| Feature | Learning Assistant MVP |
| 工作分支 | `feature/learning-assistant-mvp` |
| 上游规格 | [`mission.md`](../mission.md)、[`tech-stack.md`](../tech-stack.md)、[`roadmap.md`](../roadmap.md) |
| 状态 | 需求已冻结；五次独立学习记录待完成，工程尚未开始 |
| 日期 | 2026-08-25 |

## 目标与进入门禁

把阶段九原型加固为公开开源、Windows 本地可安装的 `0.2.0` MVP。阶段九已经通过真实 Chrome/Edge 验收；阶段十编码前还必须完成至少五次独立的完整视频学习记录，形成问题清单，并把新发现的问题补入本文与实施计划。

五次记录不与阶段九验收混算，至少覆盖 Chrome/Edge、短/长视频、单/多 P、人工/AI 字幕和多轨道。只记录环境、耗时范围、操作结果和问题类别，不记录视频、账号或学习内容。

## 核心产品契约

### 已有内容自动恢复

- 用户打开曾经生成过内容的 BV/P 并选定知识库后，侧栏必须只查询本地服务，自动加载该 BV/P 最近生成的指南；不得要求重新检查字幕、填写 Provider 或再次调用模型。
- 默认加载最近生成的版本，并提供“其他版本”入口。版本可以来自不同 Provider、模型、轨道或 Transcript revision。
- 加载内容必须继续绑定生成时的 revision 和 EvidenceRef，显示保存时的字幕轨道、revision、Provider/模型和生成时间；不得把旧证据静默重绑到当前字幕。
- 用户主动检查字幕后若发现来源变化，旧版本仍可作为历史版本加载；重新生成创建新版本，不覆盖旧版本或个人内容。
- 一次 workspace 加载恢复大纲、章节详情、练习、小测尝试、总结、导图、个人笔记、作答和反馈。未提交草稿只保存在浏览器本地。

### 任务取消、恢复与重试

- 排队任务立即取消；运行任务进入 `cancel_requested`，只在分块、模型调用和持久化之间的安全边界停止。
- 已发出的同步 Provider 请求不宣称能撤回；界面显示“取消中”，响应返回后丢弃结果，不持久化、不自动重试，也不承诺未产生费用。
- 服务重启后，未开始的排队任务继续；原先运行中的任务转为可显式重试的 `interrupted`，不得自动重复可能计费的请求。
- 只有失败、中断或取消任务可以显式重试；重试创建新 job，并保留 `retry_of` 关系、原任务和稳定错误分类。

### 用量、成本与缓存

- 每个生成任务记录请求数、Provider 返回的 input/output/total token、耗时和缓存命中。Provider 未返回的字段保持未知。
- Provider 非秘密配置可选保存输入/输出每百万 token 单价和三位大写币种；两项单价必须同时存在并使用非负 Decimal。
- 只有 usage 和价格完整时才计算并显示“估算成本”；不内置或联网维护模型价格表，不把估算写成账单。
- 首次生成前继续提示 Provider、模型和上传字幕；若价格未知，明确提示无法估算费用。
- 缓存状态显示项目数、可重建生成物数和可回收大小。默认 prune 只删除过期/孤立请求缓存；按视频或 Provider 删除可重建生成物必须预览范围并二次确认。
- 缓存操作永不删除 Transcript、原始字幕、个人笔记、用户作答、复述或测验尝试。

### 主动回忆小测

- 复用阶段九按章练习和 EvidenceRef，不建立第二套无证据 Prompt。
- 题目、答案依据和证据在用户提交或明确跳过前隐藏；不得通过时间跳转按钮提前泄露答案。
- 保存用户原始作答、提交时间和证据化定性反馈，刷新、重新配对、服务重启及模型切换后仍可恢复。
- MVP 不提供数字分数、置信度、错题队列、间隔复习或 Anki；这些属于阶段十一。

### 学习总结与基础导图

- 总结由用户主动生成，只读取 Transcript 和通过验证的 AI 生成物，完全不读取或上传个人笔记、作答、复述和测验尝试。
- 总结包含学习目标、章节结论、关键概念与联系、仍无法从字幕判断的事项；所有事实携带合法 EvidenceRef。
- 导图模型输出为受限树结构；每个事实节点携带 EvidenceRef，并限制深度、节点数和标签长度。
- Mermaid 源码由本地代码从验证后的树确定性生成，模型不得直接返回可执行 Mermaid。侧栏使用严格安全模式渲染，Markdown 保存同一 Mermaid mindmap 源码。

### 体验、文档与发布

- 长视频下可快速返回当前章节，任务运行时可浏览已有内容；错误信息提供取消、重试、重新连接或查看旧版本的明确入口。
- 支持键盘操作、可见焦点、正确标题层级、ARIA live、足够对比度、减少动画偏好及窄/宽侧栏无横向溢出。
- 补齐安装、升级、SQLite migration/回滚、隐私、故障排查、Provider 兼容和缓存管理文档。
- Python wheel/sdist 同时安装 `bili-study` 与 `bili-subtitle`；Chrome/Edge 从同一锁文件产生可复现归档并附哈希。
- 发布边界是 `0.2.0` 本地安装 MVP；不进入扩展商店，不加入 Native Messaging、独立 EXE 或中心化服务。

## 公共接口与数据类型

```text
GET  /api/v1/videos/{bvid}/pages/{page}/study-guides?library=...
GET  /api/v1/study-guides/{guide_id}/workspace?library=...
POST /api/v1/jobs/{job_id}/cancel
POST /api/v1/jobs/{job_id}/retry
POST /api/v1/quiz-attempts
GET  /api/v1/study-guides/{guide_id}/quiz-attempts?library=...
POST /api/v1/study-guides/{guide_id}/summary
POST /api/v1/study-guides/{guide_id}/mindmap
GET  /api/v1/cache?library=...
POST /api/v1/cache/prune
POST /api/v1/cache/clear
```

- 长操作继续返回 `202 + job_id`；OpenAPI 是扩展唯一接口来源。
- 新增 `StoredGuideSummary`、`StudyWorkspace`、`QuizAttempt`、`StudySummary`、`MindMapTree`、`GenerationUsage` 和 `CacheInventory` DTO/领域模型。
- job 状态扩展为 `queued|running|cancel_requested|cancelled|succeeded|failed|interrupted`。
- SQLite schema 升级到 v4，规范化保存 BV/P 来源键、指南生成元数据、测验尝试、总结、导图、usage、重试关系和取消状态；旧 v3 数据前向迁移并保留备份。
- `bili-study config provider set` 新增可选 `--input-price-per-million`、`--output-price-per-million` 和 `--currency`；旧配置继续可读。

## 明确不在范围内

- 自动暂停、强制答题、数字评分、错题本、间隔复习、Anki 和阶段十一复习队列。
- Embedding、跨视频检索、知识图谱、批量同步和阶段十二知识库能力。
- 个人笔记或作答参与总结、默认自动生成、模型流式响应、并行模型请求。
- 扩展商店、固定扩展 ID、Native Messaging、桌面 GUI、独立 EXE、云端账号或同步。

## 完成条件

- 五次独立学习记录形成的问题全部修复或登记为有理由的已知限制。
- [`validation.md`](./validation.md) 的迁移、恢复、任务、成本、缓存、证据、安全、双浏览器和发行门禁全部通过。
- 已生成视频重新打开时自动恢复完整状态，自动化证明模型请求数为零。
- Python 与 Extension CI、许可证、安全扫描、隔离安装和可复现归档通过后，才发布 `0.2.0` 并更新 Constitution。
