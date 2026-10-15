"""Opaque interior intent is reported without changing the existing paint decision."""

from __future__ import annotations

import io
from xml.etree import ElementTree as ET

import numpy as np
import pytest
import resvg_py
from PIL import Image, ImageDraw

from embroidery_rungs import GenerationParams, StitchParams
from embroidery_rungs.inputs import _monochrome_counters, prepare_artwork

_G = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="80mm" '
    'viewBox="0 0 80 80"><g fill="none" stroke="#111111" stroke-linecap="round" '
    'stroke-linejoin="round"><ellipse cx="30" cy="33" rx="12" ry="14" stroke-width="4"/>'
    '<path d="M42 19 V56 C42 71 20 70 18 59" stroke-width="4"/></g></svg>'
)


def _prepare(source, tmp_path, **settings):
    directory = tmp_path / "prepared"
    directory.mkdir(exist_ok=True)
    return prepare_artwork(
        source,
        directory,
        GenerationParams(design_width_mm=28.083333333333332, **settings),
        StitchParams(max_colors=6),
        preserve_colors=True,
    )


def _fills(path):
    return {
        element.get("fill")
        for element in ET.parse(path).getroot().iter()
        if element.get("fill") is not None
    }


def _badge(thin=False):
    image = Image.new("RGB", (160, 180), "white")
    draw = ImageDraw.Draw(image)
    if thin:
        draw.ellipse((50, 10, 100, 170), fill="white", outline="black", width=3)
    else:
        draw.ellipse((20, 30, 140, 150), fill="black")
        draw.ellipse((65, 75, 95, 105), fill="white")
    return image


def _assert_warning(warnings):
    assert any(
        "Opaque interior paint" in warning
        and "retained" in warning
        and "transparent PNG or SVG" in warning
        for warning in warnings
    )


def test_jpeg_g_reports_the_one_preserved_opaque_interior_without_claiming_false_threads(tmp_path):
    rendered = resvg_py.svg_to_bytes(
        svg_string=_G, width=1920, height=1920, dpi=96, skip_system_fonts=True
    )
    image = Image.open(io.BytesIO(rendered)).convert("RGBA")
    matte = Image.new("RGBA", image.size, "white")
    matte.alpha_composite(image)
    source = tmp_path / "g.jpg"
    matte.convert("RGB").save(source, quality=75, subsampling=2)
    prepared, warnings, diagnostics = _prepare(source, tmp_path)
    background = diagnostics["background"]
    ambiguity = background["counter_ambiguity"]
    assert _fills(prepared) == {"#111111", "#ffffff"}
    assert background["counter_inference"] == "compact_interior_preserved"
    assert background["counters_inferred"] == 0
    assert ambiguity["reason"] == "opaque_interior_matches_removed_background"
    assert ambiguity["regions"] == 1
    assert ambiguity["structures"] == {"compact_interior": 1}
    assert ambiguity["area_mm2"] > 300
    assert ambiguity["area_mm2"] == pytest.approx(
        ambiguity["pixels"] * diagnostics["resampling"]["working_pixel_size_mm"] ** 2,
        abs=1e-6,
    )
    assert diagnostics["tracing"]["final"]["changed_pixels"] == 0
    _assert_warning(warnings)


@pytest.mark.parametrize("thin,structure", [(False, "compact_interior"), (True, "thin_outline")])
def test_badges_keep_white_paint_and_explain_the_same_opaque_ambiguity(tmp_path, thin, structure):
    source = tmp_path / "badge.png"
    _badge(thin).save(source)
    prepared, warnings, diagnostics = _prepare(source, tmp_path)
    ambiguity = diagnostics["background"]["counter_ambiguity"]
    assert _fills(prepared) == {"#000000", "#ffffff"}
    assert ambiguity["regions"] == 1
    assert ambiguity["structures"] == {structure: 1}
    assert ambiguity["pixels"] > 0 and ambiguity["area_mm2"] > 0
    assert diagnostics["background"]["counters_inferred"] == 0
    _assert_warning(warnings)


