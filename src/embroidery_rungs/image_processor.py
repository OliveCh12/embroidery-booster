import os
import logging
import subprocess
import numpy as np
from PIL import Image, ImageDraw
from skimage.morphology import skeletonize, remove_small_holes, closing, disk
from skimage.draw import line
from scipy.ndimage import distance_transform_edt, convolve
from svgelements import Matrix, Move, Line, Close

logger = logging.getLogger(__name__)

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
        raise ValueError("No content found in SVG")

    # Add some padding
    padding = 20
    width = int(bbox[2] - bbox[0] + 2 * padding)
    height = int(bbox[3] - bbox[1] + 2 * padding)
    
    # Resolution: enough detail for a clean skeleton, but capped so wide/long
    # shapes don't blow up to tens of megapixels (skeletonization is the
    # bottleneck). Rung spacing is derived from the transform, so lowering this
    # does NOT change the millimetre spacing of the rungs.
    min_dim_px = 1500   # minimum across the short side
    max_dim_px = 4000   # hard cap on the long side
    current_min_dim = max(1, min(width, height))
    current_max_dim = max(1, max(width, height))

    scale = max(min_dim_px / current_min_dim, dpi / 96.0)
    scale = min(scale, max_dim_px / current_max_dim)

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
                img_rgba = Image.open(temp_png).convert('RGBA')
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
                if isinstance(seg, Move):
                    if len(pts) > 2:
                        draw.polygon(pts, fill=255, outline=255)
                    pts = []
                    # Move destination is the start of new subpath
                    p = seg.end * t_path.transform
                    pts.append((p.x, p.y))
                    continue
                    
                # Sample points from the segment
                # Segments are in local coordinates, need to apply path transform
                if isinstance(seg, (Line, Close)):
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

def extend_skeleton(skeleton, binary_mask):
    """
    Extend the skeleton endpoints to the boundary of the binary_mask.
    """
    # Find endpoints
    # An endpoint in a 1-pixel wide skeleton has 1 neighbor.
    # We use convolution to count neighbors.
    # Kernel:
    # 1 1 1
    # 1 10 1
    # 1 1 1
    # Center pixel value is 10. Neighbors are 1.
    # Sum = 11 means center is set (10) and exactly one neighbor is set (1).
    
    skel_int = skeleton.astype(int)
    kernel = np.array([[1, 1, 1],
                       [1, 10, 1],
                       [1, 1, 1]])
    
    # Use scipy.ndimage.convolve
    neighbors = convolve(skel_int, kernel, mode='constant', cval=0)
    
    endpoints = np.argwhere(neighbors == 11)
    
    if len(endpoints) == 0:
        return skeleton

    extended_skeleton = skeleton.copy()
    h, w = skeleton.shape
    
    for r, c in endpoints:
        # Walk back to find direction
        # We want to find the connected neighbor, then its neighbor, etc.
        # to get a stable direction vector.
        
        path = [(r, c)]
        curr_r, curr_c = r, c
        visited = set([(r, c)])
        
        # Walk back up to 10 pixels for better direction estimation
        for _ in range(10):
            found = False
            # Check 8 neighbors
            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    if dr == 0 and dc == 0: continue
                    nr, nc = curr_r + dr, curr_c + dc
                    
                    if 0 <= nr < h and 0 <= nc < w:
                        if skeleton[nr, nc] and (nr, nc) not in visited:
                            path.append((nr, nc))
                            visited.add((nr, nc))
                            curr_r, curr_c = nr, nc
                            found = True
                            break
                if found: break
            if not found: break
            
        if len(path) < 2:
            continue
            
        # Calculate direction vector from the inner part towards the endpoint
        # Use the last point in path (furthest from endpoint) and the endpoint
        start_node = path[-1]
        end_node = path[0]
        
        vr = end_node[0] - start_node[0]
        vc = end_node[1] - start_node[1]
        
        norm = np.sqrt(vr*vr + vc*vc)
        if norm == 0: continue
        
        vr /= norm
        vc /= norm
        
        # Ray cast
        cur_r, cur_c = float(end_node[0]), float(end_node[1])
        
        # Step size
        step = 0.5
        
        # Max distance to prevent infinite loop (e.g. diagonal of image)
        max_dist = np.sqrt(h*h + w*w)
        dist = 0
        
        hit_boundary = False
        target_r, target_c = cur_r, cur_c
        
        while dist < max_dist:
            cur_r += vr * step
            cur_c += vc * step
            dist += step
            
            ir = int(round(cur_r))
            ic = int(round(cur_c))
            
            if not (0 <= ir < h and 0 <= ic < w):
                # Out of bounds
                break
                
            if not binary_mask[ir, ic]:
                # Hit background
                hit_boundary = True
                target_r, target_c = ir, ic
                break
        
        if hit_boundary:
            # Draw line
            rr, cc = line(end_node[0], end_node[1], target_r, target_c)
            # Clip
            valid = (rr >= 0) & (rr < h) & (cc >= 0) & (cc < w)
            extended_skeleton[rr[valid], cc[valid]] = True
            
    return extended_skeleton

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
    
    # Extend skeleton to boundaries
    skeleton = extend_skeleton(skeleton, cleaned_image)
    
    return skeleton, distance, cleaned_image
