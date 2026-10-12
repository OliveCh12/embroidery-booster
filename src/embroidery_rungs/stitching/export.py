"""Export and preview the direct plan without desktop embroidery software."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pyembroidery as pe

from ..image_processor import render_preview
from ..svg_manager import UNITS_PER_MM
from .digitizer import digitize
from .params import MACHINE_PROFILES, StitchParams
from .planner import StitchPlan


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
    analysis: dict = field(default_factory=dict)
    requested_params: dict = field(default_factory=dict)
    adjustments: list[dict] = field(default_factory=list)


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


def export_direct(svg, stage: Path, stem: str, params: StitchParams, *, input_analysis=None):
    started = time.perf_counter()
    plan, layers = digitize(svg, params)
    params = plan.params
    pattern = pe.EmbPattern()
    for color in plan.threads:
        pattern.add_thread(color)
    pattern.extras["name"] = stem[:16]
    pattern.extras["comments"] = "Embroidery Booster automatic direct stitch plan"
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
    coordinates = np.asarray(plan.commands)
    sewn = coordinates[coordinates[:, 2] == pe.STITCH, :2]
    first_stitch = int(np.flatnonzero(coordinates[:, 2] == pe.STITCH)[0])
    machine = MACHINE_PROFILES[params.machine]
    speed = machine["stitches_per_minute"]
    runs = [
        {
            "start": b.command_range[0],
            "end": b.command_range[1],
            "color_index": b.color_index,
            "kind": b.kind,
            "region": b.region,
        }
        for b in plan.blocks
        if b.command_range is not None
    ]
    # The first node of a run is its previous-position context, not an extra
    # penetration. This ledger separates actual cover stitches from support
    # and connections without counting overlapping run anchors twice.
    phase_names = ("entry", "top", "underlay", "travel", "lock")
    phases = np.zeros(len(coordinates), dtype=np.uint8)
    for run in runs:
        phase = "top" if run["kind"] in ("satin", "fill", "running") else run["kind"]
        phases[run["start"] + 1 : run["end"]] = phase_names.index(phase)
    needle = coordinates[:, 2] == pe.STITCH
    plan.analysis["stitch_breakdown"] = {
        name: int(np.count_nonzero(needle & (phases == i))) for i, name in enumerate(phase_names)
    }
    (stage / names[4]).write_text(
        json.dumps(
            {
                "schema_version": 3,
                "units": "0.1mm",
                "coordinate_frame": "hoop_center",
                "origin_mm": plan.origin_mm,
                "commands": plan.commands,
                "command_codes": {
                    "stitch": pe.STITCH,
                    "jump": pe.JUMP,
                    "trim": pe.TRIM,
                    "end": pe.END,
                    "color_change": pe.COLOR_CHANGE,
                    "command_mask": pe.COMMAND_MASK,
                },
                "hoop": {
                    "width_mm": params.hoop_width_mm,
                    "height_mm": params.hoop_height_mm,
                    "bounds_mm": [
                        -params.hoop_width_mm / 2,
                        -params.hoop_height_mm / 2,
                        params.hoop_width_mm / 2,
                        params.hoop_height_mm / 2,
                    ],
                },
                "machine_bounds_mm": [*(sewn.min(axis=0) / 10), *(sewn.max(axis=0) / 10)],
                "machine": {
                    "profile": params.machine,
                    "min_stitch_mm": params.min_stitch_mm,
                    "max_stitch_mm": params.max_stitch_mm,
                    "max_jump_mm": 12,
                    "stitches_per_minute": speed,
                    "speed_source": "machine_profile"
                    if params.machine != "generic"
                    else "simulation_assumption",
                },
                "playback": {
                    "command_count": len(plan.commands),
                    "stitch_count": plan.stats["stitches"],
                    "color_changes": plan.stats["color_changes"],
                    "jumps": plan.stats["jumps"],
                    "first_stitch_index": first_stitch,
                    "first_point_units": plan.commands[first_stitch][:2],
                    "stitch_time_seconds": round(60 * plan.stats["stitches"] / speed, 1),
                    "timing_basis": "needle_cycles_only",
                },
                "stats": plan.stats,
                "params": asdict(params),
                "requested_params": plan.requested_params,
                "adjustments": plan.adjustments,
                "analysis": plan.analysis,
                "input_analysis": input_analysis or {},
                "warnings": plan.warnings,
                "decisions": plan.decisions,
                "threads": plan.threads,
                "layers": layers,
                "runs": runs,
                "top_layer_runs": [b for b in runs if b["kind"] in ("satin", "fill", "running")],
                "underlay_runs": [b for b in runs if b["kind"] == "underlay"],
                "coverage_tolerance_mm": 0.25,
                "thread_model_mm": 0.3,
                "coverage_basis": "quantized_top_layer",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return names, plan
