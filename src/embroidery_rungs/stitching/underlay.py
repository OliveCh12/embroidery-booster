"""Inset foundations: support the top stitches without exposing an edge halo."""

from __future__ import annotations

import numpy as np

from .paths import _ordered_fill_paths, resample_running, satin_points


def fill_underlay(polygon, angle, params, *, edge_walk=None):
    # Tiny details already have many penetrations per unit area. Another complete
    # foundation there adds bulk rather than support.
    if polygon.area < 4:
        return []
    inset = {30: 0.5, 40: 0.4, 60: 0.3}[params.thread_weight]
    interior = polygon.buffer(-inset)
    if interior.is_empty:
        interior = polygon.buffer(-0.2)
    if interior.is_empty:
        return []
    pieces = [interior] if interior.geom_type == "Polygon" else list(interior.geoms)
    spacing = 2.0 if params.fabric in ("stretch", "textured") else 3.0
    paths = []
    for piece in pieces:
        if piece.geom_type != "Polygon":
            continue
        # Edge support secures the boundary before the dense rows pull the cloth.
        # Holes get the same inset support; no underlay bridges their interiors.
        edge = piece.area >= (4 if params.fabric in ("stretch", "textured") else 10)
        if edge_walk is not None:
            edge = edge_walk
        if edge:
            paths.extend(
                resample_running(
                    np.asarray(ring.coords), min(2.0, params.max_stitch_mm), tolerance=0.04
                )
                for ring in (piece.exterior, *piece.interiors)
            )
        paths.extend(
            _ordered_fill_paths(
                piece,
                angle + 90,
                spacing,
                min(params.running_length_mm, params.max_stitch_mm),
                params.trim_distance_mm,
                minimum=params.min_stitch_mm,
            )
        )
    return paths


def satin_underlay(a, b, params, *, edge_walk=None, zigzag=None):
    centers = (a + b) / 2
    paths = [resample_running(centers, min(2.0, params.max_stitch_mm), tolerance=0.05)]
    vectors = b - a
    widths = np.linalg.norm(vectors, axis=1)
    edge = params.fabric in ("stretch", "textured") and np.percentile(widths, 25) >= 2.5
    if edge_walk is not None:
        edge = edge_walk
    if edge:
        direction = vectors / np.maximum(widths[:, None], 1e-8)
        inset = np.minimum(0.6, widths * 0.25)[:, None]
        edge = np.vstack([(a + direction * inset)[::-1], b - direction * inset])
        paths.append(resample_running(edge, min(2.0, params.max_stitch_mm), tolerance=0.05))
    if zigzag is None:
        zigzag = widths.max() >= 3
    if zigzag:
        paths.append(satin_points(a[::-1], b[::-1], params, underlay=True))
    return paths
