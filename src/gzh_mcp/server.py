"""gzh-mcp 的 MCPServer 入口与分域工具注册。"""

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
DESTRUCTIVE_MUTATION = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=True,
)
PUBLISH_MUTATION = DESTRUCTIVE_MUTATION


def _require_confirmation(tool_name: str, confirm: bool) -> None:
    if confirm is not True:
        raise ValueError(f"{tool_name} 必须显式传 confirm=true")


def register_v1_tools(
    server: MCPServer, client: Any, *, publish_enabled: bool
) -> None:
    @server.tool(annotations=READ_ONLY)
    async def check_credentials() -> dict[str, Any]:
        """验证公众号凭据和 IP 白名单；成功不代表拥有发布权限。"""

        return await client.check_credentials()

    @server.tool(annotations=REMOTE_MUTATION)
    async def upload_content_image(file_path: str) -> dict[str, Any]:
        """上传本机 JPG/PNG 正文图片并返回微信图片 URL。"""

        return await client.upload_content_image(file_path)

    @server.tool(annotations=REMOTE_MUTATION)
    async def upload_cover_image(file_path: str) -> dict[str, Any]:
        """上传本机图片为永久封面素材并返回 media_id。"""

        return await client.upload_cover_image(file_path)

    @server.tool(annotations=REMOTE_MUTATION)
    async def create_draft(articles: list[dict[str, Any]]) -> dict[str, Any]:
        """前置校验后创建一个或多个图文草稿，并自动回读验证。"""

        return await client.create_draft(articles)

    @server.tool(annotations=READ_ONLY)
    async def get_draft(media_id: str) -> dict[str, Any]:
        """读取草稿的完整 news_item 数组。"""

        return await client.get_draft(media_id)

    @server.tool(annotations=REMOTE_MUTATION)
    async def update_draft(
        media_id: str, index: int, article: dict[str, Any]
    ) -> dict[str, Any]:
        """按从 0 开始的文章位置更新草稿。"""

        return await client.update_draft(media_id, index, article)

    @server.tool(annotations=READ_ONLY)
    async def list_drafts(offset: int = 0, count: int = 20) -> dict[str, Any]:
        """分页列出草稿，并通过 draft/count 附带草稿总数。"""

        return await client.list_drafts(offset, count)

    @server.tool(annotations=READ_ONLY)
    async def get_publish_status(publish_id: str) -> dict[str, Any]:
        """按 publish_id 查询异步发布状态。"""

        return await client.get_publish_status(publish_id)

    @server.tool(annotations=READ_ONLY)
    async def list_published(offset: int = 0, count: int = 20) -> dict[str, Any]:
        """分页列出成功发布的文章，用于无状态对账。"""

        return await client.list_published(offset, count)

    if publish_enabled:

        @server.tool(annotations=PUBLISH_MUTATION)
        async def publish_draft(
            media_id: str, confirm: bool = False
        ) -> dict[str, Any]:
            """提交草稿发布；每次调用都必须显式设置 confirm=true。"""

            _require_confirmation("publish_draft", confirm)
            return await client.publish_draft(media_id)


def register_publish_tools(server: MCPServer, client: Any) -> None:
    @server.tool(annotations=DESTRUCTIVE_MUTATION)
    async def delete_draft(
        media_id: str, confirm: bool = False
    ) -> dict[str, Any]:
        """删除草稿；必须显式确认。"""

        _require_confirmation("delete_draft", confirm)
        return await client.delete_draft(media_id)

    @server.tool(annotations=READ_ONLY)
    async def get_published_article(article_id: str) -> dict[str, Any]:
        """按 article_id 获取单篇已发表文章。"""

        return await client.get_published_article(article_id)

    @server.tool(annotations=DESTRUCTIVE_MUTATION)
    async def delete_published_article(
        article_id: str, index: int | None = None, confirm: bool = False
    ) -> dict[str, Any]:
        """删除已发表文章或其中一篇；必须显式确认。"""

        _require_confirmation("delete_published_article", confirm)
        return await client.delete_published_article(article_id, index)


