# 阶段八：学习数据与 AI 后端实施计划

## 1. 冻结领域模型与不变量

- [x] 用失败测试定义 Transcript revision、cue、EvidenceRef、StudyGuide、章节、问题、笔记和复述模型。
- [x] 锁定稳定 ID、schema version、时间范围、cue 顺序和 evidence 合法性规则。
- [x] 定义生成指纹、缓存失效和旧 revision 生成物状态。

## 2. 建立知识库与持久化基础

- [x] 实现命名知识库注册和目录冲突、安全路径及重复创建规则。
- [x] 建立标准库 SQLite repository、编号 migration、外键、事务与迁移前备份。
- [x] 持久化 Transcript、任务、生成记录、缓存元数据和个人内容索引。
- [x] 覆盖首次创建、升级、回滚、损坏数据库和并发写入测试。

## 3. 导入 Transcript 与证据解析

- [x] 从现有字幕提取结果构造规范化 TranscriptRevision，不复制平台下载逻辑。
- [x] 保留完整 cue 范围、轨道身份、来源和内容哈希。
- [x] 实现 EvidenceRef 到 cue/时间范围的严格解析和跨 revision 拒绝规则。
- [x] 覆盖空正文、重叠时间、超长文本、Unicode 和视频尾部用例。

## 4. 配置 Provider 与秘密存储

- [x] 实现 Provider 配置端口和 CLI，仅持久化非秘密字段。
- [x] 使用 Windows Credential Manager 独立保存、读取和清除每个 Provider 的 API Key。
- [x] 校验 HTTPS base URL、模型名、上下文预算和输出语言。
- [x] 实现首次上传确认及取消不创建任务的契约。

## 5. 实现 OpenAI-compatible 适配器

- [x] 定义 Chat 请求/响应端口、超时、usage 和稳定错误类型。
- [x] 实现 OpenAI-compatible HTTP 适配器及响应大小、内容类型和结构限制。
- [x] 对认证、配额、超时、网络、结构与未知错误进行脱敏分类。
- [x] 使用固定响应覆盖成功、流式/非流式边界、异常正文和秘密金丝雀。

## 6. 实现两阶段生成与校验

- [x] 按上下文预算分块，Map 阶段逐块提取候选结构，Reduce 阶段生成覆盖完整视频的大纲。
- [x] 实现章节详情按需生成，不预生成未请求内容。
- [x] 严格校验 schema、章节顺序、cue 范围和 EvidenceRef，只允许一次结构修复。
- [x] 实现 Prompt injection 防护，将字幕始终视为不可信数据。
- [x] 记录请求数、usage、耗时和缓存命中；缺失 usage 时标记未知。

## 7. 发布 Markdown 与保护个人笔记

- [x] 定义生成 Markdown 和个人 Markdown 的独立目录、frontmatter 与稳定链接。
- [x] 实现个人笔记新增/读取及不可覆盖规则。
- [x] 从结构化生成物确定性渲染可重建 Markdown，并使用原子发布。
- [x] 覆盖重新生成、发布中断、文件冲突、非法路径和 Obsidian 兼容文本。

## 8. 接入 CLI、文档与阶段关闭

- [x] 组合知识库、Provider、Transcript、指南、章节和笔记命令，保持应用层端口边界。
- [x] 更新 README、CHANGELOG 和必要的 Constitution 状态，真实区分阶段八与阶段九能力。
- [x] 执行 [`validation.md`](./validation.md) 的全部离线质量、构建、安装、秘密和 V1 回归门禁。
- [ ] 记录脱敏真实 Provider 验收和待合并 Windows CI 证据后，才将阶段八标记完成。

