"""Choose stitch types from whole connected silhouettes, retaining useful MAT rails."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import distance_transform_edt, find_objects, label
from shapely import covers, intersection, linestrings, prepare
from shapely.geometry import GeometryCollection, LineString, Polygon
from shapely.ops import unary_union
from skimage.measure import find_contours
from svgelements import Matrix

from ..routing import route_columns
from ..rung_generator import _valid_rail_pieces
from ..svg_manager import UNITS_PER_MM
from .paths import _ordered_fill_paths
from .planner import UnstitchableRegion, build_stitch_plan
from .quality import measure_plan, satin_crowding


def _fill_angle(polygon, params):
    if not params.auto_fill_angle:
        return params.fill_angle_deg
    candidates = sorted({0.0, 30.0, 60.0, 90.0, float(params.fill_angle_deg) % 180})
    area = polygon.buffer(0.08)
    prepare(area)
    best, best_cost = candidates[0], float("inf")
    for angle in candidates:
        paths = _ordered_fill_paths(
            polygon,
            angle,
            max(1.0, params.fill_spacing_mm),
            4.0,
            params.trim_distance_mm,
            minimum=params.min_stitch_mm,
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
        polygon = Polygon(xy).buffer(0)
        if polygon.area >= 0.1:
            polygon = polygon.simplify(0.05, preserve_topology=True)
        shape = shape.symmetric_difference(polygon)
    polygons = [shape] if shape.geom_type == "Polygon" else list(shape.geoms)
    return [p for p in polygons if p.geom_type == "Polygon" and p.area >= minimum_area]


def _compact_detail(source, params):
    rectangle = np.asarray(source.minimum_rotated_rectangle.exterior.coords)
    vectors = np.diff(rectangle, axis=0)
    lengths = np.linalg.norm(vectors, axis=1)
    if source.area >= 0.15 or lengths.max() > 0.8:
        return None
    direction = vectors[np.argmax(lengths)] / lengths.max()
    center = np.asarray(source.representative_point().coords)[0]
    clipped = source.intersection(LineString([center - direction, center + direction]))
    pieces = [clipped] if clipped.geom_type == "LineString" else list(getattr(clipped, "geoms", []))
    lines = [piece for piece in pieces if piece.geom_type == "LineString"]
    if not lines:
        return None
    line = max(lines, key=lambda p: p.length)
    if line.length < params.min_stitch_mm - 0.12:
        return None
    points = np.asarray(line.coords)[[0, -1]]
    direction = (points[1] - points[0]) / line.length
    extension = max(0, (params.min_stitch_mm + 0.05 - line.length) / 2)
    points += np.array([-direction, direction]) * extension
    if not source.buffer(0.08).covers(LineString(points)):
        return None
    return {
        "type": "running",
        "points": points,
        "allowed_area": source.buffer(0.08),
        "minimum_detail_enlarged": extension > 0,
    }


def _linear_column(source, params):
    """Parallel cross-sections avoid unstable MAT fans on straight convex columns."""
    if (
        source.geom_type != "Polygon"
        or source.interiors
        or source.area / source.convex_hull.area < 0.98
    ):
        return None
    rectangle = np.asarray(source.minimum_rotated_rectangle.exterior.coords)
    vectors = np.diff(rectangle, axis=0)
    lengths = np.linalg.norm(vectors, axis=1)
    if lengths.max() / lengths.min() < 3 or lengths.min() > params.max_satin_width_mm:
        return None
    direction = vectors[np.argmax(lengths)] / lengths.max()
    normal = np.array([-direction[1], direction[0]])
    boundary = np.asarray(source.exterior.coords)
    low, high = (boundary @ direction).min(), (boundary @ direction).max()
    lateral = ((boundary @ normal).min() + (boundary @ normal).max()) / 2
    positions = np.linspace(low + 1e-6, high - 1e-6, max(3, int(np.ceil((high - low) / 0.2)) + 1))
    centers = positions[:, None] * direction + lateral * normal
    span = lengths.max() + lengths.min()
    cuts = intersection(
        source, linestrings(np.stack([centers - normal * span, centers + normal * span], axis=1))
    )
    pairs = [
        np.asarray(line.coords)[[0, -1]]
        for line in cuts
        if line.geom_type == "LineString" and line.length > 1e-6
    ]
    if len(pairs) < 2:
        return None
    a, b = np.asarray(pairs).transpose(1, 0, 2)
    reverse = (a @ normal) > (b @ normal)
    a[reverse], b[reverse] = b[reverse].copy(), a[reverse].copy()
    widths = np.linalg.norm(b - a, axis=1)
    # Raster bevels at flat caps must not turn into a dense needle fan.
    first = 1 if abs(widths[1] - widths[0]) > 0.5 else 0
    last = -1 if abs(widths[-1] - widths[-2]) > 0.5 else None
    a, b = a[first:last], b[first:last]
    if len(a) < 2:
        return None
    return {
        "type": "satin",
        "stitch_type": "satin",
        "rail_a": a,
        "rail_b": b,
        "allowed_area": source.buffer(params.pull_compensation_mm + 0.08),
    }


def select_stitch_types(elements, mask, transform, params, *, origin_mm=None):
    """Choose one top-layer strategy per connected region; never patch satin with fill."""
    minimum_width = max(
        2 * params.min_stitch_mm, {30: 0.75, 40: 0.6, 60: 0.45}[params.thread_weight]
    )
    labels, count = label(mask)
    slices = find_objects(labels)
    scale = UNITS_PER_MM * np.sqrt(abs(transform.a * transform.d - transform.b * transform.c))
    radii = distance_transform_edt(mask)
    groups = [[] for _ in range(count)]
    for element in elements:
        points = (
            np.asarray(element["points"])
            if element["type"] == "running"
            else (np.asarray(element["rail_a"]) + element["rail_b"]) / 2
        )
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
            groups[ids[positive][np.argmax(frequencies[positive])] - 1].append(element)
    chosen, decisions = [], []
    for i, bounds in enumerate(slices):
        if bounds is None:
            continue
        component = labels[bounds] == i + 1
        local_transform = transform * Matrix.translate(-bounds[1].start, -bounds[0].start)
        polygons = mask_polygons(component, local_transform, minimum_area=0.001)
        if not polygons:
            continue
        source = unary_union(polygons)
        width = float(radii[bounds][component].max() * 2 / scale)
        satin = []
        for element in groups[i]:
            if "rail_a" not in element:
                continue
            a, b = np.asarray(element["rail_a"]), np.asarray(element["rail_b"])
            for ra, rb, _ in _valid_rail_pieces(a, b, (a + b) / 2):
                if ra is not None:
                    satin.append(
                        {
                            "type": "satin",
                            "stitch_type": "satin",
                            "rail_a": ra,
                            "rail_b": rb,
                            "allowed_area": source.buffer(params.pull_compensation_mm + 0.08),
                        }
                    )
        areas = [Polygon(np.vstack([e["rail_a"], e["rail_b"][::-1]])).buffer(0) for e in satin]
        linear = _linear_column(source, params)
        if linear is not None:
            satin = [linear]
            areas = [Polygon(np.vstack([linear["rail_a"], linear["rail_b"][::-1]]))]
        covered = source.intersection(unary_union(areas)).area / source.area if areas else 0.0
        # Reserve compensation and rounding headroom so automatic satin does not
        # acquire split penetrations through its face at the machine length cap.
        float_limit = min(
            params.max_satin_width_mm, params.max_stitch_mm - 0.2 - 2 * params.pull_compensation_mm
        )
        wide = [
            area
            for e, area in zip(satin, areas, strict=True)
            if np.linalg.norm(e["rail_b"] - e["rail_a"], axis=1).max() > float_limit
        ]
        broad = source.intersection(unary_union(wide)).area / source.area if wide else 0.0
        method, reason, angle, candidates = "fill", "incomplete_or_broad_column", None, {}
        option = None
        detail = _compact_detail(source, params) if width < minimum_width else None
        if width < minimum_width and (groups[i] or detail is not None):
            running = [
                {
                    "type": "running",
                    "points": e["points"] if "points" in e else (e["rail_a"] + e["rail_b"]) / 2,
                    "allowed_area": source.buffer(0.08),
                }
                for e in groups[i]
            ]
            if detail is not None:
                running = [detail]
            try:
                candidate = build_stitch_plan(route_columns(running), params, origin_mm=origin_mm)
                metrics, _ = measure_plan(
                    candidate,
                    np.pad(component, 3),
                    scale,
                    np.array([local_transform.e, local_transform.f]) + 3,
                )
                candidates["running"] = metrics
                if metrics["structural_coverage"] >= 0.999 and metrics["largest_gap_mm2"] <= 0.05:
                    option, method, reason = running, "running", "below_satin_width"
                else:
                    reason = "running_top_layer_incomplete"
            except ValueError as exc:
                candidates["running"] = {"error": str(exc)}
                reason = "running_geometry_rejected"
        # Auto satin must fit throughout the column. A percentile can conceal a
        # broad cap whose long floats snag, even when most of the column is narrow.
        elif satin and covered >= 0.9 and not wide:
            try:
                ordered = route_columns(satin)
                candidate = build_stitch_plan(ordered, params, origin_mm=origin_mm)
                metrics, _ = measure_plan(
                    candidate,
                    np.pad(component, 3),
                    scale,
                    np.array([local_transform.e, local_transform.f]) + 3,
                )
                candidates["satin"] = metrics
                metrics["crowded_satin_penetrations"] = satin_crowding(
                    candidate, params.min_stitch_mm
                )
                reverse = [
                    {**e, "rail_a": e["rail_a"][::-1], "rail_b": e["rail_b"][::-1]}
                    for e in ordered[::-1]
                ]
                reversed_plan = build_stitch_plan(reverse, params, origin_mm=origin_mm)
                reverse_metrics, _ = measure_plan(
                    reversed_plan,
                    np.pad(component, 3),
                    scale,
                    np.array([local_transform.e, local_transform.f]) + 3,
                )
                reverse_metrics["crowded_satin_penetrations"] = satin_crowding(
                    reversed_plan, params.min_stitch_mm
                )
                metrics["reverse"] = reverse_metrics
                if (
                    metrics["structural_coverage"] >= 0.999
                    and metrics["largest_gap_mm2"] <= 0.05
                    and candidate.stats["unsafe_connections"] == 0
                    and metrics["crowded_satin_penetrations"] == 0
                    and reverse_metrics["crowded_satin_penetrations"] == 0
                    and reverse_metrics["structural_coverage"] >= 0.999
                    and reverse_metrics["largest_gap_mm2"] <= 0.05
                    and reversed_plan.stats["unsafe_connections"] == 0
                ):
                    option, method, reason = satin, "satin", "complete_regular_column"
                else:
                    reason = "satin_top_layer_incomplete"
            except ValueError as exc:
                candidates["satin"] = {"error": str(exc)}
                reason = "satin_geometry_rejected"
        if option is None:
            angle = _fill_angle(source, params)
            option = [
                {
                    "type": "fill",
                    "polygon": polygon,
                    "compensation": min(
                        params.pull_compensation_mm,
                        0.15 * polygon.area / max(polygon.length, 0.001),
                    ),
                    "fill_angle_deg": angle,
                }
                for polygon in polygons
            ]
            try:
                candidate = build_stitch_plan(route_columns(option), params, origin_mm=origin_mm)
                metrics, _ = measure_plan(
                    candidate,
                    np.pad(component, 3),
                    scale,
                    np.array([local_transform.e, local_transform.f]) + 3,
                )
                if metrics["structural_coverage"] < 0.9999 or metrics["largest_gap_mm2"] > 0.01:
                    option = [{**e, "finish_inset": 0.0} for e in option]
                candidates["fill"] = metrics
            except UnstitchableRegion as exc:
                candidates["fill"] = {"error": str(exc)}
                option, method, reason = [], "omitted", "below_machine_resolution"
        chosen.extend(option)
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
                "minimum_detail_enlarged": any(
                    e.get("minimum_detail_enlarged", False) for e in option
                ),
            }
        )
    return route_columns(chosen), decisions
