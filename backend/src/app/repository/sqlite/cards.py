import json
from dataclasses import asdict

import aiosqlite

from app.domain.card_text import SellerParam
from app.usecase.review_card import ReviewCard
from app.usecase.stand_ports import CardInput


class SqliteCards:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._db = connection

    async def save(self, key: str, card: ReviewCard) -> None:
        await self._db.execute(
            "INSERT INTO review_cards(card_key,payload) VALUES(?,?) "
            "ON CONFLICT(card_key) DO UPDATE SET payload=excluded.payload",
            (key, json.dumps(asdict(card), ensure_ascii=False, separators=(",", ":"))),
        )

    async def get(self, key: str) -> ReviewCard | None:
        async with self._db.execute(
            "SELECT payload FROM review_cards WHERE card_key=?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        data = json.loads(row[0])
        card = data["input"]
        card["seller_params"] = tuple(SellerParam(**p) for p in card["seller_params"])
        return ReviewCard(CardInput(**card), data["engine"])
