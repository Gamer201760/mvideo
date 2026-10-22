import hashlib
import json
import shutil
import subprocess
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/predict_dataset.py"


@pytest.fixture
def api_server() -> Iterator[tuple[str, list[dict[str, object]]]]:
    requests: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))
            requests.append(payload)
            assert self.path == "/api/v1/extract"
            title = payload["title"]
            status = 503 if title == "failure" else 200
            values: list[dict[str, object]] = [
                {
                    "attribute": "Title",
                    "value": title,
                    "evidence": title,
                    "start": 0,
                    "end": len(title),
                    "confidence": 0.5,
                    "source": "key_value",
                    "sources": ["key_value"],
                    "status": "review",
                    "review_id": None,
                    "acceptance": "review",
                    "risk": None,
                }
            ]
            result: dict[str, object] = {
                "engine": payload["engine"],
                "text": title,
                "category": None,
                "threshold": None,
                "auto_accept_enabled": False,
                "extra_values": [],
                "missing": [],
                "rejections": [],
                "values": values,
            }
            if title == "ungrounded":
                values[0]["evidence"] = "fabricated"
            if title == "failure":
                result = {"code": "storage_busy", "message": "storage unavailable"}
            body = b"{" if title == "malformed" else json.dumps(result).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def write_input(path: Path, titles: list[str]) -> Path:
    path.write_text(
        "".join(
            json.dumps(
                {
                    "id": f"card-{index}",
                    "title": title,
                    "description": "",
                    "category_id": 761,
                    "seller_params": [],
                }
            )
            + "\n"
            for index, title in enumerate(titles)
        ),
        encoding="utf-8",
    )
    return path


def execute(
    source: Path, output: Path, base_url: str, *extra: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input",
            str(source),
            "--output",
            str(output),
            "--base-url",
            base_url,
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_preserves_ids_grounded_results_and_hashes(
    tmp_path: Path, api_server: tuple[str, list[dict[str, object]]]
) -> None:
    url, requests = api_server
    source = write_input(tmp_path / "cards.jsonl", ["First", "Second"])
    output = tmp_path / "predictions.jsonl"
    result = execute(source, output, url)
    assert result.returncode == 0, result.stderr
    predictions = [json.loads(line) for line in output.read_text().splitlines()]
    assert [row["id"] for row in predictions] == ["card-0", "card-1"]
    assert all(row["status"] == "ok" for row in predictions)
    assert predictions[1]["result"]["values"][0]["evidence"] == "Second"
    assert all(request["engine"] == "rules" and "id" not in request for request in requests)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["counts"] == {"processed": 2, "ok": 2, "error": 0}
    assert manifest["input"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert manifest["output"]["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert manifest["records"][1] == {"id": "card-1", "status": "ok", "line": 2}
    assert manifest["status"] == "completed"


def test_partial_failures_are_explicit_and_do_not_drop_following_cards(
    tmp_path: Path, api_server: tuple[str, list[dict[str, object]]]
) -> None:
    url, requests = api_server
    source = write_input(
        tmp_path / "cards.jsonl", ["First", "failure", "malformed", "ungrounded", "Last"]
    )
    output = tmp_path / "predictions.jsonl"
    result = execute(source, output, url)
    assert result.returncode == 1, result.stderr
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(rows) == len(requests) == 5
    assert rows[1]["error"] == {"code": "storage_busy", "http_status": 503}
    assert rows[2]["error"]["code"] == rows[3]["error"]["code"] == "invalid_response"
    assert rows[4]["id"] == "card-4" and rows[4]["status"] == "ok"
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["counts"] == {"processed": 5, "ok": 2, "error": 3}


@pytest.mark.parametrize(
    "contents",
    [
        "not JSON\n",
        "\n",
        '{"id":true,"title":"Card"}\n',
        '{"id":1,"title":"Card","gold":[]}\n',
        '{"id":1,"title":"Card","seller_params":[{"name":"color_search","value":"red"}]}\n',
        '{"id":1,"title":"Card"}\n{"id":"1","title":"Second"}\n',
    ],
)
def test_invalid_or_duplicate_inputs_fail_before_http_or_output(
    tmp_path: Path, api_server: tuple[str, list[dict[str, object]]], contents: str
) -> None:
    url, requests = api_server
    source = tmp_path / "cards.jsonl"
    source.write_text(contents)
    output = tmp_path / "predictions.jsonl"
    assert execute(source, output, url).returncode == 2
    assert not requests
    assert not output.exists()
    assert not (tmp_path / "manifest.json").exists()


def test_cli_refuses_overwrite_and_preserves_existing_files(
    tmp_path: Path, api_server: tuple[str, list[dict[str, object]]]
) -> None:
    url, requests = api_server
    source = write_input(tmp_path / "cards.jsonl", ["First"])
    output = tmp_path / "predictions.jsonl"
    assert execute(source, output, url).returncode == 0
    original = output.read_bytes()
    manifest = (tmp_path / "manifest.json").read_bytes()
    assert execute(source, output, url).returncode == 2
    assert output.read_bytes() == original
    assert (tmp_path / "manifest.json").read_bytes() == manifest
    assert len(requests) == 1


def test_stale_checkpoint_is_preserved_and_prevents_requests(
    tmp_path: Path, api_server: tuple[str, list[dict[str, object]]]
) -> None:
    url, requests = api_server
    source = write_input(tmp_path / "cards.jsonl", ["First"])
    checkpoint = tmp_path / "manifest.json.tmp"
    checkpoint.write_text("partial checkpoint")
    output = tmp_path / "predictions.jsonl"
    assert execute(source, output, url).returncode == 2
    assert checkpoint.read_text() == "partial checkpoint"
    assert not output.exists() and not requests


def test_cli_is_portable_with_only_scripts_and_checked_in_inputs(tmp_path: Path) -> None:
    standalone = tmp_path / "standalone"
    shutil.copytree(
        ROOT / "scripts", standalone / "scripts", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copytree(ROOT / "examples/validation", standalone / "examples/validation")
    result = subprocess.run(
        [
            sys.executable,
            str(standalone / "scripts/predict_dataset.py"),
            "--help",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=standalone,
    )
    assert result.returncode == 0
    assert "--base-url" in result.stdout
