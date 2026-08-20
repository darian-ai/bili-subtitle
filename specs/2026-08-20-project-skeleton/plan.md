# 阶段一：项目骨架实施计划

## 1. 初始化项目元数据

- [x] 创建基于 Hatchling 的 `pyproject.toml`，声明 Python 3.12+ 和版本 `0.1.0`。
- [x] 配置 `src/bili_subtitle/` wheel 包和 `bili-subtitle` console script。
- [x] 仅加入 Typer、Rich 运行时依赖以及阶段一质量工具开发依赖。
- [x] 生成并提交 `uv.lock`，补充 Python/uv 常见忽略项。

## 2. 建立最小 CLI 包

- [x] 创建包初始化、`python -m bili_subtitle` 入口和 CLI 模块。
- [x] 定义包含完整参数帮助的提取命令。
- [x] 定义 `auth login|status|clear` 命令树和中文帮助。
- [x] 实现无参数帮助与退出码为 `2` 的明确占位失败。
- [x] 保证两种公开语法正确分派，不把 `auth` 当作视频输入。

## 3. 配置自动化测试

- [x] 测试主命令帮助、无参数行为和全部公开选项。
- [x] 测试认证命令帮助与三个子命令。
- [x] 测试占位调用的提示、退出码和分派行为。
- [x] 配置分支覆盖率并强制最低 90%。

## 4. 配置代码质量

- [x] 配置 Ruff 的 Python 3.12 规则、导入排序和格式检查。
- [x] 配置 strict Pyright，覆盖 `src` 与 `tests`。
- [x] 修正所有 lint、格式、类型和覆盖率问题，不添加忽略规则掩盖错误。

## 5. 建立 Windows CI

- [x] 创建 GitHub Actions workflow，使用 Windows runner 和 Python 3.12。
- [x] 使用锁文件同步开发环境。
- [x] 依次运行 pytest、Ruff lint、Ruff format check 和 Pyright。

## 6. 完成合并验收

- [x] 执行 [`validation.md`](./validation.md) 中的全部本地自动化命令。
- [x] 手工核对帮助文本、占位错误和退出码。
- [x] 审计直接运行时依赖，确认没有阶段外能力。
- [x] 确认变更只包含阶段一工程骨架及其 feature spec。
