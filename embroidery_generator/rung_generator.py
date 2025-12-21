import logging
import numpy as np
from scipy.interpolate import splprep, splev
from .geometry_utils import get_skeleton_paths, merge_aligned_paths, find_shape_boundaries, segments_intersect
from .image_processor import analyze_shapes
from .debug_utils import save_debug_graph, save_rung_coverage_debug

logger = logging.getLogger(__name__)

def fill_coverage_gaps(binary_img, rungs, distance_map, spacing_px):
    """
    Analyze coverage and add additional rungs to fill gaps.
    Returns additional rungs to add.
    """
    logger.info("Analyzing coverage gaps...")
    
    # Create coverage map
    coverage = np.zeros_like(binary_img, dtype=np.uint8)
    
    # Draw existing rungs
    for rung in rungs:
        (p1_x, p1_y), (p2_x, p2_y) = rung
        from skimage.draw import line
        rr, cc = line(int(p1_y), int(p1_x), int(p2_y), int(p2_x))
        valid = (rr >= 0) & (rr < coverage.shape[0]) & (cc >= 0) & (cc < coverage.shape[1])
        coverage[rr[valid], cc[valid]] = 255
    
    # Dilate coverage to account for line width
    from skimage.morphology import dilation, disk
    coverage_dilated = dilation(coverage, disk(3))  # Larger dilation for gap detection
    
    # Find significant gaps (clusters of uncovered pixels)
    gaps = (binary_img > 0) & (coverage_dilated == 0)
    
    if np.sum(gaps) == 0:
        logger.info("No significant gaps found.")
        return []
    
    # Find gap centroids using connected components
    from skimage.measure import label, regionprops
    
    labeled_gaps = label(gaps)
    gap_regions = regionprops(labeled_gaps)
    
    additional_rungs = []
    
    for region in gap_regions:
        # Skip very small gaps
        if region.area < 50:
            continue
            
        # Get centroid
        cy, cx = region.centroid
        
        # Check if this point is on the skeleton (should be fillable)
        if binary_img[int(cy), int(cx)] == 0:
            continue
            
        # Get local width from distance map
        local_width = distance_map[int(cy), int(cx)]
        
        # Try to find a good direction for the rung
        # Use gradient of distance map to find perpendicular to skeleton
        dy, dx = np.gradient(distance_map)
        
        # Direction perpendicular to gradient gives us the skeleton direction
        grad_x = dx[int(cy), int(cx)]
        grad_y = dy[int(cy), int(cx)]
        
        # Perpendicular vector (normal to skeleton)
        nx = -grad_y
        ny = grad_x
        norm = np.sqrt(nx**2 + ny**2)
        
        if norm > 0:
            nx /= norm
            ny /= norm
            
            # Cast rays to find boundaries
            max_search = max(local_width * 4.0, 20.0)
            boundaries = find_shape_boundaries(binary_img, cx, cy, nx, ny, max_search)
            
            if boundaries:
                (p1_x, p1_y), (p2_x, p2_y) = boundaries
                
                # Extend slightly
                extension = max(local_width * 0.1, 3.0)
                vx = p1_x - p2_x
                vy = p1_y - p2_y
                v_len = np.sqrt(vx**2 + vy**2)
                
                if v_len > 0:
                    vx /= v_len
                    vy /= v_len
                    
                    p1_x += vx * extension
                    p1_y += vy * extension
                    p2_x -= vx * extension
                    p2_y -= vy * extension
                
                rung = ((p1_x, p1_y), (p2_x, p2_y))
                additional_rungs.append(rung)
                logger.info(f"Added gap-filling rung at ({cx:.1f}, {cy:.1f})")
    
    logger.info(f"Added {len(additional_rungs)} gap-filling rungs")
    return additional_rungs

