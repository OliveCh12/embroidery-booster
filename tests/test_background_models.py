"""Background confidence, nonlinear fields and small paint references."""

import io

import numpy as np
import pytest
from PIL import Image, ImageDraw
from scipy.ndimage import binary_erosion, distance_transform_edt, label

from embroidery_rungs.background import bitmap_foreground


def _composite(field, *, outline=True, encoding="PNG", outline_width=4):
    height, width = field.shape[:2]
    layer = Image.new("RGBA", (width * 4, height * 4))
    draw = ImageDraw.Draw(layer)
    draw.ellipse(
        (width, height, width * 3, height * 3),
        fill="white",
        outline="black" if outline else None,
        width=outline_width * 4,
    )
    layer = layer.resize((width, height), Image.Resampling.LANCZOS)
    reference = np.asarray(layer)[..., 3] >= 128
    background = Image.fromarray(field.astype(np.uint8)).convert("RGBA")
    source = Image.alpha_composite(background, layer).convert("RGB")
    stream = io.BytesIO()
    source.save(stream, format=encoding, quality=90)
    rgba = np.asarray(Image.open(io.BytesIO(stream.getvalue())).convert("RGBA"))
    return rgba, reference


def _check_silhouette(actual, reference):
    assert not np.any(actual & (distance_transform_edt(~reference) > 2))
    assert np.all(actual[binary_erosion(reference, iterations=2)])
    assert np.count_nonzero(actual & reference) / np.count_nonzero(actual | reference) >= 0.97


@pytest.mark.parametrize("encoding", ["PNG", "JPEG", "WEBP"])
@pytest.mark.parametrize("field", ["radial_sqrt", "sinusoidal"])
def test_nonlinear_smooth_background_uses_observed_exterior_not_polynomial_extrapolation(
    field, encoding
):
    y, x = np.mgrid[:192, :240]
    if field == "radial_sqrt":
        shade = 180 + 60 * np.hypot(x / 239 - 0.5, y / 191 - 0.5)
    else:
        shade = 190 + 15 * np.sin(x / 70) + 10 * np.cos(y / 65)
    rgb = np.repeat(shade[..., None], 3, axis=-1)
    rgba, reference = _composite(rgb, encoding=encoding)
    diagnostics = {}
    output = bitmap_foreground(rgba, diagnostics=diagnostics)
    _check_silhouette(output[..., 3] >= 128, reference)
    assert output[96, 120, 3] == 255
    assert diagnostics["model"] == "smooth_gradient"
    if diagnostics["model_fit"] == "smooth":
        assert diagnostics["border_error_rgb"] is None
        assert diagnostics["gradient_step_rgb"] is not None


def test_textured_multicolor_perimeter_is_retained_in_auto():
    rng = np.random.default_rng(31)
    rgba = rng.integers(0, 256, (80, 120, 4), dtype=np.uint8)
    rgba[..., 3] = 255
    diagnostics = {}
    assert np.array_equal(bitmap_foreground(rgba, diagnostics=diagnostics), rgba)
    assert diagnostics["reason"] == "ambiguous_perimeter"
    assert not diagnostics["applied"]


@pytest.mark.parametrize("color", [245, 255])
def test_low_contrast_flat_accent_next_to_black_outline_uses_its_own_reference(color):
    rgba = np.full((100, 130, 4), 255, dtype=np.uint8)
    rgba[..., :3] = 242
    rgba[25:75, 30:80, :3] = 0
    rgba[28:72, 33:77, :3] = 255
    rgba[40:46, 82:88, :3] = color
    output = bitmap_foreground(rgba)
    assert np.all(output[40:46, 82:88, 3] == 255)
    assert np.all(output[25:75, 30:80, 3] == 255)
    assert label(output[..., 3] >= 128)[1] == 2


@pytest.mark.parametrize("size", [1, 2, 3, 4])
@pytest.mark.parametrize("color", [245, 255])
@pytest.mark.parametrize("recover_edge_colors", [False, True])
def test_literal_micro_accent_next_to_black_outline_is_never_matted_away(
    size, color, recover_edge_colors
):
    rgba = np.full((100, 130, 4), 255, dtype=np.uint8)
    rgba[..., :3] = 242
    rgba[25:75, 30:80, :3] = 0
    rgba[28:72, 33:77, :3] = 255
    rgba[40 : 40 + size, 82 : 82 + size, :3] = color
    output = bitmap_foreground(rgba, recover_edge_colors=recover_edge_colors)
    assert np.all(output[40 : 40 + size, 82 : 82 + size, 3] == 255)
    assert np.all(output[25:75, 30:80, 3] == 255)
    assert np.array_equal(output[..., :3], rgba[..., :3])
    assert label(output[..., 3] >= 128)[1] == 2


