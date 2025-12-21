#!/usr/bin/env python3
"""
Embroidery Auto Rung Generator
==============================

Automatically generates optimal rung placement for embroidery satins using 
Medial Axis Transform (MAT).

Usage:
    python3 embroidery_auto_rung_generator.py <input_svg> [options]

Options:
    -s, --spacing <float>   Rung spacing in mm (default: 5.0)
    -d, --dpi <int>         DPI for rasterization (default: 96)
    -o, --output <file>     Output filename (default: <input>_rungs.svg)
    -v, --verbose           Enable verbose output
    --debug                 Save debug images (skeleton, distance map)

Dependencies:
    numpy, scipy, scikit-image, pillow, svgelements
"""

import sys
import os
import shutil
import subprocess
import argparse
import logging
import numpy as np
from PIL import Image, ImageDraw
from skimage.morphology import skeletonize, remove_small_holes, closing, disk
from skimage.transform import hough_line, hough_line_peaks, hough_circle, hough_circle_peaks
from skimage.feature import canny
from scipy.ndimage import distance_transform_edt
from scipy.interpolate import splprep, splev
from scipy.spatial.distance import pdist, squareform
import networkx as nx
import svgelements
from svgelements import SVG, Path, Shape, Matrix, Color, Group

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

def rasterize_paths(svg, paths, dpi, svg_filename=None):
    """Rasterize SVG paths to a binary image."""
    # Calculate bounds
    bbox = None
    for path in paths:
        if bbox is None:
            bbox = path.bbox()
        else:
            b = path.bbox()
            if b:
                bbox = (min(bbox[0], b[0]), min(bbox[1], b[1]), 
                        max(bbox[2], b[2]), max(bbox[3], b[3]))
    
    if not bbox:
        logger.error("No content found in SVG")
        sys.exit(1)

    # Add some padding
    padding = 20
    width = int(bbox[2] - bbox[0] + 2 * padding)
    height = int(bbox[3] - bbox[1] + 2 * padding)
    
    # Determine scale to ensure high resolution (min dimension 3000px)
    min_dim_px = 3000
    current_min_dim = min(width, height)
    if current_min_dim < 1: current_min_dim = 1
    
    scale_factor = min_dim_px / current_min_dim
    # Also respect DPI if it results in higher res, but usually 2000px is plenty
    dpi_scale = dpi / 96.0
    scale = max(scale_factor, dpi_scale)
    
    # Calculate target DPI for Inkscape
    # Inkscape base DPI is 96. So target_dpi = 96 * scale
    target_dpi = 96.0 * scale
    
    w_px = int(width * scale)
    h_px = int(height * scale)
    
    logger.info(f"Rasterizing to {w_px}x{h_px} image (Scale: {scale:.2f})")
    
    # Try Inkscape Rasterization first
    inkscape_path = "/Applications/Inkscape.app/Contents/MacOS/inkscape"
    if os.path.exists(inkscape_path) and svg_filename:
        try:
            logger.info("Using Inkscape for high-precision rasterization...")
            # Define export area: x0:y0:x1:y1
            # bbox is (min_x, min_y, max_x, max_y)
            # We want to include padding
            area_x0 = bbox[0] - padding
            area_y0 = bbox[1] - padding
            area_x1 = bbox[2] + padding
            area_y1 = bbox[3] + padding
            
            area_str = f"{area_x0}:{area_y0}:{area_x1}:{area_y1}"
            temp_png = os.path.join(os.path.dirname(svg_filename), "temp_raster.png")
            
            # Inkscape command
            # --export-area=x0:y0:x1:y1
            # --export-dpi=DPI
            # --export-filename=OUTPUT
            cmd = [
                inkscape_path,
                f"--export-area={area_str}",
                f"--export-dpi={target_dpi}",
                f"--export-filename={temp_png}",
                svg_filename
            ]
            
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if os.path.exists(temp_png):
                # Load image
                img = Image.open(temp_png).convert('L')
                # Invert if necessary? Inkscape exports transparent background usually.
                # If we convert to 'L', transparent becomes black (0) or white (255)?
                # Usually transparent -> black in 'L' conversion if we don't handle alpha.
                # Let's handle alpha to be sure.
                img_rgba = Image.open(temp_png).convert('RGBA')
                # Create black background
                bg = Image.new('RGBA', img_rgba.size, (0, 0, 0, 255))
                # Composite: Shape on top of black
                # If shape is black in SVG, it will be black on black?
                # We need the shape to be White (255) and background Black (0) for the algorithm.
                
                # Check if shape is black or white.
                # If shape is black, we need to invert.
                # But we can just use the Alpha channel!
                # The alpha channel is the shape mask.
                alpha = img_rgba.split()[3]
                img = alpha # This gives 0 for background, 255 for shape. Perfect.
                
                os.remove(temp_png)
                
                # Transform
                # P_screen = P_world * Translate(-x0, -y0) * Scale(s, s)
                transform = Matrix.translate(-area_x0, -area_y0) * Matrix.scale(scale)
                
                return np.array(img), transform, (w_px, h_px)
                
        except Exception as e:
            logger.warning(f"Inkscape rasterization failed: {e}. Falling back to internal.")
    
    # Fallback: Internal PIL Rasterization
    img = Image.new('L', (w_px, h_px), 0)
    draw = ImageDraw.Draw(img)
    
    # Transform for drawing
    # We want to map SVG coordinates to Image coordinates
    # 1. Translate to move bbox origin to (padding, padding)
    # 2. Scale to target DPI
    # Order: P * Translate * Scale
    transform = Matrix.translate(-bbox[0] + padding, -bbox[1] + padding) * Matrix.scale(scale)
    
    for path in paths:
        # Apply transform to path
        t_path = path * transform
        
        # Better rasterization: Sample points with high resolution
        try:
            pts = []
            # Iterate over segments in the path
            for seg in t_path:
                # Handle Move (Subpaths)
                if isinstance(seg, svgelements.Move):
                    if len(pts) > 2:
                        draw.polygon(pts, fill=255, outline=255)
                    pts = []
                    # Move destination is the start of new subpath
                    p = seg.end * t_path.transform
                    pts.append((p.x, p.y))
                    continue
                    
                # Sample points from the segment
                # Segments are in local coordinates, need to apply path transform
                if isinstance(seg, (svgelements.Line, svgelements.Close)):
                    p = seg.end * t_path.transform
                    pts.append((p.x, p.y))
                else:
                    # Sample curves (QuadraticBezier, CubicBezier, Arc)
                    # Increase sampling for higher resolution
                    for t in np.linspace(0, 1, 20):
                        p = seg.point(t) * t_path.transform
                        pts.append((p.x, p.y))
            
            if len(pts) > 2:
                draw.polygon(pts, fill=255, outline=255)
                
        except Exception as e:
            logger.warning(f"Failed to rasterize a path: {e}")

    return np.array(img), transform, (w_px, h_px)

