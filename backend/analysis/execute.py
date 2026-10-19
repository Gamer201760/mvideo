import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import nbformat
from jupyter_client.kernelspec import KernelSpecManager
from jupyter_client.manager import KernelManager
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK_API: Any = nbformat


def cells(source: Path) -> list[nbformat.NotebookNode]:
    result: list[nbformat.NotebookNode] = []
    kind = "code"
    lines: list[str] = []
    for line in source.read_text().splitlines():
        if line.startswith("# %%"):
            if lines:
                text = "\n".join(lines).strip()
                result.append(
                    NOTEBOOK_API.v4.new_markdown_cell(text)
                    if kind == "markdown"
                    else NOTEBOOK_API.v4.new_code_cell(text)
                )
            kind = "markdown" if "[markdown]" in line else "code"
            lines = []
        else:
            lines.append(line.removeprefix("# ").removeprefix("#") if kind == "markdown" else line)
    if lines:
        result.append(NOTEBOOK_API.v4.new_code_cell("\n".join(lines).strip()))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--processed", type=Path, required=True)
    parser.add_argument("--notebook", type=Path, default=ROOT / "notebooks/eda.ipynb")
    parser.add_argument("--figures", type=Path, default=ROOT / "docs/images/eda")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/eda.json")
    args = parser.parse_args()
    if not (args.processed / "manifest.json").is_file():
        parser.error("Processed manifest is missing; run python -m app.prepare_data first")
    local = ROOT / ".local/eda"
    kernel = local / "kernels/release-data"
    kernel.mkdir(parents=True, exist_ok=True)
    (kernel / "kernel.json").write_text(
        json.dumps(
            {
                "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
                "display_name": "Release data",
                "language": "python",
            }
        )
    )
    for path in (args.figures, args.report.parent, args.notebook.parent, local / "matplotlib"):
        path.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "backend"),
        "EDA_RAW": str(args.raw.resolve()),
        "EDA_PROCESSED": str(args.processed.resolve()),
        "EDA_FIGURES": str(args.figures.resolve()),
        "EDA_REPORT": str(args.report.resolve()),
        "MPLCONFIGDIR": str(local / "matplotlib"),
    }
    notebook = NOTEBOOK_API.v4.new_notebook(cells=cells(ROOT / "notebooks/eda.py"))
    notebook.metadata["kernelspec"] = {
        "name": "release-data",
        "display_name": "Release data",
        "language": "python",
    }
    manager = KernelManager(
        kernel_name="release-data",
        kernel_spec_manager=KernelSpecManager(kernel_dirs=[str(kernel.parent)]),
    )
    client = NotebookClient(notebook, km=manager, timeout=900)
    try:
        client.execute(env=env, cwd=str(ROOT))
    finally:
        if manager.has_kernel:
            manager.shutdown_kernel(now=True)
    NOTEBOOK_API.write(notebook, args.notebook)
    print(
        json.dumps(
            {
                "notebook": str(args.notebook),
                "code_cells": sum(c.cell_type == "code" for c in notebook.cells),
                "report": str(args.report),
            }
        )
    )


if __name__ == "__main__":
    main()
