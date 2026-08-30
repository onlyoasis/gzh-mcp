import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from gzh_mcp.errors import (
    UncertainStateError,
    WechatAPIError,
    WechatHTTPError,
    WechatResponseError,
    WechatTransportError,
)
from gzh_mcp.validation import ValidationError
from gzh_mcp.wechat_client import WechatClient


APPID = "wx1234567890"
SECRET = "unit-test-placeholder-secret"
TOKEN = "unit-test-placeholder-token"


def response(data: dict[str, Any], status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=data)


def client_for(
    handler: Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]],
) -> WechatClient:
    return WechatClient(
        APPID,
        SECRET,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def valid_article(**overrides: object) -> dict[str, object]:
    article: dict[str, object] = {
        "article_type": "news",
        "title": "中文标题",
        "author": "作者",
        "digest": "摘要",
        "content": '<p>中文正文<img src="https://mmbiz.qpic.cn/a.png"></p>',
        "thumb_media_id": "cover-media",
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }
    article.update(overrides)
    return article


def draft_get_response(article: dict[str, object]) -> dict[str, Any]:
    return {
        "news_item": [article],
        "create_time": 1_725_000_000,
        "update_time": 1_725_000_001,
    }


@pytest.mark.asyncio
async def test_stable_token_cache_is_single_flight() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        assert request.url.path == "/cgi-bin/stable_token"
        calls += 1
        await asyncio.sleep(0.01)
        return response({"access_token": TOKEN, "expires_in": 7200})

    client = client_for(handler)
    try:
        tokens = await asyncio.gather(*(client.get_access_token() for _ in range(10)))
    finally:
        await client.aclose()

    assert tokens == [TOKEN] * 10
    assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler_result", "error_type"),
    [
        (httpx.Response(502, text="bad gateway"), WechatHTTPError),
        (httpx.Response(200, text="not-json"), WechatResponseError),
        (response({"errcode": 40164, "errmsg": "invalid ip"}), WechatAPIError),
    ],
)
async def test_four_error_layers_after_transport(
    handler_result: httpx.Response, error_type: type[Exception]
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cgi-bin/stable_token":
            return response({"access_token": TOKEN, "expires_in": 7200})
        return handler_result

    client = client_for(handler)
    try:
        with pytest.raises(error_type):
            await client.get_draft("draft-id")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_transport_error_is_distinct_for_read_request() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.url.path == "/cgi-bin/stable_token":
            return response({"access_token": TOKEN, "expires_in": 7200})
        calls += 1
        raise httpx.ConnectError("offline", request=request)

    client = client_for(handler)
    try:
        with pytest.raises(WechatTransportError):
            await client.get_draft("draft-id")
    finally:
        await client.aclose()
    assert calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "publish"])
