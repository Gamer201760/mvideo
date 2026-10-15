class DomainError(Exception):
    code = "domain_error"
    message = "Request failed"

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


class ModelFailure(DomainError):
    code = "model_failure"
    message = "Language model failed"


class EmbeddingsFailure(ModelFailure):
    code = "embeddings_failure"
    message = "Embeddings service unavailable"


class DecisionFailure(ModelFailure):
    code = "decision_failure"
    message = "Decision model failed"


class InvalidQuestion(DomainError):
    code = "invalid_question"
    message = "Decision question is invalid"
