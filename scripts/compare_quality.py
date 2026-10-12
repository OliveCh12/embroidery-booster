"""Reproducible stitch-footprint comparison, with optional real Ink/Stitch exports."""

from __future__ import annotations

import argparse
import io
import json
import math
import platform
import subprocess
import time
import zipfile
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pyembroidery as pe
import resvg_py
from PIL import Image
from svgelements import Move
from svgelements import Path as SVGPath

from embroidery_rungs import GenerationParams, StitchParams, generate
from embroidery_rungs.inputs import prepare_artwork
from embroidery_rungs.stitching.quality import measure_stitches
from embroidery_rungs.svg_manager import INKSTITCH_NS, UNITS_PER_MM, load_svg_paths
from embroidery_rungs.web.services import configure_native_svg

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


def native_plan(satin_path, directory, executable, params, safe=False):
    root = ET.parse(satin_path).getroot()
    for element in root.iter():
        if element.get(f"{{{INKSTITCH_NS}}}satin_column"):
            for name, value in {
                "zigzag_spacing_mm": params.satin_spacing_mm,
                "max_stitch_length_mm": params.max_stitch_mm,
                "pull_compensation_mm": params.pull_compensation_mm,
                "center_walk_underlay": params.underlay,
                "zigzag_underlay": params.underlay,
            }.items():
                element.set(f"{{{INKSTITCH_NS}}}{name}", str(value).lower())
        # Compare monochrome designs with identical ordering, avoiding color-change bias.
        if element.tag.endswith("}path"):
            element.set("style", element.get("style", "").replace("#1466c8", "#e02020"))
            if safe:
                element.set(f"{{{INKSTITCH_NS}}}trim_after", "true")
    prefix = "native-safe" if safe else "native"
    prepared = directory / "native-input.svg"
    ET.ElementTree(root).write(prepared, encoding="utf-8")
    if safe:
        configure_native_svg(prepared, prepared, params)
    started = time.perf_counter()
    preview = subprocess.run(
        [str(executable), "--extension=stitch_plan_preview", "--move-to-side=False", str(prepared)],
        capture_output=True,
        check=True,
        timeout=180,
    )
    if not preview.stdout:
        raise RuntimeError(preview.stderr.decode(errors="replace")[-1200:])
    svg = ET.fromstring(preview.stdout)
    group = next(e for e in svg if e.get("id") == "__inkstitch_stitch_plan__")
    first_path = next(e for e in group.iter() if e.tag.endswith("}path"))
    first = next(s.end for s in SVGPath(first_path.get("d")) if isinstance(s, Move))
    for element in list(svg):
        if element is not group:
            svg.remove(element)
    (directory / f"{prefix}.svg").write_bytes(ET.tostring(svg))
    (directory / f"{prefix}.png").write_bytes(
        resvg_py.svg_to_bytes(svg_string=ET.tostring(svg, encoding="unicode"), width=1000, dpi=96)
    )
    archive = subprocess.run(
        [
            str(executable),
            "--extension=zip",
            "--format-pes=True",
            "--format-dst=True",
            str(prepared),
        ],
        capture_output=True,
        check=True,
        timeout=180,
    )
    with zipfile.ZipFile(io.BytesIO(archive.stdout)) as bundle:
        pes = next(name for name in bundle.namelist() if name.endswith(".pes"))
        (directory / f"{prefix}.pes").write_bytes(bundle.read(pes))
    pattern = pe.read(str(directory / f"{prefix}.pes"))
    commands = np.asarray(pattern.stitches)
    first_stitch = commands[(commands[:, 2].astype(int) & pe.COMMAND_MASK) == pe.STITCH][0, :2]
    origin = np.array([first.x, first.y]) / UNITS_PER_MM - first_stitch / 10
    data = {"commands": commands.tolist(), "origin_mm": origin.tolist()}
    (directory / f"{prefix}.json").write_text(json.dumps(data))
    return data, time.perf_counter() - started


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/quality-comparison")
    parser.add_argument("--inkstitch", type=Path)
    parser.add_argument(
        "--modes",
        nargs="+",
        choices=("direct-fill", "direct-split", "direct-auto", "inkstitch", "inkstitch-safe"),
        default=["direct-fill", "direct-split", "direct-auto", "inkstitch-safe"],
    )
    parser.add_argument(
        "--reuse", action="store_true", help="Remeasure saved plans without regeneration"
    )
    parser.add_argument("--synthetic-only", action="store_true")
    parser.add_argument("--design-width-mm", type=float, help="Resize each SVG before comparison")
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    sources = make_corpus(ROOT / "examples/quality")
    if not args.synthetic_only:
        sources += [p for p in sorted((ROOT / "examples").rglob("*.svg")) if p not in sources]
    report_path = args.output / "comparison.json"
    previous = json.loads(report_path.read_text()) if report_path.exists() else {"results": []}
    if (
        previous["results"]
        and previous.get("measurement", {}).get("design_width_mm") != args.design_width_mm
    ):
        parser.error(
            "This output contains another design size; choose a separate --output directory."
        )
    rows = {r["file"]: r for r in previous["results"]}
    if "inkstitch" not in args.modes:
        for row in rows.values():
            row["methods"].pop("inkstitch", None)
    params = StitchParams(hoop_width_mm=500, hoop_height_mm=500, auto_select=False)
    for source in sources:
        name = source.relative_to(ROOT / "examples").as_posix()
        directory = args.output / source.relative_to(ROOT / "examples").with_suffix("")
        directory.mkdir(parents=True, exist_ok=True)
        if args.design_width_mm is not None:
            input_dir = directory / "input"
            input_dir.mkdir(exist_ok=True)
            source, _ = prepare_artwork(
                source, input_dir, GenerationParams(design_width_mm=args.design_width_mm), params
            )
            source = Path(source)
        target, transform, png = target_mask(source)
        (directory / "source.png").write_bytes(png)
        row = rows.setdefault(name, {"file": name, "methods": {}})
        row["source_preview"] = (directory / "source.png").relative_to(args.output).as_posix()
        # A preparation pass also ensures native-only runs have current MAT rails.
        if not args.reuse:
            geometry = generate(source, directory, GenerationParams(auto_optimize=True))
            row["rails_coverage"] = round(geometry.coverage, 4)
        for mode in args.modes:
            try:
                if args.reuse:
                    if mode in ("inkstitch", "inkstitch-safe"):
                        prefix = "native-safe" if mode == "inkstitch-safe" else "native"
                        plan_path, preview_path = (
                            directory / f"{prefix}.json",
                            directory / f"{prefix}.png",
                        )
                    else:
                        plan_path = directory / mode / f"{source.stem}_direct.json"
                        preview_path = plan_path.with_suffix(".png")
                    if not plan_path.exists():
                        continue
                    data = json.loads(plan_path.read_text())
                    seconds = row["methods"].get(mode, {}).get("seconds", 0)
                elif mode in ("inkstitch", "inkstitch-safe"):
                    if not args.inkstitch:
                        continue
                    safe = mode == "inkstitch-safe"
                    data, seconds = native_plan(
                        geometry.satin_path, directory, args.inkstitch, params, safe=safe
                    )
                    preview_path = directory / ("native-safe.png" if safe else "native.png")
                else:
                    mode_params = (
                        replace(params, auto_select=True)
                        if mode == "direct-auto"
                        else replace(params, wide_mode=mode.removeprefix("direct-"))
                    )
                    result = generate(
                        source,
                        directory / mode,
                        GenerationParams(auto_optimize=True),
                        method="both",
                        stitch_params=mode_params,
                    )
                    data = json.loads(Path(result.direct.plan_path).read_text())
                    seconds = result.timings["total"]
                    preview_path = Path(result.direct.preview_path)
                metrics, image = footprint(data["commands"], data["origin_mm"], target, transform)
                footprint_path = directory / f"{mode}-footprint.png"
                image.convert("RGB").save(footprint_path)
                row["methods"][mode] = {
                    "metrics": metrics,
                    "seconds": round(seconds, 4),
                    "preview": preview_path.relative_to(args.output).as_posix(),
                    "footprint": footprint_path.relative_to(args.output).as_posix(),
                    "stats": data.get("stats", {}),
                    "decisions": data.get("decisions", []),
                }
                print(
                    f"{name:30} {mode:13} {metrics['coverage']:6.1%} IoU {metrics['iou']:6.1%} "
                    f"{metrics['trims']:4} trims {seconds:6.2f}s",
                    flush=True,
                )
            except (
                ValueError,
                RuntimeError,
                subprocess.SubprocessError,
                StopIteration,
                ET.ParseError,
                zipfile.BadZipFile,
            ) as exc:
                row["methods"][mode] = {"error": str(exc) or type(exc).__name__}
                print(f"{name}: {mode} failed: {exc}", flush=True)
        report = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "measurement": {
                "pixels_per_mm": PIXELS_PER_MM,
                "thread_mm": THREAD_MM,
                "includes_underlay": True,
                "structural_tolerance_mm": 0.25,
                "design_width_mm": args.design_width_mm,
                "inkstitch_version": "3.3.0"
                if args.inkstitch
                else previous.get("measurement", {}).get("inkstitch_version"),
            },
            "results": list(rows.values()),
        }
        temporary_report = report_path.with_suffix(".json.tmp")
        temporary_report.write_text(json.dumps(report, indent=2) + "\n")
        temporary_report.replace(report_path)


if __name__ == "__main__":
    main()
