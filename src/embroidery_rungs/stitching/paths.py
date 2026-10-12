"""Satin, running and clipped tatami paths in millimetres."""

from __future__ import annotations

import math

import numpy as np
from shapely import covers, linestrings, prepare
from shapely.affinity import rotate
from shapely.geometry import LineString, Polygon

from ..routing import _nearest_neighbour
from .params import StitchParams


def resample_running(points, length: float, tolerance: float = 0.12) -> np.ndarray:
    """Preserve bends before subdividing: a long chord must not cut a curve."""
    points = np.asarray(points, dtype=float)
    points = points[np.r_[True, np.linalg.norm(np.diff(points, axis=0), axis=1) > 1e-8]]
    if len(points) < 2:
        return points
    simplified = np.asarray(LineString(points).simplify(tolerance).coords)
    result = [simplified[0]]
    for a, b in zip(simplified[:-1], simplified[1:], strict=True):
        n = max(1, math.ceil(np.linalg.norm(b - a) / length))
        result.extend(a + (b - a) * np.arange(1, n + 1)[:, None] / n)
    return np.asarray(result)


def _rail_samples(a, b, half_pitch, max_samples=500_000):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    steps = np.maximum(
        np.linalg.norm(np.diff(a, axis=0), axis=1), np.linalg.norm(np.diff(b, axis=0), axis=1)
    )
    keep = np.r_[True, steps > 1e-8]
    progress = np.r_[0.0, np.cumsum(steps)][keep]
    a, b = a[keep], b[keep]
    if len(a) < 2:
        return a, b
    count = max(3, math.ceil(progress[-1] / half_pitch) + 1)
    if count > max_samples:
        raise ValueError("Stitch budget exceeded; simplify the design or increase spacing.")
    targets = np.linspace(0, progress[-1], count)
    return tuple(
        np.column_stack([np.interp(targets, progress, rail[:, k]) for k in (0, 1)])
        for rail in (a, b)
    )


