from __future__ import annotations

import pytest

from bili_subtitle.application.input_parser import (
    ShortVideoUrl,
    VideoReference,
    is_allowed_redirect_host,
    parse_video_input,
)
from bili_subtitle.domain.errors import InputError


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" BV1xx411c7mD ", VideoReference(bvid="BV1xx411c7mD")),
        ("bv1xx411c7mD", VideoReference(bvid="BV1xx411c7mD")),
        ("av123", VideoReference(aid=123)),
        ("AV123", VideoReference(aid=123)),
        (
            "https://www.bilibili.com/video/BV1xx411c7mD?p=2&spm_id_from=x#reply",
            VideoReference(bvid="BV1xx411c7mD", url_page=2),
        ),
        ("http://m.bilibili.com/video/av123/", VideoReference(aid=123)),
    ],
)
def test_parse_supported_inputs(raw: str, expected: VideoReference) -> None:
    assert parse_video_input(raw) == expected


def test_parse_short_url() -> None:
    assert parse_video_input("https://b23.tv/abc") == ShortVideoUrl("https://b23.tv/abc")


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "text BV1xx411c7mD",
        "av0",
        "BV1-invalid!",
        "ftp://www.bilibili.com/video/BV1xx411c7mD",
        "https://evil.example/video/BV1xx411c7mD",
        "https://evilbilibili.com/video/BV1xx411c7mD",
        "https://user@www.bilibili.com/video/BV1xx411c7mD",
        "https://www.bilibili.com:443/video/BV1xx411c7mD",
        "https://www.bilibili.com/list/BV1xx411c7mD",
        "https://www.bilibili.com/video/BV1xx411c7mD/extra",
        "https://www.bilibili.com/video/BV1xx411c7mD?p=",
        "https://www.bilibili.com/video/BV1xx411c7mD?p=1&p=2",
        "https://www.bilibili.com/video/BV1xx411c7mD?p=-1",
        "https://b23.tv/",
    ],
)
def test_reject_invalid_inputs(raw: str) -> None:
    with pytest.raises(InputError):
        parse_video_input(raw)


def test_redirect_host_validation() -> None:
    assert is_allowed_redirect_host("https://b23.tv/next")
    assert is_allowed_redirect_host("https://www.bilibili.com/video/BV1xx411c7mD")
    assert not is_allowed_redirect_host("https://www.bilibili.com:443/video/BV1xx411c7mD")
    assert not is_allowed_redirect_host("https://attacker.example/path")
    assert not is_allowed_redirect_host("not a url")


def test_video_reference_requires_exactly_one_identifier() -> None:
    with pytest.raises(ValueError):
        VideoReference()
    with pytest.raises(ValueError):
        VideoReference(bvid="BV1xx411c7mD", aid=123)