def compute_medial_axis(binary_image):
    """Compute Skeleton and Distance Map."""
    logger.info("Computing Skeleton and Distance Map...")
    
    # Clean up binary image
    # Remove small holes (noise)
    # area_threshold is in pixels. For 2000x2000 image, 200px is small.
    # Convert to boolean for skimage
    bool_image = binary_image.astype(bool)
    
    # Remove small holes (internal noise)
    # Increase threshold to remove larger artifacts
    # Note: area_threshold is deprecated in newer skimage, using max_size if available or fallback
    try:
        cleaned_image = remove_small_holes(bool_image, max_size=2000)
    except TypeError:
        cleaned_image = remove_small_holes(bool_image, area_threshold=2000)
    
    # Smooth boundaries to reduce skeleton spurs
    # For high-res Inkscape rasterization, the edge is already clean.
    # Large closing disk rounds corners and merges fine intersections.
    # We reduce it to minimal smoothing or skip it if the image is very clean.
    # Using a very small disk just to smooth pixelation artifacts if any.
    cleaned_image = closing(cleaned_image, disk(1))
    
    # Use skeletonize for a cleaner 1-pixel wide skeleton
    # method='lee' is generally better for medial axis transform than the default 'zhang'
    try:
        skeleton = skeletonize(cleaned_image, method='lee')
    except TypeError:
        # Fallback for older versions
        skeleton = skeletonize(cleaned_image)
        
    # Use distance transform for width estimation
    distance = distance_transform_edt(cleaned_image)
    return skeleton, distance, cleaned_image

def collapse_cycles(G, max_len=200):
    """Collapse small cycles in the graph into single nodes to fix 'knots'."""
    try:
        cycles = nx.cycle_basis(G)
    except nx.NetworkXNoCycle:
        return G
        
    # Filter small cycles
    # We use a larger threshold because high-res images have more nodes
    small_cycles = [c for c in cycles if len(c) <= max_len]
    
    if not small_cycles:
        return G
        
    logger.info(f"Found {len(cycles)} cycles. Collapsing {len(small_cycles)} small cycles (<= {max_len} nodes) to fix topology...")
    
    for i, cycle in enumerate(small_cycles):
        # Check if nodes still exist (might have been merged already)
        valid_nodes = [n for n in cycle if n in G]
        if len(valid_nodes) < 3: continue
            
        # Calculate centroid
        positions = np.array([G.nodes[n]['pos'] for n in valid_nodes])
        centroid = tuple(np.mean(positions, axis=0))
        
        # Merge into the first node
        target = valid_nodes[0]
        G.nodes[target]['pos'] = centroid
        
        for other in valid_nodes[1:]:
            if other not in G: continue
            
            neighbors = list(G.neighbors(other))
            for nbr in neighbors:
                if nbr != target:
                    # Add edge to target
                    w = G[other][nbr].get('weight', 1.0)
                    if not G.has_edge(target, nbr):
                        G.add_edge(target, nbr, weight=w)
            
            G.remove_node(other)
            
    logger.info("Cycle collapse complete.")
            
    return G

