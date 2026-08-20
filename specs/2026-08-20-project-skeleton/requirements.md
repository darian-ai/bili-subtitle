# 阶段一：项目骨架需求

## 文档信息

| 项目 | 内容 |
|---|---|
| Feature | Project Skeleton |
| 工作分支 | `feature/project-skeleton` |
| 上游规格 | [`mission.md`](../mission.md)、[`tech-stack.md`](../tech-stack.md)、[`roadmap.md`](../roadmap.md) |
| 状态 | 已实现，本地验证通过，待 CI 验证 |
| 日期 | 2026-08-20 |

## 背景与目标

阶段零已经冻结产品使命、技术栈和实施顺序。阶段一需要建立后续功能共同使用的最小工程基础，使项目具备稳定的命令入口、离线测试、静态检查和 Windows CI，同时不得提前实现输入解析、登录或字幕提取。

完成后，开发者应能通过 uv 同步环境并运行空 CLI；用户应能查看 V1 的完整命令帮助，任何尚未实现的业务调用都必须明确失败而不是伪装成成功。

## 范围

- 使用 Python 3.12+、uv、Hatchling 和 `src/bili_subtitle/` 布局。
- 项目初始版本为 `0.1.0`，提交可复现的 `uv.lock`。
- 提供 `bili-subtitle` console script 和 `python -m bili_subtitle` 模块入口。
- 主命令帮助包含视频输入、`--page`、`--all-pages`、可重复 `--lang` 和 `--force`。
- 提供 `auth login`、`auth status`、`auth clear` 命令及完整简体中文帮助。
- 配置 pytest、pytest-cov、Ruff、Pyright 和仅 Windows 的 GitHub Actions 检查。
- 默认测试不联网、不读取真实凭据、不写字幕输出。

## 已确定决策

1. 包结构保持最小，只创建包初始化、模块入口和 CLI 模块；应用、领域和基础设施子包在首次使用时创建。
2. 阶段一运行时依赖只包含 Typer 和 Rich。HTTPX、qrcode、keyring 等依赖延后到对应阶段。
3. 无视频参数时显示帮助并返回 `0`；帮助请求返回 `0`。
4. 调用提取或认证占位命令时向标准错误输出明确的“尚未实现”提示并返回 `2`。
5. 参数值在阶段一只由 Typer 完成基础类型校验；分集选择优先级和互斥业务规则属于阶段二。
6. pytest 覆盖率低于 90% 时失败；覆盖率包含分支统计。
7. Pyright 使用 `strict`，Ruff 同时执行 lint 和格式检查。
8. CI 使用 Windows runner 和 Python 3.12，执行与本地相同的锁定环境检查。

## 不在范围内

- BV、av、URL、短链、分集或 CID 解析。
- 网络请求、Cookie、Credential Manager 和二维码登录。
- 字幕发现、下载、JSON/SRT/manifest 导出和文件名处理。
- 媒体下载、ASR、OCR、翻译或任何访问控制绕过。
- 提前创建没有行为的四层架构目录。
- README 用户文档、wheel 构建、`uv tool install` 和发布流程验收。

## 安全与兼容约束

- 运行时依赖不得包含媒体下载、ASR、OCR 或 GPL 工具。
- CLI 占位行为不得尝试网络访问、凭据读取或输出目录创建。
- 技术标识保留英文，所有说明、帮助和阶段性提示使用简体中文。
- Windows 是阶段一 CI 的唯一运行平台；代码仍不得无理由依赖非标准 Windows 路径。