async def test_b6_non_idempotent_transport_error_has_uncertain_state_and_no_retry(
    operation: str,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.url.path == "/cgi-bin/stable_token":
            return response({"access_token": TOKEN, "expires_in": 7200})
        if operation == "publish" and request.url.path == "/cgi-bin/draft/get":
            return response(draft_get_response(valid_article()))
        calls += 1
        raise httpx.ReadTimeout("timeout", request=request)

    client = client_for(handler)
    try:
        with pytest.raises(UncertainStateError, match="状态不确定"):
            if operation == "create":
                await client.create_draft([valid_article()])
            else:
                await client.publish_draft("draft-id")
    finally:
        await client.aclose()
    assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("errcode", [40014, 42001])
async def test_b7_business_token_error_refreshes_and_retries_once(errcode: int) -> None:
    requests: list[httpx.Request] = []
    tokens = iter(["expired-token", "fresh-token"])

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/cgi-bin/stable_token":
            return response({"access_token": next(tokens), "expires_in": 7200})
        if request.url.params["access_token"] == "expired-token":
            return response({"errcode": errcode, "errmsg": "token expired"})
        return response(draft_get_response(valid_article()))

    client = client_for(handler)
    try:
        result = await client.get_draft("draft-id")
    finally:
        await client.aclose()

    assert result["news_item"][0]["title"] == "中文标题"
    stable_requests = [r for r in requests if r.url.path == "/cgi-bin/stable_token"]
    assert len(stable_requests) == 2
    assert json.loads(stable_requests[1].content)["force_refresh"] is True


@pytest.mark.asyncio
async def test_b7_stable_token_40001_is_not_retried_or_refreshed() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response({"errcode": 40001, "errmsg": "invalid appsecret"})

    client = client_for(handler)
    try:
        with pytest.raises(WechatAPIError) as exc_info:
            await client.get_access_token()
    finally:
        await client.aclose()
    assert exc_info.value.errcode == 40001
    assert calls == 1


@pytest.mark.asyncio
async def test_b8_error_redacts_token_secret_and_query_values() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cgi-bin/stable_token":
            return response({"access_token": TOKEN, "expires_in": 7200})
        return response(
            {
                "errcode": 45009,
                "errmsg": f"token={TOKEN} secret={SECRET} access_token={TOKEN}",
            }
        )

    client = client_for(handler)
    try:
        with pytest.raises(WechatAPIError) as exc_info:
            await client.get_draft("draft-id")
    finally:
        await client.aclose()
    message = str(exc_info.value)
    assert TOKEN not in message
    assert SECRET not in message
    assert "***" in message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"title": "题" * 33},
        {"digest": "摘" * 121},
        {"content": "文" * 20_000},
        {"content": '<img src="https://example.com/a.png">'},
        {"content": "<script>alert(1)</script>"},
    ],
)
async def test_b3_create_validation_happens_before_any_http_request(
    overrides: dict[str, object],
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response({"access_token": TOKEN, "expires_in": 7200})

    client = client_for(handler)
    try:
        with pytest.raises(ValidationError):
            await client.create_draft([valid_article(**overrides)])
    finally:
        await client.aclose()
    assert calls == 0


@pytest.mark.asyncio
async def test_b10_create_draft_sends_utf8_chinese_json_and_reads_back() -> None:
    add_body = b""
    article = valid_article()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal add_body
        if request.url.path == "/cgi-bin/stable_token":
            return response({"access_token": TOKEN, "expires_in": 7200})
        if request.url.path == "/cgi-bin/draft/add":
            add_body = request.content
            return response({"media_id": "draft-media-id"})
        assert request.url.path == "/cgi-bin/draft/get"
        return response(draft_get_response(article))

    client = client_for(handler)
    try:
        result = await client.create_draft([article])
    finally:
        await client.aclose()

    assert "中文正文".encode() in add_body
    assert b"\\u4e2d" not in add_body
    assert result == {"media_id": "draft-media-id", "verified": True}


@pytest.mark.asyncio
async def test_b11_create_draft_verified_when_wechat_rewrites_src_to_data_src() -> None:
    """微信保存草稿会把 img 的 src 归一化为 data-src（懒加载），回读验证必须按同口径计数。

    真实账号验收（2026-08-30）发现：回读正文只剩 data-src 时 image_count=0，
    create_draft 对所有带图文章误报 verified=false。
    """

    article = valid_article()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cgi-bin/stable_token":
            return response({"access_token": TOKEN, "expires_in": 7200})
        if request.url.path == "/cgi-bin/draft/add":
            return response({"media_id": "draft-media-id"})
        rewritten = {
            **article,
            "content": (
                '<p>中文正文<img data-src="https://mmbiz.qpic.cn/a.png" '
                'style="width:100%;"></p>'
            ),
        }
        return response(draft_get_response(rewritten))

    client = client_for(handler)
    try:
        result = await client.create_draft([article])
    finally:
        await client.aclose()

    assert result == {"media_id": "draft-media-id", "verified": True}


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ["title", "images", "content"])
async def test_b4_create_draft_returns_media_id_with_verification_error(mismatch: str) -> None:
    article = valid_article(content='<p>' + "正文" * 100 + '<img src="https://mmbiz.qpic.cn/a.png"></p>')
    readback = dict(article)
    if mismatch == "title":
        readback["title"] = "被替换的标题"
    elif mismatch == "images":
        readback["content"] = "<p>没有图片</p>"
    else:
        readback["content"] = "<p>正文缩水</p><img src=\"https://mmbiz.qpic.cn/a.png\">"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cgi-bin/stable_token":
            return response({"access_token": TOKEN, "expires_in": 7200})
        if request.url.path == "/cgi-bin/draft/add":
            return response({"media_id": "draft-media-id"})
        return response(draft_get_response(readback))

    client = client_for(handler)
    try:
        result = await client.create_draft([article])
    finally:
        await client.aclose()
    assert result["media_id"] == "draft-media-id"
    assert result["verified"] is False
    assert result["verification_errors"]


@pytest.mark.asyncio
async def test_update_draft_uses_official_object_payload_shape() -> None:
    captured: dict[str, Any] = {}
    article = valid_article()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cgi-bin/stable_token":
            return response({"access_token": TOKEN, "expires_in": 7200})
        captured.update(json.loads(request.content))
        return response({"errcode": 0, "errmsg": "ok"})

    client = client_for(handler)
    try:
        await client.update_draft("draft-id", 0, article)
    finally:
        await client.aclose()
    assert captured == {"media_id": "draft-id", "index": 0, "articles": article}


