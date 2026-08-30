"""草稿箱接口。"""

from __future__ import annotations

from typing import Any

from ..errors import WechatResponseError
from ..validation import inspect_article_html, validate_article, validate_articles


DRAFT_CONTENT_MIN_RATIO = 0.95


class DraftMixin:
    async def create_draft(self, articles: list[dict[str, Any]]) -> dict[str, Any]:
        expected = validate_articles(articles)
        created = await self._api_request(
            "POST",
            "/draft/add",
            payload={"articles": articles},
            uncertain_on_transport=True,
        )
        media_id = created.get("media_id")
        if not isinstance(media_id, str) or not media_id:
            raise WechatResponseError("/draft/add", "缺少 media_id", self._secrets())

        readback = await self.get_draft(media_id)
        actual_articles = readback.get("news_item")
        verification_errors: list[str] = []
        if not isinstance(actual_articles, list):
            verification_errors.append("回读响应缺少 news_item 数组")
            actual_articles = []
        if len(actual_articles) != len(articles):
            verification_errors.append(
                f"文章数量不一致 expected={len(articles)} actual={len(actual_articles)}"
            )

        for index, (source, actual, source_validation) in enumerate(
            zip(articles, actual_articles, expected, strict=False)
        ):
            if not isinstance(actual, dict):
                verification_errors.append(f"第 {index} 篇回读结构不是对象")
                continue
            if actual.get("title") != source["title"]:
                verification_errors.append(f"第 {index} 篇标题不一致")
            actual_content = actual.get("content")
            if not isinstance(actual_content, str):
                verification_errors.append(f"第 {index} 篇回读正文缺失")
                continue
            try:
                actual_images = inspect_article_html(actual_content).image_count
            except ValueError as exc:
                verification_errors.append(f"第 {index} 篇回读正文无效: {exc}")
                actual_images = -1
            if actual_images != source_validation.image_count:
                verification_errors.append(
                    f"第 {index} 篇图片数量不一致 "
                    f"expected={source_validation.image_count} actual={actual_images}"
                )
            source_content = str(source["content"])
            if len(actual_content) < len(source_content) * DRAFT_CONTENT_MIN_RATIO:
                verification_errors.append(f"第 {index} 篇正文长度缩水超过 5%")

        if verification_errors:
            return {
                "media_id": media_id,
                "verified": False,
                "verification_errors": verification_errors,
            }
        return {"media_id": media_id, "verified": True}

    async def get_draft(self, media_id: str) -> dict[str, Any]:
        return await self._api_request(
            "POST", "/draft/get", payload={"media_id": media_id}, read_only=True
        )

    async def update_draft(
        self, media_id: str, index: int, article: dict[str, Any]
    ) -> dict[str, Any]:
        if index < 0:
            raise ValueError("index 不能小于 0")
        validate_article(article)
        return await self._api_request(
            "POST",
            "/draft/update",
            payload={"media_id": media_id, "index": index, "articles": article},
        )

    async def list_drafts(self, offset: int, count: int) -> dict[str, Any]:
        self._validate_page(offset, count)
        count_result = await self._api_request("GET", "/draft/count", read_only=True)
        batch = await self._api_request(
            "POST",
            "/draft/batchget",
            payload={"offset": offset, "count": count, "no_content": 0},
            read_only=True,
        )
        if "total_count" in count_result:
            batch["total_count"] = count_result["total_count"]
        return batch

    async def delete_draft(self, media_id: str) -> dict[str, Any]:
        return await self._api_request(
            "POST", "/draft/delete", payload={"media_id": media_id}
        )
