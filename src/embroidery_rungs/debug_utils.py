"""Optional debug artifacts; no work or imports on the normal execution path."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation


def save_debug_images(debug_dir, binary_img, distance, skeleton):
    directory = Path(debug_dir)
    directory.mkdir(parents=True, exist_ok=True)
    for name, data in (
        ("01_original", binary_img),
        ("03_distance", distance / max(float(distance.max()), 1.0)),
        ("04_skeleton", binary_dilation(skeleton)),
    ):
        Image.fromarray((data * 255).astype(np.uint8)).save(directory / f"debug_{name}.png")
    overlay = np.repeat((binary_img.astype(np.uint8) * 100)[..., None], 3, axis=2)
    overlay[binary_dilation(skeleton)] = (255, 0, 0)
    Image.fromarray(overlay).save(directory / "debug_05_overlay.png")


def save_rung_coverage_debug(
    debug_dir,
    binary_img,
    rungs,
    *,
    elements,
    pixels_per_mm,
):
    from .pipeline import coverage_mask

    coverage = coverage_mask(binary_img, elements, pixels_per_mm)
    overlay = np.zeros((*binary_img.shape, 3), dtype=np.uint8)
    overlay[binary_img] = (90, 25, 25)
    overlay[coverage & binary_img] = (45, 100, 65)
    image = Image.fromarray(overlay)
    draw = ImageDraw.Draw(image)
    for a, b in rungs:
        draw.line([tuple(a), tuple(b)], fill=(120, 255, 140))
    image.save(Path(debug_dir) / "debug_07_coverage.png")
