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
from .coverage import audit_coverage
from .params import StitchParams
from .planner import StitchPlan, build_stitch_plan
from .selection import mask_polygons, select_stitch_types


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


def _physical_elements(elements, transform):
    inverse = ~transform

    def physical(points):
        xy = np.asarray(points, dtype=float)
        return (
            xy @ np.array([[inverse.a, inverse.b], [inverse.c, inverse.d]]) + [inverse.e, inverse.f]
        ) / UNITS_PER_MM

    converted = []
    for element in elements:
        item = {"type": element["type"]}
        for key in ("points", "rail_a", "rail_b"):
            if key in element:
                item[key] = physical(element[key])
        converted.append(item)
    return converted


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
    colors = {
        "underlay": "#a3acbc",
        "running": "#17789d",
        "satin": "#17789d",
        "fill": "#ac6932",
        "travel": "#728486",
        "lock": "#17789d",
    }
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
            stroke=colors[block.kind],
            **{"stroke-width": "0.14", "stroke-linecap": "round", "stroke-linejoin": "round"},
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
    physical = _physical_elements(elements, transform)
    decisions = []
    if params.auto_select and mask is not None:
        physical, decisions, filled_mask = select_stitch_types(physical, mask, transform, params)
        if residual is not None:
            residual = residual & ~filled_mask
    gap_fills = _gap_fills(residual, transform) if params.fill_gaps and residual is not None else []
    # Put residual fills before the satin so satin edges finish on top.
    selected_gaps = [element for element in physical if element.get("gap_fill")]
    top = [element for element in physical if not element.get("gap_fill")]
    stitched_elements = gap_fills + selected_gaps + top
    plan = build_stitch_plan(stitched_elements, params)
    if mask is not None:
        audit_mask, audit_transform = mask, transform
        scale = UNITS_PER_MM * math.sqrt(abs(transform.a * transform.d - transform.b * transform.c))
        if scale < 12:
            audit_mask, audit_transform = rasterize_svg(svg, dpi=305)
        plan = audit_coverage(plan, stitched_elements, audit_mask, audit_transform, params)
    plan.decisions = decisions
    plan.stats["gap_fill_regions"] = (
        len(gap_fills) + len(selected_gaps) + plan.stats.get("coverage_repairs", 0)
    )
    pattern = pe.EmbPattern()
    pattern.add_thread(params.thread_color)
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
                "schema_version": 1,
                "units": "0.1mm",
                "origin_mm": plan.origin_mm,
                "commands": plan.commands,
                "command_codes": {
                    "STITCH": pe.STITCH,
                    "JUMP": pe.JUMP,
                    "TRIM": pe.TRIM,
                    "END": pe.END,
                },
                "stats": plan.stats,
                "params": asdict(params),
                "warnings": plan.warnings,
                "decisions": plan.decisions,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return names, plan