def register_material_tools(server: MCPServer, client: Any) -> None:
    @server.tool(annotations=REMOTE_MUTATION)
    async def upload_video_material(
        file_path: str, title: str, introduction: str
    ) -> dict[str, Any]:
        """上传本机 MP4 为永久视频素材。"""

        return await client.upload_video_material(file_path, title, introduction)

    @server.tool(annotations=REMOTE_MUTATION)
    async def upload_voice_material(file_path: str) -> dict[str, Any]:
        """上传本机音频为永久语音素材。"""

        return await client.upload_voice_material(file_path)

    @server.tool(annotations=READ_ONLY)
    async def get_material(media_id: str, save_path: str) -> dict[str, Any]:
        """获取永久素材；二进制响应写入本机 save_path 且不覆盖。"""

        return await client.get_material(media_id, save_path)

    @server.tool(annotations=DESTRUCTIVE_MUTATION)
    async def delete_material(
        media_id: str, confirm: bool = False
    ) -> dict[str, Any]:
        """删除永久素材；必须显式确认。"""

        _require_confirmation("delete_material", confirm)
        return await client.delete_material(media_id)

    @server.tool(annotations=READ_ONLY)
    async def list_materials(
        material_type: str, offset: int = 0, count: int = 20
    ) -> dict[str, Any]:
        """分页列出指定类型的永久素材。"""

        return await client.list_materials(material_type, offset, count)

    @server.tool(annotations=READ_ONLY)
    async def count_materials() -> dict[str, Any]:
        """获取各类型永久素材数量。"""

        return await client.count_materials()

    @server.tool(annotations=REMOTE_MUTATION)
    async def upload_temp_media(
        file_path: str, media_type: str
    ) -> dict[str, Any]:
        """上传图片、语音、视频或缩略图临时素材。"""

        return await client.upload_temp_media(file_path, media_type)

    @server.tool(annotations=READ_ONLY)
    async def download_temp_media(media_id: str, save_path: str) -> dict[str, Any]:
        """获取临时素材；二进制响应写入本机 save_path 且不覆盖。"""

        return await client.download_temp_media(media_id, save_path)


def register_datacube_tools(server: MCPServer, client: Any) -> None:
    @server.tool(annotations=READ_ONLY)
    async def get_statistics_report(
        report: str, begin_date: str, end_date: str
    ) -> dict[str, Any]:
        """按 report 获取公众号统计数据，并前置校验日期跨度。"""

        return await client.get_statistics_report(report, begin_date, end_date)


def register_user_tools(server: MCPServer, client: Any) -> None:
    @server.tool(annotations=READ_ONLY)
    async def list_users(next_openid: str = "") -> dict[str, Any]:
        """分页获取关注者 OpenID。"""

        return await client.list_users(next_openid)

    @server.tool(annotations=READ_ONLY)
    async def get_user_info(
        openid: str, lang: str = "zh_CN"
    ) -> dict[str, Any]:
        """获取单个用户基本信息。"""

        return await client.get_user_info(openid, lang)

    @server.tool(annotations=READ_ONLY)
    async def batch_get_user_info(openid_list: list[str]) -> dict[str, Any]:
        """批量获取用户基本信息。"""

        return await client.batch_get_user_info(openid_list)

    @server.tool(annotations=REMOTE_MUTATION)
    async def update_user_remark(openid: str, remark: str) -> dict[str, Any]:
        """更新用户备注名。"""

        return await client.update_user_remark(openid, remark)

    @server.tool(annotations=REMOTE_MUTATION)
    async def create_tag(name: str) -> dict[str, Any]:
        """创建用户标签。"""

        return await client.create_tag(name)

    @server.tool(annotations=READ_ONLY)
    async def list_tags() -> dict[str, Any]:
        """列出公众号全部用户标签。"""

        return await client.list_tags()

    @server.tool(annotations=REMOTE_MUTATION)
    async def update_tag(tag_id: int, name: str) -> dict[str, Any]:
        """更新用户标签名。"""

        return await client.update_tag(tag_id, name)

    @server.tool(annotations=DESTRUCTIVE_MUTATION)
    async def delete_tag(tag_id: int, confirm: bool = False) -> dict[str, Any]:
        """删除用户标签；必须显式确认。"""

        _require_confirmation("delete_tag", confirm)
        return await client.delete_tag(tag_id)

    @server.tool(annotations=READ_ONLY)
    async def get_user_ids_by_tag(
        tag_id: int, next_openid: str = ""
    ) -> dict[str, Any]:
        """分页获取指定标签下的关注者 OpenID。"""

        return await client.get_user_ids_by_tag(tag_id, next_openid)

    @server.tool(annotations=REMOTE_MUTATION)
    async def tag_users(tag_id: int, openid_list: list[str]) -> dict[str, Any]:
        """批量为用户添加标签。"""

        return await client.tag_users(tag_id, openid_list)

    @server.tool(annotations=REMOTE_MUTATION)
    async def untag_users(tag_id: int, openid_list: list[str]) -> dict[str, Any]:
        """批量取消用户标签。"""

        return await client.untag_users(tag_id, openid_list)

    @server.tool(annotations=READ_ONLY)
    async def list_blacklist(next_openid: str = "") -> dict[str, Any]:
        """分页获取公众号黑名单。"""

        return await client.list_blacklist(next_openid)

    @server.tool(annotations=REMOTE_MUTATION)
    async def blacklist_users(openid_list: list[str]) -> dict[str, Any]:
        """批量拉黑用户。"""

        return await client.blacklist_users(openid_list)

    @server.tool(annotations=REMOTE_MUTATION)
    async def unblacklist_users(openid_list: list[str]) -> dict[str, Any]:
        """批量取消拉黑用户。"""

        return await client.unblacklist_users(openid_list)


