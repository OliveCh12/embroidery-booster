"""Export and preview the direct plan without desktop embroidery software."""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pyembroidery as pe
from scipy.ndimage import distance_transform_edt, label, maximum

from ..image_processor import rasterize_svg, render_preview
from ..svg_manager import UNITS_PER_MM
from .digitizer import _physical_elements, digitize
from .params import StitchParams
from .planner import StitchPlan, build_stitch_plan
from .quality import measure_stitches
from .selection import mask_polygons


@dataclass
class DirectGenerationResult:
    pes_path: str
    dst_path: str
    preview_path: str
    svg_path: str
    plan_path: str
    stats: dict[str, float | int]
    params: StitchParams
    warnings: list[str]
    decisions: list[dict] = field(default_factory=list)
    threads: list[str] = field(default_factory=list)


def _gap_fills(residual, transform):
    """Fill residual components with a >=1.5 mm interior; keep fine strokes running."""
    pixels_per_mm = UNITS_PER_MM * math.sqrt(
        abs(transform.a * transform.d - transform.b * transform.c)
    )
    components, count = label(residual)
    if not count:
        return []
    radii = maximum(distance_transform_edt(residual), components, np.arange(1, count + 1))
    selected = np.flatnonzero(radii >= 0.75 * pixels_per_mm) + 1
    if not len(selected):
        return []
    return [
        {"type": "fill", "polygon": polygon}
        for polygon in mask_polygons(np.isin(components, selected), transform)
    ]


def _preview_svg(plan: StitchPlan, viewport_mm, path):
    width, height = viewport_mm
    origin = plan.origin_mm
    root = ET.Element(
        "svg",
        xmlns="http://www.w3.org/2000/svg",
        width=f"{width:g}mm",
        height=f"{height:g}mm",
        viewBox=f"{-origin[0]:g} {-origin[1]:g} {width:g} {height:g}",
    )
    ET.SubElement(
        root,
        "rect",
        x=str(-origin[0]),
        y=str(-origin[1]),
        width=str(width),
        height=str(height),
        fill="white",
    )
    for block in plan.blocks:
        points = block.points
        if len(points) < 2:
            continue
        d = "M" + " L".join(f"{p[0]:.2f},{p[1]:.2f}" for p in points)
        ET.SubElement(
            root,
            "path",
            d=d,
            fill="none",
            stroke="#a3acbc"
            if block.kind == "underlay"
            else "#728486"
            if block.kind == "travel"
            else plan.threads[block.color_index],
            **{"stroke-width": "0.3", "stroke-linecap": "round", "stroke-linejoin": "round"},
        )
    # Export previews include every penetration/lock, and distinguish jumps.
    coordinates = np.asarray(plan.commands)
    jump_segments = []
    for previous, current in zip(coordinates[:-1], coordinates[1:], strict=True):
        d = f"M{previous[0] / 10:.2f},{previous[1] / 10:.2f} L{current[0] / 10:.2f},{current[1] / 10:.2f}"
        if current[2] == pe.JUMP:
            jump_segments.append(d)
    ET.SubElement(
        root,
        "path",
        d=" ".join(jump_segments),
        fill="none",
        stroke="#89979d",
        **{"stroke-width": "0.08", "stroke-dasharray": "0.5 0.5"},
    )
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def export_direct(
    elements, transform, svg, stage: Path, stem: str, params: StitchParams, residual=None, mask=None
):
    started = time.perf_counter()
    layers = []
    if params.auto_select:
        plan, layers = digitize(svg, params)
    else:
        physical = _physical_elements(elements, transform)
        gap_fills = (
            _gap_fills(residual, transform) if params.fill_gaps and residual is not None else []
        )
        stitched_elements = gap_fills + physical
        plan = build_stitch_plan(stitched_elements, params)
        if mask is not None:
            audit_mask, audit_transform = rasterize_svg(svg, dpi=305)
            scale = UNITS_PER_MM * audit_transform.a
            metrics, _ = measure_stitches(
                plan.commands,
                plan.origin_mm,
                audit_mask,
                scale,
                [audit_transform.e, audit_transform.f],
            )
            plan.stats.update(
                {
                    key: value
                    for key, value in metrics.items()
                    if key
                    not in (
                        "stitches",
                        "trims",
                        "jumps",
                        "jump_length_mm",
                        "max_stitch_mm",
                        "short_stitches",
                    )
                }
            )
            if metrics["structural_coverage"] < 0.999 or metrics["largest_gap_mm2"] > 0.05:
                plan.warnings.append(
                    "Manual stitch coverage leaves gaps in the artwork; enable automatic region selection or inspect the preview."
                )
        plan.stats["gap_fill_regions"] = len(gap_fills)
        plan.stats["coverage_repairs"] = 0
        plan.threads = [params.thread_color]
    pattern = pe.EmbPattern()
    for color in plan.threads:
        pattern.add_thread(color)
    pattern.extras["name"] = stem[:16]
    pattern.extras["comments"] = "Embroidery Booster direct MAT stitch plan"
    for x, y, command in plan.commands:
        pattern.add_stitch_absolute(command, x, y)
    names = [f"{stem}_direct.{ext}" for ext in ("pes", "dst", "png", "svg", "json")]
    # Own plan has integer units, explicit locks and bounded segments. Writers
    # only encode it; no automatic resampling/density calculation is delegated.
    pe.write_pes(pattern.copy(), str(stage / names[0]), {"version": 6, "encode": False})
    pe.write_dst(
        pattern.copy(),
        str(stage / names[1]),
        {"encode": False, "version": "extended", "trim_at": 3},
    )
    _preview_svg(plan, (svg.width / UNITS_PER_MM, svg.height / UNITS_PER_MM), stage / names[3])
    (stage / names[2]).write_bytes(render_preview(stage / names[3], svg.width, svg.height))
    plan.stats["seconds"] = round(time.perf_counter() - started, 4)
    (stage / names[4]).write_text(
        json.dumps(
            {
                "schema_version": 2,
                "units": "0.1mm",
                "origin_mm": plan.origin_mm,
                "commands": plan.commands,
                "command_codes": {
                    "STITCH": pe.STITCH,
                    "JUMP": pe.JUMP,
                    "TRIM": pe.TRIM,
                    "END": pe.END,
                    "COLOR_CHANGE": pe.COLOR_CHANGE,
                },
                "stats": plan.stats,
                "params": asdict(params),
                "warnings": plan.warnings,
                "decisions": plan.decisions,
                "threads": plan.threads,
                "layers": layers,
                "top_layer_runs": [
                    {
                        "start": b.command_range[0],
                        "end": b.command_range[1],
                        "color_index": b.color_index,
                        "kind": b.kind,
                        "region": b.region,
                    }
                    for b in plan.blocks
                    if b.command_range is not None and b.kind in ("satin", "fill", "running")
                ],
                "coverage_tolerance_mm": 0.25,
                "thread_model_mm": 0.3,
                "coverage_basis": "quantized_top_layer"
                if params.auto_select
                else "all_sewn_stitches",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return names, plan
