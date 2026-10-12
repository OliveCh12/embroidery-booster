"""Background masks are evaluated against the silhouette before compositing."""

import io
import json
from pathlib import Path

import numpy as np
import pyembroidery as pe
import pytest
from PIL import Image, ImageDraw
from scipy.ndimage import binary_erosion, distance_transform_edt, label

from embroidery_rungs import GenerationParams, generate
from embroidery_rungs.colors import bitmap_foreground
from embroidery_rungs.image_processor import rasterize_rgba
from embroidery_rungs.inputs import raster_to_svg
from embroidery_rungs.svg_manager import load_svg_paths


def _badge(background="uniform", encoding="PNG", accent=False):
    height, width, zoom = 176, 224, 4
    y, x = np.mgrid[:height, :width]
    if background == "uniform":
        rgb = np.full((height, width, 3), 242.0)
    elif background == "linear":
        shade = 208 + 40 * x / (width - 1) - 12 * y / (height - 1)
        rgb = np.repeat(shade[..., None], 3, axis=2)
    elif background == "radial":
        radius = ((x - 110) / width) ** 2 + ((y - 85) / height) ** 2
        shade = 212 + 65 * radius
        rgb = np.repeat(shade[..., None], 3, axis=2)
    elif background == "colored":
        rgb = np.stack([130 + 40 * x / width, 165 + 25 * y / height, 220 - 20 * x / width], axis=2)
    else:
        raise ValueError(background)
    layer = Image.new("RGBA", (width * zoom, height * zoom))
    draw = ImageDraw.Draw(layer)
    bounds = tuple(value * zoom for value in (49, 27, 165, 143))
    draw.ellipse(bounds, fill="white", outline="black", width=5 * zoom)
    draw.rectangle(tuple(value * zoom for value in (77, 52, 137, 66)), fill="#df1837")
    draw.rectangle(tuple(value * zoom for value in (77, 103, 137, 117)), fill="#184bbd")
    if accent:
        draw.rectangle(tuple(value * zoom for value in (184, 34, 189, 39)), fill="#00b94a")
    layer = layer.resize((width, height), Image.Resampling.LANCZOS)
    alpha = np.asarray(layer)[..., 3] >= 128
    canvas = Image.fromarray(np.clip(np.rint(rgb), 0, 255).astype(np.uint8)).convert("RGBA")
    canvas = Image.alpha_composite(canvas, layer).convert("RGB")
    stream = io.BytesIO()
    canvas.save(stream, format=encoding, quality=90)
    rgba = np.asarray(Image.open(io.BytesIO(stream.getvalue())).convert("RGBA"))
    return rgba, alpha


def _assert_outline(actual, reference):
    # A compression codec can shift one boundary pixel. Fringes several pixels
    # outside the source silhouette are never acceptable embroidery regions.
    distance = distance_transform_edt(~reference)
    assert not np.any(actual & (distance > 2))
    assert np.all(actual[binary_erosion(reference, iterations=2)])
    intersection = np.count_nonzero(actual & reference)
    union = np.count_nonzero(actual | reference)
    assert intersection / union >= 0.97


@pytest.mark.parametrize("encoding", ["JPEG", "WEBP"])
def test_compressed_badge_stops_at_outer_black_outline(encoding):
    rgba, reference = _badge(encoding=encoding)
    result = bitmap_foreground(rgba)
    mask = result[..., 3] >= 128
    _assert_outline(mask, reference)
    assert label(mask)[1] == 1
    assert result[85, 107, 3] == 255
    assert np.array_equal(result[85, 107, :3], rgba[85, 107, :3])


@pytest.mark.parametrize("background", ["linear", "radial", "colored"])
@pytest.mark.parametrize("encoding", ["PNG", "JPEG"])
def test_smooth_gradient_background_is_removed_without_erasing_white_badge(background, encoding):
    rgba, reference = _badge(background, encoding)
    result = bitmap_foreground(rgba)
    _assert_outline(result[..., 3] >= 128, reference)
    assert result[85, 107, 3] == 255
    assert result[0, 0, 3] == 0


def test_detached_contrasting_accent_survives_background_cleanup():
    rgba, reference = _badge("linear", "JPEG", accent=True)
    result = bitmap_foreground(rgba)
    _assert_outline(result[..., 3] >= 128, reference)
    assert np.all(result[35:39, 185:189, 3] == 255)
    assert label(result[..., 3] >= 128)[1] == 2


def test_open_outline_does_not_invent_an_enclosed_background_badge():
    rgba = np.full((120, 144, 4), 255, dtype=np.uint8)
    y, x = np.mgrid[:120, :144]
    radius = np.hypot(x - 72, y - 60)
    outline = (radius >= 34) & (radius <= 40) & ~((x >= 72) & (np.abs(y - 60) <= 4))
    rgba[outline, :3] = 0
    result = bitmap_foreground(rgba)
    assert np.all(result[outline, 3] == 255)
    assert result[60, 72, 3] == 0
    assert not np.any(result[radius < 30, 3])


