# 阶段六：质量与交付验证及可发布标准

## 自动化质量门禁

在仓库根目录运行：

```powershell
uv sync --locked --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
git diff --check
```

全部返回 `0`；pytest 分支覆盖率不低于 90%，且无真实网络、账号、Credential Manager 或等待。
待合并提交的 Windows GitHub Actions 必须执行同等门禁并成功。

## 自动化契约矩阵

| 领域 | 必须具备的直接证据 |
|---|---|
| 输入 | BV、av、完整 URL、短链；URL `p`、默认全部、`--page`、`--all-pages` 优先级与互斥；单投稿边界 |
| 认证 | 无/损坏/有效/失效凭据；未扫码、待确认、成功、过期、取消、失败、超时、网络重试；跨进程存储端口与一次自动恢复 |
| 字幕 | 人工、AI、多语言、同语言多轨道、无字幕、无匹配、需登录、不可访问、网络与结构异常；签名 URL 立即消费 |
| 导出 | 原始 JSON 字节、忠实 SRT、确定 manifest、UTF-8、原子写入与各故障点、旧目标保护 |
| 完整流程 | 默认全部、单页、全部轨道、语言过滤、局部失败、重复跳过、缺项补齐、`--force`、摘要及 `0|1|2` |
| Windows | 非法字符、控制字符、保留名、尾随字符、大小写冲突、稳定消解、240 字符预算、临时文件清理 |

矩阵中的每项必须指向实际测试名或人工记录；仅有间接覆盖率不算通过。默认测试中任何未替换的
Bilibili 网络请求、真实 keyring 读取或真实睡眠均视为失败。

## 安全与异常响应验证

- 用不同的唯一伪 Cookie、二维码内容/密钥、签名 URL、请求头、响应正文和绝对路径作为金丝雀。
- 检查 stdout、stderr、日志、异常及其链、`repr`、测试失败输出、manifest、路径、README、
  wheel、sdist 和全部被提交文件，均不得包含金丝雀。
- 对元数据、认证、轨道和正文接口覆盖 HTTP 客户端错误、服务端错误、超时/连接故障、平台拒绝、
  未知错误码、空/截断/非 JSON、字段缺失、错误类型和异常嵌套结构；分类明确且不透传正文。
- 证明失败不会触发备用私有接口、媒体下载、识别、翻译或绕过，也不会无限重试。

## 重复运行与 Windows 文件系统验证

- 对 JSON/SRT 的四种存在组合分别验证默认跳过或缺项补齐；全跳过不下载正文且退出 `0`。
- `--force` 安全替换两项；任一准备或替换失败不损坏旧文件、不留下临时文件，并如实记录局部结果。
- 多分集/多轨道中的路径、网络、结构或导出失败只影响对应项目，后续项目继续且既有成功结果保留。
- 在 Windows 临时目录检查非法名、保留名、尾随字符、大小写等价冲突、长工作目录、确定命名、
  输出根约束和 manifest 相对路径；安装后的命令也要在仓库外目录成功运行。

## 构建产物验证

从确认只指向仓库 `dist` 的路径清理旧产物后运行：

```powershell
uv build
```

- 恰有当前版本的 wheel 与 sdist，均可读取且元数据一致。
- wheel 含 `bili_subtitle` 包和 `bili-subtitle = bili_subtitle.cli:main` 入口；Python 要求与运行时依赖
  和 `pyproject.toml` 一致。sdist 包含重建所需文件及 README/Constitution 链接目标。
- 两类归档不含 `.venv`、缓存、覆盖率、`dist` 自嵌套、真实/伪凭据、二维码、签名 URL、字幕输出、
  临时文件或无关开发制品。
- 从 sdist 重建 wheel 或由隔离构建检查证明源码分发可独立构建。

## 隔离 `uv tool install` 验证

使用新建临时根目录，并在设置前后解析绝对路径，确保不指向用户默认目录：

```powershell
$env:UV_TOOL_DIR = '<临时根>\tools'
$env:UV_TOOL_BIN_DIR = '<临时根>\bin'
uv tool install '<本地 wheel 绝对路径>'
```

随后启动全新 PowerShell 进程，只在该子进程将隔离 bin 置于 `PATH`，切换到仓库外临时工作目录，
运行 `bili-subtitle --help` 并返回 `0`。同时确认不是从仓库、`.venv` 或 `uv run` 导入。
不得列出、卸载或覆盖用户默认 uv tools；结束时只清理已核实的临时根目录。

