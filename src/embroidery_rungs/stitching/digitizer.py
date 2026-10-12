"""Colour-aware automatic digitizing in one physical, quantized machine frame."""

from __future__ import annotations

import math

import numpy as np
import pyembroidery as pe

from ..colors import separate_colors
from ..image_processor import compute_medial_axis, rasterize_rgba
from ..rung_generator import generate_rungs
from ..svg_manager import UNITS_PER_MM, SVGDocument
from .params import StitchParams
from .planner import StitchPlan, build_stitch_plan
from .quality import measure_plan, satin_crowding
from .selection import select_stitch_types


def _physical_elements(elements, transform):
    inverse = ~transform
    matrix = np.array([[inverse.a, inverse.b], [inverse.c, inverse.d]]) / UNITS_PER_MM
    offset = np.array([inverse.e, inverse.f]) / UNITS_PER_MM
    return [
        {
            "type": e["type"],
            **{
                k: np.asarray(e[k]) @ matrix + offset
                for k in ("points", "rail_a", "rail_b")
                if k in e
            },
        }
        for e in elements
    ]


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
    # Shared grid/origin: no independent per-colour centering or second rounding.
    rows, cols = np.nonzero(labels)
    inverse = ~transform
    center = np.array([(cols.min() + cols.max()) / 2, (rows.min() + rows.max()) / 2])
    origin = (
        center @ np.array([[inverse.a, inverse.b], [inverse.c, inverse.d]]) + [inverse.e, inverse.f]
    ) / UNITS_PER_MM
    plans, diagnostics, command_count = [], [], 0
    for index, color in enumerate(colors, 1):
        mask = labels == index
        skeleton, distance = compute_medial_axis(mask)
        _, _, elements = generate_rungs(
            skeleton, distance, 3 * scale, mask, min_satin_width_px=0.5 * scale, pixels_per_mm=scale
        )
        physical = _physical_elements(elements, transform)
        selected, decisions = select_stitch_types(
            physical, mask, transform, params, origin_mm=origin
        )
        if not selected:
            raise ValueError(f"Colour {color} has no stitchable regions; enlarge the design.")
        plan = build_stitch_plan(selected, params, origin_mm=origin)
        command_count += len(plan.commands)
        if command_count > params.max_stitches:
            raise ValueError(
                "Stitch budget exceeded across colour layers; reduce colours or enlarge spacing."
            )
        plan.decisions = decisions
        plan.stats["crowded_satin_penetrations"] = satin_crowding(plan, params.min_stitch_mm)
        metrics, _ = measure_plan(plan, mask, scale, [transform.e, transform.f])
        if (
            metrics["structural_coverage"] < 0.999
            or metrics["largest_gap_mm2"] > 0.05
            or metrics["uncovered_max_mm"] > 0.5
        ):
            plan.warnings.append(
                f"Top-layer coverage is {metrics['structural_coverage']:.2%}; largest unfilled area {metrics['largest_gap_mm2']:g} mm², maximum distance from thread {metrics['uncovered_max_mm']:g} mm. Enlarge fine details or inspect before sewing."
            )
        for decision in decisions:
            decision["coverage_basis"] = "quantized_top_layer"
        diagnostics.append({"color": color, "area_pixels": int(mask.sum()), **metrics})
        plans.append(plan)
    result = _combine(plans, colors, params, origin)
    enlarged = sum(d.get("minimum_detail_enlarged", False) for d in result.decisions)
    result.stats["minimum_detail_enlargements"] = enlarged
    result.stats["crowded_satin_penetrations"] = sum(
        p.stats["crowded_satin_penetrations"] for p in plans
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
    if reduced:
        result.warnings.append(
            f"Artwork gradients/colours were quantized to {len(colors)} thread colours; inspect the interpreted palette."
        )
    return result, diagnostics
