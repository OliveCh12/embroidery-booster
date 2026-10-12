"""Colour-aware automatic digitizing in one physical, quantized machine frame."""

from __future__ import annotations

import math
from dataclasses import asdict

import numpy as np
import pyembroidery as pe

from ..colors import separate_colors
from ..image_processor import rasterize_rgba
from ..svg_manager import UNITS_PER_MM, SVGDocument
from .analysis import adjust_for_sewing, analyze_regions
from .consistency import select_consistent_regions
from .params import StitchParams
from .planner import StitchPlan, UnstitchableRegion, build_stitch_plan
from .quality import coverage_needs_review, measure_plan, satin_crowding
from .regions import design_symmetries

MAX_VISIBLE_REGIONS = 4096


def _combine(plans, colors, params, origin):
    commands, blocks, decisions, warnings = [], [], [], []
    stats = {}
    region_offset = 0
    for color_index, plan in enumerate(plans):
        start = next(i for i, command in enumerate(plan.commands) if command[2] == pe.STITCH)
        first = np.asarray(plan.commands[start][:2])
        previous = np.asarray(commands[-1][:2]) if commands else np.array([0, 0])
        if commands:
            commands.append([int(previous[0]), int(previous[1]), pe.COLOR_CHANGE])
        count = max(1, math.ceil(np.linalg.norm(first - previous) / 120))
        for point in np.rint(
            previous + (first - previous) * np.arange(1, count + 1)[:, None] / count
        ).astype(int):
            commands.append([int(point[0]), int(point[1]), pe.JUMP])
        command_offset = len(commands) - start
        commands.extend(plan.commands[start:-1])  # Keep the terminal trim, one END globally.
        for block in plan.blocks:
            block.region += region_offset
            block.color_index = color_index
            if block.command_range is not None:
                block.command_range = tuple(i + command_offset for i in block.command_range)
        blocks.extend(plan.blocks)
        for decision in plan.decisions:
            decisions.append(
                {
                    **decision,
                    "source_component": decision["component"],
                    "component": len(decisions) + 1,
                    "color_index": color_index,
                    "color": colors[color_index],
                }
            )
        region_offset += max((b.region - region_offset for b in plan.blocks), default=-1) + 1
        warnings.extend(f"{colors[color_index]}: {warning}" for warning in plan.warnings)
        for key in (
            "satin_regions",
            "fill_regions",
            "running_regions",
            "underlay_stitches",
            "unsafe_connections",
            "omitted_regions",
        ):
            stats[key] = stats.get(key, 0) + plan.stats[key]
    commands.append([*commands[-1][:2], pe.END])
    array = np.asarray(commands)
    penetrations = array[array[:, 2] == pe.STITCH, :2]
    shift = np.rint((penetrations.min(axis=0) + penetrations.max(axis=0)) / 2).astype(int)
    array[:, :2] -= shift
    origin = np.asarray(origin) + shift / 10
    first_stitch = int(np.flatnonzero(array[:, 2] == pe.STITCH)[0])
    first = array[first_stitch, :2]
    count = max(1, math.ceil(np.linalg.norm(first) / 120))
    prefix = [
        [int(x), int(y), pe.JUMP]
        for x, y in np.rint(first * np.arange(1, count + 1)[:, None] / count).astype(int)
    ]
    commands = prefix + array[first_stitch:].tolist()
    for block in blocks:
        block.points -= shift / 10
        if block.command_range is not None:
            block.command_range = tuple(i + count - first_stitch for i in block.command_range)
    if len(commands) > params.max_stitches:
        raise ValueError(
            "Stitch budget exceeded across colour layers; reduce colours or enlarge spacing."
        )
    array = np.asarray(commands)
    lengths = np.linalg.norm(np.diff(array[:, :2], axis=0), axis=1) / 10
    sewn = (array[:-1, 2] == pe.STITCH) & (array[1:, 2] == pe.STITCH)
    size = np.ptp(array[array[:, 2] == pe.STITCH, :2], axis=0) / 10
    if np.any(size > [params.hoop_width_mm, params.hoop_height_mm]):
        raise ValueError("Combined colour layers exceed the configured hoop.")
    half_hoop = np.array([params.hoop_width_mm, params.hoop_height_mm]) / 2
    if np.any(np.abs(array[:, :2] / 10) > half_hoop + 1e-9):
        raise ValueError(
            "Centered machine coordinates exceed the configured hoop; enlarge the hoop or reduce the design slightly."
        )
    stats.update(
        stitches=int(np.count_nonzero(array[:, 2] == pe.STITCH)),
        trims=int(np.count_nonzero(array[:, 2] == pe.TRIM)),
        jumps=int(np.count_nonzero(array[:, 2] == pe.JUMP)),
        color_changes=len(plans) - 1,
        colors=len(plans),
        width_mm=round(float(size[0]), 2),
        height_mm=round(float(size[1]), 2),
        thread_length_mm=round(float(lengths[sewn].sum()), 1),
        jump_length_mm=round(float(lengths[array[1:, 2] == pe.JUMP].sum()), 1),
        max_stitch_mm=round(float(lengths[sewn].max(initial=0)), 2),
        short_stitches=int(np.count_nonzero(lengths[sewn] < params.min_stitch_mm - 0.08)),
        gap_fill_regions=0,
        coverage_repairs=0,
    )
    return StitchPlan(commands, blocks, tuple(origin), stats, warnings, decisions, colors)


