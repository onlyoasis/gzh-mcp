"""数据统计接口。"""

from __future__ import annotations

from typing import Any

from ..validation import validate_datacube_request


class DatacubeMixin:
    async def get_statistics_report(
        self, report: str, begin_date: str, end_date: str
    ) -> dict[str, Any]:
        validate_datacube_request(report, begin_date, end_date)
        return await self._api_request(
            "POST",
            f"/datacube/{report}",
            payload={"begin_date": begin_date, "end_date": end_date},
            read_only=True,
        )