def test_hidden_transparent_rgb_cannot_change_preservation_of_literal_paints():
    rgba = np.full((100, 130, 4), 255, dtype=np.uint8)
    rgba[..., :3] = 242
    rgba[25:75, 30:80, :3] = 0
    rgba[28:72, 33:77, :3] = 255
    rgba[40:44, 82:86, :3] = 255
    rgba[45:50, 45:50, 3] = 0
    first = bitmap_foreground(rgba)
    rgba[45:50, 45:50, :3] = np.random.default_rng(17).integers(0, 256, (5, 5, 3), dtype=np.uint8)
    second = bitmap_foreground(rgba)
    assert np.array_equal(first[..., 3], second[..., 3])
    assert np.all(second[40:44, 82:86, 3] == 255)
    assert np.array_equal(second[..., :3], rgba[..., :3])


@pytest.mark.parametrize("encoding", ["PNG", "JPEG", "WEBP"])
def test_optional_edge_color_recovery_removes_exterior_blends_without_repainting_badge(encoding):
    from embroidery_rungs.colors import bitmap_colors

    field = np.full((192, 240, 3), 242, dtype=np.uint8)
    rgba, _ = _composite(field, encoding=encoding)
    default = bitmap_foreground(rgba)
    diagnostics = {}
    recovered = bitmap_foreground(rgba, recover_edge_colors=True, diagnostics=diagnostics)
    changed = np.any(recovered[..., :3] != rgba[..., :3], axis=-1)
    assert np.array_equal(default[..., :3], rgba[..., :3])
    assert np.array_equal(default[..., 3], recovered[..., 3])
    assert diagnostics["edge_recovered_pixels"] == np.count_nonzero(changed) > 0
    assert np.all(recovered[changed, 3] >= 128)
    assert np.all(distance_transform_edt(recovered[..., 3] >= 128)[changed] <= 3)
    assert np.array_equal(recovered[96, 120], [255, 255, 255, 255])
    gray_edge = changed & (rgba[..., 0] >= 95) & (rgba[..., 0] <= 165)
    assert gray_edge.any()
    assert np.max(recovered[gray_edge, :3]) < 40
    labels, paints, _ = bitmap_colors(recovered, cleanup=True)
    assert set(paints) == {"#000000", "#ffffff"}
    assert sum(label(labels == index)[1] for index in range(1, 3)) == 2


@pytest.mark.parametrize("mode", ["auto", "keep"])
def test_optional_recovery_preserves_existing_perimeter_transparency(mode):
    field = np.full((192, 240, 3), 242, dtype=np.uint8)
    rgba, _ = _composite(field)
    rgba = rgba.copy()
    rgba[0, 0, 3] = 0
    diagnostics = {}
    recovered = bitmap_foreground(rgba, mode, recover_edge_colors=True, diagnostics=diagnostics)
    assert np.array_equal(recovered, rgba)
    assert diagnostics["edge_recovered_pixels"] == 0


def test_optional_recovery_keeps_hidden_rgb_inside_alpha_openings():
    field = np.full((192, 240, 3), 242, dtype=np.uint8)
    rgba, _ = _composite(field, encoding="JPEG")
    rgba = rgba.copy()
    rgba[90:100, 110:130, :3] = 121
    rgba[90:100, 110:130, 3] = 0
    recovered = bitmap_foreground(rgba, recover_edge_colors=True)
    assert np.array_equal(recovered[90:100, 110:130], rgba[90:100, 110:130])


@pytest.mark.parametrize("encoding", ["PNG", "JPEG", "WEBP"])
def test_white_badge_without_outline_keeps_its_intrinsic_paint(encoding):
    rgb = np.full((192, 240, 3), 180, dtype=np.uint8)
    rgba, reference = _composite(rgb, outline=False, encoding=encoding)
    output = bitmap_foreground(rgba)
    _check_silhouette(output[..., 3] >= 128, reference)
    assert label(output[..., 3] >= 128)[1] == 1


def test_two_rgb_levels_of_explicit_paint_are_preserved():
    rgba = np.full((80, 120, 4), 255, dtype=np.uint8)
    rgba[20:60, 30:90, :3] = 253
    output = bitmap_foreground(rgba)
    assert np.all(output[20:60, 30:90, 3] == 255)
    assert output[0, 0, 3] == 0


