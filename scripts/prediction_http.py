import http.client
import json
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        request: object,
        file: object,
        code: int,
        message: str,
        headers: object,
        url: str,
    ) -> None:
        return None


def endpoint(base_url: str) -> str:
    url = urllib.parse.urlsplit(base_url)
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username is not None
        or url.password is not None
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
    ):
        raise ValueError("base-url must be an HTTP origin without credentials, path or query")
    return base_url.rstrip("/") + "/api/v1/extract"


def supported_result(result: object, engine: str) -> bool:
    if not isinstance(result, dict) or result.get("engine") != engine:
        return False
    text, values, missing = (
        result.get("text"),
        result.get("values"),
        result.get("missing"),
    )
    if not isinstance(text, str) or not isinstance(values, list) or not isinstance(missing, list):
        return False
    if not all(isinstance(attribute, str) for attribute in missing):
        return False
    extra = result.get("extra_values", [])
    if not isinstance(extra, list):
        return False
    for value in [*values, *extra]:
        if not isinstance(value, dict):
            return False
        evidence, start, end = (
            value.get("evidence"),
            value.get("start"),
            value.get("end"),
        )
        if (
            not isinstance(value.get("attribute"), str)
            or not isinstance(value.get("value"), str)
            or not isinstance(evidence, str)
            or not evidence
            or type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(text)
            or text[start:end] != evidence
        ):
            return False
    return True


def predict(url: str, row: dict[str, object], engine: str, timeout: float) -> dict[str, object]:
    payload = {key: value for key, value in row.items() if key != "id"}
    request = urllib.request.Request(
        url,
        data=json.dumps({**payload, "engine": engine}, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            result = json.load(response)
        json.dumps(result, allow_nan=False)
        if not supported_result(result, engine):
            return {
                "id": row["id"],
                "status": "error",
                "error": {"code": "invalid_response"},
            }
        return {"id": row["id"], "status": "ok", "result": result}
    except urllib.error.HTTPError as error:
        try:
            body = json.load(error)
        except (ValueError, UnicodeError):
            body = {}
        code = body.get("code") if isinstance(body, dict) else None
        return {
            "id": row["id"],
            "status": "error",
            "error": {
                "code": code if isinstance(code, str) else "http_error",
                "http_status": error.code,
            },
        }
    except TimeoutError:
        return {
            "id": row["id"],
            "status": "error",
            "error": {"code": "request_timeout"},
        }
    except (urllib.error.URLError, OSError, http.client.HTTPException):
        return {
            "id": row["id"],
            "status": "error",
            "error": {"code": "connection_failure"},
        }
    except (ValueError, UnicodeError):
        return {
            "id": row["id"],
            "status": "error",
            "error": {"code": "invalid_response"},
        }
