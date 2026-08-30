"""群发、客服、模板与订阅消息接口。"""

from __future__ import annotations

from typing import Any

from ..validation import ValidationError, validate_message
from .user import _validate_openid_list


class MessageMixin:
    async def mass_send_by_tag(
        self, tag_id: int, message: dict[str, Any], clientmsgid: str
    ) -> dict[str, Any]:
        validate_message(message, kind="mass")
        self._validate_clientmsgid(clientmsgid)
        return await self._api_request(
            "POST",
            "/message/mass/sendall",
            payload={
                "filter": {"is_to_all": False, "tag_id": tag_id},
                **message,
                "clientmsgid": clientmsgid,
            },
            uncertain_on_transport=True,
        )

    async def mass_send_by_openids(
        self,
        openid_list: list[str],
        message: dict[str, Any],
        clientmsgid: str,
    ) -> dict[str, Any]:
        _validate_openid_list(openid_list, maximum=10_000)
        validate_message(message, kind="mass")
        self._validate_clientmsgid(clientmsgid)
        return await self._api_request(
            "POST",
            "/message/mass/send",
            payload={"touser": openid_list, **message, "clientmsgid": clientmsgid},
            uncertain_on_transport=True,
        )

    async def preview_mass_message(
        self,
        openid: str,
        message: dict[str, Any],
        wxname: str | None = None,
    ) -> dict[str, Any]:
        validate_message(message, kind="mass")
        recipient = {"towxname": wxname} if wxname else {"touser": openid}
        if not wxname and not openid:
            raise ValidationError("openid 和 wxname 至少提供一个")
        return await self._api_request(
            "POST",
            "/message/mass/preview",
            payload={**recipient, **message},
            uncertain_on_transport=True,
        )

    async def get_mass_status(self, msg_id: int) -> dict[str, Any]:
        return await self._api_request(
            "POST",
            "/message/mass/get",
            payload={"msg_id": msg_id},
            read_only=True,
        )

    async def delete_mass_message(
        self, msg_id: int, article_idx: int | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"msg_id": msg_id}
        if article_idx is not None:
            if article_idx < 0:
                raise ValidationError("article_idx 不能小于 0")
            payload["article_idx"] = article_idx
        return await self._api_request(
            "POST", "/message/mass/delete", payload=payload
        )

    async def send_custom_message(
        self, openid: str, message: dict[str, Any]
    ) -> dict[str, Any]:
        validate_message(message, kind="custom")
        return await self._api_request(
            "POST",
            "/message/custom/send",
            payload={**message, "touser": openid},
            uncertain_on_transport=True,
        )

    @staticmethod
    def _validate_clientmsgid(clientmsgid: str) -> None:
        if not clientmsgid:
            raise ValidationError("clientmsgid 不能为空")
        if len(clientmsgid.encode("utf-8")) > 64:
            raise ValidationError("clientmsgid 不能超过 64 字节")

    async def send_template_message(
        self,
        openid: str,
        template_id: str,
        data: dict[str, Any],
        url: str | None = None,
        miniprogram: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "touser": openid,
            "template_id": template_id,
            "data": data,
        }
        if url is not None:
            payload["url"] = url
        if miniprogram is not None:
            payload["miniprogram"] = miniprogram
        return await self._api_request(
            "POST",
            "/message/template/send",
            payload=payload,
            uncertain_on_transport=True,
        )

    async def send_subscribe_message(
        self,
        openid: str,
        template_id: str,
        data: dict[str, Any],
        page: str | None = None,
        miniprogram: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "touser": openid,
            "template_id": template_id,
            "data": data,
        }
        if page is not None:
            payload["page"] = page
        if miniprogram is not None:
            payload["miniprogram"] = miniprogram
        return await self._api_request(
            "POST",
            "/message/subscribe/bizsend",
            payload=payload,
            uncertain_on_transport=True,
        )
