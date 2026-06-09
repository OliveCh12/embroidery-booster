import logging
import numpy as np
import networkx as nx

logger = logging.getLogger(__name__)

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

def connect_close_endpoints(G, max_connect_dist_px):
    """Connect endpoints that are close to each other to close open loops."""
    logger.info(f"Connecting close endpoints within {max_connect_dist_px}px...")
    endpoints = [n for n, d in G.degree() if d == 1]
    
    connected = 0
    for i in range(len(endpoints)):
        for j in range(i+1, len(endpoints)):
            n1 = endpoints[i]
            n2 = endpoints[j]
            if n1 not in G or n2 not in G: continue
            
            p1 = np.array(G.nodes[n1]['pos'])
            p2 = np.array(G.nodes[n2]['pos'])
            dist = np.linalg.norm(p1 - p2)
            
            if dist <= max_connect_dist_px:
                # Check if connecting them would create a cycle or something bad
                # For now, just connect if not already connected
                if not G.has_edge(n1, n2):
                    G.add_edge(n1, n2, weight=dist)
                    connected += 1
                    logger.debug(f"Connected endpoints {n1} and {n2} at distance {dist:.1f}px")
    
    logger.info(f"Connected {connected} close endpoints.")
    return G

def get_skeleton_paths_from_graph(G):
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

def extend_skeleton_endpoints(G, binary_img, max_dist_px=50):
    """Extend skeleton endpoints to the shape boundary."""
    logger.info(f"Extending skeleton endpoints to boundary (max {max_dist_px}px)...")
    endpoints = [n for n, d in G.degree() if d == 1]
    extended_count = 0
    
    # Get next available node ID
    next_id = max(G.nodes()) + 1 if G.number_of_nodes() > 0 else 0
    
    for n in endpoints:
        if n not in G: continue
        
        neighbors = list(G.neighbors(n))
        if not neighbors: continue
        nbr = neighbors[0]
        
        p_end = np.array(G.nodes[n]['pos'])
        p_nbr = np.array(G.nodes[nbr]['pos'])
        
        # Vector from neighbor to endpoint
        v = p_end - p_nbr
        norm = np.linalg.norm(v)
        if norm == 0: continue
        v = v / norm
        
        # Cast ray
        # Use get_ray_intersection logic inline or call it if available
        # We need integer coordinates for image check
        start_x, start_y = p_end[1], p_end[0] # pos is (row, col) -> (y, x)
        dx, dy = v[1], v[0]
        
        # Find boundary
        end_x, end_y = get_ray_intersection(binary_img, start_x, start_y, dx, dy, max_dist_px)
        
        # Distance to boundary
        dist = np.sqrt((end_x - start_x)**2 + (end_y - start_y)**2)
        
        if dist > 0.5 and dist <= max_dist_px:
            # Add new node at boundary
            # We might want to add intermediate nodes if dist is large, but for straight line one is enough
            # However, to keep graph density consistent, maybe add nodes every few pixels?
            # For now, just add the endpoint.
            
            new_node_pos = (end_y, end_x)
            G.add_node(next_id, pos=new_node_pos)
            G.add_edge(n, next_id, weight=dist)
            next_id += 1
            extended_count += 1
            
    logger.info(f"Extended {extended_count} endpoints.")
    return G

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

def get_skeleton_paths(skeleton, binary_img=None, min_len_px=15):
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
    
    # Extend endpoints if binary image is provided
    if binary_img is not None:
        G = extend_skeleton_endpoints(G, binary_img, max_dist_px=50)
    
    # Connect close endpoints to close open loops
    G = connect_close_endpoints(G, max_connect_dist_px=100)
    
    paths, G = get_skeleton_paths_from_graph(G)

    return paths, G

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

def segments_intersect(p1, p2, p3, p4):
    """
    Check if line segment (p1, p2) intersects with line segment (p3, p4).
    p1, p2, p3, p4 are (x, y) tuples or arrays.
    Returns True if they intersect strictly (not just touching at endpoints).
    """
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    
    # Denominator
    denom = (y4 - y3) * (x2 - x1) - (x4 - x3) * (y2 - y1)
    
    if denom == 0:
        return False  # Parallel lines
        
    ua = ((x4 - x3) * (y1 - y3) - (y4 - y3) * (x1 - x3)) / denom
    ub = ((x2 - x1) * (y1 - y3) - (y2 - y1) * (x1 - x3)) / denom
    
    # Check if intersection is strictly within the segments
    if 0.001 < ua < 0.999 and 0.001 < ub < 0.999:
        return True
        
    return False
