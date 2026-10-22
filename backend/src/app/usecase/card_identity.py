import hashlib
import json

from app.usecase.stand_ports import CardInput


def card_key(card: CardInput) -> str:
    raw = json.dumps(
        [
            card.title,
            card.description,
            card.category_id,
            [(p.name, p.value, p.unit) for p in card.seller_params],
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
