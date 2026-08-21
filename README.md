# bili-subtitle

Windows 优先的命令行工具，用于提取 Bilibili 投稿中平台已经提供的字幕。

## 安装

需要 Windows、Python 3.12 或更高版本，以及 [uv](https://docs.astral.sh/uv/)。在仓库根目录构建并安装：

```powershell
uv build
uv tool install .\dist\bili_subtitle-0.1.0-py3-none-any.whl
```

升级时在安装命令后加 `--force`；卸载使用 `uv tool uninstall bili-subtitle`。

## 使用

首次使用可登录并检查状态：

```powershell
bili-subtitle auth login
bili-subtitle auth status
```

提取投稿的全部分集，或只处理一个分集：

```powershell
bili-subtitle BV1xx411c7mD
bili-subtitle BV1xx411c7mD --page 1
bili-subtitle BV1xx411c7mD --lang zh-CN --force
```

结果写入当前目录的 `subtitles` 目录；具体目录和文件规则以 [Mission](specs/mission.md) 为准。命令摘要会区分成功、跳过和失败；平台没有字幕或当前账号不可访问时不会尝试识别、翻译或下载媒体。完整参数以 `bili-subtitle --help` 为准。

## 开发验证

```powershell
uv sync --locked --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv build
uv run python scripts/verify_release.py dist --rebuild-sdist
./scripts/verify_isolated_install.ps1 -Wheel ./dist/bili_subtitle-0.1.0-py3-none-any.whl
```

产品契约、技术约束和阶段状态的唯一权威来源分别是 [Mission](specs/mission.md)、[Tech Stack](specs/tech-stack.md) 和 [Roadmap](specs/roadmap.md)。
