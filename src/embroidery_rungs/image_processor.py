"""Bounded SVG rendering and a deterministic Euclidean medial axis."""

from __future__ import annotations

import io
import logging
import math

import numpy as np
import resvg_py
from PIL import Image
from skimage.morphology import medial_axis
from svgelements import Matrix

from .svg_manager import SVGDocument

logger = logging.getLogger(__name__)
MAX_PIXELS = 4_000_000
MAX_DIMENSION = 4096


def render_preview(svg_path, width, height, max_dimension=1200):
    """Bound both sides of previews, including very tall or wide artwork."""
    size = {"width": max_dimension} if width >= height else {"height": max_dimension}
    return resvg_py.svg_to_bytes(
        svg_path=str(svg_path),
        **size,
        dpi=96,
        skip_system_fonts=True,
    )


def rasterize_rgba(svg: SVGDocument, dpi: int = 150):
    """Render visible paint, including clipping/occlusion, in a bounded common frame."""
    scale = max(dpi / 96.0, 256.0 / max(svg.width, svg.height))
    scale = min(
        scale,
        MAX_DIMENSION / max(svg.width, svg.height),
        math.sqrt(MAX_PIXELS / (svg.width * svg.height)),
    )
    png = resvg_py.svg_to_bytes(svg_string=svg.xml, zoom=scale, dpi=96, skip_system_fonts=True)
    with Image.open(io.BytesIO(png)) as image:
        rgba = np.asarray(image.convert("RGBA"))
        mask = rgba[..., 3] >= 128
    rows, cols = np.nonzero(mask)
    if not len(rows):
        raise ValueError("SVG has no visible shape at this resolution.")
    x0, x1 = int(cols.min()), int(cols.max()) + 1
    y0, y1 = int(rows.min()), int(rows.max()) + 1
    rgba = np.pad(rgba[y0:y1, x0:x1], ((3, 3), (3, 3), (0, 0)))
    transform = Matrix.scale(scale)
    transform *= Matrix.translate(3 - x0, 3 - y0)
    logger.info("Raster %dx%d; effective DPI %.1f", rgba.shape[1], rgba.shape[0], scale * 96)
    return rgba, transform


def rasterize_svg(svg: SVGDocument, dpi: int = 150):
    """Preserve the original silhouette rasterization API."""
    rgba, transform = rasterize_rgba(svg, dpi)
    return rgba[..., 3] >= 128, transform


def compute_medial_axis(binary_image: np.ndarray):
    """Return MAT and radius map, preserving input holes and components."""
    mask = np.ascontiguousarray(binary_image, dtype=bool)
    if mask.ndim != 2 or not mask.any():
        raise ValueError("Expected a nonempty two-dimensional shape mask.")
    skeleton, distance = medial_axis(mask, return_distance=True, rng=0)
    return skeleton, distance
