"""gzh-mcp 的 MCPServer 入口与工具注册。"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from .validation import is_publish_enabled
from .wechat_client import WechatClient


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)
REMOTE_MUTATION = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)
PUBLISH_MUTATION = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=True,
)


def create_server(
    *,
    client: Any | None = None,
    environ: Mapping[str, str] | None = None,
) -> MCPServer:
    environment = os.environ if environ is None else environ
    active_client = client or WechatClient(
        environment.get("WECHAT_APPID", ""), environment.get("WECHAT_SECRET", "")
    )
    server = MCPServer("gzh-mcp")

    @server.tool(annotations=READ_ONLY)
    async def check_credentials() -> dict[str, Any]:
        """验证公众号凭据和 IP 白名单；成功不代表拥有发布权限。"""

        return await active_client.check_credentials()

    @server.tool(annotations=REMOTE_MUTATION)
    async def upload_content_image(file_path: str) -> dict[str, Any]:
        """上传本机 JPG/PNG 正文图片并返回微信图片 URL。"""

        return await active_client.upload_content_image(file_path)

    @server.tool(annotations=REMOTE_MUTATION)
    async def upload_cover_image(file_path: str) -> dict[str, Any]:
        """上传本机图片为永久封面素材并返回 media_id。"""

        return await active_client.upload_cover_image(file_path)

    @server.tool(annotations=REMOTE_MUTATION)
    async def create_draft(articles: list[dict[str, Any]]) -> dict[str, Any]:
        """前置校验后创建一个或多个图文草稿，并自动回读验证。"""

        return await active_client.create_draft(articles)

    @server.tool(annotations=READ_ONLY)
    async def get_draft(media_id: str) -> dict[str, Any]:
        """读取草稿的完整 news_item 数组。"""

        return await active_client.get_draft(media_id)

    @server.tool(annotations=REMOTE_MUTATION)
    async def update_draft(
        media_id: str, index: int, article: dict[str, Any]
    ) -> dict[str, Any]:
        """按从 0 开始的文章位置更新草稿。"""

        return await active_client.update_draft(media_id, index, article)

    @server.tool(annotations=READ_ONLY)
    async def list_drafts(offset: int = 0, count: int = 20) -> dict[str, Any]:
        """分页列出草稿，并通过 draft/count 附带草稿总数。"""

        return await active_client.list_drafts(offset, count)

    @server.tool(annotations=READ_ONLY)
    async def get_publish_status(publish_id: str) -> dict[str, Any]:
        """按 publish_id 查询异步发布状态。"""

        return await active_client.get_publish_status(publish_id)

    @server.tool(annotations=READ_ONLY)
    async def list_published(offset: int = 0, count: int = 20) -> dict[str, Any]:
        """分页列出成功发布的文章，用于无状态对账。"""

        return await active_client.list_published(offset, count)

    if is_publish_enabled(environment.get("GZH_MCP_ALLOW_PUBLISH")):

        @server.tool(annotations=PUBLISH_MUTATION)
        async def publish_draft(
            media_id: str, confirm: bool = False
        ) -> dict[str, Any]:
            """提交草稿发布；每次调用都必须显式设置 confirm=true。"""

            if confirm is not True:
                raise ValueError("publish_draft 必须显式传 confirm=true")
            return await active_client.publish_draft(media_id)

    return server


def main() -> None:
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
