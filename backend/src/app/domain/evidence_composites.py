import re
from dataclasses import replace

from app.domain.attribute_flow import CatalogField, FieldAnswer
from app.domain.card_text import match_form


def components(value: str) -> tuple[str, ...]:
    return tuple(match_form(part).strip() for part in value.split(",") if part.strip())


def flag_evidence(
    answer: FieldAnswer, field: CatalogField | None
) -> tuple[tuple[FieldAnswer, CatalogField], ...]:
    parts = components(answer.value)
    if (
        not field
        or field.kind != "categorical"
        or field.unit
        or answer.unit
        or len(parts) < 2
        or len(set(parts)) != len(parts)
    ):
        return ()
    vocabulary = {part for value in field.values for part in components(value)}
    if not set(parts) <= vocabulary:
        return ()
    result = []
    for part in parts:
        found = next(
            (
                line
                for line in re.finditer(r"[^\n]+", answer.quote)
                if match_form(line[0].partition(":")[0]).strip() == part
                and match_form(line[0].partition(":")[2]).strip() in {"да", "yes", "true"}
            ),
            None,
        )
        if found is None:
            return ()
        start = answer.start + found.start()
        result.append(
            (
                replace(
                    answer,
                    attribute=part,
                    value="Да",
                    unit="",
                    quote=found[0],
                    start=start,
                    end=start + len(found[0]),
                ),
                CatalogField(part, "boolean", ""),
            )
        )
    return tuple(result)
