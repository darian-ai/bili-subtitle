# 阶段十：视频学习助手 MVP 验证及合并标准

## 五次学习记录门禁

编码前完成至少五次独立完整会话。每次只记录：浏览器、短/长、单/多 P、字幕类型/轨道数量类别、任务耗时范围、恢复操作、通过/失败和问题编号。不得记录 BV、标题、账号、字幕、Prompt、响应、笔记、作答、配对码或 Key。

| 记录 | 浏览器与场景 | 完整闭环 | 问题编号 | 状态 |
|---|---|---|---|---|
| 1 | 用户确认独立会话；环境未补录 | 已完成 | P10-001 | 修复完成，待复验 |
| 2 | 用户确认独立会话；环境未补录 | 已完成 | P10-002、P10-004 | 首次修复复验失败；重新修复完成，待再次复验 |
| 3 | 用户确认独立会话；环境未补录 | 已完成 | P10-003 | 修复完成，待复验 |
| 4 | Chrome；长视频；`video-pod` 多 BV 选集；AI 单轨 | 未完成 | P10-001、P10-002（重开）、P10-005、P10-006、P10-007 | 服务重启后首个视频正确；继续打开其他 BV/P 时出现已保存字幕正文错配或永久 transitioning。已定位旧播放器接口、描述符回退和过严 DOM 完整性门禁，待本轮修复复验 |
| 5 | 真正同 BV 多 P、Edge、服务重启、人工/多轨及三标签页按剩余覆盖组合执行 | 待执行 | 待记录 | 待执行；覆盖不足时增加第 6 次 |

问题清单必须区分阻断、重要、一般和已知限制。阻断/重要问题在发布前关闭；接受限制必须说明影响、规避方式和延后阶段。

## 自动化与质量门禁

- Python 测试、合并分支覆盖率不低于 90%、strict Pyright、Ruff lint/format、许可证、wheel/sdist、sdist 重建、隔离双命令安装和 `git diff --check` 全部通过。
- Extension 执行锁定安装、OpenAPI client 漂移、ESLint、TypeScript、Vitest、Playwright、Chrome/Edge 构建与归档哈希检查。
- 默认测试封锁真实 Bilibili、Provider、Credential Manager 和用户知识库；V1、阶段八和阶段九回归全部通过。

## 迁移与已有内容恢复

- 从真实结构的 v3 固定库迁移到 v4 前创建可验证备份；成功后旧 Transcript、指南、详情、练习、笔记和反馈均可读取，失败时原库可恢复。
- 旧指南 backfill 即使缺少 Provider/时间元数据也可列出；多个版本排序确定且最新版本唯一。
- 页面首次打开、SPA 返回、侧栏重开、重新配对和服务重启均自动加载最新 workspace；拦截 Provider/Bilibili socket 并断言模型与平台请求数为零。
- 普通大纲、章节详情、练习和相同回答反馈点击必须只执行本地 GET；已有记录时生成 POST 数为零。workspace 查询失败保持错误状态并只允许重试，不得创建任务。
- workspace 恢复大纲、详情、练习、小测、总结、导图、笔记、作答和反馈；用户草稿只从扩展本地恢复。
- 字幕或模型切换不会修改旧 revision/EvidenceRef；主动检查发现变化后旧版本仍可只读加载。

## 多 P 强绑定与字幕时间轴

- 以固定 DOM 覆盖显式 URL P、同 BV 多 P pod、`video-pod` 三个不同 BV 的激活项、外层 `.active`、`.head.active` 与内层 `.simple-base-item.active` 三种合集选中标记、仅 DOM 激活变化、metadata 次要标签残留、播放器菜单缺失、URL/选集/播放器冲突和过渡完成；单 P 合集播放器序号与合集位置一致时必须解析为 P1，多 P 合集播放器序号与内部 P 一致时必须解析；真实冲突期间来源操作均禁用，同 BV 序号必须解析为 P，多 BV 集合序号不得显示为 P。
- 人为延迟 P1 的检查、Transcript 准备和生成，期间切换 P2；P1 结果只能回写 P1 scope，P2 在取得自身正确 revision 前生成按钮保持门禁。
- Transcript 准备请求 schema 不含 AID/CID/标题但必须含成功 inspect job ID；错误 job、知识库、BV/P 或重新解析 CID 返回 `inspection_source_mismatch`。固定时间与 key 验证 WBI 参数排序、字符过滤、`wts`/`w_rid`，签名失败刷新 key 后只重试一次。播放器轨道请求必须命中 `/x/player/wbi/v2` 并断言 AID/BVID/CID、no-cache 与响应身份完全一致；不一致不保存。
- inspect 后 WBI 返回相同描述但不同轨道 ID 时必须返回 `subtitle_track_unavailable`，不得下载正文。连续加载三个不同 BV/P 的字幕正文不得复用；模拟旧接口“外层身份正确但轨道和正文轮换”的响应必须被精确 ID 门禁拒绝。
- workspace 同时覆盖“只有 Transcript、没有指南”和“已有指南”页面；Transcript-only 点击创建必须出现确认且确认前生成 POST 为零。已有指南加载新字幕后默认显示新 revision，可明确切回指南绑定 revision，旧指南保持不变。
- 覆盖 cue 起止边界、间隙无高亮和重叠取最后开始 cue；手动滚动暂停跟随、按钮恢复、点击只 seek 不 pause。
- 使用长 cue 固定数据验证完整 DOM 语义、`content-visibility` 延迟渲染、窄侧栏无横向溢出，以及列表、按钮和确认面板的键盘/ARIA 行为。
- 所有 workspace/job 结果应用前断言 BV/P/revision 与启动 owner 一致；人为乱序返回连续两次视频上下文轮询，旧响应不得覆盖新页面。guide workspace 绑定 Transcript 与请求 BV/P 不一致时保持旧指南并显示稳定错误。
- 旧 payload 读取为 `legacy_unverified` 并显示警告；仅 BV/P/CID/hash 完全一致的重新下载可升级证明，正文、revision 与证据逐字不变。

