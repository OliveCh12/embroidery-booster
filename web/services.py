"""External-tool services for the web app: input conversion + Ink/Stitch.

Everything that shells out to Inkscape / Ink/Stitch lives here so the Flask app
stays thin. All functions degrade gracefully: if a tool is missing they raise a
clear error the caller can turn into a friendly message.
"""

import os
import re
import subprocess

import numpy as np
from PIL import Image
from skimage import measure
from skimage.filters import threshold_otsu

# Tool locations (override via env vars for other machines).
INKSCAPE = os.environ.get(
    "INKSCAPE_BIN", "/Applications/Inkscape.app/Contents/MacOS/inkscape")
INKSTITCH = os.environ.get(
    "INKSTITCH_BIN",
    os.path.expanduser("~/Library/Application Support/org.inkscape.Inkscape/"
                       "config/inkscape/extensions/inkstitch/inkstitch.app/"
                       "Contents/MacOS/inkstitch"))

RASTER_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
VECTOR_EXT = {".pdf", ".eps", ".ps", ".ai"}


def has_inkscape():
    return os.path.isfile(INKSCAPE)


def has_inkstitch():
    return os.path.isfile(INKSTITCH)


def _run(cmd, timeout=120):
    return subprocess.run(cmd, check=True, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


# --------------------------------------------------------------------------- #
# Input conversion: anything -> SVG
# --------------------------------------------------------------------------- #

def raster_to_svg(input_path, svg_path):
    """Vectorize a bitmap into a filled SVG silhouette (skimage, no potrace).

    Good enough for embroidery: the medial axis is recomputed from a fresh
    rasterization downstream, so we only need a faithful filled outline.
    """
    src = Image.open(input_path)
    if src.mode in ("RGBA", "LA"):
        mask = np.asarray(src.split()[-1]) > 128          # use alpha as mask
    else:
        gray = np.asarray(src.convert("L"))
        thresh = threshold_otsu(gray)
        mask = gray < thresh                               # dark = foreground
        if mask.mean() > 0.5:                              # mostly dark image
            mask = ~mask

    h, w = mask.shape
    contours = measure.find_contours(mask.astype(float), 0.5)
    subpaths = []
    for contour in contours:
        if len(contour) < 8:                               # drop pixel noise
            continue
        pts = " L ".join(f"{x:.1f},{y:.1f}" for y, x in contour)
        subpaths.append(f"M {pts} Z")

    if not subpaths:
        raise ValueError("No shapes found in the image (is it blank?).")

    with open(svg_path, "w") as f:
        f.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" '
                f'height="{h}" viewBox="0 0 {w} {h}">'
                f'<path fill="black" fill-rule="evenodd" d="{" ".join(subpaths)}"/>'
                f'</svg>')
    return svg_path


def vector_to_svg(input_path, svg_path):
    """Convert PDF/EPS/PS/AI to plain SVG via Inkscape."""
    if not has_inkscape():
        raise RuntimeError("Inkscape is required to convert this format.")
    _run([INKSCAPE, input_path, "--export-type=svg", "--export-plain-svg",
          f"--export-filename={svg_path}"])
    if not os.path.isfile(svg_path):
        raise RuntimeError("Conversion to SVG failed.")
    return svg_path


def convert_to_svg(input_path, work_dir):
    """Return a path to an SVG for ``input_path`` (converting if needed)."""
    ext = os.path.splitext(input_path)[1].lower()
    base = os.path.splitext(os.path.basename(input_path))[0]
    if ext == ".svg":
        return input_path
    svg_path = os.path.join(work_dir, base + ".svg")
    if ext in RASTER_EXT:
        return raster_to_svg(input_path, svg_path)
    if ext in VECTOR_EXT:
        return vector_to_svg(input_path, svg_path)
    raise ValueError(f"Unsupported file type: {ext or 'unknown'}")


# --------------------------------------------------------------------------- #
# Ink/Stitch: embroidery export + realistic stitch preview
# --------------------------------------------------------------------------- #

def export_embroidery(satin_svg, zip_path):
    """Export .dst/.pes/threadlist as a zip from a satin-column SVG."""
    if not has_inkstitch():
        raise RuntimeError("Ink/Stitch is not installed.")
    with open(zip_path, "wb") as out:
        proc = subprocess.run(
            [INKSTITCH, "--extension=zip", "--format-dst=True",
             "--format-pes=True", "--format-threadlist=True", satin_svg],
            check=True, timeout=180, stdout=out, stderr=subprocess.PIPE)
    if proc.returncode != 0 or os.path.getsize(zip_path) == 0:
        raise RuntimeError("Ink/Stitch export failed.")
    return zip_path


def render_stitch_preview(satin_svg, png_path):
    """Render a realistic preview of the stitched satin.

    Runs Ink/Stitch's stitch-plan preview, removes our guide rails so only the
    rendered stitches remain, and rasterizes the result.
    """
    if not has_inkstitch() or not has_inkscape():
        raise RuntimeError("Inkscape and Ink/Stitch are required for the preview.")

    plan_svg = os.path.splitext(png_path)[0] + "_plan.svg"
    with open(plan_svg, "w") as out:
        subprocess.run([INKSTITCH, "--extension=stitch_plan_preview", satin_svg],
                       check=True, timeout=180, stdout=out, stderr=subprocess.PIPE)

    # Strip our input design group so only the rendered stitch plan is shown.
    with open(plan_svg) as f:
        content = f.read()
    content = re.sub(r'<g id="embroidery">.*?</g>', "", content, flags=re.DOTALL)
    # Drop Ink/Stitch command symbols (e.g. the "ignore layer" badge) so only the
    # rendered stitches remain.
    content = re.sub(r'<use\b[^>]*inkstitch[^>]*?>', "", content)
    with open(plan_svg, "w") as f:
        f.write(content)

    _run([INKSCAPE, "--export-type=png", "--export-area-drawing",
          "--export-width=1400", "--export-background=white",
          f"--export-filename={png_path}", plan_svg])
    if not os.path.isfile(png_path):
        raise RuntimeError("Preview rendering failed.")
    return png_path
