"""New command tree backed by the existing extraction and authentication handlers."""

from __future__ import annotations

import sys

import typer

from bili_subtitle.cli import (  # pyright: ignore[reportPrivateUsage]
    _configure_standard_streams,  # pyright: ignore[reportPrivateUsage]
    _run_app,  # pyright: ignore[reportPrivateUsage]
    auth_app,
    extract,
)

app = typer.Typer(
    add_completion=False,
    help="Bilibili 视频学习助手（当前提供字幕提取与认证）。",
    no_args_is_help=False,
    rich_markup_mode=None,
)
app.command("extract")(extract)
app.add_typer(auth_app, name="auth")


@app.callback(invoke_without_command=True)
def root(ctx: typer.Context) -> None:
    """显示当前阶段真实可用的命令。"""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


def main() -> int:
    """Run the new command tree and preserve real console exit codes."""
    _configure_standard_streams()
    return _run_app(app, prog_name="bili-study", args=sys.argv[1:])