def skeleton_to_graph(skeleton):
    """Convert skeleton image to a NetworkX graph."""
    rows, cols = np.where(skeleton)
    points = list(zip(rows, cols))
    point_to_idx = {pt: i for i, pt in enumerate(points)}
    
    G = nx.Graph()
    
    for r, c in points:
        idx = point_to_idx[(r, c)]
        G.add_node(idx, pos=(r, c))
        
        # Check 8-neighbors
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0: continue
                nr, nc = r + dr, c + dc
                if (nr, nc) in point_to_idx:
                    n_idx = point_to_idx[(nr, nc)]
                    # Add edge with weight = distance (1 or sqrt(2))
                    dist = np.sqrt(dr**2 + dc**2)
                    G.add_edge(idx, n_idx, weight=dist)
    return G

def prune_skeleton_graph(G, min_spur_length_px):
    """Remove short branches (spurs) from the graph."""
    logger.info(f"Pruning skeleton spurs shorter than {min_spur_length_px}px...")
    total_pruned = 0
    
    while True:
        changed = False
        # Find all degree-1 nodes (endpoints)
        endpoints = [n for n, d in G.degree() if d == 1]
        
        for n in endpoints:
            if n not in G: continue # Already removed in this pass
            
            # Walk from endpoint until we hit a junction (degree > 2) or another endpoint
            path = [n]
            curr = n
            prev = None
            length = 0
            is_spur = True
            
            while True:
                if G.degree(curr) > 2:
                    # Reached a junction - this is a spur connected to a main body
                    break
                
                neighbors = list(G.neighbors(curr))
                # Filter out previous node
                valid_neighbors = [nbr for nbr in neighbors if nbr != prev]
                
                if not valid_neighbors:
                    # Reached another endpoint (isolated line)
                    # If we are here, it means the whole component is just a line.
                    # We check if the total length is small.
                    if length > min_spur_length_px:
                        is_spur = False
                    break
                
                next_node = valid_neighbors[0]
                
                # Add distance
                p1 = np.array(G.nodes[curr]['pos'])
                p2 = np.array(G.nodes[next_node]['pos'])
                dist = np.linalg.norm(p1 - p2)
                length += dist
                
                if length > min_spur_length_px:
                    is_spur = False
                    break
                
                prev = curr
                curr = next_node
                path.append(curr)
            
            if is_spur:
                # Remove the path nodes (excluding the junction if we hit one)
                # If we hit a junction, 'curr' is the junction. We remove path[:-1] if path includes curr?
                # Wait, 'path' includes 'curr' at the end of the loop.
                # If we broke because degree > 2, 'curr' is the junction.
                # We want to keep the junction.
                
                nodes_to_remove = []
                if G.degree(curr) > 2:
                    nodes_to_remove = path[:-1] # Don't remove junction
                else:
                    # Isolated short line
                    nodes_to_remove = path # Remove everything
                
                if nodes_to_remove:
                    G.remove_nodes_from(nodes_to_remove)
                    total_pruned += 1
                    changed = True
        
        if not changed:
            break
            
    logger.info(f"Pruned {total_pruned} spur branches.")
    return G

