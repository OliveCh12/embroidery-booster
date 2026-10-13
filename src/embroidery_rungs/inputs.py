"""Shared bitmap tracing and explicit physical sizing, without desktop tools."""

from __future__ import annotations

import io
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import resvg_py
from PIL import Image, ImageOps, UnidentifiedImageError
from scipy.ndimage import binary_dilation, distance_transform_edt, find_objects, label
from skimage.filters import threshold_otsu
from skimage.measure import approximate_polygon, find_contours

from .background import bitmap_foreground
from .colors import bitmap_colors, clean_color_regions
from .svg_manager import MAX_INPUT_BYTES, UNITS_PER_MM, load_svg_paths

RASTER_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
MAX_RASTER_PIXELS = 16_000_000
MAX_TRACED_REGIONS = 4096


def raster_to_svg(
    input_path: str | Path,
    svg_path: str | Path,
    *,
    width_mm: float | None = None,
    threshold: int | None = None,
    invert: bool = False,
    preserve_colors: bool = False,
    max_colors: int = 12,
    background_mode: str = "auto",
    cleanup: bool = True,
    diagnostics: dict | None = None,
    hoop_size_mm: tuple[float, float] | None = None,
) -> str:
    """Trace visible paint, preserving alpha holes and enclosed opaque colours."""
    if background_mode not in ("auto", "keep", "remove"):
        raise ValueError("background mode must be 'auto', 'keep' or 'remove'.")
    if not isinstance(cleanup, bool):
        raise ValueError("cleanup must be a boolean.")
    diagnostics = diagnostics if diagnostics is not None else {}
    try:
        with Image.open(input_path) as original:
            if original.width * original.height > MAX_RASTER_PIXELS:
                raise ValueError("Raster image exceeds 16 megapixels.")
            image = ImageOps.exif_transpose(original).convert("RGBA")
            if preserve_colors and threshold is None and not invert:
                return _color_bitmap_svg(
                    image,
                    svg_path,
                    width_mm,
                    max_colors,
                    background_mode,
                    cleanup,
                    diagnostics,
                    hoop_size_mm=hoop_size_mm,
                )
            background_info = {}
            if threshold is None and not invert:
                rgba = bitmap_foreground(np.asarray(image), background_mode, background_info)
                alpha = rgba[..., 3]
                mask = alpha >= 128
            else:
                background_info.update(
                    mode=background_mode, applied=False, reason="manual_threshold_or_inversion"
                )
                alpha = np.asarray(image.getchannel("A"))
                background = Image.new("RGBA", image.size, "white")
                gray = np.asarray(Image.alpha_composite(background, image).convert("L"))
                if gray.min() == gray.max():
                    raise ValueError("No shapes found in a uniform image.")
                mask = gray <= (threshold_otsu(gray) if threshold is None else threshold)
                if threshold is None:
                    border = np.r_[mask[0], mask[-1], mask[:, 0], mask[:, -1]]
                    if border.mean() > 0.5:
                        mask = ~mask
            if invert:
                mask = ~mask
            # Threshold/inversion changes paint selection, never the explicit
            # alpha silhouette: transparent margins and counters cannot sew.
            mask &= alpha >= 128
            diagnostics.update(
                background=background_info,
                cleanup={
                    "enabled": cleanup,
                    "reason": "single_colour_silhouette",
                    "changed_pixels": 0,
                    "removed_pixels": 0,
                },
            )
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise ValueError(f"Invalid raster image: {exc}") from exc
    if not mask.any():
        raise ValueError("No shapes found in a uniform or fully transparent image.")
    _check_trace_budget(label(mask)[1])
    ys, xs = np.nonzero(mask)
    mask = np.pad(mask[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1], 1)
    height, width = mask.shape
    physical_width = width_mm if width_mm is not None else 80 * width / max(width, height)
    physical_width = _fitted_width(physical_width, width, height, hoop_size_mm, diagnostics)
    # Scale simplification to physical size, with a half-pixel upper bound.
    tolerance = min(0.5, 0.05 * width / physical_width)
    path = _trace_path(mask, tolerance)
    if not path:
        raise ValueError("No contours found in the image.")
    root = ET.Element(
        "svg",
        xmlns="http://www.w3.org/2000/svg",
        width=f"{physical_width:g}mm",
        height=f"{physical_width * height / width:g}mm",
        viewBox=f"0 0 {width} {height}",
    )
    ET.SubElement(root, "path", fill="black", attrib={"fill-rule": "evenodd", "d": path})
    ET.ElementTree(root).write(svg_path, encoding="utf-8", xml_declaration=True)
    return str(svg_path)


