import io
from xml.etree import ElementTree as ET

import numpy as np
import pytest
from PIL import Image, ImageDraw
from scipy.ndimage import binary_erosion, label

from embroidery_rungs import GenerationParams, StitchParams
from embroidery_rungs.background import bitmap_foreground
from embroidery_rungs.colors import bitmap_colors, clean_color_regions
from embroidery_rungs.inputs import _remove_alpha_fragments, prepare_artwork, raster_to_svg


def _fills(path):
    return {element.get("fill") for element in ET.parse(path).getroot().findall("{*}path")}


def _monochrome(outline=False):
    image = Image.new("RGB", (180, 140), "white")
    draw = ImageDraw.Draw(image)
    if outline:
        draw.ellipse((20, 15, 160, 125), fill="white", outline="black", width=3)
    else:
        draw.rectangle((20, 20, 160, 120), fill="black")
        draw.polygon(((75, 45), (110, 45), (90, 95)), fill="white")
    return image


@pytest.mark.parametrize("encoding", ["PNG", "JPEG"])
@pytest.mark.parametrize("orient", [np.rot90, np.flipud, np.fliplr])
def test_broad_monochrome_counter_is_transparent_with_colour_cleanup(tmp_path, encoding, orient):
    stream = io.BytesIO()
    _monochrome().save(stream, format=encoding, quality=90)
    rgba = np.asarray(Image.open(io.BytesIO(stream.getvalue())).convert("RGBA"))
    source = tmp_path / "letter.png"
    Image.fromarray(orient(rgba)).save(source)
    diagnostics = {}
    traced = raster_to_svg(
        source, tmp_path / "letter.svg", preserve_colors=True, diagnostics=diagnostics
    )
    assert _fills(traced) == {"#000000"}
    assert diagnostics["background"]["counters_inferred"] == 1
    assert diagnostics["background"]["counter_pixels_removed"] > 500
    assert diagnostics["background"]["counter_inference"] == "monochrome_broad_strokes"
    assert diagnostics["cleanup"]["palette_colors"] == 1
    # The black base silhouette carries a second contour for the transparent counter.
    assert ET.parse(traced).getroot().find("{*}path").get("d").count("M ") == 2


@pytest.mark.parametrize("settings", [{"background_mode": "keep"}, {"cleanup": False}])
def test_explicit_keep_and_disabled_cleanup_preserve_opaque_counter(tmp_path, settings):
    source = tmp_path / "letter.png"
    _monochrome().save(source)
    diagnostics = {}
    traced = raster_to_svg(
        source, tmp_path / "letter.svg", preserve_colors=True, diagnostics=diagnostics, **settings
    )
    assert _fills(traced) == {"#000000", "#ffffff"}
    assert diagnostics["background"]["counters_inferred"] == 0


@pytest.mark.parametrize("encoding", ["PNG", "JPEG"])
def test_monochrome_thin_outline_badge_preserves_its_white_paint(tmp_path, encoding):
    source = tmp_path / "badge.png"
    stream = io.BytesIO()
    _monochrome(outline=True).save(stream, format=encoding, quality=90)
    Image.open(io.BytesIO(stream.getvalue())).save(source)
    diagnostics = {}
    traced = raster_to_svg(
        source, tmp_path / "badge.svg", preserve_colors=True, diagnostics=diagnostics
    )
    assert _fills(traced) == {"#000000", "#ffffff"}
    assert diagnostics["background"]["counters_inferred"] == 0
    assert diagnostics["background"]["counter_inference"] in (
        "thin_outline_preserved",
        "compact_interior_preserved",
    )