def register_menu_tools(server: MCPServer, client: Any) -> None:
    @server.tool(annotations=REMOTE_MUTATION)
    async def create_menu(buttons: list[dict[str, Any]]) -> dict[str, Any]:
        """创建默认自定义菜单。"""

        return await client.create_menu(buttons)

    @server.tool(annotations=READ_ONLY)
    async def get_current_menu() -> dict[str, Any]:
        """获取当前自定义菜单。"""

        return await client.get_current_menu()

    @server.tool(annotations=DESTRUCTIVE_MUTATION)
    async def delete_menu(confirm: bool = False) -> dict[str, Any]:
        """删除默认自定义菜单；必须显式确认。"""

        _require_confirmation("delete_menu", confirm)
        return await client.delete_menu()

    @server.tool(annotations=REMOTE_MUTATION)
    async def create_conditional_menu(
        buttons: list[dict[str, Any]], match_rule: dict[str, Any]
    ) -> dict[str, Any]:
        """创建个性化菜单。"""

        return await client.create_conditional_menu(buttons, match_rule)

    @server.tool(annotations=DESTRUCTIVE_MUTATION)
    async def delete_conditional_menu(
        menu_id: str, confirm: bool = False
    ) -> dict[str, Any]:
        """删除个性化菜单；必须显式确认。"""

        _require_confirmation("delete_conditional_menu", confirm)
        return await client.delete_conditional_menu(menu_id)

    @server.tool(annotations=READ_ONLY)
    async def try_match_conditional_menu(user_id: str) -> dict[str, Any]:
        """测试指定用户会匹配到的个性化菜单。"""

        return await client.try_match_conditional_menu(user_id)


def register_comment_tools(server: MCPServer, client: Any) -> None:
    @server.tool(annotations=READ_ONLY)
    async def list_comments(
        msg_data_id: int,
        index: int,
        begin: int = 0,
        count: int = 50,
        comment_type: int = 0,
    ) -> dict[str, Any]:
        """分页读取已发表文章评论。"""

        return await client.list_comments(
            msg_data_id, index, begin, count, comment_type
        )

    @server.tool(annotations=REMOTE_MUTATION)
    async def mark_comment_elect(
        msg_data_id: int, index: int, user_comment_id: int
    ) -> dict[str, Any]:
        """将评论标记为精选。"""

        return await client.mark_comment_elect(msg_data_id, index, user_comment_id)

    @server.tool(annotations=REMOTE_MUTATION)
    async def unmark_comment_elect(
        msg_data_id: int, index: int, user_comment_id: int
    ) -> dict[str, Any]:
        """取消评论精选。"""

        return await client.unmark_comment_elect(msg_data_id, index, user_comment_id)


