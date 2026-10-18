"""Dev only (mounted when APP_ENV=dev): signed initData for the Mini App's browser mock, so
the real auth path runs locally (ID-01 spec, Q5). Signed with the dev bot token."""

import json
import time
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from tristhana.api import initdata


class DevInitData(BaseModel):
    init_data: str


def make_dev_router(bot_token: str) -> APIRouter:
    router = APIRouter(prefix="/dev", include_in_schema=False)

    @router.get("/telegram-init-data")
    async def telegram_init_data(  # pyright: ignore[reportUnusedFunction]
        lang: Annotated[str, Query(max_length=16)] = "en",
        first_name: Annotated[str, Query(max_length=64)] = "Dev",
        user_id: Annotated[int, Query(ge=1)] = 1,
    ) -> DevInitData:
        user = {"id": user_id, "first_name": first_name, "language_code": lang}
        fields = {"user": json.dumps(user, ensure_ascii=False), "auth_date": str(int(time.time()))}
        return DevInitData(init_data=initdata.sign(fields, bot_token))

    return router
