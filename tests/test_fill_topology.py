"""Floating-point clipping must preserve counters and machine coordinates."""

import numpy as np
import pytest
from shapely.affinity import rotate
from shapely.errors import GEOSException
from shapely.geometry import LineString, Polygon
from shapely.geometry.base import BaseGeometry

from embroidery_rungs.stitching import paths as stitch_paths
from embroidery_rungs.stitching.paths import fill_paths


def test_tangent_counter_is_clipped_in_original_frame_when_rotation_is_invalid(monkeypatch):
    polygon = Polygon(
        [(0, 0), (10, 0), (10, 8), (0, 8)],
        holes=[[(2, 0), (3, 2), (2, 3), (1, 2)]],
    )
    assert polygon.is_valid
    # Reproduce a rotated contact displaced by numerical noise independently
    # of libm/GEOS versions, which may retain the exact tangent on some hosts.
    invalid = Polygon(
        polygon.exterior,
        holes=[[(2, -1e-9), (3, 2), (2, 3), (1, 2)]],
    )
    rotated = rotate(invalid, -30, origin=(0, 0))
    assert not rotated.is_valid

    def rotate_with_displaced_contact(geometry, angle, **kwargs):
        return rotated if geometry is polygon else rotate(geometry, angle, **kwargs)

    monkeypatch.setattr(stitch_paths, "rotate", rotate_with_displaced_contact)
    intersect = BaseGeometry.intersection
    calls = []

    def tracked(self, other, **kwargs):
        assert self is polygon, "Invalid rotated contours must never reach clipping"
        calls.append(other)
        return intersect(self, other, **kwargs)

    monkeypatch.setattr(BaseGeometry, "intersection", tracked)
    paths = list(fill_paths(polygon, 30, 0.4, 2.7))
    assert len(paths) > 20
    assert calls
    assert all(polygon.buffer(1e-10).covers(LineString(path)) for path in paths)
    counter = Polygon(polygon.interiors[0]).buffer(-1e-10)
    assert all(not LineString(path).intersects(counter) for path in paths)


@pytest.mark.parametrize("angle", [0, 15, 30, 45, 60, 75, 90, 105, 135])
def test_geos_retry_keeps_machine_points_and_holes(angle, monkeypatch):
    polygon = Polygon(
        [(0, 0), (10, 0), (10, 8), (0, 8)],
        holes=[[(2, 1), (4, 1), (4, 4), (2, 4)]],
    )
    expected = list(fill_paths(polygon, angle, 0.4, 2.7))
    intersect = BaseGeometry.intersection
    failures = []

    def fail_rotated(self, other, **kwargs):
        if self is not polygon:
            failures.append(True)
            raise GEOSException("TopologyException: side location conflict")
        return intersect(self, other, **kwargs)

    monkeypatch.setattr(BaseGeometry, "intersection", fail_rotated)
    actual = list(fill_paths(polygon, angle, 0.4, 2.7))
    assert len(failures) == 1
    assert len(actual) == len(expected)
    for before, after in zip(expected, actual, strict=True):
        np.testing.assert_array_equal(np.rint(before * 10), np.rint(after * 10))
        np.testing.assert_allclose(before, after, atol=1e-12, rtol=0)
        assert polygon.buffer(1e-10).covers(LineString(after))


def test_unrecoverable_row_clipping_reports_a_clear_error(monkeypatch):
    polygon = Polygon([(0, 0), (10, 0), (10, 8), (0, 8)])

    def fail(self, other, **kwargs):
        raise GEOSException("TopologyException: side location conflict")

    monkeypatch.setattr(BaseGeometry, "intersection", fail)
    with pytest.raises(ValueError, match="clipped safely to the original contours"):
        list(fill_paths(polygon, 30, 0.4, 2.7))
