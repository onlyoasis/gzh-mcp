"""用户、标签与黑名单接口。"""

from __future__ import annotations

from typing import Any

from ..validation import ValidationError


LANGUAGES = {"zh_CN", "zh_TW", "en"}


def _validate_openid_list(openid_list: list[str], *, maximum: int) -> None:
    if not openid_list:
        raise ValidationError("openid_list 不能为空")
    if len(openid_list) > maximum:
        raise ValidationError(f"openid_list 不能超过 {maximum} 个")
    if any(not isinstance(openid, str) or not openid for openid in openid_list):
        raise ValidationError("openid_list 必须只包含非空字符串")


class UserMixin:
    async def list_users(self, next_openid: str = "") -> dict[str, Any]:
        return await self._api_request(
            "GET",
            "/user/get",
            params={"next_openid": next_openid},
            read_only=True,
        )

    async def get_user_info(
        self, openid: str, lang: str = "zh_CN"
    ) -> dict[str, Any]:
        if lang not in LANGUAGES:
            raise ValidationError(f"lang 不受支持: {lang}")
        return await self._api_request(
            "GET",
            "/user/info",
            params={"openid": openid, "lang": lang},
            read_only=True,
        )

    async def batch_get_user_info(self, openid_list: list[str]) -> dict[str, Any]:
        _validate_openid_list(openid_list, maximum=100)
        return await self._api_request(
            "POST",
            "/user/info/batchget",
            payload={
                "user_list": [
                    {"openid": openid, "lang": "zh_CN"}
                    for openid in openid_list
                ]
            },
            read_only=True,
        )

    async def update_user_remark(self, openid: str, remark: str) -> dict[str, Any]:
        return await self._api_request(
            "POST",
            "/user/info/updateremark",
            payload={"openid": openid, "remark": remark},
        )

    async def create_tag(self, name: str) -> dict[str, Any]:
        if not name:
            raise ValidationError("标签名称不能为空")
        return await self._api_request(
            "POST", "/tags/create", payload={"tag": {"name": name}}
        )

    async def list_tags(self) -> dict[str, Any]:
        return await self._api_request("GET", "/tags/get", read_only=True)

    async def update_tag(self, tag_id: int, name: str) -> dict[str, Any]:
        if not name:
            raise ValidationError("标签名称不能为空")
        return await self._api_request(
            "POST", "/tags/update", payload={"tag": {"id": tag_id, "name": name}}
        )

    async def delete_tag(self, tag_id: int) -> dict[str, Any]:
        return await self._api_request(
            "POST", "/tags/delete", payload={"tag": {"id": tag_id}}
        )

    async def get_user_ids_by_tag(
        self, tag_id: int, next_openid: str = ""
    ) -> dict[str, Any]:
        return await self._api_request(
            "POST",
            "/user/tag/get",
            payload={"tagid": tag_id, "next_openid": next_openid},
            read_only=True,
        )

    async def tag_users(
        self, tag_id: int, openid_list: list[str]
    ) -> dict[str, Any]:
        _validate_openid_list(openid_list, maximum=50)
        return await self._api_request(
            "POST",
            "/tags/members/batchtagging",
            payload={"openid_list": openid_list, "tagid": tag_id},
        )

    async def untag_users(
        self, tag_id: int, openid_list: list[str]
    ) -> dict[str, Any]:
        _validate_openid_list(openid_list, maximum=50)
        return await self._api_request(
            "POST",
            "/tags/members/batchuntagging",
            payload={"openid_list": openid_list, "tagid": tag_id},
        )

    async def list_blacklist(self, next_openid: str = "") -> dict[str, Any]:
        return await self._api_request(
            "POST",
            "/tags/members/getblacklist",
            payload={"begin_openid": next_openid},
            read_only=True,
        )

    async def blacklist_users(self, openid_list: list[str]) -> dict[str, Any]:
        _validate_openid_list(openid_list, maximum=20)
        return await self._api_request(
            "POST",
            "/tags/members/batchblacklist",
            payload={"openid_list": openid_list},
        )

    async def unblacklist_users(self, openid_list: list[str]) -> dict[str, Any]:
        _validate_openid_list(openid_list, maximum=20)
        return await self._api_request(
            "POST",
            "/tags/members/batchunblacklist",
            payload={"openid_list": openid_list},
        )
