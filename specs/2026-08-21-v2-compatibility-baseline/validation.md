# 阶段七：V2 兼容基线验证及合并标准

## 完成证据

- 2026-08-22 本地关闭验收：224 项离线测试通过，分支覆盖率 90.82%；许可证清单覆盖 40 个锁定依赖；Ruff、格式、strict Pyright、构建、归档、sdist 重建、旧 `bili-subtitle 0.1.0` 卸载迁移和隔离双命令安装通过。
- 基线实现提交：`84626659c62694e851f869df9ade341f8dabd9cb`。
- Windows GitHub Actions：关闭提交 `6e1c029f7e7c1c4c16663ab3929315e05fde538b` 的 Quality run [32504460844](https://github.com/darian-ai/bili-subtitle/actions/runs/32504460844) 全部成功；基线提交的 run [32502973696](https://github.com/darian-ai/bili-subtitle/actions/runs/32502973696) 亦成功。
- 补充关闭测试集中证明纯输入无 I/O、登录/提取中断分类、双入口共享处理器与 `0|1|2`、凭据槽位、未实现命令和应用依赖方向；四份 ADR 已补齐 Constitution/Feature 链接、安全与隐私影响及后续约束。

## 自动化质量门禁

在仓库根目录依次运行：

```powershell
uv sync --locked --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv build
uv run python scripts/verify_release.py dist --rebuild-sdist
.\scripts\verify_isolated_install.ps1 -Wheel .\dist\bili_study-0.1.1-py3-none-any.whl
git diff --check
```

全部命令必须返回 `0`。pytest 必须在默认网络封锁、无真实账号、无真实 Credential Manager、无
真实等待和无真实模型环境中通过，分支覆盖率不低于 90%。待合并提交的 Windows GitHub Actions
必须执行等价门禁并成功。

## 输入、认证与中断矩阵

| 场景 | 期望结果 |
|---|---|
| 非法 BV、av、普通文本或不受支持 URL | 返回 `2`；不创建 Client、不读 Keyring、不登录、不显示二维码 |
| `--page` 与 `--all-pages` 同时出现 | Typer/纯参数阶段返回 `2`；无任何 I/O |
| 空 `--lang` | 纯参数阶段返回 `2`；无任何 I/O |
| 合法 `b23.tv` 短链 | 本地校验后才进入共享 Client、认证和安全重定向流程 |
| 自动登录期间 Ctrl+C | stderr 为“错误：登录已取消。”；返回 `2`；无 traceback |
| `auth login` 期间 Ctrl+C | 与现有认证取消契约一致，返回 `2` |
| 有效认证后的元数据/字幕/导出阶段 Ctrl+C | stderr 为“错误：字幕提取已取消。”；返回 `2`；无 traceback |

对上述场景使用唯一 Cookie、二维码密钥、签名 URL 和远端响应正文金丝雀，证明 stdout、stderr、
异常和生成文件中均不存在秘密。

## 错误分类与局部失败

- 分别从字幕发现、正文下载、路径规划、SRT 渲染、批量发布和 manifest 发布端口注入每种已声明
  预期错误，证明 V1 分集/轨道局部失败、继续处理和 `0|1|2` 聚合不变。
- 合法 `NoSubtitles`、过滤无匹配和全部跳过仍是退出 `0` 的正常结果。
- 部分发布错误必须准确报告已经发布与失败的 JSON/SRT 动作，保留旧文件并清理临时文件。
- 从每个应用端口注入带秘密文本的 `RuntimeError`、`AssertionError` 或 `TypeError`，直接调用
  `run_extraction` 时必须观察到原异常冒泡，不能得到伪造的页面/轨道失败结果。
- 通过两个公开 console script 注入同类未知错误时，必须返回 `2`，只显示通用内部错误，不输出
  traceback、异常文本或秘密。
- 静态检查应用包不得出现用于兜底业务分类的 `except Exception`，也不得导入具体文件导出适配器。

## 导出端口与 V1 回归

- 使用内存 `ExportPort` 替身直接运行完整流程，证明应用层不需要真实文件系统导出模块即可编排。
- 架构测试证明领域层只依赖标准库，应用层只依赖 Protocol 和应用/领域边界类型，CLI 只负责组合
  适配器与渲染结果。
- 文件系统适配器继续通过现有 Windows 非法字符、保留名、大小写冲突、240 字符预算和稳定摘要
  测试。
- 旧 manifest 缺失、损坏、不安全、同语言多轨歧义和轨道 ID 轮换时的安全历史复用行为不变。
- 原始 JSON 字节、UTF-8 SRT 时间/文字、逐文件补齐、`--force`、部分发布、manifest 最后发布及
  临时文件清理回归全部通过。
- manifest schema version、字段、顺序、相对路径和秘密隔离与阶段六完成版本一致。

## 双命令等价矩阵

对单分集、多分集、多语言、同语言多轨、无字幕、无匹配、全部跳过、缺失补齐、`--force`、部分
成功和整体失败固定场景，分别调用：

```text
bili-subtitle <input> ...
bili-study extract <input> ...
```

必须逐项比较：

- 输入和分集选择、登录次数、HTTP 调用顺序、轨道顺序及下载次数。
- JSON、SRT 与 manifest 相对路径和逐字节内容。
- 分集/轨道状态、摘要计数及最终 `0|1|2` 退出码。
- stdout/stderr 的业务结果；只允许程序名、Usage 路径和命令层级不同。

认证矩阵必须证明 `bili-study auth` 与 `bili-subtitle auth` 对同一个
`bili-subtitle/default` 假 Keyring 槽位执行相同的 login、status 和 clear 行为。

## 命令帮助与未实现边界

| 命令 | 期望结果 |
|---|---|
| `bili-study` | 返回 `0` 并显示 `extract`、`auth` |
| `bili-study extract --help` | 显示 V1 全部提取参数及正确的新命令示例 |
| `bili-study auth --help` | 显示 `login`、`status`、`clear` |
| `bili-subtitle --help` | 保持现有顶层提取帮助和兼容认证提示 |
| `bili-subtitle auth --help` | 保持现有认证命令帮助 |
| 任一未来命令 | 未注册并返回参数错误，不显示伪占位成功 |

帮助、README 和包描述中不得把 Local API、插件、Provider、知识库、学习指南或笔记描述为已经
可运行。

## Distribution、归档与迁移验证

- `pyproject.toml`、锁文件、两个包版本、构建元数据和校验脚本一致声明 `bili-study 0.1.1`。
- `dist/` 只包含 `bili_study-0.1.1-py3-none-any.whl` 和 `bili_study-0.1.1.tar.gz`。
- wheel 包含 `bili_study/`、`bili_subtitle/`、`bili-study` 与 `bili-subtitle` entry point、
  Apache-2.0 License-Expression 和许可证文件。
- sdist 包含构建所需源码、README、pyproject、LICENSE、三份 Constitution 及 ADR；不得包含测试
  秘密、缓存、真实字幕或本地数据。
- 从 sdist 独立重建得到名称、版本、包、入口和许可证一致的 wheel。
- 在经绝对路径校验的临时 uv tool 根完成新 distribution 清洁安装；从仓库外的新 PowerShell 调用
  两个 `--help`，并验证两者实际控制台入口传播 `0|1|2`。
- 用隔离的旧 `bili-subtitle 0.1.0` 安装夹具验证迁移：卸载旧 distribution 后不存在遗留命令冲突，
  安装 `bili-study 0.1.1` 后两个命令可用，最终只存在 `bili-study` tool 记录。
- 迁移前预置的假 `bili-subtitle/default` 凭据在安装后仍能由两个命令读取；安装、卸载和改名不得
  删除或复制真实 Credential Manager 数据。

## 许可证审计门禁

审计记录必须覆盖当前锁定依赖和构建闭包中的每个包，并至少包含：

| 字段 | 要求 |
|---|---|
| 包与版本 | 与 `uv.lock` 或受约束构建环境逐项一致 |
| 用途 | runtime、development、build 及是否进入发行归档 |
| 许可证 | 规范 SPDX 表达式；多许可证说明实际采用选项 |
| 权威来源 | 对应版本的上游 LICENSE/COPYING/NOTICE 或发布元数据链接 |
| 兼容结论 | compatible、conditional 或 blocked，并写明依据 |
| 义务 | attribution、notice、source availability 或无额外随附义务 |

- 离线检查必须证明审计清单无遗漏、无多余陈旧项且版本完全一致。
- 元数据缺失或互相矛盾时必须查验上游对应版本原始许可证文件，不能默认判为宽松许可证。
- 任一 unknown、proprietary、GPL/AGPL/SSPL 或其他未获明确批准的不兼容项阻止合并。
- 条件兼容项的义务必须已落实到仓库和发行归档；否则仍视为 blocked。
- 新增依赖或锁定版本变化必须使检查失败，直到审计记录和所需 notice 同步更新。

## ADR 验证

- `specs/adrs/` 中存在连续编号的四份 ADR，状态为 Accepted，并链接 Mission、Tech Stack 和本
  Feature。
- 每份 ADR 都包含上下文、决定、被否决替代方案、正负后果、安全/隐私影响和后续阶段约束。
- ADR 不与 Constitution 冲突，不把计划技术写成现有实现，也不引入第二套公开产品契约。
- 命令兼容 ADR 明确 distribution 改名、显式卸载/安装迁移、双入口、凭据槽位和版本线。

## 范围、安全与文档审计

- 运行时依赖中不新增 FastAPI、Pydantic、Uvicorn、SQLite 扩展、OpenAI SDK、向量库、Node、扩展
  框架、媒体下载、ASR、OCR 或访问控制绕过能力。
- 源码、测试、脚本、README、ADR、归档和测试输出中不存在 Cookie、二维码密钥、API Key、
  字幕签名 URL、真实投稿标识、字幕正文或个人笔记。
- README 的安装、升级、卸载、认证和提取命令与实际入口一致，并清楚标记学习助手尚未实现。
- CHANGELOG 只记录阶段七真实交付物；不得记录阶段八/九能力。
- Mission、Tech Stack 和 Roadmap 只在其他门禁全部通过后更新，并继续把 Local API、存储、模型和
  扩展标为未实现/计划采用。

## 可合并与阶段完成条件

- [`requirements.md`](./requirements.md) 的全部范围与决策具有实现、测试或审计证据。
- [`plan.md`](./plan.md) 的八组任务全部完成，且复核时不存在无关工作区改动。
- 全量 V1 回归、双命令等价、错误边界、许可证、构建、归档、迁移和秘密审计全部通过。
- 待合并提交的 Windows CI 成功，记录提交哈希和 CI 链接；默认 CI 不访问真实网络、账号或凭据。
- 三份 Constitution、四份 ADR、README、CHANGELOG、源码、测试、锁文件和发行元数据一致。
- 只有满足以上全部条件后才能把 Roadmap 阶段七标记为已完成；该结论不表示阶段八或阶段九已经
  开始，也不表示包已上传索引、创建 Release 或发布浏览器扩展。