def register_message_tools(
    server: MCPServer, client: Any, *, mass_send_enabled: bool
) -> None:
    if mass_send_enabled:

        @server.tool(annotations=DESTRUCTIVE_MUTATION)
        async def mass_send_by_tag(
            tag_id: int,
            message: dict[str, Any],
            clientmsgid: str,
            confirm: bool = False,
        ) -> dict[str, Any]:
            """按标签群发；必须提供 clientmsgid 并显式确认。"""

            _require_confirmation("mass_send_by_tag", confirm)
            if not clientmsgid:
                raise ValueError("mass_send_by_tag 必须提供 clientmsgid")
            return await client.mass_send_by_tag(tag_id, message, clientmsgid)

        @server.tool(annotations=DESTRUCTIVE_MUTATION)
        async def mass_send_by_openids(
            openid_list: list[str],
            message: dict[str, Any],
            clientmsgid: str,
            confirm: bool = False,
        ) -> dict[str, Any]:
            """按 OpenID 列表群发；必须提供 clientmsgid 并显式确认。"""

            _require_confirmation("mass_send_by_openids", confirm)
            if not clientmsgid:
                raise ValueError("mass_send_by_openids 必须提供 clientmsgid")
            return await client.mass_send_by_openids(
                openid_list, message, clientmsgid
            )

        @server.tool(annotations=REMOTE_MUTATION)
        async def preview_mass_message(
            openid: str,
            message: dict[str, Any],
            wxname: str | None = None,
        ) -> dict[str, Any]:
            """向单个 OpenID 发送群发消息预览。"""

            return await client.preview_mass_message(openid, message, wxname)

    @server.tool(annotations=READ_ONLY)
    async def get_mass_status(msg_id: int) -> dict[str, Any]:
        """查询群发消息发送状态。"""

        return await client.get_mass_status(msg_id)

    @server.tool(annotations=DESTRUCTIVE_MUTATION)
    async def delete_mass_message(
        msg_id: int,
        article_idx: int | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """删除群发消息；必须显式确认。"""

        _require_confirmation("delete_mass_message", confirm)
        return await client.delete_mass_message(msg_id, article_idx)

    @server.tool(annotations=DESTRUCTIVE_MUTATION)
    async def send_custom_message(
        openid: str, message: dict[str, Any], confirm: bool = False
    ) -> dict[str, Any]:
        """发送客服消息；必须显式确认。"""

        _require_confirmation("send_custom_message", confirm)
        return await client.send_custom_message(openid, message)

    @server.tool(annotations=DESTRUCTIVE_MUTATION)
    async def send_template_message(
        openid: str,
        template_id: str,
        data: dict[str, Any],
        url: str | None = None,
        miniprogram: dict[str, Any] | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """发送模板消息；必须显式确认。"""

        _require_confirmation("send_template_message", confirm)
        return await client.send_template_message(
            openid, template_id, data, url, miniprogram
        )

    @server.tool(annotations=DESTRUCTIVE_MUTATION)
    async def send_subscribe_message(
        openid: str,
        template_id: str,
        data: dict[str, Any],
        page: str | None = None,
        miniprogram: dict[str, Any] | None = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """发送订阅通知；必须显式确认。"""

        _require_confirmation("send_subscribe_message", confirm)
        return await client.send_subscribe_message(
            openid, template_id, data, page, miniprogram
        )


def register_misc_tools(server: MCPServer, client: Any) -> None:
    @server.tool(annotations=REMOTE_MUTATION)
    async def create_qrcode(
        action_name: str,
        scene_id: int | None = None,
        scene_str: str | None = None,
        expire_seconds: int | None = None,
    ) -> dict[str, Any]:
        """创建临时或永久参数二维码。"""

        return await client.create_qrcode(
            action_name,
            scene_id=scene_id,
            scene_str=scene_str,
            expire_seconds=expire_seconds,
        )

    @server.tool(annotations=READ_ONLY)
    async def get_jsapi_ticket() -> dict[str, Any]:
        """获取 JS-SDK 的 jsapi_ticket。"""

        return await client.get_jsapi_ticket()

    @server.tool(annotations=READ_ONLY)
    async def get_autoreply_config() -> dict[str, Any]:
        """获取公众号当前自动回复配置。"""

        return await client.get_autoreply_config()

    @server.tool(annotations=READ_ONLY)
    async def get_server_ips() -> dict[str, Any]:
        """获取微信服务器回调 IP 列表。"""

        return await client.get_server_ips()


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
    register_v1_tools(
        server,
        active_client,
        publish_enabled=is_publish_enabled(
            environment.get("GZH_MCP_ALLOW_PUBLISH")
        ),
    )
    register_publish_tools(server, active_client)
    register_material_tools(server, active_client)
    register_datacube_tools(server, active_client)
    register_user_tools(server, active_client)
    register_menu_tools(server, active_client)
    register_comment_tools(server, active_client)
    register_message_tools(
        server,
        active_client,
        mass_send_enabled=is_publish_enabled(
            environment.get("GZH_MCP_ALLOW_MASS_SEND")
        ),
    )
    register_misc_tools(server, active_client)
    return server


def main() -> None:
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