def get_skeleton_paths(skeleton, min_len_px=15):
    """Decompose skeleton into simple paths between junctions/endpoints."""
    G = skeleton_to_graph(skeleton)
    logger.info(f"Initial graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    
    if G.number_of_nodes() == 0:
        return [], G
    
    # Fix topology: Collapse small cycles (knots)
    # Use a larger threshold to catch all knots in high-res images
    G = collapse_cycles(G, max_len=200)
    
    # Prune spurs
    G = prune_skeleton_graph(G, min_len_px)
    logger.info(f"Pruned graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    
    paths = []
    visited_edges = set()
    
    # Nodes with degree != 2 are junctions or endpoints
    nodes_of_interest = [n for n, d in G.degree() if d != 2]
    
    # If the skeleton is a perfect loop (all degree 2), pick one arbitrary node
    if not nodes_of_interest and G.number_of_nodes() > 0:
        nodes_of_interest = [list(G.nodes())[0]]
        
    for start_node in nodes_of_interest:
        if start_node not in G: continue
        
        for neighbor in G.neighbors(start_node):
            edge = tuple(sorted((start_node, neighbor)))
            if edge in visited_edges:
                continue
                
            # Traverse this path
            current_path = [start_node, neighbor]
            visited_edges.add(edge)
            
            curr = neighbor
            prev = start_node
            
            while True:
                # If current node is a junction or endpoint (degree != 2), stop
                if G.degree(curr) != 2:
                    break
                    
                # Get neighbors of current node excluding previous
                nbrs = [n for n in G.neighbors(curr) if n != prev]
                
                if not nbrs: # Should not happen if degree == 2
                    break
                    
                next_node = nbrs[0]
                edge = tuple(sorted((curr, next_node)))
                visited_edges.add(edge)
                
                current_path.append(next_node)
                prev = curr
                curr = next_node
                
                if curr == start_node: # Loop closed
                    break
            
            # Convert to coordinates
            path_points = [G.nodes[i]['pos'] for i in current_path]
            # Store path with start/end node info for intersection handling
            # (points, start_node_idx, end_node_idx)
            paths.append({
                'points': np.array(path_points),
                'start_node': start_node,
                'end_node': curr
            })
                
    return paths, G

def analyze_shapes(binary_img, skeleton, G):
    """
    Analyze the image structure using Hough Transforms and Skeleton Graph.
    Returns a dictionary with shape analysis results.
    """
    logger.info("Analyzing image structure...")
    results = {
        'has_intersections': False,
        'detected_shapes': [],
        'junctions': []
    }
    
    # 1. Analyze Skeleton Graph for Intersections
    # Junctions are nodes with degree > 2
    junctions = [n for n, d in G.degree() if d > 2]
    if junctions:
        results['has_intersections'] = True
        results['junctions'] = junctions
        logger.info(f"Detected {len(junctions)} intersections in the skeleton.")
    else:
        logger.info("No intersections detected in the skeleton (Simple structure).")
        
    # 2. Hough Transform for Circles (Simple Shape Detection)
    # Optimization: Downscale for Hough Transform to improve performance
    from skimage.transform import resize
    
    scale_hough = 500.0 / max(binary_img.shape)
    if scale_hough < 1.0:
        img_small = resize(binary_img, (int(binary_img.shape[0]*scale_hough), int(binary_img.shape[1]*scale_hough)), anti_aliasing=True)
    else:
        img_small = binary_img
        scale_hough = 1.0
        
    # Detect edges for Hough on small image
    edges = canny(img_small, sigma=2) # Lower sigma for smaller image
    
    # Detect radii range (heuristic)
    # Scale radii range
    min_rad = max(5, int(10 * scale_hough))
    max_rad = max(10, int(max(binary_img.shape)//2 * scale_hough))
    step = max(1, int(2 * scale_hough))
    
    h_radii = np.arange(min_rad, max_rad, 2) # Step 2 is fine for small image
    
    if len(h_radii) > 0:
        hough_res = hough_circle(edges, h_radii)
        
        # Select the most prominent 3 circles
        accums, cx, cy, radii = hough_circle_peaks(hough_res, h_radii, total_num_peaks=3)
        
        for center_y, center_x, radius in zip(cy, cx, radii):
            # Scale back to original coordinates
            orig_cx = center_x / scale_hough
            orig_cy = center_y / scale_hough
            orig_r = radius / scale_hough
            
            logger.info(f"Potential Circle detected: center=({orig_cx:.1f}, {orig_cy:.1f}), radius={orig_r:.1f}")
            results['detected_shapes'].append({'type': 'circle', 'center': (orig_cx, orig_cy), 'radius': orig_r})

    # 3. Hough Transform for Lines
    tested_angles = np.linspace(-np.pi / 2, np.pi / 2, 360, endpoint=False)
    h, theta, d = hough_line(edges, theta=tested_angles)
    
    for _, angle, dist in zip(*hough_line_peaks(h, theta, d, num_peaks=3)):
        # Scale distance back?
        # dist = x * cos(theta) + y * sin(theta)
        # If x, y are scaled by S, dist is scaled by S.
        orig_dist = dist / scale_hough
        logger.info(f"Potential Line detected: angle={np.degrees(angle):.1f}°, dist={orig_dist:.1f}")
        results['detected_shapes'].append({'type': 'line', 'angle': angle, 'dist': orig_dist})

        
    return results

def get_ray_intersection(binary_img, start_x, start_y, dx, dy, max_dist):
    """Cast a ray and find where it hits the background (0)."""
    h, w = binary_img.shape
    
    # Walk along the ray
    steps = int(max_dist)
    if steps <= 0:
        return start_x, start_y
        
    for i in range(1, steps + 1):
        cx = int(start_x + dx * i)
        cy = int(start_y + dy * i)
        
        if cx < 0 or cx >= w or cy < 0 or cy >= h:
            return cx - dx, cy - dy # Return last valid
            
        if binary_img[cy, cx] == 0:
            # Found edge
            return cx, cy
            
    return start_x + dx * max_dist, start_y + dy * max_dist

def merge_aligned_paths(paths, G, spacing_px):
    """Merge paths that are aligned at junctions to form continuous flows."""
    # Build adjacency map: Node -> [PathIndices]
    node_to_paths = {}
    for i, p in enumerate(paths):
        s, e = p['start_node'], p['end_node']
        if s not in node_to_paths: node_to_paths[s] = []
        if e not in node_to_paths: node_to_paths[e] = []
        node_to_paths[s].append(i)
        node_to_paths[e].append(i)
        
    # Identify junctions
    junctions = [n for n, d in G.degree() if d > 2]
    
    # Track merges: old_idx -> new_path_obj (if merged)
    # Actually, let's just build a new list of paths
    
    # We need an iterative approach because merging A-B and B-C might happen.
    # But for simplicity, let's just do one pass of greedy merging at junctions.
    
    # Sort junctions by degree? Or just process.
    
    # We will mark paths as "merged" to avoid double usage.
    merged_indices = set()
    new_paths = []
    
    # Helper to get vector at end of path
    def get_end_vector(path_idx, node):
        pts = paths[path_idx]['points']
        # Is node start or end?
        if paths[path_idx]['start_node'] == node:
            # Vector pointing AWAY from node (into path)
            # Use first few points
            p0 = pts[0]
            p1 = pts[min(5, len(pts)-1)]
            return p1 - p0
        else:
            # Vector pointing AWAY from node (into path)
            p0 = pts[-1]
            p1 = pts[max(0, len(pts)-6)]
            return p1 - p0

    # Process junctions to find "Main Flows"
    # We want to link paths.
    # Link map: PathIdx -> [ (ConnectedPathIdx, JunctionNode) ]
    links = []
    
    for j in junctions:
        connected_indices = [i for i in node_to_paths.get(j, []) if i not in merged_indices]
        if len(connected_indices) < 2: continue
        
        # Find best pair
        best_pair = None
        max_score = -1
        
        vectors = {}
        for idx in connected_indices:
            v = get_end_vector(idx, j)
            norm = np.linalg.norm(v)
            if norm > 0: v = v / norm
            vectors[idx] = v
            
        for i in range(len(connected_indices)):
            for k in range(i+1, len(connected_indices)):
                idx1 = connected_indices[i]
                idx2 = connected_indices[k]
                v1 = vectors[idx1]
                v2 = vectors[idx2]
                
                # Dot product. 
                # v1 points into path 1. v2 points into path 2.
                # If they form a straight line, angle is 180, dot is -1.
                dot = np.dot(v1, v2)
                
                # We want dot close to -1
                if dot < -0.5: # Angle > 120 degrees
                    score = -dot
                    if score > max_score:
                        max_score = score
                        best_pair = (idx1, idx2)
        
        if best_pair:
            p1, p2 = best_pair
            links.append((p1, p2, j))
            
    # Now execute merges based on links
    # Use a Union-Find or Graph to merge connected components of paths
    path_graph = nx.Graph()
    path_graph.add_nodes_from(range(len(paths)))
    for p1, p2, j in links:
        path_graph.add_edge(p1, p2, junction=j)
        
    # Extract components
    for component in nx.connected_components(path_graph):
        # component is a set of path indices
        # We need to order them.
        # A simple component is a line of paths: P1 - P2 - P3
        # If it's a star (unlikely with our pair selection), we have an issue.
        # Our pair selection is greedy per junction, but a path has 2 ends.
        # So we can have P1-J1-P2-J2-P3. This is fine.
        
        # Linearize the component
        comp_list = list(component)
        if len(comp_list) == 1:
            new_paths.append(paths[comp_list[0]])
            continue
            
        # Find endpoints of the chain (degree 1 in path_graph)
        subg = path_graph.subgraph(comp_list)
        endpoints = [n for n, d in subg.degree() if d == 1]
        
        if not endpoints:
            # Cycle? Break it anywhere.
            start_node = comp_list[0]
        else:
            start_node = endpoints[0]
            
        # Traverse
        ordered_indices = []
        curr = start_node
        visited = {curr}
        ordered_indices.append(curr)
        
        while True:
            nbrs = [n for n in subg.neighbors(curr) if n not in visited]
            if not nbrs: break
            curr = nbrs[0]
            visited.add(curr)
            ordered_indices.append(curr)
            
        # Merge points
        merged_points = []
        # We need to orient paths correctly
        # P1 ends at J1. P2 starts at J1.
        
        # Start with first path
        curr_idx = ordered_indices[0]
        curr_path = paths[curr_idx]
        
        # Determine orientation
        # Look at next path to see which end connects
        if len(ordered_indices) > 1:
            next_idx = ordered_indices[1]
            j_node = subg[curr_idx][next_idx]['junction']
            
            if curr_path['end_node'] == j_node:
                # Correct orientation
                pts = curr_path['points']
            else:
                # Flip
                pts = curr_path['points'][::-1]
        else:
            pts = curr_path['points']
            
        merged_points.append(pts)
        
        last_junction = None
        
        for k in range(1, len(ordered_indices)):
            prev_idx = ordered_indices[k-1]
            curr_idx = ordered_indices[k]
            j_node = subg[prev_idx][curr_idx]['junction']
            
            curr_path = paths[curr_idx]
            
            # Orient current path so it STARTS at j_node
            if curr_path['start_node'] == j_node:
                pts = curr_path['points']
            else:
                pts = curr_path['points'][::-1]
                
            # Append (skip first point as it duplicates junction)
            merged_points.append(pts[1:])
            
        # Concatenate
        full_points = np.vstack(merged_points)
        
        # Determine actual start/end nodes in G
        first_path_idx = ordered_indices[0]
        last_path_idx = ordered_indices[-1]
        
        real_start_node = -1
        real_end_node = -1
        
        if len(ordered_indices) > 1:
            # First path
            second_path_idx = ordered_indices[1]
            if subg.has_edge(first_path_idx, second_path_idx):
                j_node = subg[first_path_idx][second_path_idx]['junction']
                p_start = paths[first_path_idx]
                real_start_node = p_start['start_node'] if p_start['end_node'] == j_node else p_start['end_node']
            
            # Last path
            second_last_idx = ordered_indices[-2]
            if subg.has_edge(last_path_idx, second_last_idx):
                j_node_end = subg[last_path_idx][second_last_idx]['junction']
                p_end = paths[last_path_idx]
                real_end_node = p_end['start_node'] if p_end['end_node'] == j_node_end else p_end['end_node']
        
        # Create new path object
        new_p = {
            'points': full_points,
            'start_node': real_start_node,
            'end_node': real_end_node,
            'original_indices': ordered_indices,
            'is_merged': True
        }
        new_paths.append(new_p)
        
    return new_paths

def generate_rungs(skeleton, distance_map, spacing_px, transform, binary_img, debug_dir=None):
    """Generate rungs along the medial axis with adaptive spacing and bridges."""
    logger.info("Generating rungs...")
    
    # Calculate dynamic pruning threshold (e.g., 2% of max dimension)
    max_dim = max(binary_img.shape)
    prune_threshold = max(15, int(max_dim * 0.02))
    logger.info(f"Using skeleton pruning threshold: {prune_threshold}px")
    
    # Get all valid paths from the skeleton
    skeleton_paths, G = get_skeleton_paths(skeleton, min_len_px=prune_threshold)
    
    # Analyze Structure
    structure_info = analyze_shapes(binary_img, skeleton, G)
    
    if debug_dir:
        # Save Graph Debug SVG
        debug_graph_path = os.path.join(debug_dir, "debug_06_graph.svg")
        logger.info(f"Saving debug graph to {debug_graph_path}")
        
        # Inverse transform for debug SVG
        inv_transform = ~transform
        
        lines = []
        lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{binary_img.shape[1]}" height="{binary_img.shape[0]}">')
        
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
            
        lines.append('</svg>')
        
        with open(debug_graph_path, 'w') as f:
            f.write("\n".join(lines))
    
    if not skeleton_paths:
        logger.warning("No valid skeleton paths found.")
        return [], []
        
    # --- Merge Aligned Paths ---
    logger.info("Merging aligned paths to create continuous flows...")
    merged_paths = merge_aligned_paths(skeleton_paths, G, spacing_px)
    logger.info(f"Merged {len(skeleton_paths)} segments into {len(merged_paths)} continuous paths.")
    
    rungs = []
    bridges = []
    
    # Store all generated rungs to find connections later
    # Map: PathIndex -> List of (RungLine, CenterPoint)
    path_rungs_map = {}
    
    # --- 1. Generate Rungs for All Paths ---
    for p_idx, path_data in enumerate(merged_paths):
        path_points = path_data['points']
        
        y = path_points[:, 0]
        x = path_points[:, 1]
        
        # Downsample slightly for spline fitting but keep enough for curvature
        if len(x) > 100:
            indices = np.linspace(0, len(x)-1, 100, dtype=int)
            x = x[indices]
            y = y[indices]
            
        try:
            k = 3 if len(x) > 3 else (2 if len(x) > 2 else 1)
            if len(x) <= k: continue
            
            # Smoothing factor s. 
            # s=len(x) is a good compromise between smoothing noise and hugging the path.
            # Lower s means closer fit.
            tck, u = splprep([x, y], s=len(x), k=k) 
            
            # High-res evaluation for integration
            u_fine = np.linspace(0, 1, 1000)
            x_fine, y_fine = splev(u_fine, tck)
            dx_fine, dy_fine = splev(u_fine, tck, der=1)
            
            # Calculate curvature safely
            if k >= 2:
                ddx_fine, ddy_fine = splev(u_fine, tck, der=2)
                # Calculate curvature: k = |x'y'' - y'x''| / (x'^2 + y'^2)^(3/2)
                denom = np.power(dx_fine**2 + dy_fine**2, 1.5)
                # Avoid division by zero
                denom[denom < 1e-6] = 1e-6
                curvature = np.abs(dx_fine * ddy_fine - dy_fine * ddx_fine) / denom
            else:
                curvature = np.zeros_like(u_fine)
            
            # Calculate cumulative distance
            dist_along = np.cumsum(np.sqrt(np.diff(x_fine)**2 + np.diff(y_fine)**2))
            dist_along = np.insert(dist_along, 0, 0)
            total_len = dist_along[-1]
            
            # Define safe zones
            start_dist = 0
            end_dist = total_len
            
            # Adaptive stepping
            current_dist = start_dist
            target_dists = []
            
            while current_dist < end_dist:
                target_dists.append(current_dist)
                
                # Find current u to get curvature
                curr_u = np.interp(current_dist, dist_along, u_fine)
                curr_k = np.interp(curr_u, u_fine, curvature)
                
                # Adjust spacing based on curvature
                density_factor = 1.0 + min(curr_k * 50.0, 2.0) # Cap at 3x density
                step = spacing_px / density_factor
                step = max(step, spacing_px * 0.3)
                
                current_dist += step
            
            # Interpolate u for target distances
            target_u = np.interp(target_dists, dist_along, u_fine)
            
            x_rungs, y_rungs = splev(target_u, tck)
            dx_rungs, dy_rungs = splev(target_u, tck, der=1)
            
            if isinstance(x_rungs, float):
                x_rungs = [x_rungs]; y_rungs = [y_rungs]; dx_rungs = [dx_rungs]; dy_rungs = [dy_rungs]
            
            path_generated_rungs = []
            
            for i in range(len(x_rungs)):
                cur_x = x_rungs[i]
                cur_y = y_rungs[i]
                dx = dx_rungs[i]
                dy = dy_rungs[i]
                
                nx = -dy
                ny = dx
                norm = np.sqrt(nx**2 + ny**2)
                if norm == 0: continue
                nx /= norm
                ny /= norm
                
                est_radius = distance_map[int(np.clip(cur_y, 0, binary_img.shape[0]-1)), 
                                          int(np.clip(cur_x, 0, binary_img.shape[1]-1))]
                max_search = max(est_radius * 3.0, 10.0)
                
                p1_x, p1_y = get_ray_intersection(binary_img, cur_x, cur_y, nx, ny, max_search)
                p2_x, p2_y = get_ray_intersection(binary_img, cur_x, cur_y, -nx, -ny, max_search)
                
                # Extend rungs
                extension = 2.0
                vx = p1_x - p2_x
                vy = p1_y - p2_y
                v_len = np.sqrt(vx**2 + vy**2)
                
                if v_len < 2: continue
                
                vx /= v_len
                vy /= v_len
                
                p1_x += vx * extension
                p1_y += vy * extension
                p2_x -= vx * extension
                p2_y -= vy * extension
                
                rung = ((p1_x, p1_y), (p2_x, p2_y))
                center = (cur_x, cur_y)
                
                rungs.append(rung)
                path_generated_rungs.append({'rung': rung, 'center': center, 'u': target_u[i]})
                
            path_rungs_map[p_idx] = path_generated_rungs
                
        except Exception as e:
            logger.error(f"Spline fitting failed for a segment: {e}")
            continue

    # --- 2. Generate Bridges (Conditional) ---
    if structure_info['has_intersections']:
        logger.info("Intersections detected. Generating bridges at junctions...")
        # Graph-guided bridge generation
        junctions = structure_info['junctions']
        
        # Map Junction -> Set of PathIndices
        j_map = {j: set() for j in junctions}
        
        for p_idx, p in enumerate(merged_paths):
            # Check endpoints
            if p['start_node'] in j_map: j_map[p['start_node']].add(p_idx)
            if p['end_node'] in j_map: j_map[p['end_node']].add(p_idx)
            
            # Check internal junctions
            if 'original_indices' in p:
                for orig_idx in p['original_indices']:
                    op = skeleton_paths[orig_idx]
                    if op['start_node'] in j_map: j_map[op['start_node']].add(p_idx)
                    if op['end_node'] in j_map: j_map[op['end_node']].add(p_idx)
            
        for j, connected_paths in j_map.items():
            if len(connected_paths) < 2: continue
            
            # Get the rung closest to J for each path
            path_endpoints = []
            j_pos = G.nodes[j]['pos'] # (y, x)
            
            for p_idx in connected_paths:
                if p_idx not in path_rungs_map or not path_rungs_map[p_idx]: continue
                
                p_rungs = path_rungs_map[p_idx]
                
                # Find closest rung to junction
                best_rung = None
                min_dist = float('inf')
                
                for r in p_rungs:
                    # r['center'] is (x, y)
                    # j_pos is (y, x)
                    d = (r['center'][0] - j_pos[1])**2 + (r['center'][1] - j_pos[0])**2
                    if d < min_dist:
                        min_dist = d
                        best_rung = r
                        
                if best_rung:
                    path_endpoints.append(best_rung)
                
            # Create bridges between these endpoints
            for i in range(len(path_endpoints)):
                for k in range(i+1, len(path_endpoints)):
                    r1 = path_endpoints[i]
                    r2 = path_endpoints[k]
                    
                    # Distance check (sanity)
                    d = np.linalg.norm(np.array(r1['center']) - np.array(r2['center']))
                    if d < spacing_px * 10: # Allow larger gap for junctions
                        bridges.append((r1['center'], r2['center']))
                        
    else:
        logger.info("No intersections. Skipping bridge generation.")
            
    # Filter duplicate bridges
    unique_bridges = []
    seen_bridges = set()
    for b in bridges:
        p1, p2 = b
        k = tuple(sorted(((round(p1[0], 1), round(p1[1], 1)), (round(p2[0], 1), round(p2[1], 1)))))
        if k not in seen_bridges:
            seen_bridges.add(k)
            unique_bridges.append(b)
            
    return rungs, unique_bridges

def save_rungs_svg(original_svg_path, output_path, rungs, transform):
    """Save the generated rungs to a new SVG file."""
    logger.info(f"Saving {len(rungs)} rungs to {output_path}")
    
    # Inverse transform to map back to original SVG coordinates
    inv_transform = ~transform
    logger.info(f"Inverse Transform: {inv_transform}")
    
    # Test inverse
    test_img_pt = svgelements.Point(31.25, 31.25)
    test_svg_pt = test_img_pt * inv_transform
    logger.info(f"Test Inverse (31.25, 31.25) -> {test_svg_pt}")
    
    # Load original to keep context or start fresh?
    # Usually we want to overlay or just output the rungs.
    # Let's output a new SVG with just the rungs for Inkstitch to consume, 
    # or append to the original. The prompt says "your_design_rungs.svg".
    
    # Inverse transform to map back to original SVG coordinates
    inv_transform = ~transform
    
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
            pt1 = svgelements.Point(p1[0], p1[1]) * inv_transform
            pt2 = svgelements.Point(p2[0], p2[1]) * inv_transform
            f.write(f'  <line x1="{pt1.x:.2f}" y1="{pt1.y:.2f}" x2="{pt2.x:.2f}" y2="{pt2.y:.2f}" />\n')
        f.write('</g>\n')
        
        # Bridges (Blue)
        f.write(f'<g id="bridges" stroke="blue" stroke-width="0.1">\n')
        for p1, p2 in bridges:
            pt1 = svgelements.Point(p1[0], p1[1]) * inv_transform
            pt2 = svgelements.Point(p2[0], p2[1]) * inv_transform
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
        pt1 = svgelements.Point(p1[0], p1[1]) * inv_transform
        pt2 = svgelements.Point(p2[0], p2[1]) * inv_transform
        rungs_svg.append(f'    <line x1="{pt1.x:.2f}" y1="{pt1.y:.2f}" x2="{pt2.x:.2f}" y2="{pt2.y:.2f}" />')
    rungs_svg.append('  </g>')
    
    rungs_svg.append(f'  <g id="rungs_bridges" stroke="blue" stroke-width="0.1">')
    for p1, p2 in bridges:
        pt1 = svgelements.Point(p1[0], p1[1]) * inv_transform
        pt2 = svgelements.Point(p2[0], p2[1]) * inv_transform
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
    
    if args.debug:
        # 1. Original Rasterized (Raw)
        Image.fromarray((binary_img * 255).astype(np.uint8)).save(os.path.join(debug_dir, "debug_01_original.png"))
        
    # Medial Axis
    skeleton, distance, cleaned_binary = compute_medial_axis(binary_img)
    
    if args.debug:
        # 2. Cleaned Binary (Used for Skeletonization)
        Image.fromarray((cleaned_binary * 255).astype(np.uint8)).save(os.path.join(debug_dir, "debug_02_binary.png"))
        
        # 3. Distance Map
        # Normalize distance for display
        d_norm = (distance / np.max(distance) * 255).astype(np.uint8)
        Image.fromarray(d_norm).save(os.path.join(debug_dir, "debug_03_distance.png"))
        
        # 4. Skeleton
        # Dilate skeleton for visibility in debug image
        from skimage.morphology import dilation
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
        
    # Generate Rungs
    # Convert spacing mm to pixels
    scale_factor = args.dpi / 96.0
    # Apply density: higher density -> smaller spacing
    spacing_px = (args.spacing / args.density) * (args.dpi / 25.4)
    
    debug_dir_path = debug_dir if args.debug else None
    rungs, bridges = generate_rungs(skeleton, distance, spacing_px, transform, binary_img, debug_dir=debug_dir_path)
    
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
