from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from gzh_mcp.validation import (
    DATACUBE_MAX_DAYS,
    ValidationError,
    validate_datacube_request,
    validate_menu_buttons,
    validate_message,
    validate_permanent_media,
)


def test_b17_datacube_span_table_has_all_supported_reports() -> None:
    assert set(DATACUBE_MAX_DAYS) == {
        "getusersummary",
        "getusercumulate",
        "getarticlesummary",
        "getuserread",
        "getuserreadhour",
        "getusershare",
        "getusersharehour",
        "getarticleread",
        "getarticleshare",
        "getbizsummary",
        "getarticletotaldetail",
        "getupstreammsg",
        "getupstreammsghour",
        "getupstreammsgweek",
        "getupstreammsgmonth",
        "getupstreammsgdist",
        "getupstreammsgdistweek",
        "getupstreammsgdistmonth",
        "getinterfacesummary",
        "getinterfacesummaryhour",
    }


@pytest.mark.parametrize(
    ("report", "begin_date", "end_date", "message"),
    [
        ("unknown", "2026-08-01", "2026-08-01", "report"),
        ("getusersummary", "2026/08/01", "2026-08-01", "YYYY-MM-DD"),
        ("getusersummary", "2026-08-02", "2026-08-01", "晚于"),
        ("getarticlesummary", "2026-08-01", "2026-08-02", "1 天"),
        ("getuserread", "2026-08-01", "2026-08-04", "3 天"),
        ("getusersummary", "2026-08-01", "2026-08-08", "7 天"),
        ("getupstreammsgdist", "2026-08-01", "2026-08-16", "15 天"),
        ("getinterfacesummary", "2026-08-01", "2026-08-31", "30 天"),
    ],
)
def test_b17_datacube_validation_rejects_bad_range(
    report: str, begin_date: str, end_date: str, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        validate_datacube_request(report, begin_date, end_date)


@pytest.mark.parametrize(
    ("report", "begin_date", "end_date"),
    [
        ("getarticlesummary", "2026-08-01", "2026-08-01"),
        ("getuserread", "2026-08-01", "2026-08-03"),
        ("getusersummary", "2026-08-01", "2026-08-07"),
        ("getupstreammsgdist", "2026-08-01", "2026-08-15"),
        ("getinterfacesummary", "2026-08-01", "2026-08-30"),
    ],
)
def test_b17_datacube_validation_accepts_inclusive_max_span(
    report: str, begin_date: str, end_date: str
) -> None:
    assert validate_datacube_request(report, begin_date, end_date) == (
        date.fromisoformat(begin_date),
        date.fromisoformat(end_date),
    )


def test_b19_menu_rejects_more_than_three_top_level_buttons() -> None:
    with pytest.raises(ValidationError, match="3"):
        validate_menu_buttons([{"name": str(index), "type": "click", "key": str(index)} for index in range(4)])


def test_b19_menu_rejects_more_than_five_sub_buttons() -> None:
    buttons = [{"name": "菜单", "sub_button": [{"name": str(index), "type": "click", "key": str(index)} for index in range(6)]}]
    with pytest.raises(ValidationError, match="5"):
        validate_menu_buttons(buttons)


@pytest.mark.parametrize(
    "buttons",
    [
        [{"name": "一级菜单甲乙", "type": "click", "key": "x"}],
        [{"name": "12345678901234567", "type": "click", "key": "x"}],
        [{"name": "一级", "sub_button": [{"name": "二级菜单甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未", "type": "click", "key": "x"}]}],
        [{"name": "一级", "sub_button": [{"name": "1" * 61, "type": "click", "key": "x"}]}],
    ],
)
def test_b19_menu_rejects_names_over_official_utf8_byte_limits(
    buttons: list[dict[str, object]],
) -> None:
    with pytest.raises(ValidationError, match="名称"):
        validate_menu_buttons(buttons)


@pytest.mark.parametrize(
    ("kind", "message"),
    [
        ("mass", {"msgtype": "music", "music": {"thumb_media_id": "x"}}),
        ("mass", {"msgtype": "mpnews"}),
        ("mass", {"msgtype": "text", "text": {}}),
        ("custom", {"msgtype": "unsupported", "unsupported": {}}),
        ("custom", {"msgtype": "image"}),
    ],
)
def test_b20_message_validation_rejects_type_or_missing_content(
    kind: str, message: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        validate_message(message, kind=kind)


@pytest.mark.parametrize(
    ("kind", "message"),
    [
        ("mass", {"msgtype": "mpnews", "mpnews": {"media_id": "m"}}),
        ("mass", {"msgtype": "text", "text": {"content": "hello"}}),
        ("custom", {"msgtype": "music", "music": {"thumb_media_id": "m"}}),
        ("custom", {"msgtype": "miniprogrampage", "miniprogrampage": {"appid": "wx", "pagepath": "pages/a", "thumb_media_id": "m"}}),
    ],
)
def test_b20_message_validation_accepts_supported_shapes(
    kind: str, message: dict[str, object]
) -> None:
    validate_message(message, kind=kind)


def test_permanent_voice_limit_is_official_2mb(tmp_path: Path) -> None:
    """官方 add_material：语音 2M、不超过 60s（developers.weixin.qq.com 逐字核对）。"""
    at_limit = tmp_path / "at-limit.mp3"
    at_limit.write_bytes(b"ID3" + b"\x00" * (2 * 1024 * 1024 - 3))
    validate_permanent_media(at_limit, "voice")

    oversized = tmp_path / "oversized.mp3"
    oversized.write_bytes(b"ID3" + b"\x00" * (2 * 1024 * 1024 - 2))
    with pytest.raises(ValidationError, match="voice"):
        validate_permanent_media(oversized, "voice")
