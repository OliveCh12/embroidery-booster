"""Compare fill policies with physical sizing, repeated timings and machine-file audits.

Optional user images stay local. Coverage and machine geometry are observable;
beauty, puckering and fabric stability require sewn samples. Running stitch is a
contour interpretation and is never ranked as complete surface coverage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import resource
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time
from collections import Counter
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

from benchmark_reliability import PP1, ROOT, decision_summary, machine_metrics

POLICIES = {
    "balanced": {"stitch_type": "auto", "auto_strategy": "balanced"},
    "satin_preferred": {"stitch_type": "auto", "auto_strategy": "satin_preferred"},
    "satin": {"stitch_type": "satin"},
    "fill": {"stitch_type": "fill", "auto_fill_angle": False},
    "running": {"stitch_type": "running"},
    "comparison": {"stitch_type": "auto", "auto_strategy": "balanced"},
}
REPEATED_CASES = {"straight", "s-curve", "taper"}


def source_signature(directory):
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*.py")):
        digest.update(path.relative_to(directory).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def summarize(direct):
    from benchmark_variants import equivalence_checks

    data = json.loads(Path(direct.plan_path).read_text(encoding="utf-8"))
    machine = machine_metrics(data, direct)
    top_stitches = Counter()
    codes = data["command_codes"]
    for run in data["top_layer_runs"]:
        top_stitches[run["kind"]] += sum(
            (data["commands"][index][2] & codes["command_mask"]) == codes["stitch"]
            for index in range(run["start"] + 1, run["end"])
        )
    areas = {
        method: round(
            sum(d.get("area_mm2", 0) for d in direct.decisions if d["method"] == method), 4
        )
        for method in ("satin", "fill", "running", "omitted")
    }
    total = sum(areas.values())
    safety = {
        "within_hoop": machine["within_hoop"],
        "bounded_stitches": machine["max_stitch_mm"] <= direct.params.max_stitch_mm + 0.0001,
        "bounded_jumps": machine["max_jump_mm"] <= 12.0001,
        "machine_roundtrip": all(
            exported["same_stitch_points"]
            and exported["color_changes"] == direct.stats["color_changes"]
            for exported in machine["exports"].values()
        )
        and machine["exports"]["pes"]["same_threads"],
    }
    return {
        "stats": direct.stats,
        "analysis": direct.analysis,
        "threads": direct.threads,
        "methods": dict(Counter(d["method"] for d in direct.decisions)),
        "top_layer_stitches": dict(top_stitches),
        "homogeneous_top_layer": len(top_stitches) == 1,
        "method_area_mm2": areas,
        "satin_area_ratio": round(areas["satin"] / total, 6) if total else 0,
        "machine": machine,
        "safety_checks": safety,
        "quality_checks": {
            "no_rejected_connections": direct.stats["unsafe_connections"] == 0,
            "no_satin_crowding": direct.stats["crowded_satin_penetrations"] == 0,
            "no_short_stitches": direct.stats["short_stitches"] == 0,
        },
        "equivalence": equivalence_checks(
            direct.decisions, auto_fill_angle=direct.params.auto_fill_angle
        ),
        "decision_summary": decision_summary(direct.decisions),
        "effective_params": asdict(direct.params),
        "command_sha256": hashlib.sha256(
            json.dumps([data["commands"], data["threads"]], separators=(",", ":")).encode()
        ).hexdigest(),
        "stitch_breakdown": direct.analysis.get("stitch_breakdown", {}),
        "warnings": direct.warnings,
    }


def worker(args):
    sys.path.insert(0, str(args.worker_src))
    import embroidery_rungs
    from embroidery_rungs import GenerationParams, StitchParams, generate

    if not Path(embroidery_rungs.__file__).resolve().is_relative_to(args.worker_src.resolve()):
        raise RuntimeError("Worker imported an engine outside the requested snapshot")
    density = (
        {"density_percent": args.density_percent}
        if "density_percent" in StitchParams.__dataclass_fields__
        else {}
    )
    params = StitchParams.for_fabric(
        "stable", stabilizer="cutaway", machine=PP1, **POLICIES[args.worker_policy], **density
    )
    row = {
        "policy": args.worker_policy,
        "coverage_scope": "contour" if args.worker_policy == "running" else "surface",
        "engine_source_sha256": source_signature(args.worker_src),
    }
    started = time.perf_counter()
    try:
        result = generate(
            args.worker_input,
            args.worker_output,
            GenerationParams(design_width_mm=80, fit_to_hoop=True),
            stitch_params=params,
            compare_strategies=args.worker_policy == "comparison",
        )
        # Generation timing excludes audit/read-back and Python import startup.
        row["seconds"] = round(time.perf_counter() - started, 6)
        row.update(summarize(result.direct))
        row["input_analysis"] = result.input_analysis
        row["timings"] = {key: round(value, 6) for key, value in result.timings.items()}
        if args.worker_policy == "comparison":
            row.update(
                recommended_variant=result.recommended_variant,
                skipped_variants=result.skipped_variants,
                variants=[
                    {
                        "id": variant.id,
                        "equivalent_strategies": variant.equivalent_strategies,
                        "quality": variant.quality,
                        **summarize(variant.direct),
                    }
                    for variant in result.variants
                ],
            )
    except (ValueError, RuntimeError, OSError) as exc:
        row.update(
            seconds=round(time.perf_counter() - started, 6),
            error=str(exc),
            error_type=type(exc).__name__,
        )
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    row["peak_rss_mib"] = round(peak / (1024**2 if sys.platform == "darwin" else 1024), 3)
    print(json.dumps(row), flush=True)


def corpus(args):
    # Actual reported problem images run first so their evidence is available early.
    for name in ("phoenix", "falcon", "nike", "pepsi"):
        source = getattr(args, name)
        if source is not None:
            yield name, source.resolve()
    for name in (
        "straight",
        "s-curve",
        "taper",
        "ring",
        "star",
        "junction",
        "holes",
        "union-jack",
        "thin",
    ):
        yield name, ROOT / "examples" / "quality" / f"{name}.svg"
    yield "nike-vector", ROOT / "examples/nike.svg"


def run_case(source_root, phase, name, source, args):
    row = {
        "case": name,
        "input_name": source.name,
        "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "policies": [],
    }
    for policy in POLICIES:
        if args.policy and policy not in args.policy:
            continue
        if policy == "comparison" and not args.compare_strategies:
            continue
        measurements = []
        for repeat in range(args.repeats if name in REPEATED_CASES else 1):
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker-src",
                str(source_root),
                "--worker-input",
                str(source),
                "--worker-policy",
                policy,
                "--worker-output",
                str(args.output / phase / name / policy / str(repeat)),
                "--density-percent",
                str(args.density_percent),
            ]
            started = time.perf_counter()
            try:
                process = subprocess.run(
                    command, capture_output=True, text=True, timeout=args.timeout, check=True
                )
                measurement = json.loads(process.stdout)
            except subprocess.TimeoutExpired:
                measurement = {
                    "error_type": "TimeoutExpired",
                    "error": f"Timeout after {args.timeout} s",
                    "seconds": round(time.perf_counter() - started, 6),
                }
            measurements.append(measurement)
        result = measurements[0]
        timings = [run["seconds"] for run in measurements]
        result.update(
            policy=policy,
            repetitions=len(measurements),
            seconds_median=round(statistics.median(timings), 6),
            seconds_min=min(timings),
            seconds_max=max(timings),
            seconds_samples=timings,
            repeatable_outcome=len(
                {run.get("command_sha256", run.get("error")) for run in measurements}
            )
            == 1,
            repeat_peak_rss_mib=[run.get("peak_rss_mib") for run in measurements],
        )
        row["policies"].append(result)
        outcome = (
            result.get("error")
            or f"{result['methods']}; {len(result['threads'])} threads; coverage {result['stats']['structural_coverage']:.2%}"
        )
        print(
            f"{phase}/{name}/{policy}: {outcome} ({result['seconds_median']:.2f}s, n={len(measurements)})",
            flush=True,
        )
        # Incremental evidence is retained even if a later complex case times out.
        partial = args.output / phase / f"{name}.json"
        partial.parent.mkdir(parents=True, exist_ok=True)
        partial.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    successful = [policy for policy in row["policies"] if "error" not in policy]
    material_fields = (
        "fabric",
        "stabilizer",
        "thread_weight",
        "satin_spacing_mm",
        "fill_spacing_mm",
        "pull_compensation_mm",
        "underlay",
        "machine",
        "max_stitch_mm",
        "min_stitch_mm",
    )
    row["invariant_checks"] = {
        "same_palette": len({tuple(policy["threads"]) for policy in successful}) <= 1,
        "same_material_settings": all(
            len({policy["effective_params"][field] for policy in successful}) <= 1
            for field in material_fields
        ),
        "equivalence_preserved": all(policy["equivalence"]["consistent"] for policy in successful),
        "machine_safety": all(all(policy["safety_checks"].values()) for policy in successful),
        "deterministic_repeats": all(policy["repeatable_outcome"] for policy in row["policies"]),
        "unchanged_engine_sources": len(
            {
                policy["engine_source_sha256"]
                for policy in row["policies"]
                if "engine_source_sha256" in policy
            }
        )
        <= 1,
    }
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline-ref",
        default="650e164",
        help="Git snapshot extracted without switching the shared branch",
    )
    parser.add_argument("--phase", choices=("baseline", "current", "both"), default="both")
    parser.add_argument("--case", action="append", help="Limit corpus; repeat for more cases")
    parser.add_argument(
        "--policy",
        action="append",
        choices=POLICIES,
        help="Limit policies; repeat for more policies",
    )
    parser.add_argument(
        "--compare-strategies",
        action="store_true",
        help="Also measure automatic comparison and audit every returned candidate",
    )
    for name in ("phoenix", "falcon", "nike", "pepsi"):
        parser.add_argument(
            f"--{name}", type=Path, help="Optional local bitmap, never copied into tracked fixtures"
        )
    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="Timed runs per policy on straight, s-curve and taper",
    )
    parser.add_argument(
        "--timeout", type=float, default=300, help="Maximum seconds per isolated run"
    )
    parser.add_argument(
        "--density-percent",
        type=int,
        default=100,
        help="Relative material density (80 to 120); current engine only for non-default values",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "output/performance-quality")
    parser.add_argument("--worker-src", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--worker-input", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--worker-policy", choices=POLICIES, help=argparse.SUPPRESS)
    parser.add_argument("--worker-output", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker_src is not None:
        worker(args)
        return
    if args.policy and "comparison" in args.policy:
        args.compare_strategies = True
    if args.repeats < 3:
        parser.error("--repeats must be at least 3 for meaningful bounded-case medians")
    if not 80 <= args.density_percent <= 120:
        parser.error("--density-percent must be between 80 and 120")
    if args.density_percent != 100 and args.phase != "current":
        parser.error("Non-default density requires --phase current")
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    selected = [case for case in corpus(args) if not args.case or case[0] in args.case]
    if args.case and len(selected) != len(set(args.case)):
        parser.error("A requested case is absent; provide its optional bitmap path")
    report = {
        "measurement": {
            "basis": "quantized_top_layer",
            "design_width_mm": 80,
            "machine": PP1,
            "fabric": "stable",
            "stabilizer": "cutaway",
            "thread_weight": 40,
            "density_percent": args.density_percent,
            "structural_tolerance_mm": 0.25,
            "machine_grid_mm": 0.1,
            "physical_sewout": False,
            "visual_ranking": False,
            "connection_metric": "legacy unsafe_connections counts rejected proposed connections, excluded from emitted machine stitches",
            "timing_scope": "generate including interpretation, stitches, preview and machine export; excluding process startup and read-back audits",
            "timing_environment": "serial runs in shared development environment; no claim of isolated hardware benchmarking",
            "repeated_cases": sorted(REPEATED_CASES),
            "repetitions": args.repeats,
            "automatic_comparison_included": args.compare_strategies,
            "memory_scope": "fresh worker process peak RSS including interpreter, libraries, generation and audits",
            "python": platform.python_version(),
            "platform": platform.platform(),
            "dependencies": {
                package: version(package)
                for package in (
                    "numpy",
                    "scipy",
                    "scikit-image",
                    "shapely",
                    "resvg-py",
                    "pyembroidery",
                )
            },
        },
        "baseline_ref": args.baseline_ref,
        "baseline_commit": (
            subprocess.check_output(
                ["git", "rev-parse", args.baseline_ref], cwd=ROOT, text=True
            ).strip()
            if args.phase in ("baseline", "both")
            else None
        ),
        "current_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "current_source_sha256": source_signature(ROOT / "src"),
        "before": [],
        "after": [],
    }
    if args.phase in ("baseline", "both"):
        with tempfile.TemporaryDirectory(prefix="embroidery-fill-baseline-") as directory:
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
            report["before"] = [
                run_case(Path(directory) / "src", "before", name, source, args)
                for name, source in selected
            ]
    if args.phase in ("current", "both"):
        report["after"] = [
            run_case(ROOT / "src", "after", name, source, args) for name, source in selected
        ]
    destination = args.output / "fill-methods-benchmark.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    main()
