from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from bili_subtitle.domain.errors import SubtitlePlatformResponseError
from bili_subtitle.domain.models import SubtitleCue, SubtitleTrack, SubtitleTrackKind


def test_subtitle_models_are_immutable_and_preserve_text() -> None:
    track = SubtitleTrack(7, "zh-CN", "中文（AI生成）", SubtitleTrackKind.AI)
    cue = SubtitleCue(Decimal("1.25"), Decimal("2.5"), "  原文\n第二行 ")
    assert cue.text == "  原文\n第二行 "
    assert track.kind is SubtitleTrackKind.AI
    with pytest.raises(FrozenInstanceError):
        track.language = "en"  # type: ignore[misc]


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-1")])
def test_cue_rejects_invalid_time(value: Decimal) -> None:
    with pytest.raises(SubtitlePlatformResponseError):
        SubtitleCue(value, Decimal("2"), "x")
