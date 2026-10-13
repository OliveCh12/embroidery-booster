from xml.etree import ElementTree as ET

import numpy as np
import pytest
from PIL import Image

from embroidery_rungs.input_quality import complete_input_analysis
from embroidery_rungs.inputs import raster_to_svg
from embroidery_rungs.svg_manager import load_svg_paths


@pytest.mark.parametrize("preserve_colors", [False, True])
def test_raster_contract_reports_canvas_visible_size_and_source_crop(tmp_path, preserve_colors):
    rgba = np.zeros((40, 60, 4), dtype=np.uint8)
    rgba[8:20, 12:28, 3] = 255
    source, target = tmp_path / "input.png", tmp_path / "artwork.svg"
    Image.fromarray(rgba).save(source)
    diagnostics = {}
    assert raster_to_svg(
        source, target, width_mm=80, preserve_colors=preserve_colors, diagnostics=diagnostics
    ) == str(target)
    geometry = diagnostics["geometry"]
    assert geometry["source_crop_box_px"] == [12, 8, 28, 20]
    assert geometry["canvas_size_mm"] == pytest.approx([80, 80 * 14 / 18])
    assert geometry["visible_size_mm"] == pytest.approx([80 * 16 / 18, 80 * 12 / 18])
    assert geometry["pixel_size_mm"] == pytest.approx([80 / 18, 80 / 18])
    assert ET.parse(target).getroot().attrib["viewBox"] == "0 0 18 14"


def test_geometry_report_tracks_final_sizing_without_changing_source_crop(tmp_path):
    rgba = np.zeros((40, 60, 4), dtype=np.uint8)
    rgba[8:20, 12:28, 3] = 255
    source, target = tmp_path / "input.png", tmp_path / "artwork.svg"
    Image.fromarray(rgba).save(source)
    diagnostics = {}
    raster_to_svg(source, target, width_mm=80, preserve_colors=True, diagnostics=diagnostics)
    svg, _ = load_svg_paths(target)
    svg.width /= 2
    svg.height /= 2
    complete_input_analysis(svg, diagnostics)
    geometry = diagnostics["geometry"]
    assert geometry["canvas_size_mm"] == pytest.approx([40, 31.1111])
    assert geometry["visible_size_mm"] == pytest.approx([40 * 16 / 18, 40 * 12 / 18], abs=1e-4)
    assert geometry["source_crop_box_px"] == [12, 8, 28, 20]
    first = geometry.copy()
    complete_input_analysis(svg, diagnostics)
    assert geometry == first
