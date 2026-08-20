# 阶段一：项目骨架验证与合并标准

## 自动化验证

在仓库根目录依次运行：

```powershell
uv sync --locked --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

全部命令必须返回 `0`。pytest 必须在无网络、无账号环境通过，且分支覆盖率不低于 90%。Windows GitHub Actions 必须运行同一组质量检查。

## CLI 场景

| 场景 | 期望结果 |
|---|---|
| `uv run bili-subtitle --help` | 返回 `0`；显示视频参数、全部公开选项和认证命令提示 |
| `uv run python -m bili_subtitle --help` | 返回 `0`；行为与 console script 一致 |
| `uv run bili-subtitle` | 返回 `0`；显示主命令帮助 |
| `uv run bili-subtitle auth --help` | 返回 `0`；列出 `login`、`status`、`clear` |
| `uv run bili-subtitle BV1xx411c7mD` | 返回 `2`；标准错误明确说明功能尚未实现 |
| 任一认证子命令 | 返回 `2`；标准错误明确说明功能尚未实现 |
| 非法参数或类型 | 由 Typer 返回明确的用法错误，不产生业务副作用 |

## 无副作用与依赖审计

- 占位命令不得访问网络、读取 Windows Credential Manager 或创建 `subtitles/`。
- 捕获输出不得包含 Cookie、二维码密钥或签名 URL。
- `pyproject.toml` 的直接运行时依赖只能是 Typer 和 Rich。
- 依赖树不得出现媒体下载、FFmpeg、ASR、OCR 或访问控制绕过工具。
- 不要求执行 `uv build` 或 `uv tool install`；安装制品验收留到阶段六。

## 可合并条件

- 上述自动化验证和 CLI 场景全部通过。
- `requirements.md` 中的范围与已确定决策均有实现或测试保护。
- 代码与文档没有提前引入阶段二及以后功能。
- CI 配置、锁文件和 feature spec 与实现保持一致。
- Git 工作区除预期阶段一文件外没有无关改动。

## 本地验证记录

2026-08-20 在 Windows、CPython 3.14.2 和 uv 0.11.29 环境完成验证：

- 9 项 pytest 测试全部通过，分支覆盖率为 94.87%。
- Ruff lint、Ruff format check 和 strict Pyright 全部通过。
- console script、模块入口和认证帮助均返回 `0`。
- 提取占位调用返回 `2`，并输出明确的未实现提示。
- 直接运行时依赖仅为 Typer 和 Rich。
- GitHub Actions 尚待仓库配置远程并推送后验证。
