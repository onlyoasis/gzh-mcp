from __future__ import annotations

from typing import Any

import pytest
from mcp import Client

from gzh_mcp.server import create_server


NEW_TOOLS = {
    "delete_draft",
    "get_published_article",
    "delete_published_article",
    "upload_video_material",
    "upload_voice_material",
    "get_material",
    "delete_material",
    "list_materials",
    "count_materials",
    "upload_temp_media",
    "download_temp_media",
    "get_statistics_report",
    "list_users",
    "get_user_info",
    "batch_get_user_info",
    "update_user_remark",
    "create_tag",
    "list_tags",
    "update_tag",
    "delete_tag",
    "get_user_ids_by_tag",
    "tag_users",
    "untag_users",
    "list_blacklist",
    "blacklist_users",
    "unblacklist_users",
    "create_menu",
    "get_current_menu",
    "delete_menu",
    "create_conditional_menu",
    "delete_conditional_menu",
    "try_match_conditional_menu",
    "list_comments",
    "mark_comment_elect",
    "unmark_comment_elect",
    "mass_send_by_tag",
    "mass_send_by_openids",
    "preview_mass_message",
    "get_mass_status",
    "delete_mass_message",
    "send_custom_message",
    "send_template_message",
    "send_subscribe_message",
    "create_qrcode",
    "get_jsapi_ticket",
    "get_autoreply_config",
    "get_server_ips",
}

MASS_GATED_TOOLS = {
    "mass_send_by_tag",
    "mass_send_by_openids",
    "preview_mass_message",
}


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def __getattr__(self, name: str) -> Any:
        async def record(*args: Any, **kwargs: Any) -> dict[str, object]:
            self.calls.append((name, args, kwargs))
            return {"errcode": 0, "errmsg": "ok"}

        return record


async def listed_tool_names(environ: dict[str, str]) -> set[str]:
    server = create_server(client=RecordingClient(), environ=environ)
    async with Client(server) as mcp_client:
        tools = await mcp_client.list_tools()
    return {tool.name for tool in tools.tools}


@pytest.mark.asyncio
@pytest.mark.parametrize("switch", [None, "", " ", "0", "false", "True"])
async def test_b13_mass_tools_are_absent_for_non_strict_values(
    switch: str | None,
) -> None:
    environ = {} if switch is None else {"GZH_MCP_ALLOW_MASS_SEND": switch}
    names = await listed_tool_names(environ)
    assert MASS_GATED_TOOLS.isdisjoint(names)
    assert NEW_TOOLS - MASS_GATED_TOOLS <= names
    assert len(NEW_TOOLS & names) == 44


@pytest.mark.asyncio
@pytest.mark.parametrize("switch", ["1", "true"])
async def test_b13_mass_tools_are_registered_for_strict_true(switch: str) -> None:
    names = await listed_tool_names({"GZH_MCP_ALLOW_MASS_SEND": switch})
    assert NEW_TOOLS <= names
    assert len(NEW_TOOLS & names) == 47


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("mass_send_by_tag", {"tag_id": 2, "message": {"msgtype": "text", "text": {"content": "x"}}, "confirm": True}),
        ("mass_send_by_tag", {"tag_id": 2, "message": {"msgtype": "text", "text": {"content": "x"}}, "clientmsgid": "client", "confirm": False}),
        ("mass_send_by_openids", {"openid_list": ["o1"], "message": {"msgtype": "text", "text": {"content": "x"}}, "confirm": True}),
        ("mass_send_by_openids", {"openid_list": ["o1"], "message": {"msgtype": "text", "text": {"content": "x"}}, "clientmsgid": "client", "confirm": False}),
    ],
)
async def test_b14_mass_send_requires_clientmsgid_and_confirmation_before_client_call(
    tool_name: str, arguments: dict[str, object]
) -> None:
    client = RecordingClient()
    server = create_server(client=client, environ={"GZH_MCP_ALLOW_MASS_SEND": "1"})
    async with Client(server) as mcp_client:
        result = await mcp_client.call_tool(tool_name, arguments)
    assert result.is_error is True
    assert client.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("delete_draft", {"media_id": "m"}),
        ("delete_published_article", {"article_id": "a"}),
        ("delete_material", {"media_id": "m"}),
        ("delete_tag", {"tag_id": 2}),
        ("delete_menu", {}),
        ("delete_conditional_menu", {"menu_id": "m"}),
        ("delete_mass_message", {"msg_id": 1}),
    ],
)
async def test_b15_delete_tools_require_confirmation_before_client_call(
    tool_name: str, arguments: dict[str, object]
) -> None:
    client = RecordingClient()
    server = create_server(client=client, environ={})
    async with Client(server) as mcp_client:
        result = await mcp_client.call_tool(tool_name, arguments)
    assert result.is_error is True
    assert client.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("send_custom_message", {"openid": "o", "message": {"msgtype": "text", "text": {"content": "x"}}}),
        ("send_template_message", {"openid": "o", "template_id": "t", "data": {}}),
        ("send_subscribe_message", {"openid": "o", "template_id": "t", "data": {}}),
    ],
)
async def test_b16_direct_message_tools_require_confirmation_before_client_call(
    tool_name: str, arguments: dict[str, object]
) -> None:
    client = RecordingClient()
    server = create_server(client=client, environ={})
    async with Client(server) as mcp_client:
        result = await mcp_client.call_tool(tool_name, arguments)
    assert result.is_error is True
    assert client.calls == []


@pytest.mark.asyncio
async def test_b25_delete_conditional_menu_accepts_integer_menu_id() -> None:
    """真实账号实测（2026-08-30）：menu/addconditional 返回整型 menuid（425787302），
    agent 原样回传 delete_conditional_menu 时被 str 参数声明拒绝（pydantic
    string_type），create→delete 自然工作流被打断。"""

    client = RecordingClient()
    server = create_server(client=client, environ={})
    async with Client(server) as mcp_client:
        result = await mcp_client.call_tool(
            "delete_conditional_menu", {"menu_id": 425787302, "confirm": True}
        )
    assert result.is_error is False
    assert client.calls and client.calls[0][0] == "delete_conditional_menu"
