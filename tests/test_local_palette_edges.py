import io

import numpy as np
import pytest
from PIL import Image
from scipy.ndimage import label

from embroidery_rungs.colors import bitmap_colors, separate_colors
from embroidery_rungs.image_processor import rasterize_rgba
from embroidery_rungs.svg_manager import load_svg_paths


def _compressed_flat_artwork():
    rgba = np.full((100, 160, 4), 255, dtype=np.uint8)
    rgba[:50, :, :3] = [14, 15, 149]
    rgba[65:85, 10:35, :3] = 1
    rgba[65:85, 60:85, :3] = [255, 19, 1]
    rgba[20, 120, :3] = 1  # A genuine isolated black pixel remains valid paint.
    rgba[15:25, 140:150, 3] = 0
    # Source colours observed along Pepsi's compressed blue/white transition.
    # Global Lab assignment incorrectly chooses the distant black paint.
    rgba[49, 65, :3] = [97, 94, 150]
    rgba[50, 95, :3] = [115, 114, 164]
    for index in range(10):
        rgba[15, 20 + index, :3] = [14, 15, 140 + index]
    return rgba


def _paint_mask(labels, colors, paint):
    return labels == colors.index(paint) + 1


def test_remote_black_is_not_used_for_compressed_blue_white_edges():
    rgba = _compressed_flat_artwork()
    original = rgba.copy()
    baseline, baseline_colors, _ = separate_colors(rgba, 6)
    assert baseline_colors[baseline[49, 65] - 1] == "#010101"
    assert baseline_colors[baseline[50, 95] - 1] == "#010101"
    diagnostics = {}
    labels, colors, _ = bitmap_colors(rgba, 6, diagnostics=diagnostics)
    assert colors[labels[49, 65] - 1] == "#0e0f95"
    assert colors[labels[50, 95] - 1] == "#ffffff"
    assert diagnostics["palette_edge_pixels"] == 2
    # The large black region and the genuine one-pixel accent both survive.
    expected_black = (rgba[..., :3] == 1).all(axis=2) & (rgba[..., 3] >= 128)
    assert np.array_equal(_paint_mask(labels, colors, "#010101"), expected_black)
    assert label(expected_black)[1] == 2
    assert np.array_equal(labels > 0, rgba[..., 3] >= 128)
    assert np.array_equal(rgba, original)


@pytest.mark.parametrize("orient", [np.rot90, np.flipud, np.fliplr])
def test_local_colour_assignment_respects_rotations_and_reflections(orient):
    source = _compressed_flat_artwork()
    first_info, transformed_info = {}, {}
    first, colors, _ = bitmap_colors(source, 6, diagnostics=first_info)
    transformed, other_colors, _ = bitmap_colors(orient(source), 6, diagnostics=transformed_info)
    assert other_colors == colors
    assert np.array_equal(transformed, orient(first))
    assert transformed_info["palette_edge_pixels"] == first_info["palette_edge_pixels"] == 2


def test_disabled_cleanup_does_not_reinterpret_ambiguous_bitmap_edges():
    source = _compressed_flat_artwork()
    expected, expected_colors, reduced = separate_colors(source, 6)
    diagnostics = {}
    actual, colors, actual_reduced = bitmap_colors(
        source, 6, cleanup=False, diagnostics=diagnostics
    )
    assert np.array_equal(actual, expected)
    assert colors == expected_colors
    assert actual_reduced == reduced
    assert diagnostics["palette_edge_pixels"] == 0


def test_exact_dark_chromatic_paint_at_a_boundary_is_retained():
    source = np.full((80, 120, 4), 255, dtype=np.uint8)
    source[:40, :, :3] = [14, 15, 149]
    source[60:70, 10:30, :3] = 1
    source[39, 60, :3] = [97, 94, 150]
    diagnostics = {}
    labels, colors, _ = bitmap_colors(source, 6, diagnostics=diagnostics)
    assert colors[labels[39, 60] - 1] == "#615e96"
    assert diagnostics["palette_edge_pixels"] == 0


def test_a_weak_colour_with_only_one_supported_local_paint_is_not_reassigned():
    source = _compressed_flat_artwork()
    source[49, 65, :3] = [14, 15, 149]
    source[50, 95, :3] = 255
    source[20, 60, :3] = [97, 94, 150]
    labels, colors, _ = bitmap_colors(source, 6)
    # No observed transition supports changing this ambiguous interior detail.
    assert colors[labels[20, 60] - 1] == "#010101"


@pytest.mark.parametrize("encoding", ["PNG", "JPEG"])
def test_genuine_black_dots_survive_inside_blue_and_on_blue_white_boundary(encoding):
    source = np.full((200, 320, 4), 255, dtype=np.uint8)
    source[:100, :, :3] = [14, 15, 149]
    source[130:170, 20:70, :3] = 1
    source[130:170, 120:170, :3] = [255, 19, 1]
    source[40:47, 240:247, :3] = 1
    source[96:103, 260:267, :3] = 1
    stream = io.BytesIO()
    Image.fromarray(source).convert("RGB").save(stream, format=encoding, quality=90, subsampling=0)
    decoded = np.asarray(Image.open(io.BytesIO(stream.getvalue())).convert("RGBA"))
    diagnostics = {}
    labels, colors, _ = bitmap_colors(decoded, 8, diagnostics=diagnostics)
    for probe in ((43, 243), (99, 263), (140, 40)):
        assert colors[labels[probe] - 1] == "#010101"
    if encoding == "JPEG":
        assert diagnostics["flat_paints_recovered"]


def test_vector_blue_white_curve_does_not_create_remote_black_at_machine_resolution(tmp_path):
    source = tmp_path / "four-paints.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="80mm" viewBox="0 0 80 80">'
        '<rect width="80" height="80" fill="#ffffff"/>'
        '<path d="M0 0 H80 V38 Q40 57 0 38 Z" fill="#0e0f95"/>'
        '<rect x="8" y="62" width="15" height="12" fill="#010101"/>'
        '<rect x="34" y="62" width="15" height="12" fill="#ff1301"/></svg>'
    )
    document, _ = load_svg_paths(source)
    rgba, _ = rasterize_rgba(document, 305)
    labels, colors, _ = separate_colors(rgba, 6)
    assert set(colors) == {"#ffffff", "#0e0f95", "#010101", "#ff1301"}
    source_black = (rgba[..., :3] == 1).all(axis=2) & (rgba[..., 3] >= 128)
    assert np.array_equal(_paint_mask(labels, colors, "#010101"), source_black)
    assert label(source_black)[1] == 1
