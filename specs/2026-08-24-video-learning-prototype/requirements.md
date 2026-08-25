# 阶段九：Chrome/Edge 视频学习原型需求

## 文档信息

| 项目 | 内容 |
|---|---|
| Feature | Video Learning Prototype |
| 工作分支 | `feature/video-learning-prototype` |
| 上游规格 | [`mission.md`](../mission.md)、[`tech-stack.md`](../tech-stack.md)、[`roadmap.md`](../roadmap.md) |
| 状态 | 已完成；真实 Chrome/Edge 脱敏验收与 Windows CI 均通过 |
| 日期 | 2026-08-25 |

## 目标与范围

交付用户主动控制的单视频学习侧栏：本地服务复用阶段八的知识库、字幕、AI 生成、证据和 Markdown 能力；Chrome/Edge 扩展负责页面上下文与交互，不直接持有平台或模型凭据。

- 只绑定 `127.0.0.1` 的 FastAPI/Uvicorn Local API、持久 job、OpenAPI 和生成的 TypeScript client。
- 五分钟单次配对码、扩展 Origin 绑定、Bearer token，以及 Host、Origin、CORS、内容类型、schema 和请求大小校验。
- WXT、TypeScript、React、Manifest V3 侧栏及 Chrome/Edge 构建。
- 当前 BV/P/播放时间识别、字幕轨道选择、章节跟随和证据跳转。
- 单次优先的轻量学习大纲、按需章节详情、按章练习、时间戳笔记、回答/复述和证据化反馈。
- 大纲、练习、笔记和章节详情分离的多页面侧栏、18px 正文及随浏览器侧栏宽度响应的布局。
- 可移植 Markdown、个人内容保护及服务重启后的状态恢复。

## 核心契约

- 除最小健康检查外均需有效 token；服务不得监听局域网或提供关闭认证的生产选项。
- 长任务返回 `202 + job_id`，由扩展轮询阶段进度；单 worker 串行执行平台与模型任务，生成期间允许浏览其他侧栏页面。
- 所有模型请求和生成均由用户点击触发；扩展只跟随章节，不自动暂停、弹题、上传或生成。
- 多轨道允许选择，单轨道可直接使用；无字幕、认证失败和访问失败必须明确区分。
- AI 事实、反馈和回看建议必须引用当前 Transcript revision；证据跳转误差不超过两秒。
- 首次指南只生成学习目标和内容自适应的粗粒度章节；章节数不设硬上限，短暂过场、重复和细碎事件必须合并。
- 详情和每章一至三个练习题分别按需生成；证据必须位于当前章节，首次无效输出只允许一次结构修复。
- 个人笔记绑定 BV、P 和时间戳，刷新、重启、失败及重新生成均不得覆盖。
- 扩展不保存 API Key、Cookie、二维码密钥或字幕签名 URL，也不直接访问模型、字幕接口或 Credential Manager。

## 最小接口

```text
bili-study plugin pair
bili-study serve [--port 8765]

GET  /api/v1/health
POST /api/v1/pair
GET  /api/v1/libraries
POST /api/v1/videos/inspect
POST /api/v1/study-guides
GET  /api/v1/jobs/{job_id}
GET  /api/v1/study-guides/{guide_id}
POST /api/v1/study-guides/{guide_id}/chapters/{chapter_id}/details
POST /api/v1/study-guides/{guide_id}/chapters/{chapter_id}/practice
POST /api/v1/notes
GET  /api/v1/sources/{source_id}/notes
POST /api/v1/reflections
```

OpenAPI 是扩展接口的唯一来源；生成 client 必须由 CI 检查无漂移。

## 不在范围内

- 自动安装或唤起本地服务、Native Messaging、扩展商店发布或固定扩展 ID。
- 自动暂停、自动上传、自动生成、强制答题、测验、导图、间隔复习或 Anki。
- 模型响应流式展示、并行模型请求、任务取消、固定章节数量或自动后台生成详情与练习。
- ASR、OCR、媒体下载、访问控制绕过、番剧/互动视频适配。
- Embedding、跨视频检索、批量同步、云端知识库、账号、计费或跨设备同步。

## 完成条件

- [`validation.md`](./validation.md) 的自动化、安全、恢复、双浏览器和 V1 回归门禁全部通过。
- 用户可按文档完成知识库、Provider、登录、服务启动、扩展加载与配对。
- 真实字幕和模型完成轻量大纲、按需详情、按章练习、笔记、复述反馈及证据回看闭环。
- 发布边界为 `0.2.0-alpha`，只提供仓库构建和加载已解压扩展。

以上完成条件已于 2026-08-25 全部满足；阶段十能力仍未开始。
