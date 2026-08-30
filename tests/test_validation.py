from pathlib import Path

import pytest

from gzh_mcp.validation import (
    ValidationError,
    is_publish_enabled,
    validate_article,
    validate_content_image,
    validate_cover_image,
)


@pytest.mark.parametrize("value", [None, "", " ", "0", "false", "True", "TRUE", "yes"])
def test_b1_publish_switch_rejects_non_strict_truth_values(value: str | None) -> None:
    assert is_publish_enabled(value) is False


@pytest.mark.parametrize("value", ["1", "true"])
def test_b1_publish_switch_accepts_only_documented_truth_values(value: str) -> None:
    assert is_publish_enabled(value) is True


def valid_article(**overrides: object) -> dict[str, object]:
    article: dict[str, object] = {
        "title": "标题",
        "digest": "摘要",
        "content": '<p>正文<img src="https://mmbiz.qpic.cn/example.png"></p>',
        "thumb_media_id": "cover-media",
    }
    article.update(overrides)
    return article


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"title": "题" * 33}, "title 不能超过 32"),
        ({"digest": "摘" * 121}, "digest 不能超过 120"),
        ({"content": "文" * 20_000}, "content 必须少于 20000"),
        ({"content": '<img src="https://example.com/a.png">'}, "example.com/a.png"),
        ({"content": "<SCRIPT>alert(1)</SCRIPT>"}, "script"),
    ],
)
def test_b3_article_validation_rejects_invalid_input_without_network(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        validate_article(valid_article(**overrides))


def test_article_validation_returns_image_count() -> None:
    article = valid_article(
        content=(
            '<img src="https://mmbiz.qpic.cn/a.png">'
            '<img src="https://mmbiz.qlogo.cn/b.jpg">'
        )
    )
    assert validate_article(article).image_count == 2


def write_image(path: Path, header: bytes, size: int | None = None) -> Path:
    payload = header + b"image"
    if size is not None:
        payload += b"x" * (size - len(payload))
    path.write_bytes(payload)
    return path


def test_b5_content_image_must_exist(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="不存在"):
        validate_content_image(tmp_path / "missing.jpg")


def test_b5_content_image_rejects_unknown_magic(tmp_path: Path) -> None:
    path = write_image(tmp_path / "looks-like.jpg", b"not-an-image")
    with pytest.raises(ValidationError, match="JPEG 或 PNG"):
        validate_content_image(path)


@pytest.mark.parametrize(
    ("header", "mime_type"),
    [(b"\xff\xd8\xff", "image/jpeg"), (b"\x89PNG\r\n\x1a\n", "image/png")],
)
def test_b5_content_image_uses_magic_not_extension(
    tmp_path: Path, header: bytes, mime_type: str
) -> None:
    path = write_image(tmp_path / "wrong.txt", header)
    assert validate_content_image(path).mime_type == mime_type


def test_b5_content_image_rejects_exactly_one_mebibyte(tmp_path: Path) -> None:
    path = write_image(tmp_path / "large.png", b"\x89PNG\r\n\x1a\n", 1024 * 1024)
    with pytest.raises(ValidationError, match="小于 1MB"):
        validate_content_image(path)


@pytest.mark.parametrize(
    ("header", "mime_type"),
    [
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"GIF89a", "image/gif"),
        (b"BM", "image/bmp"),
    ],
)
def test_cover_image_supports_official_permanent_material_formats(
    tmp_path: Path, header: bytes, mime_type: str
) -> None:
    path = write_image(tmp_path / "cover.bin", header)
    assert validate_cover_image(path).mime_type == mime_type

