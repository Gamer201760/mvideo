from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.errors import ModelFailure
from app.domain.inference import StructuredRequest, Tier, Usage
from app.domain.page_text import find_quote
from app.domain.text_reading import guess_title
from app.usecase.interface import LanguageModel

TITLE_LLM = "llm"
TITLE_RULE = "rule"
PROMPT_CHARS = 3000
SYSTEM = (
    "Ты читаешь текст карточки товара интернет-магазина. Найди в тексте название этого товара "
    "так, как его написал продавец: обычно это заголовок или первая строка, с типом товара, "
    "брендом, моделью и тем, что продавец включил в название. Скопируй его из текста дословно, "
    "одним непрерывным фрагментом, ничего не исправляй, не сокращай и не дополняй. Не бери "
    "названия других товаров со страницы. Если названия в тексте нет — верни пустую строку."
)
SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"title": {"type": "string"}},
    "required": ["title"],
    "additionalProperties": False,
}


@dataclass(frozen=True, slots=True)
class TitleRead:
    start: int
    end: int
    source: str
    confidence: float
    usage: Usage | None


class TitleReader:
    def __init__(self, language: LanguageModel | None) -> None:
        self._language = language

    async def read(self, text: str, references: Sequence[str]) -> TitleRead | None:
        usage = None
        if self._language is not None:
            span, usage = await self._ask(text, references)
            if span is not None:
                return TitleRead(span[0], span[1], TITLE_LLM, 1.0, usage)
        guess = guess_title(text, references)
        if guess is None:
            return None
        return TitleRead(guess.start, guess.end, TITLE_RULE, guess.score, usage)

    async def _ask(self, text: str, references: Sequence[str]
                   ) -> tuple[tuple[int, int] | None, Usage | None]:
        examples = "\n".join(f"- {r}" for r in references)
        prompt = (f"Названия похожих товаров из каталога (только для образца формы):\n{examples}"
                  f"\n\nТекст карточки:\n{text[:PROMPT_CHARS]}")
        request = StructuredRequest(system=SYSTEM, prompt=prompt, schema=SCHEMA, tier=Tier.FAST)
        try:
            completion = await self._language.complete(request) if self._language else None
        except ModelFailure:
            return None, None
        if completion is None:
            return None, None
        title = completion.output.get("title")
        span = find_quote(text, title) if isinstance(title, str) else None
        return span, completion.usage
