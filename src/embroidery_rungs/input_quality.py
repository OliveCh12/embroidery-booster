"""Source sampling diagnostics, independent of stitch coverage or sew-out quality."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

from .svg_manager import UNITS_PER_MM, SVGDocument

# A 0.25 mm contour transition has three samples at our 12 px/mm working target.
# Lower thresholds are advice, never a reason to reject simple low-res artwork.
TARGET_PIXELS_PER_MM = 12.0


def raster_quality(
    *,
    source_pixels: Sequence[int],
    artwork_pixels: Sequence[int],
    working_pixels: Sequence[int],
    physical_size_mm: Sequence[float],
    source_format: str,
    cleanup: dict,
    monochrome: bool = False,
) -> dict:
    pixels_per_mm = min(
        artwork_pixels[0] / physical_size_mm[0], artwork_pixels[1] / physical_size_mm[1]
    )
    issues = []
    status = "good"
    if pixels_per_mm < 3:
        issues.append("very_low_resolution")
        status = "poor"
    elif pixels_per_mm < 6:
        issues.append("low_resolution")
        status = "caution"
    reduced = cleanup.get("palette_reduced", False)
    kind = (
        "monochrome"
        if monochrome
        else (
            "many_shades"
            if reduced and not cleanup.get("flat_paints_recovered")
            else "flat_artwork"
        )
    )
    if kind == "many_shades":
        issues.append("many_shades")
        if status == "good":
            status = "caution"
    if reduced:
        issues.append("palette_reduced")
    if source_format.upper() in ("JPEG", "JPG"):
        issues.append("lossy_source")
    return {
        "source_type": "raster",
        "format": source_format.upper(),
        "status": status,
        "kind": kind,
        "source_pixels": list(source_pixels),
        "artwork_pixels": list(artwork_pixels),
        "working_pixels": list(working_pixels),
        "physical_size_mm": list(physical_size_mm),
        "pixels_per_mm": pixels_per_mm,
        "effective_dpi": pixels_per_mm * 25.4,
        "recommended_pixels": [math.ceil(size * TARGET_PIXELS_PER_MM) for size in physical_size_mm],
        "recommended_width_mm": artwork_pixels[0] / TARGET_PIXELS_PER_MM,
        "detail_sample_mm": 3 / pixels_per_mm,
        "region_count": cleanup.get("regions_after"),
        "color_count": cleanup.get("palette_colors", 1 if monochrome else None),
        "issues": issues,
    }


def complete_input_analysis(
    svg: SVGDocument, diagnostics: dict, *, source_is_vector: bool = False
) -> None:
    """Use final document dimensions, including explicit sizing and hoop fitting."""
    # SVG unit conversion can differ by a few 1e-5 mm. This is far below the
    # machine's 0.1 mm grid, but must not add a pixel or flip a threshold.
    size = [round(svg.width / UNITS_PER_MM, 4), round(svg.height / UNITS_PER_MM, 4)]
    if source_is_vector:
        retraced = diagnostics.get("cleanup", {}).get("reason") != "vector_artwork_preserved"
        gradient_ids = {
            element.get("id")
            for element in svg.root.iter()
            if element.tag.rsplit("}", 1)[-1] in ("linearGradient", "radialGradient")
        }
        # Exporters often leave unused gradient definitions in a flat logo.
        references = set(re.findall(r"url\(\s*['\"]?#([^\s'\")]+)", svg.xml))
        gradients = bool(gradient_ids & references)
        issues = (["svg_background_retraced"] if retraced else []) + (
            ["many_shades"] if gradients else []
        )
        diagnostics["quality"] = {
            "source_type": "vector",
            "format": "SVG",
            "status": "caution" if issues else "good",
            "kind": "vector",
            "source_pixels": None,
            "artwork_pixels": None,
            "working_pixels": diagnostics.get("quality", {}).get("working_pixels"),
            "physical_size_mm": size,
            "pixels_per_mm": None,
            "effective_dpi": None,
            "recommended_pixels": None,
            "recommended_width_mm": None,
            "detail_sample_mm": None,
            "region_count": diagnostics.get("cleanup", {}).get("regions_after"),
            "color_count": diagnostics.get("cleanup", {}).get("palette_colors"),
            "issues": issues,
        }
    else:
        quality = diagnostics["quality"]
        diagnostics["quality"] = raster_quality(
            source_pixels=quality["source_pixels"],
            artwork_pixels=quality["artwork_pixels"],
            working_pixels=quality["working_pixels"],
            physical_size_mm=size,
            source_format=quality["format"],
            cleanup=diagnostics["cleanup"],
            monochrome=quality["kind"] == "monochrome",
        )


def quality_warnings(quality: dict) -> list[str]:
    """Library/CLI advice mirrors the preflight; never changes stitch density."""
    warnings = []
    if "very_low_resolution" in quality["issues"] or "low_resolution" in quality["issues"]:
        width, height = quality["recommended_pixels"]
        warnings.append(
            f"Limited source resolution at the embroidery size ({quality['pixels_per_mm']:.1f} px/mm). "
            f"For detailed contours, use original vector SVG or artwork of about {width} × {height} px; "
            "enlarging the bitmap cannot recover missing detail."
        )
    if "many_shades" in quality["issues"]:
        warnings.append(
            "Many colour shades were reduced to thread paints. Check the interpreted artwork; "
            "photos and gradients cannot retain every tonal detail as flat embroidery regions."
        )
    return warnings