## 视频类型边界

- 固定平台响应覆盖普通单 P/多 P、`ugc_season` 当前项、已有权限 UGC、互动、Story、首映、仅预览和关键分类字段缺失；后三类及未知类型必须在字幕适配器调用前失败。
- URL 单测拒绝 bangumi、cheese、live、festival、medialist、空间列表和非 Bilibili 域名；标准 `/video/BV...` 仅作为候选，服务端拒绝后不得保留旧检查结果或启用生成。
- inspect schema v2 对普通视频返回 `supported`，对已有权限内容返回 `conditional + existing_entitlement_required`，对合集当前项返回 `current_item_only`；无字幕保持受支持类型并返回独立状态。
- Chrome/Edge 真实验收至少分别覆盖普通多 P、UGC 合集当前项和一个明确拒绝类型；已有权限场景只使用账号已经合法可见的内容，不执行购买或解锁。

## 任务取消、恢复与重试

- 覆盖排队取消、运行安全点取消、在途请求取消、完成/取消竞态、重复取消和终态取消。
- `cancel_requested` 不伪装成已撤销远端请求；迟到响应不得持久化内容，usage 可记录时仍保留成本提示。
- 服务重启保留 queued，原 running 转 interrupted；只有用户显式 retry 才创建新 job，且 `retry_of`、错误和请求脱敏正确。
- 取消、失败、重试和 Provider 切换不得破坏 Transcript、个人内容或已有有效生成物。
- 取消重新生成后旧指南仍可浏览；取消反馈保留原始回答；取消字幕准备不得留下半成品 Transcript。

## 用量、成本与缓存

- 覆盖完整/部分/缺失 usage，零 token、修复请求、多请求 map/reduce、缓存命中和未知值。
- Decimal 单价、大小写币种、舍入和输入/输出分别估算有确定测试；价格不完整时只显示 usage 和“成本未知”。
- 缓存 inventory 的数量/大小与数据库和文件一致；prune 只删孤立/过期请求缓存。
- clear 在未确认、范围变化或含受保护内容时拒绝；按视频/Provider 删除生成物后 Transcript、笔记、作答和复述逐字不变。

## 小测、总结、导图与证据

- 小测提交前不返回或渲染答案、证据文本和回看入口；提交后保存原始作答及合法证据反馈，刷新与重启可恢复。
- 总结输入构造测试证明不读取个人笔记、作答、复述或测验尝试；所有事实引用当前保存 revision 的合法 cue。
- MindMapTree 覆盖深度、节点数、标签、顺序、循环和 EvidenceRef 校验；无效结果只允许一次结构修复。
- Mermaid 由本地生成，模型返回的指令、HTML、链接、事件和 Mermaid 片段只能作为不可信文本处理；严格模式无脚本执行。
- 总结与导图重新生成只创建新生成物，不覆盖个人内容或其他历史版本。

## Extension、长视频与无障碍 E2E

- Chrome/Edge 模拟 E2E 覆盖自动恢复、历史版本、取消/重试、成本、缓存预览、小测、总结、导图和服务断开。
- 覆盖两个已点击视频标签页各自独立、未点击视频标签页无侧栏、非视频页隐藏、返回原标签页自动恢复，以及同标签页 A→B→A 的 workspace 与异步任务隔离。
- 长视频可返回当前章节，生成期间可浏览已有内容，窄/宽侧栏不横向溢出。
- 全部交互可用键盘完成；焦点顺序、可见焦点、标题层级、label、ARIA live、对比度和 reduced-motion 通过审计。
- 未经点击不上传、不生成、不清理缓存、不自动暂停或强制答题。
- 在视频页保持打开时重载扩展，旧 content script 应立即停止 observer/定时器/runtime 消息；控制台不得出现未捕获的 `Extension context invalidated`，新实例仍能报告当前来源。

## 本轮测试数据重置

- WBI、精确轨道和来源门禁自动化全部通过后停止本地服务，事务清空并压缩测试期全局 `api.sqlite3` 与当前注册测试库的 `study.sqlite3`，再启动服务；所有学习数据与任务表必须为零。
- 不删除 `libraries.json`、Bilibili Credential Manager 凭据、Provider 配置或导出 Markdown；重载扩展以清除内存 session。
- 空库重启后依次打开同 BV 多 P、多 BV 合集和普通视频，所有字幕必须重新下载；数据库不得出现同一 BV/P/CID 对应互不相干正文的 revision。

## 真实脱敏验收与发布

- 在 Chrome 与 Edge 使用真实字幕和用户自备 Provider 验证已有内容零模型恢复、每标签页一次点击的独立侧栏、非视频页隐藏、历史版本、取消/显式重试、小测、总结、导图、成本与缓存保护。
- 验证从 `0.2.0a1` 升级到 `0.2.0`、v3→v4 migration、服务重启、双命令安装和两个扩展归档。
- 只记录环境、命令形态、请求/耗时范围、迁移结论和通过/失败；不记录任何账号或内容数据。
- 待合并提交的 Windows CI、依赖/许可证、安全扫描和归档审计全部通过，并记录提交哈希与 CI 链接。
- 只有五次记录问题全部关闭或接受、本文全部门禁通过后，才更新 `mission.md`、`tech-stack.md`、`roadmap.md` 并发布本地安装 `0.2.0`。
