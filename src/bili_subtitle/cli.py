"""命令行入口。"""

from __future__ import annotations

import sys
from io import TextIOWrapper
from pathlib import Path
from typing import Annotated

import typer
from typer.main import _click as click

from bili_subtitle.application.auth import login
from bili_subtitle.application.full_flow import FlowResult, run_extraction
from bili_subtitle.application.input_parser import parse_video_input
from bili_subtitle.application.metadata import resolve_parsed_selection
from bili_subtitle.domain import MetadataError
from bili_subtitle.domain.auth import CredentialState, LoginState
from bili_subtitle.infrastructure.auth import BilibiliAuthAdapter
from bili_subtitle.infrastructure.bilibili import BilibiliMetadataAdapter, create_http_client
from bili_subtitle.infrastructure.credentials import CredentialStoreError, KeyringCredentialStore
from bili_subtitle.infrastructure.export import FileSystemExportAdapter
from bili_subtitle.infrastructure.subtitles import BilibiliSubtitleAdapter
from bili_subtitle.infrastructure.terminal_qr import render_qr

# Stable patch point retained for embedders of the V1 Python module.
resolve_selection = resolve_parsed_selection

extract_app = typer.Typer(
    add_completion=False,
    help="提取 Bilibili 播放器已提供且当前账号可见的字幕轨道。",
    rich_markup_mode=None,
)
auth_app = typer.Typer(
    add_completion=False,
    help="管理保存在 Windows Credential Manager 中的 Bilibili 登录状态。",
    no_args_is_help=True,
    rich_markup_mode=None,
)


@extract_app.command(
    epilog=(
        "认证命令：bili-subtitle auth login | bili-subtitle auth status | bili-subtitle auth clear"
    )
)
def extract(
    ctx: typer.Context,
    video: Annotated[
        str | None,
        typer.Argument(help="BV 号、av 号、Bilibili 视频 URL 或 b23.tv 短链。"),
    ] = None,
    page: Annotated[
        int | None,
        typer.Option("--page", min=1, help="只处理第 N 个分集；与 --all-pages 互斥。"),
    ] = None,
    all_pages: Annotated[
        bool,
        typer.Option("--all-pages", help="处理投稿的全部分集；与 --page 互斥。"),
    ] = False,
    lang: Annotated[
        list[str] | None,
        typer.Option("--lang", help="按平台语言代码过滤；可重复使用。"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="覆盖已经存在的输出文件。"),
    ] = False,
) -> None:
    """提取一个普通 UGC 投稿的站内字幕。"""
    if video is None:
        typer.echo(ctx.get_help())
        return
    if page is not None and all_pages:
        raise typer.BadParameter("--page 与 --all-pages 不能同时使用。")
    if any(not value.strip() for value in (lang or ())):
        raise typer.BadParameter("--lang 不能是空值。")

    # Input syntax is deliberately validated before credentials, HTTP, or QR I/O.
    try:
        parsed_video = parse_video_input(video)
    except MetadataError as exc:
        raise typer.BadParameter(str(exc), param_hint="video") from None

    store = KeyringCredentialStore()
    try:
        with create_http_client() as client:
            auth = BilibiliAuthAdapter(client)
            try:
                outcome = login(store, auth, render_qr, typer.echo)
            except KeyboardInterrupt:
                typer.echo("错误：登录已取消。", err=True)
                raise typer.Exit(code=2) from None
            if (
                outcome.state not in {LoginState.VALID, LoginState.SUCCESS}
                or outcome.credential is None
            ):
                typer.echo(f"错误：{outcome.message}", err=True)
                raise typer.Exit(code=2)
            auth.apply(outcome.credential)
            try:
                selection = resolve_selection(
                    parsed_video,
                    page=page,
                    all_pages=all_pages,
                    metadata=BilibiliMetadataAdapter(client),
                )
                outcome_result = run_extraction(
                    selection=selection,
                    languages=tuple(lang or ()),
                    force=force,
                    cwd=Path.cwd(),
                    subtitles=BilibiliSubtitleAdapter(client),
                    exporter=FileSystemExportAdapter(),
                )
            except KeyboardInterrupt:
                typer.echo("错误：字幕提取已取消。", err=True)
                raise typer.Exit(code=2) from None
    except (MetadataError, CredentialStoreError) as exc:
        typer.echo(f"错误：{exc}", err=True)
        raise typer.Exit(code=2) from None

    for notice in selection.notices:
        typer.echo(notice)
    _render_flow(outcome_result)
    if outcome_result.exit_code:
        raise typer.Exit(code=outcome_result.exit_code)


