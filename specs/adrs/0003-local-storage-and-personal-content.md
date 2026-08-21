# ADR 0003：本地存储与个人内容

- 日期：2026-08-21
- 状态：Accepted
- 关联：[`mission.md`](../mission.md)、[`tech-stack.md`](../tech-stack.md)、[`阶段七 Feature`](../2026-08-21-v2-compatibility-baseline/requirements.md)

## 上下文

学习数据同时包含秘密、结构化索引、可重建生成物和不可替代的用户内容。

## 决策

普通配置进入配置文件，秘密进入 Windows Credential Manager，索引与任务进入版本化 SQLite，便携内容进入命名知识库的 Markdown。migration 前备份并可恢复。个人笔记、回答和修订与可重建 AI 输出分离；重新生成、索引重建和迁移不得覆盖个人资产。

## 替代方案

拒绝把秘密写入 SQLite/Markdown、把所有状态塞进单一 JSON，以及用生成结果覆盖用户文件。

## 后果

本地优先降低托管依赖并提高可移植性，但需要处理 Windows 路径、原子发布、数据库迁移、备份和多类数据所有权。

## 安全与隐私影响

API Key 与 Cookie 不得写入配置、SQLite 或 Markdown。个人内容不得因缓存清理、重新生成或 migration 丢失；备份也必须遵守相同的秘密隔离与本地保存边界。

## 后续阶段约束

阶段八必须定义 schema、迁移、备份和所有权测试；阶段七不添加 SQLite 或知识库实现。后续索引可以删除重建，个人笔记、回答和修订不得被当作缓存处理。
