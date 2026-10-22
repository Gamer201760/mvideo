import unicodedata
from functools import lru_cache


@lru_cache(maxsize=4096)
def match_character(character: str) -> str:
    if unicodedata.category(character) == "Zs":
        return " "
    if "\uff01" <= character <= "\uff5e":
        character = unicodedata.normalize("NFKC", character)
    decimal = unicodedata.decimal(character, None)
    if decimal is not None:
        return str(decimal)
    lowered = character.lower()
    return lowered.replace("ё", "е") if len(lowered) == 1 else character


@lru_cache(maxsize=8192)
def matching_text(text: str) -> str:
    return "".join(match_character(character) for character in text)
