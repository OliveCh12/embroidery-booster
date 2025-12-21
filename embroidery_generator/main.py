#!/usr/bin/env python3
"""
Embroidery Auto Rung Generator
==============================

Automatically generates optimal rung placement for embroidery satins using 
Medial Axis Transform (MAT).
"""

import sys
import os
import shutil
import argparse
import logging
from svgelements import Matrix, Point

from .svg_manager import load_svg_paths, save_rungs_svg, save_combined_svg, open_in_inkscape, extract_path_endpoints
from .image_processor import rasterize_paths, compute_medial_axis
from .rung_generator import generate_rungs
from .debug_utils import save_debug_images

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def parse_arguments():
    parser = argparse.ArgumentParser(description="Embroidery Auto Rung Generator")
    parser.add_argument("input", help="Input SVG file")
    parser.add_argument("-s", "--spacing", type=float, default=3.0, help="Rung spacing in mm")
    parser.add_argument("--density", type=float, default=1.0, help="Density multiplier (higher = more rungs)")
    parser.add_argument("-d", "--dpi", type=int, default=150, help="DPI for processing (higher is better)")
    parser.add_argument("--no-preview", action="store_true", help="Do not open Inkscape automatically")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--debug", action="store_true", help="Save debug images")
    return parser.parse_args()

def main():
    args = parse_arguments()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        
    # Setup output directory
    output_dir = "output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    debug_dir = os.path.join(output_dir, "debug")
    if args.debug and not os.path.exists(debug_dir):
        os.makedirs(debug_dir)
        
    input_filename = os.path.basename(args.input)
    base_name, ext = os.path.splitext(input_filename)
    
    # Define output paths
    path_original_copy = os.path.join(output_dir, input_filename)
    path_rungs = os.path.join(output_dir, f"{base_name}_rungs.svg")
    path_ready = os.path.join(output_dir, f"{base_name}_ready.svg")
    
    logger.info(f"Processing {args.input}...")
    
    # Copy original file to output
    shutil.copy2(args.input, path_original_copy)
    
    svg, paths = load_svg_paths(args.input)
    
    # Extract path endpoints for proper rung placement
    path_endpoints = extract_path_endpoints(paths)
    
    # Apply the same ViewBox correction to endpoints if needed
    if svg.viewbox:
        offset_x = svg.viewbox.x
        offset_y = svg.viewbox.y
        if offset_x != 0 or offset_y != 0:
            corrected_endpoints = []
            for start_point, end_point in path_endpoints:
                corrected_start = start_point - Point(offset_x, offset_y)
                corrected_end = end_point - Point(offset_x, offset_y)
                corrected_endpoints.append((corrected_start, corrected_end))
            path_endpoints = corrected_endpoints
    
    if not paths:
        logger.warning("No paths found in SVG.")
        sys.exit(0)
        
    # Rasterize
    # Pass absolute path for Inkscape
    abs_input_path = os.path.abspath(args.input)
    binary_img, transform, dims = rasterize_paths(svg, paths, args.dpi, svg_filename=abs_input_path)
    
    # Correction for ViewBox offset if svgelements normalized the paths
    if svg.viewbox:
        offset_x = svg.viewbox.x
        offset_y = svg.viewbox.y
        if offset_x != 0 or offset_y != 0:
            logger.info(f"Applying ViewBox offset correction: ({offset_x}, {offset_y})")
            # We need to shift the coordinate system back by the offset
            # transform maps World -> Image
            # We want World -> Image to be: (P - Offset) * transform_original
            # So transform_new = Translate(-Offset) * transform_original
            correction = Matrix.translate(-offset_x, -offset_y)
            transform = correction * transform
    
    # Medial Axis
    skeleton, distance, cleaned_binary = compute_medial_axis(binary_img)
    
    if args.debug:
        save_debug_images(debug_dir, binary_img, cleaned_binary, distance, skeleton)
        
    # Generate Rungs
    # Convert spacing mm to pixels
    scale_factor = args.dpi / 96.0
    # Apply density: higher density -> smaller spacing
    # Reduce spacing multiplier for better rung density while keeping InkStitch compatibility
    # User requested much lower density (around 20 rungs for Nike logo)
    # Previous was 2.5, increasing to 10.0 to drastically reduce density
    base_spacing = args.spacing * 10.0
    spacing_px = (base_spacing / args.density) * (args.dpi / 25.4)
    
    debug_dir_path = debug_dir if args.debug else None
    rungs, bridges = generate_rungs(skeleton, distance, spacing_px, transform, binary_img, path_endpoints, debug_dir=debug_dir_path)
    
    # Save Rungs Only
    save_rungs_svg(path_rungs, rungs, bridges, transform)
    
    # Save Combined Ready File
    save_combined_svg(args.input, path_ready, rungs, bridges, transform)
    
    logger.info("Done!")
    logger.info(f"Files created in '{output_dir}/':")
    logger.info(f"  - {os.path.basename(path_original_copy)} (Original)")
    logger.info(f"  - {os.path.basename(path_rungs)} (Rungs only)")
    logger.info(f"  - {os.path.basename(path_ready)} (Ready to edit)")
    
    if not args.no_preview:
        open_in_inkscape(path_ready)

if __name__ == "__main__":
    main()
