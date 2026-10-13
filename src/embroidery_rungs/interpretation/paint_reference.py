"""Conservative flat-paint evidence before antialiasing is reduced again."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import binary_erosion, label

_FG4 = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=bool)
_TILE_PIXELS = 65_536
_MIN_CORE_PIXELS = 9
_MIN_CORE_COVERAGE = 0.5
_MIN_PAINT_AREA_MM2 = 0.01


def region_counts(groups: np.ndarray, count: int, *, mask: np.ndarray | None = None) -> np.ndarray:
    """Count labels in fixed tiles without NumPy's full-grid int64 cast."""
    counts = np.zeros(count + 1, dtype=np.uint32)
    if count == 1:
        counts[1] = np.count_nonzero(groups if mask is None else (groups > 0) & mask)
        return counts
    flat = groups.ravel()
    flat_mask = None if mask is None else mask.ravel()
    for start in range(0, len(flat), _TILE_PIXELS):
        part = flat[start : start + _TILE_PIXELS]
        if flat_mask is not None:
            part = part[flat_mask[start : start + _TILE_PIXELS]]
        values, amounts = np.unique(part, return_counts=True)
        counts[values] += amounts.astype(np.uint32)
    return counts


@dataclass(frozen=True, eq=False)
class FlatPaintReference:
    """Estimated paints supported by opaque, locally constant source cores."""

    rgba: np.ndarray = field(repr=False)
    paints: tuple[int, ...]
    core_counts: tuple[int, ...]
    core_coverage: float
    pixel_size_mm: float

    @property
    def palette(self) -> np.ndarray:
        return np.asarray(self.paints, dtype=np.uint32)

    def paint_mask(self, paint: int) -> np.ndarray:
        """Exclude same-RGB fringes without their own physically useful core."""
        rgba = self.rgba
        mask = rgba[..., 3] >= 128
        for channel, shift in enumerate((16, 8, 0)):
            mask &= rgba[..., channel] == ((paint >> shift) & 255)
        opaque_core = binary_erosion(mask & (rgba[..., 3] == 255), structure=_FG4)
        groups, count = label(mask, structure=_FG4)
        sizes = region_counts(groups, count)
        cores = region_counts(groups, count, mask=opaque_core)
        useful = (sizes >= _MIN_PAINT_AREA_MM2 / self.pixel_size_mm**2 - 1e-9) & (
            cores >= _MIN_CORE_PIXELS
        )
        useful[0] = False
        return useful[groups]

    def diagnostics(self) -> dict:
        return {
            "evidence": "opaque_four_neighbour_cores",
            "core_coverage": round(self.core_coverage, 6),
            "minimum_core_pixels": _MIN_CORE_PIXELS,
            "minimum_core_coverage": _MIN_CORE_COVERAGE,
            "minimum_paint_area_mm2": _MIN_PAINT_AREA_MM2,
            "core_pixels": {
                f"#{paint:06x}": count
                for paint, count in zip(self.paints, self.core_counts, strict=True)
            },
        }


def discover_flat_paints(
    rgba: np.ndarray, physical_width_mm: float, *, max_colors: int
) -> FlatPaintReference | None:
    """Find a small stable palette without quantizing or histogramming a photo.

    A flat core is opaque and has the same RGB as all four opaque neighbours.
    The complete source is scanned in fixed tiles; too many core colours abort
    immediately. No literal colour is inferred from hidden RGB or matte alpha.
    """
    height, width = rgba.shape[:2]
    if min(height, width) < 3:
        return None
    tile_width = min(width - 2, _TILE_PIXELS)
    tile_height = max(1, _TILE_PIXELS // tile_width)
    counts: dict[int, int] = {}
    visible_pixels = int(np.count_nonzero(rgba[..., 3] >= 128))
    if visible_pixels == 0:
        return None
    interior_pixels = (height - 2) * (width - 2)
    processed_pixels = 0
    core_pixels = 0
    for y in range(1, height - 1, tile_height):
        y1 = min(height - 1, y + tile_height)
        for x in range(1, width - 1, tile_width):
            x1 = min(width - 1, x + tile_width)
            centre = rgba[y:y1, x:x1]
            core = centre[..., 3] == 255
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                neighbour = rgba[y + dy : y1 + dy, x + dx : x1 + dx]
                core &= (neighbour[..., 3] == 255) & np.all(
                    centre[..., :3] == neighbour[..., :3], axis=-1
                )
            rgb = centre[..., :3][core].astype(np.uint32)
            packed = (rgb[:, 0] << 16) | (rgb[:, 1] << 8) | rgb[:, 2]
            values, amounts = np.unique(packed, return_counts=True)
            processed_pixels += centre.shape[0] * centre.shape[1]
            core_pixels += len(packed)
            for value, amount in zip(values, amounts, strict=True):
                key = int(value)
                counts[key] = counts.get(key, 0) + int(amount)
                if len(counts) > max_colors:
                    return None
            if (
                core_pixels + interior_pixels - processed_pixels
                < _MIN_CORE_COVERAGE * visible_pixels
            ):
                return None
    coverage = sum(counts.values()) / visible_pixels
    paints = tuple(sorted(paint for paint, count in counts.items() if count >= _MIN_CORE_PIXELS))
    if not paints or coverage < _MIN_CORE_COVERAGE:
        return None
    return FlatPaintReference(
        rgba,
        paints,
        tuple(counts[paint] for paint in paints),
        coverage,
        float(physical_width_mm) / (width + 2),
    )