def find_rung_at_endpoint(x, y, binary_img, distance_map, max_length):
    """Create a rung at a specific endpoint position."""
    # Check if the point is within the shape
    if not (0 <= int(y) < binary_img.shape[0] and 0 <= int(x) < binary_img.shape[1]):
        return None
    
    if binary_img[int(y), int(x)] == 0:
        return None
    
    # Get local width from distance map
    local_width = distance_map[int(y), int(x)]
    
    # Try different directions to find valid rung
    directions = [
        (1, 0),   # right
        (-1, 0),  # left  
        (0, 1),   # down
        (0, -1),  # up
        (0.707, 0.707),   # diagonal
        (0.707, -0.707),  # diagonal
        (-0.707, 0.707),  # diagonal
        (-0.707, -0.707)  # diagonal
    ]
    
    for dx, dy in directions:
        # Cast ray in this direction
        search_dist = min(max_length, local_width * 2.0)
        found_boundary = False
        boundary_point = None
        
        for dist in range(1, int(search_dist) + 1):
            test_x = x + dx * dist
            test_y = y + dy * dist
            
            if not (0 <= int(test_y) < binary_img.shape[0] and 0 <= int(test_x) < binary_img.shape[1]):
                break
                
            if binary_img[int(test_y), int(test_x)] == 0:
                # Found boundary
                boundary_point = (test_x, test_y)
                found_boundary = True
                break
        
        if found_boundary and boundary_point:
            # Create rung from current point to boundary
            rung_length = ((boundary_point[0] - x)**2 + (boundary_point[1] - y)**2)**0.5
            if rung_length > 2.0:  # Minimum meaningful length
                return ((x, y), boundary_point)
    
    # If no good direction found, create a small rung in the most open direction
    # This ensures we have some rung even if it's not optimal
    local_width = max(local_width, 5.0)
    return ((x - local_width * 0.5, y), (x + local_width * 0.5, y))

