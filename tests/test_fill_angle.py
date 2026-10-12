import numpy as np
import pytest
from shapely.affinity import rotate, scale, translate
from shapely.geometry import Polygon, box

from embroidery_rungs.stitching.params import StitchParams
from embroidery_rungs.stitching.selection import _fill_angle


@pytest.mark.parametrize("factor", [0.04, 0.75, 1.0, 1.175, 20.0])
@pytest.mark.parametrize("offset", [(0, 0), (0.3, 0.5), (100_000, -100_000)])
def test_fill_direction_is_independent_of_position_size_and_stitch_grid(factor, offset):
    source = rotate(Polygon([(0, 0), (25, 15), (22, 20), (-3, 5)]), 13, origin=(0, 0))
    changed = translate(scale(source, xfact=factor, yfact=factor, origin=(0, 0)), *offset)
    params = StitchParams()
    assert _fill_angle(changed, params) == _fill_angle(source, params) == 45


@pytest.mark.parametrize("angle", [0, 30, 60, 90, 180, 270])
def test_fill_direction_follows_rotated_anisotropic_regions(angle):
    source = rotate(box(-15, -3, 15, 3), 30, origin=(0, 0))
    assert _fill_angle(rotate(source, angle, origin=(0, 0)), StitchParams()) == (30 + angle) % 180


@pytest.mark.parametrize("axis", [(1, -1), (-1, 1), (-1, -1)])
def test_fill_direction_follows_reflected_anisotropic_regions(axis):
    source = rotate(box(-15, -3, 15, 3), 30, origin=(0, 0))
    reflected = scale(source, xfact=axis[0], yfact=axis[1], origin=(0, 0))
    expected = 30 if axis[0] == axis[1] else 150
    assert _fill_angle(reflected, StitchParams()) == expected


def test_holes_subtract_from_filled_area_moments_regardless_of_winding():
    boundary = list(box(-20, -20, 20, 20).exterior.coords)
    hole = list(box(-7, -18, 7, 18).exterior.coords)
    params = StitchParams(fill_angle_deg=45)
    assert _fill_angle(Polygon(boundary), params) == 45
    assert _fill_angle(Polygon(boundary, [hole]), params) == 0
    assert _fill_angle(Polygon(boundary[::-1], [hole[::-1]]), params) == 0


@pytest.mark.parametrize("noise", [0, 0.001, 0.1, 0.3])
def test_near_isotropic_regions_keep_configured_direction(noise):
    source = Polygon([(0, 0), (20 + noise, 0), (20, 20 - noise), (0, 20)])
    params = StitchParams(fill_angle_deg=37)
    assert _fill_angle(source, params) == 37
    assert _fill_angle(rotate(source, 60), params) == 37


def test_manual_direction_is_preserved_exactly():
    params = StitchParams(auto_fill_angle=False, fill_angle_deg=-63)
    assert _fill_angle(box(0, 0, 30, 3), params) == -63


def test_contour_start_vertex_and_direction_do_not_change_fill_angle():
    source = rotate(Polygon([(0, 0), (18, 0), (23, 4), (15, 9), (0, 6)]), 28)
    coords = np.asarray(source.exterior.coords)[:-1]
    reference = _fill_angle(source, StitchParams())
    for start in range(len(coords)):
        changed = np.roll(coords, start, axis=0)
        assert _fill_angle(Polygon(changed), StitchParams()) == reference
        assert _fill_angle(Polygon(changed[::-1]), StitchParams()) == reference