def test_compact_white_badge_preserves_opaque_paint_even_with_a_thick_black_frame(tmp_path):
    image = Image.new("RGBA", (160, 160), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((20, 20, 140, 140), fill="black")
    draw.ellipse((65, 65, 95, 95), fill="white")
    source = tmp_path / "badge.png"
    image.save(source)
    diagnostics = {}
    traced = raster_to_svg(
        source, tmp_path / "badge.svg", preserve_colors=True, diagnostics=diagnostics
    )
    assert _fills(traced) == {"#000000", "#ffffff"}
    assert diagnostics["background"]["counters_inferred"] == 0
    assert diagnostics["background"]["counter_inference"] == "compact_interior_preserved"


@pytest.mark.parametrize("detached", [False, True])
def test_rare_low_saturation_accent_survives_a_noisy_flat_palette(detached):
    rgba = np.zeros((120, 160, 4), dtype=np.uint8)
    if detached:
        rgba[20:100, 10:70] = [0, 0, 255, 255]
        rgba[20:100, 90:150] = [0, 255, 0, 255]
        rgba[3:7, 3:7] = [0, 128, 192, 255]
        probe = (4, 4)
    else:
        rgba[..., 3] = 255
        rgba[:, :80, :3] = [0, 0, 255]
        rgba[:, 80:, :3] = [0, 255, 0]
        rgba[20, 20:50, :3] = [0, 128, 192]
        probe = (20, 30)
    for index in range(20):
        rgba[25, 20 + index, :3] = [0, 0, 230 + index]
    labels, colors, _ = bitmap_colors(rgba, 12)
    assert colors[labels[probe] - 1] == "#0080c0"


def test_counter_inference_warns_and_never_reinterprets_explicit_vector_paint(tmp_path):
    bitmap = tmp_path / "letter.png"
    _monochrome().save(bitmap)
    _, warnings, _ = prepare_artwork(
        bitmap, tmp_path, GenerationParams(), StitchParams(), preserve_colors=True
    )
    assert any("geometric" in warning and "counters" in warning for warning in warnings)
    vector = tmp_path / "vector.svg"
    vector.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="50mm" height="40mm" viewBox="0 0 50 40">'
        '<rect width="50" height="40" fill="white"/>'
        '<rect x="5" y="5" width="40" height="30" fill="black"/>'
        '<rect x="20" y="15" width="10" height="10" fill="white"/></svg>'
    )
    directory = tmp_path / "prepared"
    directory.mkdir()
    output, _, diagnostics = prepare_artwork(
        vector,
        directory,
        GenerationParams(background_mode="remove"),
        StitchParams(),
        preserve_colors=True,
    )
    assert _fills(output) == {"#000000", "#ffffff"}
    assert diagnostics["background"]["counters_inferred"] == 0


def test_local_source_blends_merge_without_removing_real_colour_or_alpha():
    labels = np.ones((50, 70), dtype=np.uint8)
    labels[:, 35:] = 2
    labels[15, 34] = labels[25, 34] = labels[35, 34] = 3
    labels[5:10, 5:10] = 0
    colors = ["#000000", "#ffffff", "#98afc1"]
    paints = np.array([[0, 0, 0], [255, 255, 255], [152, 175, 193]])
    rgba = np.zeros((*labels.shape, 4), dtype=np.uint8)
    rgba[..., 3] = np.where(labels > 0, 255, 0)
    rgba[..., :3] = paints[np.maximum(labels.astype(int) - 1, 0)]
    rgba[15, 34, :3] = [127, 127, 127]
    rgba[35, 34, :3] = [0, 255, 0]
    diagnostics = {}
    result = clean_color_regions(labels, colors, 12, diagnostics, rgba=rgba)
    assert result[15, 34] in (1, 2)
    assert result[25, 34] == result[35, 34] == 3
    assert np.array_equal(result > 0, labels > 0)
    assert diagnostics["edge_blend_pixels"] == 1
    assert diagnostics["removed_pixels"] == 0


@pytest.mark.parametrize("second_paint", [False, True])
def test_cleanup_does_not_report_a_change_when_the_selected_paint_is_unchanged(second_paint):
    labels = np.zeros((40, 60), dtype=np.uint8)
    labels[5:35, 5:30] = 1
    labels[5:35, 30:55] = 2 if second_paint else 0
    labels[20, 31] = 1
    colors = ["#000000", "#ffffff"] if second_paint else ["#000000"]
    rgba = np.zeros((*labels.shape, 4), dtype=np.uint8)
    rgba[..., 3] = np.where(labels > 0, 255, 0)
    rgba[labels == 2, :3] = 255
    diagnostics = {}
    result = clean_color_regions(labels, colors, 12, diagnostics, rgba=rgba)
    assert np.array_equal(result, labels)
    assert diagnostics["changed_pixels"] == diagnostics["edge_blend_pixels"] == 0
    assert diagnostics["changed_area_mm2"] == 0
    assert diagnostics["regions_after"] == diagnostics["regions_before"]
    assert diagnostics["reason"] == "no_safe_speckles"


def test_compression_padding_is_background_but_literal_dark_flag_bands_are_kept():
    image = Image.new("RGB", (180, 140), "black")
    draw = ImageDraw.Draw(image)
    draw.ellipse((30, 20, 150, 120), fill="white", outline="#98afc1", width=5)
    stream = io.BytesIO()
    image.save(stream, format="JPEG", quality=80)
    rgba = np.asarray(Image.open(io.BytesIO(stream.getvalue())).convert("RGBA")).copy()
    rgba[:, 0, :3] = 13
    rgba[:, -1, :3] = 7
    diagnostics = {}
    result = bitmap_foreground(rgba, diagnostics=diagnostics)
    assert diagnostics["model_fit"] == "compressed_constant"
    assert np.all(result[:, [0, -1], 3] == 0)
    assert result[70, 90, 3] == 255
    flag = np.full((80, 120, 4), 255, dtype=np.uint8)
    flag[..., :3] = np.repeat([[0, 0, 0], [7, 7, 7], [13, 13, 13]], 40, axis=0)[None]
    assert np.array_equal(bitmap_foreground(flag), flag)