## README 与唯一真实来源审计

- README 的安装、登录、提取、参数示例及开发命令与实际 `--help` 和验证结果一致。
- README 链接 Mission、Tech Stack 和 Roadmap，并声明三者分别是产品、技术和阶段状态的权威来源。
- README 不重新维护完整范围、错误码、架构、依赖选择或阶段状态；没有与 Constitution 冲突的承诺。
- 文档不含真实账号、投稿标识、字幕正文、Cookie、二维码、签名 URL 或绕过建议。

## 全依赖、架构与禁止能力审计

- `pyproject.toml`、`uv.lock`、安装环境和归档元数据的直接/传递依赖一致；每个直接运行时依赖均可
  追溯到 Tech Stack 用途，没有未声明导入或多余运行时依赖。
- 领域层仅依赖标准库；CLI 不直接联网、读 Cookie 或写字幕；平台字段、凭据和文件实现仍位于适配层。
- 对源码、测试、脚本、CI、文档、锁文件和归档进行关键词搜索并人工复核调用路径，确认不存在媒体、
  音频、封面下载、FFmpeg、ASR、OCR、翻译、浏览器自动化、WBI、APP 私有接口、访问控制绕过、
  异步框架、任务队列、数据库或插件系统。
- 不生成 EXE、不发布包索引或 Release、不加入自动更新；发布边界仍为本地标准构建与 uv 工具安装。

## 真实平台 Windows 人工验收

在不录屏、不复制响应且仅使用当前账号正常可见内容的 Windows 终端执行：

1. 使用 Credential Manager 中既有有效凭据，或通过二维码正常登录；确认主命令无需手工 Cookie。
2. 对一个含 AI 字幕的普通 UGC 投稿运行默认命令，确认每条所选可见轨道生成 JSON、SRT 和 manifest。
3. 人工抽查同一轨道 JSON 与 SRT 的文字、标点、空格、分段和时间对应；记录仅写“通过/失败”。
4. 对普通多分集投稿不带分集参数运行，确认按平台顺序处理全部分集。
5. 在独立清洁目录以 `--page N` 运行，确认只处理指定分集。
6. 原目录重复运行，确认已有文件逐项跳过、无不必要正文下载且退出 `0`。
7. 再以 `--force` 运行，确认选中结果被安全覆盖，未选文件不被删除。
8. 核对所有场景的 P 序号、轨道身份、摘要和退出码；确认无 traceback、秘密或签名 URL。

记录不得包含账号名/UID、Cookie、二维码或密钥、请求头、响应正文、字幕正文、真实投稿 BV/av/CID、
文件标题或签名 URL。若需保留输出供人工比较，应只留在用户明确控制的临时目录，不提交仓库。

## Mission 成功标准逐项证据

可发布结论必须逐项说明以下证据位置：

1. 一个主命令完成提取且无需手工 Cookie：认证恢复自动化与真实 Windows 流程。
2. AI 字幕每条所选轨道生成 JSON/SRT：离线固定响应测试与真实 AI 投稿验收。
3. 单/多分集、多语言、同语言多轨道不覆盖：完整流程矩阵与真实多分集验收。
4. SRT 忠实对应原始 JSON：转换边界测试与人工抽查。
5. 无字幕和访问失败明确区分：错误分类测试。
6. 重复运行、部分失败和退出码正确：重复/故障矩阵。
7. 测试和实际输出无凭据或签名 URL：金丝雀测试与人工安全检查。
8. 全库无媒体下载、ASR、OCR 或绕过路径：依赖与调用路径审计。

任一项缺少直接证据都不得声称 V1 完成。

## CI 与可合并、可发布条件

- Windows CI 在待合并提交上完成锁定同步、全量测试、覆盖率、Ruff、格式、strict Pyright、构建、
  归档检查和隔离 `uv tool install`；CI 不访问 Bilibili 或真实凭据。
- 本文全部自动化、构建、安装、README、依赖、安全、范围和真实人工验收均有脱敏记录且通过。
- [`requirements.md`](./requirements.md) 的每项范围和决策具有直接实现或验证证据，八组计划全部完成。
- Mission 所有成功标准和不可违背原则、Tech Stack 约束、Roadmap 阶段六验收及 V1 完成定义逐项通过。
- feature spec、README、源码、测试、CI、锁文件和构建元数据一致；工作区无无关改动，生成产物未误提交。
- 只在上述证据齐全后更新 Roadmap 阶段状态。阶段六合并即表示 V1 可按文档本地构建和安装，
  不表示已经上传包索引或创建公开 Release。

