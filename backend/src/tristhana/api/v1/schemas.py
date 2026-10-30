"""Schemas shared by several routers."""

from pydantic import BaseModel

from tristhana.domain.moon import City


class CityOut(BaseModel):
    slug: str
    name_en: str
    name_ru: str
    timezone: str

    @classmethod
    def of(cls, city: City) -> "CityOut":
        return cls(
            slug=city.slug, name_en=city.name_en, name_ru=city.name_ru, timezone=city.location.tz
        )
