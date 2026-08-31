from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest

from gzh_mcp.errors import UncertainStateError, WechatAPIError
from gzh_mcp.validation import ValidationError
from gzh_mcp.wechat_client import WechatClient


APPID = "wx1234567890"
SECRET = "unit-test-placeholder-secret"
TOKEN = "unit-test-placeholder-token"


def response(data: dict[str, Any], status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=data)


def client_for(handler: Any) -> WechatClient:
    client = WechatClient(
        APPID,
        SECRET,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    client._token = TOKEN
    client._token_expires_at = float("inf")
    return client


MASS_TEXT = {"msgtype": "text", "text": {"content": "通知"}}
CUSTOM_TEXT = {"msgtype": "text", "text": {"content": "你好"}}
MENU_BUTTONS = [{"name": "菜单", "type": "click", "key": "KEY"}]
MATCH_RULE = {"tag_id": "2", "language": "zh_CN"}


@dataclass(frozen=True)
class EndpointCase:
    method_name: str
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    http_method: str = "POST"
    path: str = ""
    payload: dict[str, Any] | None = None
    params: dict[str, Any] | None = None


ENDPOINT_CASES = [
    EndpointCase("delete_draft", ("draft-id",), path="/cgi-bin/draft/delete", payload={"media_id": "draft-id"}),
    EndpointCase("get_published_article", ("article-id",), path="/cgi-bin/freepublish/getarticle", payload={"article_id": "article-id"}),
    EndpointCase("delete_published_article", ("article-id", 2), path="/cgi-bin/freepublish/delete", payload={"article_id": "article-id", "index": 2}),
    EndpointCase("delete_material", ("media-id",), path="/cgi-bin/material/del_material", payload={"media_id": "media-id"}),
    EndpointCase("list_materials", ("news", 5, 10), path="/cgi-bin/material/batchget_material", payload={"type": "news", "offset": 5, "count": 10}),
    EndpointCase("count_materials", path="/cgi-bin/material/get_materialcount", http_method="GET"),
    EndpointCase("get_statistics_report", ("getusersummary", "2026-08-01", "2026-08-02"), path="/datacube/getusersummary", payload={"begin_date": "2026-08-01", "end_date": "2026-08-02"}),
    EndpointCase("list_users", ("next-id",), path="/cgi-bin/user/get", http_method="GET", params={"next_openid": "next-id"}),
    EndpointCase("get_user_info", ("openid", "en"), path="/cgi-bin/user/info", http_method="GET", params={"openid": "openid", "lang": "en"}),
    EndpointCase("batch_get_user_info", (["o1", "o2"],), path="/cgi-bin/user/info/batchget", payload={"user_list": [{"openid": "o1", "lang": "zh_CN"}, {"openid": "o2", "lang": "zh_CN"}]}),
    EndpointCase("update_user_remark", ("openid", "备注"), path="/cgi-bin/user/info/updateremark", payload={"openid": "openid", "remark": "备注"}),
    EndpointCase("create_tag", ("读者",), path="/cgi-bin/tags/create", payload={"tag": {"name": "读者"}}),
    EndpointCase("list_tags", path="/cgi-bin/tags/get", http_method="GET"),
    EndpointCase("update_tag", (2, "新读者"), path="/cgi-bin/tags/update", payload={"tag": {"id": 2, "name": "新读者"}}),
    EndpointCase("delete_tag", (2,), path="/cgi-bin/tags/delete", payload={"tag": {"id": 2}}),
    EndpointCase("get_user_ids_by_tag", (2, "next-id"), path="/cgi-bin/user/tag/get", payload={"tagid": 2, "next_openid": "next-id"}),
    EndpointCase("tag_users", (2, ["o1", "o2"]), path="/cgi-bin/tags/members/batchtagging", payload={"openid_list": ["o1", "o2"], "tagid": 2}),
    EndpointCase("untag_users", (2, ["o1", "o2"]), path="/cgi-bin/tags/members/batchuntagging", payload={"openid_list": ["o1", "o2"], "tagid": 2}),
    EndpointCase("list_blacklist", ("next-id",), path="/cgi-bin/tags/members/getblacklist", payload={"begin_openid": "next-id"}),
    EndpointCase("blacklist_users", (["o1", "o2"],), path="/cgi-bin/tags/members/batchblacklist", payload={"openid_list": ["o1", "o2"]}),
    EndpointCase("unblacklist_users", (["o1", "o2"],), path="/cgi-bin/tags/members/batchunblacklist", payload={"openid_list": ["o1", "o2"]}),
    EndpointCase("create_menu", (MENU_BUTTONS,), path="/cgi-bin/menu/create", payload={"button": MENU_BUTTONS}),
    EndpointCase("get_current_menu", path="/cgi-bin/menu/get", http_method="GET"),
    EndpointCase("delete_menu", path="/cgi-bin/menu/delete", http_method="GET"),
    EndpointCase("create_conditional_menu", (MENU_BUTTONS, MATCH_RULE), path="/cgi-bin/menu/addconditional", payload={"button": MENU_BUTTONS, "matchrule": MATCH_RULE}),
    EndpointCase("delete_conditional_menu", ("menu-id",), path="/cgi-bin/menu/delconditional", payload={"menuid": "menu-id"}),
    EndpointCase("try_match_conditional_menu", ("openid",), path="/cgi-bin/menu/trymatch", payload={"user_id": "openid"}),
    EndpointCase("list_comments", (123, 1, 0, 20, 0), path="/cgi-bin/comment/list", payload={"msg_data_id": 123, "index": 1, "begin": 0, "count": 20, "type": 0}),
    EndpointCase("mark_comment_elect", (123, 1, 456), path="/cgi-bin/comment/markelect", payload={"msg_data_id": 123, "index": 1, "user_comment_id": 456}),
    EndpointCase("unmark_comment_elect", (123, 1, 456), path="/cgi-bin/comment/unmarkelect", payload={"msg_data_id": 123, "index": 1, "user_comment_id": 456}),
    EndpointCase("mass_send_by_tag", (2, MASS_TEXT, "client-1"), path="/cgi-bin/message/mass/sendall", payload={"filter": {"is_to_all": False, "tag_id": 2}, "msgtype": "text", "text": {"content": "通知"}, "clientmsgid": "client-1"}),
    EndpointCase("mass_send_all", (MASS_TEXT, "client-all"), path="/cgi-bin/message/mass/sendall", payload={"filter": {"is_to_all": True}, "msgtype": "text", "text": {"content": "通知"}, "clientmsgid": "client-all"}),
    EndpointCase("mass_send_by_openids", (["o1", "o2"], MASS_TEXT, "client-2"), path="/cgi-bin/message/mass/send", payload={"touser": ["o1", "o2"], "msgtype": "text", "text": {"content": "通知"}, "clientmsgid": "client-2"}),
    EndpointCase("preview_mass_message", ("openid", MASS_TEXT), path="/cgi-bin/message/mass/preview", payload={"touser": "openid", "msgtype": "text", "text": {"content": "通知"}}),
    EndpointCase("get_mass_status", (123,), path="/cgi-bin/message/mass/get", payload={"msg_id": 123}),
    EndpointCase("delete_mass_message", (123, 2), path="/cgi-bin/message/mass/delete", payload={"msg_id": 123, "article_idx": 2}),
    EndpointCase("send_custom_message", ("openid", CUSTOM_TEXT), path="/cgi-bin/message/custom/send", payload={"touser": "openid", "msgtype": "text", "text": {"content": "你好"}}),
    EndpointCase("send_template_message", ("openid", "template", {"keyword1": {"value": "值"}}), {"url": "https://example.invalid", "miniprogram": {"appid": "wxmini", "pagepath": "pages/a"}}, path="/cgi-bin/message/template/send", payload={"touser": "openid", "template_id": "template", "data": {"keyword1": {"value": "值"}}, "url": "https://example.invalid", "miniprogram": {"appid": "wxmini", "pagepath": "pages/a"}}),
    EndpointCase("send_subscribe_message", ("openid", "template", {"thing1": {"value": "值"}}), {"page": "pages/a", "miniprogram": {"appid": "wxmini", "pagepath": "pages/a"}}, path="/cgi-bin/message/subscribe/bizsend", payload={"touser": "openid", "template_id": "template", "data": {"thing1": {"value": "值"}}, "page": "pages/a", "miniprogram": {"appid": "wxmini", "pagepath": "pages/a"}}),
    EndpointCase("create_qrcode", ("QR_STR_SCENE",), {"scene_str": "campaign", "expire_seconds": 60}, path="/cgi-bin/qrcode/create", payload={"action_name": "QR_STR_SCENE", "action_info": {"scene": {"scene_str": "campaign"}}, "expire_seconds": 60}),
    EndpointCase("get_jsapi_ticket", path="/cgi-bin/ticket/getticket", http_method="GET", params={"type": "jsapi"}),
    EndpointCase("get_autoreply_config", path="/cgi-bin/get_current_autoreply_info", http_method="GET"),
    EndpointCase("get_server_ips", path="/cgi-bin/getcallbackip", http_method="GET"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ENDPOINT_CASES, ids=lambda case: case.method_name)
async def test_b22_json_endpoint_mapping(case: EndpointCase) -> None:
    captured: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return response({"errcode": 0, "errmsg": "ok", "ticket": "ticket", "expires_in": 7200})

    client = client_for(handler)
    try:
        await getattr(client, case.method_name)(*case.args, **case.kwargs)
    finally:
        await client.aclose()

    assert captured is not None
    assert captured.method == case.http_method
    assert captured.url.path == case.path
    assert captured.url.params["access_token"] == TOKEN
    if case.params:
        for key, value in case.params.items():
            assert captured.url.params[key] == str(value)
    if case.payload is not None:
        assert json.loads(captured.content) == case.payload


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "filename", "content", "args", "path", "media_type"),
    [
        ("upload_video_material", "movie.mp4", b"\x00\x00\x00\x18ftypmp42video", ("标题", "简介"), "/cgi-bin/material/add_material", "video"),
        ("upload_voice_material", "voice.mp3", b"ID3voice", (), "/cgi-bin/material/add_material", "voice"),
        ("upload_temp_media", "temp.jpg", b"\xff\xd8\xffimage", ("image",), "/cgi-bin/media/upload", "image"),
    ],
)
async def test_b22_upload_endpoint_mapping(
    tmp_path: Path,
    method_name: str,
    filename: str,
    content: bytes,
    args: tuple[Any, ...],
    path: str,
    media_type: str,
) -> None:
    source = tmp_path / filename
    source.write_bytes(content)
    captured: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return response({"media_id": "media-id", "type": media_type, "created_at": 1})

    client = client_for(handler)
    try:
        await getattr(client, method_name)(source, *args)
    finally:
        await client.aclose()

    assert captured is not None
    assert captured.method == "POST"
    assert captured.url.path == path
    assert captured.url.params["type"] == media_type
    assert b'name="media"' in captured.content
    if method_name == "upload_video_material":
        assert b'name="description"' in captured.content
        assert "标题".encode() in captured.content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "path"),
    [
        ("get_material", "/cgi-bin/material/get_material"),
        ("download_temp_media", "/cgi-bin/media/get"),
    ],
)
async def test_b18_b22_binary_download_creates_parent_and_returns_absolute_path(
    tmp_path: Path, method_name: str, path: str
) -> None:
    target = tmp_path / "nested" / "download.bin"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST" if method_name == "get_material" else request.method == "GET"
        assert request.url.path == path
        return httpx.Response(200, content=b"binary-content", headers={"Content-Type": "application/octet-stream"})

    client = client_for(handler)
    try:
        result = await getattr(client, method_name)("media-id", target)
    finally:
        await client.aclose()

    assert target.read_bytes() == b"binary-content"
    assert result == {"file_path": str(target.resolve()), "size": len(b"binary-content")}


