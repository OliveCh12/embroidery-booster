#!/usr/bin/env python3
"""Command-line entry point for the Embroidery Auto Rung Generator.

A thin wrapper around :func:`embroidery_rungs.pipeline.generate`.
"""

import sys
import logging
import argparse

from .pipeline import generate, GenerationParams
from .svg_manager import open_in_inkscape

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description="Embroidery Auto Rung Generator")
    parser.add_argument("input", help="Input SVG file")
    parser.add_argument("-s", "--spacing", type=float, default=3.0,
                        help="Rung spacing in mm")
    parser.add_argument("--density", type=float, default=1.0,
                        help="Density multiplier (higher = more rungs)")
    parser.add_argument("-d", "--dpi", type=int, default=150,
                        help="DPI for processing (higher is better)")
    parser.add_argument("-o", "--output-dir", default="output",
                        help="Directory for generated files")
    parser.add_argument("--no-preview", action="store_true",
                        help="Do not open Inkscape automatically")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--debug", action="store_true", help="Save debug images")
    parser.add_argument("--auto-optimize", action="store_true",
                        help="Automatically find optimal parameters (no intersections, max 25 rungs)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_arguments(argv)
    if args.verbose:
        logging.getLogger("embroidery_rungs").setLevel(logging.DEBUG)

    params = GenerationParams(
        spacing=args.spacing,
        density=args.density,
        dpi=args.dpi,
        debug=args.debug,
        auto_optimize=args.auto_optimize,
    )

    try:
        result = generate(args.input, output_dir=args.output_dir, params=params)
    except (FileNotFoundError, ValueError) as e:
        logger.error(str(e))
        return 1

    logger.info(f"Files created in '{args.output_dir}/':")
    logger.info(f"  - {result.original_path} (Original)")
    logger.info(f"  - {result.rungs_path} (Rungs only)")
    logger.info(f"  - {result.ready_path} (Ready to edit)")

    if not args.no_preview:
        open_in_inkscape(result.ready_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
