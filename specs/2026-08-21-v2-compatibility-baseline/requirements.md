# 阶段七：V2 兼容基线需求

## 文档信息

| 项目 | 内容 |
|---|---|
| Feature | V2 Compatibility Baseline |
| 工作分支 | `feature/v2-compatibility-baseline` |
| 上游规格 | [`mission.md`](../mission.md)、[`tech-stack.md`](../tech-stack.md)、[`roadmap.md`](../roadmap.md) |
| 状态 | 已完成 |
| 日期 | 2026-08-21（2026-08-22 完成验收） |

## 背景与目标

V1 字幕提取已经通过阶段零至阶段六验收。阶段七的产品、技术和路线决策已经写入三份
Constitution，但许可证、ADR、核心整改、导出端口和新命令基线仍未实现。本 Feature 在不破坏
V1 的前提下完成阶段七全部剩余工作，使后续阶段能够在稳定的命令、应用端口、安全边界和发行
身份上继续演进。

本阶段只交付兼容基线，不交付 Local API、浏览器扩展、模型调用、知识库、Transcript、学习指南
或笔记功能。任何用户文档和命令帮助都必须真实区分“兼容提取已可用”与“V2 学习能力尚未实现”。

## 范围

- 添加标准 Apache-2.0 许可证文件、SPDX 包元数据和完整依赖许可证审计。
- 建立 Local API 安全、AI 生成契约、本地存储、命令与发行兼容四份 Accepted ADR。
- 在访问 Credential Manager、创建 HTTP Client 或启动登录前完成纯输入与纯参数校验。
- 区分登录期间中断与认证后的提取中断，不再把所有 `KeyboardInterrupt` 都描述为登录取消。
- 收窄应用编排中的异常捕获，只把已声明的预期端口故障转换为局部失败。
- 通过应用层 `ExportPort` 移除完整提取编排对具体文件导出模块的直接依赖。
- 新增 `bili-study` 命令入口，同时保留 `bili-subtitle` 的公开语法与行为。
- 将 Python distribution 改名为 `bili-study`，发布兼容基线版本 `0.1.1`，并定义 V1 安装迁移路径。
- 扩展测试、构建、归档、隔离安装、README、CHANGELOG 和 Constitution 状态。

## 公开命令契约

新入口提供以下已经可用的命令：

```text
bili-study extract <视频标识或URL> [--page N | --all-pages] [--lang 语言代码]... [--force]
bili-study auth login|status|clear
```

兼容入口继续提供：

```text
bili-subtitle <视频标识或URL> [--page N | --all-pages] [--lang 语言代码]... [--force]
bili-subtitle auth login|status|clear
```

- `bili-study extract` 和 `bili-subtitle` 必须调用同一应用流程，不复制输入、认证、字幕、导出、
  摘要或退出码规则。
- 对同一固定输入和替身依赖，两者必须得到相同的选择结果、网络调用顺序、输出文件字节、
  manifest 内容、结果分类和 `0|1|2` 退出码。帮助中的程序名和命令层级可以不同。
- `bili-study auth` 与兼容认证命令共享实现和 Credential Manager 数据。
- 不带参数运行 `bili-study` 时显示当前可用命令帮助并正常退出；未知命令按 Typer 参数错误返回
  `2`。
- `library`、`config`、`plugin`、`serve` 和 `doctor` 本阶段不注册占位命令。README 和帮助可以说明
  学习能力仍在规划中，但不得展示为可调用功能。
- `bili-subtitle` 的已有脚本调用、参数含义、输出目录、JSON/SRT/manifest 格式、摘要和退出码不得
  因新入口退化。

## Distribution、版本与安装迁移

- `[project].name` 改为 `bili-study`，版本改为 `0.1.1`；构建产物使用规范化名称
  `bili_study-0.1.1-py3-none-any.whl` 和 `bili_study-0.1.1.tar.gz`。
- 同一 wheel 包含新的 `bili_study` 包和现有 `bili_subtitle` 包，并注册 `bili-study`、
  `bili-subtitle` 两个 console script。
- 两个 Python 包暴露的版本信息必须来自同一版本来源并一致为 `0.1.1`，不得在源码、构建脚本和
  归档校验器中维护相互漂移的版本常量。
