"""自定义菜单接口。"""

from __future__ import annotations

from typing import Any

from ..validation import ValidationError, validate_menu_buttons


MATCH_RULE_FIELDS = {
    "tag_id",
    "sex",
    "country",
    "province",
    "city",
    "client_platform_type",
    "language",
}


class MenuMixin:
    async def create_menu(self, buttons: list[dict[str, Any]]) -> dict[str, Any]:
        validate_menu_buttons(buttons)
        return await self._api_request(
            "POST", "/menu/create", payload={"button": buttons}
        )

    async def get_current_menu(self) -> dict[str, Any]:
        return await self._api_request("GET", "/menu/get", read_only=True)

    async def delete_menu(self) -> dict[str, Any]:
        return await self._api_request("GET", "/menu/delete")

    async def create_conditional_menu(
        self, buttons: list[dict[str, Any]], match_rule: dict[str, Any]
    ) -> dict[str, Any]:
        validate_menu_buttons(buttons)
        unknown = set(match_rule) - MATCH_RULE_FIELDS
        if unknown:
            raise ValidationError(f"match_rule 含未知字段: {', '.join(sorted(unknown))}")
        return await self._api_request(
            "POST",
            "/menu/addconditional",
            payload={"button": buttons, "matchrule": match_rule},
        )

    async def delete_conditional_menu(self, menu_id: str | int) -> dict[str, Any]:
        # menu/addconditional 实际返回整型 menuid（2026-08-30 真实账号实测），
        # 与 publish_id 同理：接受整型并归一化为字符串。
        if isinstance(menu_id, bool) or not isinstance(menu_id, (str, int)):
            raise ValidationError("menu_id 必须是字符串或整数")
        normalized = str(menu_id).strip()
        if not normalized:
            raise ValidationError("menu_id 不能为空")
        return await self._api_request(
            "POST", "/menu/delconditional", payload={"menuid": normalized}
        )

    async def try_match_conditional_menu(self, user_id: str) -> dict[str, Any]:
        return await self._api_request(
            "POST",
            "/menu/trymatch",
            payload={"user_id": user_id},
            read_only=True,
        )
