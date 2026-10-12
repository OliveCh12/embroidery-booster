"""Library-first orchestration shared by CLI and web."""

from __future__ import annotations

import logging
import math
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image, ImageDraw

from .image_processor import compute_medial_axis, rasterize_svg
from .inputs import prepare_artwork
from .routing import route_columns
from .rung_generator import generate_rungs
from .stitching.export import DirectGenerationResult, export_direct
from .stitching.params import StitchParams
from .svg_manager import (
    UNITS_PER_MM,
    load_svg_paths,
    save_combined_svg,
    save_rungs_svg,
    save_satin_svg,
)

logger = logging.getLogger(__name__)
MIN_SATIN_WIDTH_MM = 1.5


@dataclass
class GenerationParams:
    spacing: float = 3.0
    density: float = 1.0
    dpi: int = 150
    debug: bool = False
    auto_optimize: bool = False
    design_width_mm: float | None = None
    fit_to_hoop: bool = False
    raster_threshold: int | None = None
    raster_invert: bool = False

    def validate(self) -> None:
        if self.design_width_mm is not None and (
            not isinstance(self.design_width_mm, (int, float))
            or isinstance(self.design_width_mm, bool)
            or not math.isfinite(self.design_width_mm)
            or not 1 <= self.design_width_mm <= 500
        ):
            raise ValueError("design_width_mm must be between 1 and 500 mm.")
        if self.raster_threshold is not None and (
            not isinstance(self.raster_threshold, int)
            or isinstance(self.raster_threshold, bool)
            or not 0 <= self.raster_threshold <= 255
        ):
            raise ValueError("raster_threshold must be an integer between 0 and 255.")
        if not isinstance(self.fit_to_hoop, bool) or not isinstance(self.raster_invert, bool):
            raise ValueError("fit_to_hoop and raster_invert must be booleans.")
        for name in ("spacing", "density"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a positive finite number.")
        if (
            not isinstance(self.dpi, int)
            or isinstance(self.dpi, bool)
            or not 36 <= self.dpi <= 2400
        ):
            raise ValueError("dpi must be an integer between 36 and 2400.")
        if self.spacing / self.density < 0.1:
            raise ValueError("Effective rung spacing must be at least 0.1 mm.")


@dataclass
class GenerationResult:
    rungs_count: int
    bridges_count: int
    columns_count: int
    running_count: int
    coverage: float
    original_path: str
    rungs_path: str
    ready_path: str
    satin_path: str
    debug_dir: str | None = None
    params: GenerationParams = field(default_factory=GenerationParams)
    warnings: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    direct: DirectGenerationResult | None = None
    artwork_size_mm: tuple[float, float] = (0.0, 0.0)


def image_scale(transform) -> float:
    return float(np.sqrt(abs(transform.a * transform.d - transform.b * transform.c)))


def spacing_to_px(spacing_mm: float, density: float, scale: float) -> float:
    return spacing_mm / density * UNITS_PER_MM * scale


def coverage_mask(binary_img, elements, pixels_per_mm=6.0):
    """Rasterize swept satin quads and physical-width running stitches."""
    image = Image.new("1", (binary_img.shape[1], binary_img.shape[0]))
    draw = ImageDraw.Draw(image)
    for element in elements:
        if element["type"] == "running":
            draw.line(
                [tuple(p) for p in element["points"]],
                fill=1,
                width=max(1, round(0.3 * pixels_per_mm)),
            )
        else:
            a, b = element["rail_a"], element["rail_b"]
            for i in range(len(a) - 1):
                draw.polygon([tuple(a[i]), tuple(a[i + 1]), tuple(b[i + 1]), tuple(b[i])], fill=1)
    return np.asarray(image, dtype=bool)


def compute_coverage(binary_img, elements, pixels_per_mm=6.0) -> float:
    total = np.count_nonzero(binary_img)
    return (
        float(
            np.count_nonzero(coverage_mask(binary_img, elements, pixels_per_mm) & binary_img)
            / total
        )
        if total
        else 0.0
    )


def generate(
    input_path: str | os.PathLike,
    output_dir: str | os.PathLike = "output",
    params: GenerationParams | None = None,
    *,
    method: Literal["inkstitch", "direct", "both"] = "inkstitch",
    stitch_params: StitchParams | None = None,
) -> GenerationResult:
    """Generate editable SVGs; validate before writing and stage outputs atomically."""
    started = time.perf_counter()
    params = replace(params) if params else GenerationParams()
    params.validate()
    if method not in ("inkstitch", "direct", "both"):
        raise ValueError("method must be 'inkstitch', 'direct' or 'both'.")
    stitch_params = replace(stitch_params) if stitch_params else StitchParams()
    if method != "inkstitch" or params.fit_to_hoop:
        stitch_params.validate()
    input_source = Path(input_path).resolve()
    with tempfile.TemporaryDirectory(prefix="embroidery-input-") as temporary:
        source, input_warnings = prepare_artwork(
            input_source,
            temporary,
            params,
            stitch_params,
            preserve_colors=method != "inkstitch"
            and stitch_params.auto_select
            and stitch_params.preserve_colors,
        )
        return _generate_svg(
            source, input_source, output_dir, params, method, stitch_params, started, input_warnings
        )


def _generate_svg(
    source, input_source, output_dir, params, method, stitch_params, started, input_warnings
):
    svg, _ = load_svg_paths(source)
    loaded = time.perf_counter()
    mask, transform = rasterize_svg(svg, params.dpi)
    rasterized = time.perf_counter()
    skeleton, distance = compute_medial_axis(mask)
    skeletonized = time.perf_counter()
    scale = image_scale(transform)
    pixels_per_mm = UNITS_PER_MM * scale
    spacing_px = spacing_to_px(params.spacing, params.density, scale)
    rungs, bridges, elements = generate_rungs(
        skeleton,
        distance,
        spacing_px,
        mask,
        min_satin_width_px=MIN_SATIN_WIDTH_MM * pixels_per_mm,
        pixels_per_mm=pixels_per_mm,
        auto_optimize=params.auto_optimize,
    )
    if not elements:
        raise ValueError("No stitchable columns found; enlarge the shape or increase DPI.")
    generated = time.perf_counter()
    elements = route_columns(elements)
    coverage = compute_coverage(mask, elements, pixels_per_mm)
    warnings = list(input_warnings)
    if coverage < 0.85 and method != "direct":
        warnings.append(
            ("Ink/Stitch rails: " if method == "both" else "")
            + f"Swept stitch coverage is {coverage:.1%}; inspect junctions and broad regions in Inkscape."
        )
    if method != "direct" and any(
        np.linalg.norm(np.asarray(e["rail_b"]) - e["rail_a"], axis=1).max() > 12 * pixels_per_mm
        for e in elements
        if e["type"] == "satin"
    ):
        warnings.append(
            "Some satin widths exceed 12 mm; resize or configure split stitches in Ink/Stitch."
        )
    if mask.shape[0] * mask.shape[1] >= 3_900_000 or max(mask.shape) >= 4090:
        warnings.append(
            "Raster resolution capped to bound memory; split very large designs for finer detail."
        )
    output = Path(output_dir).resolve()
    names = [
        source.name,
        f"{source.stem}_rungs.svg",
        f"{source.stem}_ready.svg",
        f"{source.stem}_satin.svg",
    ]
    if source != input_source and output / names[0] == input_source:
        names[0] = f"{source.stem}_prepared.svg"
    # Guard against overwriting the input with a generated file.
    if any((output / name) == input_source for name in names[1:]):
        raise ValueError("Output paths conflict with the input SVG.")
    output.mkdir(parents=True, exist_ok=True)
    direct_result = None
    with tempfile.TemporaryDirectory(prefix=".rungs-", dir=output) as temporary:
        stage = Path(temporary)
        shutil.copy2(source, stage / names[0])
        save_rungs_svg(stage / names[1], rungs, bridges, transform, svg)
        save_combined_svg(stage / names[2], rungs, bridges, transform, svg)
        save_satin_svg(stage / names[3], elements, transform, svg)
        direct_names = []
        if method != "inkstitch":
            direct_names, plan = export_direct(
                elements,
                transform,
                svg,
                stage,
                source.stem,
                stitch_params,
                residual=mask & ~coverage_mask(mask, elements, pixels_per_mm)
                if stitch_params.fill_gaps and not stitch_params.auto_select
                else None,
                mask=mask,
            )
            direct_result = DirectGenerationResult(
                *(str(output / name) for name in direct_names),
                stats=plan.stats,
                params=stitch_params,
                warnings=plan.warnings,
                decisions=plan.decisions,
                threads=plan.threads,
            )
        if params.debug:
            from .debug_utils import save_debug_images, save_rung_coverage_debug

            save_debug_images(stage / "debug", mask, distance, skeleton)
            save_rung_coverage_debug(
                stage / "debug", mask, rungs, elements=elements, pixels_per_mm=pixels_per_mm
            )
        for name in names + direct_names:
            os.replace(stage / name, output / name)
        if params.debug:
            debug = output / "debug"
            debug.mkdir(exist_ok=True)
            for file in (stage / "debug").iterdir():
                os.replace(file, debug / file.name)
    finished = time.perf_counter()
    timings = {
        "load": loaded - started,
        "raster": rasterized - loaded,
        "medial_axis": skeletonized - rasterized,
        "rungs": generated - skeletonized,
        "output": finished - generated,
        "total": finished - started,
    }
    n_satin = sum(e["type"] == "satin" for e in elements)
    logger.info(
        "%d rungs, %d satin columns, %d running paths; %.1f%% swept coverage in %.3fs",
        len(rungs),
        n_satin,
        len(elements) - n_satin,
        coverage * 100,
        timings["total"],
    )
    return GenerationResult(
        len(rungs),
        len(bridges),
        n_satin,
        len(elements) - n_satin,
        coverage,
        *(str(output / n) for n in names),
        debug_dir=str(output / "debug") if params.debug else None,
        params=params,
        warnings=warnings,
        timings=timings,
        direct=direct_result,
        artwork_size_mm=(svg.width / UNITS_PER_MM, svg.height / UNITS_PER_MM),
    )