## 验证记录约束

后续仅追加环境版本、命令形态、测试数量、覆盖率、脱敏场景、退出码、构建文件名/哈希、提交哈希和
CI 链接。不得记录账号、Cookie、二维码、签名 URL、请求头、响应正文、字幕正文或真实投稿标识。

## 2026-08-21 自动化实施记录

当前状态：自动化、文档、构建、隔离安装及审计已完成；真实 AI 字幕与多分集投稿人工验收、待合并提交的 Windows CI 尚未完成，因此不得声称阶段六或 V1 完成。

### 契约—测试追踪矩阵

| 领域 | 直接证据 |
|---|---|
| 输入 | `test_parse_supported_inputs`、`test_parse_short_url`、`test_default_selects_all_pages`、`test_url_page_selects_one`、`test_explicit_selection_overrides_url_page`、`test_invalid_page_and_mutual_exclusion` |
| 认证 | `test_credential_rejects_invalid`、`test_login_reuses_valid_credential`、`test_login_state_sequence_saves_without_leaks`、`test_login_terminal_states_do_not_save`、`test_login_times_out_with_fake_clock`、`test_login_retries_transient_network_errors_within_limit`、`test_keyring_store_paths`、`test_auth_login_handles_ctrl_c_without_traceback` |
| 字幕 | `test_ai_track_full_http_to_files_integration`、`test_discovers_in_order_and_immediately_downloads_raw_bytes`、`test_legal_no_subtitles`、`test_http_failures_have_stable_classification`、`test_platform_codes_have_stable_classification`、`test_malformed_discovery_is_not_no_subtitles`、`test_malformed_body_is_classified_without_raw_content`、`test_protocol_relative_url_is_https_and_consumed_without_retention` |
| 导出 | `test_export_preserves_raw_json_and_publishes_manifest_last`、`test_srt_round_half_up_and_preserves_order_and_text`、`test_any_existing_target_rejects_before_publication`、`test_temporary_publication_failures_are_cleaned`、`test_manifest_failure_keeps_published_subtitles` |
| 完整流程 | `test_full_flow_filters_in_platform_order_and_skips_existing`、`test_track_failure_isolated_and_exit_codes`、`test_no_match_missing_repair_force_and_manifest_failure`、`test_second_replace_failure_preserves_first_and_records_partial_publish`、CLI 摘要和错误映射测试 |
| Windows | `test_sanitize_component_covers_windows_edge_cases`、`test_collision_resolution_is_stable_when_track_order_changes`、路径预算三项测试、隔离安装脚本的新 PowerShell 仓库外调用 |
| 安全与交付 | 认证/字幕适配器的秘密泄漏测试、`test_committed_delivery_files_do_not_contain_secret_canaries`、归档校验器测试、`scripts/verify_release.py` |

### 本地门禁与交付证据

- 环境：Windows，CPython 3.12.13，uv 锁定环境。
- `uv sync --locked --dev`、`uv run pytest`、Ruff lint、Ruff format check、strict Pyright、`git diff --check` 均返回 `0`。
- pytest：187 项通过；总覆盖率 91.94%，满足分支覆盖门槛；测试使用固定响应、假凭据端口和假时钟。
- `uv build` 从本地源码生成且仅生成 `bili_subtitle-0.1.0-py3-none-any.whl` 与 `bili_subtitle-0.1.0.tar.gz`；`scripts/verify_release.py` 校验包、入口、Python 要求、直接依赖、README、三份 Constitution 和禁止文件，返回 `0`。
- `scripts/verify_isolated_install.ps1` 将两个 uv 目录限定到经绝对路径确认的临时根，从本地 wheel 安装，并在仓库外工作目录的新 PowerShell 进程仅通过隔离 PATH 调用 `bili-subtitle --help`，返回 `0`；脚本只清理自己创建的临时根，未查询或修改用户默认工具状态。
- Windows CI 已扩展为在原有门禁后执行构建、归档校验及隔离安装；推送后的 run 证据待补。

### 依赖、架构与禁止能力审计

