from typing import cast

from fastapi import Request

from tristhana.settings import Settings


def app_settings(request: Request) -> Settings:
    """The Settings the app was created with (see `tristhana.main.create_app`)."""
    return cast(Settings, request.app.state.settings)
