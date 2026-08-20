"""命令行入口与阶段一占位行为。"""

from __future__ import annotations

import sys
from typing import Annotated

import typer

_NOT_IMPLEMENTED = "该功能尚未实现；当前版本仅提供阶段一项目骨架。"

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


def _not_implemented() -> None:
    typer.echo(_NOT_IMPLEMENTED, err=True)
    raise typer.Exit(code=2)


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
    del page, all_pages, lang, force
    if video is None:
        typer.echo(ctx.get_help())
        return
    _not_implemented()


@auth_app.command("login")
def auth_login() -> None:
    """通过终端二维码登录 Bilibili。"""
    _not_implemented()


@auth_app.command("status")
def auth_status() -> None:
    """检查已保存登录状态是否有效。"""
    _not_implemented()


@auth_app.command("clear")
def auth_clear() -> None:
    """清除已保存的 Bilibili 登录凭据。"""
    _not_implemented()


def main() -> None:
    """将公开命令语法分派给对应的 Typer 应用。"""
    args = sys.argv[1:]
    if args and args[0] == "auth":
        auth_app(prog_name="bili-subtitle auth", args=args[1:])
        return
    extract_app(prog_name="bili-subtitle", args=args)
