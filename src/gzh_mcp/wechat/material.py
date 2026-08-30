"""永久素材与临时素材接口。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..errors import WechatResponseError
from ..validation import (
    ValidationError,
    validate_content_image,
    validate_cover_image,
    validate_permanent_media,
    validate_temp_media,
)


MATERIAL_TYPES = {"image", "voice", "video", "news"}


class MaterialMixin:
    async def upload_content_image(self, file_path: str | Path) -> dict[str, Any]:
        image = validate_content_image(file_path)
        data = await self._api_request(
            "POST",
            "/media/uploadimg",
            files={"media": (image.path.name, image.path.read_bytes(), image.mime_type)},
        )
        if not isinstance(data.get("url"), str):
            raise WechatResponseError("/media/uploadimg", "缺少 url", self._secrets())
        return data

    async def upload_cover_image(self, file_path: str | Path) -> dict[str, Any]:
        image = validate_cover_image(file_path)
        data = await self._api_request(
            "POST",
            "/material/add_material",
            params={"type": "image"},
            files={"media": (image.path.name, image.path.read_bytes(), image.mime_type)},
        )
        self._require_media_id("/material/add_material", data)
        return data

    async def upload_video_material(
        self, file_path: str | Path, title: str, introduction: str
    ) -> dict[str, Any]:
        if not title:
            raise ValidationError("title 不能为空")
        media = validate_permanent_media(file_path, "video")
        description = json.dumps(
            {"title": title, "introduction": introduction},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        data = await self._api_request(
            "POST",
            "/material/add_material",
            params={"type": "video"},
            files={
                "media": (media.path.name, media.path.read_bytes(), media.mime_type),
                "description": (None, description, "application/json; charset=utf-8"),
            },
        )
        self._require_media_id("/material/add_material", data)
        return data

    async def upload_voice_material(self, file_path: str | Path) -> dict[str, Any]:
        media = validate_permanent_media(file_path, "voice")
        data = await self._api_request(
            "POST",
            "/material/add_material",
            params={"type": "voice"},
            files={"media": (media.path.name, media.path.read_bytes(), media.mime_type)},
        )
        self._require_media_id("/material/add_material", data)
        return data

    async def get_material(
        self, media_id: str, save_path: str | Path
    ) -> dict[str, Any]:
        return await self._api_download(
            "POST",
            "/material/get_material",
            save_path,
            payload={"media_id": media_id},
        )

    async def delete_material(self, media_id: str) -> dict[str, Any]:
        return await self._api_request(
            "POST", "/material/del_material", payload={"media_id": media_id}
        )

    async def list_materials(
        self, material_type: str, offset: int = 0, count: int = 20
    ) -> dict[str, Any]:
        if material_type not in MATERIAL_TYPES:
            raise ValidationError(f"material_type 不受支持: {material_type}")
        self._validate_page(offset, count)
        return await self._api_request(
            "POST",
            "/material/batchget_material",
            payload={"type": material_type, "offset": offset, "count": count},
            read_only=True,
        )

    async def count_materials(self) -> dict[str, Any]:
        return await self._api_request(
            "GET", "/material/get_materialcount", read_only=True
        )

    async def upload_temp_media(
        self, file_path: str | Path, media_type: str
    ) -> dict[str, Any]:
        media = validate_temp_media(file_path, media_type)
        data = await self._api_request(
            "POST",
            "/media/upload",
            params={"type": media_type},
            files={"media": (media.path.name, media.path.read_bytes(), media.mime_type)},
        )
        self._require_media_id("/media/upload", data)
        return data

    async def download_temp_media(
        self, media_id: str, save_path: str | Path
    ) -> dict[str, Any]:
        return await self._api_download(
            "GET", "/media/get", save_path, params={"media_id": media_id}
        )

    def _require_media_id(self, endpoint: str, data: dict[str, Any]) -> None:
        if not isinstance(data.get("media_id"), str):
            raise WechatResponseError(endpoint, "缺少 media_id", self._secrets())
