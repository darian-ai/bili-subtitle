"""New command tree backed by the existing extraction and authentication handlers."""

from __future__ import annotations

import json
import socket
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated

import typer

from bili_study.domain import DomainError, new_note
from bili_study.provider import (
    OpenAIChatAdapter,
    ProviderConfig,
    ProviderConfigStore,
    ProviderError,
    ProviderSecretStore,
)
from bili_study.services import (
    GuideGenerator,
    generation_usage,
    guide_from_payload,
    import_bilibili_json,
    render_guide_markdown,
)
from bili_study.storage import (
    AppPaths,
    Library,
    LibraryRegistry,
    StorageError,
    StudyRepository,
    library_database,
    publish_generated,
    publish_note,
)
from bili_subtitle.cli import (  # pyright: ignore[reportPrivateUsage]
    _configure_standard_streams,  # pyright: ignore[reportPrivateUsage]
    _run_app,  # pyright: ignore[reportPrivateUsage]
    auth_app,
    extract,
)

app = typer.Typer(
    add_completion=False,
    help="Bilibili 本地优先视频学习助手。",
    no_args_is_help=False,
    rich_markup_mode=None,
)
app.command("extract")(extract)
app.add_typer(auth_app, name="auth")
library_app = typer.Typer(help="管理本地命名知识库。", no_args_is_help=True)
config_app = typer.Typer(help="管理非秘密配置与 Provider Key。", no_args_is_help=True)
provider_app = typer.Typer(help="管理 OpenAI-compatible Provider。", no_args_is_help=True)
transcript_app = typer.Typer(help="导入和查看版本化 Transcript。", no_args_is_help=True)
guide_app = typer.Typer(help="生成和查看证据化学习指南。", no_args_is_help=True)
chapter_app = typer.Typer(help="按需生成章节详情。", no_args_is_help=True)
note_app = typer.Typer(help="管理不可覆盖的个人 Markdown 笔记。", no_args_is_help=True)
plugin_app = typer.Typer(help="管理浏览器扩展配对。", no_args_is_help=True)
app.add_typer(library_app, name="library")
config_app.add_typer(provider_app, name="provider")
app.add_typer(config_app, name="config")
app.add_typer(transcript_app, name="transcript")
app.add_typer(guide_app, name="guide")
app.add_typer(chapter_app, name="chapter")
app.add_typer(note_app, name="note")
app.add_typer(plugin_app, name="plugin")


@app.callback(invoke_without_command=True)
def root(ctx: typer.Context) -> None:
    """显示当前阶段真实可用的命令。"""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


def _paths() -> AppPaths:
    return AppPaths.windows_default()


def _library(name: str) -> tuple[Library, StudyRepository]:
    paths = _paths()
    library = LibraryRegistry(paths).get(name)
    return library, StudyRepository(library_database(paths, library))


def _known_error(exc: Exception) -> None:
    typer.echo(f"错误：{exc}", err=True)
    raise typer.Exit(code=2) from None


@library_app.command("create")
def library_create(name: str, path: Path) -> None:
    """创建并注册一个知识库目录。"""
    try:
        library = LibraryRegistry(_paths()).create(name, path)
        StudyRepository(library_database(_paths(), library))
    except StorageError as exc:
        _known_error(exc)
        return
    typer.echo(f"已创建知识库：{library.name}（{library.path}）")


@library_app.command("list")
def library_list() -> None:
    """列出已注册知识库。"""
    try:
        libraries = LibraryRegistry(_paths()).list()
    except StorageError as exc:
        _known_error(exc)
        return
    for library in libraries:
        typer.echo(f"{library.name}\t{library.path}")


@library_app.command("show")
def library_show(name: str) -> None:
    """显示一个知识库。"""
    try:
        library = LibraryRegistry(_paths()).get(name)
    except StorageError as exc:
        _known_error(exc)
        return
    typer.echo(f"名称：{library.name}\nID：{library.library_id}\n目录：{library.path}")


@provider_app.command("set")
def provider_set(
    name: str,
    base_url: str,
    model: str,
    api_key: Annotated[str, typer.Option(prompt=True, hide_input=True)],
    output_language: str = "zh-CN",
    context_budget: int = 12000,
    input_price_per_million: str | None = None,
    output_price_per_million: str | None = None,
    currency: str | None = None,
) -> None:
    """保存非秘密 Provider 配置，并把 Key 写入 Credential Manager。"""
    try:
        config = ProviderConfig(
            name,
            base_url,
            model,
            output_language,
            context_budget,
            input_price_per_million=(
                Decimal(input_price_per_million) if input_price_per_million is not None else None
            ),
            output_price_per_million=(
                Decimal(output_price_per_million) if output_price_per_million is not None else None
            ),
            currency=currency.upper() if currency else None,
        )
        ProviderConfigStore(_paths()).set(config)
        ProviderSecretStore().set(name, api_key)
    except InvalidOperation:
        _known_error(ProviderError("Provider 单价格式无效。"))
        return
    except (ProviderError, StorageError) as exc:
        _known_error(exc)
        return
    typer.echo(f"已保存 Provider：{name}（{model}）")


