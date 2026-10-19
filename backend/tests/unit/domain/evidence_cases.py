from app.domain.attribute_evidence import parse_batch
from app.domain.attribute_flow import CatalogCandidate, CatalogField, Extraction, FlowCard


def extract(
    text: str,
    attribute: str,
    kind: str,
    value: str,
    unit: str,
    quote: str,
    *,
    extra: bool = False,
    flags: int = 0,
    schema_unit: str = "",
) -> tuple[FlowCard, Extraction]:
    field = CatalogField(attribute, kind, schema_unit)
    card = FlowCard(1, text, (CatalogCandidate(7, "Товары", 0.99, (field,)),))
    raw = {
        "c": [
            {
                "i": 0,
                "k": 0,
                "a": [
                    {
                        "f": attribute + " товара" if extra else 0,
                        "v": value,
                        "u": unit,
                        "q": quote,
                        "r": flags,
                    }
                ],
                "r": [],
            }
        ]
    }
    return card, parse_batch(raw, (card,))[0]
