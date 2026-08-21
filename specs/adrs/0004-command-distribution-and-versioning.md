# ADR 0004：命令、distribution 与版本

- 日期：2026-08-21
- 状态：Accepted
- 关联：[`mission.md`](../mission.md)、[`tech-stack.md`](../tech-stack.md)、[`阶段七 Feature`](../2026-08-21-v2-compatibility-baseline/requirements.md)

## 上下文

项目将演进为学习助手，同时不能破坏已发布的字幕脚本和 Credential Manager 会话。

## 决策

distribution 改名为 `bili-study`，阶段七版本为 `0.1.1`；同一 wheel 提供 `bili-study extract|auth` 与兼容 `bili-subtitle`，并共享实现和 `bili-subtitle/default` 凭据槽位。旧用户先 `uv tool uninstall bili-subtitle`，再安装 `bili-study`。阶段八使用 `0.2.0.devN`，阶段九从 `0.2.0a1` 开始，阶段十发布 `0.2.0`。

## 替代方案

拒绝立即删除旧入口、两个 distribution 争用脚本、强制覆盖安装和阶段七冒用 `0.2.0`。

## 后果

归档、隔离安装和固定响应测试必须同时验证两个入口；一个 wheel 携带两个包和命令会扩大兼容矩阵，但避免复制业务实现。

## 安全与隐私影响

保留 `bili-subtitle/default` 槽位避免迁移过程复制、打印或删除真实凭据。distribution 卸载只处理工具文件，不得清理 Credential Manager 数据。

## 后续阶段约束

阶段八使用 `0.2.0.devN`，阶段九使用 `0.2.0aN`，阶段十才发布 `0.2.0`。未来删除兼容入口、改变凭据槽位或恢复双 distribution 发布都需要新的 ADR 和迁移验证。
