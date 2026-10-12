"""Reproducible end-to-end benchmark; no hardware-dependent test assertions."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import tempfile
from pathlib import Path

from embroidery_rungs import GenerationParams, generate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="*", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--auto-optimize", action="store_true")
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    inputs = args.inputs or sorted((Path(__file__).resolve().parents[1] / "examples").glob("*.svg"))
    rows = []
    for source in inputs:
        times = []
        for _ in range(args.repeats + 1):
            with tempfile.TemporaryDirectory() as output:
                result = generate(
                    source, output, GenerationParams(dpi=args.dpi, auto_optimize=args.auto_optimize)
                )
            times.append(result.timings["total"])
        row = {
            "file": source.name,
            "median_seconds": round(statistics.median(times[1:]), 4),
            "rungs": result.rungs_count,
            "satin": result.columns_count,
            "running": result.running_count,
            "coverage": round(result.coverage, 4),
        }
        rows.append(row)
        print(
            f"{source.name:20} {row['median_seconds']:8.4f}s  "
            f"{result.columns_count:3} satin  {result.running_count:3} running  "
            f"{result.coverage:6.1%} swept coverage",
            flush=True,
        )
    report = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "dpi": args.dpi,
        "auto_optimize": args.auto_optimize,
        "repeats": args.repeats,
        "results": rows,
    }
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
