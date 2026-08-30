# 阶段十：视频学习助手 MVP 实施计划

## 1. 基于四次独立学习记录持续完成问题闭环（已完成）

- [x] 已按 [`validation.md`](./validation.md) 的脱敏模板形成四次独立学习记录；结合此前反馈修改闭环，现有记录已经足以识别阶段十的主要问题，不再要求补足第五次记录。
- [x] 将已发现问题按阻断、重要、一般和已知限制分类，并持续随修复、复验结果更新需求、计划与验收，不再以预先冻结问题清单作为编码门禁。

四次记录及此前反馈修改闭环已经形成 P10-001 至 P10-007，其中 P10-001 至 P10-006 为阻断问题，P10-007 为重要问题；该清单随修复和复验结果持续维护，不视为冻结。第 4 次实测是 Chrome、长视频、`video-pod` 多 BV 选集、AI 单轨；后续服务重启与跨页面复验确认 P10-001、P10-002 仍未关闭：首个视频可正确加载，但继续打开其他 BV/P 后会保存错配字幕，或永久停在来源 transitioning。只清理测试数据不能代替根因修复。真正同 BV 多 P、Edge、服务重启、人工/多轨和三标签页等剩余组合纳入本阶段最终真实验收，不再要求形成第五次独立学习记录，也不得用自动化测试替代真实复验。

### 本轮阻断修复

- [x] P10-001：播放器字幕轨道发现改用 `/x/player/wbi/v2` 和当前登录会话的 WBI key；严格核对 AID/BVID/CID。下载阶段只接受 inspect 选中的精确轨道 ID，ID 消失或变化时返回 `subtitle_track_unavailable` 并要求重新检查，禁止按语言、显示名或人工/AI 类型回退。代码、自动化、三个 BV/P 连续真实 WBI 冒烟及 Chrome/Edge 脱敏侧边栏复验均已通过。旧 `/x/player/v2` 实测会为同一来源返回轮换且属于其他视频的字幕，原“稳定描述唯一回退”结论撤销。
- [x] P10-002：以 `tabId + library + BV/P` 隔离结果；同 BV 多 P 以 URL 与 pod 激活序号为主证据，pod 多 BV 使用激活 `data-key` 与页码确认。来源判定改为渐进增强：URL 是主身份，未知 DOM、虚拟列表、缺少或陈旧播放器菜单只减少旁证，不再永久阻塞；只有已明确激活的 BV/P 与 URL 冲突才进入 transitioning，最终仍由服务端 WBI 的 BVID/CID/轨道 ID 强校验防止错配。轮询响应、workspace 和生成结果应用前再次核对 owner 与 BV/P，迟到结果只回原作用域。真实复验新增 `.normal-base-item.active` 与虚拟化播放器菜单变体，修复后的 Chrome/Edge 重载验收、32 项 Vitest、3 项 Playwright 及双浏览器生产构建均已通过。
- [x] P10-003：证据反馈 Prompt 增加明确 `output_schema`，限制反馈证据不得超出问题范围；在模型调用前持久保存原始回答，失败时保留 `feedback_failed` 状态。
- [x] P10-004：禁用全局侧栏回退，只为普通 Bilibili 视频标签页启用独立 panel；未点击或不支持页面隐藏，返回已打开标签页自动恢复。代码、自动化与 Chrome/Edge 脱敏复验均已完成。
- [x] P10-005：实现排队/在途取消、迟到结果丢弃、重启中断、显式 retry 与 `retry_of`；核心状态机自动化、真实 Provider 和服务重启复验均已通过。
- [x] P10-006：workspace 区分 empty/transcript-only/guide-ready；只有 `existing.guide` 才短路首次生成，Transcript-only 显示准确提示并进入确认面板。代码、自动化与 Chrome/Edge 脱敏复验均已完成。
- [x] P10-007：使用 WXT content context 管理 popstate、定时器和 MutationObserver；失效时断开 observer、移除 runtime listener，并吞掉仅发生于同步失效窗口的 runtime 异常。代码、类型检查、双浏览器构建与 Chrome/Edge 真实扩展重载复验均已通过。

### 本轮 Transcript 与多 P 增量

- [x] 新增 Transcript 准备与读取 API；客户端不再提交 CID/标题，指南请求只使用保存 revision 与预期 BV/P。
- [x] workspace 可恢复最近 Transcript；侧栏区分指南绑定版本和新加载版本，新加载 revision 默认显示并可切回指南绑定字幕，生成前显示来源确认面板。
- [x] 增加 URL/`video-pod`/播放器身份解析、DOM-only 指纹通知、切换冲突门禁，以及 inspect job→轨道→服务端 CID 的强绑定。
- [x] 区分同 BV 多 P pod 与多 BV pod；播放器轨道请求加入 AID/BVID/CID 和 no-cache，响应身份不完整或不一致时拒绝保存，并在字幕页显示完整来源链。
- [x] 历史 Transcript 默认标记 `legacy_unverified`；仅完全相同来源与哈希允许升级验证标记。
- [x] 新增完整字幕页、当前 cue 高亮、跟随暂停/恢复、cue 跳转和原生延迟渲染样式。
- [x] OpenAPI JSON 与 TypeScript client 从 FastAPI 定义重新生成，未手工编辑生成文件。

### 本轮来源一致性修复