- 已安装 `bili-subtitle 0.1.0` 的用户采用显式迁移：先运行
  `uv tool uninstall bili-subtitle`，再从新 wheel 安装 `bili-study`。不得推荐强制覆盖导致两个 uv
  tool 记录争用 `bili-subtitle.exe`。
- 新 distribution 安装后同时拥有新旧命令；卸载身份变为 `bili-study`。
- Bilibili 会话继续使用现有 Credential Manager 服务名 `bili-subtitle` 和账号名 `default`，从而
  复用 V1 登录状态。未来模型 API Key 必须使用独立槽位，不属于本阶段。
- 版本线定义为：阶段七 `0.1.1`；阶段八开发构建使用 `0.2.0.devN`；阶段九原型从
  `0.2.0a1` 开始；阶段十公开本地安装 MVP 使用 `0.2.0`。阶段七不得使用 `0.2.0` 版本暗示学习
  功能已经可用。

## 输入、认证与中断顺序

- CLI 首先执行不需要 I/O 的参数互斥、空语言和视频输入语法校验；纯无效输入必须在创建
  HTTP Client、读取 Keyring、检查登录或显示二维码之前返回 `2`。
- 合法 `b23.tv` 短链只完成本地格式校验后进入网络阶段；短链解析、元数据和字幕请求仍使用同一
  安全 HTTPX Client。
- 纯解析结果应传给后续元数据选择流程，不能为了调整顺序在登录后重复解析或复制解析规则。
- `auth login` 或提取命令的自动登录期间收到 Ctrl+C 时，输出 `错误：登录已取消。`，返回 `2`。
- 已取得有效会话后，在短链、元数据、字幕或导出阶段收到 Ctrl+C 时，输出
  `错误：字幕提取已取消。`，返回 `2`。两类场景均不得输出 traceback、响应正文或凭据。

## 错误分类与安全边界

- 字幕发现、正文取得、路径规划、SRT 准备、文件发布和 manifest 发布只能捕获各端口明确声明的
  预期错误类型；`NoSubtitles` 继续作为正常空字幕结果。
- 已声明的字幕网络、访问、平台结构和导出错误按 V1 规则转为分集级或轨道级失败，其他分集和
  轨道继续处理，最终仍按 `0|1|2` 聚合。
- `RuntimeError`、`AssertionError`、`TypeError` 等未声明的编程错误不得在应用层被伪装为“轨道
  发现失败”“路径规划失败”“字幕处理失败”或 manifest 失败。
- 未知异常从应用层冒泡至 CLI 最外层；CLI 只输出稳定的通用内部错误，不拼接异常文本、不显示
  traceback，并返回 `2`。测试与开发仍可直接调用应用函数观察原始异常类型。
- 部分文件已经安全发布后发生的预期发布错误必须携带已发布目标集合，使现有逐文件动作和局部
  成功语义保持不变；该信息不得包含文件内容、远端 URL 或凭据。
- 清理字幕适配器待消费地址的行为必须在所有正常、预期失败和中断路径执行；清理不得掩盖原始
  失败。

## 导出端口与依赖方向

- 在应用层定义 `ExportPort` Protocol，由 `run_extraction` 显式接收；CLI 负责注入文件系统适配器。
- 端口覆盖完整流程使用的全部输出能力：输出路径规划、旧 manifest 安全读取、SRT 渲染、字幕
  文件批量发布和最终 manifest 原子发布。
- `OutputPlan`、发布请求、部分发布结果/错误等跨边界类型归应用层或领域层所有；应用模块不得
  导入 `bili_subtitle.infrastructure.export` 中的具体函数、类或异常。
- 文件系统适配器继续复用 V1 的 Windows 净化、240 字符预算、历史路径安全校验、UTF-8 SRT、
  同目录临时文件和原子替换实现，不重新实现另一套导出算法。
- 缺失、损坏或不安全的旧 manifest 仍视为无可复用历史，不允许其覆盖当前确定性规划；已声明的
  当前发布故障则必须进入结果聚合。
- 端口替换是内部架构重构，不改变 manifest schema、文件命名、原始 JSON 忠实性或现有文件
  `written|replaced|skipped` 语义。

## Apache-2.0 与依赖许可证审计

- 根目录添加未经改写的 Apache License 2.0 正文 `LICENSE`，包元数据使用 SPDX 表达式
  `Apache-2.0`，wheel 和 sdist 均包含许可证文件。
