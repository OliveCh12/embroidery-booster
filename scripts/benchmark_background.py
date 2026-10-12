"""Compare source silhouettes; requires the repository and its dev dependencies.

Synthetic fixtures are loaded explicitly from tests/test_background_edges.py.
The historical baseline is the standalone extractor in colors.py (release 0.5.0).
An optional Pepsi input uses a dark-ring reference proxy, not a hand-labeled truth.
Neither these mask measurements nor their timings establish sew-out quality.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import importlib.util
import json
import subprocess
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import (
    binary_erosion,
    binary_fill_holes,
    binary_propagation,
    distance_transform_edt,
    label,
)

from embroidery_rungs.colors import bitmap_foreground

ROOT = Path(__file__).resolve().parents[1]


def baseline_extractor(ref: str):
    path = "src/embroidery_rungs/colors.py"
    source = subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=ROOT, text=True)
    tree = ast.parse(source)
    function = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "bitmap_foreground"
        ),
        None,
    )
    if function is None:
        raise ValueError(
            "Baseline needs the standalone bitmap_foreground in colors.py; use the 0.5.0 ref 30c58df."
        )
    # Load only the historical function, without importing its entire old package.
    namespace = {"np": np, "binary_propagation": binary_propagation}
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    exec(compile(module, f"{ref}:{path}", "exec"), namespace)
    commit = subprocess.check_output(["git", "rev-parse", ref], cwd=ROOT, text=True).strip()
    return namespace["bitmap_foreground"], commit


def synthetic_inputs():
    spec = importlib.util.spec_from_file_location(
        "background_fixtures", ROOT / "tests/test_background_edges.py"
    )
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    for background in ("uniform", "linear", "radial", "colored"):
        for encoding in ("PNG", "JPEG", "WEBP"):
            rgba, reference = fixtures._badge(background, encoding)
            yield (
                f"{background}-{encoding.lower()}",
                rgba,
                reference,
                {"reference": "known foreground alpha before compositing and compression"},
            )
    rgba, reference = fixtures._badge("linear", "JPEG", accent=True)
    yield (
        "linear-detached-accent-jpeg",
        rgba,
        reference,
        {"reference": "known foreground alpha before compositing and compression"},
    )


def pepsi_input(path: Path):
    with Image.open(path) as image:
        rgba = np.asarray(image.convert("RGBA"))
    components, _ = label(np.max(rgba[..., :3], axis=2) < 80)
    areas = np.bincount(components.ravel())
    areas[0] = 0
    if not areas.max():
        raise ValueError("Pepsi reference proxy requires a closed dark outline.")
    reference = binary_fill_holes(components == areas.argmax())
    return (
        "pepsi-real",
        rgba,
        reference,
        {
            "input_name": path.name,
            "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "reference": "proxy: fill largest four-connected dark component, max RGB <80",
            "reference_limit": "Dark-core edge omits antialiasing; allow two source pixels."
            " This is a proxy for the closed Pepsi outline, not a labeled photograph mask.",
        },
    )


def measure(rgba, reference, extractor):
    diagnostics = {}
    started = time.perf_counter()
    result = extractor(rgba, diagnostics=diagnostics)
    elapsed = time.perf_counter() - started
    mask = result[..., 3] >= 128
    distance = distance_transform_edt(~reference)
    union = np.count_nonzero(mask | reference)
    metrics = {
        "seconds": round(elapsed, 4),
        "mask_pixels": int(mask.sum()),
        "components": label(mask)[1],
        "intersection_over_union": round(np.count_nonzero(mask & reference) / union, 5),
        "false_pixels_beyond_1_5px": int(np.count_nonzero(mask & (distance > 1.5))),
        "false_pixels_beyond_2px": int(np.count_nonzero(mask & (distance > 2))),
        "maximum_outer_distance_px": round(float(distance[mask].max(initial=0)), 3),
        "missing_core_pixels": int(
            np.count_nonzero(binary_erosion(reference, iterations=2) & ~mask)
        ),
        "reason": diagnostics.get("reason"),
        "diagnostics": diagnostics,
    }
    return result, metrics


def comparison(name, before, after, reference, output):
    height, width = before.shape[:2]
    false_exterior = distance_transform_edt(~reference) > 1.5
    panels = []
    for rgba in (before, after):
        cloth = Image.new("RGBA", (width, height), (166, 184, 199, 255))
        preview = np.array(Image.alpha_composite(cloth, Image.fromarray(rgba)).convert("RGB"))
        preview[(rgba[..., 3] >= 128) & false_exterior] = [255, 0, 210]
        image = Image.fromarray(preview)
        image.thumbnail((640, 480), Image.Resampling.LANCZOS)
        panels.append(image)
    width, height = panels[0].size
    board = Image.new("RGB", (width * 2 + 16, height + 34), (245, 247, 250))
    board.paste(panels[0], (0, 34))
    board.paste(panels[1], (width + 16, 34))
    draw = ImageDraw.Draw(board)
    draw.text((4, 8), f"{name} / baseline", fill="black")
    draw.text((width + 20, 8), "current / magenta = fringe >1.5px", fill="black")
    board.save(output / f"{name}-comparison.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline-ref",
        default="30c58df",
        help="Git revision containing the standalone 0.5.0 extractor",
    )
    parser.add_argument(
        "--pepsi", type=Path, help="Optional real Pepsi image with a closed black ring"
    )
    parser.add_argument("--output", type=Path, default=ROOT / "output/background-investigation")
    args = parser.parse_args()
    try:
        baseline, commit = baseline_extractor(args.baseline_ref)
        inputs = list(synthetic_inputs())
        if args.pepsi is not None:
            inputs.append(pepsi_input(args.pepsi))
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Background benchmark failed: {exc}\n")
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, rgba, reference, metadata in inputs:
        before, a = measure(rgba, reference, baseline)
        after, b = measure(rgba, reference, bitmap_foreground)
        rows.append({"case": name, **metadata, "before": a, "after": b})
        comparison(name, before, after, reference, args.output)
        print(
            f"{name}: fringe >2px {a['false_pixels_beyond_2px']} -> {b['false_pixels_beyond_2px']}; "
            f"components {a['components']} -> {b['components']}; "
            f"missing core {b['missing_core_pixels']}; IoU {b['intersection_over_union']}"
        )
    payload = {
        "baseline_commit": commit,
        "reference_units": "source pixels, before tracing and machine compensation",
        "scope": "Source-mask audit; timing is one measured run, no sew-out quality inference.",
        "cases": rows,
    }
    (args.output / "mask-benchmark.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    fields = (
        "components",
        "false_pixels_beyond_2px",
        "missing_core_pixels",
        "intersection_over_union",
        "seconds",
    )
    with (args.output / "mask-benchmark.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["case", "phase", *fields])
        for row in rows:
            for phase in ("before", "after"):
                writer.writerow([row["case"], phase, *[row[phase][key] for key in fields]])


if __name__ == "__main__":
    main()