@pytest.mark.parametrize("transform", [lambda array: array, np.rot90, np.fliplr])
def test_diagnostic_never_changes_existing_compact_paint_or_input_labels(transform):
    labels = np.zeros((70, 90), dtype=np.uint8)
    labels[5:65, 5:85] = 1
    labels[25:45, 35:55] = 2
    labels = transform(labels)
    before = labels.copy()
    info = {"mode": "auto", "applied": True, "background_color": "#ffffff"}
    actual = _monochrome_counters(labels, ["#000000", "#ffffff"], info, True, pixels_per_mm=10)
    assert np.array_equal(actual, before)
    assert np.array_equal(labels, before)
    assert info["counter_ambiguity"] == {
        "reason": "opaque_interior_matches_removed_background",
        "regions": 1,
        "pixels": 400,
        "area_mm2": 4.0,
        "structures": {"compact_interior": 1},
    }


def test_direct_helper_without_scale_does_not_invent_square_millimetres():
    labels = np.ones((30, 30), dtype=np.uint8)
    labels[10:20, 10:20] = 2
    info = {"mode": "auto", "applied": True, "background_color": "#ffffff"}
    _monochrome_counters(labels, ["#000000", "#ffffff"], info, True)
    assert info["counter_ambiguity"]["area_mm2"] is None


@pytest.mark.parametrize("settings", [{"background_mode": "keep"}, {"raster_cleanup": False}])
def test_explicit_keep_or_disabled_cleanup_does_not_claim_ambiguous_interpretation(
    tmp_path, settings
):
    source = tmp_path / "badge.png"
    _badge().save(source)
    _, warnings, diagnostics = _prepare(source, tmp_path, **settings)
    assert "counter_ambiguity" not in diagnostics["background"]
    assert not any("Opaque interior paint" in warning for warning in warnings)


def test_native_alpha_g_has_no_opaque_paint_ambiguity(tmp_path):
    source = tmp_path / "g.png"
    source.write_bytes(
        resvg_py.svg_to_bytes(svg_string=_G, width=960, height=960, dpi=96, skip_system_fonts=True)
    )
    prepared, warnings, diagnostics = _prepare(source, tmp_path)
    assert _fills(prepared) == {"#111111"}
    assert "counter_ambiguity" not in diagnostics["background"]
    assert not any("Opaque interior paint" in warning for warning in warnings)


@pytest.mark.parametrize("background_mode", ["auto", "remove"])
def test_explicit_vector_white_never_acquires_raster_counter_ambiguity(tmp_path, background_mode):
    source = tmp_path / "badge.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="30mm" height="30mm" viewBox="0 0 30 30">'
        '<rect width="30" height="30" fill="white"/>'
        '<circle cx="15" cy="15" r="12" fill="black"/>'
        '<circle cx="15" cy="15" r="3" fill="white"/></svg>'
    )
    prepared, warnings, diagnostics = _prepare(source, tmp_path, background_mode=background_mode)
    assert "#ffffff" in _fills(prepared) or "white" in _fills(prepared)
    assert "counter_ambiguity" not in diagnostics["background"]
    assert not any("Opaque interior paint" in warning for warning in warnings)


@pytest.mark.parametrize("transparent", [False, True])
def test_multicolor_badge_or_transparent_white_border_remains_explicit_paint(tmp_path, transparent):
    # Pepsi-like white centre vs Jungly-like explicit alpha and white border.
    image = Image.new("RGBA", (180, 180), (0, 0, 0, 0) if transparent else "#dddddd")
    draw = ImageDraw.Draw(image)
    draw.ellipse((10, 10, 170, 170), fill="white", outline="black", width=3)
    draw.pieslice((20, 20, 160, 160), 180, 360, fill="red")
    draw.pieslice((20, 20, 160, 160), 0, 180, fill="blue")
    draw.rectangle((20, 75, 160, 105), fill="white")
    draw.rectangle((65, 80, 80, 100), fill="black")
    source = tmp_path / "multicolor.png"
    image.save(source)
    prepared, warnings, diagnostics = _prepare(source, tmp_path)
    assert "#ffffff" in _fills(prepared)
    assert diagnostics["cleanup"]["palette_colors"] >= 4
    assert "counter_ambiguity" not in diagnostics["background"]
    assert not any("Opaque interior paint" in warning for warning in warnings)