@provider_app.command("show")
def provider_show(name: str) -> None:
    """显示不含 API Key 的 Provider 配置。"""
    try:
        config = ProviderConfigStore(_paths()).get(name)
    except (ProviderError, StorageError) as exc:
        _known_error(exc)
        return
    input_price = config.input_price_per_million
    output_price = config.output_price_per_million
    typer.echo(
        f"名称：{config.name}\nBase URL：{config.base_url}\n模型：{config.model}\n"
        f"输出语言：{config.output_language}\n上下文预算：{config.context_budget}"
        f"\n输入单价/百万 token：{input_price if input_price is not None else '未设置'}"
        f"\n输出单价/百万 token：{output_price if output_price is not None else '未设置'}"
        f"\n币种：{config.currency or '未设置'}"
    )


@provider_app.command("clear")
def provider_clear(name: str) -> None:
    """清除 Provider 配置和对应 API Key。"""
    try:
        config_removed = ProviderConfigStore(_paths()).clear(name)
        key_removed = ProviderSecretStore().clear(name)
    except (ProviderError, StorageError) as exc:
        _known_error(exc)
        return
    typer.echo("Provider 已清除。" if config_removed or key_removed else "Provider 不存在。")


@transcript_app.command("import")
def transcript_import(
    library_name: Annotated[str, typer.Option("--library")],
    source: Path,
    bvid: str,
    page: int,
    cid: int,
    title: str,
    language: str,
    display_name: str,
    kind: str = "ai",
    track_id: int | None = None,
) -> None:
    """从现有原始字幕 JSON 导入 Transcript，不访问平台。"""
    try:
        _, repository = _library(library_name)
        transcript = import_bilibili_json(
            source.read_bytes(),
            bvid=bvid,
            page=page,
            cid=cid,
            title=title,
            track_id=track_id,
            language=language,
            display_name=display_name,
            kind=kind,
        )
        repository.save_transcript(transcript)
    except (OSError, DomainError, StorageError) as exc:
        _known_error(exc)
        return
    typer.echo(f"已导入 Transcript：{transcript.revision_id}（{len(transcript.cues)} cues）")


@transcript_app.command("show")
def transcript_show(
    library_name: Annotated[str, typer.Option("--library")], revision_id: str | None = None
) -> None:
    """显示 Transcript 元数据。"""
    try:
        _, repository = _library(library_name)
        transcript = (
            repository.get_transcript(revision_id)
            if revision_id
            else repository.latest_transcript()
        )
    except StorageError as exc:
        _known_error(exc)
        return
    typer.echo(
        f"Revision：{transcript.revision_id}\n来源：{transcript.bvid} P{transcript.page}\n"
        f"语言：{transcript.language}\nCues：{len(transcript.cues)}\nSHA-256：{transcript.content_sha256}"
    )


@guide_app.command("generate")
def guide_generate(
    library_name: Annotated[str, typer.Option("--library")],
    provider_name: Annotated[str, typer.Option("--provider")],
    revision_id: str | None = None,
    regenerate: bool = False,
    yes: Annotated[bool, typer.Option("--yes", help="确认将字幕发送至已配置 Provider。")] = False,
) -> None:
    """主动生成完整视频学习大纲。"""
    try:
        library, repository = _library(library_name)
        transcript = (
            repository.get_transcript(revision_id)
            if revision_id
            else repository.latest_transcript()
        )
        config = ProviderConfigStore(_paths()).get(provider_name)
        if not yes and not typer.confirm(
            f"将 {len(transcript.cues)} 条字幕发送到 {config.name} / {config.model}，继续？"
        ):
            typer.echo("已取消；未创建模型任务。")
            return
        key = ProviderSecretStore().get(provider_name)
        with OpenAIChatAdapter(config, key) as chat:
            result = GuideGenerator(chat, repository).generate(
                transcript, config, regenerate=regenerate
            )
        markdown = render_guide_markdown(result.guide, transcript)
        target = publish_generated(library, result.guide.guide_id, markdown)
    except (DomainError, ProviderError, StorageError) as exc:
        _known_error(exc)
        return
    typer.echo(
        f"学习指南：{result.guide.guide_id}\n文件：{target}\n"
        f"请求：{result.metrics.requests}，缓存：{'命中' if result.metrics.cache_hit else '未命中'}"
    )
    usage = generation_usage(result.metrics, config)
    typer.echo(
        f"Token：输入 {usage['input_tokens'] if usage['input_tokens'] is not None else '未知'}，"
        f"输出 {usage['output_tokens'] if usage['output_tokens'] is not None else '未知'}；"
        f"估算成本：{usage['estimated_cost']} {usage['currency']}"
        if usage["estimated_cost"] is not None
        else "估算成本：未知"
    )


