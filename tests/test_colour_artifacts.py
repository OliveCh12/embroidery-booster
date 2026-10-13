"""Colour-specific fidelity: real accents, compression slivers and sewn travel."""

import json
from pathlib import Path

import numpy as np
import pyembroidery as pe
import pytest
from scipy.ndimage import label
from shapely import covers, linestrings
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from embroidery_rungs import StitchParams, generate
from embroidery_rungs.colors import bitmap_colors, separate_colors
from embroidery_rungs.image_processor import rasterize_rgba
from embroidery_rungs.stitching.quality import measure_stitches
from embroidery_rungs.svg_manager import UNITS_PER_MM, load_svg_paths


def _compressed_paint(*, paint=(14, 15, 149), fragment=(97, 94, 150)):
    rgba = np.full((80, 100, 4), 255, dtype=np.uint8)
    rgba[10:70, 40:90, :3] = paint
    rgba[10:70, 10:25, :3] = 1
    # Several observed nearby shades enter the compressed-flat-paint path.
    for x in range(40, 90):
        rgba[30:40, x, :3] = np.clip(np.array(paint) + x % 5 - 2, 0, 255)
    rgba[10, 70, :3] = fragment
    return rgba


@pytest.mark.parametrize(
    "paint,fragment",
    [((14, 15, 149), (97, 94, 150)), ((0, 156, 48), (59, 85, 65)), ((255, 19, 1), (145, 76, 77))],
)
def test_a_compressed_colour_fragment_cannot_borrow_distant_black_ink(paint, fragment):
    rgba = _compressed_paint(paint=paint, fragment=fragment)
    labels, colors, _ = bitmap_colors(rgba, max_colors=6, cleanup=True)
    # A fringe may resolve to either adjacent paint, depending on its colour
    # mixture. The unrelated remote black is never a valid local choice.
    assert labels[10, 70] in {labels[9, 70], labels[20, 70]}, (
        paint,
        fragment,
        colors[labels[10, 70] - 1],
    )
    black = next(index for index, color in enumerate(colors, 1) if color == "#010101")
    assert label(labels == black)[1] == 1


@pytest.mark.parametrize("size", [1, 2, 3])
def test_actual_black_accents_survive_among_compressed_neighbouring_colours(size):
    rgba = _compressed_paint()
    rgba[50 : 50 + size, 70 : 70 + size, :3] = 1
    labels, colors, _ = bitmap_colors(rgba, max_colors=6, cleanup=True)
    black = colors.index("#010101") + 1
    assert np.all(labels[50 : 50 + size, 70 : 70 + size] == black)
    assert np.all(labels[10:70, 10:25] == black)


def test_neutral_ink_fringe_is_not_reinterpreted_as_neighbouring_coloured_paint():
    rgba = _compressed_paint(paint=(0, 156, 48), fragment=(69, 75, 72))
    baseline, before, _ = bitmap_colors(rgba, max_colors=6, cleanup=False)
    labels, colors, _ = bitmap_colors(rgba, max_colors=6, cleanup=True)
    # Nearly neutral grey can be the fringe of intended black ink. Local colour
    # proximity alone cannot establish that it belongs to the green body.
    assert before[baseline[10, 70] - 1] == colors[labels[10, 70] - 1] == "#010101"


def test_a_stable_gray_paint_is_distinct_from_an_isolated_compression_fragment():
    rgba = _compressed_paint()
    rgba[50:55, 70:75, :3] = [97, 94, 150]
    labels, colors, _ = bitmap_colors(rgba, max_colors=6, cleanup=True)
    accent = colors.index("#615e96") + 1
    assert np.all(labels[50:55, 70:75] == accent)


def test_exact_palette_keeps_an_isolated_contrasting_pixel_even_beside_black():
    rgba = np.full((50, 60, 4), 255, dtype=np.uint8)
    rgba[10:40, 10:25, :3] = 1
    rgba[10:40, 30:50, :3] = [14, 15, 149]
    rgba[20, 32, :3] = [97, 94, 150]
    labels, colors, reduced = bitmap_colors(rgba, cleanup=True)
    assert colors[labels[20, 32] - 1] == "#615e96"
    assert not reduced


def _sewn(commands):
    commands = np.asarray(commands)
    codes = commands[:, 2].astype(int) & pe.COMMAND_MASK
    current_color = np.cumsum(codes == pe.COLOR_CHANGE)
    sewn = (codes[:-1] == pe.STITCH) & (codes[1:] == pe.STITCH)
    return np.stack((commands[:-1, :2], commands[1:, :2]), axis=1)[sewn], current_color[1:][sewn]


def _exported_top(data, color):
    result = []
    for run in data["top_layer_runs"]:
        if run["color_index"] != color:
            continue
        coordinates = np.asarray(data["commands"])[run["start"] : run["end"], :2]
        result.append([*coordinates[0], pe.JUMP])
        result.extend([[*point, pe.STITCH] for point in coordinates])
    return result


@pytest.mark.parametrize("underlay", [False, True])
def test_real_black_eyes_and_lettering_have_complete_own_colour_coverage_without_foreign_travel(
    tmp_path, underlay
):
    source = tmp_path / "eyes-and-letter.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="40mm" height="20mm" viewBox="0 0 40 20">'
        '<rect width="40" height="20" fill="#f4b221"/>'
        '<circle cx="10" cy="6" r=".8" fill="#000000"/>'
        '<circle cx="30" cy="6" r=".8" fill="#000000"/>'
        '<path d="M16 10V15H22" fill="none" stroke="#000000" stroke-width="1"/>'
        "</svg>"
    )
    result = generate(
        source,
        tmp_path / "machine",
        stitch_params=StitchParams.for_fabric("stable", underlay=underlay),
    )
    data = json.loads(Path(result.direct.plan_path).read_text())
    assert set(data["threads"]) == {"#000000", "#f4b221"}
    commands = np.asarray(data["commands"])
    expected_segments, expected_colors = _sewn(commands)
    for path in (result.direct.pes_path, result.direct.dst_path):
        pattern = pe.read(path)
        actual_segments, actual_colors = _sewn(pattern.stitches)
        np.testing.assert_array_equal(actual_segments, expected_segments)
        np.testing.assert_array_equal(actual_colors, expected_colors)
        assert [thread.hex_color().lower() for thread in pattern.threadlist] == data["threads"]

    # All sewn phases count here, including underlay, ties and connectors. Only
    # geometric compensation around the intended black ink is permitted.
    black = data["threads"].index("#000000")
    physical = expected_segments[expected_colors == black] / 10 + data["origin_mm"]
    allowed = unary_union(
        [
            Point(10, 6).buffer(0.8),
            Point(30, 6).buffer(0.8),
            LineString([(16, 10), (16, 15), (22, 15)]).buffer(0.5),
        ]
    ).buffer(0.35)
    assert covers(allowed, linestrings(physical)).all()
    document, _ = load_svg_paths(result.original_path)
    rgba, transform = rasterize_rgba(document, 305)
    labels, colors, _ = separate_colors(rgba)
    for index, color in enumerate(data["threads"]):
        metrics, _ = measure_stitches(
            _exported_top(data, index),
            data["origin_mm"],
            labels == colors.index(color) + 1,
            transform.a * UNITS_PER_MM,
            [transform.e, transform.f],
        )
        assert metrics["structural_coverage"] >= 0.999
        assert metrics["largest_gap_mm2"] <= 0.05
    assert result.direct.stats["omitted_regions"] == 0
