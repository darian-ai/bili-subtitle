# ADR 0001：Local API 安全边界

- 日期：2026-08-21
- 状态：Accepted
- 关联：[`mission.md`](../mission.md)、[`tech-stack.md`](../tech-stack.md)、[`阶段七 Feature`](../2026-08-21-v2-compatibility-baseline/requirements.md)

## 上下文

阶段九将让浏览器扩展访问本机服务；浏览器来源、恶意网页、DNS rebinding 和泄漏凭据都是信任边界。

## 决策

服务只绑定 loopback，拒绝非预期 Host；首次连接使用五分钟单次配对码，并把随机 Bearer token 绑定到明确的扩展 Origin。所有请求校验 Host、Origin、CORS、方法、内容类型、大小与 schema，并设置速率和并发限制。长任务持久化且可恢复。扩展永不读取 Bilibili Cookie、模型密钥或 Credential Manager，权限只覆盖必要的 Bilibili 页面与 loopback。

## 替代方案

拒绝监听局域网、无认证 localhost、把 Cookie/API Key 交给扩展，以及通配 CORS。

## 后果

用户需要显式配对；服务实现必须有独立安全测试。限制 loopback 会排除局域网直接访问，配对与逐请求校验也会增加实现复杂度。

## 安全与隐私影响

该决定降低恶意网页、DNS rebinding、跨 Origin 调用和扩展凭据泄漏风险，但 localhost 不能被视为可信边界；阶段九仍必须对 Host、Origin、token 生命周期、请求限制和日志脱敏分别测试。

## 后续阶段约束

阶段七仅冻结契约，不添加服务依赖。阶段九实现 Local API 时不得提供公开监听、通配 CORS、关闭认证或把凭据交给扩展的生产选项；改变这些边界需要新的 ADR。
