# 阶段十：视频学习助手 MVP 需求

## 文档信息

| 项目 | 内容 |
|---|---|
| Feature | Learning Assistant MVP |
| 工作分支 | `feature/learning-assistant-mvp` |
| 上游规格 | [`mission.md`](../mission.md)、[`tech-stack.md`](../tech-stack.md)、[`roadmap.md`](../roadmap.md) |
| 状态 | 实施中；已确认 4/5 次独立学习记录，第 4 次被阻断且服务重启未测试 |
| 日期 | 2026-08-25 |

## 目标与进入门禁

把阶段九原型加固为公开开源、Windows 本地可安装的 `0.2.0` MVP。阶段九已经通过真实 Chrome/Edge 验收；阶段十编码前还必须完成至少五次独立的完整视频学习记录，形成问题清单，并把新发现的问题补入本文与实施计划。

五次记录不与阶段九验收混算，至少覆盖 Chrome/Edge、短/长视频、单/多 P、人工/AI 字幕和多轨道。只记录环境、耗时范围、操作结果和问题类别，不记录视频、账号或学习内容。

## 核心产品契约

### 已有内容自动恢复

- 用户打开曾经生成过内容的 BV/P 并选定知识库后，侧栏必须只查询本地服务，自动加载该 BV/P 最近生成的指南；不得要求重新检查字幕、填写 Provider 或再次调用模型。
- 普通“创建大纲”“生成详情”“生成练习”和相同回答的“获取反馈”必须先查询本地记录；只有服务明确返回无记录才允许首次生成，查询失败不得降级为生成。只有独立的“重新生成”操作可以再次调用模型并创建新版本。
- 默认加载最近生成的版本，并提供“其他版本”入口。版本可以来自不同 Provider、模型、轨道或 Transcript revision。
- 加载内容必须继续绑定生成时的 revision 和 EvidenceRef，显示保存时的字幕轨道、revision、Provider/模型和生成时间；不得把旧证据静默重绑到当前字幕。
- 用户主动检查字幕后若发现来源变化，旧版本仍可作为历史版本加载；重新生成创建新版本，不覆盖旧版本或个人内容。
- 一次 workspace 加载恢复大纲、章节详情、练习、小测尝试、总结、导图、个人笔记、作答和反馈。未提交草稿只保存在浏览器本地。

### 标签页侧栏归属

- manifest 的默认 side panel 不得形成跨标签页的全局实例。每个普通 Bilibili 视频标签页只有在用户点击扩展后才打开绑定其 `tabId` 的独立侧栏。
- 切到未打开侧栏的标签页或非普通视频页面时隐藏侧栏；返回已打开的视频标签页时恢复该标签页原实例。同标签页 Bilibili SPA 切换 BV/P 时保持侧栏打开并切换独立 workspace。
- 同一标签页导航到不支持页面时关闭并禁用侧栏；返回视频页后需要重新点击一次。侧栏没有合法 `tabId` 时不得回退查询当前活动标签页。

### 多 P 来源强绑定与字幕时间轴

