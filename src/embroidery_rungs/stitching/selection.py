"""Choose stitch types from whole connected silhouettes, retaining useful MAT rails."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import distance_transform_edt, find_objects, label
from shapely import covers, linestrings, prepare
from shapely.geometry import GeometryCollection, LineString, Polygon
from shapely.ops import unary_union
from skimage.measure import find_contours
from svgelements import Matrix

from ..routing import route_columns
from ..rung_generator import _valid_rail_pieces
from ..svg_manager import UNITS_PER_MM
from .paths import _ordered_fill_paths
from .planner import build_stitch_plan
from .quality import measure_stitches


def _fill_angle(polygon, params):
    if not params.auto_fill_angle:
        return params.fill_angle_deg
    candidates = sorted({0.0, 30.0, 60.0, 90.0, float(params.fill_angle_deg) % 180})
    area = polygon.buffer(0.08)
    prepare(area)
    best, best_cost = candidates[0], float("inf")
    for angle in candidates:
        paths = _ordered_fill_paths(
            polygon, angle, max(1.0, params.fill_spacing_mm), 4.0, params.trim_distance_mm
        )
        if len(paths) < 2:
            continue
        connectors = np.array([[a[-1], b[0]] for a, b in zip(paths[:-1], paths[1:], strict=True)])
        distances = np.linalg.norm(connectors[:, 1] - connectors[:, 0], axis=1)
        safe = covers(area, linestrings(connectors)) & (distances <= params.trim_distance_mm)
        cost = np.count_nonzero(~safe) * 25 + distances.sum()
        if cost < best_cost:
            best, best_cost = angle, cost
    return best


def mask_polygons(mask, transform, minimum_area=0.1):
    inverse = ~transform
    matrix = np.array([[inverse.a, inverse.b], [inverse.c, inverse.d]]) / UNITS_PER_MM
    offset = np.array([inverse.e, inverse.f]) / UNITS_PER_MM
    shape = GeometryCollection()
    for contour in find_contours(np.pad(mask, 1), 0.5):
        xy = (contour[:, ::-1] - 1) @ matrix + offset
        polygon = Polygon(xy).buffer(0).simplify(0.05, preserve_topology=True)
        shape = shape.symmetric_difference(polygon)
    polygons = [shape] if shape.geom_type == "Polygon" else list(shape.geoms)
    return [p for p in polygons if p.geom_type == "Polygon" and p.area >= minimum_area]


def select_stitch_types(elements, mask, transform, params):
    """Explainable geometry heuristics, not a prediction of physical sew-out quality."""
    minimum_width = max(
        2 * params.min_stitch_mm, {30: 0.75, 40: 0.6, 60: 0.45}[params.thread_weight]
    )
    fine_elements = []
    for element in elements:
        if element["type"] != "running" or "rail_a" not in element:
            fine_elements.append(element)
            continue
        a, b = np.asarray(element["rail_a"]), np.asarray(element["rail_b"])
        if np.median(np.linalg.norm(b - a, axis=1)) < minimum_width:
            fine_elements.append(element)
            continue
        for ra, rb, centers in _valid_rail_pieces(a, b, (a + b) / 2):
            fine_elements.append(
                {"type": "running", "points": centers}
                if ra is None
                else {"type": "satin", "rail_a": ra, "rail_b": rb}
            )
    elements = fine_elements
    labels, count = label(mask)
    slices = find_objects(labels)
    scale = UNITS_PER_MM * np.sqrt(abs(transform.a * transform.d - transform.b * transform.c))
    radii = distance_transform_edt(mask)
    groups = [[] for _ in range(count)]
    orphaned = []
    for element in elements:
        points = (
            np.asarray(element["points"])
            if element["type"] == "running"
            else (np.asarray(element["rail_a"]) + element["rail_b"]) / 2
        )
        # Forward affine transform maps physical millimetres into the cropped mask.
        pixels = np.rint(
            points
            * UNITS_PER_MM
            @ np.array([[transform.a, transform.b], [transform.c, transform.d]])
            + [transform.e, transform.f]
        ).astype(int)
        pixels[:, 0] = pixels[:, 0].clip(0, mask.shape[1] - 1)
        pixels[:, 1] = pixels[:, 1].clip(0, mask.shape[0] - 1)
        ids, frequencies = np.unique(labels[pixels[:, 1], pixels[:, 0]], return_counts=True)
        positive = ids > 0
        if positive.any():
            region = ids[positive][np.argmax(frequencies[positive])]
            groups[region - 1].append(element)
        else:
            orphaned.append(element)
    chosen, decisions, filled_ids = [], [], []
    for i, bounds in enumerate(slices):
        if bounds is None:
            continue
        component = labels[bounds] == i + 1
        # Translate the cropped component's coordinates before vectorization.
        local_transform = transform * Matrix.translate(-bounds[1].start, -bounds[0].start)
        polygons = mask_polygons(component, local_transform)
        if not polygons:
            chosen.extend(groups[i])
            continue
        source = unary_union(polygons)
        prepare(source)
        width = float(radii[bounds][component].max() * 2 / scale)
        areas, wide_areas = [], []
        for element in groups[i]:
            if element["type"] == "running":
                areas.append(LineString(element["points"]).buffer(0.15))
            else:
                a, b = np.asarray(element["rail_a"]), np.asarray(element["rail_b"])
                polygon = Polygon(np.vstack([a, b[::-1]])).buffer(0)
                areas.append(polygon)
                if np.percentile(np.linalg.norm(b - a, axis=1), 75) > params.max_satin_width_mm:
                    wide_areas.append(polygon)
        covered = source.intersection(unary_union(areas)).area / source.area if areas else 0.0
        broad = (
            source.intersection(unary_union(wide_areas)).area / source.area if wide_areas else 0.0
        )
        rectangle = np.asarray(source.minimum_rotated_rectangle.exterior.coords)
        sides = np.linalg.norm(np.diff(rectangle, axis=0), axis=1)
        aspect = float(sides.max() / max(sides.min(), 1e-6))
        tapered_column = aspect >= 3 and covered >= 0.97 and width <= 2 * params.max_satin_width_mm
        fill = width >= minimum_width and (
            covered < 0.9 or (broad > 0.2 and not tapered_column) or not groups[i]
        )
        angle = None
        candidates = {}
        if fill:
            angle = _fill_angle(source, params)
            fill_elements = [
                {
                    "type": "fill",
                    "polygon": polygon,
                    "compensation": min(params.pull_compensation_mm, width * 0.1),
                    "fill_angle_deg": angle,
                }
                for polygon in polygons
            ]
            satin_elements = [{**e, "stitch_type": "satin"} for e in groups[i]]
            satin_gaps = []
            if params.fill_gaps:
                missing = source.difference(unary_union(areas))
                pieces = [missing] if missing.geom_type == "Polygon" else list(missing.geoms)
                satin_gaps = [
                    {
                        "type": "fill",
                        "polygon": piece,
                        "gap_fill": True,
                        "underlay": False,
                        "fill_angle_deg": angle,
                    }
                    for piece in pieces
                    if piece.geom_type == "Polygon" and piece.area >= 0.5
                ]
                satin_elements = satin_gaps + satin_elements
            for name, option in (("satin", satin_elements), ("fill", fill_elements)):
                if not option:
                    continue
                try:
                    plan = build_stitch_plan(option, params)
                    metrics, _ = measure_stitches(
                        plan.commands,
                        plan.origin_mm,
                        np.pad(component, 3),
                        scale,
                        np.array([local_transform.e, local_transform.f]) + 3,
                    )
                    cost = (
                        10 * (1 - metrics["structural_coverage"])
                        + max(0, metrics["spill_mm2"] / source.area - 0.08)
                        + 0.01 * metrics["trims"]
                        + 0.000002 * metrics["stitches"]
                        + 0.003 * plan.stats["unsafe_connections"]
                    )
                    candidates[name] = {**metrics, "cost": round(cost, 6)}
                except ValueError as exc:
                    candidates[name] = {"error": str(exc)}
            eligible = [name for name, metrics in candidates.items() if "cost" in metrics]
            if not eligible:
                details = "; ".join(
                    f"{name}: {m.get('error', '')}" for name, m in candidates.items()
                )
                raise ValueError(
                    f"Neither satin nor fill produced a valid plan for a source region. {details}"
                )
            best_coverage = max(candidates[name]["structural_coverage"] for name in eligible)
            faithful = [
                name
                for name in eligible
                if candidates[name]["structural_coverage"] >= best_coverage - 0.0025
            ]
            method = min(faithful, key=lambda name: candidates[name]["cost"])
            fill = method == "fill"
            chosen.extend(fill_elements if fill else satin_elements)
            if fill or satin_gaps:
                filled_ids.append(i + 1)
            reason = "sampled_stitch_quality"
        else:
            # A short, locally wide rung at a corner does not make a whole narrow
            # column a fill. Bounded split satin handles those occasional rungs.
            chosen.extend({**e, "stitch_type": "satin"} for e in groups[i])
            method = "satin" if any(e["type"] == "satin" for e in groups[i]) else "running"
            reason = "paired_rails" if method == "satin" else "thin_stroke"
        decisions.append(
            {
                "component": i + 1,
                "method": method,
                "reason": reason,
                "width_mm": round(width, 2),
                "area_mm2": round(source.area, 2),
                "mat_coverage": round(covered, 4),
                "broad_fraction": round(broad, 4),
                "fill_angle_deg": angle,
                "candidates": candidates,
            }
        )
    chosen.extend(orphaned)
    return route_columns(chosen), decisions, np.isin(labels, filled_ids)
