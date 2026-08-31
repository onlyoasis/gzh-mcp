import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp import Client

from gzh_mcp.server import _configure_sensitive_loggers, create_server


class FakeWechatClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def check_credentials(self) -> dict[str, object]:
        self.calls.append(("check_credentials", ()))
        return {"ok": True, "appid_prefix": "wx1234"}

    async def upload_content_image(self, file_path: str) -> dict[str, object]:
        self.calls.append(("upload_content_image", (file_path,)))
        return {"url": "https://mmbiz.qpic.cn/a.png"}

    async def upload_cover_image(self, file_path: str) -> dict[str, object]:
        self.calls.append(("upload_cover_image", (file_path,)))
        return {"media_id": "cover-id"}

    async def create_draft(self, articles: list[dict[str, object]]) -> dict[str, object]:
        self.calls.append(("create_draft", (articles,)))
        return {"media_id": "draft-id", "verified": True}

    async def get_draft(self, media_id: str) -> dict[str, object]:
        self.calls.append(("get_draft", (media_id,)))
        return {"news_item": [{"title": "标题"}]}

    async def update_draft(
        self, media_id: str, index: int, article: dict[str, object]
    ) -> dict[str, object]:
        self.calls.append(("update_draft", (media_id, index, article)))
        return {"errcode": 0, "errmsg": "ok"}

    async def list_drafts(self, offset: int, count: int) -> dict[str, object]:
        self.calls.append(("list_drafts", (offset, count)))
        return {"total_count": 0, "item_count": 0, "item": []}

    async def get_publish_status(self, publish_id: str) -> dict[str, object]:
        self.calls.append(("get_publish_status", (publish_id,)))
        return {"publish_id": publish_id, "publish_status": 1}

    async def list_published(self, offset: int, count: int) -> dict[str, object]:
        self.calls.append(("list_published", (offset, count)))
        return {"total_count": 0, "item_count": 0, "item": []}


def test_sensitive_http_loggers_never_emit_access_token_urls() -> None:
    httpx_logger = logging.getLogger("httpx")
    httpcore_logger = logging.getLogger("httpcore")
    previous_levels = (httpx_logger.level, httpcore_logger.level)
    try:
        httpx_logger.setLevel(logging.INFO)
        httpcore_logger.setLevel(logging.DEBUG)

        _configure_sensitive_loggers()

        assert httpx_logger.level == logging.WARNING
        assert httpcore_logger.level == logging.WARNING
    finally:
        httpx_logger.setLevel(previous_levels[0])
        httpcore_logger.setLevel(previous_levels[1])

    async def publish_draft(self, media_id: str) -> dict[str, object]:
        self.calls.append(("publish_draft", (media_id,)))
        return {
            "publish_id": "publish-id",
            "media_id": media_id,
            "title": "标题",
            "appid_prefix": "wx1234",
        }


EXPECTED_DEFAULT_TOOLS = {
    "check_credentials",
    "upload_content_image",
    "upload_cover_image",
    "create_draft",
    "get_draft",
    "update_draft",
    "list_drafts",
    "get_publish_status",
    "list_published",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("switch", [None, "", " ", "0", "false", "True"])
async def test_b1_publish_tool_is_absent_for_non_strict_values(switch: str | None) -> None:
    client = FakeWechatClient()
    environ = {} if switch is None else {"GZH_MCP_ALLOW_PUBLISH": switch}
    server = create_server(client=client, environ=environ)
    async with Client(server) as mcp_client:
        tools = await mcp_client.list_tools()
    names = {tool.name for tool in tools.tools}
    assert EXPECTED_DEFAULT_TOOLS <= names
    assert "publish_draft" not in names


@pytest.mark.asyncio
@pytest.mark.parametrize("switch", ["1", "true"])
async def test_b1_publish_tool_is_registered_for_strict_true(switch: str) -> None:
    server = create_server(
        client=FakeWechatClient(), environ={"GZH_MCP_ALLOW_PUBLISH": switch}
    )
    async with Client(server) as mcp_client:
        tools = await mcp_client.list_tools()
    names = {tool.name for tool in tools.tools}
    assert EXPECTED_DEFAULT_TOOLS | {"publish_draft"} <= names


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", [{"media_id": "draft-id"}, {"media_id": "draft-id", "confirm": False}])
async def test_b2_publish_requires_explicit_confirmation_before_client_call(
    arguments: dict[str, object],
) -> None:
    client = FakeWechatClient()
    server = create_server(client=client, environ={"GZH_MCP_ALLOW_PUBLISH": "1"})
    async with Client(server) as mcp_client:
        result = await mcp_client.call_tool("publish_draft", arguments)
    assert result.is_error is True
    assert client.calls == []


@pytest.mark.asyncio
async def test_tool_dict_return_populates_structured_and_text_content() -> None:
    server = create_server(client=FakeWechatClient(), environ={})
    async with Client(server) as mcp_client:
        result = await mcp_client.call_tool("check_credentials", {})
    assert result.is_error is False
    assert result.structured_content == {"ok": True, "appid_prefix": "wx1234"}
    assert json.loads(result.content[0].text) == result.structured_content


def test_b9_stdio_stdout_contains_only_json_rpc() -> None:
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1"},
        },
    }
    env = os.environ.copy()
    env.update(
        {
            "WECHAT_APPID": "wx-placeholder-appid",
            "WECHAT_SECRET": "placeholder-secret",
            "GZH_MCP_ALLOW_PUBLISH": "0",
        }
    )
    entrypoint = Path(sys.executable).with_name("gzh-mcp")
    completed = subprocess.run(
        [str(entrypoint)],
        input=json.dumps(initialize) + "\n",
        text=True,
        capture_output=True,
        env=env,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    lines = [line for line in completed.stdout.splitlines() if line]
    assert lines
    messages = [json.loads(line) for line in lines]
    assert messages[0]["jsonrpc"] == "2.0"
    assert messages[0]["id"] == 1


def test_create_server_passes_only_explicit_proxy_to_wechat_client(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class ProxyRecordingClient(FakeWechatClient):
        def __init__(self, appid: str, secret: str, *, proxy: str | None = None) -> None:
            super().__init__()
            captured.update({"appid": appid, "secret": secret, "proxy": proxy})

    monkeypatch.setattr("gzh_mcp.server.WechatClient", ProxyRecordingClient)
    create_server(
        environ={
            "WECHAT_APPID": "wx-proxy-test",
            "WECHAT_SECRET": "proxy-test-secret",
            "HTTPS_PROXY": "http://ambient.invalid:9999",
            "GZH_MCP_PROXY": "http://127.0.0.1:2080",
        }
    )

    assert captured == {
        "appid": "wx-proxy-test",
        "secret": "proxy-test-secret",
        "proxy": "http://127.0.0.1:2080",
    }
