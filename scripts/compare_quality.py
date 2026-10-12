"""Reproducible direct-stitch corpus, source previews and quantized top-layer audits."""

from __future__ import annotations

import argparse
import io
import json
import math
import platform
from pathlib import Path

import numpy as np
import pyembroidery as pe
import resvg_py
from PIL import Image

from embroidery_rungs import GenerationParams, StitchParams, generate
from embroidery_rungs.stitching.quality import measure_stitches
from embroidery_rungs.svg_manager import UNITS_PER_MM, load_svg_paths

ROOT = Path(__file__).resolve().parents[1]
PIXELS_PER_MM = 12
THREAD_MM = 0.3


def make_corpus(directory):
    directory.mkdir(parents=True, exist_ok=True)
    star = []
    for i in range(10):
        angle, radius = i * math.pi / 5 - math.pi / 2, 23 if i % 2 == 0 else 9
        star.append(f"{40 + radius * math.cos(angle):.4f},{35 + radius * math.sin(angle):.4f}")
    shapes = {
        "straight": '<rect x="10" y="30" width="60" height="4"/>',
        "capsule": '<rect x="10" y="30" width="60" height="5" rx="2.5"/>',
        "tight-curve": '<path d="M45 30 A5 5 0 1 0 45 40" fill="none" stroke="black" stroke-width="4"/>',
        "s-curve": '<path d="M10 45 C10 5 40 5 40 35 S70 65 70 25" fill="none" stroke="black" stroke-width="5"/>',
        "ring": '<circle cx="40" cy="35" r="20" fill="none" stroke="black" stroke-width="4"/>',
        "wide-ring": '<circle cx="40" cy="35" r="20" fill="none" stroke="black" stroke-width="11"/>',
        "taper": '<path d="M10 35 L70 29 L70 41 Z"/>',
        "sharp-corner": '<path d="M15 10 H20 V50 H65 V55 H15 Z"/>',
        "star": '<polygon points="' + " ".join(star) + '"/>',
        "holes": '<path fill-rule="evenodd" d="M10 10 H70 V60 H10 Z M20 20 H35 V40 H20 Z M45 30 H60 V50 H45 Z"/>',
        "junction": '<path d="M37.5 10 H42.5 V32.5 H70 V37.5 H42.5 V60 H37.5 V37.5 H10 V32.5 H37.5 Z"/>',
        "thin": '<path d="M10 45 C10 10 40 10 40 35 S70 60 70 20" fill="none" stroke="black" stroke-width="0.8"/>',
        "small-counter": '<path fill-rule="evenodd" d="M30 25 H50 V45 H30 Z M39.6 34.4 H40.4 V35.6 H39.6 Z"/>',
        "fine-ring": '<circle cx="40" cy="35" r="4" fill="none" stroke="black" stroke-width="0.8"/>',
        "fine-junction": '<path d="M39.55 20 H40.45 V34.55 H55 V35.45 H40.45 V50 H39.55 V35.45 H25 V34.55 H39.55 Z"/>',
        "small-islands": "".join(f'<circle cx="{30 + 4 * i}" cy="35" r="0.45"/>' for i in range(6)),
    }
    for name, shape in shapes.items():
        (directory / f"{name}.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="70mm" viewBox="0 0 80 70">'
            + shape
            + "</svg>\n"
        )
    return sorted(directory.glob("*.svg"))


def footprint(commands, origin_mm, target, transform):
    return measure_stitches(commands, origin_mm, target, transform[0], transform[1], THREAD_MM)


def target_mask(source):
    svg, _ = load_svg_paths(source)
    width, height = svg.width / UNITS_PER_MM, svg.height / UNITS_PER_MM
    # Bound large artwork exactly as generation does, but measure at higher resolution.
    scale = min(PIXELS_PER_MM, 2400 / max(width, height))
    png = resvg_py.svg_to_bytes(
        svg_string=svg.xml, zoom=scale / UNITS_PER_MM, dpi=96, skip_system_fonts=True
    )
    alpha = np.asarray(Image.open(io.BytesIO(png)).getchannel("A")) >= 128
    padded = np.pad(alpha, 12)
    return padded, (scale, np.array([12, 12])), png


def top_commands(data):
    commands = []
    for run in data["top_layer_runs"]:
        points = data["commands"][run["start"] : run["end"]]
        if points:
            commands.append([*points[0][:2], pe.JUMP])
            commands.extend(points)
    if not commands:
        raise ValueError("No top-layer stitches to measure.")
    return commands


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/quality")
    parser.add_argument("--synthetic-only", action="store_true")
    parser.add_argument("--design-width-mm", type=float)
    parser.add_argument("--input", type=Path, nargs="+", help="Optional SVG or bitmap corpus")
    parser.add_argument("--machine", choices=("generic", "brother-skitch-pp1"), default="generic")
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    sources = args.input or make_corpus(ROOT / "examples/quality")
    if not args.input and not args.synthetic_only:
        sources += [p for p in sorted((ROOT / "examples").rglob("*.svg")) if p not in sources]
    report = {
        "schema_version": 3,
        "engine": "direct",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "measurement": {
            "basis": "quantized_top_layer",
            "pixels_per_mm": PIXELS_PER_MM,
            "thread_mm": THREAD_MM,
            "structural_tolerance_mm": 0.25,
            "design_width_mm": args.design_width_mm,
        },
        "results": [],
    }
    for source in sources:
        source = source.resolve()
        name = (
            source.relative_to(ROOT / "examples").as_posix()
            if source.is_relative_to(ROOT / "examples")
            else source.name
        )
        directory = args.output / Path(name).with_suffix("")
        row = {"file": name}
        report["results"].append(row)
        try:
            result = generate(
                source,
                directory,
                GenerationParams(design_width_mm=args.design_width_mm, fit_to_hoop=True),
                stitch_params=StitchParams.for_fabric("stable", machine=args.machine),
            )
            data = json.loads(Path(result.direct.plan_path).read_text())
            target, transform, png = target_mask(result.original_path)
            directory.joinpath("source.png").write_bytes(png)
            metrics, image = footprint(top_commands(data), data["origin_mm"], target, transform)
            footprint_path = directory / "footprint.png"
            image.convert("RGB").save(footprint_path)
            row.update(
                source_preview=(directory / "source.png").relative_to(args.output).as_posix(),
                preview=Path(result.direct.preview_path).relative_to(args.output).as_posix(),
                footprint=footprint_path.relative_to(args.output).as_posix(),
                seconds=round(result.timings["total"], 4),
                metrics=metrics,
                stats=result.direct.stats,
                decisions=result.direct.decisions,
                threads=result.direct.threads,
                analysis=result.direct.analysis,
                adjustments=result.direct.adjustments,
                warnings=list(dict.fromkeys([*result.warnings, *result.direct.warnings])),
            )
            print(
                f"{name:32} coverage {metrics['structural_coverage']:.2%} gap {metrics['largest_gap_mm2']:g} mm² {result.timings['total']:.2f}s",
                flush=True,
            )
        except (ValueError, RuntimeError, OSError) as exc:
            row["error"] = str(exc)
            print(f"{name}: {exc}", flush=True)
        report_path = args.output / "comparison.json"
        temporary = report_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        temporary.replace(report_path)
    if any("error" in row for row in report["results"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
