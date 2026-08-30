"""工具输入与本地图片的前置校验。"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


CONTENT_IMAGE_LIMIT = 1024 * 1024
COVER_IMAGE_LIMIT = 10 * 1024 * 1024
WECHAT_IMAGE_HOSTS = {"mmbiz.qpic.cn", "mmbiz.qlogo.cn"}


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ArticleValidation:
    image_count: int


@dataclass(frozen=True)
class ValidatedImage:
    path: Path
    mime_type: str
    size: int


class _ArticleHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.has_script = False
        self.image_sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered_tag = tag.lower()
        if lowered_tag == "script":
            self.has_script = True
        if lowered_tag == "img":
            source = next((value for key, value in attrs if key.lower() == "src"), None)
            if source:
                self.image_sources.append(source)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


def is_publish_enabled(value: str | None) -> bool:
    return value in {"1", "true"}


def inspect_article_html(content: str) -> ArticleValidation:
    parser = _ArticleHTMLParser()
    parser.feed(content)
    parser.close()
    if parser.has_script:
        raise ValidationError("content 不能包含 script 标签")

    external_sources = []
    for source in parser.image_sources:
        parsed = urlparse(source)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in WECHAT_IMAGE_HOSTS:
            external_sources.append(source)
    if external_sources:
        raise ValidationError(f"content 含非微信正文图片 URL: {', '.join(external_sources)}")
    return ArticleValidation(image_count=len(parser.image_sources))


def validate_article(article: dict[str, Any]) -> ArticleValidation:
    title = article.get("title")
    if not isinstance(title, str) or not title:
        raise ValidationError("title 必须是非空字符串")
    if len(title) > 32:
        raise ValidationError("title 不能超过 32 字符")

    digest = article.get("digest", "")
    if not isinstance(digest, str):
        raise ValidationError("digest 必须是字符串")
    if len(digest) > 120:
        raise ValidationError("digest 不能超过 120 字符")

    content = article.get("content")
    if not isinstance(content, str) or not content:
        raise ValidationError("content 必须是非空字符串")
    if len(content) >= 20_000:
        raise ValidationError("content 必须少于 20000 字符")
    return inspect_article_html(content)


def validate_articles(articles: list[dict[str, Any]]) -> list[ArticleValidation]:
    if not articles:
        raise ValidationError("articles 至少需要一篇文章")
    return [validate_article(article) for article in articles]


def _resolved_regular_file(file_path: str | Path) -> tuple[Path, int, bytes]:
    path = Path(file_path).expanduser()
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValidationError(f"图片文件不存在: {path}") from exc
    if not resolved.is_file():
        raise ValidationError(f"图片路径不是普通文件: {resolved}")
    size = resolved.stat().st_size
    with resolved.open("rb") as image_file:
        header = image_file.read(8)
    return resolved, size, header


def _image_mime_type(header: bytes, *, cover: bool) -> str:
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG"):
        return "image/png"
    if cover and header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if cover and header.startswith(b"BM"):
        return "image/bmp"
    expected = "JPEG、PNG、GIF 或 BMP" if cover else "JPEG 或 PNG"
    raise ValidationError(f"图片真实格式必须是 {expected}")


def validate_content_image(file_path: str | Path) -> ValidatedImage:
    path, size, header = _resolved_regular_file(file_path)
    mime_type = _image_mime_type(header, cover=False)
    if size >= CONTENT_IMAGE_LIMIT:
        raise ValidationError("正文图片必须严格小于 1MB")
    return ValidatedImage(path=path, mime_type=mime_type, size=size)


def validate_cover_image(file_path: str | Path) -> ValidatedImage:
    path, size, header = _resolved_regular_file(file_path)
    mime_type = _image_mime_type(header, cover=True)
    if size > COVER_IMAGE_LIMIT:
        raise ValidationError("封面图片不能超过 10MB")
    return ValidatedImage(path=path, mime_type=mime_type, size=size)
