import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx

from app.domain.inference import Completion, StructuredRequest, Usage
from app.main import create_app
from app.settings import Settings
from app.usecase.interface import LanguageModel


@asynccontextmanager
async def client_for(
    database: Path, model: LanguageModel | None = None, *, settings: Settings | None = None
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings or Settings(database=database), model=model)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield client


class ColorModel:
    def __init__(self) -> None:
        self.quote = "Цвет: синий"
        self.abstain = False

    async def complete(self, request: StructuredRequest) -> Completion:
        data = json.loads(request.prompt)
        answers: list[dict[str, Any]] = (
            []
            if self.abstain
            else [
                {
                    "f": data["f"].index("Цвет"),
                    "v": "синий",
                    "u": "",
                    "q": self.quote,
                    "r": 0,
                }
            ]
        )
        return Completion({"c": [{"i": 0, "k": 0, "r": [], "a": answers}]}, Usage("test-port"))


class NewCategoryModel:
    async def complete(self, request: StructuredRequest) -> Completion:
        return Completion(
            {
                "c": [
                    {
                        "i": 0,
                        "k": "Техника / Беспилотники",
                        "r": [],
                        "a": [
                            {
                                "f": "Дальность полета",
                                "v": "12",
                                "u": "км",
                                "q": "Дальность полета: 12 км",
                                "r": 0,
                            }
                        ],
                    }
                ]
            },
            Usage("test-port"),
        )