def digitize(svg: SVGDocument, params: StitchParams) -> tuple[StitchPlan, list[dict]]:
    requested_params = asdict(params)
    params, adjustments = adjust_for_sewing(params)
    rgba, transform = rasterize_rgba(svg, dpi=305)
    if params.preserve_colors:
        labels, colors, reduced = separate_colors(rgba, params.max_colors)
    else:
        labels, colors, reduced = (
            (rgba[..., 3] >= 128).astype(np.uint8),
            [params.thread_color],
            False,
        )
    scale = UNITS_PER_MM * np.sqrt(abs(transform.a * transform.d - transform.b * transform.c))
    analysis = analyze_regions(labels, scale, params, palette_reduced=reduced)
    if analysis["region_count"] > MAX_VISIBLE_REGIONS:
        raise ValueError(
            f"Artwork contains {analysis['region_count']} visible regions; the limit is {MAX_VISIBLE_REGIONS}. Simplify the artwork, remove image noise, or reduce the number of colours."
        )
    # Shared grid/origin: no independent per-colour centering or second rounding.
    rows, cols = np.nonzero(labels)
    inverse = ~transform
    center = np.array([(cols.min() + cols.max()) / 2, (rows.min() + rows.max()) / 2])
    origin = (
        center @ np.array([[inverse.a, inverse.b], [inverse.c, inverse.d]]) + [inverse.e, inverse.f]
    ) / UNITS_PER_MM
    plans, diagnostics, command_count = [], [], 0
    symmetries = design_symmetries(labels)
    sewn_colors, skipped_decisions, skipped_warnings = [], [], []
    for index, color in enumerate(colors, 1):
        mask = labels == index
        selected, decisions = select_consistent_regions(mask, transform, params, origin, symmetries)
        if not selected:
            skipped_decisions.extend(
                {**d, "color": color, "color_index": None, "source_component": d["component"]}
                for d in decisions
            )
            skipped_warnings.append(
                f"Colour {color} has no stitchable regions and was omitted; enlarge its details."
            )
            empty = StitchPlan([], [], tuple(origin), {})
            metrics, _ = measure_plan(empty, mask, scale, [transform.e, transform.f])
            diagnostics.append(
                {"color": color, "area_pixels": int(mask.sum()), "omitted": True, **metrics}
            )
            continue
        plan = build_stitch_plan(selected, params, origin_mm=origin)
        command_count += len(plan.commands)
        if command_count > params.max_stitches:
            raise ValueError(
                "Stitch budget exceeded across colour layers; reduce colours or enlarge spacing."
            )
        plan.decisions = decisions
        omitted = sum(d["method"] == "omitted" for d in decisions)
        plan.stats["omitted_regions"] += omitted
        rejected_geometry = sum(
            d["method"] == "omitted" and d["reason"] == "machine_geometry_rejected"
            for d in decisions
        )
        if rejected_geometry:
            plan.warnings.append(
                f"{rejected_geometry} details failed safe geometry validation on the machine grid and were omitted; inspect the preview or simplify their sharp corners."
            )
        if omitted > rejected_geometry:
            plan.warnings.append(
                f"{omitted - rejected_geometry} details are below machine resolution and were omitted; enlarge the design."
            )
        plan.stats["crowded_satin_penetrations"] = satin_crowding(plan, params.min_stitch_mm)
        metrics, _ = measure_plan(plan, mask, scale, [transform.e, transform.f])
        if params.stitch_type == "satin" and (
            coverage_needs_review(metrics)
            or plan.stats["unsafe_connections"]
            or plan.stats["crowded_satin_penetrations"]
            or plan.stats["omitted_regions"]
            or plan.stats["short_stitches"]
        ):
            raise ValueError(
                f"Satin requested, but colour {color} fails complete safe coverage or regularity in the final machine plan. Use automatic or fill stitching, or simplify the shape."
            )
        if coverage_needs_review(metrics):
            if params.stitch_type == "running":
                plan.warnings.append(
                    f"Running stitches reproduce contours/centerlines rather than solid fill; solid artwork coverage is {metrics['structural_coverage']:.2%}. Inspect the intended outlines before sewing."
                )
            else:
                plan.warnings.append(
                    f"Top-layer coverage is {metrics['structural_coverage']:.2%}; largest unfilled area {metrics['largest_gap_mm2']:g} mm², maximum distance from thread {metrics['uncovered_max_mm']:g} mm. Enlarge fine details or inspect before sewing."
                )
        for decision in decisions:
            decision["coverage_basis"] = "quantized_top_layer"
        diagnostics.append({"color": color, "area_pixels": int(mask.sum()), **metrics})
        plans.append(plan)
        sewn_colors.append(color)
    if not plans:
        raise UnstitchableRegion("No colour has stitchable regions; enlarge the design.")
    result = _combine(plans, sewn_colors, params, origin)
    decision_offset = len(result.decisions)
    result.decisions.extend(
        {**d, "component": decision_offset + i + 1} for i, d in enumerate(skipped_decisions)
    )
    result.stats["omitted_regions"] += len(skipped_decisions)
    result.warnings.extend(skipped_warnings)
    enlarged = sum(d.get("minimum_detail_enlarged", False) for d in result.decisions)
    result.stats["minimum_detail_enlargements"] = enlarged
    result.stats["crowded_satin_penetrations"] = sum(
        p.stats["crowded_satin_penetrations"] for p in plans
    )
    if result.stats["short_stitches"]:
        result.warnings.append(
            f"{result.stats['short_stitches']} stitches are below the machine minimum after quantization; inspect before sewing."
        )
    if result.stats["crowded_satin_penetrations"]:
        result.warnings.append(
            f"{result.stats['crowded_satin_penetrations']} satin penetrations are crowded; inspect sharp curves before sewing."
        )
    if enlarged:
        result.warnings.append(
            f"{enlarged} compact details were extended by at most 0.08 mm per end to retain the minimum stitch length; enlarge the design for finer fidelity."
        )
    weights = np.array([d["area_pixels"] for d in diagnostics], dtype=float)
    for key in ("coverage", "structural_coverage", "iou"):
        result.stats[key] = round(
            float(np.average([d[key] for d in diagnostics], weights=weights)), 4
        )
    for key in ("spill_mm2", "missing_mm2", "structural_missing_mm2"):
        result.stats[key] = round(sum(d[key] for d in diagnostics), 2)
    for key in ("largest_gap_mm2", "uncovered_max_mm", "uncovered_p95_mm"):
        result.stats[key] = max(d[key] for d in diagnostics)
    result.stats["audit_pixels_per_mm"] = round(float(scale), 3)
    result.stats["symmetry_operations"] = len(symmetries)
    result.stats["equivalent_regions"] = sum(d["equivalent_regions"] > 1 for d in result.decisions)
    result.stats["omitted_colors"] = len(colors) - len(sewn_colors)
    result.stats["adjusted_parameters"] = len(adjustments)
    result.params = params
    result.requested_params = requested_params
    result.adjustments = adjustments
    result.analysis = {
        **analysis,
        "requested_stitch_type": params.stitch_type,
        "strategy_policy": "coherent_color_fill"
        if any(d.get("strategy_scope") == "color" for d in result.decisions)
        else "geometry_per_region"
        if params.stitch_type == "auto"
        else "explicit_uniform",
        "strategy_counts": {
            method: sum(d["method"] == method for d in result.decisions)
            for method in ("satin", "fill", "running", "omitted")
        },
        "quality_status": "needs_review"
        if result.stats["omitted_regions"]
        or result.stats["unsafe_connections"]
        or result.stats["short_stitches"]
        or result.stats["crowded_satin_penetrations"]
        or analysis["micro_region_count"] >= 50
        or any(coverage_needs_review(d) for d in diagnostics)
        else "geometric_checks_passed",
    }
    if analysis["micro_region_count"] >= 50:
        result.warnings.append(
            f"Artwork contains {analysis['micro_region_count']} disconnected colour islands smaller than 0.15 mm² ({analysis['micro_region_area_mm2']:g} mm² total). These may produce excessive tiny runs and jumps; inspect image noise and colour boundaries."
        )
    if reduced:
        result.warnings.append(
            f"Artwork gradients/colours were quantized to {len(colors)} thread colours; inspect the interpreted palette."
        )
    if params.fabric == "stretch" and params.stabilizer != "cutaway":
        result.warnings.append(
            "Stretch fabrics need lasting support; select a suitable cutaway stabilizer and test on the actual fabric."
        )
    if params.fabric in ("stretch", "textured") and not params.underlay:
        result.warnings.append(
            "Underlay is disabled on an unstable or textured fabric; top stitches may sink or pucker."
        )
    if params.machine == "brother-skitch-pp1":
        result.warnings.append(
            "Import the PES via Artspira; enable Jump Stitch Trimming on the Skitch PP1 and sew a fabric sample first."
        )
    return result, diagnostics
