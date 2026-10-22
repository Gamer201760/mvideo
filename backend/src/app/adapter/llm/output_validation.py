from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError
from jsonschema.validators import validator_for
from referencing import Registry
from referencing.exceptions import Unresolvable

from app.domain.errors import InvalidModelOutput
from app.domain.inference import JsonSchema


def validate_output(output: dict[str, Any], schema: JsonSchema) -> None:
    try:
        validator = validator_for(schema, default=Draft202012Validator)
        validator.check_schema(schema)
        validator(schema, registry=Registry(), format_checker=FormatChecker()).validate(output)
    except (SchemaError, ValidationError, Unresolvable, TypeError, ValueError, RecursionError):
        raise InvalidModelOutput() from None
