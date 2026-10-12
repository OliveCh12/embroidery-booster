import io
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pytest
from PIL import Image, ImageDraw

from embroidery_rungs import GenerationParams, StitchParams
from embroidery_rungs.colors import bitmap_colors, bitmap_foreground, clean_color_regions
from embroidery_rungs.image_processor import rasterize_rgba
from embroidery_rungs.inputs import prepare_artwork, raster_to_svg
from embroidery_rungs.svg_manager import UNITS_PER_MM, load_svg_paths


def badge():
    image = Image.new("RGBA", (80, 60), "#eeeeee")
    drawing = ImageDraw.Draw(image)
    drawing.rectangle((20, 10, 60, 50), fill="black")
    drawing.rectangle((24, 14, 56, 46), fill="white")
    drawing.rectangle((30, 20, 50, 26), fill="red")
    return np.asarray(image)


@pytest.mark.parametrize("mode", ["auto", "remove"])
def test_border_background_does_not_erase_enclosed_white(mode):
    original = badge()
    diagnostics = {}
    result = bitmap_foreground(original, mode, diagnostics)
    assert result[0, 0, 3] == 0
    assert result[30, 30, 3] == 255
    assert np.array_equal(result[..., :3], original[..., :3])
    assert original[0, 0, 3] == 255
    assert diagnostics["applied"]
    assert diagnostics["background_color"] == "#eeeeee"


@pytest.mark.parametrize("orient", [np.rot90, np.transpose, np.flipud, np.fliplr])
def test_background_extraction_is_covariant_to_artwork_orientation(orient):
    original = badge()
    if orient == np.transpose:

        def transform(array):
            return np.swapaxes(array, 0, 1)
    else:
        transform = orient
    assert np.array_equal(
        bitmap_foreground(transform(original)), transform(bitmap_foreground(original))
    )


def test_enclosed_identical_background_colour_is_preserved_but_diagonal_escape_is_open():
    rgba = np.full((9, 9, 4), 255, dtype=np.uint8)
    rgba[2:7, 2:7, :3] = 0
    rgba[3:6, 3:6, :3] = 255
    diagnostics = {}
    closed = bitmap_foreground(rgba, diagnostics=diagnostics)
    assert np.all(closed[3:6, 3:6, 3] == 255)
    assert diagnostics["interior_preserved_pixels"] == 9
    rgba[2, 2, :3] = 255
    opened = bitmap_foreground(rgba)
    assert np.all(opened[3:6, 3:6, 3] == 0)
    # Hidden RGB values in an alpha opening cannot block a real escape route.
    rgba[2, 2] = [0, 0, 0, 0]
    transparent_opening = bitmap_foreground(rgba)
    assert np.all(transparent_opening[3:6, 3:6, 3] == 0)


def test_keep_and_ambiguous_auto_retain_every_pixel():
    rgba = badge().copy()
    assert np.array_equal(bitmap_foreground(rgba, "keep"), rgba)
    rgba[:30, 0] = [0, 0, 255, 255]
    rgba[:30, -1] = [0, 0, 255, 255]
    rgba[0] = [0, 0, 255, 255]
    diagnostics = {}
    assert np.array_equal(bitmap_foreground(rgba, "auto", diagnostics), rgba)
    assert diagnostics["reason"] == "ambiguous_perimeter"
    assert diagnostics["border_confidence"] < 0.85
    assert bitmap_foreground(rgba, "remove")[0, 0, 3] == 0


def test_actual_alpha_has_priority_but_almost_opaque_alpha_does_not_disable_detection():
    rgba = badge().copy()
    rgba[30, 30, 3] = 254
    assert bitmap_foreground(rgba)[0, 0, 3] == 0
    rgba[30, 30, 3] = 0
    assert bitmap_foreground(rgba)[30, 30, 3] == 0
    assert bitmap_foreground(rgba)[0, 0, 3] == 0
    rgba[0, 0, 3] = 0
    assert np.array_equal(bitmap_foreground(rgba), rgba)


def test_pale_foreground_is_distinct_from_uniform_background():
    rgba = np.full((40, 60, 4), 255, dtype=np.uint8)
    rgba[10:30, 15:45, :3] = 245
    result = bitmap_foreground(rgba)
    assert np.all(result[10:30, 15:45, 3] == 255)
    assert result[0, 0, 3] == 0


def test_raster_keep_includes_canvas_and_auto_retains_white_badge(tmp_path):
    path = tmp_path / "badge.png"
    Image.fromarray(badge()).save(path)
    auto = Path(raster_to_svg(path, tmp_path / "auto.svg", preserve_colors=True))
    kept = Path(
        raster_to_svg(path, tmp_path / "kept.svg", preserve_colors=True, background_mode="keep")
    )
    automatic_colors = {p.get("fill") for p in ET.parse(auto).getroot().findall("{*}path")}
    kept_colors = {p.get("fill") for p in ET.parse(kept).getroot().findall("{*}path")}
    assert automatic_colors == {"#ffffff", "#000000", "#ff0000"}
    assert kept_colors == automatic_colors | {"#eeeeee"}
    auto_svg, _ = load_svg_paths(auto)
    kept_svg, _ = load_svg_paths(kept)
    assert kept_svg.height / kept_svg.width < auto_svg.height / auto_svg.width


