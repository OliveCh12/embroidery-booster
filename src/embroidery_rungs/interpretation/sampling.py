"""Bounded bitmap reduction that checks details before colour interpretation."""

from __future__ import annotations

import math
from numbers import Integral, Real

import numpy as np
from PIL import Image
from scipy.ndimage import binary_erosion, label
from scipy.spatial import cKDTree

from ..colors import bitmap_colors
from .paint_reference import (
    FlatPaintReference,
    PaintFamilyReference,
    discover_flat_paints,
    discover_paint_families,
    match_paint_families,
    region_counts,
)

_FG4 = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=bool)
_BG8 = np.ones((3, 3), dtype=bool)
_MAX_SOURCE_PIXELS = 16_000_000
_MAX_SIDE = 2048
_DETAIL_AREA_MM2 = 0.01
_HISTOGRAM_TILE_PIXELS = 65_536


def _literal_palette(rgba: np.ndarray, limit: int) -> np.ndarray | None:
    """Read every visible pixel, stopping as soon as the literal palette exceeds limit."""
    height, width = rgba.shape[:2]
    tile_width = min(width, _HISTOGRAM_TILE_PIXELS)
    tile_height = max(1, _HISTOGRAM_TILE_PIXELS // tile_width)
    palette: set[int] = set()
    for y in range(0, height, tile_height):
        for x in range(0, width, tile_width):
            tile = rgba[y : y + tile_height, x : x + tile_width]
            visible = tile[..., 3] >= 128
            rgb = tile[..., :3][visible].astype(np.uint32)
            packed = (rgb[:, 0] << 16) | (rgb[:, 1] << 8) | rgb[:, 2]
            values = np.unique(packed)
            if len(values) > limit:
                return None
            palette.update(int(value) for value in values)
            if len(palette) > limit:
                return None
    return np.array(sorted(palette), dtype=np.uint32)


def _packed(rgba: np.ndarray) -> np.ndarray:
    packed = rgba[..., 0].astype(np.uint32) << 16
    packed |= rgba[..., 1].astype(np.uint32) << 8
    packed |= rgba[..., 2]
    return packed


def _paint_labels(rgba: np.ndarray, palette: np.ndarray) -> np.ndarray:
    paints = np.column_stack([palette >> 16, (palette >> 8) & 255, palette & 255])
    tree = cKDTree(paints)
    labels = np.empty(rgba.shape[:2], dtype=np.uint16)
    for start in range(0, len(rgba), 32):
        stop = min(len(rgba), start + 32)
        rgb = rgba[start:stop, :, :3]
        labels[start:stop] = tree.query(rgb.reshape(-1, 3))[1].reshape(rgb.shape[:2])
    return labels


def _features(mask: np.ndarray, pixel_mm: float, *, holes: bool) -> tuple:
    groups, count = label(~mask if holes else mask, structure=_BG8 if holes else _FG4)
    included = np.ones(count + 1, dtype=bool)
    included[0] = False
    if holes:
        exterior = np.unique(np.concatenate((groups[0], groups[-1], groups[:, 0], groups[:, -1])))
        included[exterior] = False
    if not included.any():
        return groups, included, included.copy()
    counts = region_counts(groups, count)
    relevant = included & (counts >= _DETAIL_AREA_MM2 / pixel_mm**2 - 1e-9)
    return groups, included, relevant


def _compare_features(
    source: np.ndarray,
    working: np.ndarray,
    source_pixel_mm: float,
    working_pixel_mm: float,
    *,
    holes: bool,
) -> dict[str, int]:
    source_ids, included, relevant = _features(source, source_pixel_mm, holes=holes)
    target_ids, target_included, target_relevant = _features(working, working_pixel_mm, holes=holes)
    if not relevant.any():
        return {
            "source": int(included.sum()),
            "working": int(target_included.sum()),
            "relevant_source": 0,
            "lost": 0,
            "merged": 0,
            "split": 0,
            "created": int(target_relevant.sum()) if not included.any() else 0,
        }
    # Target pixel centres refer back to source cells. Counts alone miss a lost
    # accent offset by a newly created island elsewhere in the drawing.
    sy = np.minimum(
        ((np.arange(working.shape[0]) + 0.5) * source.shape[0] / working.shape[0]).astype(int),
        source.shape[0] - 1,
    )
    sx = np.minimum(
        ((np.arange(working.shape[1]) + 0.5) * source.shape[1] / working.shape[1]).astype(int),
        source.shape[1] - 1,
    )
    observed_source = source_ids[sy[:, None], sx]
    matched = included[observed_source] & target_included[target_ids]
    base = len(target_included)
    pairs = np.unique(observed_source[matched].astype(np.uint64) * base + target_ids[matched])
    sources = (pairs // base).astype(np.intp)
    targets = (pairs % base).astype(np.intp)
    source_matches = np.bincount(sources, minlength=len(included))
    significant_matches = np.bincount(sources[target_relevant[targets]], minlength=len(included))
    target_matches = np.bincount(targets[relevant[sources]], minlength=base)
    split = (significant_matches > 1) | ((significant_matches == 0) & (source_matches > 1))
    return {
        "source": int(included.sum()),
        "working": int(target_included.sum()),
        "relevant_source": int(relevant.sum()),
        "lost": int(np.count_nonzero(relevant & (source_matches == 0))),
        "merged": int(np.count_nonzero(target_matches > 1)),
        "split": int(np.count_nonzero(relevant & split)),
        "created": int(
            np.count_nonzero(target_relevant & (np.bincount(targets, minlength=base) == 0))
        ),
    }


def _audit_mask(source: np.ndarray, working: np.ndarray, sx: float, wx: float) -> dict:
    if source.all() and working.all():
        component = {
            "source": 1,
            "working": 1,
            "relevant_source": int(source.size * sx**2 >= _DETAIL_AREA_MM2),
            "lost": 0,
            "merged": 0,
            "split": 0,
            "created": 0,
        }
        return {
            "components": component,
            "holes": {key: 0 for key in component},
            "issues": 0,
            "topology_preserved": True,
        }
    components = _compare_features(source, working, sx, wx, holes=False)
    holes = _compare_features(source, working, sx, wx, holes=True)
    issues = sum(
        values[key]
        for values in (components, holes)
        for key in ("lost", "merged", "split", "created")
    )
    return {
        "components": components,
        "holes": holes,
        "issues": issues,
        "topology_preserved": all(
            values["source"] == values["working"] for values in (components, holes)
        ),
    }


def _audit(
    source: np.ndarray,
    working: np.ndarray,
    width_mm: float,
    palette: np.ndarray | None,
    *,
    paint_reference: FlatPaintReference | PaintFamilyReference | None = None,
    max_colors: int = 12,
) -> dict:
    source_visible = source[..., 3] >= 128
    working_visible = working[..., 3] >= 128
    sx = width_mm / (source.shape[1] + 2)
    wx = width_mm / (working.shape[1] + 2)
    masks = {"alpha": _audit_mask(source_visible, working_visible, sx, wx)}
    at_risk = []
    unverified_paints = []
    palette_match = {}
    if palette is not None:
        source_rgb = None if paint_reference is not None else _packed(source)
        working_rgb = _packed(working)
        working_has_blends = _literal_palette(working, len(palette)) is None
        actual_palette = None
        if paint_reference is not None:
            working_labels, actual_palette, _ = bitmap_colors(working, max_colors)
            if isinstance(paint_reference, PaintFamilyReference):
                palette_match = match_paint_families(
                    [f"#{int(value):06x}" for value in palette], actual_palette
                )
        else:
            working_labels = _paint_labels(working, palette) if working_has_blends else None
        for index, value in enumerate(palette):
            color = f"#{int(value):06x}"
            source_paint = (
                paint_reference.paint_mask(int(value))
                if paint_reference is not None
                else source_visible & (source_rgb == value)
            )
            literal_paint = working_visible & (working_rgb == value)
            if actual_palette is not None:
                matched_color = (
                    palette_match.get(color)
                    if isinstance(paint_reference, PaintFamilyReference)
                    else color
                )
                working_paint = (
                    working_labels == actual_palette.index(matched_color) + 1
                    if matched_color in actual_palette
                    else np.zeros(working_visible.shape, dtype=bool)
                )
            else:
                working_paint = (
                    literal_paint
                    if working_labels is None
                    else working_visible & (working_labels == index)
                )
            masks[color] = _audit_mask(source_paint, working_paint, sx, wx)
            source_pixels = int(source_paint.sum())
            masks[color]["source_pixels"] = source_pixels
            masks[color]["source_area_mm2"] = round(float(source_pixels * sx**2), 6)
            # The current palette recovery requires nine literal interior pixels
            # for a rare paint. Do not let interpolation make an intentional
            # small flat accent indistinguishable from an RGB edge blend.
            rare = literal_paint.sum() < 0.005 * working_visible.sum()
            if (
                not isinstance(paint_reference, PaintFamilyReference)
                and working_has_blends
                and rare
                and masks[color]["components"]["relevant_source"]
            ):
                core = binary_erosion(literal_paint, structure=_FG4)
                if core.sum() < 9:
                    at_risk.append(color)
        if actual_palette is not None:
            source_palette = (
                set(palette_match.values())
                if isinstance(paint_reference, PaintFamilyReference)
                else {f"#{int(value):06x}" for value in palette}
            )
            for index, color in enumerate(actual_palette, 1):
                if color in source_palette:
                    continue
                _, _, relevant = _features(working_labels == index, wx, holes=False)
                if relevant.any():
                    unverified_paints.append(color)
    return {
        "issues": int(
            sum(mask["issues"] for mask in masks.values()) + len(at_risk) + len(unverified_paints)
        ),
        "topology_preserved": all(mask["topology_preserved"] for mask in masks.values()),
        "palette_at_risk": at_risk,
        "masks": masks,
        **({"unverified_working_paints": sorted(unverified_paints)} if paint_reference else {}),
        **(
            {"palette_match": palette_match}
            if isinstance(paint_reference, PaintFamilyReference)
            else {}
        ),
    }


def _sample(source: np.ndarray, side: int, resampling: Image.Resampling) -> np.ndarray:
    image = Image.fromarray(source)
    image.thumbnail((side, side), resampling)
    return np.asarray(image)


def sample_bitmap(
    rgba: np.ndarray,
    physical_width_mm: float,
    *,
    max_colors: int = 12,
    recover_flat_paints: bool = True,
) -> tuple[np.ndarray, dict]:
    """Reduce cropped RGBA at 12 px/mm, adapting only to observed detail loss.

    ``physical_width_mm`` includes the pipeline's historical two padding pixels.
    Detail relevance uses 0.01 mm² (a 0.1 mm equivalent square); this is a graphic
    preservation threshold, not a claim that a needle can sew such a feature.
    Literal palettes get per-paint checks; photographs only get alpha checks.
    """
    source = np.asarray(rgba)
    if source.ndim != 3 or source.shape[-1] != 4 or source.dtype != np.uint8 or not source.size:
        raise ValueError("Bitmap sampling requires a nonempty uint8 RGBA image.")
    if source.shape[0] * source.shape[1] > _MAX_SOURCE_PIXELS:
        raise ValueError("Raster image exceeds 16 megapixels.")
    if (
        isinstance(physical_width_mm, bool)
        or not isinstance(physical_width_mm, Real)
        or not math.isfinite(physical_width_mm)
        or physical_width_mm <= 0
    ):
        raise ValueError("Bitmap sampling width must be positive finite millimetres.")
    physical_width_mm = float(physical_width_mm)
    if (
        isinstance(max_colors, bool)
        or not isinstance(max_colors, Integral)
        or not 1 <= max_colors <= 256
    ):
        raise ValueError("Bitmap palette limit must be an integer between 1 and 256.")
    if not isinstance(recover_flat_paints, bool):
        raise ValueError("Flat paint recovery must be a boolean.")
    height, width = source.shape[:2]
    longest_mm = physical_width_mm * max(width, height) / width
    first_side = min(_MAX_SIDE, max(1, round(longest_mm * 12)))
    report = {
        "policy": "topology_guarded",
        "source_pixels": [width, height],
        "source_canvas_size_mm": [
            physical_width_mm,
            physical_width_mm * (height + 2) / (width + 2),
        ],
        "source_pixel_size_mm": physical_width_mm / (width + 2),
        "max_working_side_px": _MAX_SIDE,
        "detail_area_mm2": _DETAIL_AREA_MM2,
        "detail_scope": "graphic_preservation_not_sewability",
        "attempts": [],
        "adapted": False,
        "source_palette": None,
    }
    if max(width, height) <= first_side:
        report.update(
            reference="source_unchanged",
            literal_palette_colors=None,
            working_pixels=[width, height],
            working_canvas_size_mm=report["source_canvas_size_mm"].copy(),
            working_pixel_size_mm=report["source_pixel_size_mm"],
            resampling="none",
            passed=True,
            unresolved_issues=0,
            topology_preserved=True,
        )
        return source, report
    palette = _literal_palette(source, max_colors)
    paint_reference = (
        discover_flat_paints(source, physical_width_mm, max_colors=max_colors)
        if palette is None and recover_flat_paints
        else None
    )
    reference = "source_alpha_and_literal_paints" if palette is not None else "source_alpha"
    literal_palette_colors = None if palette is None else int(len(palette))
    if paint_reference is not None:
        palette = paint_reference.palette
        reference = "source_alpha_and_flat_paint_cores"
        report["flat_paint_reference"] = paint_reference.diagnostics()
    report.update(
        reference=reference,
        literal_palette_colors=literal_palette_colors,
        source_palette=None if palette is None else [f"#{int(value):06x}" for value in palette],
    )
    second_side = min(_MAX_SIDE, max(1, round(longest_mm * 24)))
    methods = [(12, first_side, Image.Resampling.LANCZOS)]
    if second_side > first_side:
        methods.append((24, second_side, Image.Resampling.LANCZOS))
    if palette is not None:
        methods.append((24, second_side, Image.Resampling.NEAREST))
    selected = None
    best = None
    alpha_fallback = None
    alpha_best = None
    for density, side, method in methods:
        working = _sample(source, side, method)
        audit = _audit(
            source,
            working,
            physical_width_mm,
            palette,
            paint_reference=paint_reference,
            max_colors=max_colors,
        )
        attempt = {
            "target_pixels_per_mm": density,
            "working_pixels": [working.shape[1], working.shape[0]],
            "resampling": method.name.lower(),
            **audit,
        }
        report["attempts"].append(attempt)
        if paint_reference is not None and method == Image.Resampling.LANCZOS:
            if (
                alpha_best is None
                or audit["masks"]["alpha"]["issues"] < alpha_best["masks"]["alpha"]["issues"]
            ):
                alpha_fallback, alpha_best = working, attempt
        if best is None or audit["issues"] < best["issues"]:
            selected, best = working, attempt
        if audit["issues"] == 0:
            break
    # Preserve every successful literal/exact-core result. Noisy families are
    # an optional second proof; an ambiguous retry never replaces the old grid.
    if (
        literal_palette_colors is None
        and recover_flat_paints
        and (paint_reference is None or best["issues"] > 0)
    ):
        families = discover_paint_families(source, physical_width_mm, max_colors=max_colors)
        if families is not None:
            family_methods = methods.copy()
            if not any(method == Image.Resampling.NEAREST for _, _, method in family_methods):
                family_methods.append((24, second_side, Image.Resampling.NEAREST))
            attempts = []
            for density, side, method in family_methods:
                working = _sample(source, side, method)
                audit = _audit(
                    source,
                    working,
                    physical_width_mm,
                    families.palette,
                    paint_reference=families,
                    max_colors=max_colors,
                )
                attempt = {
                    "target_pixels_per_mm": density,
                    "working_pixels": [working.shape[1], working.shape[0]],
                    "resampling": method.name.lower(),
                    **audit,
                }
                attempts.append(attempt)
                if audit["issues"] == 0:
                    selected, best, paint_reference = working, attempt, families
                    report.pop("flat_paint_reference", None)
                    report.update(
                        reference="source_alpha_and_paint_families",
                        source_palette=[f"#{int(value):06x}" for value in families.palette],
                        paint_family_reference=families.diagnostics(),
                        attempts=attempts,
                    )
                    break
            else:
                report["paint_family_retry"] = {
                    "adopted": False,
                    "baseline_retained": True,
                    "reason": "unconfirmed_working_palette_or_geometry",
                    "unresolved_issues": min(attempt["issues"] for attempt in attempts),
                    "source_palette": [f"#{int(value):06x}" for value in families.palette],
                    "attempts": [
                        {
                            key: attempt[key]
                            for key in (
                                "target_pixels_per_mm",
                                "working_pixels",
                                "resampling",
                                "issues",
                                "unverified_working_paints",
                            )
                        }
                        for attempt in attempts
                    ],
                }
    if paint_reference is not None and best["issues"] > 0:
        # Estimated paint evidence must not turn a partially successful retry
        # into new unsupported thread regions. Keep the original sampling and
        # expose the unresolved checks instead of choosing an ambiguous edit.
        # Preserve the historical alpha-only adapter's Lanczos selection: its
        # 24 px/mm retry may be necessary to retain a transparent counter.
        selected, best = alpha_fallback, alpha_best
        report["flat_paint_reference"]["baseline_retained"] = True
    report.update(
        working_pixels=best["working_pixels"],
        working_canvas_size_mm=[
            physical_width_mm,
            physical_width_mm * (best["working_pixels"][1] + 2) / (best["working_pixels"][0] + 2),
        ],
        working_pixel_size_mm=physical_width_mm / (best["working_pixels"][0] + 2),
        resampling=best["resampling"],
        adapted=best is not report["attempts"][0],
        passed=best["issues"] == 0,
        unresolved_issues=best["issues"],
        topology_preserved=best["topology_preserved"],
    )
    return selected, report
