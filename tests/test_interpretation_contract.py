import json
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from embroidery_rungs.interpretation import RasterArtwork


def _artwork():
    labels = np.zeros((8, 12), dtype=np.uint8)
    labels[1:7, 2:10] = 1
    labels[2:6, 6:10] = 2
    labels[3:5, 4:7] = 0
    return RasterArtwork(labels, ("#010101", "#ff1301"), (60, 24), (10, 20, 130, 100))


def test_labels_are_an_independent_immutable_copy_even_from_a_noncontiguous_view():
    original = np.zeros((12, 16), dtype=np.int32)
    original[2:10, 4:12] = 1
    view = original[::2, ::2]
    artwork = RasterArtwork(view, ("#010101",), (24, 18))
    before = artwork.labels.copy()
    original[:] = 0
    assert np.array_equal(artwork.labels, before)
    assert not np.shares_memory(artwork.labels, original)
    assert artwork.labels.dtype == np.int32
    with pytest.raises(ValueError, match="read-only"):
        artwork.labels[2, 2] = 0
    with pytest.raises(ValueError):
        artwork.labels.setflags(write=True)
    with pytest.raises(ValueError):
        artwork.labels.base.setflags(write=True)
    with pytest.raises(FrozenInstanceError):
        artwork.canvas_size_mm = (1, 1)


def test_mutable_palette_size_and_crop_inputs_are_not_retained():
    palette, size, crop = ["#010101"], [24, 12], [3, 5, 27, 17]
    artwork = RasterArtwork(np.ones((4, 8), dtype=int), palette, size, crop)
    palette[0], size[0], crop[0] = "#ffffff", 100, 0
    assert artwork.palette == ("#010101",)
    assert artwork.canvas_size_mm == (24.0, 12.0)
    assert artwork.source_crop_box_px == (3, 5, 27, 17)


def test_existing_pixel_centred_frame_and_transparent_holes_are_preserved():
    artwork = _artwork()
    assert artwork.labels[3, 5] == 0
    assert artwork.labels[2, 7] == 2
    assert artwork.pixel_size_mm == (5, 3)
    assert artwork.visible_bounds_mm == (7.5, 1.5, 47.5, 19.5)
    assert artwork.visible_size_mm == (40, 18)
    contour = np.array([[1.5, 0.5], [9.5, 6.5]], dtype=float)
    assert np.array_equal(artwork.pixel_to_mm(contour), [[7.5, 1.5], [47.5, 19.5]])
    assert np.array_equal(contour, [[1.5, 0.5], [9.5, 6.5]])
    assert np.array_equal(artwork.pixel_to_mm((0, 0)), [0, 0])
    assert artwork.pixel_to_mm(np.empty((0, 2))).shape == (0, 2)


@pytest.mark.parametrize("source_width", [4, 16, 160, 960])
def test_existing_padding_is_part_of_the_canvas_without_changing_visible_scale(source_width):
    labels = np.pad(np.ones((source_width, source_width), dtype=np.uint8), 1)
    artwork = RasterArtwork(labels, ("#010101",), (80, 80))
    expected_visible = 80 * source_width / (source_width + 2)
    assert artwork.canvas_size_mm == (80, 80)
    assert artwork.visible_size_mm == pytest.approx((expected_visible, expected_visible))
    assert artwork.pixel_size_mm == (80 / (source_width + 2),) * 2
    assert artwork.labels.shape == (source_width + 2,) * 2


def test_geometry_diagnostics_are_json_ready_and_cannot_mutate_the_artwork():
    artwork = _artwork()
    diagnostics = artwork.diagnostics()
    assert json.loads(json.dumps(diagnostics)) == {
        "canvas_size_mm": [60.0, 24.0],
        "visible_bounds_mm": [7.5, 1.5, 47.5, 19.5],
        "visible_size_mm": [40.0, 18.0],
        "pixel_size_mm": [5.0, 3.0],
        "source_crop_box_px": [10, 20, 130, 100],
    }
    diagnostics["canvas_size_mm"][0] = 1
    diagnostics["source_crop_box_px"][0] = 0
    assert artwork.canvas_size_mm == (60, 24)
    assert artwork.source_crop_box_px == (10, 20, 130, 100)
    assert (
        RasterArtwork(np.ones((2, 2), dtype=int), ("#000000",), (2, 2)).diagnostics()[
            "source_crop_box_px"
        ]
        is None
    )


@pytest.mark.parametrize(
    "labels",
    [
        np.zeros((3, 3), dtype=int),
        np.ones((0, 3), dtype=int),
        np.ones((3,), dtype=int),
        np.ones((3, 3), dtype=bool),
        np.ones((3, 3), dtype=float),
        np.array([[-1, 1]], dtype=int),
        np.array([[1, 2]], dtype=int),
    ],
)
def test_invalid_label_grids_are_rejected(labels):
    with pytest.raises(ValueError):
        RasterArtwork(labels, ("#000000",), (24, 12))


@pytest.mark.parametrize(
    "palette", [None, (), ("red",), ("#fff",), ("#00000g",), (None,), ("#ff00ab", "#FF00AB")]
)
def test_invalid_or_ambiguous_palettes_are_rejected(palette):
    with pytest.raises(ValueError):
        RasterArtwork(np.ones((2, 2), dtype=int), palette, (24, 12))


@pytest.mark.parametrize(
    "size",
    [None, 24, (0, 1), (-1, 1), (1, float("inf")), (float("nan"), 1), (True, 1), (1,), ("24", 12)],
)
def test_invalid_physical_canvas_dimensions_are_rejected(size):
    with pytest.raises(ValueError):
        RasterArtwork(np.ones((2, 2), dtype=int), ("#000000",), size)


@pytest.mark.parametrize(
    "crop", [1, (-1, 0, 1, 1), (0, 0, 0, 1), (0, 5, 1, 4), (0, 0, 1.5, 2), (False, 0, 1, 1), (0, 1)]
)
def test_invalid_source_crop_boxes_are_rejected(crop):
    with pytest.raises(ValueError):
        RasterArtwork(np.ones((2, 2), dtype=int), ("#000000",), (24, 12), crop)


@pytest.mark.parametrize(
    "points",
    [1, [1], [1, 2, 3], [[1, float("nan")]], [[1, float("inf")]], ["x", "y"], [True, False]],
)
def test_invalid_contour_coordinates_are_rejected(points):
    with pytest.raises(ValueError):
        _artwork().pixel_to_mm(points)
