# 阶段十：视频学习助手 MVP 实施计划

## 1. 完成五次独立学习记录并冻结问题清单（进行中：4/5）

- [ ] 按 [`validation.md`](./validation.md) 的脱敏模板完成五次完整学习会话，不与阶段九验收混算。
- [ ] 将问题按阻断、重要、一般和已知限制分类，更新需求与验收后才开始编码。

已冻结 P10-001 至 P10-006 六个阻断问题。第 4 次实测实际是 Chrome、长视频、`video-pod` 多 BV 选集、AI 单轨，不是同 BV 多 P；字幕错配使 P10-002 再次打开，另发现 P10-005 与 P10-006，未完成闭环且未执行服务重启。剩余真实记录继续覆盖真正同 BV 多 P、Edge、服务重启、人工/多轨和三标签页，必要时增加第 6 次记录；不得用自动化测试替代。

### 本轮阻断修复

- [x] P10-001：请求保存字幕轨道的语言、显示名和人工/AI 类型；下载时先匹配原始 ID，ID 轮换后仅允许稳定描述唯一命中，多候选返回独立错误码并要求重选。
- [ ] P10-002：以 `tabId + library + BV/P` 隔离结果；同 BV 多 P 使用 URL P，`video-pod` 多 BV 使用激活 `data-key` 与播放器序号交叉确认；过渡态禁用操作。字幕准备绑定成功 inspect job 并再次解析 CID，迟到结果只回原 owner。代码与自动化已完成，待第 4 次场景真实复验。
- [x] P10-003：证据反馈 Prompt 增加明确 `output_schema`，限制反馈证据不得超出问题范围；在模型调用前持久保存原始回答，失败时保留 `feedback_failed` 状态。
- [ ] P10-004：禁用全局侧栏回退，只为普通 Bilibili 视频标签页启用独立 panel；未点击或不支持页面隐藏，返回已打开标签页自动恢复。代码与自动化已完成，待真实复验。
- [ ] P10-005：实现排队/在途取消、迟到结果丢弃、重启中断、显式 retry 与 `retry_of`；核心状态机自动化完成，待真实 Provider 和服务重启复验。
- [ ] P10-006：workspace 区分 empty/transcript-only/guide-ready；只有 `existing.guide` 才短路首次生成，Transcript-only 显示准确提示并进入确认面板。代码与自动化已完成，待真实复验。

### 本轮 Transcript 与多 P 增量

- [x] 新增 Transcript 准备与读取 API；客户端不再提交 CID/标题，指南请求只使用保存 revision 与预期 BV/P。
- [x] workspace 可恢复最近 Transcript；侧栏区分指南绑定版本和新加载版本，新加载 revision 默认显示并可切回指南绑定字幕，生成前显示来源确认面板。
- [x] 增加 URL/`video-pod`/播放器身份解析、DOM-only 指纹通知、切换冲突门禁，以及 inspect job→轨道→服务端 CID 的强绑定。
- [x] 历史 Transcript 默认标记 `legacy_unverified`；仅完全相同来源与哈希允许升级验证标记。
- [x] 新增完整字幕页、当前 cue 高亮、跟随暂停/恢复、cue 跳转和原生延迟渲染样式。
- [x] OpenAPI JSON 与 TypeScript client 从 FastAPI 定义重新生成，未手工编辑生成文件。

## 2. 建立 v4 持久化与已有内容查询

- [ ] 先写 v3→v4 migration、备份/回滚、旧指南 backfill 和多版本排序测试，再实现来源索引及新表。
- [ ] 实现本地 guide 列表与聚合 workspace 接口，保证旧指南和个人内容均可恢复。
- [x] 增量实现按 BV/P 查询最近指南的只读 workspace 接口，为侧栏重开恢复提供零模型请求路径；完整 v4 聚合模型和历史版本列表仍待实现。

## 3. 在侧栏自动恢复完整学习状态

- [ ] 打开 BV/P 后直接加载最新本地版本，不检查字幕、不要求 Provider、不调用模型，并提供历史版本选择。
- [ ] 显示保存时的 revision/轨道/Provider 信息；字幕更新后旧内容只保持原证据语义。
- [ ] 当前 BV/P 存在指南时读取完整本地 workspace；普通大纲、详情、练习和相同回答反馈均零模型复用，标签页切换及同标签页 A→B→A 不覆盖内容。自动化已完成，待真实复验。

## 4. 加固持久任务生命周期

- [x] 以测试驱动实现 queued/running 的协作取消、`cancel_requested|cancelled`、重启中断和安全持久化边界。
- [x] 实现显式 retry、新 job 与 `retry_of`，避免自动重复可能计费的在途请求。

## 5. 接入用量、成本与分层缓存管理

- [ ] 扩展 Provider 配置、GenerationUsage、Decimal 估算和未知值展示，保持旧配置兼容。
- [ ] 实现缓存 inventory、默认 prune、带预览和二次确认的生成物 clear，保护全部来源与个人内容。

## 6. 将按章练习升级为持久主动小测

- [ ] 隐藏答案依据和证据，持久保存用户作答，再生成证据化定性反馈。
- [ ] workspace 恢复小测尝试和反馈；数字评分、置信度和复习队列继续延后。
- [x] 反馈生成前持久保存用户原始回答，成功与失败状态均可从 SQLite 读取；完整 QuizAttempt DTO 和 workspace 恢复仍待实现。

## 7. 实现证据化总结与 Mermaid 导图

- [ ] 总结只使用 Transcript 和已验证生成物，不读取个人内容；结构、引用和无证据拒答均本地校验。
- [ ] 验证 MindMapTree 后由本地确定性生成 Mermaid，完成严格渲染、Markdown 发布和注入测试。

## 8. 改善长视频、错误恢复与无障碍

- [ ] 重构侧栏状态加载与任务反馈；本轮已提供取消、重试和字幕页，返回当前章节、重连和历史版本入口仍待完成。
- [ ] 完成键盘、焦点、语义、ARIA、对比度、减少动画和响应宽度门禁。
- [x] 增加字幕轨道 ID 轮换恢复、歧义错误提示、标签页定向消息和后台任务按 scope 保存进度。
- [ ] 完成 tab-specific panel 的 Chrome/Edge 真实复验：每个视频标签页点击一次、非视频页不显示、返回原标签页恢复原实例。

## 9. 完成交付文档和 0.2.0 归档

- [ ] 编写安装、升级、迁移、隐私、排障、Provider 兼容、成本与缓存说明。
- [ ] 更新双命令发行、Chrome/Edge 可复现归档、哈希、许可证及秘密扫描门禁。

## 10. 验证、真实使用与阶段关闭

- [ ] 执行 [`validation.md`](./validation.md) 的全量 Python、Extension、E2E、迁移、安全和 V1 回归。
- [ ] 完成真实 Chrome/Edge MVP 脱敏验收和待合并 CI；全部通过后更新 Constitution 并发布 `0.2.0`。

本轮自动化结果：Python 286 项通过、覆盖率 90.16%，Ruff format/lint 与 strict Pyright 通过；Extension OpenAPI/client 已从 API 1.3.0 重新生成且二次生成哈希稳定，TypeScript、ESLint、14 项 Vitest、3 项 Playwright 以及 Chrome/Edge 生产构建通过。第 4 次 Chrome 场景重跑、真实 Provider 在途取消、服务重启、Edge/多轨和其余 v4/发布门禁仍未关闭。