def test_monochrome_keep_is_the_visible_canvas_not_an_ignored_setting(tmp_path):
    source = tmp_path / "badge.png"
    Image.fromarray(badge()).save(source)
    kept, _ = load_svg_paths(raster_to_svg(source, tmp_path / "mono.svg", background_mode="keep"))
    assert kept.height / kept.width == pytest.approx(62 / 82)
    diagnostics = {}
    raster_to_svg(
        source,
        tmp_path / "threshold.svg",
        threshold=100,
        background_mode="keep",
        diagnostics=diagnostics,
    )
    assert diagnostics["background"]["reason"] == "manual_threshold_or_inversion"


def test_manual_inversion_never_sews_transparent_margins_or_counters(tmp_path):
    image = Image.new("RGBA", (120, 120), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 99, 99), fill=(200, 200, 200, 255))
    draw.rectangle((45, 45, 74, 74), fill=(255, 255, 255, 0))
    source = tmp_path / "transparent.png"
    image.save(source)
    result = raster_to_svg(source, tmp_path / "inverted.svg", threshold=128, invert=True)
    document, _ = load_svg_paths(result)
    assert document.root.get("viewBox") == "0 0 82 82"
    rgba, _ = rasterize_rgba(document)
    centre = rgba[rgba.shape[0] // 2, rgba.shape[1] // 2]
    assert centre[3] == 0


def test_svg_explicit_removal_preserves_feature_scale_and_white_interior(tmp_path):
    source = tmp_path / "framed.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="60mm" viewBox="0 0 100 60">'
        '<rect width="100" height="60" fill="#eeeeee"/>'
        '<rect x="30" y="20" width="40" height="20" fill="black"/>'
        '<rect x="35" y="25" width="30" height="10" fill="white"/></svg>'
    )
    output = tmp_path / "prepared"
    output.mkdir()
    before = source.read_bytes()
    result, warnings, diagnostics = prepare_artwork(
        source,
        output,
        GenerationParams(background_mode="remove"),
        StitchParams(),
        preserve_colors=True,
    )
    assert source.read_bytes() == before
    document, _ = load_svg_paths(result)
    assert document.width / UNITS_PER_MM == pytest.approx(40, abs=0.3)
    assert document.height / UNITS_PER_MM == pytest.approx(20, abs=0.3)
    assert {p.get("fill") for p in document.root.findall("{*}path")} == {"#000000", "#ffffff"}
    assert diagnostics["background"]["applied"]
    assert any("physical scale is preserved" in warning for warning in warnings)


def test_compressed_logo_recovers_flat_paints_without_edge_threads():
    image = Image.new("RGB", (240, 240), "#eeeeee")
    drawing = ImageDraw.Draw(image)
    drawing.ellipse((20, 20, 220, 220), fill="white", outline="black", width=5)
    drawing.rectangle((55, 55, 185, 95), fill="#ff1301")
    drawing.rectangle((55, 145, 185, 185), fill="#0e0f95")
    stream = io.BytesIO()
    image.save(stream, format="JPEG", quality=90)
    compressed = np.asarray(Image.open(io.BytesIO(stream.getvalue())).convert("RGBA"))
    rgba = bitmap_foreground(compressed)
    labels, colors, reduced = bitmap_colors(rgba)
    assert reduced
    assert len(colors) == 4
    assert all((labels > 0)[rgba[..., 3] >= 128])
    turned, again, _ = bitmap_colors(np.rot90(rgba))
    assert again == colors
    assert np.array_equal(turned, np.rot90(labels))


def test_recovered_compressed_palette_preserves_an_isolated_contrasting_accent():
    image = Image.new("RGB", (240, 240), "#eeeeee")
    drawing = ImageDraw.Draw(image)
    drawing.ellipse((20, 20, 220, 220), fill="white", outline="black", width=5)
    drawing.rectangle((55, 55, 185, 95), fill="#ff1301")
    drawing.rectangle((55, 145, 185, 185), fill="#0e0f95")
    stream = io.BytesIO()
    image.save(stream, format="JPEG", quality=90)
    compressed = np.asarray(Image.open(io.BytesIO(stream.getvalue())).convert("RGBA"))
    rgba = bitmap_foreground(compressed)
    rgba[4, 4] = [0, 255, 0, 255]
    diagnostics = {}
    labels, colors, _ = bitmap_colors(rgba, diagnostics=diagnostics)
    assert diagnostics["flat_paints_recovered"]
    assert diagnostics["retained_accent_colors"] == 1
    assert len(colors) == 5
    assert colors[labels[4, 4] - 1] == "#00ff00"
    cleaned = clean_color_regions(labels, colors, 12, {})
    assert colors[cleaned[4, 4] - 1] == "#00ff00"


