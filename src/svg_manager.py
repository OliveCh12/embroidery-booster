import os
import sys
import logging
import subprocess
from svgelements import SVG, Path, Shape, Point

logger = logging.getLogger(__name__)

def load_svg_paths(svg_path):
    """Load paths from SVG file."""
    if not os.path.exists(svg_path):
        logger.error(f"File not found: {svg_path}")
        sys.exit(1)
    
    svg = SVG.parse(svg_path)
    paths = []
    for element in svg.elements():
        if isinstance(element, Path):
            paths.append(element)
        elif isinstance(element, Shape):
            paths.append(Path(element))
            
    logger.info(f"Loaded {len(paths)} paths from {svg_path}")
    return svg, paths

def extract_path_endpoints(paths):
    """Extract start and end points of all paths."""
    endpoints = []
    for path in paths:
        if len(path) > 0:
            # Get the first and last points of the path
            start_point = path.point(0)  # Start of path
            end_point = path.point(path.length())  # End of path
            endpoints.append((start_point, end_point))
    return endpoints

def save_rungs_svg(output_path, rungs, bridges, transform):
    """Save just the rungs to a new SVG file."""
    logger.info(f"Saving {len(rungs)} rungs and {len(bridges)} bridges to {output_path}")
    
    # Inverse transform to map back to original SVG coordinates
    inv_transform = ~transform
    
    # Create SVG content manually
    with open(output_path, 'w') as f:
        f.write('<?xml version="1.0" encoding="utf-8" ?>\n')
        f.write('<svg width="100%" height="100%" xmlns="http://www.w3.org/2000/svg" version="1.1">\n')
        
        # Normal Rungs (Red)
        f.write(f'<g id="rungs" stroke="red" stroke-width="0.1">\n')
        for p1, p2 in rungs:
            pt1 = Point(p1[0], p1[1]) * inv_transform
            pt2 = Point(p2[0], p2[1]) * inv_transform
            f.write(f'  <line x1="{pt1.x:.2f}" y1="{pt1.y:.2f}" x2="{pt2.x:.2f}" y2="{pt2.y:.2f}" />\n')
        f.write('</g>\n')
        
        # Bridges (Blue)
        f.write(f'<g id="bridges" stroke="blue" stroke-width="0.1">\n')
        for p1, p2 in bridges:
            pt1 = Point(p1[0], p1[1]) * inv_transform
            pt2 = Point(p2[0], p2[1]) * inv_transform
            f.write(f'  <line x1="{pt1.x:.2f}" y1="{pt1.y:.2f}" x2="{pt2.x:.2f}" y2="{pt2.y:.2f}" />\n')
        f.write('</g>\n')
        
        f.write('</svg>\n')

def save_combined_svg(original_path, output_path, rungs, bridges, transform):
    """Save the original SVG combined with rungs."""
    logger.info(f"Creating combined file: {output_path}")
    
    # We'll read the original file as text and inject the rungs group before </svg>
    # This preserves all original metadata, groups, etc.
    
    inv_transform = ~transform
    
    rungs_svg = []
    rungs_svg.append(f'<g id="generated_rungs" inkscape:label="Rungs">')
    
    rungs_svg.append(f'  <g id="rungs_normal" stroke="red" stroke-width="0.1">')
    for p1, p2 in rungs:
        pt1 = Point(p1[0], p1[1]) * inv_transform
        pt2 = Point(p2[0], p2[1]) * inv_transform
        rungs_svg.append(f'    <line x1="{pt1.x:.2f}" y1="{pt1.y:.2f}" x2="{pt2.x:.2f}" y2="{pt2.y:.2f}" />')
    rungs_svg.append('  </g>')
    
    rungs_svg.append(f'  <g id="rungs_bridges" stroke="blue" stroke-width="0.1">')
    for p1, p2 in bridges:
        pt1 = Point(p1[0], p1[1]) * inv_transform
        pt2 = Point(p2[0], p2[1]) * inv_transform
        rungs_svg.append(f'    <line x1="{pt1.x:.2f}" y1="{pt1.y:.2f}" x2="{pt2.x:.2f}" y2="{pt2.y:.2f}" />')
    rungs_svg.append('  </g>')
    
    rungs_svg.append('</g>')
    
    rungs_block = "\n".join(rungs_svg)
    
    with open(original_path, 'r') as f:
        content = f.read()
        
    # Insert before closing svg tag
    if '</svg>' in content:
        new_content = content.replace('</svg>', f'\n{rungs_block}\n</svg>')
    else:
        # Fallback if malformed
        new_content = content + f'\n{rungs_block}'
        
    with open(output_path, 'w') as f:
        f.write(new_content)

def open_in_inkscape(filepath):
    """Open the file in Inkscape (macOS)."""
    logger.info(f"Opening in Inkscape: {filepath}")
    try:
        # Try standard 'open' command on macOS
        subprocess.run(['open', '-a', 'Inkscape', filepath], check=True)
    except subprocess.CalledProcessError:
        logger.warning("Could not open Inkscape automatically.")
    except Exception as e:
        logger.warning(f"Error opening Inkscape: {e}")
