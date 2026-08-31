"""工具输入与本地图片的前置校验。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse


CONTENT_IMAGE_LIMIT = 1024 * 1024
COVER_IMAGE_LIMIT = 10 * 1024 * 1024
WECHAT_IMAGE_HOSTS = {"mmbiz.qpic.cn", "mmbiz.qlogo.cn"}
DATACUBE_MAX_DAYS = {
    "getusersummary": 7,
    "getusercumulate": 7,
    "getarticlesummary": 1,
    "getuserread": 3,
    "getuserreadhour": 1,
    "getusershare": 7,
    "getusersharehour": 1,
    "getarticleread": 1,
    "getarticleshare": 1,
    "getbizsummary": 1,
    "getarticletotaldetail": 1,
    "getupstreammsg": 7,
    "getupstreammsghour": 1,
    "getupstreammsgweek": 30,
    "getupstreammsgmonth": 30,
    "getupstreammsgdist": 15,
    "getupstreammsgdistweek": 30,
    "getupstreammsgdistmonth": 30,
    "getinterfacesummary": 30,
    "getinterfacesummaryhour": 1,
}
MASS_MESSAGE_TYPES = {"mpnews", "text", "voice", "image", "mpvideo", "wxcard"}
CUSTOM_MESSAGE_TYPES = {
    "text",
    "image",
    "voice",
    "video",
    "music",
    "news",
    "mpnews",
    "wxcard",
    "miniprogrampage",
    "msgmenu",
}
_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


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


@dataclass(frozen=True)
class ValidatedMedia:
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
            # 微信保存草稿会把 src 归一化为 data-src（懒加载），两者都算图片。
            source = next(
                (
                    value
                    for key, value in attrs
                    if key.lower() == "src" or key.lower() == "data-src"
                ),
                None,
            )
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

    content = article.get("content")
    if not isinstance(content, str) or not content:
        raise ValidationError("content 必须是非空字符串")
    if len(content) >= 20_000:
        raise ValidationError("content 必须少于 20000 字符")

    if article.get("article_type") == "newspic":
        image_info = article.get("image_info")
        image_list = image_info.get("image_list") if isinstance(image_info, dict) else None
        if not isinstance(image_list, list):
            raise ValidationError("newspic image_info.image_list 必须是数组")
        if not image_list:
            raise ValidationError("newspic 至少需要 1 张图片")
        if len(image_list) > 20:
            raise ValidationError("newspic 不能超过 20 张图片")
        for index, image in enumerate(image_list):
            media_id = image.get("image_media_id") if isinstance(image, dict) else None
            if not isinstance(media_id, str) or not media_id:
                raise ValidationError(
                    f"newspic image_list[{index}].image_media_id 必须是非空字符串"
                )
        return ArticleValidation(image_count=len(image_list))

    digest = article.get("digest", "")
    if not isinstance(digest, str):
        raise ValidationError("digest 必须是字符串")
    if len(digest) > 120:
        raise ValidationError("digest 不能超过 120 字符")

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
        header = image_file.read(16)
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


def validate_datacube_request(
    report: str, begin_date: str, end_date: str
) -> tuple[date, date]:
    max_days = DATACUBE_MAX_DAYS.get(report)
    if max_days is None:
        raise ValidationError(f"report 不受支持: {report}")
    if not _DATE_PATTERN.fullmatch(begin_date) or not _DATE_PATTERN.fullmatch(end_date):
        raise ValidationError("begin_date 和 end_date 必须是 YYYY-MM-DD")
    try:
        begin = date.fromisoformat(begin_date)
        end = date.fromisoformat(end_date)
    except ValueError as exc:
        raise ValidationError("begin_date 和 end_date 必须是有效的 YYYY-MM-DD") from exc
    if begin > end:
        raise ValidationError("begin_date 不能晚于 end_date")
    if (end - begin).days >= max_days:
        raise ValidationError(f"{report} 最大时间跨度为 {max_days} 天")
    return begin, end


def _validate_menu_name(value: object, *, max_bytes: int, level: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{level}菜单名称必须是非空字符串")
    if len(value.encode("utf-8")) > max_bytes:
        raise ValidationError(f"{level}菜单名称不能超过 {max_bytes} 字节")


def validate_menu_buttons(buttons: list[dict[str, Any]]) -> None:
    if not isinstance(buttons, list) or not buttons:
        raise ValidationError("button 至少需要一个菜单项")
    if len(buttons) > 3:
        raise ValidationError("一级 button 不能超过 3 个")
    for button in buttons:
        if not isinstance(button, dict):
            raise ValidationError("button 菜单项必须是对象")
        _validate_menu_name(button.get("name"), max_bytes=16, level="一级")
        sub_buttons = button.get("sub_button")
        if sub_buttons is None:
            continue
        if not isinstance(sub_buttons, list):
            raise ValidationError("sub_button 必须是数组")
        if len(sub_buttons) > 5:
            raise ValidationError("sub_button 不能超过 5 个")
        for sub_button in sub_buttons:
            if not isinstance(sub_button, dict):
                raise ValidationError("sub_button 菜单项必须是对象")
            _validate_menu_name(sub_button.get("name"), max_bytes=60, level="二级")


_MESSAGE_REQUIRED_FIELDS = {
    "text": ("content",),
    "image": ("media_id",),
    "voice": ("media_id",),
    "video": ("media_id",),
    "music": ("thumb_media_id",),
    "news": ("articles",),
    "mpnews": ("media_id",),
    "mpvideo": ("media_id",),
    "wxcard": ("card_id",),
    "miniprogrampage": ("appid", "pagepath", "thumb_media_id"),
    "msgmenu": ("head_content", "list"),
}


def validate_message(message: dict[str, Any], *, kind: str) -> None:
    if not isinstance(message, dict):
        raise ValidationError("message 必须是对象")
    allowed = MASS_MESSAGE_TYPES if kind == "mass" else CUSTOM_MESSAGE_TYPES
    msgtype = message.get("msgtype")
    if msgtype not in allowed:
        raise ValidationError(f"{kind} msgtype 不受支持: {msgtype}")
    content = message.get(str(msgtype))
    if not isinstance(content, dict):
        raise ValidationError(f"message 缺少 {msgtype} 内容对象")
    missing = [field for field in _MESSAGE_REQUIRED_FIELDS[str(msgtype)] if not content.get(field)]
    if missing:
        raise ValidationError(f"{msgtype} 缺少字段: {', '.join(missing)}")


def _media_mime_type(header: bytes, media_type: str) -> str:
    if media_type in {"image", "thumb"}:
        cover = media_type == "image"
        mime_type = _image_mime_type(header, cover=cover)
        if media_type == "image" and mime_type == "image/bmp":
            raise ValidationError("image 真实格式必须是 JPEG、PNG 或 GIF")
        if media_type == "thumb" and mime_type != "image/jpeg":
            raise ValidationError("thumb 真实格式必须是 JPEG")
        return mime_type
    if media_type == "video":
        if len(header) >= 8 and header[4:8] == b"ftyp":
            return "video/mp4"
        raise ValidationError("video 真实格式必须是 MP4")
    if media_type == "voice":
        if header.startswith(b"ID3") or (
            len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0
        ):
            return "audio/mpeg"
        if header.startswith(b"#!AMR"):
            return "audio/amr"
        if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
            return "audio/wav"
        if header.startswith(b"0&\xb2u\x8ef\xcf\x11"):
            return "audio/x-ms-wma"
        raise ValidationError("voice 真实格式必须是 MP3、AMR、WAV 或 WMA")
    raise ValidationError(f"media_type 不受支持: {media_type}")


def _validate_media_file(
    file_path: str | Path, media_type: str, limits: dict[str, int]
) -> ValidatedMedia:
    if media_type not in limits:
        raise ValidationError(f"media_type 不受支持: {media_type}")
    path, size, header = _resolved_regular_file(file_path)
    mime_type = _media_mime_type(header, media_type)
    if size > limits[media_type]:
        raise ValidationError(f"{media_type} 文件不能超过 {limits[media_type]} 字节")
    return ValidatedMedia(path=path, mime_type=mime_type, size=size)


def validate_permanent_media(
    file_path: str | Path, media_type: str
) -> ValidatedMedia:
    return _validate_media_file(
        file_path,
        media_type,
        {"voice": 2 * 1024 * 1024, "video": 10 * 1024 * 1024},
    )


def validate_temp_media(file_path: str | Path, media_type: str) -> ValidatedMedia:
    return _validate_media_file(
        file_path,
        media_type,
        {
            "image": 2 * 1024 * 1024,
            "voice": 2 * 1024 * 1024,
            "video": 10 * 1024 * 1024,
            "thumb": 64 * 1024,
        },
    )


def validate_download_path(save_path: str | Path) -> Path:
    target = Path(save_path).expanduser().resolve()
    if target.exists():
        raise ValidationError(f"目标文件已存在，拒绝覆盖: {target}")
    return target
