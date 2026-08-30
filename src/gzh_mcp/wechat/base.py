"""微信 API 传输、token 缓存与错误协议。"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from ..errors import (
    UncertainStateError,
    WechatAPIError,
    WechatHTTPError,
    WechatResponseError,
    WechatTransportError,
)
from ..validation import validate_download_path


API_ORIGIN = "https://api.weixin.qq.com"
BASE_URL = f"{API_ORIGIN}/cgi-bin"
TOKEN_REFRESH_CODES = {40014, 42001}
TOKEN_EARLY_REFRESH_SECONDS = 300


class BaseWechatClient:
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

    @staticmethod
    def _endpoint_url(endpoint: str) -> str:
        if endpoint.startswith("/datacube/"):
            return f"{API_ORIGIN}{endpoint}"
        return f"{BASE_URL}{endpoint}"

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

    async def _api_download(
        self,
        method: str,
        endpoint: str,
        save_path: str | Path,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target = validate_download_path(save_path)
        token = await self.get_access_token()
        try:
            result = await self._request_binary_with_token(
                method, endpoint, token, payload=payload, params=params
            )
        except WechatAPIError as exc:
            if exc.errcode not in TOKEN_REFRESH_CODES:
                raise
            token = await self.get_access_token(force_refresh=True)
            result = await self._request_binary_with_token(
                method, endpoint, token, payload=payload, params=params
            )
        if isinstance(result, dict):
            return result
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("xb") as output_file:
                output_file.write(result)
        except FileExistsError as exc:
            raise ValueError(f"目标文件已存在，拒绝覆盖: {target}") from exc
        return {"file_path": str(target), "size": len(result)}

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

    async def _request_binary_with_token(
        self,
        method: str,
        endpoint: str,
        token: str,
        *,
        payload: dict[str, Any] | None,
        params: dict[str, Any] | None,
    ) -> dict[str, Any] | bytes:
        query = {**(params or {}), "access_token": token}
        secrets = self._secrets(token)
        for attempt in range(2):
            try:
                response = await self._http.request(
                    method,
                    self._endpoint_url(endpoint),
                    params=query,
                    content=(
                        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                        if payload is not None
                        else None
                    ),
                    headers=(
                        {"Content-Type": "application/json; charset=utf-8"}
                        if payload is not None
                        else None
                    ),
                )
            except httpx.TransportError as exc:
                if attempt == 0:
                    await asyncio.sleep(0.05)
                    continue
                raise WechatTransportError(endpoint, exc, secrets) from exc
            if response.status_code != 200:
                if response.status_code >= 500 and attempt == 0:
                    await asyncio.sleep(0.05)
                    continue
                raise WechatHTTPError(endpoint, response.status_code, response.text, secrets)
            if "json" not in response.headers.get("Content-Type", "").lower():
                return response.content
            data = self._parse_json_response(endpoint, response, secrets)
            if data.get("errcode") == -1 and attempt == 0:
                await asyncio.sleep(0.05)
                continue
            self._raise_api_error(endpoint, data, secrets)
            return data
        raise AssertionError("二进制请求重试循环未返回")

    @staticmethod
    def _parse_json_response(
        endpoint: str, response: httpx.Response, secrets: tuple[str, ...]
    ) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise WechatResponseError(endpoint, "响应不是 JSON", secrets) from exc
        if not isinstance(data, dict):
            raise WechatResponseError(endpoint, "JSON 顶层不是对象", secrets)
        return data

    @staticmethod
    def _raise_api_error(
        endpoint: str, data: dict[str, Any], secrets: tuple[str, ...]
    ) -> None:
        errcode = data.get("errcode", 0)
        if errcode in (0, None):
            return
        try:
            numeric_errcode = int(errcode)
        except (TypeError, ValueError):
            raise WechatResponseError(endpoint, "errcode 不是整数", secrets) from None
        raise WechatAPIError(endpoint, numeric_errcode, data.get("errmsg", ""), secrets)

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
                request_kwargs["headers"] = {
                    "Content-Type": "application/json; charset=utf-8"
                }
            try:
                response = await self._http.request(
                    method, self._endpoint_url(endpoint), **request_kwargs
                )
            except httpx.TransportError as exc:
                if attempt + 1 < attempts:
                    await asyncio.sleep(0.05)
                    continue
                error_type = (
                    UncertainStateError
                    if uncertain_on_transport
                    else WechatTransportError
                )
                raise error_type(endpoint, exc, secrets) from exc

            if response.status_code != 200:
                if retry_read and response.status_code >= 500 and attempt + 1 < attempts:
                    await asyncio.sleep(0.05)
                    continue
                raise WechatHTTPError(
                    endpoint, response.status_code, response.text, secrets
                )
            data = self._parse_json_response(endpoint, response, secrets)
            if retry_read and data.get("errcode") in (-1, "-1") and attempt + 1 < attempts:
                await asyncio.sleep(0.05)
                continue
            self._raise_api_error(endpoint, data, secrets)
            return data
        raise AssertionError("请求重试循环未返回")