- [x] 实现 WBI 参数签名、key 缓存与签名失败后的单次刷新重试；移除旧播放器接口。
- [x] 将 inspect→prepare 的轨道选择收紧为精确 ID，覆盖“外层身份正确但返回另一同名轨道”的拒绝测试。
- [x] 重写 DOM metadata 优先级和 pod 判定，使缺少播放器菜单的稳定页面可解析、真实冲突仍保持 transitioning。
- [x] 为侧栏轮询增加序号门禁，为检查/字幕准备增加同步 in-flight 锁，并拒绝加载不属于请求 BV/P 的 guide workspace。
- [x] 修复完成并停止服务后，事务清空当前测试期 `api.sqlite3` 与注册测试库的 `study.sqlite3`，保留库注册、凭据、Provider 配置和导出文件；服务已重启且学习表均为零。

### 视频类型边界

- [x] 冻结普通 UGC、同 BV 多 P、UGC 合集当前项和已有权限受限 UGC 的覆盖边界；明确无字幕是能力不可用而非视频类型不支持。
- [x] 从平台元数据归一视频、容器和访问类型；互动、Story、未知特殊模型、首映中和仅预览内容在字幕访问前失败关闭。
- [x] inspect job result 升级到 schema v2，返回类型、条件支持和限制字段；扩展增加稳定错误文案与非视频路由测试。
- [x] 使用真实普通多 P、UGC 合集当前项、已有权限内容及至少一个明确拒绝类型完成 Chrome/Edge 脱敏复验，包括渐进增强来源判定修复。

## 2. 建立 v4 持久化与已有内容查询

- [x] 先写 v3→v4 migration、备份/回滚、旧指南 backfill 和多版本排序测试，再实现来源索引及新表。
- [x] 实现本地 guide 列表与聚合 workspace 接口，保证旧指南和个人内容均可恢复。
- [x] 增量实现按 BV/P 查询最近指南的只读 workspace 接口，为侧栏重开恢复提供零模型请求路径；完整 v4 聚合模型和历史版本列表仍待实现。

## 3. 在侧栏自动恢复完整学习状态

- [x] 打开 BV/P 后直接加载最新本地版本，不检查字幕、不要求 Provider、不调用模型，并提供历史版本选择。
- [x] 显示保存时的 revision/轨道/Provider 信息；字幕更新后旧内容只保持原证据语义。
- [x] 当前 BV/P 存在指南时读取完整本地 workspace；普通大纲、详情、练习和相同回答反馈均零模型复用，标签页切换及同标签页 A→B→A 不覆盖内容。自动化与 Chrome/Edge 脱敏复验均已完成。

## 4. 加固持久任务生命周期

- [x] 以测试驱动实现 queued/running 的协作取消、`cancel_requested|cancelled`、重启中断和安全持久化边界。
- [x] 实现显式 retry、新 job 与 `retry_of`，避免自动重复可能计费的在途请求。

## 5. 接入用量、成本与分层缓存管理

- [x] 扩展 Provider 配置、GenerationUsage、Decimal 估算和未知值展示，保持旧配置兼容。
- [x] 实现缓存 inventory、默认 prune、带预览和二次确认的生成物 clear，保护全部来源与个人内容。

## 6. 将按章练习升级为持久主动小测

- [x] 隐藏答案依据和证据，持久保存用户作答，再生成证据化定性反馈。
- [x] workspace 恢复小测尝试和反馈；数字评分、置信度和复习队列继续延后。
- [x] 反馈生成前持久保存用户原始回答，成功与失败状态均可从 SQLite 读取；完整 QuizAttempt DTO 和 workspace 恢复仍待实现。

## 7. 实现证据化总结与 Mermaid 导图

- [x] 总结只使用 Transcript 和已验证生成物，不读取个人内容；结构、引用和无证据拒答均本地校验。
- [x] 验证 MindMapTree 后由本地确定性生成 Mermaid，完成严格渲染、Markdown 发布和注入测试。

## 8. 改善长视频、错误恢复与无障碍

- [x] 重构侧栏状态加载与任务反馈；已提供取消、重试、字幕页、返回当前章节、重连和历史版本入口。
- [x] 完成键盘、焦点、语义、ARIA、对比度、减少动画和响应宽度门禁。
- [x] 增加字幕轨道 ID 轮换恢复、歧义错误提示、标签页定向消息和后台任务按 scope 保存进度。
- [x] 完成 tab-specific panel 的 Chrome/Edge 真实复验：每个视频标签页点击一次、非视频页不显示、返回原标签页恢复原实例。

## 9. 完成交付文档和 0.2.0 归档

- [x] 编写安装、升级、迁移、隐私、排障、Provider 兼容、成本与缓存说明。
- [x] 更新双命令发行、Chrome/Edge 可复现归档、哈希、许可证及秘密扫描门禁。

## 10. 验证、真实使用与阶段关闭

- [x] 执行 [`validation.md`](./validation.md) 的全量 Python、Extension、E2E、迁移、安全和 V1 回归。
- [x] 完成真实 Chrome/Edge MVP 脱敏验收和待合并 CI；全部人工验收与 Quality run 33060881906 已通过，Constitution 已更新并发布 `0.2.0`。

本轮自动化结果：Python 315 项通过、覆盖率 90.08%，Ruff format/lint、strict Pyright、许可证/秘密扫描、wheel/sdist、sdist 重建、隔离双命令安装与 `git diff --check` 通过；Extension OpenAPI 重新生成、TypeScript、ESLint、32 项 Vitest、3 项 Playwright、Chrome/Edge 生产构建、确定性归档及 SHA-256 清单通过。三个已知 BV/P 的连续真实 WBI 请求均命中预期轨道与正文；本地服务此前已在空测试库上重启并通过健康检查。渐进增强来源判定、真实 Provider 重启/取消和全部 Chrome/Edge 人工验收均已通过；仅待提交后 CI，不以本地自动化替代。