@pytest.mark.asyncio
async def test_b18_binary_download_refuses_to_overwrite_before_http(tmp_path: Path) -> None:
    target = tmp_path / "exists.bin"
    target.write_bytes(b"original")
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=b"replacement")

    client = client_for(handler)
    try:
        with pytest.raises(ValidationError, match="已存在"):
            await client.download_temp_media("media-id", target)
    finally:
        await client.aclose()
    assert calls == 0
    assert target.read_bytes() == b"original"


@pytest.mark.asyncio
async def test_b18_binary_json_error_uses_four_layer_protocol(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response({"errcode": 40007, "errmsg": "invalid media_id"})

    client = client_for(handler)
    try:
        with pytest.raises(WechatAPIError) as exc_info:
            await client.get_material("bad-id", tmp_path / "unused.bin")
    finally:
        await client.aclose()
    assert exc_info.value.errcode == 40007


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name,args",
    [
        ("mass_send_by_tag", (2, MASS_TEXT, "client-1")),
        ("mass_send_all", (MASS_TEXT, "client-all")),
        ("mass_send_by_openids", (["o1"], MASS_TEXT, "client-2")),
        ("preview_mass_message", ("openid", MASS_TEXT)),
        ("send_custom_message", ("openid", CUSTOM_TEXT)),
        ("send_template_message", ("openid", "template", {"k": {"value": "v"}})),
        ("send_subscribe_message", ("openid", "template", {"k": {"value": "v"}})),
    ],
)
async def test_b21_non_idempotent_message_transport_error_is_uncertain_without_retry(
    method_name: str, args: tuple[Any, ...]
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("timeout", request=request)

    client = client_for(handler)
    try:
        with pytest.raises(UncertainStateError):
            await getattr(client, method_name)(*args)
    finally:
        await client.aclose()
    assert calls == 1


@pytest.mark.asyncio
async def test_b21_new_read_endpoint_retries_once_on_server_error() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, text="busy")
        return response({"total": 0, "count": 0, "data": {"openid": []}, "next_openid": ""})

    client = client_for(handler)
    try:
        result = await client.list_users()
    finally:
        await client.aclose()
    assert result["total"] == 0
    assert calls == 2


