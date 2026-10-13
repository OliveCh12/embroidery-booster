"""Audit automatic texture variants on a bounded vector/bitmap corpus.

Optional user bitmaps remain local. The report measures quantized geometry and
machine-file fidelity; it cannot establish fabric stability or visual sew-out
quality. Runtime figures are single runs rather than performance benchmarks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

from benchmark_reliability import PP1, ROOT, decision_summary, machine_metrics, synthetic_inputs

from embroidery_rungs import GenerationParams, StitchParams, generate


def equivalence_checks(decisions, *, auto_fill_angle):
    cohorts = defaultdict(list)
    for decision in decisions:
        if decision.get("equivalent_regions", 1) > 1:
            cohorts[(decision.get("color"), decision["equivalence_group"])].append(decision)
    fields = (
        "method",
        "satin_spacing_mm",
        "fill_spacing_mm",
        "pull_compensation_mm",
        "canonical_fill_angle_deg" if auto_fill_angle else "fill_angle_deg",
        "underlay_strategy",
    )
    failures = []
    for (color, group), members in cohorts.items():
        inconsistent = [
            field for field in fields if len({member.get(field) for member in members}) > 1
        ]
        if inconsistent:
            failures.append({"color": color, "group": group, "fields": inconsistent})
    return {"cohorts": len(cohorts), "consistent": not failures, "failures": failures}


def summarize_variant(variant):
    direct = variant.direct
    data = json.loads(Path(direct.plan_path).read_text(encoding="utf-8"))
    checks = machine_metrics(data, direct)
    areas = {
        method: round(
            sum(d.get("area_mm2", 0) for d in direct.decisions if d["method"] == method), 2
        )
        for method in ("satin", "fill", "running", "omitted")
    }
    total = sum(areas.values())
    safety = {
        "within_hoop": checks["within_hoop"],
        "bounded_stitches": checks["max_stitch_mm"] <= direct.params.max_stitch_mm + 0.0001,
        "bounded_jumps": checks["max_jump_mm"] <= 12.0001,
        "no_unsafe_connections": direct.stats["unsafe_connections"] == 0,
        "no_satin_crowding": direct.stats["crowded_satin_penetrations"] == 0,
        "no_short_stitches": direct.stats["short_stitches"] == 0,
        "machine_roundtrip": all(
            export["same_stitch_points"]
            and export["color_changes"] == direct.stats["color_changes"]
            for export in checks["exports"].values()
        )
        and checks["exports"]["pes"]["same_threads"],
    }
    return {
        "id": variant.id,
        "equivalent_strategies": variant.equivalent_strategies,
        "quality": variant.quality,
        "reasons": variant.reasons,
        "stats": direct.stats,
        "analysis": direct.analysis,
        "threads": direct.threads,
        "methods": dict(Counter(d["method"] for d in direct.decisions)),
        "method_area_mm2": areas,
        "satin_area_ratio": round(areas["satin"] / total, 4) if total else 0,
        "machine": checks,
        "safety_checks": safety,
        "equivalence": equivalence_checks(
            direct.decisions, auto_fill_angle=direct.params.auto_fill_angle
        ),
        "decision_summary": decision_summary(direct.decisions),
        "effective_params": asdict(direct.params),
        "command_sha256": hashlib.sha256(
            json.dumps([data["commands"], data["threads"]], separators=(",", ":")).encode()
        ).hexdigest(),
        "warnings": direct.warnings,
    }


def cases(directory, args):
    selected = {
        "column",
        "taper",
        "ring",
        "branches",
        "holes",
        "symmetry",
    }
    for name, path, _settings in synthetic_inputs(directory):
        shape, strategy = name.rsplit("-", 1)
        if shape in selected and strategy == "auto":
            yield shape, path
    broad = directory / "broad-stroke.svg"
    broad.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="70mm" '
        'viewBox="0 0 80 70"><rect x="10" y="10" width="32" height="12"/></svg>\n',
        encoding="utf-8",
    )
    yield "broad-stroke", broad
    yield "union-jack", ROOT / "examples/quality/union-jack.svg"
    yield "nike-vector", ROOT / "examples/nike.svg"
    yield "thin-detail", ROOT / "examples/quality/thin.svg"
    for name, path in (("nike-bitmap", args.nike), ("pepsi-bitmap", args.pepsi)):
        if path is not None:
            yield name, path.resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nike", type=Path, help="Optional local black Nike bitmap")
    parser.add_argument("--pepsi", type=Path, help="Optional local badge with enclosed white paint")
    parser.add_argument("--output", type=Path, default=ROOT / "output/automatic-variants")
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    rows, failures = [], []
    for name, path in cases(args.output / "fixtures", args):
        started = time.perf_counter()
        row = {"case": name, "input_name": path.name}
        try:
            row["input_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            result = generate(
                path,
                args.output / name,
                GenerationParams(design_width_mm=80, fit_to_hoop=True),
                stitch_params=StitchParams.for_fabric("stable", stabilizer="cutaway", machine=PP1),
                compare_strategies=True,
            )
            variants = [summarize_variant(variant) for variant in result.variants]
            chosen = next(v for v in result.variants if v.id == result.recommended_variant)
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
            invariant_checks = {
                "unique_machine_plans": len({v["command_sha256"] for v in variants})
                == len(variants),
                "same_palette": len({tuple(v["threads"]) for v in variants}) == 1,
                "same_material_settings": all(
                    len({v["effective_params"][field] for v in variants}) == 1
                    for field in material_fields
                ),
                "recommended_result_selected": result.direct.plan_path == chosen.direct.plan_path,
                "qualified_candidate_preferred": not any(
                    v["analysis"]["quality_status"] == "geometric_checks_passed" for v in variants
                )
                or chosen.direct.analysis["quality_status"] == "geometric_checks_passed",
                "equivalence_preserved": all(v["equivalence"]["consistent"] for v in variants),
                "machine_safety": all(all(v["safety_checks"].values()) for v in variants),
            }
            failed = [key for key, passed in invariant_checks.items() if not passed]
            if failed:
                failures.append({"case": name, "checks": failed})
            row.update(
                recommended_variant=result.recommended_variant,
                skipped_variants=result.skipped_variants,
                variants=variants,
                invariant_checks=invariant_checks,
                input_analysis=result.input_analysis,
                timings={key: round(value, 4) for key, value in result.timings.items()},
                warnings=result.warnings,
            )
            summary = ", ".join(
                f"{v['id']}={v['methods']} ({v['stats']['structural_coverage']:.2%})"
                for v in variants
            )
            print(f"{name}: recommended {result.recommended_variant}; {summary}", flush=True)
        except Exception as exc:
            row.update(error=str(exc), error_type=type(exc).__name__)
            failures.append({"case": name, "error": str(exc)})
            print(f"{name}: {type(exc).__name__}: {exc}", flush=True)
        row["seconds"] = round(time.perf_counter() - started, 4)
        rows.append(row)
    report = {
        "measurement": {
            "basis": "quantized_top_layer",
            "design_width_mm": 80,
            "machine": PP1,
            "fabric": "stable",
            "stabilizer": "cutaway",
            "thread_weight": 40,
            "structural_tolerance_mm": 0.25,
            "machine_grid_mm": 0.1,
            "ranking_scope": "geometric_diagnostics_and_qualified_texture_preferences",
            "physical_sewout": False,
            "timings": "single_runs_in_shared_development_environment",
        },
        "cases": rows,
        "invariant_failures": failures,
    }
    destination = args.output / "automatic-variants-benchmark.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(destination)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
