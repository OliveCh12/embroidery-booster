"""Compare interpreted artwork and full machine exports on a small reliability corpus.

Optional user images stay local. Measurements audit generated geometry and do
not establish sew-out quality; timings are single runs, not a performance test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PP1 = "brother-skitch-pp1"


def synthetic_inputs(directory):
    directory.mkdir(parents=True, exist_ok=True)
    shapes = {
        "column": '<rect x="10" y="20" width="60" height="4"/>',
        "border-column": '<rect x="10" y="20" width="60" height="7.2"/>',
        "over-limit-column": '<rect x="10" y="20" width="60" height="7.8"/>',
        "wide-column": '<rect x="10" y="20" width="60" height="12"/>',
        "taper": '<path d="M10 35L70 29L70 41Z"/>',
        "ring": '<circle cx="40" cy="35" r="20" fill="none" stroke="black" stroke-width="4"/>',
        "branches": '<path fill="none" stroke="black" stroke-width="4" '
        'stroke-linejoin="round" d="M10 55L40 20L70 55M40 20V65"/>',
        "tight-curve": '<path d="M45 30A5 5 0 1 0 45 40" fill="none" '
        'stroke="black" stroke-width="4"/>',
        "holes": '<path fill-rule="evenodd" '
        'd="M10 10H70V60H10Z M20 20H35V40H20Z M45 30H60V50H45Z"/>',
        "symmetry": '<path d="M8 10H33V15H15V30H8Z"/><path d="M72 60H47V55H65V40H72Z"/>',
        "multicolor": '<rect x="5" y="10" width="70" height="48" fill="#012169"/>'
        '<path d="M5 10L75 58M75 10L5 58" stroke="#ffffff" stroke-width="7"/>'
        '<path d="M5 10L75 58M75 10L5 58" stroke="#c8102e" stroke-width="2"/>'
        '<path d="M40 10V58M5 34H75" stroke="#ffffff" stroke-width="12"/>'
        '<path d="M40 10V58M5 34H75" stroke="#c8102e" stroke-width="6"/>',
        "accent": '<rect x="8" y="10" width="45" height="15"/>'
        '<circle cx="60" cy="17" r="0.55" fill="#00ff00"/>',
    }
    for name, shape in shapes.items():
        source = directory / f"{name}.svg"
        source.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="70mm" '
            f'viewBox="0 0 80 70">{shape}</svg>\n',
            encoding="utf-8",
        )
        strategies = (
            ("auto",)
            if name in ("symmetry", "multicolor", "accent")
            else (
                "auto",
                "satin",
            )
        )
        for strategy in strategies:
            manual = strategy == "satin" and name in (
                "border-column",
                "over-limit-column",
                "wide-column",
            )
            yield (
                f"{name}-{strategy}",
                source,
                {
                    "stitch_type": strategy,
                    **({"auto_adjust": False, "max_satin_width_mm": 7.5} if manual else {}),
                },
            )


def machine_metrics(data, direct):
    import numpy as np
    import pyembroidery as pe

    commands = np.asarray(data["commands"])
    codes = commands[:, 2].astype(int) & pe.COMMAND_MASK
    previous = np.vstack([np.zeros(2), commands[:-1, :2]])
    lengths = np.linalg.norm(commands[:, :2] - previous, axis=1) / 10
    sewn = (codes == pe.STITCH) & (lengths > 1e-9)
    satin_floats = []
    for run in data["top_layer_runs"]:
        if run["kind"] == "satin":
            start, end = run["start"], run["end"]
            # The first run node supplies previous-position context.
            satin_floats.extend(lengths[start + 1 : end][sewn[start + 1 : end]])
    expected = commands[codes == pe.STITCH, :2]
    exports = {}
    for kind, path in (("pes", direct.pes_path), ("dst", direct.dst_path)):
        pattern = pe.read(str(path))
        actual = np.asarray(pattern.stitches)
        actual_codes = actual[:, 2].astype(int) & pe.COMMAND_MASK
        exports[kind] = {
            "same_stitch_points": bool(
                np.array_equal(actual[actual_codes == pe.STITCH, :2], expected)
            ),
            "stitches": int(np.count_nonzero(actual_codes == pe.STITCH)),
            "color_changes": int(np.count_nonzero(actual_codes == pe.COLOR_CHANGE)),
            "bytes": Path(path).stat().st_size,
        }
        if kind == "pes":
            exports[kind]["same_threads"] = [
                thread.hex_color().lower() for thread in pattern.threadlist
            ] == data["threads"]
    half_hoop = np.array([direct.params.hoop_width_mm, direct.params.hoop_height_mm]) / 2
    return {
        "command_count": len(commands),
        "min_stitch_mm": round(float(lengths[sewn].min()), 4) if sewn.any() else None,
        "max_stitch_mm": round(float(lengths[sewn].max(initial=0)), 4),
        "max_satin_float_mm": round(float(max(satin_floats, default=0)), 4),
        "max_jump_mm": round(float(lengths[codes == pe.JUMP].max(initial=0)), 4),
        "maximum_abs_point_mm": np.round(np.abs(commands[:, :2]).max(axis=0) / 10, 3).tolist(),
        "within_hoop": bool(np.all(np.abs(commands[:, :2] / 10) <= half_hoop + 1e-9)),
        "exports": exports,
    }


def decision_summary(decisions):
    groups = defaultdict(list)
    for decision in decisions:
        groups[(decision.get("color"), decision["method"], decision.get("reason"))].append(decision)
    return [
        {
            "color": color,
            "method": method,
            "reason": reason,
            "regions": len(members),
            "area_mm2": round(sum(d.get("area_mm2", 0) for d in members), 2),
            "maximum_width_mm": max(d.get("width_mm", 0) for d in members),
            "safe_satin_width_mm": max(
                (d["safe_satin_width_mm"] for d in members if "safe_satin_width_mm" in d),
                default=None,
            ),
            "split_satin_columns": sum(d.get("split_satin_columns", 0) for d in members),
            "equivalence_groups": len({d.get("equivalence_group") for d in members}),
        }
        for (color, method, reason), members in groups.items()
    ]


def worker(args):
    sys.path.insert(0, str(args.worker_src))
    from embroidery_rungs import GenerationParams, StitchParams, generate

    cases = list(synthetic_inputs(args.output / "fixtures"))
    for name, source in (
        ("nike", args.nike),
        ("complex-badge", args.complex_badge),
        ("pepsi", args.pepsi),
    ):
        if source is not None:
            cases.append((f"{name}-auto-pp1", source, {}))
            if name == "nike":
                cases.append(("nike-satin-pp1", source, {"stitch_type": "satin"}))
            if name == "complex-badge":
                cases.append(("complex-badge-auto-12-colors", source, {"machine": "generic"}))
    for name, source, settings in cases:
        started = time.perf_counter()
        row = {"case": name, "input_name": source.name, "settings": settings}
        try:
            row["input_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            settings = {"machine": PP1, **settings}
            params = StitchParams.for_fabric("stable", stabilizer="cutaway", **settings)
            result = generate(
                source,
                args.output / args.worker_phase / name,
                GenerationParams(design_width_mm=80, fit_to_hoop=True),
                stitch_params=params,
            )
            direct = result.direct
            data = json.loads(Path(direct.plan_path).read_text())
            row.update(
                stats=direct.stats,
                analysis=direct.analysis,
                threads=direct.threads,
                methods=dict(Counter(d["method"] for d in direct.decisions)),
                machine=machine_metrics(data, direct),
                input_analysis=result.input_analysis,
                adjustments=direct.adjustments,
                effective_limits={
                    "max_stitch_mm": direct.params.max_stitch_mm,
                    "max_satin_width_mm": direct.params.max_satin_width_mm,
                    "min_stitch_mm": direct.params.min_stitch_mm,
                    "max_colors": direct.params.max_colors,
                },
                timings={key: round(value, 4) for key, value in result.timings.items()},
                warnings=list(dict.fromkeys([*result.warnings, *direct.warnings])),
                decision_summary=decision_summary(direct.decisions),
            )
        except Exception as exc:
            row.update(error=str(exc), error_type=type(exc).__name__)
        row["seconds"] = round(time.perf_counter() - started, 4)
        print(json.dumps(row), flush=True)


def run(source, phase, args):
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker-src",
        str(source),
        "--worker-phase",
        phase,
        "--output",
        str(args.output),
    ]
    for name in ("nike", "complex_badge", "pepsi"):
        value = getattr(args, name)
        if value is not None:
            command += ["--" + name.replace("_", "-"), str(value)]
    rows = []
    with subprocess.Popen(command, stdout=subprocess.PIPE, text=True) as process:
        for line in process.stdout:
            row = json.loads(line)
            rows.append(row)
            if "error" in row:
                summary = row["error"]
            else:
                summary = (
                    f"{row['methods']}; {len(row['threads'])} threads; "
                    f"{row['analysis']['region_count']} regions; "
                    f"coverage {row['stats']['structural_coverage']:.2%}"
                )
            print(f"{phase}/{row['case']}: {summary} ({row['seconds']:.2f}s)", flush=True)
        if process.wait():
            raise subprocess.CalledProcessError(process.returncode, command)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", help="Optional Git revision, isolated with git archive")
    parser.add_argument("--nike", type=Path, help="Optional local black Nike bitmap")
    parser.add_argument("--complex-badge", type=Path, help="Optional local noisy badge JPEG")
    parser.add_argument("--pepsi", type=Path, help="Optional local badge with enclosed white paint")
    parser.add_argument("--output", type=Path, default=ROOT / "output/reliability")
    parser.add_argument("--worker-src", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--worker-phase", default="after", help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.worker_src is not None:
        worker(args)
        return
    for name in ("nike", "complex_badge", "pepsi"):
        value = getattr(args, name)
        if value is not None:
            setattr(args, name, value.resolve())
    args.output.mkdir(parents=True, exist_ok=True)
    report = {
        "baseline_ref": args.baseline_ref,
        "measurement": {
            "basis": "quantized_top_layer",
            "design_width_mm": 80,
            "machine": PP1,
            "structural_tolerance_mm": 0.25,
            "machine_grid_mm": 0.1,
            "segment_basis": "command destination; initial position at hoop center",
            "minimum_basis": "nonzero needle moves; stationary penetrations excluded",
        },
        "before": None,
        "after": None,
    }
    if args.baseline_ref:
        report["baseline_commit"] = subprocess.check_output(
            ["git", "rev-parse", args.baseline_ref], cwd=ROOT, text=True
        ).strip()
        with tempfile.TemporaryDirectory(prefix="embroidery-baseline-") as directory:
            archive = Path(directory) / "source.tar"
            with archive.open("wb") as stream:
                subprocess.run(
                    ["git", "archive", args.baseline_ref, "src"],
                    cwd=ROOT,
                    stdout=stream,
                    check=True,
                )
            with tarfile.open(archive) as bundle:
                bundle.extractall(directory, filter="data")
            report["before"] = run(Path(directory) / "src", "before", args)
    report["after"] = run(ROOT / "src", "after", args)
    destination = args.output / "reliability-benchmark.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    main()
