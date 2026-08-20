"""命令行入口。"""

from __future__ import annotations

import sys
from typing import Annotated

import typer

from bili_subtitle.application.auth import login
from bili_subtitle.application.metadata import resolve_selection
from bili_subtitle.domain import MetadataError
from bili_subtitle.domain.auth import CredentialState, LoginState
from bili_subtitle.infrastructure.auth import BilibiliAuthAdapter
from bili_subtitle.infrastructure.bilibili import BilibiliMetadataAdapter, create_http_client
from bili_subtitle.infrastructure.credentials import CredentialStoreError, KeyringCredentialStore
from bili_subtitle.infrastructure.terminal_qr import render_qr

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
    del lang, force
    if video is None:
        typer.echo(ctx.get_help())
        return
    if page is not None and all_pages:
        raise typer.BadParameter("--page 与 --all-pages 不能同时使用。")

    store = KeyringCredentialStore()
    try:
        with create_http_client() as client:
            auth = BilibiliAuthAdapter(client)
            outcome = login(store, auth, render_qr, typer.echo)
            if (
                outcome.state not in {LoginState.VALID, LoginState.SUCCESS}
                or outcome.credential is None
            ):
                typer.echo(f"错误：{outcome.message}", err=True)
                raise typer.Exit(code=2)
            auth.apply(outcome.credential)
            selection = resolve_selection(
                video,
                page=page,
                all_pages=all_pages,
                metadata=BilibiliMetadataAdapter(client),
            )
    except (MetadataError, CredentialStoreError) as exc:
        typer.echo(f"错误：{exc}", err=True)
        raise typer.Exit(code=2) from None
    except KeyboardInterrupt:
        typer.echo("错误：登录已取消。", err=True)
        raise typer.Exit(code=2) from None

    for notice in selection.notices:
        typer.echo(notice)
    typer.echo(f"标题：{_terminal_safe(selection.video.title)}")
    typer.echo(f"BV号：{selection.video.bvid}")
    typer.echo(f"av号：av{selection.video.aid}")
    typer.echo(f"所选分集：{len(selection.pages)}")
    for item in selection.pages:
        typer.echo(f"P{item.number:02d} | CID {item.cid} | {_terminal_safe(item.title)}")


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


def main() -> None:
    """将公开命令语法分派给对应的 Typer 应用。"""
    args = sys.argv[1:]
    if args and args[0] == "auth":
        auth_app(prog_name="bili-subtitle auth", args=args[1:])
        return
    extract_app(prog_name="bili-subtitle", args=args)
