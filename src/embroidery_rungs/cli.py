"""Thin, scriptable wrapper around generate()."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict

from .pipeline import GenerationParams, generate
from .stitching.params import StitchParams
from .svg_manager import open_in_inkscape


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate editable Ink/Stitch columns and/or direct PES/DST stitches."
    )
    parser.add_argument("input", help="Input SVG or bitmap image")
    parser.add_argument("--design-width", type=float, help="Artwork document width in mm")
    parser.add_argument("--fit-to-hoop", action="store_true", help="Shrink artwork to fit the hoop")
    parser.add_argument("--raster-threshold", type=int, help="Bitmap luminance threshold (0–255)")
    parser.add_argument("--invert-image", action="store_true", help="Invert bitmap foreground")
    parser.add_argument("-s", "--spacing", type=float, default=3.0, help="Maximum rung gap in mm")
    parser.add_argument("--density", type=float, default=1.0, help="Rung density multiplier")
    parser.add_argument("-d", "--dpi", type=int, default=150, help="Requested processing DPI")
    parser.add_argument("-o", "--output-dir", default="output")
    parser.add_argument("--no-preview", action="store_true", help="Skip opening Inkscape")
    parser.add_argument("--preview", action="store_true", help="Open the combined SVG in Inkscape")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--debug", action="store_true", help="Save intermediate PNGs")
    parser.add_argument(
        "--auto-optimize", action="store_true", help="Refine rungs at bends and width changes"
    )
    parser.add_argument("--json", action="store_true", help="Print structured results to stdout")
    parser.add_argument("--method", choices=("inkstitch", "direct", "both"), default="inkstitch")
    parser.add_argument(
        "--stitch-spacing",
        type=float,
        help="Direct satin row spacing in mm (overrides material preset)",
    )
    parser.add_argument(
        "--fill-spacing",
        type=float,
        help="Direct fill row spacing in mm (overrides material preset)",
    )
    parser.add_argument(
        "--running-length", type=float, default=2.5, help="Direct running stitch length in mm"
    )
    parser.add_argument(
        "--max-stitch", type=float, default=8.0, help="Maximum direct stitch length in mm"
    )
    parser.add_argument(
        "--pull-compensation",
        type=float,
        help="Direct compensation per rail in mm (overrides preset)",
    )
    parser.add_argument("--no-underlay", action="store_true", help="Disable direct underlay")
    parser.add_argument(
        "--wide-mode",
        choices=("fill", "split"),
        help="Manual wide-region policy; disables automatic type selection",
    )
    parser.add_argument("--no-gap-fill", action="store_true", help="Disable fill of broad MAT gaps")
    parser.add_argument("--fill-angle", type=float, help="Manual direct tatami angle in degrees")
    parser.add_argument("--hoop-width", type=float, default=100.0, help="Hoop width in mm")
    parser.add_argument("--hoop-height", type=float, default=100.0, help="Hoop height in mm")
    parser.add_argument("--thread-color", default="#176d9c", help="Direct thread hex color")
    parser.add_argument(
        "--fabric", choices=("custom", "stable", "stretch", "textured"), default="custom"
    )
    parser.add_argument("--thread-weight", type=int, choices=(30, 40, 60), default=40)
    parser.add_argument(
        "--stabilizer",
        choices=("unspecified", "cutaway", "tearaway", "washaway"),
        default="unspecified",
    )
    parser.add_argument(
        "--no-auto-select", action="store_true", help="Keep legacy per-rail stitch type selection"
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_arguments(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        overrides = {
            name: value
            for name, value in (
                ("satin_spacing_mm", args.stitch_spacing),
                ("fill_spacing_mm", args.fill_spacing),
                ("pull_compensation_mm", args.pull_compensation),
                ("fill_angle_deg", args.fill_angle),
            )
            if value is not None
        }
        result = generate(
            args.input,
            args.output_dir,
            GenerationParams(
                spacing=args.spacing,
                density=args.density,
                dpi=args.dpi,
                debug=args.debug,
                auto_optimize=args.auto_optimize,
                design_width_mm=args.design_width,
                fit_to_hoop=args.fit_to_hoop,
                raster_threshold=args.raster_threshold,
                raster_invert=args.invert_image,
            ),
            method=args.method,
            stitch_params=StitchParams.for_fabric(
                args.fabric,
                thread_weight=args.thread_weight,
                stabilizer=args.stabilizer,
                **overrides,
                running_length_mm=args.running_length,
                max_stitch_mm=args.max_stitch,
                underlay=not args.no_underlay,
                wide_mode=args.wide_mode or "fill",
                fill_gaps=not args.no_gap_fill,
                auto_select=not args.no_auto_select and args.wide_mode is None,
                auto_fill_angle=args.fill_angle is None,
                hoop_width_mm=args.hoop_width,
                hoop_height_mm=args.hoop_height,
                thread_color=args.thread_color,
            ),
        )
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(asdict(result), ensure_ascii=False))
    else:
        print(
            f"{result.columns_count} satin columns, {result.running_count} running paths, "
            f"{result.rungs_count} rungs; coverage {result.coverage:.1%}\n{result.satin_path}"
        )
        for warning in result.warnings:
            print(f"Warning: {warning}", file=sys.stderr)
        if result.direct:
            print(
                f"{result.direct.stats['stitches']} direct stitches; {result.direct.pes_path}\n{result.direct.dst_path}"
            )
            for warning in result.direct.warnings:
                print(f"Warning: {warning}", file=sys.stderr)
    if args.preview and not args.no_preview:
        open_in_inkscape(result.direct.svg_path if args.method == "direct" else result.ready_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
