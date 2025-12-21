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
import numpy as np
from skimage.morphology import dilation, disk
from skimage.draw import line

from svg_manager import load_svg_paths, save_rungs_svg, save_combined_svg, open_in_inkscape, extract_path_endpoints
from image_processor import rasterize_paths, compute_medial_axis
from rung_generator import generate_rungs
from debug_utils import save_debug_images

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
    parser.add_argument("--auto-optimize", action="store_true", help="Automatically find optimal parameters (no intersections, max 25 rungs)")
    return parser.parse_args()

def optimize_rung_parameters(svg, paths, path_endpoints, dpi, max_rungs=25, logger=None):
    """
    Trouve automatiquement les paramètres optimaux pour la génération de rungs.
    Version optimisée qui teste seulement quelques configurations clés.
    """
    if logger:
        logger.info("🔍 Recherche automatique des paramètres optimaux...")

    # Rasterisation (commune à toutes les configurations)
    abs_input_path = os.path.abspath("temp.svg")
    with open(abs_input_path, 'w') as f:
        f.write(str(svg))
    
    binary_img, transform, dims = rasterize_paths(svg, paths, dpi, svg_filename=abs_input_path)
    os.remove(abs_input_path)
    
    # Correction ViewBox si nécessaire
    if svg.viewbox:
        offset_x = svg.viewbox.x
        offset_y = svg.viewbox.y
        if offset_x != 0 or offset_y != 0:
            correction = Matrix.translate(-offset_x, -offset_y)
            transform = correction * transform
    
    # Calcul du squelette (commun)
    skeleton, distance, cleaned_binary = compute_medial_axis(binary_img)
    
    # Fonction helper pour tester une configuration
    def test_config(spacing_mm, density):
        scale_factor = dpi / 96.0
        base_spacing = spacing_mm * 10.0
        spacing_px = (base_spacing / density) * (dpi / 25.4)
        
        try:
            rungs, bridges = generate_rungs(skeleton, distance, spacing_px, transform, 
                                           binary_img, path_endpoints, debug_dir=None)
            return len(rungs), len(bridges), rungs
        except Exception as e:
            if logger:
                logger.debug(f"Erreur config spacing={spacing_mm}mm, density={density}: {e}")
            return 0, 999, []
    
    # Tester quelques configurations clés
    test_configs = [
        (3.0, 1.0),   # Configuration par défaut
        (4.0, 1.0),   # Plus espacé
        (5.0, 1.0),   # Encore plus espacé
        (6.0, 1.0),   # Très espacé
        (3.0, 0.8),   # Plus dense
        (4.0, 0.8),   # Dense et espacé
    ]
    
    best_config = None
    best_score = -1
    
    if logger:
        logger.info("Test des configurations candidates...")
    
    for spacing_mm, density in test_configs:
        rungs_count, bridges_count, rungs = test_config(spacing_mm, density)
        
        if logger:
            logger.info(f"  Spacing {spacing_mm}mm, density {density}: {rungs_count} rungs, {bridges_count} intersections")
        
        # Accepter seulement les configs sans intersections et avec un nombre raisonnable de rungs
        if bridges_count == 0 and 15 <= rungs_count <= max_rungs:
            # Calculer couverture
            coverage = np.zeros_like(binary_img, dtype=np.uint8)
            for rung in rungs:
                (p1_x, p1_y), (p2_x, p2_y) = rung
                rr, cc = line(int(p1_y), int(p1_x), int(p2_y), int(p2_x))
                valid = (rr >= 0) & (rr < coverage.shape[0]) & (cc >= 0) & (cc < coverage.shape[1])
                coverage[rr[valid], cc[valid]] = 255
            
            coverage_dilated = dilation(coverage, disk(2))
            total_shape_pixels = np.sum(binary_img > 0)
            covered_pixels = np.sum((binary_img > 0) & (coverage_dilated > 0))
            coverage_ratio = covered_pixels / total_shape_pixels if total_shape_pixels > 0 else 0
            
            # Score: privilégier les configs proches de max_rungs avec bonne couverture
            rung_score = 1.0 - abs(rungs_count - max_rungs) / max_rungs
            score = coverage_ratio + rung_score
            
            if score > best_score:
                best_score = score
                best_config = (spacing_mm, density, rungs_count, bridges_count, coverage_ratio)
                if logger:
                    logger.info(f"  ✨ Nouvelle meilleure config: {rungs_count} rungs, {coverage_ratio:.1%} couverture")
    
    if best_config:
        spacing_mm, density, rungs, bridges, coverage = best_config
        if logger:
            logger.info(f"✅ Configuration optimale trouvée: spacing={spacing_mm}mm, density={density}")
            logger.info(f"   Résultat: {rungs} rungs, {bridges} intersections, {coverage:.1%} couverture")
        return best_config
    else:
        # Fallback: prendre la config avec le moins d'intersections
        if logger:
            logger.info("Aucune config parfaite trouvée, recherche du meilleur compromis...")
        
        all_results = []
        for spacing_mm, density in test_configs:
            rungs_count, bridges_count, _ = test_config(spacing_mm, density)
            all_results.append((spacing_mm, density, rungs_count, bridges_count))
        
        # Trier par nombre d'intersections croissant, puis par nombre de rungs décroissant
        all_results.sort(key=lambda x: (x[3], -x[2]))  # (bridges, -rungs)
        
        if all_results:
            spacing_mm, density, rungs_count, bridges_count = all_results[0]
            if logger:
                logger.warning(f"⚠️ Meilleur compromis: {rungs_count} rungs, {bridges_count} intersections")
            return (spacing_mm, density, rungs_count, bridges_count, 0.0)  # Couverture inconnue
    
    if logger:
        logger.error("❌ Aucune configuration viable trouvée")
    return None

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
    
    # Optimisation automatique si demandée
    if args.auto_optimize:
        logger.info("Mode optimisation automatique activé")
        optimal_config = optimize_rung_parameters(svg, paths, path_endpoints, args.dpi, logger=logger)
        
        if optimal_config:
            optimal_spacing, optimal_density, predicted_rungs, predicted_bridges, predicted_coverage = optimal_config
            args.spacing = optimal_spacing
            args.density = optimal_density
            logger.info(f"Paramètres optimaux appliqués: spacing={args.spacing}mm, density={args.density}")
        else:
            logger.warning("Optimisation échouée, utilisation des paramètres par défaut")
        
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
