# ADR 0004：命令、distribution 与版本

- 日期：2026-08-21
- 状态：Accepted

## 上下文

项目将演进为学习助手，同时不能破坏已发布的字幕脚本和 Credential Manager 会话。

## 决策

distribution 改名为 `bili-study`，阶段七版本为 `0.1.1`；同一 wheel 提供 `bili-study extract|auth` 与兼容 `bili-subtitle`，并共享实现和 `bili-subtitle/default` 凭据槽位。旧用户先 `uv tool uninstall bili-subtitle`，再安装 `bili-study`。阶段八使用 `0.2.0.devN`，阶段九从 `0.2.0a1` 开始，阶段十发布 `0.2.0`。

## 替代方案

拒绝立即删除旧入口、两个 distribution 争用脚本、强制覆盖安装和阶段七冒用 `0.2.0`。

## 后果

归档、隔离安装和固定响应测试必须同时验证两个入口；未来删除兼容入口需要新的 ADR。