def generate_rungs(skeleton, distance_map, spacing_px, transform, binary_img, path_endpoints=None, debug_dir=None):
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
        save_debug_graph(debug_dir, G, binary_img.shape)
    
    if not skeleton_paths:
        logger.warning("No valid skeleton paths found.")
        return [], []
        
    # --- Merge Aligned Paths ---
    logger.info("Merging aligned paths to create continuous flows...")
    merged_paths = merge_aligned_paths(skeleton_paths, G, spacing_px)
    logger.info(f"Merged {len(skeleton_paths)} segments into {len(merged_paths)} continuous paths.")
    
    rungs = []
    bridges = []
    rejected_rungs_debug = []
    
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
            
            # Adaptive stepping - ensure rungs at endpoints for proper satin definition
            # For InkStitch-like behavior, place rungs from start to end with appropriate density
            segment_length = total_len
            
            # Iterative density adjustment
            # Try to generate rungs with current spacing. If intersections occur, increase spacing.
            current_spacing = spacing_px
            best_rungs = []
            best_rejections = float('inf')
            
            # Max attempts to find a non-intersecting set
            for attempt in range(5):
                # Calculate number of rungs based on current spacing
                num_rungs = max(2, int(total_len / current_spacing) + 1)
                
                # Generate target distances (uniform spacing)
                if num_rungs == 2:
                    target_dists = [0.0, total_len]
                else:
                    target_dists = np.linspace(0.0, total_len, num_rungs)
                
                # Interpolate u for target distances
                target_u = np.interp(target_dists, dist_along, u_fine)
                
                x_rungs, y_rungs = splev(target_u, tck)
                dx_rungs, dy_rungs = splev(target_u, tck, der=1)
                
                if isinstance(x_rungs, float):
                    x_rungs = [x_rungs]; y_rungs = [y_rungs]; dx_rungs = [dx_rungs]; dy_rungs = [dy_rungs]
                
                # --- Normal Smoothing Pass ---
                # Calculate raw normals
                raw_normals = []
                for i in range(len(dx_rungs)):
                    dx, dy = dx_rungs[i], dy_rungs[i]
                    nx, ny = -dy, dx
                    norm = np.sqrt(nx**2 + ny**2)
                    if norm > 0:
                        raw_normals.append((nx/norm, ny/norm))
                    else:
                        raw_normals.append((0, 0))
                
                # Smooth normals using a moving average
                smoothed_normals = []
                window_size = 5
                half_window = window_size // 2
                
                for i in range(len(raw_normals)):
                    start_idx = max(0, i - half_window)
                    end_idx = min(len(raw_normals), i + half_window + 1)
                    sum_nx = sum(raw_normals[j][0] for j in range(start_idx, end_idx))
                    sum_ny = sum(raw_normals[j][1] for j in range(start_idx, end_idx))
                    count = end_idx - start_idx
                    
                    if count > 0:
                        avg_nx = sum_nx / count
                        avg_ny = sum_ny / count
                        norm = np.sqrt(avg_nx**2 + avg_ny**2)
                        if norm > 0:
                            smoothed_normals.append((avg_nx/norm, avg_ny/norm))
                        else:
                            smoothed_normals.append(raw_normals[i])
                    else:
                        smoothed_normals.append(raw_normals[i])
                
                # Generate candidate rungs
                candidate_rungs = []
                valid_generation = True
                
                for i in range(len(x_rungs)):
                    cur_x = x_rungs[i]
                    cur_y = y_rungs[i]
                    nx, ny = smoothed_normals[i]
                    
                    est_radius = distance_map[int(np.clip(cur_y, 0, binary_img.shape[0]-1)), 
                                              int(np.clip(cur_x, 0, binary_img.shape[1]-1))]
                    max_search = max(est_radius * 4.0, 20.0)
                    
                    boundaries = find_shape_boundaries(binary_img, cur_x, cur_y, nx, ny, max_search)
                    
                    if boundaries is None: continue
                        
                    (p1_x, p1_y), (p2_x, p2_y) = boundaries
                    rung_length = np.sqrt((p1_x - p2_x)**2 + (p1_y - p2_y)**2)
                    
                    if rung_length < 2.0: continue
                    
                    # Extension
                    extension = max(est_radius * 0.1, 3.0)
                    vx = p1_x - p2_x
                    vy = p1_y - p2_y
                    v_len = np.sqrt(vx**2 + vy**2)
                    if v_len > 0:
                        vx /= v_len; vy /= v_len
                        p1_x += vx * extension; p1_y += vy * extension
                        p2_x -= vx * extension; p2_y -= vy * extension
                    
                    rung = ((p1_x, p1_y), (p2_x, p2_y))
                    center = (cur_x, cur_y)
                    candidate_rungs.append({'rung': rung, 'center': center, 'u': target_u[i], 'length': rung_length})
                
                # Check for intersections in this candidate set
                intersections_count = 0
                if len(candidate_rungs) > 1:
                    for i in range(len(candidate_rungs)-1):
                        p1, p2 = candidate_rungs[i]['rung']
                        p3, p4 = candidate_rungs[i+1]['rung']
                        if segments_intersect(p1, p2, p3, p4):
                            intersections_count += 1
                
                if intersections_count == 0:
                    # Perfect! No intersections.
                    path_generated_rungs = candidate_rungs
                    logger.info(f"Found optimal spacing {current_spacing:.1f}px with {len(candidate_rungs)} rungs (0 intersections).")
                    break
                else:
                    # Intersections found, try reducing density
                    logger.info(f"Attempt {attempt+1}: {intersections_count} intersections with spacing {current_spacing:.1f}px. Reducing density...")
                    if intersections_count < best_rejections:
                        best_rejections = intersections_count
                        best_rungs = candidate_rungs
                    
                    current_spacing *= 1.5  # Increase spacing by 50%
            else:
                # If we exhausted attempts, use the best one we found (fewest intersections)
                logger.warning(f"Could not find intersection-free placement. Using best attempt with {best_rejections} intersections.")
                path_generated_rungs = best_rungs

            # Final pass to remove any remaining crossing rungs from the chosen set
            valid_rungs = []
            if path_generated_rungs:
                valid_rungs.append(path_generated_rungs[0])
                for i in range(1, len(path_generated_rungs)):
                    current = path_generated_rungs[i]
                    last = valid_rungs[-1]
                    p1, p2 = last['rung']
                    p3, p4 = current['rung']
                    
                    if segments_intersect(p1, p2, p3, p4):
                        logger.warning(f"Removing crossing rung at index {i} (final cleanup).")
                        rejected_rungs_debug.append(current['rung'])
                    else:
                        valid_rungs.append(current)
            
            path_generated_rungs = valid_rungs
            
            # Add valid rungs to main list
            for item in valid_rungs:
                rungs.append(item['rung'])
                
            path_rungs_map[p_idx] = valid_rungs
                
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
    
    # Debug: Save coverage analysis
    if debug_dir and skeleton_paths:
        save_rung_coverage_debug(debug_dir, binary_img, rungs, skeleton_paths, rejected_rungs=rejected_rungs_debug) 

    # Fill coverage gaps with additional rungs
    # Disabled for InkStitch-like behavior - users create structural rungs manually
    gap_rungs = []  # fill_coverage_gaps(binary_img, rungs, distance_map, spacing_px)
    rungs.extend(gap_rungs)
    
    # Final coverage analysis after gap filling
    if debug_dir and gap_rungs:
        save_rung_coverage_debug(debug_dir, binary_img, rungs, skeleton_paths)
    
    # Ensure rungs at path endpoints for proper satin definition
    if path_endpoints:
        endpoint_rungs = []
        for start_point, end_point in path_endpoints:
            # Transform endpoints to image coordinates
            start_img = start_point * transform
            end_img = end_point * transform
            
            # Check if we already have rungs near these endpoints
            start_has_rung = False
            end_has_rung = False
            
            for rung in rungs:
                (rung_p1x, rung_p1y), (rung_p2x, rung_p2y) = rung
                # Check distance to start point
                dist_start = min(
                    ((rung_p1x - start_img.x)**2 + (rung_p1y - start_img.y)**2)**0.5,
                    ((rung_p2x - start_img.x)**2 + (rung_p2y - start_img.y)**2)**0.5
                )
                if dist_start < spacing_px * 0.5:  # Within half spacing
                    start_has_rung = True
                
                # Check distance to end point
                dist_end = min(
                    ((rung_p1x - end_img.x)**2 + (rung_p1y - end_img.y)**2)**0.5,
                    ((rung_p2x - end_img.x)**2 + (rung_p2y - end_img.y)**2)**0.5
                )
                if dist_end < spacing_px * 0.5:  # Within half spacing
                    end_has_rung = True
            
            # Add rungs at endpoints if missing
            if not start_has_rung:
                # Try to find a rung near the start point and extend it, or create a small rung
                start_rung = find_rung_at_endpoint(start_img.x, start_img.y, binary_img, distance_map, spacing_px)
                if start_rung:
                    endpoint_rungs.append(start_rung)
                    logger.info(f"Added endpoint rung at start: ({start_img.x:.1f}, {start_img.y:.1f})")
            
            if not end_has_rung:
                # Try to find a rung near the end point and extend it, or create a small rung
                end_rung = find_rung_at_endpoint(end_img.x, end_img.y, binary_img, distance_map, spacing_px)
                if end_rung:
                    endpoint_rungs.append(end_rung)
                    logger.info(f"Added endpoint rung at end: ({end_img.x:.1f}, {end_img.y:.1f})")
        
        rungs.extend(endpoint_rungs)
        if endpoint_rungs:
            logger.info(f"Added {len(endpoint_rungs)} endpoint rungs")
            
    return rungs, unique_bridges
