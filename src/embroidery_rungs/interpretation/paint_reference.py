"""Conservative flat-paint evidence before antialiasing is reduced again."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import binary_erosion, label
from scipy.spatial import cKDTree
from skimage.color import rgb2lab

_FG4 = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=bool)
_TILE_PIXELS = 65_536
_MIN_CORE_PIXELS = 9
_MIN_CORE_COVERAGE = 0.5
_MIN_PAINT_AREA_MM2 = 0.01
_FAMILY_MERGE_DELTA_E = 2.0
_FAMILY_SEPARATION_DELTA_E = 8.0
_FAMILY_SOURCE_DELTA_E = 8.0
_FAMILY_MATCH_DELTA_E = 8.0
_FAMILY_MATCH_MARGIN = 2.0


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
        if count <= _TILE_PIXELS:
            counts += np.bincount(part.astype(np.intp, copy=False), minlength=count + 1).astype(
                np.uint32
            )
        else:
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
    counts = _opaque_core_catalog(rgba, max_colors)
    if counts is None:
        return None
    visible_pixels = int(np.count_nonzero(rgba[..., 3] >= 128))
    coverage = sum(counts.values()) / visible_pixels
    paints = tuple(sorted(paint for paint, count in counts.items() if count >= _MIN_CORE_PIXELS))
    if not paints or coverage < _MIN_CORE_COVERAGE:
        return None
    return FlatPaintReference(
        rgba,
        paints,
        tuple(counts[paint] for paint in paints),
        coverage,
        float(physical_width_mm) / (rgba.shape[1] + 2),
    )


@dataclass(frozen=True, eq=False)
class PaintFamilyReference:
    """Estimated source regions around observed opaque RGB core anchors."""

    labels: np.ndarray = field(repr=False)
    paints: tuple[int, ...]
    core_counts: tuple[int, ...]
    core_coverage: float

    @property
    def palette(self) -> np.ndarray:
        return np.asarray(self.paints, dtype=np.uint32)

    def paint_mask(self, paint: int) -> np.ndarray:
        return self.labels == self.paints.index(paint) + 1

    def diagnostics(self) -> dict:
        return {
            "evidence": "opaque_exact_core_families",
            "core_coverage": round(self.core_coverage, 6),
            "minimum_core_pixels": _MIN_CORE_PIXELS,
            "minimum_core_coverage": _MIN_CORE_COVERAGE,
            "minimum_paint_area_mm2": _MIN_PAINT_AREA_MM2,
            "minimum_exact_core_pixels_per_component": _MIN_CORE_PIXELS,
            "merge_delta_e": _FAMILY_MERGE_DELTA_E,
            "minimum_family_separation": _FAMILY_SEPARATION_DELTA_E,
            "maximum_source_delta_e": _FAMILY_SOURCE_DELTA_E,
            "matching_delta_e": _FAMILY_MATCH_DELTA_E,
            "matching_margin_delta_e": _FAMILY_MATCH_MARGIN,
            "core_pixels": {
                f"#{paint:06x}": count
                for paint, count in zip(self.paints, self.core_counts, strict=True)
            },
        }


def match_paint_families(source: list[str], working: list[str]) -> dict[str, str]:
    """Match one observed working paint per source family; ambiguous shades abstain."""
    if not source or not working:
        return {}
    colors = [
        np.array([[int(color[i : i + 2], 16) for i in (1, 3, 5)] for color in palette])
        for palette in (source, working)
    ]
    source_labs, working_labs = [rgb2lab(rgb[None, ...] / 255)[0] for rgb in colors]
    distances = np.linalg.norm(working_labs[:, None] - source_labs[None, ...], axis=2)
    nearest = distances.argmin(axis=1)
    errors = distances[np.arange(len(working)), nearest]
    eligible = errors <= _FAMILY_MATCH_DELTA_E
    if len(source) > 1:
        ordered = np.sort(distances, axis=1)
        eligible &= ordered[:, 1] - ordered[:, 0] >= _FAMILY_MATCH_MARGIN
    counts = np.bincount(nearest[eligible], minlength=len(source))
    return {
        source[nearest[index]]: working[index]
        for index in np.flatnonzero(eligible & (counts[nearest] == 1))
    }


def _opaque_core_tiles(rgba: np.ndarray):
    """Yield local core evidence without a full-grid RGB comparison."""
    height, width = rgba.shape[:2]
    if min(height, width) < 3:
        return
    words = rgba.view(np.uint32)[..., 0] if rgba.strides[-1] == 1 else None
    tile_width = min(width - 2, _TILE_PIXELS)
    tile_height = max(1, _TILE_PIXELS // tile_width)
    for y in range(1, height - 1, tile_height):
        y1 = min(height - 1, y + tile_height)
        for x in range(1, width - 1, tile_width):
            x1 = min(width - 1, x + tile_width)
            centre = rgba[y:y1, x:x1]
            core = centre[..., 3] == 255
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                if words is not None:
                    # Byte equality also requires opaque neighbouring alpha.
                    core &= words[y:y1, x:x1] == words[y + dy : y1 + dy, x + dx : x1 + dx]
                else:
                    neighbour = rgba[y + dy : y1 + dy, x + dx : x1 + dx]
                    core &= (neighbour[..., 3] == 255) & np.all(
                        centre[..., :3] == neighbour[..., :3], axis=-1
                    )
            yield np.s_[y:y1, x:x1], core


def _opaque_core_catalog(rgba: np.ndarray, limit: int) -> dict[int, int] | None:
    """Collect exact opaque cores in bounded tiles; reject excessive colours early."""
    height, width = rgba.shape[:2]
    visible = int(np.count_nonzero(rgba[..., 3] >= 128))
    if not visible or min(height, width) < 3:
        return None
    counts: dict[int, int] = {}
    scanned = cores = 0
    interior = (height - 2) * (width - 2)
    for patch, core in _opaque_core_tiles(rgba):
        centre = rgba[patch]
        rgb = centre[..., :3][core].astype(np.uint32)
        values, amounts = np.unique(
            (rgb[:, 0] << 16) | (rgb[:, 1] << 8) | rgb[:, 2], return_counts=True
        )
        scanned += centre.shape[0] * centre.shape[1]
        cores += len(rgb)
        for value, amount in zip(values, amounts, strict=True):
            paint = int(value)
            counts[paint] = counts.get(paint, 0) + int(amount)
            if len(counts) > limit:
                return None
        if cores + interior - scanned < _MIN_CORE_COVERAGE * visible:
            return None
    return counts if cores >= _MIN_CORE_COVERAGE * visible else None


def discover_paint_families(
    rgba: np.ndarray, physical_width_mm: float, *, max_colors: int
) -> PaintFamilyReference | None:
    """Retry noisy flat artwork with bounded, source-anchored colour families.

    Exact opaque cores anchor every family. Fixed-radius merging avoids treating
    a chain of intermediate gradient shades as one paint. This estimate is only
    adopted when the actual working palette and geometry also pass their audit.
    """
    catalog = _opaque_core_catalog(rgba, min(2048, max(64, 8 * max_colors)))
    if catalog is None:
        return None
    values = np.array(
        sorted(paint for paint, count in catalog.items() if count >= _MIN_CORE_PIXELS), np.uint32
    )
    if not len(values):
        return None
    counts = np.array([catalog[int(paint)] for paint in values])
    rgb = np.column_stack([values >> 16, (values >> 8) & 255, values & 255])
    labs = rgb2lab(rgb[None, ...] / 255)[0]
    seeds = []
    for index in np.argsort(-counts, kind="stable"):
        if (
            not seeds
            or np.linalg.norm(labs[seeds] - labs[index], axis=1).min() > _FAMILY_MERGE_DELTA_E
        ):
            seeds.append(index)
            if len(seeds) > max_colors:
                return None
    if len(seeds) < 2:
        return None
    seed_labs = labs[seeds]
    separation = np.linalg.norm(seed_labs[:, None] - seed_labs[None, ...], axis=2)
    np.fill_diagonal(separation, np.inf)
    if separation.min() < _FAMILY_SEPARATION_DELTA_E:
        return None
    seeds = np.asarray(seeds)[np.argsort(values[seeds])]
    paints = values[seeds]
    tree = cKDTree(labs[seeds])
    labels = np.zeros(rgba.shape[:2], dtype=np.uint16)
    tile_width = min(rgba.shape[1], _TILE_PIXELS)
    tile_height = min(32, max(1, _TILE_PIXELS // tile_width))
    for y in range(0, len(rgba), tile_height):
        for x in range(0, rgba.shape[1], tile_width):
            patch = np.s_[y : y + tile_height, x : x + tile_width]
            source = rgba[patch]
            colors = rgb2lab(source[..., :3] / 255)
            distance, nearest = tree.query(colors, k=2)
            supported = (
                (source[..., 3] >= 128)
                & (distance[..., 0] <= _FAMILY_SOURCE_DELTA_E)
                & (distance[..., 1] - distance[..., 0] >= _FAMILY_MATCH_MARGIN)
            )
            labels[patch][supported] = nearest[..., 0][supported] + 1
    core = binary_erosion(rgba[..., 3] == 255, structure=_FG4)
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        core[1:-1, 1:-1] &= (
            labels[1:-1, 1:-1]
            == labels[1 + dy : labels.shape[0] - 1 + dy, 1 + dx : labels.shape[1] - 1 + dx]
        )
    core &= labels > 0
    exact_core = np.zeros(labels.shape, dtype=bool)
    for patch, evidence in _opaque_core_tiles(rgba):
        exact_core[patch] = evidence
    pixel_mm = float(physical_width_mm) / (rgba.shape[1] + 2)
    core_counts = []
    for index, paint in enumerate(paints, 1):
        mask = labels == index
        groups, count = label(mask, structure=_FG4)
        sizes = region_counts(groups, count)
        anchors = region_counts(groups, count, mask=exact_core)
        useful = (sizes >= _MIN_PAINT_AREA_MM2 / pixel_mm**2 - 1e-9) & (anchors >= _MIN_CORE_PIXELS)
        useful[0] = False
        retained = useful[groups]
        if not retained.any():
            return None
        # The representative must be observed in a supported opaque core, not
        # merely be a globally frequent matte or a distant discarded fragment.
        exact = retained & (rgba[..., 3] == 255)
        for channel, shift in enumerate((16, 8, 0)):
            exact &= rgba[..., channel] == ((int(paint) >> shift) & 255)
        if not binary_erosion(exact, structure=_FG4).any():
            return None
        labels[mask & ~retained] = 0
        core_counts.append(int(np.count_nonzero(core & retained)))
    coverage = sum(core_counts) / np.count_nonzero(rgba[..., 3] >= 128)
    if coverage < _MIN_CORE_COVERAGE:
        return None
    labels.setflags(write=False)
    return PaintFamilyReference(
        labels, tuple(map(int, paints)), tuple(core_counts), float(coverage)
    )