- 普通同 BV 多 P 以 `video-pod` 激活项序号为 P，并与 URL 的显式 `p=N`、播放器选中序号交叉确认；站内 `video-pod` 多 BV 选集以激活项 `data-key` 的 BV 和播放器序号确认，集合序号只显示为“选集第 N 项”，不得冒充 P。当前仅支持操作当前选中视频，不包含合集批量导入或同步。
- URL、选集 DOM 与播放器状态不一致的切换瞬间标记为 `transitioning/ambiguous`，禁止检查、加载字幕或生成；内容脚本按完整身份指纹通知，不得只依赖 `location.href` 变化。
- 检查接口只发现规范 AID/BV/P、CID、分集标题和轨道；客户端准备字幕时只提交知识库、成功检查 job ID 与选定轨道描述，后端校验检查 job 的知识库/BV/P/轨道后再次解析 BV/P→AID/CID。播放器字幕请求必须同时携带 AID/BVID/CID、禁用缓存并核对响应身份；客户端不得提交 AID、CID 或标题。
- 单轨检查后自动准备字幕；多轨必须由用户明确选择并点击“加载字幕”。指南只接受已保存的 Transcript `revision_id` 与预期 BV/P，来源不匹配稳定失败且不得调用 Provider。
- workspace 同时返回该 BV/P 最近保存的 Transcript revision，并明确区分空、仅 Transcript 和已有指南；仅 Transcript 不得被误报为“已有学习内容”或阻止首次生成。已有指南保持绑定 revision，新明确加载的 revision 成为字幕页默认版本，并可切回指南绑定字幕，旧指南不被覆盖。
- 独立字幕页完整显示时间戳和 cue 文本；间隙无高亮，重叠时使用最后开始的 cue。默认跟随播放位置，手动滚动暂停，明确恢复后继续；点击 cue 只跳转起点，不暂停视频。
- 长字幕使用浏览器原生延迟渲染优化，但保留完整列表语义、键盘操作和可访问名称。旧 revision 缺少来源证明时标记 `legacy_unverified` 并显示警告；只有 BV/P/CID/内容哈希完全一致时才能原位升级验证来源，不删除、不重绑或改写历史内容。
- 检查、字幕准备、workspace 与生成结果均绑定启动时的 `tabId + library + BV/P` owner；所有任务结果携带 BV/P/revision，应用前再次核对，迟到结果只能写回原作用域。
- 创建或重新生成前必须显示 P、分集标题、轨道、revision 和 Provider 的确认面板；确认前不得调用模型。取消、失败和重新生成期间继续显示旧指南，只有来源匹配的新指南成功后才切换。

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
GET  /api/v1/videos/{bvid}/pages/{page}/workspace?library=...
POST /api/v1/videos/inspect
POST /api/v1/videos/{bvid}/pages/{page}/transcripts
GET  /api/v1/transcripts/{revision_id}?library=...
POST /api/v1/study-guides
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
- 新增 `VideoWorkspaceLookup`、`StoredGuideSummary`、`StudyWorkspace`、`ReflectionAttempt`、`QuizAttempt`、`StudySummary`、`MindMapTree`、`GenerationUsage` 和 `CacheInventory` DTO/领域模型。
- job 状态扩展为 `queued|running|cancel_requested|cancelled|succeeded|failed|interrupted`。
- SQLite schema 升级到 v4，规范化保存 BV/P 来源键、指南生成元数据、测验尝试、总结、导图、usage、重试关系和取消状态；旧 v3 数据前向迁移并保留备份。
- `bili-study config provider set` 新增可选 `--input-price-per-million`、`--output-price-per-million` 和 `--currency`；旧配置继续可读。
- `VideoContext` 携带 `identity_state`、`identity_evidence` 及可选集合序号；Transcript 携带 `source_verification`、`page_identity_source` 与 `inspection_job_id`，字幕页展示 BV/P/CID/inspect 来源链。来源冲突稳定返回 `video_identity_ambiguous`、`page_identity_unresolved` 或 `inspection_source_mismatch`。

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

## 已冻结问题清单

| 编号 | 级别 | 问题 | 处置状态 |
|---|---|---|---|
| P10-001 | 阻断 | 平台字幕轨道数字 ID 轮换后，生成大纲要求手动重选轨道 | 已实现“原 ID 优先、稳定描述唯一回退、多候选强制重选”；待真实复验 |
| P10-002 | 阻断 | P1 检查期间切换 P2，P1 迟到结果污染 P2；后端同时信任客户端 CID/标题，无法形成强来源边界 | 第 4 次记录重新打开；已改为 owner 作用域回写、服务端重解析 BV/P 和 revision 生成门禁，自动化通过，真实复验待执行 |
| P10-003 | 阻断 | 证据反馈缺少明确输出 schema，修复后仍可能格式无效 | 已补齐反馈 schema、问题证据边界校验和失败作答持久化；待真实复验 |
| P10-004 | 阻断 | 默认全局 side panel 导致未点击标签页和非 Bilibili 页面仍显示侧栏 | 已改为仅受支持视频标签页启用的 tab-specific panel；自动化通过，Chrome/Edge 真实复验待执行 |
| P10-005 | 阻断 | 长任务缺少停止与显式重试，服务重启可能重复发送计费请求 | 已实现取消状态机、重启中断与 `retry_of`；自动化已覆盖核心状态，真实在途 Provider/重启复验待执行 |
| P10-006 | 阻断 | 只有 Transcript、从未生成指南的 workspace 被误判为已有学习内容，首次创建被短路 | 已区分 Transcript-only 与 guide-ready；创建仅在确有 guide 时复用，自动化通过，待真实复验 |