@pytest.mark.asyncio
async def test_b24_new_endpoint_redacts_access_token_from_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response({"errcode": 45009, "errmsg": f"access_token={TOKEN}"})

    client = client_for(handler)
    try:
        with pytest.raises(WechatAPIError) as exc_info:
            await client.list_tags()
    finally:
        await client.aclose()
    assert TOKEN not in str(exc_info.value)
    assert "***" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "args"),
    [
        ("get_statistics_report", ("unknown", "2026-08-01", "2026-08-01")),
        ("create_menu", ([{"name": "超长一级菜单甲", "type": "click", "key": "x"}],)),
        ("mass_send_by_tag", (2, {"msgtype": "music", "music": {}}, "client")),
        ("send_custom_message", ("openid", {"msgtype": "image"})),
    ],
)
async def test_b17_b19_b20_validation_happens_before_http(
    method_name: str, args: tuple[Any, ...]
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response({"errcode": 0})

    client = client_for(handler)
    try:
        with pytest.raises(ValidationError):
            await getattr(client, method_name)(*args)
    finally:
        await client.aclose()
    assert calls == 0


@pytest.mark.asyncio
async def test_b25_delete_conditional_menu_normalizes_integer_menu_id() -> None:
    """整型 menuid（addconditional 实际返回）应归一化为字符串 payload；bool 拒绝。"""

    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["payload"] = json.loads(request.content)
        return response({"errcode": 0, "errmsg": "ok"})

    client = client_for(handler)
    try:
        await client.delete_conditional_menu(425787302)
    finally:
        await client.aclose()
    assert captured["path"] == "/cgi-bin/menu/delconditional"
    assert captured["payload"] == {"menuid": "425787302"}

    with pytest.raises(ValidationError):
        await client.delete_conditional_menu(True)  # type: ignore[arg-type]
