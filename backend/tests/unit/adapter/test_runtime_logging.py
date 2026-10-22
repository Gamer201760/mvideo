import json
import subprocess
import sys
from pathlib import Path


def test_container_logging_emits_application_info_without_enabling_http_client_logs() -> None:
    root = Path(__file__).resolve().parents[3]
    dockerfile = (root / "Dockerfile").read_text()
    command = json.loads(
        next(line[4:] for line in dockerfile.splitlines() if line.startswith("CMD "))
    )
    filename = command[command.index("--log-config") + 1]
    assert f"COPY {filename} ./" in dockerfile
    program = """
import logging
from uvicorn import Config
from app.adapter.log.stdlib import StdlibLogger
Config('app.main:create_app', factory=True, log_config='logging.json')
assert logging.getLogger('attributes').isEnabledFor(logging.INFO)
assert not logging.getLogger('httpx').isEnabledFor(logging.INFO)
StdlibLogger('attributes').info('gateway_response', request_id='test', attempt=1, status=200)
"""
    result = subprocess.run(
        [sys.executable, "-c", program], cwd=root, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "gateway_response" in result.stderr
    assert "attempt=1" in result.stderr and "status=200" in result.stderr