def test_partial_transparency_and_keep_are_byte_identical():
    rgba = np.full((80, 120, 4), 255, dtype=np.uint8)
    rgba[25:55, 35:85, :3] = 0
    rgba[0, 0, 3] = 0
    assert np.array_equal(bitmap_foreground(rgba), rgba)
    assert np.array_equal(bitmap_foreground(rgba, "keep"), rgba)


@pytest.mark.parametrize("observed_background", [False, True])
def test_tiled_refinement_matches_complete_frame_across_512px_boundaries(observed_background):
    from scipy.ndimage import binary_propagation

    from embroidery_rungs.background import _edge_tile, _perimeter, _refine_edge

    height, width = 768, 1040
    y, x = np.mgrid[:height, :width]
    shade = np.full((height, width), 210.0)
    if observed_background:
        shade += 25 * x / (width - 1) + 10 * y / (height - 1)
    field = np.repeat(shade[..., None], 3, axis=-1)
    rgba, _ = _composite(field, encoding="JPEG")
    # The ellipse's right edge crosses x=512; its bottom crosses y=512.
    rgb = rgba[..., :3]
    coefficients = None
    if not observed_background:
        coefficients = np.zeros((3, 3))
        coefficients[0] = 210
    residual = np.linalg.norm(rgb.astype(float) - field, axis=-1)
    matching = residual <= 3
    outside = binary_propagation(_perimeter((height, width)) & matching, mask=matching)
    full_weak = _edge_tile(
        rgb,
        outside,
        coefficients,
        3,
        (0, height, 0, width),
        (0, height, 0, width),
    )
    expected = binary_propagation(outside, structure=np.ones((3, 3)), mask=outside | full_weak)
    actual, _ = _refine_edge(rgb, outside, coefficients, 3)
    assert np.array_equal(actual, expected)


@pytest.mark.parametrize("orient", [np.rot90, np.fliplr])
def test_large_gradient_mask_is_covariant_across_refinement_tile_boundaries(orient):
    y, x = np.mgrid[:768, :1040]
    shade = 210 + 25 * x / 1039 + 10 * y / 767
    rgba, _ = _composite(np.repeat(shade[..., None], 3, axis=-1), encoding="JPEG")
    original = bitmap_foreground(rgba)[..., 3] >= 128
    transformed = bitmap_foreground(orient(rgba))[..., 3] >= 128
    expected = orient(original)
    assert np.count_nonzero(transformed ^ expected) <= 0.001 * expected.size
    assert np.all(distance_transform_edt(~expected)[transformed & ~expected] <= 1)
    assert np.all(distance_transform_edt(~transformed)[expected & ~transformed] <= 1)


@pytest.mark.parametrize("encoding", ["PNG", "JPEG", "WEBP"])
def test_thin_antialiased_black_outline_keeps_enclosed_white_paint(encoding):
    field = np.full((192, 240, 3), 242, dtype=np.uint8)
    rgba, reference = _composite(field, encoding=encoding, outline_width=1)
    output = bitmap_foreground(rgba)
    _check_silhouette(output[..., 3] >= 128, reference)
    assert output[96, 120, 3] == 255
    assert label(output[..., 3] >= 128)[1] == 1


@pytest.mark.parametrize("encoding", ["PNG", "JPEG", "WEBP"])
def test_global_outline_protection_keeps_enclosed_core_across_512px_tile_boundaries(encoding):
    field = np.full((768, 1040, 3), 242, dtype=np.uint8)
    rgba, reference = _composite(field, encoding=encoding, outline_width=1)
    mask = bitmap_foreground(rgba)[..., 3] >= 128
    assert np.all(mask[binary_erosion(reference, iterations=2)])
    assert np.count_nonzero(mask & reference) / np.count_nonzero(mask | reference) >= 0.99


def test_full_canvas_gradient_without_a_distinct_subject_is_kept_in_auto():
    y, x = np.mgrid[:80, :120]
    rgb = np.stack([20 + 210 * x / 119, np.full_like(x, 60), 230 - 210 * x / 119], axis=-1)
    rgba = np.dstack((rgb.astype(np.uint8), np.full((80, 120), 255, dtype=np.uint8)))
    diagnostics = {}
    assert np.array_equal(bitmap_foreground(rgba, diagnostics=diagnostics), rgba)
    assert diagnostics["reason"] == "no_distinct_foreground"
    assert diagnostics["model"] == "smooth_gradient"
    assert not diagnostics["applied"]
    assert not np.any(bitmap_foreground(rgba, "remove")[..., 3])
