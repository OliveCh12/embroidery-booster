"""Shared bitmap tracing and explicit physical sizing, without desktop tools."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from skimage.filters import threshold_otsu
from skimage.measure import approximate_polygon, find_contours

from .colors import bitmap_foreground, separate_colors
from .external import _run, _tool
from .svg_manager import MAX_INPUT_BYTES, UNITS_PER_MM, load_svg_paths

RASTER_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
VECTOR_EXT = {".pdf", ".eps", ".ps", ".ai"}
MAX_RASTER_PIXELS = 16_000_000


def raster_to_svg(
    input_path: str | Path,
    svg_path: str | Path,
    *,
    width_mm: float | None = None,
    threshold: int | None = None,
    invert: bool = False,
    preserve_colors: bool = False,
    max_colors: int = 12,
) -> str:
    """Trace a monochrome silhouette; crop blank margins and preserve holes."""
    try:
        with Image.open(input_path) as original:
            if original.width * original.height > MAX_RASTER_PIXELS:
                raise ValueError("Raster image exceeds 16 megapixels.")
            image = ImageOps.exif_transpose(original).convert("RGBA")
            if preserve_colors and threshold is None and not invert:
                return _color_bitmap_svg(image, svg_path, width_mm, max_colors)
            alpha = np.asarray(image.getchannel("A"))
            if alpha.min() < 255 and threshold is None:
                mask = alpha >= 128
            else:
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
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise ValueError(f"Invalid raster image: {exc}") from exc
    if not mask.any() or mask.all():
        raise ValueError("No distinct visible shapes found in the image.")
    ys, xs = np.nonzero(mask)
    mask = np.pad(mask[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1], 1)
    height, width = mask.shape
    physical_width = width_mm if width_mm is not None else 80 * width / max(width, height)
    parts = []
    # Scale simplification to physical size, with a half-pixel upper bound.
    tolerance = min(0.5, 0.05 * width / physical_width)
    for contour in find_contours(mask.astype(np.uint8), 0.5):
        contour = approximate_polygon(contour, tolerance=tolerance)
        if len(contour) >= 4:
            parts.append("M " + " L ".join(f"{x:.3f},{y:.3f}" for y, x in contour) + " Z")
    if not parts:
        raise ValueError("No contours found in the image.")
    root = ET.Element(
        "svg",
        xmlns="http://www.w3.org/2000/svg",
        width=f"{physical_width:g}mm",
        height=f"{physical_width * height / width:g}mm",
        viewBox=f"0 0 {width} {height}",
    )
    ET.SubElement(root, "path", fill="black", attrib={"fill-rule": "evenodd", "d": " ".join(parts)})
    ET.ElementTree(root).write(svg_path, encoding="utf-8", xml_declaration=True)
    return str(svg_path)


def _color_bitmap_svg(image, svg_path, width_mm, max_colors):
    # Preserve physical detail (~0.08 mm) without tracing camera-sized noise.
    longest_mm = max(80.0, width_mm or 80.0)
    image.thumbnail((min(2048, round(longest_mm * 12)),) * 2, Image.Resampling.LANCZOS)
    rgba = bitmap_foreground(np.asarray(image))
    labels, colors, _ = separate_colors(rgba, max_colors)
    ys, xs = np.nonzero(labels)
    labels = np.pad(labels[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1], 1)
    height, width = labels.shape
    physical_width = width_mm if width_mm is not None else 80 * width / max(width, height)
    root = ET.Element(
        "svg",
        xmlns="http://www.w3.org/2000/svg",
        width=f"{physical_width:g}mm",
        height=f"{physical_width * height / width:g}mm",
        viewBox=f"0 0 {width} {height}",
    )
    tolerance = min(0.5, 0.03 * width / physical_width)
    for index, color in enumerate(colors, 1):
        parts = []
        for contour in find_contours(labels == index, 0.5):
            contour = approximate_polygon(contour, tolerance=tolerance)
            if len(contour) >= 4:
                parts.append("M " + " L ".join(f"{x:.3f},{y:.3f}" for y, x in contour) + " Z")
        if parts:
            ET.SubElement(
                root, "path", fill=color, attrib={"fill-rule": "evenodd", "d": " ".join(parts)}
            )
    ET.ElementTree(root).write(svg_path, encoding="utf-8", xml_declaration=True)
    return str(svg_path)


def convert_to_svg(input_path, work_dir):
    file = Path(input_path)
    ext = file.suffix.lower()
    if ext == ".svg":
        return str(file)
    destination = Path(work_dir) / (file.stem + ".svg")
    if ext in RASTER_EXT:
        return raster_to_svg(file, destination)
    if ext in VECTOR_EXT:
        executable = _tool("inkscape")
        if not executable:
            raise ValueError("Inkscape is required to convert PDF/EPS/PS/AI.")
        _run(
            [
                executable,
                str(file),
                "--export-type=svg",
                "--export-plain-svg",
                f"--export-filename={destination}",
            ]
        )
        if not destination.is_file():
            raise RuntimeError("Conversion to SVG failed.")
        return str(destination)
    raise ValueError(f"Unsupported file type: {ext or 'unknown'}")


def prepare_artwork(source, directory, params, stitch_params, *, preserve_colors=False):
    """Keep SVG bytes by default; sizing/conversion is opt-in except bitmap scale."""
    source, directory = Path(source), Path(directory)
    if source.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("Input exceeds the 10 MiB limit.")
    converted = source.suffix.lower() in RASTER_EXT
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
            )
        )
    elif source.suffix.lower() in VECTOR_EXT:
        prepared = Path(convert_to_svg(source, directory))
    elif source.suffix.lower() == ".svg":
        prepared = source
    else:
        raise ValueError("Expected SVG, bitmap or an Inkscape-supported PDF/EPS/PS/AI file.")
    warnings = []
    if converted:
        warnings.append(
            "Bitmap traced with a bounded colour palette and automatic background removal. Check the interpreted artwork before sewing."
            if preserve_colors and params.raster_threshold is None and not params.raster_invert
            else "Bitmap traced as a single-colour silhouette. Check the interpreted artwork before sewing."
        )
    if params.design_width_mm is None and not params.fit_to_hoop:
        return prepared, warnings
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
        return prepared, warnings
    # Explicit viewBox is essential for SVGs whose geometry uses bare CSS pixels.
    if not svg.root.get("viewBox"):
        svg.root.set("viewBox", f"0 0 {svg.width:g} {svg.height:g}")
    svg.root.set("width", f"{width * factor:.9g}mm")
    svg.root.set("height", f"{height * factor:.9g}mm")
    prepared = directory / f"{source.stem}.svg"
    ET.ElementTree(svg.root).write(prepared, encoding="utf-8", xml_declaration=True)
    warnings.append(f"Artwork sized to {width * factor:.1f} × {height * factor:.1f} mm.")
    return prepared, warnings
