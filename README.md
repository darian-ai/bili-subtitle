# bili-study

当前源码是已通过阶段九验收的 `0.2.0-alpha` 浏览器学习原型：除字幕提取与阶段八学习后端外，已经提供只监听 loopback 的 Local API，以及由 WXT、TypeScript、React 构建的 Chrome/Edge Manifest V3 侧栏。当前只提供本地安装和加载已解压扩展，不进入扩展商店。

新安装使用 `uv tool install bili-study`，提供 `bili-study extract <视频标识或URL>` 与 `bili-study auth login|status|clear`。原有 `bili-subtitle` 命令继续兼容并复用原 Credential Manager 登录状态。

已安装 `bili-subtitle 0.1.0` 的用户应先运行 `uv tool uninstall bili-subtitle`，再安装 `bili-study`；不要强制覆盖两个工具记录。

`bili-subtitle` 是一个 Windows 优先的命令行工具，用于提取 Bilibili 播放器已经提供、且当前账号可以正常访问的字幕轨道。人工字幕和 AI 字幕都会保存为平台原始 JSON，同时生成 UTF-8 编码的 SRT 文件。

它只负责取回站内已有字幕，不下载视频或音频，也不进行语音识别、OCR、翻译、润色或访问权限绕过。

## 功能概览

- 支持 BV 号、av 号、Bilibili 视频页链接和 `b23.tv` 短链。
- 支持普通 UGC 投稿的单分集和多分集视频。
- 默认处理投稿的全部分集，也可以通过 URL 的 `p` 参数或 `--page` 选择单个分集。
- 默认提取每个分集的全部可见字幕轨道，可以按平台语言代码过滤。
- 自动完成终端二维码登录，并把凭据安全保存在 Windows Credential Manager 中。
- 同时输出平台原始 JSON、SRT 和包含处理结果的 `manifest.json`。
- 重复运行时默认跳过已有文件；使用 `--force` 可以安全覆盖本次选中的字幕文件。
- 单个分集或字幕轨道失败时继续处理其他项目，并通过摘要和退出码报告结果。

## 运行要求

