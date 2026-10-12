"""Safe travel, locks, quantization and machine command invariants."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pyembroidery as pe
from shapely import covers, linestrings, prepare
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from .params import StitchParams
from .paths import _ordered_fill_paths, _safe_pieces, _subdivide, resample_running, satin_points


@dataclass
class StitchBlock:
    kind: str
    points: np.ndarray
    region: int


@dataclass
class StitchPlan:
    # Integer tenths of a millimetre, exactly as sent to the writers.
    commands: list[list[int]]
    blocks: list[StitchBlock]
    origin_mm: tuple[float, float]
    stats: dict[str, float | int]
    warnings: list[str] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)


def _make_blocks(elements, params):
    blocks, areas, rejected, point_count = [], [], 0, 0
    for region, element in enumerate(elements):
        paths = []
        if element["type"] == "running":
            points = np.asarray(element["points"], dtype=float)
            area = element.get("allowed_area", LineString(points).buffer(0.25))
            paths.append(
                (
                    "running",
                    resample_running(points, min(params.running_length_mm, params.max_stitch_mm)),
                )
            )
        else:
            is_gap = element["type"] == "fill"
            if is_gap:
                polygon = element["polygon"]
                angle = element.get("fill_angle_deg", params.fill_angle_deg)
                wide = True
            else:
                a, b = np.asarray(element["rail_a"]), np.asarray(element["rail_b"])
                polygon = Polygon(np.vstack([a, b[::-1]]))
                angle = params.fill_angle_deg
                wide = np.linalg.norm(b - a, axis=1).max() > params.max_satin_width_mm
            if not polygon.is_valid or polygon.area <= 0:
                raise ValueError("Invalid paired rails in direct stitch input.")
            compensation = element.get(
                "compensation", 0.0 if is_gap else params.pull_compensation_mm
            )
            area = polygon.buffer(compensation + 0.08)
            if is_gap or (
                wide and params.wide_mode == "fill" and element.get("stitch_type") != "satin"
            ):
                fill_area = polygon.buffer(compensation)
                if element.get("underlay", params.underlay):
                    paths.extend(
                        ("underlay", p)
                        for p in _ordered_fill_paths(
                            polygon,
                            angle + 90,
                            3.0,
                            min(params.running_length_mm, params.max_stitch_mm),
                            params.trim_distance_mm,
                        )
                    )
                paths.extend(
                    ("fill", p)
                    for p in _ordered_fill_paths(
                        fill_area,
                        angle,
                        params.fill_spacing_mm,
                        min(params.fill_length_mm, params.max_stitch_mm) * 0.9,
                        params.trim_distance_mm,
                    )
                )
            else:
                if params.underlay:
                    centers = (a + b) / 2
                    paths.append(
                        ("underlay", resample_running(centers, min(2.0, params.max_stitch_mm)))
                    )
                    if np.linalg.norm(b - a, axis=1).max() >= 3:
                        paths.append(
                            ("underlay", satin_points(a[::-1], b[::-1], params, underlay=True))
                        )
                paths.append(("satin", satin_points(a, b, params)))
        areas.append(area)
        for kind, points in paths:
            points = _subdivide(points, params.max_stitch_mm)
            pieces, bad = _safe_pieces(points, area)
            rejected += bad
            blocks.extend(StitchBlock(kind, p, region) for p in pieces)
            point_count += sum(len(p) for p in pieces)
            if point_count > params.max_stitches:
                raise ValueError("Stitch budget exceeded; simplify the design or increase spacing.")
    return blocks, areas, rejected


def build_stitch_plan(elements, params: StitchParams | None = None) -> StitchPlan:
    """Plan a monochrome design with safe travel, locks, trims and bounded stitches."""
    params = params or StitchParams()
    params.validate()
    if not elements:
        raise ValueError("No direct stitches could be generated.")
    extents = np.vstack(
        [
            np.asarray(e["polygon"].exterior.coords)
            if e["type"] == "fill"
            else np.asarray(e["points"], dtype=float)
            if e["type"] == "running"
            else np.vstack([e["rail_a"], e["rail_b"]])
            for e in elements
        ]
    )
    if not np.isfinite(extents).all():
        raise ValueError("Stitch coordinates must be finite.")
    if np.any(np.ptp(extents, axis=0) > [params.hoop_width_mm, params.hoop_height_mm]):
        raise ValueError(
            "Design exceeds the configured hoop; resize the SVG or choose a larger hoop."
        )
    blocks, areas, rejected = _make_blocks(elements, params)
    if not blocks:
        raise ValueError("No direct stitches could be generated.")
    all_points = np.vstack([b.points for b in blocks])
    low, high = all_points.min(axis=0), all_points.max(axis=0)
    size = high - low
    if np.any(size > [params.hoop_width_mm, params.hoop_height_mm]):
        raise ValueError(
            f"Design is {size[0]:.1f} × {size[1]:.1f} mm; it exceeds the {params.hoop_width_mm:g} × {params.hoop_height_mm:g} mm hoop. Resize the SVG or choose a larger hoop."
        )
    origin = (low + high) / 2
    commands, rendered = [], []
    allowed = unary_union(areas)
    prepare(allowed)
    quantized_position = np.array([0, 0], dtype=int)

    def append(command, point):
        nonlocal quantized_position
        xy = (
            quantized_position.copy()
            if command in (pe.TRIM, pe.END)
            else np.rint((point - origin) * 10).astype(int)
        )
        if command == pe.STITCH and commands and commands[-1][2] == pe.STITCH:
            if np.linalg.norm(xy - quantized_position) < params.min_stitch_mm * 10 - 0.01:
                return
        commands.append([int(xy[0]), int(xy[1]), command])
        quantized_position = xy
        if len(commands) > params.max_stitches:
            raise ValueError("Stitch budget exceeded; simplify the design or increase spacing.")

    def lock(points, start, region):
        if len(points) < 2:
            return
        endpoint = points[0] if start else points[-1]
        direction = (points[1] - endpoint) if start else (points[-2] - endpoint)
        length = np.linalg.norm(direction)
        if length < 0.6:
            return
        direction /= length
        begin = len(commands) - 1
        for length in (0.6, 0.3, 0):
            append(pe.STITCH, endpoint + direction * length)
        rendered.append(
            StitchBlock(
                "lock", np.asarray([c[:2] for c in commands[begin:]], dtype=float) / 10, region
            )
        )

    current = None
    current_block = None
    for block in blocks:
        points = block.points
        first = points[0]
        distance = float(np.linalg.norm(first - current)) if current is not None else math.inf
        if current is None or distance > 0.1:
            travel_limit = params.trim_distance_mm
            if (
                current_block is not None
                and current_block.kind == block.kind == "underlay"
                and current_block.region == block.region
                and travel_limit > 0
            ):
                # These connectors are covered by the later top layer of this region.
                travel_limit = max(travel_limit, 2 * params.running_length_mm)
            travel_area = (
                areas[block.region]
                if current_block is not None and current_block.region == block.region
                else allowed
            )
            connected = (
                current is not None
                and distance <= travel_limit
                and travel_area.covers(LineString([current, first]))
            )
            if connected:
                connector = _subdivide(
                    np.asarray([current, first]),
                    min(params.running_length_mm, params.max_stitch_mm),
                )
                begin = len(commands)
                for point in connector[1:]:
                    append(pe.STITCH, point)
                rendered.append(
                    StitchBlock(
                        "travel",
                        np.asarray([c[:2] for c in commands[begin - 1 :]], dtype=float) / 10,
                        block.region,
                    )
                )
            else:
                if current is not None:
                    lock(current_block.points, False, current_block.region)
                    append(pe.TRIM, current)
                start = origin if current is None else current
                for point in _subdivide(np.asarray([start, first]), 12.0)[1:]:
                    append(pe.JUMP, point)
                if not commands or commands[-1][2] != pe.JUMP:
                    append(pe.JUMP, first)
                append(pe.STITCH, first)
                lock(points, True, block.region)
        begin = len(commands)
        for point in points:
            append(pe.STITCH, point)
        if len(commands) > begin:
            rendered.append(
                StitchBlock(
                    block.kind,
                    np.asarray([c[:2] for c in commands[max(0, begin - 1) :]], dtype=float) / 10,
                    block.region,
                )
            )
        current, current_block = quantized_position / 10 + origin, block
    lock(current_block.points, False, current_block.region)
    append(pe.TRIM, current)
    append(pe.END, current)
    array = np.asarray(commands)
    stitched_coordinates = array[array[:, 2] == pe.STITCH, :2]
    size = np.ptp(stitched_coordinates, axis=0) / 10
    if np.any(size > [params.hoop_width_mm, params.hoop_height_mm]):
        raise ValueError("Quantized stitch dimensions exceed the configured hoop.")
    # Consecutive STITCH commands are sew segments; JUMP→STITCH is a first penetration.
    lengths = np.linalg.norm(np.diff(array[:, :2], axis=0), axis=1) / 10
    sewn = (array[1:, 2] == pe.STITCH) & (array[:-1, 2] == pe.STITCH)
    jumps = array[1:, 2] == pe.JUMP
    if np.any(lengths[sewn] > params.max_stitch_mm + 0.001):
        raise ValueError("A planned stitch exceeds max_stitch_mm.")
    physical_segments = np.stack([array[:-1, :2], array[1:, :2]], axis=1)[sewn] / 10 + origin
    quantized_area = allowed.buffer(0.08)
    prepare(quantized_area)
    if not covers(quantized_area, linestrings(physical_segments)).all():
        raise ValueError(
            "Quantized stitches leave their regions; simplify sharp corners or reduce the minimum stitch length."
        )
    warnings = []
    if rejected:
        warnings.append(
            f"{rejected} unsafe stitch connections were split into separate runs; inspect corners in the preview."
        )
    stats = {
        "stitches": int(np.count_nonzero(array[:, 2] == pe.STITCH)),
        "jumps": int(np.count_nonzero(array[:, 2] == pe.JUMP)),
        "trims": int(np.count_nonzero(array[:, 2] == pe.TRIM)),
        "satin_regions": len({b.region for b in blocks if b.kind == "satin"}),
        "fill_regions": len({b.region for b in blocks if b.kind == "fill"}),
        "running_regions": len({b.region for b in blocks if b.kind == "running"}),
        "underlay_stitches": sum(len(b.points) for b in rendered if b.kind == "underlay"),
        "thread_length_mm": round(float(lengths[sewn].sum()), 1),
        "jump_length_mm": round(float(lengths[jumps].sum()), 1),
        "max_stitch_mm": round(float(lengths[sewn].max(initial=0)), 2),
        "short_stitches": int(np.count_nonzero(lengths[sewn] < params.min_stitch_mm - 0.08)),
        "width_mm": round(float(size[0]), 2),
        "height_mm": round(float(size[1]), 2),
        "unsafe_connections": rejected,
    }
    return StitchPlan(commands, rendered, tuple(origin), stats, warnings)