def test_observed_border_shades_do_not_erase_a_distinct_pale_subject():
    rgba = np.full((160, 200, 4), 255, dtype=np.uint8)
    rgba[:30, :, :3] = 245
    rgba[75:135, 80:145, :3] = 240
    rgba[80:130, 145:160, :3] = 0
    for index in range(10):
        rgba[150, 20 + index, :3] = [10 + index, 20 + index, 30 + index]
    result = bitmap_foreground(rgba)
    assert np.all(result[75:135, 80:145, 3] == 255)
    assert np.array_equal(result[75:135, 80:145, :3], rgba[75:135, 80:145, :3])


def test_counter_inference_checks_the_region_budget_before_distance_work(tmp_path, monkeypatch):
    rgba = np.full((220, 220, 4), 255, dtype=np.uint8)
    rgba[10:210, 10:210, :3] = 0
    rgba[20:200:2, 20:200:2, :3] = 255
    source = tmp_path / "dense-counters.png"
    Image.fromarray(rgba).save(source)

    def unexpected_distance(*args, **kwargs):
        raise AssertionError("Counter inference should not start above the region budget")

    monkeypatch.setattr("embroidery_rungs.inputs.distance_transform_edt", unexpected_distance)
    with pytest.raises(ValueError, match="visible regions after interpretation"):
        raster_to_svg(source, tmp_path / "counters.svg", preserve_colors=True)
    assert not (tmp_path / "counters.svg").exists()


@pytest.mark.parametrize("small_flat_paint", [False, True])
def test_dense_compressed_badge_is_cleaned_before_the_trace_budget(tmp_path, small_flat_paint):
    size = 640
    image = Image.new("RGB", (size, size), "black")
    draw = ImageDraw.Draw(image)
    draw.ellipse((15, 15, size - 15, size - 15), fill="white")
    draw.ellipse((23, 23, size - 23, size - 23), fill="black")
    for x in range(60, size - 60, 24):
        for y in range(60, size - 60, 24):
            if (x - size / 2) ** 2 + (y - size / 2) ** 2 < (size * 0.35) ** 2:
                draw.ellipse((x, y, x + 14, y + 14), fill="white")
                draw.line((x, y + 10, x + 12, y + 4), fill="#98afc1", width=3)
    if small_flat_paint:
        draw.rectangle((290, 290, 350, 350), fill="#98afc1")
    stream = io.BytesIO()
    image.save(stream, format="JPEG", quality=80)
    source = tmp_path / "badge.jpg"
    source.write_bytes(stream.getvalue())
    diagnostics = {}
    traced = raster_to_svg(
        source, tmp_path / "badge.svg", preserve_colors=True, diagnostics=diagnostics
    )
    assert diagnostics["cleanup"]["regions_before"] > (1000 if small_flat_paint else 4096)
    assert diagnostics["cleanup"]["regions_after"] < 1000
    assert diagnostics["cleanup"]["flat_paints_recovered"]
    assert len(_fills(traced)) == (3 if small_flat_paint else 2)


def test_photo_like_continuous_colours_keep_the_bounded_palette():
    rgba = np.random.default_rng(42).integers(0, 256, size=(120, 160, 4), dtype=np.uint8)
    rgba[..., 3] = 255
    diagnostics = {}
    labels, colors, reduced = bitmap_colors(rgba, max_colors=6, diagnostics=diagnostics)
    assert reduced
    assert not diagnostics["flat_paints_recovered"]
    assert 1 < len(colors) <= 6
    assert label(labels > 0)[1] == 1


def _matte_black_mark():
    rgba = np.zeros((240, 280, 4), dtype=np.uint8)
    rows, columns = np.indices(rgba.shape[:2])
    rgba[..., 0] = 18 + columns % 3
    rgba[..., 1] = 19 + rows % 3
    rgba[..., 2] = 19 + columns % 3
    rgba[10:-10, 10:-10, 3] = 255
    visible = rgba[..., 3] > 0
    fringe = visible & ~binary_erosion(visible)
    rgba[fringe, :3] = 75
    rgba[fringe, 3] = 220
    return rgba, fringe


