import numpy as np
import pytest
from scipy.ndimage import binary_dilation

from embroidery_rungs.geometry_utils import get_skeleton_paths, segments_intersect
from embroidery_rungs.image_processor import compute_medial_axis, rasterize_svg
from embroidery_rungs.pipeline import coverage_mask, image_scale, spacing_to_px
from embroidery_rungs.rung_generator import generate_rungs
from embroidery_rungs.svg_manager import load_svg_paths


def geometry(path, *, dpi=150, density=1, auto=False):
    doc, _ = load_svg_paths(path)
    mask, transform = rasterize_svg(doc, dpi)
    skeleton, distance = compute_medial_axis(mask)
    scale = image_scale(transform)
    ppm = spacing_to_px(1, 1, scale)
    rungs, bridges, elements = generate_rungs(
        skeleton,
        distance,
        spacing_to_px(3, density, scale),
        mask,
        min_satin_width_px=1.5 * ppm,
        pixels_per_mm=ppm,
        auto_optimize=auto,
    )
    return mask, rungs, elements, ppm


def test_mat_preserves_small_hole_and_is_deterministic():
    mask = np.zeros((80, 100), dtype=bool)
    mask[5:75, 5:95] = True
    mask[30:38, 45:53] = False
    original = mask.copy()
    a, distance = compute_medial_axis(mask)
    b, _ = compute_medial_axis(mask)
    assert np.array_equal(original, mask)
    assert np.array_equal(a, b)
    assert np.all(mask[a])
    assert distance[33, 49] == 0
    assert distance[10, 10] == 6


def test_all_disconnected_cycles_are_traced():
    skeleton = np.zeros((90, 110), dtype=bool)
    skeleton[5, 5:20] = True
    for x in (10, 60):
        skeleton[30, x : x + 25] = skeleton[54, x : x + 25] = True
        skeleton[30:55, x] = skeleton[30:55, x + 24] = True
    paths = get_skeleton_paths(skeleton)
    assert len(paths) == 3
    assert sum(np.array_equal(p["points"][0], p["points"][-1]) for p in paths) == 2


@pytest.mark.parametrize(
    "content,min_coverage",
    [
        ('<rect x="10" y="20" width="200" height="40"/>', 0.98),
        ('<circle cx="60" cy="60" r="40"/>', 0.97),
        (
            '<rect x="10" y="10" width="100" height="15"/><rect x="10" y="35" width="100" height="15"/>',
            0.98,
        ),
        ('<path fill-rule="evenodd" d="M10 10H110V110H10Z M30 30H90V90H30Z"/>', 0.85),
        ('<path d="M50 10H70V50H110V70H70V110H50V70H10V50H50Z"/>', 0.9),
    ],
)
def test_swept_coverage_and_no_large_spill(svg_file, content, min_coverage):
    mask, rungs, elements, ppm = geometry(svg_file(content))
    covered = coverage_mask(mask, elements, ppm)
    assert np.count_nonzero(covered & mask) / mask.sum() >= min_coverage
    assert np.count_nonzero(covered & ~binary_dilation(mask, iterations=2)) / mask.sum() < 0.005
    assert rungs
    assert all(len(e["rungs"]) >= 3 for e in elements if e["type"] == "satin")
    for i, (a, b) in enumerate(rungs):
        assert not any(segments_intersect(a, b, c, d) for c, d in rungs[:i])


def test_hole_is_not_filled(svg_file):
    mask, _, elements, ppm = geometry(
        svg_file('<path fill-rule="evenodd" d="M10 10H110V110H10Z M30 30H90V90H30Z"/>')
    )
    swept = coverage_mask(mask, elements, ppm)
    assert not swept[65:95, 65:95].any()


def test_density_changes_checkpoints_not_rails(svg_file):
    path = svg_file('<rect x="10" y="20" width="200" height="40"/>')
    _, sparse, es, _ = geometry(path)
    _, dense, ed, _ = geometry(path, density=2)
    assert len(dense) > len(sparse)
    assert es[0]["rail_a"] == ed[0]["rail_a"]
    assert es[0]["rail_b"] == ed[0]["rail_b"]


def test_thin_column_becomes_running(svg_file):
    path = svg_file('<rect x="10" y="10" width="100" height="3"/>')
    _, rungs, elements, _ = geometry(path)
    assert elements and all(e["type"] == "running" for e in elements)
    assert not rungs


def test_auto_refines_without_rebuilding_rails(svg_file):
    path = svg_file('<path d="M10 50 Q100 10 210 50 L210 70 Q100 30 10 70Z"/>')
    _, manual, a, _ = geometry(path)
    _, automatic, b, _ = geometry(path, auto=True)
    assert len(automatic) >= len(manual)
    assert [(e.get("rail_a"), e.get("rail_b")) for e in a] == [
        (e.get("rail_a"), e.get("rail_b")) for e in b
    ]


def test_raster_budget(svg_file):
    from embroidery_rungs.image_processor import MAX_DIMENSION, MAX_PIXELS

    doc, _ = load_svg_paths(
        svg_file('<rect width="10000" height="10000"/>', width="10000", height="10000")
    )
    mask, transform = rasterize_svg(doc, dpi=2400)
    assert max(mask.shape) <= MAX_DIMENSION + 6
    assert (mask.shape[0] - 6) * (mask.shape[1] - 6) <= MAX_PIXELS
    assert image_scale(transform) < 1
