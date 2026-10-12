"""Canonical component frames preserve geometry, topology and real hoop orientation."""

import json
from pathlib import Path

import numpy as np
import pyembroidery as pe
import pytest
from scipy.ndimage import label
from shapely import intersects, linestrings
from shapely.geometry import Polygon, box
from svgelements import Matrix

from embroidery_rungs import StitchParams, generate
from embroidery_rungs.stitching.regions import canonical_regions, design_symmetries, orientations
from embroidery_rungs.stitching.selection import mask_polygons
from embroidery_rungs.svg_manager import UNITS_PER_MM


def _asymmetric_shape():
    mask = np.zeros((30, 46), dtype=bool)
    mask[:, :8] = True
    mask[:8, :] = True
    return mask


@pytest.mark.parametrize("variant", range(8))
def test_d4_canonical_mask_and_frame_reconstruct_original_pixels(variant):
    source = list(orientations(_asymmetric_shape()))[variant][0]
    canvas = np.pad(source, ((7, 11), (13, 5)))
    original = canvas.copy()
    transform = Matrix(2.5, 0, 0, 2.5, 11, -9)
    regions = canonical_regions(canvas, transform)
    assert len(regions) == 1
    region = regions[0]
    reference = canonical_regions(_asymmetric_shape(), transform)[0]
    assert np.array_equal(region.mask, reference.mask)
    assert np.array_equal(canvas, original)
    assert np.array_equal(region.source_mask, source)

    scale = UNITS_PER_MM * transform.a
    local = np.argwhere(region.mask)[:, ::-1] / scale
    world = region.frame.to_world(local)
    np.testing.assert_allclose(region.frame.to_local(world), local, atol=1e-12)
    pixels = world * UNITS_PER_MM @ np.array(
        [[transform.a, transform.b], [transform.c, transform.d]]
    ) + [transform.e, transform.f]
    np.testing.assert_allclose(pixels, np.rint(pixels), atol=1e-10)
    pixels = np.rint(pixels).astype(int)
    reconstructed = np.zeros_like(canvas)
    reconstructed[pixels[:, 1], pixels[:, 0]] = True
    assert np.array_equal(reconstructed, canvas)


