"""Native-grid fidelity checks for categorical bitmap contours."""

from __future__ import annotations

import io
from copy import deepcopy
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

import numpy as np
import resvg_py
from PIL import Image
from scipy.ndimage import binary_erosion, distance_transform_edt, label

from ..svg_manager import MAX_INPUT_BYTES

if TYPE_CHECKING:
    from .types import RasterArtwork

_FOREGROUND = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=bool)
_BACKGROUND = np.ones((3, 3), dtype=bool)
_MAX_AUDIT_PIXELS = 16_100_000
_MAX_AUDIT_DIMENSION = 16_384


def check_grid_budget(shape: tuple[int, int]) -> None:
    height, width = shape
    if width * height > _MAX_AUDIT_PIXELS or max(width, height) > _MAX_AUDIT_DIMENSION:
        raise ValueError(
            "Native trace audit exceeds its raster size limit; reduce image dimensions."
        )


def topology(mask: np.ndarray) -> dict[str, int]:
    """Count painted components with fg4 and counters with bg8 connectivity."""
    components = int(label(mask, structure=_FOREGROUND)[1])
    background, count = label(~mask, structure=_BACKGROUND)
    exterior = np.unique(
        np.concatenate((background[0], background[-1], background[:, 0], background[:, -1]))
    )
    holes = int(count - np.count_nonzero(exterior))
    return {"components": components, "holes": holes}


def _categorical_pixels(rgba: np.ndarray, palette: tuple[str, ...]) -> np.ndarray:
    paints = np.array(
        [
            [int(color[1 + channel * 2 : 3 + channel * 2], 16) for channel in range(3)]
            for color in palette
        ],
        dtype=np.int32,
    )
    dtype = np.min_scalar_type(len(palette))
    result = np.zeros(rgba.shape[:2], dtype=dtype)
    for start in range(0, len(rgba), 64):
        stop = min(len(rgba), start + 64)
        pixels = rgba[start:stop, :, :3].astype(np.int32)
        visible = rgba[start:stop, :, 3] >= 128
        best = np.full(visible.shape, np.iinfo(np.int32).max, dtype=np.int32)
        selected = np.zeros(visible.shape, dtype=dtype)
        for index, paint in enumerate(paints, 1):
            delta = pixels - paint
            distance = np.einsum("ijk,ijk->ij", delta, delta)
            closer = distance < best
            best[closer] = distance[closer]
            selected[closer] = index
        result[start:stop] = np.where(visible, selected, 0)
    return result


def _contour_distances(
    expected: np.ndarray, actual: np.ndarray, pixel_size_mm: tuple[float, float]
) -> dict[str, float | bool]:
    if expected is actual or np.array_equal(expected, actual):
        return {"p95_mm": 0.0, "max_mm": 0.0, "missing_boundary": False}
    expected_edge = expected & ~binary_erosion(expected, structure=_BACKGROUND)
    actual_edge = actual & ~binary_erosion(actual, structure=_BACKGROUND)
    if not expected_edge.any() or not actual_edge.any():
        height, width = expected.shape
        bound = float(np.hypot(width * pixel_size_mm[0], height * pixel_size_mm[1]))
        return {"p95_mm": bound, "max_mm": bound, "missing_boundary": True}
    sampling = (pixel_size_mm[1], pixel_size_mm[0])
    to_actual = distance_transform_edt(~actual_edge, sampling=sampling)[expected_edge]
    to_expected = distance_transform_edt(~expected_edge, sampling=sampling)[actual_edge]
    distances = np.concatenate((to_actual, to_expected))
    return {
        "p95_mm": round(float(np.percentile(distances, 95)), 6),
        "max_mm": round(float(distances.max()), 6),
        "missing_boundary": False,
    }


def _paint_masks(expected: np.ndarray, actual: np.ndarray, palette: tuple[str, ...], exact: bool):
    source = expected > 0
    yield "alpha", source, source if exact else actual > 0
    for index, color in enumerate(palette, 1):
        source = expected == index
        rendered = source if exact else actual == index
        if source.any() or rendered.any():
            yield color, source, rendered


def audit_trace(root: ET.Element, artwork: RasterArtwork, *, node_count: int) -> dict:
    """Render once and compare all paints on the bitmap's original pixel centres.

    Marching squares uses integer coordinates as pixel centres. SVG renderers
    sample at half-integers. Only the audit copy shifts its viewBox by -0.5;
    emitted SVGs and their historical machine coordinate transform stay intact.
    """
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    if len(payload) > MAX_INPUT_BYTES:
        raise ValueError("Traced SVG exceeds the 10 MiB input limit; simplify the artwork.")
    height, width = artwork.labels.shape
    check_grid_budget(artwork.labels.shape)
    audit_root = deepcopy(root)
    audit_root.set("viewBox", f"-0.5 -0.5 {width} {height}")
    audit_root.set("width", str(width))
    audit_root.set("height", str(height))
    png = resvg_py.svg_to_bytes(
        svg_string=ET.tostring(audit_root, encoding="unicode"),
        width=width,
        height=height,
        dpi=96,
        skip_system_fonts=True,
    )
    with Image.open(io.BytesIO(png)) as image:
        actual = _categorical_pixels(np.asarray(image.convert("RGBA")), artwork.palette)
    expected = artwork.labels
    changed = int(np.count_nonzero(actual != expected))
    silhouette_changed = int(np.count_nonzero((actual > 0) != (expected > 0)))
    paints = {}
    topology_preserved = True
    for color, source, rendered in _paint_masks(expected, actual, artwork.palette, changed == 0):
        before = topology(source)
        after = before.copy() if source is rendered else topology(rendered)
        equal = before == after
        topology_preserved &= equal
        paints[color] = {
            "source": before,
            "rendered": after,
            "topology_preserved": equal,
            "changed_pixels": 0
            if source is rendered
            else int(np.count_nonzero(source != rendered)),
            "contour": _contour_distances(source, rendered, artwork.pixel_size_mm),
        }
    return {
        "passed": changed == 0,
        "categorical_pixels_preserved": changed == 0,
        "topology_preserved": bool(topology_preserved),
        "changed_pixels": changed,
        "changed_area_mm2": round(float(changed * np.prod(artwork.pixel_size_mm)), 6),
        "silhouette_changed_pixels": silhouette_changed,
        "grid": "integer_pixel_centres",
        "audit_viewbox": [-0.5, -0.5, width, height],
        "canvas_size_mm": list(artwork.canvas_size_mm),
        "pixel_size_mm": list(artwork.pixel_size_mm),
        "serialized_bytes": len(payload),
        "nodes": int(node_count),
        "paints": paints,
    }
