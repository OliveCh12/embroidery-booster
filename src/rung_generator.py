import logging
import numpy as np
import networkx as nx
from scipy.interpolate import splprep, splev
from geometry_utils import get_skeleton_paths, merge_aligned_paths, find_shape_boundaries, segments_intersect, get_ray_intersection
from debug_utils import save_debug_graph, save_rung_coverage_debug

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
    
    # Calculate dynamic pruning threshold
    # Reduced to avoid removing valid endpoints (e.g. 0.5% or fixed small value)
    # We want to keep endpoints that are part of the shape, even if short.
    # But we want to remove pixel noise.
    prune_threshold = 10 # Fixed small threshold for noise
    logger.info(f"Using skeleton pruning threshold: {prune_threshold}px")
    
    # Get all valid paths from the skeleton
    skeleton_paths, G = get_skeleton_paths(skeleton, binary_img=binary_img, min_len_px=prune_threshold)
    
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
            # Increase smoothing to ensure stable normals and parallelism
            tck, u = splprep([x, y], s=len(x) * 10, k=k) 
            
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
            
            # --- Optimized Rung Generation ---
            # Instead of global retry, we use a local conflict resolution strategy.
            # We walk along the path and place rungs. If a rung intersects the previous one,
            # we advance slightly until it fits.
            
            path_generated_rungs = []
            current_dist = 0.0
            step_size = spacing_px * 0.1  # Small step for finding valid position
            
            # Initial position
            current_dist = 0.0
            
            while current_dist <= total_len:
                # Find u for current distance
                # np.interp requires sorted x, dist_along is sorted
                target_u = np.interp(current_dist, dist_along, u_fine)
                
                # Get position and derivative
                cur_x, cur_y = splev(target_u, tck)
                dx, dy = splev(target_u, tck, der=1)
                
                # Calculate normal
                n_x, n_y = -dy, dx
                norm = np.sqrt(n_x**2 + n_y**2)
                if norm > 0:
                    n_x /= norm
                    n_y /= norm
                else:
                    # Should not happen with spline, but safety check
                    current_dist += step_size
                    continue
                
                # Find boundaries
                est_radius = distance_map[int(np.clip(cur_y, 0, binary_img.shape[0]-1)), 
                                          int(np.clip(cur_x, 0, binary_img.shape[1]-1))]
                max_search = max(est_radius * 4.0, 20.0)
                
                boundaries = find_shape_boundaries(binary_img, cur_x, cur_y, n_x, n_y, max_search)
                
                if boundaries is None:
                    current_dist += step_size
                    continue
                    
                (p1_x, p1_y), (p2_x, p2_y) = boundaries
                rung_length = np.sqrt((p1_x - p2_x)**2 + (p1_y - p2_y)**2)
                
                if rung_length < 2.0:
                    current_dist += step_size
                    continue
                
                # Extension
                extension = max(est_radius * 0.1, 3.0)
                vx = p1_x - p2_x
                vy = p1_y - p2_y
                v_len = np.sqrt(vx**2 + vy**2)
                if v_len > 0:
                    vx /= v_len; vy /= v_len
                    p1_x += vx * extension; p1_y += vy * extension
                    p2_x -= vx * extension; p2_y -= vy * extension
                
                new_rung = ((p1_x, p1_y), (p2_x, p2_y))
                
                # Check intersection with previous valid rungs (check last 5 to be safe in curves)
                intersects = False
                if path_generated_rungs:
                    # Check against last few rungs to prevent crossing in tight curves
                    check_count = min(len(path_generated_rungs), 5)
                    for i in range(1, check_count + 1):
                        last_rung_data = path_generated_rungs[-i]
                        lp1, lp2 = last_rung_data['rung']
                        if segments_intersect(lp1, lp2, (p1_x, p1_y), (p2_x, p2_y)):
                            intersects = True
                            break
                
                if intersects:
                    # If intersects, we are too close or turning too fast.
                    # Try to rotate the rung to "fan out" and avoid intersection.
                    # This is crucial for tight curves where normals cross inside the shape.
                    
                    found_rotated = False
                    best_rotated_rung = None
                    
                    # Try angles: +/- 5, 10, 15, 20, 25, 30 degrees
                    angles = [5, -5, 10, -10, 15, -15, 20, -20, 25, -25, 30, -30]
                    
                    for angle_deg in angles:
                        rad = np.radians(angle_deg)
                        c, s = np.cos(rad), np.sin(rad)
                        
                        # Rotate normal vector
                        rot_nx = n_x * c - n_y * s
                        rot_ny = n_x * s + n_y * c
                        
                        # Ray cast with rotated normal
                        rot_boundaries = find_shape_boundaries(binary_img, cur_x, cur_y, rot_nx, rot_ny, max_search)
                        
                        if rot_boundaries:
                            (rp1_x, rp1_y), (rp2_x, rp2_y) = rot_boundaries
                            
                            # Apply extension
                            rvx = rp1_x - rp2_x
                            rvy = rp1_y - rp2_y
                            rv_len = np.sqrt(rvx**2 + rvy**2)
                            
                            if rv_len > 2.0:
                                rvx /= rv_len; rvy /= rv_len
                                rp1_x += rvx * extension; rp1_y += rvy * extension
                                rp2_x -= rvx * extension; rp2_y -= rvy * extension
                                
                                candidate_rung = ((rp1_x, rp1_y), (rp2_x, rp2_y))
                                
                                # Check intersection again
                                rot_intersects = False
                                for i in range(1, check_count + 1):
                                    last_rung_data = path_generated_rungs[-i]
                                    lp1, lp2 = last_rung_data['rung']
                                    if segments_intersect(lp1, lp2, (rp1_x, rp1_y), (rp2_x, rp2_y)):
                                        rot_intersects = True
                                        break
                                
                                if not rot_intersects:
                                    # Found a valid rotated rung!
                                    new_rung = candidate_rung
                                    rung_length = rv_len # Approximate
                                    found_rotated = True
                                    break
                    
                    if found_rotated:
                        # Use the rotated rung
                        pass
                    else:
                        # Still intersects even after rotation attempts.
                        # Advance a small step and try again.
                        current_dist += step_size
                        continue
                
                # Valid rung (either original or rotated)
                path_generated_rungs.append({
                    'rung': new_rung,
                    'center': (float(cur_x), float(cur_y)),
                    'u': target_u,
                    'length': rung_length,
                    'dist': current_dist
                })
                
                # Determine next spacing based on curvature
                # High curvature -> smaller spacing to guide satin better
                # Low curvature -> larger spacing to reduce density
                # Curvature is roughly 1/radius.
                local_k = np.interp(target_u, u_fine, curvature)
                
                # Base spacing
                next_spacing = spacing_px
                
                if local_k > 0.05:
                    # High curvature: reduce spacing (down to 50%)
                    factor = max(0.5, 1.0 - (local_k * 5.0)) 
                    next_spacing = spacing_px * factor
                    next_spacing = max(next_spacing, spacing_px * 0.5)
                elif local_k < 0.01:
                    # Low curvature (straight lines): increase spacing (up to 200%)
                    # This significantly reduces density in straight sections
                    next_spacing = spacing_px * 2.0
                else:
                    # Moderate curvature: linear interpolation
                    # 0.01 -> 2.0x, 0.05 -> 1.0x
                    t = (local_k - 0.01) / (0.04) # 0 to 1 range
                    factor = 2.0 - t # 2.0 to 1.0
                    next_spacing = spacing_px * factor
                
                current_dist += next_spacing

            # Add valid rungs to main list
            for item in path_generated_rungs:
                rungs.append(item['rung'])
                
            path_rungs_map[p_idx] = path_generated_rungs
            logger.info(f"Generated {len(path_generated_rungs)} rungs for path segment {p_idx}")
                
        except Exception as e:
            logger.error(f"Spline fitting failed for a segment: {e}")
            continue
                
        except Exception as e:
            logger.error(f"Spline fitting failed for a segment: {e}")
            continue

    # --- 2. Generate Bridges (Conditional) ---
    junctions = [n for n, d in G.degree() if d > 2]
    if junctions:
        logger.info("Intersections detected. Generating bridges at junctions...")
        # Graph-guided bridge generation
        
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
            junction_rungs = []
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
                    junction_rungs.append(best_rung)
            
            if len(junction_rungs) < 2:
                continue

            # Create bridges using Minimum Spanning Tree (MST) to avoid crossing bridges
            # and ensure minimal connectivity (N rungs -> N-1 bridges)
            
            # Create a small graph for this junction
            G_bridge = nx.Graph()
            for i in range(len(junction_rungs)):
                G_bridge.add_node(i)
            
            # Add edges between all pairs with weight = distance
            for i in range(len(junction_rungs)):
                for k in range(i+1, len(junction_rungs)):
                    r1 = junction_rungs[i]
                    r2 = junction_rungs[k]
                    
                    # Distance check (sanity)
                    d = np.linalg.norm(np.array(r1['center']) - np.array(r2['center']))
                    
                    # Only consider reasonable connections
                    if d < spacing_px * 10: 
                        G_bridge.add_edge(i, k, weight=d)
            
            # Compute MST
            if G_bridge.number_of_edges() > 0:
                mst = nx.minimum_spanning_tree(G_bridge)
                
                for u, v in mst.edges():
                    r1 = junction_rungs[u]
                    r2 = junction_rungs[v]
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
