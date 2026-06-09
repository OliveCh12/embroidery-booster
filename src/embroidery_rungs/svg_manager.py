import os
import logging
import subprocess
from svgelements import SVG, Path, Shape, Point

logger = logging.getLogger(__name__)

def load_svg_paths(svg_path):
    """Load paths from SVG file."""
    if not os.path.exists(svg_path):
        raise FileNotFoundError(f"SVG file not found: {svg_path}")

    svg = SVG.parse(svg_path)
    paths = []
    for element in svg.elements():
        if isinstance(element, Path):
            paths.append(element)
        elif isinstance(element, Shape):
            paths.append(Path(element))
            
    logger.info(f"Loaded {len(paths)} paths from {svg_path}")
    return svg, paths

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
        f.write('<g id="rungs" stroke="red" stroke-width="0.1">\n')
        for p1, p2 in rungs:
            pt1 = Point(p1[0], p1[1]) * inv_transform
            pt2 = Point(p2[0], p2[1]) * inv_transform
            f.write(f'  <line x1="{pt1.x:.2f}" y1="{pt1.y:.2f}" x2="{pt2.x:.2f}" y2="{pt2.y:.2f}" />\n')
        f.write('</g>\n')
        
        # Bridges (Blue)
        f.write('<g id="bridges" stroke="blue" stroke-width="0.1">\n')
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
    # No inkscape:label here: the original root may not declare that namespace,
    # which makes the file non-conformant.
    rungs_svg.append('<g id="generated_rungs">')

    rungs_svg.append('  <g id="rungs_normal" stroke="red" stroke-width="0.1">')
    for p1, p2 in rungs:
        pt1 = Point(p1[0], p1[1]) * inv_transform
        pt2 = Point(p2[0], p2[1]) * inv_transform
        rungs_svg.append(f'    <line x1="{pt1.x:.2f}" y1="{pt1.y:.2f}" x2="{pt2.x:.2f}" y2="{pt2.y:.2f}" />')
    rungs_svg.append('  </g>')
    
    rungs_svg.append('  <g id="rungs_bridges" stroke="blue" stroke-width="0.1">')
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

_INKSTITCH_NS = "http://inkstitch.org/namespace"


def save_satin_svg(output_path, columns, transform, svg):
    """Write a standalone SVG of Ink/Stitch satin columns.

    Each column is one ``<path>`` with two rail subpaths plus rung subpaths
    (direction checkpoints), tagged ``inkstitch:satin_column``. The file carries
    the Ink/Stitch SVG-version metadata so Ink/Stitch does not prompt to update
    it, and the viewBox is fitted to the satin so nothing is cropped.
    """
    logger.info(f"Saving {len(columns)} satin columns to {output_path}")
    inv = ~transform
    xs, ys = [], []

    def to_svg(p):
        q = Point(p[0], p[1]) * inv
        xs.append(q.x)
        ys.append(q.y)
        return q.x, q.y

    path_data = []
    for col in columns:
        rail_a, rail_b, rungs = col["rail_a"], col["rail_b"], col["rungs"]
        segments = []
        for rail in (rail_a, rail_b):
            pts = [to_svg(p) for p in rail]
            segments.append("M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in pts))

        # Ink/Stitch needs >= 3 rungs (2 is ambiguous). Each rung must clearly
        # cross both rails, so extend it past each endpoint.
        if len(rungs) >= 3:
            for a, b in rungs:
                ax, ay = a
                bx, by = b
                dx, dy = bx - ax, by - ay
                length = (dx * dx + dy * dy) ** 0.5 or 1.0
                ux, uy = dx / length, dy / length
                ext = min(max(3.0, 0.1 * length), 8.0)
                sx, sy = to_svg((ax - ux * ext, ay - uy * ext))
                ex, ey = to_svg((bx + ux * ext, by + uy * ext))
                segments.append(f"M {sx:.2f},{sy:.2f} L {ex:.2f},{ey:.2f}")
        path_data.append(" ".join(segments))

    # Fit the viewBox to the satin so nothing is clipped.
    if xs:
        pad = 5.0
        minx, miny = min(xs) - pad, min(ys) - pad
        w, h = max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad
    else:
        minx, miny, w, h = 0, 0, svg.width or 100, svg.height or 100
    view_box = f"{minx:.2f} {miny:.2f} {w:.2f} {h:.2f}"

    lines = [
        '<?xml version="1.0" encoding="utf-8" ?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkstitch="{_INKSTITCH_NS}" '
        f'width="{w:.2f}" height="{h:.2f}" viewBox="{view_box}" version="1.1">',
        # Mark as a current Ink/Stitch file (suppresses the "update?" dialog).
        '<metadata><inkstitch:inkstitch_svg_version>3</inkstitch:inkstitch_svg_version></metadata>',
        '<g id="satin_columns">',
    ]
    for d in path_data:
        lines.append(f'  <path inkstitch:satin_column="true" '
                     f'style="fill:none;stroke:#e02020;stroke-width:1" d="{d}" />')
    lines.append("</g>")
    lines.append("</svg>")

    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")


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