def test_unrecoverable_checkerboard_fails_before_contour_tracing(tmp_path, monkeypatch):
    rgba = np.empty((100, 100, 4), dtype=np.uint8)
    rgba[..., 3] = 255
    rgba[..., :3] = np.where(np.indices((100, 100)).sum(axis=0)[..., None] % 2, 255, 0)
    path = tmp_path / "checkerboard.png"
    Image.fromarray(rgba).save(path)

    def unexpected_contours(*args, **kwargs):
        raise AssertionError("Contour tracing should not start above the region budget")

    monkeypatch.setattr("embroidery_rungs.inputs.find_contours", unexpected_contours)
    with pytest.raises(ValueError, match="visible regions after interpretation"):
        raster_to_svg(
            path, tmp_path / "checkerboard.svg", preserve_colors=True, background_mode="keep"
        )
    assert not (tmp_path / "checkerboard.svg").exists()


def test_bitmap_cleanup_keeps_exact_similar_paints_and_isolated_contrasting_accents():
    rgba = np.full((60, 100, 4), 255, dtype=np.uint8)
    rgba[:, :50, :3] = [253, 0, 0]
    rgba[:, 50:, :3] = [255, 0, 0]
    rgba[3, 3] = [0, 255, 0, 255]
    labels, colors, _ = bitmap_colors(rgba)
    assert set(colors) == {"#fd0000", "#ff0000", "#00ff00"}
    diagnostics = {}
    cleaned = clean_color_regions(labels, colors, 20, diagnostics)
    assert colors[cleaned[3, 3] - 1] == "#00ff00"


@pytest.mark.parametrize("orient", [np.rot90, np.flipud, np.fliplr])
def test_small_similar_speckles_merge_without_alpha_changes_or_lost_accents(orient):
    labels = np.zeros((40, 60), dtype=np.uint8)
    labels[5:35, 5:45] = 1
    labels[10, 10] = 2
    labels[25, 20] = 3
    labels[1, 55] = 2
    labels[15:20, 20:25] = 0
    colors = ["#f99000", "#f99804", "#00ff00"]
    diagnostics = {}
    cleaned = clean_color_regions(labels, colors, 20, diagnostics)
    assert cleaned[10, 10] == 1
    assert cleaned[25, 20] == 3
    assert cleaned[1, 55] == 2
    assert np.array_equal(cleaned > 0, labels > 0)
    assert diagnostics["changed_pixels"] == 1
    assert diagnostics["removed_pixels"] == 0
    assert diagnostics["regions_after"] == diagnostics["regions_before"] - 1
    assert np.array_equal(clean_color_regions(orient(labels), colors, 20, {}), orient(cleaned))


def test_cleanup_has_physical_area_bound_and_can_be_disabled(tmp_path):
    image = Image.new("RGBA", (200, 200), "#f99000")
    ImageDraw.Draw(image).point((100, 100), fill="#f99804")
    source = tmp_path / "speckle.png"
    image.save(source)
    enabled = {}
    disabled = {}
    raster_to_svg(
        source,
        tmp_path / "clean.svg",
        width_mm=10,
        preserve_colors=True,
        background_mode="keep",
        diagnostics=enabled,
    )
    raster_to_svg(
        source,
        tmp_path / "raw.svg",
        width_mm=10,
        preserve_colors=True,
        background_mode="keep",
        cleanup=False,
        diagnostics=disabled,
    )
    assert enabled["cleanup"]["changed_pixels"] > 0
    assert enabled["cleanup"]["changed_area_mm2"] <= 0.10
    assert disabled["cleanup"]["changed_pixels"] == 0
    assert disabled["cleanup"]["reason"] == "disabled_by_request"


def test_cleanup_uses_final_hoop_size_instead_of_the_oversized_request(tmp_path):
    image = Image.new("RGBA", (200, 200), "#f99000")
    ImageDraw.Draw(image).point((100, 100), fill="#f99804")
    source = tmp_path / "speckle.png"
    image.save(source)
    exact_dir, fitted_dir = tmp_path / "exact", tmp_path / "fitted"
    exact_dir.mkdir()
    fitted_dir.mkdir()
    machine = StitchParams(hoop_width_mm=37, hoop_height_mm=37)
    exact, _, exact_analysis = prepare_artwork(
        source,
        exact_dir,
        GenerationParams(design_width_mm=35, background_mode="keep"),
        machine,
        preserve_colors=True,
    )
    fitted, warnings, fitted_analysis = prepare_artwork(
        source,
        fitted_dir,
        GenerationParams(design_width_mm=200, background_mode="keep", fit_to_hoop=True),
        machine,
        preserve_colors=True,
    )
    assert exact.read_bytes() == fitted.read_bytes()
    assert exact_analysis["cleanup"] == fitted_analysis["cleanup"]
    assert exact_analysis["cleanup"]["changed_pixels"] == 1
    assert any("Artwork sized to 35.0" in warning for warning in warnings)
