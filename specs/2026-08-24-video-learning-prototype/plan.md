# 阶段九：Chrome/Edge 视频学习原型实施计划

## 1. 冻结 Local API 与安全契约

- [x] 定义版本化 API、DTO、稳定错误和 OpenAPI 漂移门禁。
- [x] 锁定 loopback、配对码、Origin、Bearer、Host/CORS 和请求限制。

## 2. 实现本地服务与持久任务

- [x] 接入 `bili-study serve`、`plugin pair` 和既有学习后端端口。
- [x] 实现单 worker 持久 job、轮询、失败分类与重启恢复。

## 3. 生成 TypeScript client

- [x] 从 OpenAPI 生成类型安全 client，不维护手写重复契约。
- [x] 覆盖认证、超时、任务状态和脱敏错误映射。

## 4. 建立 Chrome/Edge 扩展骨架

- [x] 创建 WXT、TypeScript、React、Manifest V3 workspace 和双浏览器构建。
- [x] 实现配对、连接状态、SPA 导航和不支持页面提示。

## 5. 接入视频、字幕与学习大纲

- [x] 识别当前 BV、P、播放时间和字幕轨道，区分无字幕与访问失败。
- [x] 由用户主动创建指南，显示持久任务、大纲、章节跟随和按需详情。

## 6. 完成学习交互闭环

- [x] 保存结构化时间戳笔记，刷新、重启和重新生成均不覆盖个人内容。
- [x] 支持引导问题、回答/复述、证据化反馈及两秒内证据跳转。

## 7. 发布 Markdown 与原型文档

- [x] 复用可移植 Markdown 发布，保持个人内容与 AI 内容分离。
- [x] 编写服务启动、扩展配对及 Chrome/Edge 加载已解压扩展说明。

## 8. 验证与阶段关闭

- [x] 执行 [`validation.md`](./validation.md) 的 Python、Extension、E2E、安全和 V1 回归门禁。
- [ ] 完成真实 Chrome/Edge 脱敏验收后，才发布 `0.2.0-alpha` 并更新阶段状态。