def satin_points(a, b, params: StitchParams, *, underlay=False) -> np.ndarray:
    """Bound outer-edge spacing; distribute crowded inner-corner penetrations."""
    pitch = 3.0 if underlay else params.satin_spacing_mm
    a, b = _rail_samples(a, b, pitch / 2, params.max_stitches)
    if len(a) < 2:
        return np.empty((0, 2))
    vectors = b - a
    widths = np.linalg.norm(vectors, axis=1)
    directions = vectors / np.maximum(widths[:, None], 1e-8)
    if underlay:
        inset = np.minimum(0.6, widths * 0.25)
        a, b = a + directions * inset[:, None], b - directions * inset[:, None]
    else:
        compensation = np.minimum(params.pull_compensation_mm, widths * 0.1)
        a, b = a - directions * compensation[:, None], b + directions * compensation[:, None]
    points = []
    for i in range(len(a)):
        side = i % 2
        edge, other = (a[i], b[i]) if side == 0 else (b[i], a[i])
        candidate = edge
        if not underlay and i >= 2:
            rail = a if side == 0 else b
            advance = np.linalg.norm(rail[i] - rail[i - 2])
            if advance < params.min_stitch_mm:
                # Short-stitch fan: keep regular outer pitch while spreading
                # compressed inner penetrations over deterministic inset bands.
                bands = min(4, math.ceil(params.min_stitch_mm / max(advance, 0.01)))
                depth = min((i // 2 % bands) * (params.min_stitch_mm + 0.08), widths[i] * 0.3)
                candidate = edge + (other - edge) * depth / max(np.linalg.norm(other - edge), 1e-8)
        points.append(candidate)
    # Finish the terminal cross-section rather than leaving a half-covered cap.
    terminal = b[-1] if (len(a) - 1) % 2 == 0 else a[-1]
    if np.linalg.norm(points[-1] - terminal) >= params.min_stitch_mm:
        points.append(terminal)
    result = np.asarray(points)
    maximum = (
        min(params.running_length_mm, params.max_stitch_mm) if underlay else params.max_stitch_mm
    )
    # Offset subdivision phases avoid a visible line of needle holes in split satin.
    return _subdivide(result, maximum)


def _subdivide(points, maximum):
    result = [points[0]] if len(points) else []
    for i, (a, b) in enumerate(zip(points[:-1], points[1:], strict=True)):
        distance = float(np.linalg.norm(b - a))
        if distance <= maximum - 0.15:
            result.append(b)
            continue
        n = math.ceil(distance / (maximum * 0.85))
        positions = np.arange(1, n) / n
        positions += ((i % 3) - 1) * 0.1 / n
        result.extend(a + (b - a) * positions[:, None])
        result.append(b)
    return np.asarray(result)


def fill_paths(polygon: Polygon, angle: float, spacing: float, length: float):
    """Staggered tatami rows clipped to a polygon, including its holes."""
    shape = rotate(polygon, -angle, origin=(0, 0))
    xmin, ymin, xmax, ymax = shape.bounds
    first_row = math.floor(ymin / spacing)
    ys = (np.arange(first_row, math.ceil(ymax / spacing)) + 0.5) * spacing
    radians = math.radians(angle)
    matrix = np.array(
        [[math.cos(radians), -math.sin(radians)], [math.sin(radians), math.cos(radians)]]
    )
    for local_row, y in enumerate(ys):
        row = first_row + local_row
        clipped = shape.intersection(LineString([(xmin - 1, y), (xmax + 1, y)]))
        segments = (
            [clipped] if clipped.geom_type == "LineString" else list(getattr(clipped, "geoms", []))
        )
        segments = sorted(
            (s for s in segments if s.geom_type == "LineString" and s.length >= 0.3),
            key=lambda s: s.bounds[0],
            reverse=bool(row % 2),
        )
        for segment in segments:
            low, _, high, _ = segment.bounds
            phase = (row % 4) * length / 4
            inner = (
                np.arange(
                    math.floor((low - phase) / length) + 1, math.ceil((high - phase) / length)
                )
                * length
                + phase
            )
            inner = inner[(inner - low >= 0.3) & (high - inner >= 0.3)]
            xs = np.r_[low, inner, high]
            if row % 2:
                xs = xs[::-1]
            yield np.column_stack([xs, np.full(len(xs), y)]) @ matrix.T


def _safe_pieces(points, area):
    if len(points) < 2:
        return [], 0
    segments = linestrings(np.stack([points[:-1], points[1:]], axis=1))
    prepare(area)
    safe = covers(area, segments)
    starts = np.r_[0, np.flatnonzero(~safe) + 1]
    ends = np.r_[np.flatnonzero(~safe) + 1, len(points)]
    pieces = [points[a:b] for a, b in zip(starts, ends, strict=True) if b - a >= 2]
    return pieces, int(np.count_nonzero(~safe))


def _ordered_fill_paths(polygon, angle, spacing, length, max_travel=3.0):
    """Prefer nearby connections inside the fill before crossing a hole or gap."""
    paths = list(fill_paths(polygon, angle, spacing, length))
    if len(paths) < 2:
        return paths
    endpoints = np.asarray([(p[0], p[-1]) for p in paths])
    visited = np.zeros(len(paths), dtype=bool)
    region = polygon.buffer(0.08)
    prepare(region)
    index, side = np.unravel_index(np.argmin(endpoints.sum(axis=2)), (len(paths), 2))
    ordered = []
    for _ in paths:
        visited[index] = True
        path = paths[index][::-1] if side else paths[index]
        ordered.append(path)
        if visited.all():
            break
        distances = np.linalg.norm(endpoints - path[-1], axis=2)
        distances[visited] = np.inf
        flat = distances.ravel()
        count = min(16, np.count_nonzero(np.isfinite(flat)))
        nearest = np.argpartition(flat, count - 1)[:count]
        connectors = np.stack(
            [np.broadcast_to(path[-1], (count, 2)), endpoints.reshape(-1, 2)[nearest]], axis=1
        )
        safe = (flat[nearest] <= max_travel) & covers(region, linestrings(connectors))
        best = nearest[np.argmin(flat[nearest] + 25 * ~safe)]
        index, side = np.unravel_index(best, distances.shape)
    sequence = _nearest_neighbour([(p[0], p[-1]) for p in paths])
    baseline = [paths[e["col"]][::-1] if e["rev"] else paths[e["col"]] for e in sequence]

    def cost(candidate):
        connectors = np.asarray(
            [[a[-1], b[0]] for a, b in zip(candidate[:-1], candidate[1:], strict=True)]
        )
        distances = np.linalg.norm(connectors[:, 1] - connectors[:, 0], axis=1)
        safe = (distances <= max_travel) & covers(region, linestrings(connectors))
        return 25 * np.count_nonzero(~safe) + distances.sum()

    return ordered if cost(ordered) < cost(baseline) else baseline
