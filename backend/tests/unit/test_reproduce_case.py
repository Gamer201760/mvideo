import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[3] / "scripts/reproduce_case.sh"
KEYS = (
    "GATEWAY_API_KEY",
    "OPENAI_API_KEY",
    "GATEWAY_URL",
    "OPENAI_BASE_URL",
    "GATEWAY_MODEL",
    "OPENAI_MODEL",
)


def repository(root: Path) -> tuple[Path, dict[str, str]]:
    (root / "scripts").mkdir(parents=True)
    shutil.copy2(SOURCE, root / "scripts/reproduce_case.sh")
    binaries = root / "bin"
    binaries.mkdir()
    python = binaries / "python3"
    python.write_text(
        f"#!{sys.executable}\n"
        "import os,sys\nfrom pathlib import Path\n"
        f"real={sys.executable!r}\n"
        "if sys.argv[1]=='-': os.execv(real,[real,*sys.argv[1:]])\n"
        "assert sys.argv[1]=='scripts/restore_dataset.py'\n"
        "output=Path(sys.argv[sys.argv.index('--output')+1])\n"
        "output.mkdir(parents=True)\n(output/'opaque-source').write_bytes(b'preserved')\n"
    )
    docker = binaries / "docker"
    docker.write_text(
        f"#!{sys.executable}\n"
        "import json,os,sys\n"
        f"keys={KEYS!r}\n"
        "with open(os.environ['COMMAND_LOG'],'a') as stream:\n"
        " stream.write(json.dumps({'args':sys.argv[1:],'keys':{k:os.environ.get(k) for k in keys}})+'\\n')\n"
        "raise SystemExit(7 if os.environ.get('FAIL_MODULE','unused') in sys.argv else 0)\n"
    )
    python.chmod(0o755)
    docker.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{binaries}:{os.environ['PATH']}",
        "COMMAND_LOG": str(root / "commands.jsonl"),
    }
    env.update({name: "private-ambient-setting" for name in KEYS})
    return root, env


def execute(root: Path, env: dict[str, str], *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(root / "scripts/reproduce_case.sh"), *arguments],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "output",
    [
        "/tmp/outside",
        "data",
        "../data/run",
        "data/../escape",
        "./data/run",
        "data//run",
        "data/run/",
        "data/a b",
        "data/$HOME",
    ],
)
def test_bad_output_paths_fail_before_restoration_or_docker(tmp_path: Path, output: str) -> None:
    root, env = repository(tmp_path)
    result = execute(root, env, output)
    assert result.returncode != 0
    assert not (root / "data").exists()
    assert not (root / "commands.jsonl").exists()


@pytest.mark.parametrize("arguments", [[], ["data/a", "data/b"]])
def test_one_new_run_argument_is_required(tmp_path: Path, arguments: list[str]) -> None:
    root, env = repository(tmp_path)
    assert execute(root, env, *arguments).returncode == 2
    assert not (root / "data").exists()


@pytest.mark.parametrize(
    "kind", ["directory", "file", "staging", "broken-staging", "parent-symlink"]
)
def test_existing_outputs_and_symlinks_are_preserved(tmp_path: Path, kind: str) -> None:
    root, env = repository(tmp_path)
    output = root / "data/run"
    output.parent.mkdir()
    sentinel = root / "sentinel"
    sentinel.write_bytes(b"original")
    if kind == "directory":
        output.mkdir()
        (output / "existing").write_bytes(b"original")
    elif kind == "file":
        output.write_bytes(b"original")
    elif kind == "staging":
        output.with_name("run.building").mkdir()
    elif kind == "broken-staging":
        output.with_name("run.building").symlink_to(root / "missing")
    else:
        output.parent.rmdir()
        output.parent.symlink_to(root / "scripts", target_is_directory=True)
    assert execute(root, env, "data/run").returncode != 0
    assert sentinel.read_bytes() == b"original"
    assert not (root / "commands.jsonl").exists()


def test_pipeline_uses_isolated_outputs_all_rows_two_workers_and_no_provider_keys(
    tmp_path: Path,
) -> None:
    root, env = repository(tmp_path)
    result = execute(root, env, "data/new-run")
    assert result.returncode == 0, result.stderr
    records = [json.loads(line) for line in (root / "commands.jsonl").read_text().splitlines()]
    assert len(records) == 5
    assert records[0]["args"] == [
        "compose",
        "--env-file",
        "/dev/null",
        "--profile",
        "tools",
        "build",
        "backend",
    ]
    modules = ["app.prepare_data", "analysis.execute", "batch_predict", "batch_predict.verify"]
    for record, module in zip(records[1:], modules):
        args = record["args"]
        assert args[args.index("dataset") + 1 :][:3] == ["python", "-m", module]
        assert args[args.index("--user") + 1] == f"{os.getuid()}:{os.getgid()}"
        assert all(value == "" for value in record["keys"].values())
        assert "--limit" not in args
        assert "UV_PROJECT_ENVIRONMENT=/workspace/.local/data-env" in args
    prepare, eda, predict, verify = [record["args"] for record in records[1:]]
    assert prepare[prepare.index("--threads") + 1] == "2"
    assert predict[predict.index("--workers") + 1] == "2"
    assert predict[predict.index("--output") + 1] == "/workspace/data/new-run/predictions"
    assert verify[verify.index("--data") + 1] == "/workspace/data/new-run/processed"
    assert verify.count("--write-receipt") == 1
    for flag, suffix in (
        ("--notebook", "eda.ipynb"),
        ("--report", "eda.json"),
        ("--figures", "figures"),
    ):
        assert eda[eda.index(flag) + 1] == f"/workspace/data/new-run/{suffix}"
    assert (root / "data/new-run/raw/opaque-source").read_bytes() == b"preserved"
    assert all(value == "private-ambient-setting" for key, value in env.items() if key in KEYS)


def test_failed_stage_stops_before_prediction_and_preserves_source(tmp_path: Path) -> None:
    root, env = repository(tmp_path)
    env["FAIL_MODULE"] = "analysis.execute"
    assert execute(root, env, "data/failed").returncode == 7
    records = (root / "commands.jsonl").read_text().splitlines()
    assert len(records) == 3
    assert (root / "data/failed/raw/opaque-source").read_bytes() == b"preserved"
    assert execute(root, env, "data/failed").returncode != 0
    assert (root / "commands.jsonl").read_text().splitlines() == records
