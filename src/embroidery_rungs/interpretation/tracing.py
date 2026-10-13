"""Audited SVG serialization without changing categorical source artwork."""

from __future__ import annotations

import math
from itertools import chain
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

import numpy as np
from scipy.ndimage import binary_dilation
from skimage.measure import approximate_polygon, find_contours

from .audit import audit_trace, check_grid_budget, topology

if TYPE_CHECKING:
    from .types import RasterArtwork

MAX_TRACE_CONTOURS = 8192


def _without_collinear_vertices(contour: np.ndarray) -> np.ndarray:
    points = contour[:-1] if np.array_equal(contour[0], contour[-1]) else contour
    if len(points) < 3:
        return points
    before = points - np.roll(points, 1, axis=0)
    after = np.roll(points, -1, axis=0) - points
    cross = before[:, 0] * after[:, 1] - before[:, 1] * after[:, 0]
    forward = np.einsum("ij,ij->i", before, after) >= 0
    return points[(cross != 0) | ~forward]


def trace_path(mask: np.ndarray, tolerance: float) -> tuple[str, int]:
    """Trace fg4/bg8 contours; tolerance zero retains the exact marching squares."""
    check_grid_budget(mask.shape)
    counts = topology(mask)
    count = counts["components"] + counts["holes"]
    if count > MAX_TRACE_CONTOURS:
        raise ValueError(
            f"Bitmap mask contains {count} contours (paint components and counters); "
            f"the limit is {MAX_TRACE_CONTOURS}. Simplify the artwork or reduce image dimensions."
        )
    parts = []
    nodes = 0
    for contour in find_contours(mask, 0.5, fully_connected="low"):
        if tolerance > 0:
            contour = approximate_polygon(contour, tolerance=tolerance)
        contour = _without_collinear_vertices(contour)
        if len(contour) >= 3:
            nodes += len(contour)
            parts.append("M " + " L ".join(f"{x:.3f},{y:.3f}" for y, x in contour) + " Z")
    return " ".join(parts), nodes


def _serialize(
    artwork: RasterArtwork, tolerance: float, crisp_edges: bool
) -> tuple[ET.Element, int]:
    labels = artwork.labels
    height, width = labels.shape
    canvas_width, canvas_height = artwork.canvas_size_mm
    root = ET.Element(
        "svg",
        xmlns="http://www.w3.org/2000/svg",
        width=f"{canvas_width:g}mm",
        height=f"{canvas_height:g}mm",
        viewBox=f"0 0 {width} {height}",
    )
    if crisp_edges:
        root.set("shape-rendering", "crispEdges")
    visible = labels > 0
    boundary = visible & binary_dilation(~visible)
    base = int(np.bincount(labels[boundary], minlength=len(artwork.palette) + 1)[1:].argmax()) + 1
    nodes = 0
    # Shared silhouette closes inter-paint cracks without adding a pale rim to
    # a dark outline. Other paints overlay it, retaining evenodd counters.
    masks = chain(
        ((artwork.palette[base - 1], visible),),
        (
            (color, labels == index)
            for index, color in enumerate(artwork.palette, 1)
            if index != base
        ),
    )
    for color, mask in masks:
        path, count = trace_path(mask, tolerance)
        nodes += count
        if path:
            ET.SubElement(root, "path", fill=color, attrib={"fill-rule": "evenodd", "d": path})
    return root, nodes


def serialize_bitmap(
    artwork: RasterArtwork, tolerance: float, *, crisp_edges: bool
) -> tuple[ET.Element, dict]:
    """Simplify when native categorical paint is preserved, otherwise retrace.

    Exact-grid agreement is deliberately stronger than aggregate coverage:
    losing a one-pixel counter or accent cannot be hidden by a large filled area.
    """
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("Trace tolerance must be finite and nonnegative.")
    if not isinstance(crisp_edges, bool):
        raise ValueError("crisp_edges must be a boolean.")
    check_grid_budget(artwork.labels.shape)
    root, nodes = _serialize(artwork, tolerance, crisp_edges)
    first = audit_trace(root, artwork, node_count=nodes)
    diagnostics = {
        "requested_tolerance_px": float(tolerance),
        "effective_tolerance_px": float(tolerance),
        "fallback": False,
        "render_attempts": 1,
        "initial": first,
        "final": first,
    }
    if first["passed"]:
        return root, diagnostics
    if tolerance > 0:
        root, nodes = _serialize(artwork, 0, crisp_edges)
        final = audit_trace(root, artwork, node_count=nodes)
        diagnostics.update(
            effective_tolerance_px=0.0,
            fallback=True,
            fallback_reason=(
                "simplification_changed_topology"
                if not first["topology_preserved"]
                else "simplification_changed_categorical_paint"
            ),
            render_attempts=2,
            final=final,
        )
        if final["passed"]:
            return root, diagnostics
    raise ValueError("Bitmap contours could not preserve source paint on the native pixel grid.")
