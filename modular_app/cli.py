"""Command-line interface for the modular business analyst."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from modular_app.graph import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the LangGraph multi-agent business analyst.")
    parser.add_argument("--query", required=True, help="Business analysis request.")
    parser.add_argument("--data", default="data", help="Input file or data directory.")
    parser.add_argument("--output", default="modular_smoke_output", help="Artifact output directory.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(f"[INFO] Starting analysis: {args.query}")
    print(f"[INFO] Data path: {Path(args.data).resolve()}")
    try:
        result = run_pipeline(args.query, args.data, args.output)
    except Exception as exc:
        print(f"[ERROR] Pipeline failed: {type(exc).__name__}: {exc}")
        return 1
    print(f"[INFO] Status: {result.get('status', 'unknown')}")
    for warning in result.get("warnings", []):
        print(f"[WARNING] {warning}")
    print("[INFO] Artifacts:")
    for key, value in result.get("artifacts", {}).items():
        print(f"  {key}: {value}")
    return 0 if result.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
