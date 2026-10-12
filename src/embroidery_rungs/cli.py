"""Thin, scriptable wrapper around generate()."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict

from .pipeline import GenerationParams, generate
from .stitching.params import StitchParams


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate PES/DST embroidery and stitch previews from SVG or bitmap artwork."
    )
    parser.add_argument("input", help="Input SVG or bitmap image")
    parser.add_argument("--design-width", type=float, help="Artwork document width in mm")
    parser.add_argument("--fit-to-hoop", action="store_true", help="Shrink artwork to fit the hoop")
    parser.add_argument("--raster-threshold", type=int, help="Bitmap luminance threshold (0–255)")
    parser.add_argument("--invert-image", action="store_true", help="Invert bitmap foreground")
    parser.add_argument("-o", "--output-dir", default="output")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print structured results to stdout")
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
        "--no-auto-adjust",
        action="store_true",
        help="Use requested settings without automatic adjustments",
    )
    parser.add_argument("--fill-angle", type=float, help="Manual direct tatami angle in degrees")
    parser.add_argument("--hoop-width", type=float, default=100.0, help="Hoop width in mm")
    parser.add_argument("--hoop-height", type=float, default=100.0, help="Hoop height in mm")
    parser.add_argument("--thread-color", help="Override source colours with one hex thread colour")
    parser.add_argument(
        "--single-color", action="store_true", help="Trace/digitize a monochrome silhouette"
    )
    parser.add_argument(
        "--max-colors",
        type=int,
        help="Maximum automatic thread palette (1–32; machine preset by default)",
    )
    parser.add_argument("--machine", choices=("generic", "brother-skitch-pp1"), default="generic")
    parser.add_argument("--max-satin-width", type=float, help="Maximum automatic satin width in mm")
    parser.add_argument(
        "--fabric", choices=("custom", "stable", "stretch", "textured"), default="custom"
    )
    parser.add_argument("--thread-weight", type=int, choices=(30, 40, 60), default=40)
    parser.add_argument(
        "--stabilizer",
        choices=("unspecified", "cutaway", "tearaway", "washaway"),
        default="unspecified",
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
                ("max_colors", args.max_colors),
                ("max_satin_width_mm", args.max_satin_width),
            )
            if value is not None
        }
        result = generate(
            args.input,
            args.output_dir,
            GenerationParams(
                design_width_mm=args.design_width,
                fit_to_hoop=args.fit_to_hoop,
                raster_threshold=args.raster_threshold,
                raster_invert=args.invert_image,
            ),
            stitch_params=StitchParams.for_fabric(
                args.fabric,
                thread_weight=args.thread_weight,
                stabilizer=args.stabilizer,
                machine=args.machine,
                **overrides,
                running_length_mm=args.running_length,
                max_stitch_mm=args.max_stitch,
                underlay=not args.no_underlay,
                auto_adjust=not args.no_auto_adjust,
                auto_fill_angle=args.fill_angle is None,
                hoop_width_mm=args.hoop_width,
                hoop_height_mm=args.hoop_height,
                thread_color=args.thread_color or "#176d9c",
                preserve_colors=not args.single_color and args.thread_color is None,
            ),
        )
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(asdict(result), ensure_ascii=False))
    else:
        print(
            f"{result.direct.stats['stitches']} stitches, {len(result.direct.threads)} colours; "
            f"coverage {result.direct.stats['structural_coverage']:.1%}\n"
            f"{result.direct.pes_path}\n{result.direct.dst_path}"
        )
        for warning in dict.fromkeys([*result.warnings, *result.direct.warnings]):
            print(f"Warning: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
