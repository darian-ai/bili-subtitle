from __future__ import annotations

from dataclasses import dataclass

import pytest

from bili_subtitle.application.input_parser import VideoReference
from bili_subtitle.application.metadata import resolve_selection
from bili_subtitle.domain.errors import (
    InputError,
    InvalidPageError,
    PlatformResponseError,
    RedirectError,
)
from bili_subtitle.domain.models import SelectionSource, VideoMetadata, VideoPage


@dataclass
class FakeMetadata:
    video: VideoMetadata
    resolved_url: str = "https://www.bilibili.com/video/BV1xx411c7mD?p=2"

    def resolve_short_url(self, url: str) -> str:
        del url
        return self.resolved_url

    def fetch_video(self, reference: VideoReference) -> VideoMetadata:
        assert reference.bvid == "BV1xx411c7mD"
        return self.video


@pytest.fixture
def video() -> VideoMetadata:
    return VideoMetadata(
        123,
        "BV1xx411c7mD",
        "测试投稿",
        (VideoPage(1, 101, "P1"), VideoPage(2, 102, "P2")),
    )


def test_default_selects_all_pages(video: VideoMetadata) -> None:
    result = resolve_selection(
        "BV1xx411c7mD", page=None, all_pages=False, metadata=FakeMetadata(video)
    )
    assert result.pages == video.pages
    assert result.source is SelectionSource.DEFAULT_ALL


def test_url_page_selects_one(video: VideoMetadata) -> None:
    result = resolve_selection(
        "https://www.bilibili.com/video/BV1xx411c7mD?p=2",
        page=None,
        all_pages=False,
        metadata=FakeMetadata(video),
    )
    assert result.pages == (video.pages[1],)
    assert result.source is SelectionSource.URL_PAGE


@pytest.mark.parametrize(("page", "all_pages"), [(1, False), (None, True)])
def test_explicit_selection_overrides_url_page(
    video: VideoMetadata, page: int | None, all_pages: bool
) -> None:
    result = resolve_selection(
        "https://www.bilibili.com/video/BV1xx411c7mD?p=2",
        page=page,
        all_pages=all_pages,
        metadata=FakeMetadata(video),
    )
    assert result.notices
    assert result.source is (
        SelectionSource.EXPLICIT_PAGE if page is not None else SelectionSource.EXPLICIT_ALL
    )


def test_short_url_is_resolved(video: VideoMetadata) -> None:
    result = resolve_selection(
        "https://b23.tv/abc", page=None, all_pages=False, metadata=FakeMetadata(video)
    )
    assert result.pages == (video.pages[1],)


def test_short_url_must_resolve_to_direct_video(video: VideoMetadata) -> None:
    adapter = FakeMetadata(video, resolved_url="https://b23.tv/again")
    with pytest.raises(RedirectError):
        resolve_selection("https://b23.tv/abc", page=None, all_pages=False, metadata=adapter)


def test_invalid_page_and_mutual_exclusion(video: VideoMetadata) -> None:
    with pytest.raises(InvalidPageError):
        resolve_selection("BV1xx411c7mD", page=3, all_pages=False, metadata=FakeMetadata(video))
    with pytest.raises(InputError):
        resolve_selection("BV1xx411c7mD", page=1, all_pages=True, metadata=FakeMetadata(video))
    with pytest.raises(InputError):
        resolve_selection("BV1xx411c7mD", page=0, all_pages=False, metadata=FakeMetadata(video))


def test_domain_models_reject_invalid_platform_values(video: VideoMetadata) -> None:
    with pytest.raises(PlatformResponseError):
        VideoPage(0, 1, "bad")
    with pytest.raises(PlatformResponseError):
        VideoMetadata(1, "BV1xx411c7mD", "bad", (video.pages[0], video.pages[0]))
    with pytest.raises(PlatformResponseError):
        VideoMetadata(1, "BVbad", "bad", video.pages)
