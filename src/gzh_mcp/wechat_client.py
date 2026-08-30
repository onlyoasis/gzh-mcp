"""微信公众号 API 的异步客户端。"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from .errors import (
    UncertainStateError,
    WechatAPIError,
    WechatHTTPError,
    WechatResponseError,
    WechatTransportError,
)
from .validation import (
    inspect_article_html,
    validate_article,
    validate_articles,
    validate_content_image,
    validate_cover_image,
)


BASE_URL = "https://api.weixin.qq.com/cgi-bin"
TOKEN_REFRESH_CODES = {40014, 42001}
TOKEN_EARLY_REFRESH_SECONDS = 300
DRAFT_CONTENT_MIN_RATIO = 0.95


class WechatClient:
    def __init__(
        self,
        appid: str,
        secret: str,
        *,
        http_client: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not appid:
            raise ValueError("缺少 WECHAT_APPID")
        if not secret:
            raise ValueError("缺少 WECHAT_SECRET")
        self.appid = appid
        self._secret = secret
        self._http = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            trust_env=False,
        )
        self._clock = clock
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._http.aclose()

    @property
    def appid_prefix(self) -> str:
        return self.appid[:6]

    def _secrets(self, token: str | None = None) -> tuple[str, ...]:
        values = [self._secret]
        if token:
            values.append(token)
        if self._token:
            values.append(self._token)
        return tuple(values)

    async def get_access_token(self, *, force_refresh: bool = False) -> str:
        async with self._token_lock:
            if (
                not force_refresh
                and self._token
                and self._clock() < self._token_expires_at - TOKEN_EARLY_REFRESH_SECONDS
            ):
                return self._token

            payload: dict[str, object] = {
                "grant_type": "client_credential",
                "appid": self.appid,
                "secret": self._secret,
            }
            if force_refresh:
                payload["force_refresh"] = True
            data = await self._request_json(
                "POST",
                "/stable_token",
                payload=payload,
                secrets=self._secrets(),
            )
            token = data.get("access_token")
            expires_in = data.get("expires_in")
            if not isinstance(token, str) or not token:
                raise WechatResponseError(
                    "/stable_token", "缺少 access_token", self._secrets()
                )
            if not isinstance(expires_in, (int, float)) or expires_in <= 0:
                raise WechatResponseError(
                    "/stable_token", "expires_in 无效", self._secrets(token)
                )
            self._token = token
            self._token_expires_at = self._clock() + float(expires_in)
            return token

    async def check_credentials(self) -> dict[str, object]:
        await self.get_access_token()
        return {"ok": True, "appid_prefix": self.appid_prefix}

    async def upload_content_image(self, file_path: str | Path) -> dict[str, Any]:
        image = validate_content_image(file_path)
        data = await self._api_request(
            "POST",
            "/media/uploadimg",
            files={"media": (image.path.name, image.path.read_bytes(), image.mime_type)},
        )
        if not isinstance(data.get("url"), str):
            raise WechatResponseError(
                "/media/uploadimg", "缺少 url", self._secrets()
            )
        return data

    async def upload_cover_image(self, file_path: str | Path) -> dict[str, Any]:
        image = validate_cover_image(file_path)
        data = await self._api_request(
            "POST",
            "/material/add_material",
            params={"type": "image"},
            files={"media": (image.path.name, image.path.read_bytes(), image.mime_type)},
        )
        if not isinstance(data.get("media_id"), str):
            raise WechatResponseError(
                "/material/add_material", "缺少 media_id", self._secrets()
            )
        return data

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
            # 微信可能做轻微 HTML 归一化；只有长度缩水超过 5% 才视为异常。
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
        # 微信可能返回整型 publish_id（2026-08-30 真实账号实测）；统一转字符串。
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

    @staticmethod
    def _validate_page(offset: int, count: int) -> None:
        if offset < 0:
            raise ValueError("offset 不能小于 0")
        if count < 1 or count > 20:
            raise ValueError("count 必须在 1 到 20 之间")

    async def _api_request(
        self,
        method: str,
        endpoint: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        files: Any = None,
        read_only: bool = False,
        uncertain_on_transport: bool = False,
    ) -> dict[str, Any]:
        token = await self.get_access_token()
        try:
            return await self._request_with_token(
                method,
                endpoint,
                token,
                payload=payload,
                params=params,
                files=files,
                read_only=read_only,
                uncertain_on_transport=uncertain_on_transport,
            )
        except WechatAPIError as exc:
            if exc.errcode not in TOKEN_REFRESH_CODES:
                raise

        fresh_token = await self.get_access_token(force_refresh=True)
        return await self._request_with_token(
            method,
            endpoint,
            fresh_token,
            payload=payload,
            params=params,
            files=files,
            read_only=read_only,
            uncertain_on_transport=uncertain_on_transport,
        )

    async def _request_with_token(
        self,
        method: str,
        endpoint: str,
        token: str,
        *,
        payload: dict[str, Any] | None,
        params: dict[str, Any] | None,
        files: Any,
        read_only: bool,
        uncertain_on_transport: bool,
    ) -> dict[str, Any]:
        query = {**(params or {}), "access_token": token}
        return await self._request_json(
            method,
            endpoint,
            payload=payload,
            params=query,
            files=files,
            retry_read=read_only,
            uncertain_on_transport=uncertain_on_transport,
            secrets=self._secrets(token),
        )

    async def _request_json(
        self,
        method: str,
        endpoint: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        files: Any = None,
        retry_read: bool = False,
        uncertain_on_transport: bool = False,
        secrets: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        attempts = 2 if retry_read else 1
        for attempt in range(attempts):
            request_kwargs: dict[str, Any] = {"params": params}
            if files is not None:
                request_kwargs["files"] = files
            elif payload is not None:
                request_kwargs["content"] = json.dumps(
                    payload, ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8")
                request_kwargs["headers"] = {"Content-Type": "application/json; charset=utf-8"}
            try:
                response = await self._http.request(
                    method, f"{BASE_URL}{endpoint}", **request_kwargs
                )
            except httpx.TransportError as exc:
                if attempt + 1 < attempts:
                    await asyncio.sleep(0.05)
                    continue
                error_type = UncertainStateError if uncertain_on_transport else WechatTransportError
                raise error_type(endpoint, exc, secrets) from exc

            if response.status_code != 200:
                if retry_read and response.status_code >= 500 and attempt + 1 < attempts:
                    await asyncio.sleep(0.05)
                    continue
                raise WechatHTTPError(endpoint, response.status_code, response.text, secrets)
            try:
                data = response.json()
            except ValueError as exc:
                raise WechatResponseError(endpoint, "响应不是 JSON", secrets) from exc
            if not isinstance(data, dict):
                raise WechatResponseError(endpoint, "JSON 顶层不是对象", secrets)
            errcode = data.get("errcode", 0)
            if errcode not in (0, None):
                if retry_read and errcode == -1 and attempt + 1 < attempts:
                    await asyncio.sleep(0.05)
                    continue
                try:
                    numeric_errcode = int(errcode)
                except (TypeError, ValueError):
                    raise WechatResponseError(endpoint, "errcode 不是整数", secrets) from None
                raise WechatAPIError(endpoint, numeric_errcode, data.get("errmsg", ""), secrets)
            return data
        raise AssertionError("请求重试循环未返回")
