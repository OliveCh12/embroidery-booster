"""Visible-region diagnostics and bounded physical sewing adjustments."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
from scipy.ndimage import binary_fill_holes, distance_transform_edt, label, maximum
from skimage.measure import perimeter_crofton

from .params import MACHINE_PROFILES, StitchParams


def adjust_for_sewing(params: StitchParams) -> tuple[StitchParams, list[dict]]:
    """Keep ordinary presets; bound extremes consistently across the whole design."""
    params.validate()
    effective, adjustments = replace(params), []
    if not params.auto_adjust:
        return effective, adjustments

    def change(parameter, value, reason):
        requested = getattr(params, parameter)
        if value != requested:
            setattr(effective, parameter, value)
            adjustments.append(
                {
                    "parameter": parameter,
                    "requested": requested,
                    "effective": value,
                    "reason": reason,
                }
            )

    factor = {30: 1.25, 40: 1.0, 60: 0.75}[params.thread_weight]
    reference = round({"stretch": 0.45, "textured": 0.35}.get(params.fabric, 0.4) * factor, 3)
    low, high = (0.7, 1.5) if params.fabric == "custom" else (0.8, 1.25)
    for name in ("satin_spacing_mm", "fill_spacing_mm"):
        # More geometry does not justify more density: extra thread can pucker
        # fabric. Only clearly sparse/dense requests leave the material range.
        value = round(
            float(np.clip(getattr(params, name), max(0.2, low * reference), high * reference)), 3
        )
        change(name, value, "material_density_range")
    if params.fabric in ("stretch", "textured"):
        change("underlay", True, "unstable_fabric_requires_underlay")
    compensation_limit = {"stretch": 0.35, "textured": 0.3}.get(params.fabric, 0.25)
    change(
        "pull_compensation_mm",
        min(params.pull_compensation_mm, compensation_limit),
        "excessive_pull_compensation",
    )
    # Leave room for compensation and the 0.1 mm machine grid. Wider regions
    # become coherent fill instead of acquiring split stitches through satin.
    width_limit = min(
        MACHINE_PROFILES[params.machine]["max_satin_width"],
        max(2.0, params.max_stitch_mm - 0.2 - 2 * effective.pull_compensation_mm),
    )
    change(
        "max_satin_width_mm", min(params.max_satin_width_mm, width_limit), "safe_satin_float_limit"
    )
    effective.validate()
    return effective, adjustments


def analyze_regions(labels, pixels_per_mm, params, *, palette_reduced=False):
    """Describe the interpreted colour geometry, without guessing image semantics."""
    minimum_width = max(
        2 * params.min_stitch_mm, {30: 0.75, 40: 0.6, 60: 0.45}[params.thread_weight]
    )
    colors = np.unique(labels[labels > 0])
    regions, holes, fine_pixels, boundary = 0, 0, 0, 0.0
    background_structure = np.ones((3, 3), dtype=bool)
    for color in colors:
        mask = labels == color
        components, count = label(mask)
        regions += count
        areas = np.bincount(components.ravel())[1:]
        widths = 2 * maximum(distance_transform_edt(mask), components, np.arange(1, count + 1))
        fine_pixels += int(areas[widths / pixels_per_mm < minimum_width].sum())
        holes += label(
            binary_fill_holes(mask, structure=background_structure) & ~mask,
            structure=background_structure,
        )[1]
        boundary += perimeter_crofton(mask, directions=4) / pixels_per_mm
    pixels = int(np.count_nonzero(labels))
    category = (
        "complex"
        if regions > 32 or holes > 8
        else "multicolor"
        if len(colors) > 1
        else "monochrome"
    )
    return {
        "category": category,
        "topology_basis": "visible_color_regions",
        "color_count": len(colors),
        "region_count": regions,
        "hole_count": holes,
        "area_mm2": round(pixels / pixels_per_mm**2, 2),
        "boundary_length_mm": round(boundary, 2),
        "fine_region_area_ratio": round(fine_pixels / pixels, 4),
        "palette_reduced": bool(palette_reduced),
    }