@pytest.mark.parametrize("orient", [np.rot90, np.flipud, np.fliplr])
def test_gradient_background_mask_respects_rotation_and_reflection(orient):
    rgba, _ = _badge("colored", "JPEG")
    original = bitmap_foreground(rgba)[..., 3] >= 128
    changed = bitmap_foreground(orient(rgba))[..., 3] >= 128
    # A fitted field may differ at a rounding boundary, but the sewing contour
    # must have the same geometry rather than changing by image enumeration.
    expected = orient(original)
    assert np.count_nonzero(changed ^ expected) <= 0.001 * expected.size
    assert np.all(distance_transform_edt(~expected)[changed & ~expected] <= 1)
    assert np.all(distance_transform_edt(~changed)[expected & ~changed] <= 1)


def test_low_contrast_explicit_paint_is_not_removed_by_a_wide_global_threshold():
    rgba = np.full((80, 120, 4), 255, dtype=np.uint8)
    rgba[20:60, 30:90, :3] = 245
    result = bitmap_foreground(rgba)
    assert np.all(result[20:60, 30:90, 3] == 255)
    assert result[0, 0, 3] == 0


@pytest.mark.parametrize("background", ["uniform", "colored", "radial"])
def test_refined_contour_survives_resampling_palette_and_svg_trace(background, tmp_path):
    rgba, _ = _badge(background, "JPEG")
    source = tmp_path / "badge.png"
    Image.fromarray(rgba).save(source)
    diagnostics = {}
    traced = raster_to_svg(
        source,
        tmp_path / "badge.svg",
        preserve_colors=True,
        width_mm=35,
        diagnostics=diagnostics,
    )
    document, _ = load_svg_paths(traced)
    rendered, _ = rasterize_rgba(document)
    visible = rendered[..., 3] >= 128
    assert label(visible)[1] == 1
    assert rendered[rendered.shape[0] // 2, rendered.shape[1] // 2, 3] == 255
    assert diagnostics["background"]["applied"]
    assert diagnostics["background"]["edge_refined_pixels"] > 0
    paints = {
        tuple(int(path.get("fill")[i : i + 2], 16) for i in (1, 3, 5))
        for path in document.root.findall("{*}path")
    }
    # Re-rasterization must not invent intermediate thread colours at shared
    # edges after the bitmap's palette has already been resolved.
    assert set(map(tuple, np.unique(rendered[visible, :3], axis=0))) <= paints


def test_shared_colour_silhouette_preserves_alpha_counter_and_detached_paint(tmp_path):
    image = Image.new("RGBA", (120, 100))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 10, 90, 90), fill="red")
    draw.rectangle((55, 10, 90, 90), fill="blue")
    draw.rectangle((45, 35, 70, 65), fill=(0, 0, 0, 0))
    draw.rectangle((100, 40, 115, 60), fill="green")
    source = tmp_path / "counter.png"
    image.save(source)
    traced = raster_to_svg(source, tmp_path / "counter.svg", preserve_colors=True, width_mm=35)
    document, _ = load_svg_paths(traced)
    rendered, _ = rasterize_rgba(document)
    assert rendered[rendered.shape[0] // 2, rendered.shape[1] // 2, 3] == 0
    assert label(rendered[..., 3] >= 128)[1] == 2
    assert {path.get("fill") for path in document.root.findall("{*}path")} == {
        "#ff0000",
        "#0000ff",
        "#008000",
    }


@pytest.mark.parametrize("encoding", ["PNG", "JPEG", "WEBP"])
def test_gradient_badge_remains_covered_and_satin_ready_in_exported_pes(encoding, tmp_path):
    source = tmp_path / "badge.png"
    Image.fromarray(_badge("linear", encoding)[0]).save(source)
    result = generate(source, tmp_path / "out", GenerationParams(design_width_mm=35))
    stats = result.direct.stats
    assert stats["satin_regions"] >= 1
    assert stats["structural_coverage"] >= 0.999
    assert stats["largest_gap_mm2"] <= 0.04
    assert stats["short_stitches"] == stats["unsafe_connections"] == 0
    data = json.loads(Path(result.direct.plan_path).read_text())
    planned = np.asarray(data["commands"])
    planned = planned[planned[:, 2] == pe.STITCH, :2]
    actual = np.asarray(pe.read(result.direct.pes_path).stitches)
    actual = actual[(actual[:, 2].astype(int) & pe.COMMAND_MASK) == pe.STITCH, :2]
    assert np.array_equal(actual, planned)