- 审计覆盖 `uv.lock` 中的运行时、开发及全部传递依赖，并覆盖 `[build-system].requires` 及其实际
  使用的传递构建依赖。构建依赖必须以可复现的已审计版本参与 CI。
- 每个审计项记录规范包名、锁定版本、用途/分发状态、许可证 SPDX 标识、权威来源、与
  Apache-2.0 项目的兼容结论及必须履行的 notice/source 等义务。
- 权威证据优先使用上游仓库对应版本的 LICENSE/COPYING/NOTICE 和发布元数据；不得只依赖可能
  缺失或矛盾的 PyPI classifier。
- 运行时与构建产物携带的第三方内容必须满足其许可证义务；确有要求时添加并打包第三方 notice。
  开发工具虽不随 wheel 分发，也必须具有允许项目开发和 CI 使用的已核实许可证。
- 提供离线检查，保证当前锁文件与审计清单一一对应；新增、删除、改版、未知、专有或不兼容项
  必须使门禁失败并要求重新审计。许可证兼容性结论是工程发布门禁，不替代专业法律意见。

## ADR

在 `specs/adrs/` 建立编号、日期、状态、上下文、决策、替代方案和后果一致的文档：

1. `0001-local-api-security.md`：只绑定 loopback、配对码、Origin 绑定、Bearer token、Host/Origin/
   CORS/请求限制、持久 job 和扩展不得接触凭据。
2. `0002-ai-generation-and-evidence.md`：OpenAI-compatible Provider、用户主动上传、完整字幕
   Map/Reduce、按需详情、严格 schema/cue 校验、一次修复和 Prompt injection 边界。
3. `0003-local-storage-and-personal-content.md`：配置、Credential Manager、SQLite、知识库目录、迁移
   备份、个人内容与可重建生成物分离。
4. `0004-command-distribution-and-versioning.md`：distribution 改名、双入口、0.1.1 迁移、凭据槽位、
   0.2.0 版本线和 V1 行为兼容。

ADR 只冻结后续阶段已经批准的边界，不提前添加 FastAPI、SQLite、模型或扩展依赖和实现。

## 文档与阶段状态

- README 以当前可用能力为准，说明 `bili-study extract|auth`、兼容 `bili-subtitle`、新安装方式和
  已安装 V1 用户的卸载/重装迁移步骤。
- README 可以说明学习助手正在开发，但不得给出尚不存在的配置、服务、插件或 AI 使用教程。
- CHANGELOG 记录许可证、发行改名、双命令、兼容整改和架构端口，不把阶段八/九能力写为完成。
- 只有 [`validation.md`](./validation.md) 全部通过后，才把 Mission 的命令状态、Tech Stack 的新
  CLI 状态和 Roadmap 阶段七状态更新为已完成；Local API、模型、存储和扩展继续标记为计划采用。

## 不在范围内

- Transcript revision、cue/evidence、StudyGuide、章节、问题、Reflection 或 AI 评测实现。
- Provider 配置、API Key 槽位、OpenAI-compatible HTTP 请求或真实模型调用。
- 命名知识库、SQLite、migration、任务、缓存、Markdown 笔记或生成内容发布。
- FastAPI、Uvicorn、Local API、配对 token、浏览器扩展、Node.js、WXT、React、Vitest 或
  Playwright。
- 向量检索、Embedding、复习、测验、导图、Anki、批量入库或跨视频能力。
- 真实 Bilibili 投稿重新验收；阶段七只要求 V1 固定响应回归、构建和隔离安装继续通过。

## 已确定决策

1. 本 Feature 一次覆盖阶段七全部待办，不拆分治理与工程基线。
2. 新命令只开放可真实复用的 `extract` 和 `auth`，不注册未来功能占位。
3. distribution 改名为 `bili-study 0.1.1`，但同一 wheel 保留旧命令和旧 Python 包。
4. 已安装用户显式卸载旧 distribution 后再安装新 distribution，不采用强制覆盖。
5. Bilibili Credential Manager 槽位保持 `bili-subtitle/default`，避免发行改名破坏凭据。
6. 预期错误局部隔离，未知错误应用层冒泡并由 CLI 脱敏，不再使用兜底 `except Exception` 伪分类。
7. 许可证审计覆盖全部锁定、开发和构建依赖；未知或不兼容项阻止合并。
8. 阶段七完成后只宣告兼容基线可用，不宣告任何视频学习功能可用。
