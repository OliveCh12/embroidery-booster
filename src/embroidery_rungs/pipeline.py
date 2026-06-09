"""Core processing pipeline.

This module exposes a single high-level entry point, :func:`generate`, that turns
an input SVG into rung/ready SVG files. Both the CLI and the web server are thin
clients of this function — they must never reach into the lower-level modules
directly or duplicate the orchestration logic below.
"""

import os
import shutil
import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from skimage.draw import line
from skimage.morphology import dilation, disk
from svgelements import Matrix

from .svg_manager import load_svg_paths, save_rungs_svg, save_combined_svg, save_satin_svg
from .image_processor import rasterize_paths, compute_medial_axis
from .rung_generator import generate_rungs
from .debug_utils import save_debug_images
from .optimizer import optimize_rung_parameters
from .routing import route_columns

logger = logging.getLogger(__name__)


@dataclass
class GenerationParams:
    """User-tunable parameters for a generation run."""

    spacing: float = 3.0          # rung spacing in mm
    density: float = 1.0          # density multiplier (higher = more rungs)
    dpi: int = 150                # processing DPI
    debug: bool = False           # save debug images
    auto_optimize: bool = False   # search for optimal spacing/density


@dataclass
class GenerationResult:
    """Structured result of a generation run."""

    rungs_count: int
    bridges_count: int
    columns_count: int
    coverage: float                       # 0..1, or -1.0 when not computed
    original_path: str
    rungs_path: str
    ready_path: str
    satin_path: str
    debug_dir: Optional[str] = None
    params: GenerationParams = field(default_factory=GenerationParams)


_WORLD_UNITS_PER_MM = 96.0 / 25.4  # SVG default: 1 user unit = 1px @ 96 dpi


def image_scale(transform) -> float:
    """Image pixels per SVG user unit, recovered from the world->image matrix."""
    return float(np.sqrt(abs(transform.a * transform.d - transform.b * transform.c)))


def spacing_to_px(spacing_mm: float, density: float, scale: float) -> float:
    """Convert a spacing in millimetres to image pixels.

    ``spacing_mm`` is interpreted in real-world millimetres and mapped through the
    actual rasterization scale, so density no longer depends on image resolution.
    """
    return (spacing_mm / density) * _WORLD_UNITS_PER_MM * scale


def _viewbox_offset(svg):
    """Return the (x, y) ViewBox offset, or None when there is nothing to correct."""
    if not svg.viewbox:
        return None
    offset_x, offset_y = svg.viewbox.x, svg.viewbox.y
    if offset_x == 0 and offset_y == 0:
        return None
    return offset_x, offset_y


def compute_coverage(binary_img, rungs) -> float:
    """Fraction of shape pixels covered by the generated rungs (0..1)."""
    total = np.sum(binary_img > 0)
    if total == 0 or not rungs:
        return 0.0

    coverage = np.zeros_like(binary_img, dtype=np.uint8)
    h, w = coverage.shape
    for (p1_x, p1_y), (p2_x, p2_y) in rungs:
        rr, cc = line(int(p1_y), int(p1_x), int(p2_y), int(p2_x))
        valid = (rr >= 0) & (rr < h) & (cc >= 0) & (cc < w)
        coverage[rr[valid], cc[valid]] = 255

    coverage_dilated = dilation(coverage, disk(2))
    covered = np.sum((binary_img > 0) & (coverage_dilated > 0))
    return float(covered / total)


def generate(input_path: str, output_dir: str = "output",
             params: Optional[GenerationParams] = None) -> GenerationResult:
    """Generate rungs for ``input_path`` and write the output SVGs to ``output_dir``.

    Returns a :class:`GenerationResult` describing the run. Does not open any
    external viewer — that is the caller's responsibility.
    """
    params = params or GenerationParams()

    os.makedirs(output_dir, exist_ok=True)
    debug_dir = os.path.join(output_dir, "debug")
    if params.debug:
        os.makedirs(debug_dir, exist_ok=True)

    input_filename = os.path.basename(input_path)
    base_name, _ = os.path.splitext(input_filename)
    path_original = os.path.join(output_dir, input_filename)
    path_rungs = os.path.join(output_dir, f"{base_name}_rungs.svg")
    path_ready = os.path.join(output_dir, f"{base_name}_ready.svg")
    path_satin = os.path.join(output_dir, f"{base_name}_satin.svg")

    logger.info(f"Processing {input_path}...")
    shutil.copy2(input_path, path_original)

    svg, paths = load_svg_paths(input_path)
    if not paths:
        logger.warning("No paths found in SVG.")
        raise ValueError("No paths found in SVG.")

    offset = _viewbox_offset(svg)

    # Rasterize and build the World -> Image transform.
    binary_img, transform, _dims = rasterize_paths(
        svg, paths, params.dpi, svg_filename=os.path.abspath(input_path))
    if offset is not None:
        logger.info(f"Applying ViewBox offset correction: {offset}")
        transform = Matrix.translate(-offset[0], -offset[1]) * transform

    scale = image_scale(transform)
    skeleton, distance, cleaned_binary = compute_medial_axis(binary_img)

    if params.debug:
        save_debug_images(debug_dir, binary_img, cleaned_binary, distance, skeleton)

    spacing, density = params.spacing, params.density
    if params.auto_optimize:
        logger.info("Auto-optimization enabled")
        best = optimize_rung_parameters(skeleton, distance, binary_img, scale)
        if best:
            spacing, density = best[0], best[1]
            logger.info(f"Optimal parameters applied: spacing={spacing}mm, density={density}")
        else:
            logger.warning("Optimization failed, using default parameters")

    spacing_px = spacing_to_px(spacing, density, scale)
    rungs, bridges, columns = generate_rungs(
        skeleton, distance, spacing_px, binary_img,
        debug_dir=debug_dir if params.debug else None)

    coverage = compute_coverage(binary_img, rungs)
    columns = route_columns(columns)

    save_rungs_svg(path_rungs, rungs, bridges, transform)
    save_combined_svg(input_path, path_ready, rungs, bridges, transform)
    save_satin_svg(path_satin, columns, transform, svg)

    logger.info(
        f"Done! {len(rungs)} rungs, {len(columns)} satin columns, "
        f"{len(bridges)} bridges, {coverage:.1%} coverage -> '{output_dir}/'")

    return GenerationResult(
        rungs_count=len(rungs),
        bridges_count=len(bridges),
        columns_count=len(columns),
        coverage=coverage,
        original_path=path_original,
        rungs_path=path_rungs,
        ready_path=path_ready,
        satin_path=path_satin,
        debug_dir=debug_dir if params.debug else None,
        params=GenerationParams(spacing=spacing, density=density, dpi=params.dpi,
                                debug=params.debug, auto_optimize=params.auto_optimize),
    )
