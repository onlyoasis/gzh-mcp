"""发表接口。"""

from __future__ import annotations

from typing import Any

from ..errors import WechatResponseError


class PublishMixin:
    async def get_publish_status(self, publish_id: str) -> dict[str, Any]:
        return await self._api_request(
            "POST",
            "/freepublish/get",
            payload={"publish_id": publish_id},
            read_only=True,
        )

    async def list_published(self, offset: int, count: int) -> dict[str, Any]:
        self._validate_page(offset, count)
        return await self._api_request(
            "POST",
            "/freepublish/batchget",
            payload={"offset": offset, "count": count, "no_content": 0},
            read_only=True,
        )

    async def publish_draft(self, media_id: str) -> dict[str, Any]:
        draft = await self.get_draft(media_id)
        news_items = draft.get("news_item")
        title = ""
        if isinstance(news_items, list) and news_items and isinstance(news_items[0], dict):
            candidate = news_items[0].get("title")
            if isinstance(candidate, str):
                title = candidate
        published = await self._api_request(
            "POST",
            "/freepublish/submit",
            payload={"media_id": media_id},
            uncertain_on_transport=True,
        )
        publish_id = published.get("publish_id")
        if (
            isinstance(publish_id, bool)
            or not isinstance(publish_id, (str, int))
            or not str(publish_id).strip()
        ):
            raise WechatResponseError(
                "/freepublish/submit",
                f"缺少 publish_id（实际返回字段: {sorted(published.keys())}）",
                self._secrets(),
            )
        return {
            **published,
            "publish_id": str(publish_id),
            "media_id": media_id,
            "title": title,
            "appid_prefix": self.appid_prefix,
        }

    async def get_published_article(self, article_id: str) -> dict[str, Any]:
        return await self._api_request(
            "POST",
            "/freepublish/getarticle",
            payload={"article_id": article_id},
            read_only=True,
        )

    async def delete_published_article(
        self, article_id: str, index: int | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"article_id": article_id}
        if index is not None:
            if index < 0:
                raise ValueError("index 不能小于 0")
            payload["index"] = index
        return await self._api_request("POST", "/freepublish/delete", payload=payload)