@pytest.mark.parametrize("orient", [np.rot90, np.flipud, np.fliplr])
def test_soft_gray_matte_fringe_is_one_black_thread_with_identical_alpha(orient):
    rgba, fringe = _matte_black_mark()
    rgba = orient(rgba)
    diagnostics = {}
    labels, colors, _ = bitmap_colors(rgba, 6, diagnostics=diagnostics)
    assert len(colors) == 1
    assert max(int(colors[0][i : i + 2], 16) for i in (1, 3, 5)) <= 22
    assert np.array_equal(labels > 0, rgba[..., 3] >= 128)
    assert diagnostics["dark_ink_edge_pixels"] == fringe.sum()
    # Palette assignment must not mutate the uploaded source.
    assert np.all(rgba[orient(fringe), :3] == 75)


@pytest.mark.parametrize(
    "counterevidence", ["opaque_outline", "interior_gray", "accent", "shading"]
)
def test_black_ink_normalization_preserves_evidence_of_deliberate_paints(counterevidence):
    rgba, fringe = _matte_black_mark()
    if counterevidence == "opaque_outline":
        rgba[fringe, 3] = 255
    elif counterevidence == "interior_gray":
        rgba[110:120, 130:140] = [80, 80, 80, 220]
    elif counterevidence == "accent":
        rgba[110:120, 130:140] = [0, 128, 192, 255]
    else:
        rows = np.indices(rgba.shape[:2])[0]
        shade = (5 + rows % 31).astype(np.uint8)
        rgba[~fringe, :3] = np.repeat(shade[..., None], 3, axis=2)[~fringe]
    diagnostics = {}
    labels, colors, _ = bitmap_colors(rgba, 6, diagnostics=diagnostics)
    assert len(colors) > 1
    assert diagnostics["dark_ink_edge_pixels"] == 0
    assert np.array_equal(labels > 0, rgba[..., 3] >= 128)
    if counterevidence == "accent":
        assert colors[labels[115, 135] - 1] == "#0080c0"


@pytest.mark.parametrize("cleanup", [False, True])
def test_literal_gray_outline_is_not_reinterpreted_as_a_compression_fringe(cleanup):
    rgba, fringe = _matte_black_mark()
    rgba[~fringe, :3] = 20
    diagnostics = {}
    _, colors, _ = bitmap_colors(rgba, 6, cleanup=cleanup, diagnostics=diagnostics)
    assert len(colors) == 2
    assert diagnostics["dark_ink_edge_pixels"] == 0


@pytest.mark.parametrize("kind", ["soft_fringe", "opaque_detail", "different_paint", "isolated"])
def test_only_soft_alpha_dust_at_the_same_mark_is_discarded(kind):
    labels = np.zeros((100, 120), dtype=np.uint8)
    labels[20:80, 20:100] = 1
    row, column = (19, 100) if kind != "isolated" else (15, 104)
    labels[row, column] = 2 if kind == "different_paint" else 1
    rgba = np.zeros((*labels.shape, 4), dtype=np.uint8)
    rgba[labels > 0, 3] = 255
    rgba[row, column, 3] = 255 if kind == "opaque_detail" else 177
    diagnostics = {"removed_pixels": 0, "reason": "no_safe_speckles"}
    result = _remove_alpha_fragments(labels, rgba, 12, diagnostics)
    expected = 0 if kind == "soft_fringe" else labels[row, column]
    assert result[row, column] == expected
    assert np.array_equal(result[20:80, 20:100], labels[20:80, 20:100])
    assert diagnostics["alpha_fragments_removed"] == int(kind == "soft_fringe")
    assert diagnostics["alpha_fragment_pixels"] == int(kind == "soft_fringe")


def test_alpha_edge_fragment_cleanup_is_reported_in_bitmap_preparation(tmp_path):
    rgba = np.zeros((320, 320, 4), dtype=np.uint8)
    rgba[40:280, 40:280, 3] = 255
    rgba[39, 280, 3] = 177
    source = tmp_path / "soft-tip.png"
    Image.fromarray(rgba).save(source)
    prepared, warnings, diagnostics = prepare_artwork(
        source,
        tmp_path,
        GenerationParams(design_width_mm=20),
        StitchParams(),
        preserve_colors=True,
    )
    assert diagnostics["cleanup"]["alpha_fragments_removed"] == 1
    assert diagnostics["cleanup"]["regions_after"] == 1
    assert any("partially transparent fragments" in warning for warning in warnings)
    assert ET.parse(prepared).getroot().find("{*}path").get("d").count("M ") == 1
