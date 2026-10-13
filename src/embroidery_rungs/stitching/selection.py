"""Choose stitch types from whole connected silhouettes, retaining useful MAT rails."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import distance_transform_edt, find_objects, label
from shapely import intersection, linestrings
from shapely.geometry import GeometryCollection, LineString, Polygon
from shapely.ops import unary_union
from skimage.measure import find_contours
from svgelements import Matrix

from ..routing import route_columns
from ..svg_manager import UNITS_PER_MM
from .planner import CandidateGeometryError, UnstitchableRegion, build_stitch_plan
from .quality import coverage_needs_review, measure_plan, satin_crowding
from .rails import _valid_rail_pieces


def _fill_angle(polygon, params):
    if not params.auto_fill_angle:
        return params.fill_angle_deg
    # Filled-area moments describe the whole region, including its holes. Unlike
    # sampling travel at a fixed row pitch, they do not change with its size,
    # position, contour start vertex or the machine's stitch grid.
    center = np.asarray(polygon.centroid.coords)[0]
    moment = np.zeros((2, 2))
    pieces = [polygon] if polygon.geom_type == "Polygon" else polygon.geoms
    for piece in pieces:
        for index, ring in enumerate((piece.exterior, *piece.interiors)):
            points = np.asarray(ring.coords) - center
            x, y = points[:-1].T
            nx, ny = points[1:].T
            cross = x * ny - nx * y
            # SVG/Shapely rings need not share winding; interiors always subtract.
            cross *= np.sign(cross.sum()) * (1 if index == 0 else -1)
            xx = np.sum(cross * (x * x + x * nx + nx * nx)) / 12
            yy = np.sum(cross * (y * y + y * ny + ny * ny)) / 12
            xy = np.sum(cross * (2 * x * y + x * ny + nx * y + 2 * nx * ny)) / 24
            moment += [[xx, xy], [xy, yy]]
    values, vectors = np.linalg.eigh(moment / polygon.area)
    if values[1] <= 1.2 * values[0]:
        # Near-round regions have no meaningful preferred direction. Keeping the
        # configured angle avoids arbitrary changes from tiny boundary noise.
        return float(params.fill_angle_deg) % 180
    direction = vectors[:, 1]
    angle = np.degrees(np.arctan2(direction[1], direction[0])) % 180
    # Regular 15° bands stabilize antialiased boundaries. The bands are closed
    # under the quarter turns/reflections used by corresponding region frames.
    return float(np.rint(angle / 15) * 15 % 180)


def fill_elements(polygons, angle, params, *, finish_inset=0.12):
    return [
        {
            "type": "fill",
            "polygon": polygon,
            "compensation": min(
                params.pull_compensation_mm,
                0.15 * polygon.area / max(polygon.length, 0.001),
            ),
            "fill_angle_deg": angle,
            "finish_inset": finish_inset,
        }
        for polygon in polygons
    ]


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
    # Two rounded endpoints can lose up to sqrt(2) * 0.1 mm along their chord.
    # Reserve that headroom, still bounded to 0.08 mm per end; the candidate is
    # then checked on the real grid rather than exporting a lone penetration.
    extension = min(0.08, max(0, (params.min_stitch_mm + np.sqrt(2) * 0.1 - line.length) / 2))
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
    if lengths.max() / lengths.min() < 3:
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
    # Keep a full cap close to the contour: dropping the raster bevel without
    # extending the next section leaves a visible triangular gap on broad rails.
    for index, position in ((0, low + 0.04), (-1, high - 0.04)):
        if (index == 0 and first) or (index == -1 and last):
            a[index] += direction * (position - a[index] @ direction)
            b[index] += direction * (position - b[index] @ direction)
    return {
        "type": "satin",
        "stitch_type": "satin",
        "rail_a": a,
        "rail_b": b,
        "allowed_area": source.buffer(params.pull_compensation_mm + 0.08),
    }


def _split_columns(elements, float_limit, params):
    """Divide a broad rail sweep into adjacent columns, retaining its outer rails."""
    column_limit = max(float_limit / 2, float_limit - 0.2 - 2 * params.pull_compensation_mm)
    result = []
    for element in elements:
        a, b = element["rail_a"], element["rail_b"]
        vectors = b - a
        widths = np.linalg.norm(vectors, axis=1)
        # Compensation already separates the neighbouring seam penetrations.
        # With compensation disabled, a small overlap keeps the seam sewable.
        overlap = max(0.0, params.min_stitch_mm / 2 - params.pull_compensation_mm)
        count = max(1, int(np.ceil(widths.max() / (column_limit - 2 * overlap))))
        if count == 1:
            result.append(element)
            continue
        directions = vectors / np.maximum(widths[:, None], 1e-8)
        centers = (a + b) / 2
        progress = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(centers, axis=0), axis=1))]
        amplitude = np.minimum.reduce(
            [
                np.full(len(widths), 0.3),
                np.maximum(0, (column_limit - widths / count - 2 * overlap) / 4),
                widths / (count * 6),
            ]
        )
        if LineString(centers).hausdorff_distance(LineString(centers[[0, -1]])) > 0.15:
            amplitude[:] = 0
        seams = [a]
        for index in range(1, count):
            # Shared staggered seams avoid a straight row of split needle holes.
            displacement = amplitude * np.sin(
                progress * 2 * np.pi / max(3.2, 8 * params.satin_spacing_mm) + index * np.pi / 3
            )
            seams.append(a + vectors * index / count + directions * displacement[:, None])
        seams.append(b)
        for index in range(count):
            left, right = seams[index], seams[index + 1]
            local_overlap = np.minimum(overlap, widths / (count * 4))[:, None]
            if index:
                left = left - directions * local_overlap
            if index + 1 < count:
                right = right + directions * local_overlap
            result.append(
                {
                    **element,
                    "rail_a": left,
                    "rail_b": right,
                    "split_columns": count,
                }
            )
    return result


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
        linear = _linear_column(source, params) if params.stitch_type in ("auto", "satin") else None
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
        split_count = 0
        if wide and (
            params.stitch_type == "satin"
            or (
                params.stitch_type == "auto"
                and (linear is not None or source.area / max(width**2, 1e-6) >= 3)
                and all(
                    np.linalg.norm(e["rail_b"] - e["rail_a"], axis=1).max() <= 2 * float_limit
                    for e in satin
                )
            )
        ):
            satin = _split_columns(satin, float_limit, params)
            split_count = sum("split_columns" in e for e in satin)
            wide = []
        method, reason, angle, candidates = "fill", "incomplete_or_broad_column", None, {}
        option = None
        detail = _compact_detail(source, params) if width < minimum_width else None
        if params.stitch_type == "running" or (
            params.stitch_type == "auto"
            and width < minimum_width
            and (groups[i] or detail is not None)
        ):
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
            running_contour = False
            if params.stitch_type == "running" and (width >= minimum_width or not running):
                running_contour = True
                running = [
                    {
                        "type": "running",
                        "points": np.asarray(ring.coords),
                        "allowed_area": source.buffer(0.08),
                    }
                    for polygon in polygons
                    for ring in (polygon.exterior, *polygon.interiors)
                ]
            try:
                running = route_columns(running)
                candidate = build_stitch_plan(running, params, origin_mm=origin_mm)
                metrics, _ = measure_plan(
                    candidate,
                    np.pad(component, 3),
                    scale,
                    np.array([local_transform.e, local_transform.f]) + 3,
                )
                candidates["running"] = metrics
                if params.stitch_type == "running" or (not coverage_needs_review(metrics)):
                    option, method, reason = (
                        running,
                        "running",
                        (
                            "requested_running_contour"
                            if running_contour
                            else "requested_running_centerline"
                            if params.stitch_type == "running"
                            else "below_satin_width"
                        ),
                    )
                else:
                    reason = "running_top_layer_incomplete"
            except ValueError as exc:
                candidates["running"] = {"error": str(exc)}
                reason = "running_geometry_rejected"
            if params.stitch_type == "running" and option is None:
                option, method, reason = [], "omitted", "below_machine_resolution"
        # Auto satin must fit throughout the column. A percentile can conceal a
        # broad cap whose long floats snag, even when most of the column is narrow.
        elif (
            params.stitch_type in ("auto", "satin")
            and width >= minimum_width
            and satin
            and covered >= 0.9
            and not wide
        ):
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
                if (
                    not coverage_needs_review(metrics)
                    and candidate.stats["unsafe_connections"] == 0
                    and metrics["crowded_satin_penetrations"] == 0
                ):
                    option, method, reason = (
                        ordered,
                        "satin",
                        "complete_split_columns" if split_count else "complete_regular_column",
                    )
                else:
                    reason = "satin_top_layer_incomplete"
            except ValueError as exc:
                candidates["satin"] = {"error": str(exc)}
                reason = "satin_geometry_rejected"
        if option is None:
            if params.stitch_type == "satin":
                failure = (
                    f"the detail is thinner than the minimum sewable satin width {minimum_width:.2f} mm"
                    if width < minimum_width
                    else "the rail geometry leaves uncovered areas"
                    if covered < 0.9
                    else "the machine stitches leave uncovered areas or crowded penetrations"
                    if reason == "satin_top_layer_incomplete"
                    else "the rails fail machine geometry validation"
                    if reason == "satin_geometry_rejected"
                    else "no complete regular column could be extracted"
                )
                raise ValueError(
                    f"Satin requested, but component {i + 1} cannot be sewn as complete safe columns: {failure} (width {width:.2f} mm; safe satin width limit {float_limit:.2f} mm). Use automatic or fill stitching, or simplify the shape."
                )
            angle = _fill_angle(source, params)
            option = fill_elements(polygons, angle, params)
            if params.stitch_type == "fill":
                reason = "requested_uniform_fill"
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
                    candidate = build_stitch_plan(
                        route_columns(option), params, origin_mm=origin_mm
                    )
                    metrics, _ = measure_plan(
                        candidate,
                        np.pad(component, 3),
                        scale,
                        np.array([local_transform.e, local_transform.f]) + 3,
                    )
                candidates["fill"] = metrics
            except (UnstitchableRegion, CandidateGeometryError) as exc:
                candidates["fill"] = {"error": str(exc)}
                option, method, reason = (
                    [],
                    "omitted",
                    "machine_geometry_rejected"
                    if isinstance(exc, CandidateGeometryError)
                    else "below_machine_resolution",
                )
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
                "split_satin_columns": split_count if method == "satin" else 0,
                "safe_satin_width_mm": round(float_limit, 2),
                "fill_angle_deg": angle,
                "candidates": candidates,
                "minimum_detail_enlarged": any(
                    e.get("minimum_detail_enlarged", False) for e in option
                ),
            }
        )
    return chosen, decisions
