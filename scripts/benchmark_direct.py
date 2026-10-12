"""Compare direct engines with the same top-layer audit and physical sizing."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def worker(source_root, width):
    sys.path.insert(0, str(source_root))
    from embroidery_rungs import GenerationParams, StitchParams, generate
    from embroidery_rungs.image_processor import rasterize_svg
    from embroidery_rungs.stitching import export
    from embroidery_rungs.svg_manager import UNITS_PER_MM, load_svg_paths

    spec = importlib.util.spec_from_file_location(
        "benchmark_quality", ROOT / "src/embroidery_rungs/stitching/quality.py"
    )
    quality = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(quality)
    captured = []
    preview = export._preview_svg

    def capture(plan, *args):
        captured[:] = [plan]
        return preview(plan, *args)

    export._preview_svg = capture
    rows = []
    with tempfile.TemporaryDirectory(prefix="embroidery-benchmark-") as directory:
        for source in sorted((ROOT / "examples").rglob("*.svg")):
            started = time.perf_counter()
            try:
                result = generate(
                    source,
                    directory,
                    GenerationParams(design_width_mm=width),
                    method="direct",
                    stitch_params=StitchParams(hoop_width_mm=500, hoop_height_mm=500),
                )
                plan = captured[-1]
                document, _ = load_svg_paths(result.original_path)
                target, transform = rasterize_svg(document, dpi=305)
                metrics, _ = quality.measure_plan(
                    plan, target, transform.a * UNITS_PER_MM, [transform.e, transform.f]
                )
                rows.append(
                    {
                        "file": source.relative_to(ROOT / "examples").as_posix(),
                        "top_metrics": metrics,
                        "stats": result.direct.stats,
                        "threads": getattr(plan, "threads", [result.direct.params.thread_color]),
                        "methods": sorted({d["method"] for d in plan.decisions}),
                        "seconds": round(time.perf_counter() - started, 4),
                        "warnings": result.direct.warnings,
                        "analysis": getattr(plan, "analysis", {}),
                        "adjustments": getattr(plan, "adjustments", []),
                    }
                )
            except (ValueError, RuntimeError, OSError) as exc:
                rows.append(
                    {"file": source.relative_to(ROOT / "examples").as_posix(), "error": str(exc)}
                )
    print(json.dumps(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/benchmarks/direct-top-layer.json"
    )
    parser.add_argument(
        "--baseline-ref", help="Optional Git revision, run in an isolated temporary checkout"
    )
    parser.add_argument("--design-width-mm", type=float)
    parser.add_argument("--worker-src", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker_src:
        worker(args.worker_src, args.design_width_mm)
        return

    def run(source_root):
        command = [sys.executable, str(Path(__file__).resolve()), "--worker-src", str(source_root)]
        if args.design_width_mm is not None:
            command += ["--design-width-mm", str(args.design_width_mm)]
        return json.loads(
            subprocess.run(command, capture_output=True, text=True, check=True).stdout
        )

    baseline = None
    if args.baseline_ref:
        with tempfile.TemporaryDirectory(prefix="embroidery-baseline-") as directory:
            archive = Path(directory) / "source.tar"
            with archive.open("wb") as output:
                subprocess.run(
                    ["git", "archive", args.baseline_ref, "src"],
                    cwd=ROOT,
                    stdout=output,
                    check=True,
                )
            with tarfile.open(archive) as bundle:
                bundle.extractall(directory, filter="data")
            baseline = run(Path(directory) / "src")
    current = run(ROOT / "src")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "baseline_ref": args.baseline_ref,
                "design_width_mm": args.design_width_mm,
                "measurement": {
                    "basis": "quantized_top_layer",
                    "thread_mm": 0.3,
                    "structural_tolerance_mm": 0.25,
                    "dpi": 305,
                },
                "before": baseline,
                "after": current,
            },
            indent=2,
        )
        + "\n"
    )
    for title, rows in (("before", baseline), ("after", current)):
        if rows is None:
            continue
        valid = [row for row in rows if "error" not in row]
        print(
            f"{title}: {len(valid)}/{len(rows)} plans, top coverage {sum(r['top_metrics']['structural_coverage'] for r in valid) / len(valid):.4%}, "
            f"{sum(r['stats']['trims'] for r in valid)} trims; largest gap {max(r['top_metrics']['largest_gap_mm2'] for r in valid):g} mm²"
        )
    print(args.output)


if __name__ == "__main__":
    main()
