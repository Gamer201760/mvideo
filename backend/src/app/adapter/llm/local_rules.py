import json

from app.domain.inference import Completion, StructuredRequest, Usage


class LocalRulesModel:
    async def complete(self, request: StructuredRequest) -> Completion:
        payload = json.loads(request.prompt)
        cards = [
            {"i": index, "k": card["k"][0] if card["k"] else None, "a": card.get("h", []), "r": []}
            for index, card in enumerate(payload["c"])
        ]
        return Completion({"c": cards}, Usage(model="local_rules", duration_ms=0))

    async def aclose(self) -> None:
        return None
