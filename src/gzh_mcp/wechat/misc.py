"""二维码、JSAPI ticket、自动回复与服务器 IP 接口。"""

from __future__ import annotations

from typing import Any

from ..validation import ValidationError


QR_ACTIONS = {
    "QR_SCENE",
    "QR_STR_SCENE",
    "QR_LIMIT_SCENE",
    "QR_LIMIT_STR_SCENE",
}


class MiscMixin:
    async def create_qrcode(
        self,
        action_name: str,
        *,
        scene_id: int | None = None,
        scene_str: str | None = None,
        expire_seconds: int | None = None,
    ) -> dict[str, Any]:
        if action_name not in QR_ACTIONS:
            raise ValidationError(f"action_name 不受支持: {action_name}")
        is_string_scene = action_name in {"QR_STR_SCENE", "QR_LIMIT_STR_SCENE"}
        if is_string_scene:
            if not scene_str or len(scene_str) > 64:
                raise ValidationError("scene_str 长度必须为 1 到 64")
            scene: dict[str, Any] = {"scene_str": scene_str}
        else:
            if isinstance(scene_id, bool) or not isinstance(scene_id, int) or scene_id < 1:
                raise ValidationError("scene_id 必须是正整数")
            maximum = 100_000 if action_name == "QR_LIMIT_SCENE" else 2**32 - 1
            if scene_id > maximum:
                raise ValidationError(f"scene_id 不能超过 {maximum}")
            scene = {"scene_id": scene_id}
        payload: dict[str, Any] = {
            "action_name": action_name,
            "action_info": {"scene": scene},
        }
        if expire_seconds is not None:
            if action_name.startswith("QR_LIMIT_"):
                raise ValidationError("永久二维码不能设置 expire_seconds")
            if expire_seconds < 1 or expire_seconds > 2_592_000:
                raise ValidationError("expire_seconds 必须在 1 到 2592000 之间")
            payload["expire_seconds"] = expire_seconds
        return await self._api_request("POST", "/qrcode/create", payload=payload)

    async def get_jsapi_ticket(self) -> dict[str, Any]:
        return await self._api_request(
            "GET",
            "/ticket/getticket",
            params={"type": "jsapi"},
            read_only=True,
        )

    async def get_autoreply_config(self) -> dict[str, Any]:
        return await self._api_request(
            "GET", "/get_current_autoreply_info", read_only=True
        )

    async def get_server_ips(self) -> dict[str, Any]:
        return await self._api_request("GET", "/getcallbackip", read_only=True)
