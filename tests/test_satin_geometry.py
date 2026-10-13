"""Fallback satin partitions preserve topology and actual needle regularity."""

from dataclasses import replace

import numpy as np
import pytest
from shapely import covers, linestrings
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from embroidery_rungs.routing import route_columns
from embroidery_rungs.stitching.params import StitchParams
from embroidery_rungs.stitching.paths import satin_points
from embroidery_rungs.stitching.planner import build_stitch_plan
from embroidery_rungs.stitching.quality import satin_crowding
from embroidery_rungs.stitching.satin_geometry import directional_columns
from embroidery_rungs.stitching.selection import _split_columns


@pytest.mark.parametrize(
    "source",
    [
        Polygon([(0, 0), (30, 0), (30, 4), (18, 4), (18, 20), (14, 20), (14, 4), (0, 4)]),
        Polygon(box(0, 0, 30, 20).exterior, [box(10, 5, 20, 15).exterior]),
    ],
    ids=["fork", "counter"],
)
def test_directional_columns_partition_branches_and_counters(source):
    params = StitchParams.for_fabric("stable", machine="brother-skitch-pp1")
    columns = directional_columns(source, 0, params.pull_compensation_mm)
    assert len(columns) == (4 if source.interiors else 3)
    sweeps = [Polygon(np.vstack([e["rail_a"], e["rail_b"][::-1]])) for e in columns]
    assert source.symmetric_difference(unary_union(sweeps)).area < 1e-4
    divided = _split_columns(columns, params.max_satin_width_mm, params)
    assert max(np.linalg.norm(e["rail_b"] - e["rail_a"], axis=1).max() for e in divided) <= 7
    plan = build_stitch_plan(route_columns(divided), params)
    assert plan.stats["fill_regions"] == plan.stats["running_regions"] == 0
    assert plan.stats["unsafe_connections"] == plan.stats["short_stitches"] == 0
    assert satin_crowding(plan, params.min_stitch_mm) == 0
    for block in plan.blocks:
        if block.kind != "satin":
            continue
        points = block.points + plan.origin_mm
        segments = linestrings(np.stack([points[:-1], points[1:]], axis=1))
        assert covers(source.buffer(0.25), segments).all()


@pytest.mark.parametrize("spacing", [0.3, 0.4, 0.5])
def test_straight_satin_keeps_requested_density_without_unnecessary_shortening(spacing):
    a, b = np.array([[0, 0], [20, 0]]), np.array([[0, 4], [20, 4]])
    params = StitchParams(satin_spacing_mm=spacing, pull_compensation_mm=0, underlay=False)
    points = satin_points(a, b, params)
    assert np.all(np.isin(points[:, 1], [0, 4]))
    assert np.diff(points[:-1:2, 0]).max() <= spacing + 0.001


def test_taper_adapts_only_when_the_next_crossing_cannot_fit_on_machine_grid():
    a = np.array([[0, 0], [10, 0], [20, 0]])
    b = np.array([[0, 0.05], [10, 3], [20, 4]])
    params = StitchParams(pull_compensation_mm=0, underlay=False)
    raw = satin_points(a, b, params)
    # A short sequence near the tip is spaced out, while the broader face keeps
    # its regular half-pitch. This avoids parity changes in machine filtering.
    assert np.linalg.norm(np.diff(raw, axis=0), axis=1).min() >= params.min_stitch_mm
    plan = build_stitch_plan([{"type": "satin", "rail_a": a, "rail_b": b}], params)
    assert satin_crowding(plan, params.min_stitch_mm) == 0
    assert plan.stats["unsafe_connections"] == plan.stats["short_stitches"] == 0
    dense = satin_points(a, b, replace(params, satin_spacing_mm=0.3))
    assert len(dense) > len(raw)
