"""已发表文章评论接口。"""

from __future__ import annotations

from typing import Any

from ..validation import ValidationError


class CommentMixin:
    async def list_comments(
        self,
        msg_data_id: int,
        index: int,
        begin: int = 0,
        count: int = 50,
        comment_type: int = 0,
    ) -> dict[str, Any]:
        if index < 0 or begin < 0:
            raise ValidationError("index 和 begin 不能小于 0")
        if count < 1 or count > 50:
            raise ValidationError("count 必须在 1 到 50 之间")
        if comment_type not in {0, 1}:
            raise ValidationError("comment_type 只能是 0 或 1")
        return await self._api_request(
            "POST",
            "/comment/list",
            payload={
                "msg_data_id": msg_data_id,
                "index": index,
                "begin": begin,
                "count": count,
                "type": comment_type,
            },
            read_only=True,
        )

    async def mark_comment_elect(
        self, msg_data_id: int, index: int, user_comment_id: int
    ) -> dict[str, Any]:
        return await self._api_request(
            "POST",
            "/comment/markelect",
            payload={
                "msg_data_id": msg_data_id,
                "index": index,
                "user_comment_id": user_comment_id,
            },
        )

    async def unmark_comment_elect(
        self, msg_data_id: int, index: int, user_comment_id: int
    ) -> dict[str, Any]:
        return await self._api_request(
            "POST",
            "/comment/unmarkelect",
            payload={
                "msg_data_id": msg_data_id,
                "index": index,
                "user_comment_id": user_comment_id,
            },
        )