- `pyproject.toml`、`uv.lock`、`uv tree --locked` 和两类归档元数据一致。五个直接运行时依赖用途分别为：HTTPX 平台 HTTP，keyring Credential Manager，qrcode 终端二维码，Rich 终端呈现，Typer CLI；其传递依赖仅服务这些调用和 Windows 凭据后端。
- 领域层只导入标准库；平台网络位于 infrastructure，凭据边界位于 credentials/auth，字幕文件写入位于 export；CLI 只装配并呈现结果。
- 对源码、测试、脚本、CI、README、配置、锁文件和归档的关键词及调用路径审计未发现媒体/音频/封面下载、FFmpeg、ASR、OCR、翻译、浏览器自动化、WBI、APP 私有接口、访问控制绕过、异步框架、任务队列、数据库或插件系统。命中项均为 Constitution 禁止描述、测试中的字幕正文下载方法名或开发工具自身依赖，并不形成禁止能力。
- 未生成 EXE，未发布包索引或 Release，未加入自动更新；交付边界仍为标准 wheel/sdist 和本地 `uv tool install`。

### 待完成证据

- 使用真实平台正常权限对一个含 AI 字幕的普通 UGC 投稿完成人工端到端与 JSON/SRT 忠实性抽查。
- 使用真实普通多分集 UGC 投稿验证默认全部、`--page N`、重复跳过、`--force`、身份、摘要及退出码。
- 在待合并提交上取得扩展后的 Windows CI 成功 run，并补充链接和提交哈希。

### 2026-08-21 Windows 隔离入口编码修复

- Windows Quality run `32412642906` 的测试、Ruff、Pyright、构建、归档校验均通过；隔离
  `uv tool install` 成功，但仓库外的新 Windows PowerShell 调用 `bili-subtitle --help`
  时，Python stdout 采用 cp1252，中文帮助触发 `UnicodeEncodeError`，隔离入口门禁失败。
- 控制台入口现在于 Typer 输出前将标准输出和标准错误的 `TextIOWrapper` 重新配置为 UTF-8，
  并以 `backslashreplace` 兜底不可编码的异常字符；公开中文帮助和运行输出仍输出真实 UTF-8，
  不删除、不静默或替换中文界面。
- `test_main_reconfigures_non_utf8_standard_streams` 以 cp1252 风格的 stdout/stderr 验证两路
  中文输出均成为可解码 UTF-8；`test_help_survives_cp1252_fresh_process` 在 fresh Python 子进程
  中将两路流预置为 cp1252，再运行完整 `--help`，验证退出码 `0` 且中文帮助完整。
- 修复后本地 CPython 3.12.13 全量 193 项测试通过，总覆盖率 91.93%；Ruff lint、Ruff
  format check、strict Pyright 和 `git diff --check` 均返回 `0`。待合并提交的 Windows CI
  成功 run 仍待补，不得据此声明阶段六完成。

## 2026-08-21 独立复核与加固记录

- 独立复核在提交 `dca9835e2db26a4ed1b7117d5004b989298ecaa9` 上补充默认网络封锁；任何未由替身接管的 socket 连接都会使 pytest 立即失败。全量 191 项测试通过，分支覆盖率 91.94%。
- `scripts/verify_release.py` 现同时检查 wheel/sdist 成员内容中的秘密金丝雀，并以临时目录从 sdist 独立重建 wheel；临时目录由标准库管理，不接触用户工具目录。
- 隔离安装再次从本地 wheel 成功安装，并在仓库外的新 PowerShell 仅通过隔离 `PATH` 调用帮助；额外用预置哨兵值证明脚本结束后完整恢复调用者原有 `UV_TOOL_DIR` 和 `UV_TOOL_BIN_DIR`。
- README 默认输出入口修正为当前工作目录下的 `subtitles`，具体文件规则仍只链接 Mission；安装、升级、卸载、认证、主命令与质量命令均与实际帮助及执行结果一致。
- 归档名称为 `bili_subtitle-0.1.0-py3-none-any.whl` 与 `bili_subtitle-0.1.0.tar.gz`；身份、版本、Python 要求、五项直接运行时依赖、控制台入口和发布文件范围一致。最终归档哈希须以待合并提交在 CI 中重新构建的产物为准。
- 项目当前未声明许可证或作者，也不发布到包索引或 Release。复核不擅自替所有者作法律授权或身份决定；这不阻碍当前经授权的本地构建/安装边界，任何外部分发前必须先由所有者确定并补齐许可证元数据。
- `uv sync --locked --dev`、pytest、Ruff lint、Ruff format check、strict Pyright、构建、归档及 sdist 重建校验、隔离工具安装和 `git diff --check` 均返回 `0`。真实 AI 投稿、真实多分集投稿及待合并提交 Windows CI 仍未完成，阶段六/V1 仍不得声明完成。
