"""Library-first artwork preparation and direct machine-file generation."""

from __future__ import annotations

import logging
import math
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

from .inputs import prepare_artwork
from .stitching.export import DirectGenerationResult, export_direct
from .stitching.params import StitchParams
from .svg_manager import UNITS_PER_MM, load_svg_paths

logger = logging.getLogger(__name__)


@dataclass
class GenerationParams:
    design_width_mm: float | None = None
    fit_to_hoop: bool = False
    raster_threshold: int | None = None
    raster_invert: bool = False
    background_mode: str = "auto"
    raster_cleanup: bool = True

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
        if self.background_mode not in ("auto", "keep", "remove"):
            raise ValueError("background_mode must be 'auto', 'keep' or 'remove'.")
        if not isinstance(self.raster_cleanup, bool):
            raise ValueError("raster_cleanup must be a boolean.")


@dataclass
class GenerationResult:
    input_path: str
    original_path: str
    direct: DirectGenerationResult
    artwork_size_mm: tuple[float, float]
    params: GenerationParams
    warnings: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    input_analysis: dict = field(default_factory=dict)


def generate(
    input_path: str | os.PathLike,
    output_dir: str | os.PathLike = "output",
    params: GenerationParams | None = None,
    *,
    method: str = "direct",
    stitch_params: StitchParams | None = None,
) -> GenerationResult:
    """Prepare SVG/bitmap artwork and export PES, DST and inspectable stitch previews.

    ``original_path`` points to the interpreted artwork, including any explicit
    sizing or bitmap tracing. The input file is never modified. Files are staged
    together so a failed digitizer or machine writer preserves previous outputs.
    """
    started = time.perf_counter()
    params = replace(params) if params is not None else GenerationParams()
    params.validate()
    if method != "direct":
        raise ValueError(
            "method must be 'direct'; external embroidery workflows are not supported."
        )
    stitch_params = replace(stitch_params) if stitch_params is not None else StitchParams()
    stitch_params.validate()
    input_source = Path(input_path).resolve()
    output = Path(output_dir).resolve()
    with tempfile.TemporaryDirectory(prefix="embroidery-input-") as temporary:
        source, warnings, input_analysis = prepare_artwork(
            input_source,
            temporary,
            params,
            stitch_params,
            preserve_colors=stitch_params.preserve_colors,
        )
        svg, _ = load_svg_paths(source)
        prepared = time.perf_counter()
        artwork_name = f"{input_source.stem}_artwork.svg"
        stage_parent = output
        while not stage_parent.is_dir():
            stage_parent = stage_parent.parent
        with tempfile.TemporaryDirectory(prefix=".embroidery-", dir=stage_parent) as temporary:
            stage = Path(temporary)
            shutil.copy2(source, stage / artwork_name)
            names, plan = export_direct(
                svg, stage, input_source.stem, stitch_params, input_analysis=input_analysis
            )
            generated = time.perf_counter()
            direct = DirectGenerationResult(
                *(str(output / name) for name in names),
                stats=plan.stats,
                params=plan.params,
                warnings=plan.warnings,
                decisions=plan.decisions,
                threads=plan.threads,
                analysis=plan.analysis,
                requested_params=plan.requested_params,
                adjustments=plan.adjustments,
            )
            output.mkdir(parents=True, exist_ok=True)
            for name in [artwork_name, *names]:
                os.replace(stage / name, output / name)
        finished = time.perf_counter()
    timings = {
        "prepare": prepared - started,
        "digitize_and_export": generated - prepared,
        "publish": finished - generated,
        "total": finished - started,
    }
    logger.info(
        "%d stitches, %d colours; %.1f%% structural coverage in %.3fs",
        direct.stats["stitches"],
        len(direct.threads),
        direct.stats["structural_coverage"] * 100,
        timings["total"],
    )
    return GenerationResult(
        input_path=str(input_source),
        original_path=str(output / artwork_name),
        direct=direct,
        artwork_size_mm=(svg.width / UNITS_PER_MM, svg.height / UNITS_PER_MM),
        params=params,
        warnings=list(warnings),
        timings=timings,
        input_analysis=input_analysis,
    )
