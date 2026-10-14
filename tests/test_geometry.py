import numpy as np

from embroidery_rungs.geometry_utils import get_skeleton_paths
from embroidery_rungs.image_processor import compute_medial_axis, rasterize_svg
from embroidery_rungs.svg_manager import load_svg_paths


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


def test_raster_budget(svg_file):
    from embroidery_rungs.image_processor import MAX_DIMENSION, MAX_PIXELS

    doc, _ = load_svg_paths(
        svg_file('<rect width="10000" height="10000"/>', width="10000", height="10000")
    )
    mask, transform = rasterize_svg(doc, dpi=2400)
    assert max(mask.shape) <= MAX_DIMENSION + 6
    assert (mask.shape[0] - 6) * (mask.shape[1] - 6) <= MAX_PIXELS
    assert transform.a < 1
    assert transform.a == transform.d


def test_loop_returning_to_an_adjacent_junction_pixel_is_preserved():
    skeleton = np.zeros((22, 25), dtype=bool)
    skeleton[7, 5:19] = skeleton[17, 5:19] = True
    skeleton[7:18, 5] = skeleton[7:18, 18] = True
    skeleton[4:7, 10] = True
    skeleton[8:11, 11] = True
    paths = get_skeleton_paths(skeleton)
    loops = [p for p in paths if np.array_equal(p["points"][0], p["points"][-1])]
    assert len(loops) == 1
    points = loops[0]["points"]
    assert np.linalg.norm(np.diff(points, axis=0), axis=1).sum() > 40
    assert points[:, 0].max() == 17
    assert points[:, 1].min() == 5
    assert points[:, 1].max() == 18
    assert loops[0]["start_node"] == loops[0]["end_node"]
