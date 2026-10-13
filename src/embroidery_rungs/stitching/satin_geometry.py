"""Directional satin strips when a branched medial axis cannot cover a region."""

from __future__ import annotations

import numpy as np
from shapely import intersection, linestrings
from shapely.affinity import rotate
from shapely.geometry import Polygon, box


def directional_columns(source: Polygon, angle: float, compensation: float) -> list[dict]:
    """Partition a silhouette into monotone strips without bridging its holes.

    A contour reversal is a sweep event. Adjacent intervals are joined only when
    their correspondence is one-to-one; forks and holes become separate columns.
    This is a genuine paired-rail satin decomposition, not subdivided fill rows.
    """
    if source.geom_type != "Polygon":
        return []
    # Suppress raster stair steps below the machine's 0.1 mm grid. The original
    # silhouette remains the allowed area and the target of the stitch audit.
    shape = rotate(source.simplify(0.08, preserve_topology=True), -angle, origin=(0, 0))
    low, bottom, high, top = shape.bounds
    stations = [low, high]
    for ring in (shape.exterior, *shape.interiors):
        xs = np.asarray(ring.coords)[:-1, 0]
        previous, following = np.roll(xs, 1) - xs, np.roll(xs, -1) - xs
        extrema = (previous * following >= 0) & (
            np.maximum(np.abs(previous), np.abs(following)) > 1e-6
        )
        stations.extend(xs[extrema])
    stations = np.unique(stations)
    if len(stations) > 256:
        return []
    bands: list[tuple[np.ndarray, np.ndarray]] = []
    previous_bands: list[int] = []
    for left, right in zip(stations[:-1], stations[1:], strict=True):
        if right - left < 1e-7:
            continue
        clipped = shape.intersection(box(left, bottom - 1, right, top + 1))
        pieces = [clipped] if clipped.geom_type == "Polygon" else getattr(clipped, "geoms", ())
        current = []
        for piece in pieces:
            if piece.geom_type != "Polygon" or piece.area < 1e-7:
                continue
            if piece.interiors:
                return []
            xs = np.unique(
                np.r_[
                    np.asarray(piece.exterior.coords)[:, 0],
                    np.linspace(left, right, max(3, int(np.ceil((right - left) / 0.15)) + 1)),
                ]
            )
            xs[0], xs[-1] = left + 1e-7, right - 1e-7
            starts = np.column_stack([xs, np.full(len(xs), bottom - 1)])
            ends = np.column_stack([xs, np.full(len(xs), top + 1)])
            cuts = intersection(piece, linestrings(np.stack([starts, ends], axis=1)))
            pairs = []
            for position, cut in zip(xs, cuts, strict=True):
                segments = [cut] if cut.geom_type == "LineString" else getattr(cut, "geoms", ())
                segments = [s for s in segments if s.geom_type == "LineString" and s.length > 1e-8]
                if len(segments) > 1:
                    return []
                if segments:
                    ys = np.asarray(segments[0].coords)[:, 1]
                    pairs.append([[position, ys.min()], [position, ys.max()]])
            if len(pairs) < 2:
                continue
            a, b = np.asarray(pairs).transpose(1, 0, 2)
            a[0, 0] = b[0, 0] = left
            a[-1, 0] = b[-1, 0] = right
            current.append((a, b))
        links = []
        for previous_index, band_index in enumerate(previous_bands):
            pa, pb = bands[band_index]
            for current_index, (a, b) in enumerate(current):
                if min(pb[-1, 1], b[0, 1]) - max(pa[-1, 1], a[0, 1]) > 1e-6:
                    links.append((previous_index, current_index))
        previous_degree = np.bincount([p for p, _ in links], minlength=len(previous_bands))
        current_degree = np.bincount([c for _, c in links], minlength=len(current))
        # Keep large square corners as flat-ended columns instead of a needle
        # fan on one stationary rail. Smaller contour steps retain both vertices
        # and are still checked for crowding after machine rounding.
        continuations = {
            c: previous_bands[p]
            for p, c in links
            if previous_degree[p] == current_degree[c] == 1
            and max(
                abs(bands[previous_bands[p]][0][-1, 1] - current[c][0][0, 1]),
                abs(bands[previous_bands[p]][1][-1, 1] - current[c][1][0, 1]),
            )
            <= 1.0
        }
        previous_bands = []
        for index, (a, b) in enumerate(current):
            if index in continuations:
                band_index = continuations[index]
                pa, pb = bands[band_index]
                bands[band_index] = (np.vstack([pa, a]), np.vstack([pb, b]))
            else:
                band_index = len(bands)
                bands.append((a, b))
            previous_bands.append(band_index)
        if len(bands) > 64:
            return []
    radians = np.deg2rad(angle)
    matrix = np.array([[np.cos(radians), -np.sin(radians)], [np.sin(radians), np.cos(radians)]])
    allowed_area = source.buffer(compensation + 0.08)
    columns = []
    for a, b in bands:
        a, b = a @ matrix.T, b @ matrix.T
        polygon = Polygon(np.vstack([a, b[::-1]]))
        if not polygon.is_valid or polygon.area <= 0:
            return []
        columns.append(
            {
                "type": "satin",
                "stitch_type": "satin",
                "rail_a": a,
                "rail_b": b,
                "allowed_area": allowed_area,
                "directional_satin_angle_deg": (angle + 90) % 180,
            }
        )
    return columns
