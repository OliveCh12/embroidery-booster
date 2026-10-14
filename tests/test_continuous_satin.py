"""Optional continuous rails preserve legacy quality and machine topology."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from shapely import covers, linestrings
from shapely.geometry import Point

from embroidery_rungs.image_processor import compute_medial_axis
from embroidery_rungs.stitching import consistency, planner, rails
from embroidery_rungs.stitching.digitizer import digitize
from embroidery_rungs.stitching.params import StitchParams
from embroidery_rungs.stitching.paths import _rail_samples, satin_points
from embroidery_rungs.stitching.planner import (
    CandidateGeometryError,
    StitchBlock,
    build_stitch_plan,
)
from embroidery_rungs.stitching.quality import satin_crowding
from embroidery_rungs.stitching.satin_geometry import column_polygon
from embroidery_rungs.stitching.underlay import satin_underlay
from embroidery_rungs.svg_manager import load_svg_paths

ELLIPSE = '<ellipse cx="40" cy="35" rx="20" ry="10" fill="none" stroke="black" stroke-width="4"/>'
FINE_ELLIPSE = (
    '<ellipse cx="40" cy="35" rx="12" ry="6" fill="none" stroke="black" stroke-width=".8"/>'
)
RING = '<circle cx="40" cy="35" r="20" fill="none" stroke="black" stroke-width="4"/>'
FINE_RING = '<circle cx="40" cy="35" r="4" fill="none" stroke="black" stroke-width=".8"/>'
CURVE = (
    '<path d="M10 45 C10 5 40 5 40 35 S70 65 70 25" fill="none" stroke="black" stroke-width="5"/>'
)


def document(tmp_path, content):
    path = tmp_path / "continuous.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" '
        f'viewBox="0 0 100 100">{content}</svg>'
    )
    return load_svg_paths(path)[0]


def legacy_plan(svg, params, monkeypatch):
    with monkeypatch.context() as context:
        context.setattr(consistency, "_promote_continuous", lambda *args: False)
        return digitize(svg, params)[0]


def circle_rails():
    angles = np.linspace(0, 2 * np.pi, 129)
    directions = np.column_stack([np.cos(angles), np.sin(angles)])
    directions[-1] = directions[0]
    return directions * 10, directions * 6


def test_periodic_rails_preserve_counter_and_one_closing_crossing():
    a, b = circle_rails()
    polygon = column_polygon(a, b, closed=True)
    assert polygon.is_valid and len(polygon.interiors) == 1
    assert not polygon.covers(Point(0, 0))
    params = StitchParams(pull_compensation_mm=0, underlay=False)
    sampled = _rail_samples(a, b, params.satin_spacing_mm / 2, closed=True)
    assert len(sampled[0]) % 2 == 0
    assert np.linalg.norm(sampled[0][0] - sampled[0][-1]) > 0
    points = satin_points(a, b, params, closed=True)
    np.testing.assert_array_equal(points[0], points[-1])
    assert len(points) == len(sampled[0]) + 1
    supports = satin_underlay(a, b, params, edge_walk=False, zigzag=True, closed=True)
    for support in supports:
        np.testing.assert_array_equal(support[0], support[-1])
    plan = build_stitch_plan([dict(type="satin", rail_a=a, rail_b=b, closed=True)], params)
    top = [block for block in plan.blocks if block.kind == "satin"]
    assert len(top) == 1 and top[0].closed
    np.testing.assert_array_equal(top[0].points[0], top[0].points[-1])
    assert satin_crowding(plan, params.min_stitch_mm) == 0
    world = top[0].points + plan.origin_mm
    assert covers(
        polygon.buffer(0.08), linestrings(np.stack([world[:-1], world[1:]], axis=1))
    ).all()
    with pytest.raises(ValueError, match="budget"):
        _rail_samples(a, b, params.satin_spacing_mm / 2, len(sampled[0]), closed=True)
    with pytest.raises(ValueError, match="loops"):
        satin_points(a[:-1], b[:-1], params, closed=True)


def test_closed_crowding_audits_seam_without_counting_exact_closure():
    angles = np.arange(20) * 2 * np.pi / 20
    points = np.column_stack([np.cos(angles), np.sin(angles)]) * 10
    points[-2] = points[0] + [0.1, 0]
    closed = np.vstack([points, points[0]])
    block = StitchBlock("satin", closed, 0)
    plan = SimpleNamespace(blocks=[block])
    assert satin_crowding(plan, 0.3) == 0
    block.closed = True
    assert satin_crowding(plan, 0.3) > 0
    ordinary = np.column_stack([np.cos(angles), np.sin(angles)]) * 10
    block.points = np.vstack([ordinary, ordinary[0]])
    assert satin_crowding(plan, 0.3) == 0


@pytest.mark.parametrize("content,closed", [(ELLIPSE, True), (FINE_ELLIPSE, True), (CURVE, False)])
def test_continuous_promotion_preserves_final_quality_with_fewer_commands(
    tmp_path, monkeypatch, content, closed
):
    svg = document(tmp_path, content)
    params = StitchParams.for_fabric("stable", machine="brother-skitch-pp1")
    old = legacy_plan(svg, params, monkeypatch)
    plan, _ = digitize(svg, params)
    assert plan.decisions[0]["reason"] == "complete_continuous_columns"
    old_top = [b for b in old.blocks if b.kind == "satin"]
    top = [b for b in plan.blocks if b.kind == "satin"]
    assert len(top) == 1 < len(old_top)
    assert top[0].closed == closed
    if closed:
        np.testing.assert_array_equal(top[0].points[0], top[0].points[-1])
    assert len(plan.commands) <= len(old.commands)
    assert plan.stats["coverage"] >= old.stats["coverage"] - 0.005
    area = plan.decisions[0]["area_mm2"]
    assert plan.stats["spill_mm2"] <= old.stats["spill_mm2"] + max(0.25, 0.02 * area)
    assert plan.stats["trims"] < old.stats["trims"]
    assert plan.stats["underlay_stitches"] > 0
    assert plan.stats["unsafe_connections"] == plan.stats["short_stitches"] == 0
    assert plan.stats["crowded_satin_penetrations"] == 0
    assert plan.stats["structural_coverage"] >= 0.999


@pytest.mark.parametrize("content", [RING, FINE_RING])
def test_degraded_closed_ring_keeps_exact_legacy_commands(tmp_path, monkeypatch, content):
    svg = document(tmp_path, content)
    params = StitchParams.for_fabric("stable", machine="brother-skitch-pp1")
    old = legacy_plan(svg, params, monkeypatch)
    plan, _ = digitize(svg, params)
    assert plan.commands == old.commands
    assert plan.decisions == old.decisions
    assert sum(b.kind == "satin" for b in plan.blocks) == 5


def test_existing_fill_and_explicit_fill_do_not_promote(tmp_path, monkeypatch):
    svg = document(tmp_path, f'<g transform="translate(5.1,5.2) scale(.75)">{FINE_RING}</g>')
    params = StitchParams.for_fabric("stable", machine="brother-skitch-pp1")
    old = legacy_plan(svg, params, monkeypatch)
    plan, _ = digitize(svg, params)
    assert {d["method"] for d in plan.decisions} == {"fill"}
    assert plan.commands == old.commands
    with monkeypatch.context() as context:

        def forbidden(*args, **kwargs):
            raise AssertionError("Explicit fill must not compute MAT rails.")

        context.setattr(consistency, "compute_medial_axis", forbidden)
        explicit, _ = digitize(svg, replace(params, stitch_type="fill"))
    assert {d["method"] for d in explicit.decisions} == {"fill"}


def test_optional_budget_failure_restores_valid_legacy_plan(tmp_path, monkeypatch):
    svg = document(tmp_path, FINE_RING)
    params = StitchParams.for_fabric("stable", machine="brother-skitch-pp1", satin_spacing_mm=0.3)
    old = legacy_plan(svg, params, monkeypatch)
    params = replace(params, max_stitches=len(old.commands))
    original = consistency.build_stitch_plan
    calls = 0

    def reject_closed(elements, *args, **kwargs):
        nonlocal calls
        if any(e.get("closed") for e in elements):
            calls += 1
            raise ValueError("Stitch budget exceeded.")
        return original(elements, *args, **kwargs)

    monkeypatch.setattr(consistency, "build_stitch_plan", reject_closed)
    plan, _ = digitize(svg, params)
    assert calls == 1
    assert plan.commands == old.commands
    assert plan.decisions == old.decisions


def test_equivalent_cohort_rolls_back_every_member_on_one_failed_trial(tmp_path, monkeypatch):
    source = '<g fill="none" stroke="black" stroke-width=".8"><ellipse cx="22" cy="35" rx="14" ry="7"/><ellipse cx="58" cy="35" rx="14" ry="7"/></g>'
    svg = document(tmp_path, source)
    params = StitchParams.for_fabric("stable", machine="brother-skitch-pp1")
    old = legacy_plan(svg, params, monkeypatch)
    original = consistency._audit_members
    attempted = []

    def reject_member(members, *args):
        passed = original(members, *args)
        if any(e.get("closed") for m in members for e in m.elements):
            attempted.append(len(members))
            members[-1].metrics["coverage"] -= 0.1
        return passed

    monkeypatch.setattr(consistency, "_audit_members", reject_member)
    plan, _ = digitize(svg, params)
    assert attempted == [2]
    assert plan.commands == old.commands
    assert plan.decisions == old.decisions
    assert all(not b.closed for b in plan.blocks if b.kind == "satin")


def test_invalid_rung_is_never_bridged_into_continuous_column(monkeypatch):
    y, x = np.mgrid[:120, :120]
    radius = np.hypot(x - 60, y - 60)
    mask = (radius >= 30) & (radius <= 45)
    skeleton, distance = compute_medial_axis(mask)
    candidates = []
    legacy = rails.generate_columns(skeleton, distance, mask, continuous_candidates=candidates)
    assert len(legacy) > len(candidates) == 1
    original = rails._crossing_filter

    def missing_rung(items):
        return [
            (a, b, centers, valid[valid != len(a) // 2]) for a, b, centers, valid in original(items)
        ]

    monkeypatch.setattr(rails, "_crossing_filter", missing_rung)
    candidates = []
    rails.generate_columns(skeleton, distance, mask, continuous_candidates=candidates)
    assert candidates == []


def test_closed_machine_filter_cannot_silently_drop_closure(monkeypatch):
    a, b = circle_rails()
    original = planner._machine_points

    def lose_closure(points, *args):
        result = original(points, *args)
        return result[:-1] if np.linalg.norm(result[0] - result[-1]) < 1e-8 else result

    monkeypatch.setattr(planner, "_machine_points", lose_closure)
    with pytest.raises(CandidateGeometryError, match="closure"):
        build_stitch_plan(
            [dict(type="satin", rail_a=a, rail_b=b, closed=True)], StitchParams(underlay=False)
        )


def test_continuous_candidates_cannot_increase_assembled_command_budget(monkeypatch):
    a = np.array([[0.0, 0.0], [10.0, 0.0]])
    b = a + [0, 4]
    params = StitchParams()
    old_metrics = dict(
        satin_blocks=5, command_count=100, coverage=0.9, spill_mm2=1, underlay_stitches=20
    )
    member = consistency.RegionCandidate(
        region=SimpleNamespace(frame=None),
        elements=[dict(type="satin", rail_a=a, rail_b=b, underlay=True)],
        decision={"reason": "complete_regular_column"},
        polygons=[column_polygon(a, b)],
        params=params,
        metrics=old_metrics,
        continuous_elements=(dict(type="satin", rail_a=a, rail_b=b, closed=False),),
    )
    old_elements = member.elements

    def audit(trials, *args):
        trials[0].metrics = dict(
            old_metrics,
            satin_blocks=1,
            command_count=101,
            unsafe_connections=0,
            omitted_regions=0,
            short_stitches=0,
        )
        return True

    monkeypatch.setattr(consistency, "_audit_members", audit)
    assert not consistency._promote_continuous([member], params, None, None, 12)
    assert member.elements is old_elements and member.metrics is old_metrics
    assert member.decision["reason"] == "complete_regular_column"


def test_equivalent_candidates_require_same_column_topology_before_audit(monkeypatch):
    members = [
        SimpleNamespace(continuous_elements=(dict(closed=closed),)) for closed in (False, True)
    ]

    def forbidden(*args):
        raise AssertionError("Mismatching topology must not reach the machine audit.")

    monkeypatch.setattr(consistency, "_audit_members", forbidden)
    assert not consistency._promote_continuous(members, StitchParams(), None, None, 12)