@guide_app.command("show")
def guide_show(library_name: Annotated[str, typer.Option("--library")], guide_id: str) -> None:
    """显示已保存学习指南 JSON。"""
    try:
        _, repository = _library(library_name)
        payload = repository.guide_payload(guide_id)
    except StorageError as exc:
        _known_error(exc)
        return
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


@chapter_app.command("generate")
def chapter_generate(
    library_name: Annotated[str, typer.Option("--library")],
    provider_name: Annotated[str, typer.Option("--provider")],
    guide_id: str,
    chapter_id: str,
    yes: Annotated[bool, typer.Option("--yes")] = False,
) -> None:
    """按需生成一个章节详情。"""
    try:
        _, repository = _library(library_name)
        payload = repository.guide_payload(guide_id)
        transcript = repository.get_transcript(str(payload["revision_id"]))
        config = ProviderConfigStore(_paths()).get(provider_name)
        guide = guide_from_payload(
            payload, transcript, str(payload["fingerprint"]), str(payload["output_language"])
        )
        chapter = next(item for item in guide.chapters if item.chapter_id == chapter_id)
        if not yes and not typer.confirm(
            f"将章节字幕发送到 {config.name} / {config.model}，继续？"
        ):
            typer.echo("已取消；未创建模型任务。")
            return
        with OpenAIChatAdapter(config, ProviderSecretStore().get(provider_name)) as chat:
            detail, metrics = GuideGenerator(chat, repository).generate_chapter_detail(
                transcript, chapter
            )
    except StopIteration:
        _known_error(DomainError("章节不存在。"))
        return
    except (KeyError, DomainError, ProviderError, StorageError) as exc:
        _known_error(exc)
        return
    typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, sort_keys=True))
    typer.echo(f"请求：{metrics.requests}")


@note_app.command("add")
def note_add(
    library_name: Annotated[str, typer.Option("--library")],
    revision_id: str,
    timestamp_ms: int,
    body: str,
    note_type: str = "note",
) -> None:
    """新增独立个人 Markdown 笔记。"""
    try:
        library, repository = _library(library_name)
        repository.get_transcript(revision_id)
        note = new_note(
            revision_id=revision_id, timestamp_ms=timestamp_ms, note_type=note_type, body=body
        )
        target = publish_note(library, note)
        repository.save_note(note)
    except (DomainError, StorageError) as exc:
        _known_error(exc)
        return
    typer.echo(f"笔记：{note.note_id}\n文件：{target}")


@note_app.command("list")
def note_list(library_name: Annotated[str, typer.Option("--library")], revision_id: str) -> None:
    """列出 Transcript 的个人笔记。"""
    try:
        _, repository = _library(library_name)
        notes = repository.notes(revision_id)
    except StorageError as exc:
        _known_error(exc)
        return
    for note in notes:
        typer.echo(f"{note.note_id}\t{note.timestamp_ms}\t{note.note_type}\t{note.body}")


@plugin_app.command("pair")
def plugin_pair() -> None:
    """生成五分钟有效、单次使用的本机扩展配对码。"""
    from bili_study.security import PairingStore

    try:
        code, expires = PairingStore(_paths()).create()
    except StorageError as exc:
        _known_error(exc)
        return
    typer.echo(f"配对码：{code}")
    typer.echo(f"有效期至：{expires.astimezone().isoformat(timespec='seconds')}")


@app.command("serve")
def serve(
    port: Annotated[int, typer.Option(min=1, max=65535, help="loopback Local API 端口。")] = 8765,
) -> None:
    """只在 127.0.0.1 启动已认证的 Local API。"""
    import uvicorn

    from bili_study.api import create_app

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", port))
    except OSError:
        probe.close()
        _known_error(StorageError("Local API 端口已被占用。"))
        return
    probe.close()
    uvicorn.run(
        create_app(allowed_hosts={"127.0.0.1", "localhost"}),
        host="127.0.0.1",
        port=port,
        access_log=False,
        log_level="warning",
    )


def main() -> int:
    """Run the new command tree and preserve real console exit codes."""
    _configure_standard_streams()
    return _run_app(app, prog_name="bili-study", args=sys.argv[1:])