- Windows 10/11 和 PowerShell。
- Python 3.12 或更高版本。
- [uv](https://docs.astral.sh/uv/)。
- 可以访问 Bilibili 的网络环境。
- 用于扫码登录的哔哩哔哩手机客户端。

项目当前通过源码在本地构建和安装，暂不提供独立 EXE 或 PyPI 安装包，也不需要 FFmpeg。

## 安装

如果尚未安装 uv，请先按 [uv 官方安装说明](https://docs.astral.sh/uv/getting-started/installation/) 完成安装，并确认下面的命令可以输出版本号：

```powershell
uv --version
```

### 1. 获取源码

```powershell
git clone https://github.com/darian-ai/bili-subtitle.git
Set-Location .\bili-subtitle
```

如果本机还没有合适的 Python，可以让 uv 安装 Python 3.12：

```powershell
uv python install 3.12
```

### 2. 构建并安装命令

```powershell
uv build
uv tool install .\dist\bili_study-0.2.0a1-py3-none-any.whl
```

安装完成后验证命令：

```powershell
bili-subtitle --help
```

如果 PowerShell 提示找不到 `bili-subtitle`，运行下面的命令，然后关闭并重新打开 PowerShell：

```powershell
uv tool update-shell
```

### 升级和卸载

拉取新代码后重新构建，并强制安装新 wheel：

```powershell
git pull
uv build
uv tool install .\dist\bili_study-0.2.0a1-py3-none-any.whl
```

卸载：

```powershell
uv tool uninstall bili-study
```

## 快速开始

### 1. 登录

首次使用可以先主动登录：

```powershell
bili-subtitle auth login
```

终端会显示二维码。使用哔哩哔哩手机客户端扫码并确认后，凭据会保存到 Windows Credential Manager。工具不会要求手工复制 Cookie，也不会把 Cookie 写入项目文件。

这一步也可以省略：直接执行提取命令时，如果没有有效凭据，工具会自动显示二维码，并在登录成功后继续原来的提取任务。

检查或清除登录状态：

```powershell
bili-subtitle auth status
bili-subtitle auth clear
```

`auth clear` 只删除本机保存的凭据，不会调用 Bilibili 的账号退出接口。

### 学习后端

先创建命名知识库，并配置用户自备的 OpenAI-compatible Provider。API Key 通过隐藏输入读取，只保存到 Windows Credential Manager：

```powershell
bili-study library create my-library D:\BiliKnowledge
bili-study config provider set my-provider https://api.example.com/v1 model-name
```

从已经提取的原始字幕 JSON 构造版本化 Transcript。导入只读取本地 JSON，不会再次访问 Bilibili：

```powershell
bili-study transcript import --library my-library .\subtitle.json BV1xx411c7mD 1 123456 "标题" zh-CN "中文（AI）"
```

生成前会显示 Provider、模型和将上传的 cue 数并要求确认；也可以在自动化环境显式传入 `--yes`。相同生成指纹默认命中本地缓存：

```powershell
bili-study guide generate --library my-library --provider my-provider
bili-study guide show --library my-library GUIDE_ID
bili-study chapter generate --library my-library --provider my-provider GUIDE_ID ch001
```

个人笔记保存为独立 Markdown 文件，重新生成指南或清理可重建缓存不会覆盖笔记：

```powershell
bili-study note add --library my-library REVISION_ID 120000 "这里需要复习" --note-type question
bili-study note list --library my-library REVISION_ID
```

Embedding、跨视频问答、复习和测验仍不在本原型范围内。

### Chrome/Edge 学习侧栏

先完成知识库、Provider 和 Bilibili 登录配置，再启动 Local API。服务只监听 `127.0.0.1`，不提供局域网监听或关闭认证的参数：

```powershell
bili-study auth login
bili-study serve --port 8765
```

在另一个 PowerShell 中构建扩展：

```powershell
Set-Location .\extension
npm ci
npm run api:check
npm run lint
npm run typecheck
npm test
npm run build
```

Chrome 打开 `chrome://extensions`，Edge 打开 `edge://extensions`，启用“开发者模式”并选择“加载已解压的扩展”：

- Chrome 选择 `extension\.output\chrome-mv3`。
- Edge 选择 `extension\.output\edge-mv3`。

点击工具栏中的 bili-study 图标打开侧栏。首次连接时，在另一个 PowerShell 生成五分钟有效、单次使用的配对码：

```powershell
bili-study plugin pair
```

把配对码输入侧栏。Bearer token 只保存在扩展本地存储并绑定当前扩展 Origin；本地服务重启后 token 会失效，需要重新配对。扩展不保存或读取 Bilibili Cookie、Provider API Key、二维码密钥或字幕签名 URL。

打开普通 Bilibili 视频页后，依次选择知识库、填写已配置的 Provider 名称、检查字幕轨道，再主动点击“创建轻量学习大纲”。可容纳的字幕只调用一次模型，超预算内容才使用 Map/Reduce；详情和按章练习仍只在点击后生成。侧栏通过“大纲 / 练习 / 笔记”多页面导航展示内容，正文默认为 18px，并随用户拖动后的浏览器侧栏宽度响应，不会自动暂停视频、弹题或上传字幕。

个人时间戳笔记写入知识库的 `notes\`，AI 指南写入 `generated\videos\`；重新生成 AI 内容不会覆盖个人 Markdown。任务、指南和笔记状态保存在本机 SQLite，服务重启后会恢复未完成任务。

开发环境首次执行 Playwright 需要下载隔离测试浏览器：

```powershell
npx playwright install chromium
npm run test:e2e
```

### 2. 进入希望保存字幕的目录

字幕总是写入当前工作目录下的 `subtitles` 文件夹。例如：

```powershell
New-Item -ItemType Directory -Path D:\BiliSubtitles -Force
Set-Location D:\BiliSubtitles
```

### 3. 提取字幕

传入 BV 号：

```powershell
bili-subtitle BV1xx411c7mD
```

也可以直接传入视频链接。建议始终用引号包住 URL，避免 PowerShell 把 `&` 等查询字符解释为命令语法：

```powershell
bili-subtitle "https://www.bilibili.com/video/BV1xx411c7mD"
bili-subtitle "https://www.bilibili.com/video/BV1xx411c7mD?p=2"
```

还支持 av 号和 `b23.tv` 短链：

```powershell
bili-subtitle av123456789
bili-subtitle "https://b23.tv/xxxxxxx"
```

命令完成后会逐项显示处理结果，并输出类似下面的摘要：

```text
摘要：分集 2，轨道 3，写入 6，覆盖 0，跳过 0，无字幕 0，无匹配 0，失败 0。
```

## 输入和分集选择

主命令语法：

```text
bili-subtitle <视频标识或 URL> [--page N | --all-pages] [--lang 语言代码]... [--force]
```

支持的输入如下：

| 输入 | 示例 | 说明 |
|---|---|---|
| BV 号 | `BV1xx411c7mD` | 大小写前缀均可，工具会规范化为 `BV` |
| av 号 | `av123456789` | `av` 前缀大小写均可 |
| 视频页 URL | `https://www.bilibili.com/video/BV1xx411c7mD` | 支持 `bilibili.com`、`www.bilibili.com` 和 `m.bilibili.com` 的普通视频页 |
| 带分集的 URL | `https://www.bilibili.com/video/BV1xx411c7mD?p=2` | 默认只处理 URL 指定的 P2 |
| 短链 | `https://b23.tv/xxxxxxx` | 必须最终跳转到受支持的 Bilibili 视频页 |

分集选择规则：

| 输入方式 | 实际处理范围 |
|---|---|
| 不带 `p`，也不传分集选项 | 默认处理投稿的全部分集 |
| URL 带 `?p=N` | 只处理第 N 个分集 |
| `--page N` | 只处理第 N 个分集 |
| `--all-pages` | 明确处理全部分集 |

`--page` 和 `--all-pages` 不能同时使用。显式命令行选项会覆盖 URL 中的 `p` 参数，并在终端显示一条覆盖提示。

示例：

```powershell
# 只处理 P1
bili-subtitle BV1xx411c7mD --page 1

# 即使 URL 指向 P2，也明确处理全部分集
bili-subtitle "https://www.bilibili.com/video/BV1xx411c7mD?p=2" --all-pages

# 显式选择 P3；--page 会覆盖 URL 中的 p=2
bili-subtitle "https://www.bilibili.com/video/BV1xx411c7mD?p=2" --page 3
```

一次命令只接受一个普通 UGC 投稿，不会自动展开合集中的其他投稿，也不支持一次传入多个 URL。

## 按语言过滤字幕

不传 `--lang` 时，工具按平台返回顺序提取所有当前可见字幕轨道。`--lang` 使用平台提供的语言代码，采用精确且区分大小写的匹配方式。

只提取一种语言：

```powershell
bili-subtitle BV1xx411c7mD --lang zh-CN
```

提取多种语言时重复传入选项：

```powershell
bili-subtitle BV1xx411c7mD --lang zh-CN --lang en-US
```

平台实际语言代码可能因字幕轨道而异。可以先不加 `--lang` 执行一次，再从生成的 `manifest.json` 中查看每条轨道的 `language`。如果所选分集存在字幕，但没有符合过滤条件的轨道，终端会显示“无匹配字幕”；这是正常结果，不算失败。

同一种语言可能有多条轨道。工具会保留轨道 ID，并分别生成文件，不会按语言或显示名称擅自去重。

## 已有文件和覆盖规则

默认情况下，工具不会覆盖已有字幕：

- JSON 和 SRT 都存在时，两者都跳过。
- 只缺少其中一个文件时，仅补齐缺失文件，已有文件保持不变。
- 两个文件都不存在时，正常写入两者。
- 再次运行且所有目标都存在时，摘要会标记“全部已有文件跳过”。

需要重新下载并替换本次选中的 JSON 和 SRT 时使用：

```powershell
bili-subtitle BV1xx411c7mD --force
```

`--force` 不会清空投稿目录，也不会删除本次未选中的旧文件。

## 输出文件

默认输出结构：

```text
当前工作目录/
└── subtitles/
    └── 视频标题 [BV号]/
        ├── P01-分集标题.语言.轨道ID.json
        ├── P01-分集标题.语言.轨道ID.srt
        ├── P02-分集标题.语言.轨道ID.json
        ├── P02-分集标题.语言.轨道ID.srt
        └── manifest.json
```

- `.json` 是字幕正文接口返回的原始内容。
- `.srt` 从同一份 JSON 忠实转换，保留字幕文字、标点、空格、时间范围和分段。
- `manifest.json` 记录投稿、分集、CID、字幕轨道、相对文件名和本次处理结果。
- 人工字幕和 AI 字幕会在 manifest 中分别标记为 `human` 和 `ai`。
- 文件名会自动处理 Windows 非法字符、保留名称、重复名称和过长路径。

当前版本不支持通过参数指定其他输出目录。请在运行命令前切换到希望存放 `subtitles` 的目录。如果提示当前工作目录过长，请换到更短的路径后重试，例如 `D:\BiliSubtitles`。

## 参数速查

| 参数 | 作用 |
|---|---|
| `video` | 必填的视频标识或 URL；不传参数时显示帮助 |
| `--page N` | 只处理第 N 个分集，N 必须为正整数 |
| `--all-pages` | 明确处理投稿的全部分集 |
| `--lang CODE` | 按平台语言代码过滤，可以重复使用 |
| `--force` | 重新下载并覆盖本次选中的已有 JSON/SRT |
| `--help` | 显示完整命令帮助 |

查看认证子命令：

```powershell
bili-subtitle auth --help
```

## 退出码

脚本或自动化任务可以读取 PowerShell 的 `$LASTEXITCODE`：

```powershell
bili-subtitle BV1xx411c7mD --page 1
$LASTEXITCODE
```

| 退出码 | 含义 |
|---|---|
| `0` | 正常完成，包括无字幕、无匹配字幕或全部文件跳过 |
| `1` | 至少有一个有效结果，同时有其他分集、轨道或 manifest 失败 |
| `2` | 输入、认证或元数据等命令级失败，或者没有任何有效轨道结果 |

## 常见问题

### 输入视频链接后提示 URL 不受支持

请确认输入的是普通 Bilibili 视频页或 `b23.tv` 短链，而不是番剧、影视、课程、互动视频、收藏夹、UP 主空间或合集页面。完整 URL 建议用双引号包住。

### 没有有效登录状态

主命令通常会自动进入扫码流程。也可以手动清除旧凭据后重新登录：

```powershell
bili-subtitle auth clear
bili-subtitle auth login
```

如果二维码过期，重新执行登录命令即可。登录等待不会无限持续。

### 显示“无字幕”

这表示当前账号在该分集上没有可见的站内字幕轨道。工具不会下载媒体后执行 ASR 或 OCR，因此不会生成识别字幕。

### 显示“无匹配字幕”

该分集存在字幕轨道，但没有轨道精确匹配传入的 `--lang`。去掉语言过滤重新运行，并检查 `manifest.json` 中的平台语言代码。

### 命令执行后找不到文件

检查执行命令时所在目录。结果不会固定写入源码目录或用户主目录，而是写入当时工作目录下的 `subtitles`。

```powershell
Get-Location
Get-ChildItem .\subtitles
```

### 某个分集或轨道失败

工具会继续处理其他分集和轨道，已成功写入的结果会保留。请先查看最终摘要和退出码；网络错误可以稍后重试，重复运行默认只补齐缺失文件，不会覆盖已有结果。

## 支持范围和限制

当前 V1 支持普通 UGC 投稿及当前账号通过正常网页流程可见的人工/AI 字幕，不支持：

- 番剧、影视、课程和互动视频。
- 收藏夹、UP 主空间、跨投稿合集和批量 URL。
- 视频、音频、封面或弹幕下载。
- ASR、OCR、翻译、润色、繁简转换和双语合并。
- 付费、地区、会员、登录、风控等访问控制绕过。
- 自定义输出目录、配置文件、GUI、独立 EXE 和自动更新。

平台本身没有字幕、字幕未对当前账号开放或平台拒绝访问时，工具会明确报告结果，不会启用替代识别或绕过路径。

## 开发与验证

安装锁定的开发环境：

```powershell
uv sync --locked --dev
```

在源码环境直接运行：

```powershell
uv run bili-subtitle --help
uv run bili-subtitle BV1xx411c7mD --page 1
```

运行完整质量检查：

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv build
uv run python scripts/verify_release.py dist --rebuild-sdist
.\scripts\verify_isolated_install.ps1 -Wheel .\dist\bili_study-0.2.0a1-py3-none-any.whl
```

扩展门禁在 `extension` 目录运行：

```powershell
npm ci
npm run api:check
npm run lint
npm run typecheck
npm test
npm run test:e2e
npm run build
```

默认自动化测试不访问真实 Bilibili 网络，也不读取本机真实凭据。

## 项目文档

- [项目使命与产品边界](specs/mission.md)
- [技术栈与架构约束](specs/tech-stack.md)
- [实施路线与当前状态](specs/roadmap.md)
- [版本变更记录](CHANGELOG.md)

`specs/` 是产品行为和技术约束的唯一权威来源；README 只提供安装与使用入口。
