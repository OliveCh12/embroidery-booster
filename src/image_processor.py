import os
import sys
import logging
import subprocess
import numpy as np
from PIL import Image, ImageDraw
from skimage.morphology import skeletonize, remove_small_holes, closing, disk
from skimage.transform import hough_line, hough_line_peaks, hough_circle, hough_circle_peaks
from skimage.feature import canny
from scipy.ndimage import distance_transform_edt
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