@pytest.mark.asyncio
async def test_list_drafts_uses_official_response_shape_and_count_endpoint() -> None:
    paths: list[str] = []
    batch = {
        "total_count": 1,
        "item_count": 1,
        "item": [
            {
                "media_id": "draft-id",
                "content": {"news_item": [valid_article()]},
                "update_time": 1_725_000_001,
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/cgi-bin/stable_token":
            return response({"access_token": TOKEN, "expires_in": 7200})
        if request.url.path == "/cgi-bin/draft/count":
            return response({"total_count": 1})
        return response(batch)

    client = client_for(handler)
    try:
        result = await client.list_drafts(0, 20)
    finally:
        await client.aclose()
    assert result == batch
    assert "/cgi-bin/draft/count" in paths


@pytest.mark.asyncio
async def test_publish_read_apis_preserve_official_response_fields() -> None:
    status = {
        "publish_id": "publish-id",
        "publish_status": 0,
        "article_id": "article-id",
        "article_detail": {"count": 1, "item": [{"idx": 1, "article_url": "https://mp.weixin.qq.com/s/x"}]},
        "fail_idx": [],
    }
    published = {
        "total_count": 1,
        "item_count": 1,
        "item": [
            {
                "article_id": "article-id",
                "content": {"news_item": [valid_article()]},
                "update_time": 1_725_000_001,
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cgi-bin/stable_token":
            return response({"access_token": TOKEN, "expires_in": 7200})
        if request.url.path == "/cgi-bin/freepublish/get":
            return response(status)
        return response(published)

    client = client_for(handler)
    try:
        assert await client.get_publish_status("publish-id") == status
        assert await client.list_published(0, 20) == published
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_upload_content_image_uses_validated_multipart(tmp_path: Path) -> None:
    image = tmp_path / "body.dat"
    image.write_bytes(b"\xff\xd8\xffimage")
    request_body = b""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_body
        if request.url.path == "/cgi-bin/stable_token":
            return response({"access_token": TOKEN, "expires_in": 7200})
        request_body = request.content
        return response({"url": "https://mmbiz.qpic.cn/uploaded.jpg"})

    client = client_for(handler)
    try:
        result = await client.upload_content_image(image)
    finally:
        await client.aclose()
    assert result["url"].startswith("https://mmbiz.qpic.cn/")
    assert b'name="media"' in request_body
    assert b"image/jpeg" in request_body


@pytest.mark.asyncio
async def test_b5_upload_rejects_invalid_file_before_token_request(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response({"access_token": TOKEN, "expires_in": 7200})

    client = client_for(handler)
    try:
        with pytest.raises(ValidationError, match="不存在"):
            await client.upload_content_image(tmp_path / "missing.png")
    finally:
        await client.aclose()
    assert calls == 0


@pytest.mark.asyncio
async def test_upload_cover_image_uses_permanent_image_material_endpoint(
    tmp_path: Path,
) -> None:
    image = tmp_path / "cover.gif"
    image.write_bytes(b"GIF89aimage")
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        if request.url.path == "/cgi-bin/stable_token":
            return response({"access_token": TOKEN, "expires_in": 7200})
        captured_request = request
        return response({"media_id": "cover-media-id", "url": "https://example.invalid"})

    client = client_for(handler)
    try:
        result = await client.upload_cover_image(image)
    finally:
        await client.aclose()
    assert result["media_id"] == "cover-media-id"
    assert captured_request is not None
    assert captured_request.url.path == "/cgi-bin/material/add_material"
    assert captured_request.url.params["type"] == "image"
    assert b"image/gif" in captured_request.content


@pytest.mark.asyncio
async def test_publish_draft_returns_account_title_and_identifiers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cgi-bin/stable_token":
            return response({"access_token": TOKEN, "expires_in": 7200})
        if request.url.path == "/cgi-bin/draft/get":
            return response(draft_get_response(valid_article()))
        assert request.url.path == "/cgi-bin/freepublish/submit"
        return response({"publish_id": "publish-id", "msg_data_id": "msg-data-id"})

    client = client_for(handler)
    try:
        result = await client.publish_draft("draft-id")
    finally:
        await client.aclose()
    assert result == {
        "publish_id": "publish-id",
        "msg_data_id": "msg-data-id",
        "media_id": "draft-id",
        "title": "中文标题",
        "appid_prefix": "wx1234",
    }


@pytest.mark.asyncio
async def test_b12_publish_draft_accepts_integer_publish_id() -> None:
    """真实账号验收（2026-08-30）：submit 成功（文章已发布）但 publish_id 是整数时，
    旧代码抛 WechatResponseError，导致「发布成功却被报错」的不确定状态。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cgi-bin/stable_token":
            return response({"access_token": TOKEN, "expires_in": 7200})
        if request.url.path == "/cgi-bin/draft/get":
            return response(draft_get_response(valid_article()))
        assert request.url.path == "/cgi-bin/freepublish/submit"
        return response({"publish_id": 100000233, "msg_data_id": 12345})

    client = client_for(handler)
    try:
        result = await client.publish_draft("draft-id")
    finally:
        await client.aclose()
    assert result["publish_id"] == "100000233"
    assert result["msg_data_id"] == 12345