def _render_flow(result: FlowResult) -> None:
    written = replaced = skipped = failed = tracks = no_subtitles = no_match = 0
    for page in result.pages:
        if page.status == "no_subtitles":
            no_subtitles += 1
            typer.echo(f"P{page.page.number:02d}：无字幕")
        elif page.status == "no_match":
            no_match += 1
            typer.echo(f"P{page.page.number:02d}：无匹配字幕")
        elif page.status == "failed":
            failed += 1
            typer.echo(f"P{page.page.number:02d}：失败（{page.error}）")
        for track in page.tracks:
            tracks += 1
            if track.status == "failed":
                failed += 1
                typer.echo(f"P{page.page.number:02d} 轨道 {track.track.track_id}：失败")
                continue
            written += sum(action == "written" for action in (track.json_action, track.srt_action))
            replaced += sum(
                action == "replaced" for action in (track.json_action, track.srt_action)
            )
            skipped += sum(action == "skipped" for action in (track.json_action, track.srt_action))
            typer.echo(f"P{page.page.number:02d} 轨道 {track.track.track_id}：完成")
    failed += int(result.manifest_failed)
    all_skipped = tracks > 0 and failed == 0 and skipped == tracks * 2
    completion = "（全部已有文件跳过）" if all_skipped else ""
    typer.echo(
        f"摘要：分集 {len(result.pages)}，轨道 {tracks}，写入 {written}，覆盖 {replaced}，"
        f"跳过 {skipped}，无字幕 {no_subtitles}，无匹配 {no_match}，失败 {failed}。{completion}"
    )


def _terminal_safe(value: str) -> str:
    """防止不可信平台标题伪造额外终端行或控制序列。"""
    return "".join(character if character.isprintable() else " " for character in value)


@auth_app.command("login")
def auth_login() -> None:
    """通过终端二维码登录 Bilibili。"""
    try:
        with create_http_client() as client:
            outcome = login(
                KeyringCredentialStore(), BilibiliAuthAdapter(client), render_qr, typer.echo
            )
    except (MetadataError, CredentialStoreError) as exc:
        typer.echo(f"错误：{exc}", err=True)
        raise typer.Exit(code=2) from None
    except KeyboardInterrupt:
        typer.echo("错误：登录已取消。", err=True)
        raise typer.Exit(code=2) from None
    typer.echo(outcome.message, err=outcome.state not in {LoginState.VALID, LoginState.SUCCESS})
    if outcome.state not in {LoginState.VALID, LoginState.SUCCESS}:
        raise typer.Exit(code=2)


@auth_app.command("status")
def auth_status() -> None:
    """检查已保存登录状态是否有效。"""
    try:
        stored = KeyringCredentialStore().read()
        if stored.state is CredentialState.MISSING:
            typer.echo("未登录。")
            raise typer.Exit(code=1)
        if stored.state is CredentialState.INVALID or stored.credential is None:
            typer.echo("凭据无效。")
            raise typer.Exit(code=1)
        with create_http_client() as client:
            status = BilibiliAuthAdapter(client).check(stored.credential)
    except (MetadataError, CredentialStoreError) as exc:
        typer.echo(f"错误：{exc}", err=True)
        raise typer.Exit(code=2) from None
    if status.state is LoginState.VALID:
        suffix = f"（{_terminal_safe(status.display_name)}）" if status.display_name else ""
        typer.echo(f"已登录{suffix}。")
        return
    typer.echo("登录已失效。")
    raise typer.Exit(code=1)


@auth_app.command("clear")
def auth_clear() -> None:
    """清除已保存的 Bilibili 登录凭据。"""
    try:
        removed = KeyringCredentialStore().clear()
    except CredentialStoreError as exc:
        typer.echo(f"错误：{exc}", err=True)
        raise typer.Exit(code=2) from None
    typer.echo("凭据已清除。" if removed else "当前没有已保存凭据。")


def main() -> int:
    """将公开命令语法分派给对应的 Typer 应用。"""
    _configure_standard_streams()
    args = sys.argv[1:]
    if args and args[0] == "auth":
        return _run_app(auth_app, prog_name="bili-subtitle auth", args=args[1:])
    return _run_app(extract_app, prog_name="bili-subtitle", args=args)


def _run_app(app: typer.Typer, *, prog_name: str, args: list[str]) -> int:
    """Return Click's real status so console-script and ``python -m`` agree."""
    try:
        result = app(prog_name=prog_name, args=args, standalone_mode=False)
    except click.exceptions.Exit as exc:
        return exc.exit_code
    except click.ClickException as exc:
        exc.show()
        return exc.exit_code
    except Exception:
        typer.echo("错误：发生内部错误。", err=True)
        return 2
    return result if isinstance(result, int) else 0


def _configure_standard_streams() -> None:
    """让 Windows 控制台与重定向输出可靠承载公开的中文界面。"""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
