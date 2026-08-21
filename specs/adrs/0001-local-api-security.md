# ADR 0001：Local API 安全边界

- 日期：2026-08-21
- 状态：Accepted

## 上下文

阶段九将让浏览器扩展访问本机服务；浏览器来源、恶意网页、DNS rebinding 和泄漏凭据都是信任边界。

## 决策

服务只绑定 loopback，拒绝非预期 Host；首次连接使用五分钟单次配对码，并把随机 Bearer token 绑定到明确的扩展 Origin。所有请求校验 Host、Origin、CORS、方法、内容类型、大小与 schema，并设置速率和并发限制。长任务持久化且可恢复。扩展永不读取 Bilibili Cookie、模型密钥或 Credential Manager，权限只覆盖必要的 Bilibili 页面与 loopback。

## 替代方案

拒绝监听局域网、无认证 localhost、把 Cookie/API Key 交给扩展，以及通配 CORS。

## 后果

用户需要显式配对；服务实现必须有独立安全测试。阶段七仅冻结契约，不添加服务依赖。