def _color_bitmap_svg(
    image,
    svg_path,
    width_mm,
    max_colors,
    background_mode,
    cleanup,
    diagnostics,
    *,
    pixel_size_mm=None,
    hoop_size_mm=None,
    infer_counters=True,
):
    background_info = {}
    # Flood the source before resampling: Lanczos otherwise mixes opaque blank
    # margins into the artwork and makes background-coloured islands.
    rgba = bitmap_foreground(
        np.asarray(image), background_mode, background_info, recover_edge_colors=cleanup
    )
    ys, xs = np.nonzero(rgba[..., 3] >= 128)
    if not len(ys):
        raise ValueError("No shapes found in a uniform or fully transparent image.")
    rgba = rgba[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    source_height, source_width = rgba.shape[:2]
    physical_width = (
        width_mm
        if width_mm is not None
        else (
            pixel_size_mm * (source_width + 2)
            if pixel_size_mm is not None
            else 80 * (source_width + 2) / (max(source_width, source_height) + 2)
        )
    )
    requested_width = physical_width
    physical_width = _fitted_width(
        physical_width, source_width + 2, source_height + 2, hoop_size_mm, diagnostics
    )
    # Crop first so blank canvas cannot consume the physical detail budget.
    image = Image.fromarray(rgba)
    physical_longest = physical_width * max(source_width, source_height) / source_width
    image.thumbnail(
        (min(2048, max(1, round(physical_longest * 12))),) * 2, Image.Resampling.LANCZOS
    )
    rgba = np.asarray(image)
    cleanup_info = {
        "enabled": cleanup,
        "changed_pixels": 0,
        "removed_pixels": 0,
        "changed_area_mm2": 0.0,
        "reason": "disabled_by_request",
    }
    labels, colors, reduced = bitmap_colors(
        rgba, max_colors, cleanup=cleanup, diagnostics=cleanup_info
    )
    cleanup_info.update(palette_reduced=bool(reduced), palette_colors=len(colors))
    ys, xs = np.nonzero(labels)
    labels = labels[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    rgba = rgba[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    height, width = np.array(labels.shape) + 2
    physical_width = _fitted_width(requested_width, width, height, hoop_size_mm, diagnostics)
    pixels_per_mm = width / physical_width
    if cleanup:
        labels = clean_color_regions(
            labels, colors, pixels_per_mm, cleanup_info, rgba=rgba if reduced else None
        )
    else:
        count = sum(label(labels == index)[1] for index in range(1, len(colors) + 1))
        cleanup_info.update(regions_before=count, regions_after=count)
    if cleanup_info["flat_paints_recovered"]:
        cleanup_info["regions_after_palette"] = cleanup_info["regions_before"]
        cleanup_info["regions_before"] = cleanup_info.pop("palette_regions_before")
        cleanup_info["palette_changed_area_mm2"] = (
            cleanup_info["palette_consolidated_pixels"] / pixels_per_mm**2
        )
    labels = _monochrome_counters(labels, colors, background_info, cleanup and infer_counters)
    cleanup_info["palette_colors"] = len(np.unique(labels[labels > 0]))
    cleanup_info["regions_after"] = sum(
        label(labels == index)[1] for index in range(1, len(colors) + 1)
    )
    _check_trace_budget(cleanup_info["regions_after"])
    diagnostics.update(background=background_info, cleanup=cleanup_info)
    labels = np.pad(labels, 1)
    height, width = labels.shape
    root = ET.Element(
        "svg",
        xmlns="http://www.w3.org/2000/svg",
        width=f"{physical_width:g}mm",
        height=f"{physical_width * height / width:g}mm",
        viewBox=f"0 0 {width} {height}",
    )
    tolerance = min(0.5, 0.03 * width / physical_width)
    # Thread masks are categorical paint: a second antialiasing pass would
    # recreate blended slivers and can split a narrow satin outline.
    root.set("shape-rendering", "crispEdges")
    # Independent antialiased paint contours leave cracks at shared boundaries.
    # Paint the complete alpha silhouette first, then overlay the other colours.
    # The most frequent boundary paint avoids a pale rim around dark outlines.
    visible = labels > 0
    boundary = visible & binary_dilation(~visible)
    base = int(np.bincount(labels[boundary], minlength=len(colors) + 1)[1:].argmax()) + 1
    ET.SubElement(
        root,
        "path",
        fill=colors[base - 1],
        attrib={"fill-rule": "evenodd", "d": _trace_path(visible, tolerance)},
    )
    for index, color in enumerate(colors, 1):
        if index == base:
            continue
        path = _trace_path(labels == index, tolerance)
        if path:
            ET.SubElement(root, "path", fill=color, attrib={"fill-rule": "evenodd", "d": path})
    ET.ElementTree(root).write(svg_path, encoding="utf-8", xml_declaration=True)
    return str(svg_path)


def _monochrome_counters(labels, colors, background_info, cleanup):
    background_info.update(
        counters_inferred=0,
        counter_pixels_removed=0,
        counter_inference="not_applicable",
    )
    background = background_info.get("background_color")
    if (
        not cleanup
        or not background_info["applied"]
        or len(colors) != 2
        or background not in colors
    ):
        return labels
    background_index = colors.index(background) + 1
    paint_index = 3 - background_index
    paint = np.array([int(colors[paint_index - 1][i : i + 2], 16) for i in (1, 3, 5)])
    blank = np.array([int(background[i : i + 2], 16) for i in (1, 3, 5)])
    if np.ptp(paint) > 4 or np.linalg.norm(paint - blank) < 128:
        return labels
    holes, count = label(labels == background_index)
    _check_trace_budget(count)
    paint_radius = distance_transform_edt(labels == paint_index)
    hole_radius = distance_transform_edt(holes > 0)
    result = labels.copy()
    removed = inferred = compact = 0
    for index, box in enumerate(find_objects(holes), 1):
        mask = holes[box] == index
        height, width = mask.shape
        if max(height, width) / min(height, width) < 2 and mask.mean() > 0.65:
            compact += 1
            continue
        radius = float(hole_radius[box][mask].max())
        padding = max(6, int(np.ceil(radius)))
        patch = tuple(
            slice(max(0, axis.start - padding), min(size, axis.stop + padding))
            for axis, size in zip(box, labels.shape, strict=True)
        )
        local_hole = holes[patch] == index
        neighbours = (distance_transform_edt(~local_hole) <= padding) & (
            labels[patch] == paint_index
        )
        if not neighbours.any():
            continue
        # Broad monochrome strokes support a counter interpretation. A thin
        # outline around a large white centre supplies evidence for a badge.
        stroke = float(np.percentile(paint_radius[patch][neighbours], 75))
        if stroke <= max(2.0, 0.65 * radius):
            continue
        result[box][mask] = 0
        removed += int(mask.sum())
        inferred += 1
    background_info.update(
        counters_inferred=inferred,
        counter_pixels_removed=removed,
        counter_inference=(
            "monochrome_broad_strokes"
            if inferred
            else "compact_interior_preserved"
            if compact
            else "thin_outline_preserved"
        ),
    )
    return result


def _trace_path(mask: np.ndarray, tolerance: float) -> str:
    parts = []
    for contour in find_contours(mask, 0.5):
        contour = approximate_polygon(contour, tolerance=tolerance)
        if len(contour) >= 4:
            parts.append("M " + " L ".join(f"{x:.3f},{y:.3f}" for y, x in contour) + " Z")
    return " ".join(parts)


def _fitted_width(width_mm, width, height, hoop_size_mm, diagnostics):
    effective = width_mm
    if hoop_size_mm is not None:
        effective = min(width_mm, hoop_size_mm[0] - 2, (hoop_size_mm[1] - 2) * width / height)
    diagnostics["sizing"] = {
        "requested_width_mm": float(width_mm),
        "effective_width_mm": float(effective),
        "effective_height_mm": float(effective * height / width),
        "fitted": bool(effective < width_mm - 1e-6),
    }
    return effective


def _check_trace_budget(regions):
    if regions > MAX_TRACED_REGIONS:
        raise ValueError(
            f"Bitmap contains {regions} visible regions after interpretation; the limit is {MAX_TRACED_REGIONS}. Enable raster cleanup, reduce colours, or simplify the image."
        )


def convert_to_svg(input_path, work_dir):
    """Return SVG artwork or trace a supported bitmap without external tools."""
    file = Path(input_path)
    ext = file.suffix.lower()
    if ext == ".svg":
        return str(file)
    destination = Path(work_dir) / (file.stem + ".svg")
    if ext in RASTER_EXT:
        return raster_to_svg(file, destination)
    raise ValueError(_unsupported_format(ext))


def _unsupported_format(extension: str) -> str:
    return (
        f"Unsupported file type: {extension or 'unknown'}. "
        "Use SVG, PNG, JPEG, WebP, BMP, GIF or TIFF; export other artwork to SVG first."
    )


def prepare_artwork(source, directory, params, stitch_params, *, preserve_colors=False):
    """Keep SVG bytes by default; sizing/conversion is opt-in except bitmap scale."""
    source, directory = Path(source), Path(directory)
    if source.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("Input exceeds the 10 MiB limit.")
    converted = source.suffix.lower() in RASTER_EXT
    input_analysis = {}
    hoop_size = (
        (stitch_params.hoop_width_mm, stitch_params.hoop_height_mm) if params.fit_to_hoop else None
    )
    if converted:
        prepared = Path(
            raster_to_svg(
                source,
                directory / f"{source.stem}.svg",
                width_mm=params.design_width_mm,
                threshold=params.raster_threshold,
                invert=params.raster_invert,
                preserve_colors=preserve_colors,
                max_colors=stitch_params.max_colors,
                background_mode=params.background_mode,
                cleanup=params.raster_cleanup,
                diagnostics=input_analysis,
                hoop_size_mm=hoop_size,
            )
        )
    elif source.suffix.lower() == ".svg":
        prepared = source
        input_analysis.update(
            background={
                "mode": params.background_mode,
                "applied": False,
                "reason": "explicit_vector_paint",
            },
            cleanup={
                "enabled": params.raster_cleanup,
                "reason": "vector_artwork_preserved",
                "changed_pixels": 0,
                "removed_pixels": 0,
            },
        )
        if params.background_mode == "remove":
            svg, _ = load_svg_paths(source)
            longest_mm = max(svg.width, svg.height) / UNITS_PER_MM
            side = min(2048, max(1, round(longest_mm * 12)))
            size = {"width": side} if svg.width >= svg.height else {"height": side}
            png = resvg_py.svg_to_bytes(svg_string=svg.xml, dpi=96, skip_system_fonts=True, **size)
            with Image.open(io.BytesIO(png)) as rendered:
                prepared = Path(
                    _color_bitmap_svg(
                        rendered.convert("RGBA"),
                        directory / f"{source.stem}.svg",
                        params.design_width_mm,
                        stitch_params.max_colors,
                        "remove",
                        params.raster_cleanup,
                        input_analysis,
                        pixel_size_mm=svg.width / UNITS_PER_MM / rendered.width,
                        hoop_size_mm=hoop_size,
                        infer_counters=False,
                    )
                )
    else:
        raise ValueError(_unsupported_format(source.suffix.lower()))
    warnings = []
    if converted:
        warnings.append(
            "Bitmap traced with a bounded colour palette. Check the interpreted artwork before sewing."
            if preserve_colors and params.raster_threshold is None and not params.raster_invert
            else "Bitmap traced as a single-colour silhouette. Check the interpreted artwork before sewing."
        )
    elif params.background_mode == "remove":
        warnings.append(
            "SVG rasterized and retraced for explicit border-connected background removal; physical scale is preserved."
        )
    if input_analysis["background"]["applied"]:
        model = input_analysis["background"].get("model")
        counters = input_analysis["background"].get("counters_inferred", 0)
        if counters:
            warnings.append(
                f"Inferred {counters} background-coloured counters inside broad monochrome strokes. This interpretation is geometric; choose Keep or disable bitmap cleanup to preserve opaque interior paint."
            )
        else:
            warnings.append(
                "Only the smooth gradient connected to the image border was removed; enclosed opaque colours remain embroidery regions."
                if model == "smooth_gradient"
                else "Only the background connected to the image border was removed; enclosed opaque colours remain embroidery regions."
            )
        if input_analysis["background"].get("edge_refined_pixels"):
            warnings.append(
                "Background blending and compression fringes were refined at exterior contours; inspect the interpreted artwork for very fine edge details."
            )
        if input_analysis["background"].get("edge_recovered_pixels"):
            warnings.append(
                "Background colour contamination was removed from retained contour pixels before palette assignment; disable bitmap cleanup to keep their original RGB."
            )
    elif input_analysis["background"]["reason"] == "ambiguous_perimeter":
        warnings.append(
            "Background kept because the image perimeter is ambiguous; choose Keep or Remove explicitly after checking the artwork."
        )
    cleaning = input_analysis["cleanup"]
    if cleaning.get("changed_pixels"):
        warnings.append(
            f"Reduced {cleaning['changed_pixels']} small adjacent colour speckles ({cleaning['changed_area_mm2']:.2f} mm²); isolated or contrasting accents were preserved. Disable raster cleanup to retain every colour detail."
        )
    if cleaning.get("flat_paints_recovered"):
        warnings.append(
            f"Recovered {cleaning['palette_colors']} flat paints from compressed colour shades; {cleaning['retained_accent_colors']} additional accent colours were preserved. Background and tiny detail interpretation still need a preview check."
        )
    if input_analysis.get("sizing", {}).get("fitted"):
        sizing = input_analysis["sizing"]
        warnings.append(
            f"Artwork sized to {sizing['effective_width_mm']:.1f} × {sizing['effective_height_mm']:.1f} mm."
        )
    if params.design_width_mm is None and not params.fit_to_hoop:
        return prepared, warnings, input_analysis
    svg, _ = load_svg_paths(prepared)
    width, height = svg.width / UNITS_PER_MM, svg.height / UNITS_PER_MM
    factor = params.design_width_mm / width if params.design_width_mm is not None else 1.0
    if params.fit_to_hoop:
        factor = min(
            factor,
            (stitch_params.hoop_width_mm - 2) / width,
            (stitch_params.hoop_height_mm - 2) / height,
        )
    if abs(factor - 1) < 1e-6:
        return prepared, warnings, input_analysis
    # Explicit viewBox is essential for SVGs whose geometry uses bare CSS pixels.
    if not svg.root.get("viewBox"):
        svg.root.set("viewBox", f"0 0 {svg.width:g} {svg.height:g}")
    svg.root.set("width", f"{width * factor:.9g}mm")
    svg.root.set("height", f"{height * factor:.9g}mm")
    prepared = directory / f"{source.stem}.svg"
    ET.ElementTree(svg.root).write(prepared, encoding="utf-8", xml_declaration=True)
    warnings.append(f"Artwork sized to {width * factor:.1f} × {height * factor:.1f} mm.")
    return prepared, warnings, input_analysis
