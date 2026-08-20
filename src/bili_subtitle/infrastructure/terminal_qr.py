"""不泄露原始内容的终端二维码渲染。"""

from __future__ import annotations

import qrcode
import typer


def render_qr(content: str) -> None:
    qr = qrcode.QRCode(border=2)
    qr.add_data(content)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    for row in matrix:
        typer.echo("".join("██" if cell else "  " for cell in row))
