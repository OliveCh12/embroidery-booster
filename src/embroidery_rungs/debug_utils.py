import os
import logging
import numpy as np
from PIL import Image
from skimage.morphology import dilation, disk

logger = logging.getLogger(__name__)

def save_debug_images(debug_dir, binary_img, cleaned_binary, distance, skeleton):
    """Save intermediate processing images for debugging."""
    if not os.path.exists(debug_dir):
        os.makedirs(debug_dir)
        
    # 1. Original Rasterized (Raw)
    Image.fromarray((binary_img * 255).astype(np.uint8)).save(os.path.join(debug_dir, "debug_01_original.png"))
    
    # 2. Cleaned Binary (Used for Skeletonization)
    Image.fromarray((cleaned_binary * 255).astype(np.uint8)).save(os.path.join(debug_dir, "debug_02_binary.png"))
    
    # 3. Distance Map
    # Normalize distance for display
    d_norm = (distance / np.max(distance) * 255).astype(np.uint8)
    Image.fromarray(d_norm).save(os.path.join(debug_dir, "debug_03_distance.png"))
    
    # 4. Skeleton
    # Dilate skeleton for visibility in debug image
    skel_vis = dilation(skeleton, disk(1))
    Image.fromarray((skel_vis * 255).astype(np.uint8)).save(os.path.join(debug_dir, "debug_04_skeleton.png"))
    
    # 5. Overlay (Skeleton on Original)
    # Create RGB image
    overlay = np.zeros((binary_img.shape[0], binary_img.shape[1], 3), dtype=np.uint8)
    # Background (Original) in Gray
    overlay[..., 0] = binary_img * 100
    overlay[..., 1] = binary_img * 100
    overlay[..., 2] = binary_img * 100
    
    # Skeleton in Red
    overlay[skel_vis > 0] = [255, 0, 0]
    
    Image.fromarray(overlay).save(os.path.join(debug_dir, "debug_05_overlay.png"))

def save_debug_graph(debug_dir, G, binary_img_shape):
    """Save the skeleton graph as an SVG for debugging."""
    debug_graph_path = os.path.join(debug_dir, "debug_06_graph.svg")
    logger.info(f"Saving debug graph to {debug_graph_path}")
    
    lines = []
    lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{binary_img_shape[1]}" height="{binary_img_shape[0]}">')
    
    # Draw edges
    for u, v in G.edges():
        p1 = G.nodes[u]['pos']
        p2 = G.nodes[v]['pos']
        # Note: pos is (y, x)
        lines.append(f'<line x1="{p1[1]}" y1="{p1[0]}" x2="{p2[1]}" y2="{p2[0]}" stroke="green" stroke-width="1" />')
        
    # Draw nodes (junctions in red, others in blue)
    for n in G.nodes():
        p = G.nodes[n]['pos']
        color = "red" if G.degree(n) > 2 else ("blue" if G.degree(n) == 1 else "gray")
        radius = 2 if color == "red" else 1
        lines.append(f'<circle cx="{p[1]}" cy="{p[0]}" r="{radius}" fill="{color}" />')
        
    with open(debug_graph_path, 'w') as f:
        f.write("\n".join(lines))

def save_rung_coverage_debug(debug_dir, binary_img, rungs, skeleton_paths, rejected_rungs=None):
    """Create debug images showing rung coverage and gaps."""
    if not os.path.exists(debug_dir):
        os.makedirs(debug_dir)
        
    # Create coverage map
    coverage = np.zeros_like(binary_img, dtype=np.uint8)
    
    # Draw existing rungs
    from skimage.draw import line
    
    for rung in rungs:
        (p1_x, p1_y), (p2_x, p2_y) = rung
        rr, cc = line(int(p1_y), int(p1_x), int(p2_y), int(p2_x))
        valid = (rr >= 0) & (rr < coverage.shape[0]) & (cc >= 0) & (cc < coverage.shape[1])
        coverage[rr[valid], cc[valid]] = 255
    
    # Dilate coverage slightly to account for line width
    coverage_dilated = dilation(coverage, disk(2))
    
    # Find gaps: areas in binary_img that are not covered
    gaps = (binary_img > 0) & (coverage_dilated == 0)
    
    # Create debug image
    debug_img = np.zeros((binary_img.shape[0], binary_img.shape[1], 3), dtype=np.uint8)
    
    # Simple shape outline in bright red using morphological gradient (fast)
    from scipy import ndimage
    outline = ndimage.morphological_gradient(binary_img.astype(np.uint8), size=(3,3))
    debug_img[outline > 0] = [255, 0, 0]  # Bright red outline
    
    # Rungs in bright green (more visible)
    debug_img[coverage > 0] = [0, 255, 0]
    
    # Dilate rungs slightly for better visibility
    rung_mask = coverage > 0
    rung_dilated = dilation(rung_mask, disk(1))
    debug_img[rung_dilated] = [0, 255, 0]
    
    # Draw rejected rungs in Orange/Yellow
    if rejected_rungs:
        for rung in rejected_rungs:
            (p1_x, p1_y), (p2_x, p2_y) = rung
            rr, cc = line(int(p1_y), int(p1_x), int(p2_y), int(p2_x))
            valid = (rr >= 0) & (rr < debug_img.shape[0]) & (cc >= 0) & (cc < debug_img.shape[1])
            # Orange color [255, 165, 0]
            debug_img[rr[valid], cc[valid]] = [255, 165, 0]
    
    # Gaps in very low opacity red (further reduced)
    gap_overlay = np.zeros_like(debug_img)
    gap_overlay[gaps] = [255, 0, 0]
    # Blend with existing image for very low opacity effect
    alpha = 0.1  # 10% opacity for gaps (further reduced)
    debug_img[gaps] = (1 - alpha) * debug_img[gaps] + alpha * gap_overlay[gaps]
    
    # Skeleton paths in bright blue (more vivid)
    for path_data in skeleton_paths:
        points = path_data['points']
        for point in points:
            y, x = point
            if 0 <= int(y) < debug_img.shape[0] and 0 <= int(x) < debug_img.shape[1]:
                debug_img[int(y), int(x)] = [0, 100, 255]  # Bright blue
    
    Image.fromarray(debug_img).save(os.path.join(debug_dir, "debug_07_coverage.png"))
    
    # Calculate coverage statistics
    total_shape_pixels = np.sum(binary_img > 0)
    covered_pixels = np.sum((binary_img > 0) & (coverage_dilated > 0))
    coverage_ratio = covered_pixels / total_shape_pixels if total_shape_pixels > 0 else 0
    
    logger.info(f"Coverage: {coverage_ratio:.2f}")
    
    # Save statistics
    with open(os.path.join(debug_dir, "coverage_stats.txt"), 'w') as f:
        f.write(f"Total shape pixels: {total_shape_pixels}\n")
        f.write(f"Covered pixels: {covered_pixels}\n")
        f.write(f"Coverage ratio: {coverage_ratio:.2f}\n")
        f.write(f"Gaps: {np.sum(gaps)}\n")
