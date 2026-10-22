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

    def __init__(self, message: str | None = None, *, attempts: int = 1) -> None:
        self.attempts = attempts
        super().__init__(message)


class ModelCapacity(ModelFailure):
    code = "model_capacity"
    message = "Extraction capacity is full; retry later"


class ModelTimeout(ModelFailure):
    code = "model_timeout"
    message = "Extraction timed out; retry later"


class ModelUnavailable(ModelFailure):
    code = "model_unavailable"
    message = "Model service is unavailable; retry later"


class ModelRateLimited(ModelFailure):
    code = "model_rate_limited"
    message = "Model service is overloaded; retry later"


class InvalidModelOutput(ModelFailure):
    code = "invalid_model_output"
    message = "Model response did not pass validation"


class ModelInputTooLarge(ModelFailure):
    code = "model_input_too_large"
    message = "Card and category schemas exceed the model request limit"


class EmbeddingsFailure(ModelFailure):
    code = "embeddings_failure"
    message = "Embeddings service unavailable"


class DecisionFailure(ModelFailure):
    code = "decision_failure"
    message = "Decision model failed"


class InvalidQuestion(DomainError):
    code = "invalid_question"
    message = "Decision question is invalid"


class RunNotFound(DomainError):
    code = "run_not_found"
    message = "Extraction run not found"


class StorageFailure(DomainError):
    code = "storage_failure"
    message = "Storage operation failed"


class StorageUnavailable(StorageFailure):
    code = "storage_unavailable"
    message = "Storage is unavailable; retry later"


class StorageBusy(StorageUnavailable):
    code = "storage_busy"
    message = "Storage is busy; retry later"