def test_rigid_equivalents_share_group_but_keep_their_original_masks():
    canvas = np.zeros((160, 260), dtype=bool)
    for index, (shape, _) in enumerate(orientations(_asymmetric_shape())):
        row, column = 10 + (index // 4) * 75, 10 + (index % 4) * 60
        canvas[row : row + shape.shape[0], column : column + shape.shape[1]] = shape
    original = canvas.copy()
    regions = canonical_regions(canvas, Matrix.scale(2))
    assert len(regions) == 8
    assert len({region.group for region in regions}) == 1
    assert all(np.array_equal(region.mask, regions[0].mask) for region in regions)
    assert all(np.array_equal(region.source_mask, canvas[region.bounds]) for region in regions)
    assert np.array_equal(canvas, original)


def test_equal_area_and_bounds_do_not_group_geometrically_different_regions():
    left = _asymmetric_shape()
    right = left.copy()
    right[4:8, 18:28] = False
    right[18:28, 8:12] = True
    assert left.shape == right.shape and left.sum() == right.sum()
    assert label(left)[1] == label(right)[1] == 1
    canvas = np.zeros((50, 120), dtype=bool)
    canvas[10:40, 5:51], canvas[10:40, 65:111] = left, right
    regions = canonical_regions(canvas, Matrix.scale(2))
    assert len(regions) == 2
    assert regions[0].group != regions[1].group


def test_small_counter_prevents_matching_with_a_solid_region():
    solid = np.ones((60, 60), dtype=bool)
    counter = solid.copy()
    counter[29:31, 29:31] = False
    # The four-pixel hole fits area/noise tolerances, but changes the topology.
    canvas = np.zeros((80, 150), dtype=bool)
    canvas[10:70, 5:65], canvas[10:70, 85:145] = solid, counter
    regions = canonical_regions(canvas, Matrix.scale(2))
    assert len(regions) == 2
    assert regions[0].group != regions[1].group
    assert regions[0].mask.all()
    assert np.count_nonzero(~regions[1].mask) == 4
    assert label(~np.pad(regions[1].mask, 1))[1] == 2


def test_diagonal_open_channel_is_not_equivalent_to_an_enclosed_counter():
    enclosed = np.ones((20, 20), dtype=bool)
    opened = enclosed.copy()
    for index in range(1, 11):
        enclosed[index, index] = False
    enclosed[0, 19] = False
    for index in range(11):
        opened[index, index] = False
    assert enclosed.sum() == opened.sum()
    assert label(enclosed)[1] == label(opened)[1] == 1
    # Four-connected foreground needs eight-connected background: the channel
    # reaches the outside by diagonal contacts, unlike the enclosed counter.
    background = np.ones((3, 3))
    assert label(~np.pad(enclosed, 2), structure=background)[1] == 2
    assert label(~np.pad(opened, 2), structure=background)[1] == 1
    enclosed_polygons = mask_polygons(np.pad(enclosed, 2), Matrix())
    opened_polygons = mask_polygons(np.pad(opened, 2), Matrix())
    assert sum(len(p.interiors) for p in enclosed_polygons) == 1
    assert sum(len(p.interiors) for p in opened_polygons) == 0
    canvas = np.zeros((30, 60), dtype=bool)
    canvas[5:25, 5:25], canvas[5:25, 35:55] = enclosed, opened
    regions = canonical_regions(canvas, Matrix())
    assert len(regions) == 2
    assert regions[0].group != regions[1].group


@pytest.mark.parametrize("variant", range(8))
def test_frame_maps_polygon_counters_and_angles_without_distortion(variant):
    shape = list(orientations(_asymmetric_shape()))[variant][0]
    frame = canonical_regions(np.pad(shape, 4), Matrix(3, 0, 0, 3, 8, -12))[0].frame
    local = Polygon(box(0, 0, 5, 3).exterior, [box(1, 1, 2, 2).exterior])
    actual = frame.geometry_to_world(local)
    expected = Polygon(
        frame.to_world(local.exterior.coords),
        [frame.to_world(ring.coords) for ring in local.interiors],
    )
    assert actual.is_valid
    assert len(actual.interiors) == 1
    assert actual.area == pytest.approx(local.area)
    assert actual.symmetric_difference(expected).area < 1e-12
    roundtrip = Polygon(
        frame.to_local(actual.exterior.coords),
        [frame.to_local(ring.coords) for ring in actual.interiors],
    )
    assert roundtrip.symmetric_difference(local).area < 1e-12
    for angle in (0, 27, 45, 90, 169):
        returned = frame.angle_to_local(frame.angle_to_world(angle))
        difference = abs(angle - returned)
        assert min(difference, 180 - difference) < 1e-6


def test_corner_only_contacts_remain_two_four_connected_regions():
    mask = np.zeros((12, 12), dtype=bool)
    mask[2:6, 2:6] = True
    mask[6:10, 6:10] = True
    assert label(mask, structure=np.ones((3, 3)))[1] == 1
    regions = canonical_regions(mask, Matrix())
    assert len(regions) == 2
    assert all(region.mask.sum() == 16 for region in regions)


def test_colored_rotational_design_is_not_forced_to_be_a_mirror():
    labels = np.ones((24, 40), dtype=np.uint8)
    labels[2:9, 3:19] = labels[-9:-2, -19:-3] = 2
    labels[2:9, 24:36] = labels[-9:-2, -36:-24] = 3
    assert np.array_equal(labels, labels[::-1, ::-1])
    assert not np.array_equal(labels, labels[:, ::-1])
    assert not np.array_equal(labels, labels[::-1])
    symmetries = design_symmetries(labels)
    assert len(symmetries) == 1
    assert np.array_equal(symmetries[0], -np.eye(2))


@pytest.mark.parametrize("vertical", [False, True], ids=["wide-hoop", "tall-hoop"])
def test_canonical_rotation_respects_global_non_square_hoop_and_counter(tmp_path, vertical):
    outer, counter = (box(10, 11, 135, 19), box(60, 13, 85, 17))
    if vertical:
        outer, counter = (box(11, 10, 19, 135), box(13, 60, 17, 85))
    width, height = (30, 150) if vertical else (150, 30)
    params = StitchParams.for_fabric(
        "stable", thread_weight=40, hoop_width_mm=width, hoop_height_mm=height
    )

    def rectangle_path(rectangle):
        x0, y0, x1, y1 = rectangle.bounds
        return f"M{x0} {y0}H{x1}V{y1}H{x0}Z"

    source = tmp_path / "non-square.svg"
    source.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" '
        f'height="{height}mm" viewBox="0 0 {width} {height}">'
        f'<path fill-rule="evenodd" d="{rectangle_path(outer)} {rectangle_path(counter)}"/>'
        "</svg>"
    )
    direct = generate(source, tmp_path / "valid", method="direct", stitch_params=params).direct
    assert direct.stats["structural_coverage"] >= 0.999
    assert direct.stats["largest_gap_mm2"] <= 0.05
    assert direct.stats["omitted_regions"] == 0
    assert direct.stats["width_mm"] <= width and direct.stats["height_mm"] <= height
    assert direct.stats["height_mm" if vertical else "width_mm"] > 120

    data = json.loads(Path(direct.plan_path).read_text())
    commands = np.asarray(data["commands"])
    sewn = (commands[:-1, 2] == pe.STITCH) & (commands[1:, 2] == pe.STITCH)
    segments = (
        np.stack([commands[:-1, :2], commands[1:, :2]], axis=1)[sewn] / 10 + data["origin_mm"]
    )
    assert not intersects(linestrings(segments), counter.buffer(-0.2)).any()
    actual = np.asarray(pe.read(direct.pes_path).stitches)
    assert np.array_equal(
        actual[(actual[:, 2].astype(int) & pe.COMMAND_MASK) == pe.STITCH, :2],
        commands[commands[:, 2] == pe.STITCH, :2],
    )

    wrong_orientation = StitchParams.for_fabric(
        "stable", thread_weight=40, hoop_width_mm=height, hoop_height_mm=width
    )
    with pytest.raises(ValueError, match="hoop"):
        generate(source, tmp_path / "invalid", method="direct", stitch_params=wrong_orientation)
    assert not list((tmp_path / "invalid").glob("*.pes"))
