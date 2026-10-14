"""Deferred narrow satin is compared to the fill actually selected by policy."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from shapely.geometry import box

from embroidery_rungs.stitching import consistency, selection
from embroidery_rungs.stitching.params import StitchParams
from embroidery_rungs.stitching.regions import RegionFrame


def metrics(**overrides):
    return (
        dict(
            coverage=0.9,
            structural_coverage=1.0,
            largest_gap_mm2=0.0,
            uncovered_max_mm=0.0,
            spill_mm2=4.0,
            satin_blocks=0,
            command_count=100,
            underlay_stitches=10,
            unsafe_connections=0,
            omitted_regions=0,
            short_stitches=0,
            crowded_satin_penetrations=0,
        )
        | overrides
    )


def member(component=1, *, angle=45, kind="stroke"):
    a = np.array([[0.0, 0.0], [20.0, 0.0]])
    b = a + [0, 4]
    source = box(0, 0, 20, 4)
    element = dict(
        type="satin",
        rail_a=a,
        rail_b=b,
        allowed_area=source.buffer(0.23),
        directional_satin_angle_deg=angle,
    )
    option = selection._satin_option([element], metrics(), "directional", angle)
    frame = RegionFrame(np.eye(2), np.array([component * 25.0, 0.0]))
    return consistency.RegionCandidate(
        region=SimpleNamespace(component=component, frame=frame),
        elements=[dict(type="fill", polygon=source, fill_angle_deg=90, compensation=0.15)],
        decision=dict(
            method="fill",
            reason="satin_fidelity_regression",
            shape_profile=dict(kind=kind, narrow=True),
            candidates=dict(fill_reference=metrics(coverage=0.95, spill_mm2=1)),
        ),
        polygons=[source],
        params=StitchParams(),
        metrics=metrics(),
        satin_options=(option,),
    )


def test_promotion_compares_actual_policy_fill_without_tracing_it_again(monkeypatch):
    original = member()
    reference = original.metrics.copy()
    calls = []

    def audit(trials, method, *args):
        assert method == "satin"
        calls.append(method)
        trials[0].metrics = metrics(coverage=0.98, spill_mm2=5, command_count=90, satin_blocks=1)
        return True

    monkeypatch.setattr(consistency, "_audit_members", audit)
    profile = consistency._promote_fill_satin([original], StitchParams(), None, None, 12)
    assert profile == "center+zigzag"
    assert calls == ["satin"]
    assert original.decision["method"] == "satin"
    assert original.decision["reason"] == "complete_fidelity_columns"
    assert original.decision["candidates"]["fill_policy_reference"] == reference
    comparison = original.decision["candidates"]["fill_policy_comparison"]
    assert comparison == dict(coverage_delta=0.08, spill_delta_mm2=1.0, accepted=True)
    assert original.decision["canonical_satin_angle_deg"] == 45
    assert original.elements[0]["frame"] is original.region.frame
    assert original.elements[0]["underlay"] and original.elements[0]["underlay_zigzag"]
    saved = original.satin_options[0]["elements"][0]["rail_a"].copy()
    original.elements[0]["rail_a"][0] += [1, 1]
    np.testing.assert_array_equal(original.satin_options[0]["elements"][0]["rail_a"], saved)


@pytest.mark.parametrize(
    "change",
    [
        dict(coverage=0.894),
        dict(spill_mm2=5.61),
        dict(command_count=101),
        dict(unsafe_connections=1),
        dict(omitted_regions=1),
        dict(short_stitches=1),
        dict(crowded_satin_penetrations=1),
        dict(underlay_stitches=0),
    ],
)
def test_one_failed_cohort_member_retains_every_fill_member(monkeypatch, change):
    members = [member(1), member(2)]
    snapshots = [(m.elements, m.metrics, m.decision) for m in members]

    def audit(trials, *args):
        for trial in trials:
            trial.metrics = metrics(coverage=0.98, spill_mm2=5, command_count=90, satin_blocks=1)
        trials[-1].metrics.update(change)
        return True

    monkeypatch.setattr(consistency, "_audit_members", audit)
    assert consistency._promote_fill_satin(members, StitchParams(), None, None, 12) is None
    for m, (elements, measured, decision) in zip(members, snapshots, strict=True):
        assert m.elements is elements and m.metrics is measured and m.decision is decision
        assert m.decision["method"] == "fill"


@pytest.mark.parametrize(
    "failure", ["direction", "count", "closed", "compact", "wide", "preferred"]
)
def test_incompatible_or_ineligible_options_do_not_reach_audit(monkeypatch, failure):
    members = [member(1), member(2)]
    params = StitchParams()
    if failure == "direction":
        members[-1] = member(2, angle=90)
    elif failure == "count":
        option = members[-1].satin_options[0]
        option["elements"] = option["elements"] * 2
    elif failure == "closed":
        members[-1].satin_options[0]["elements"][0]["closed"] = True
    elif failure == "compact":
        members[-1].decision["shape_profile"]["kind"] = "compact"
    elif failure == "wide":
        members[-1].decision["shape_profile"]["narrow"] = False
    else:
        params = replace(params, auto_strategy="satin_preferred")

    def forbidden(*args):
        raise AssertionError("Incompatible candidates must retain the current fill.")

    monkeypatch.setattr(consistency, "_audit_members", forbidden)
    assert consistency._promote_fill_satin(members, params, None, None, 12) is None


def test_optional_budget_failure_preserves_valid_fill(monkeypatch):
    original = member()
    saved = (original.elements, original.metrics, original.decision)

    def reject(*args):
        raise ValueError("Stitch budget exceeded.")

    monkeypatch.setattr(consistency, "_audit_members", reject)
    assert consistency._promote_fill_satin([original], StitchParams(), None, None, 12) is None
    assert (original.elements, original.metrics, original.decision) == saved


def test_next_common_option_can_succeed_after_first_real_fill_regression(monkeypatch):
    members = [member(1, angle=0), member(2, angle=0)]
    for m in members:
        m.satin_options += member(m.region.component, angle=45).satin_options
    calls = []

    def audit(trials, *args):
        angle = trials[0].elements[0].get("directional_satin_angle_deg")
        calls.append(angle)
        for trial in trials:
            trial.metrics = metrics(
                coverage=0.98, spill_mm2=7 if len(calls) == 1 else 5, command_count=90
            )
        return True

    monkeypatch.setattr(consistency, "_audit_members", audit)
    assert (
        consistency._promote_fill_satin(members, StitchParams(), None, None, 12) == "center+zigzag"
    )
    assert len(calls) == 2
    assert all(m.decision["canonical_satin_angle_deg"] == 45 for m in members)


@pytest.mark.parametrize(
    "reference,proposed,accepted", [(1, 2, True), (2, 3, False), (3, 3, True), (3, 4, False)]
)
def test_fill_promotion_does_not_add_top_stacks_beyond_two_column_joins(
    monkeypatch, reference, proposed, accepted
):
    members = [member(1), member(2)]
    for m in members:
        m.metrics["max_top_penetration_multiplicity"] = reference
    snapshots = [(m.elements, m.metrics) for m in members]

    def audit(trials, *args):
        for trial in trials:
            trial.metrics = metrics(
                coverage=0.98,
                spill_mm2=5,
                command_count=90,
                satin_blocks=1,
                max_top_penetration_multiplicity=reference,
            )
        trials[-1].metrics["max_top_penetration_multiplicity"] = proposed
        return True

    monkeypatch.setattr(consistency, "_audit_members", audit)
    profile = consistency._promote_fill_satin(members, StitchParams(), None, None, 12)
    if accepted:
        assert profile == "center+zigzag"
        assert all(m.decision["reason"] == "complete_fidelity_columns" for m in members)
    else:
        assert profile is None
        for m, (elements, measured) in zip(members, snapshots, strict=True):
            assert m.elements is elements and m.metrics is measured
            assert m.decision["method"] == "fill"
            assert m.decision["reason"] == "satin_intercolumn_repeats"
            assert m.decision["candidates"]["intercolumn_repeat_comparison"]["accepted"] is False
        assert members[-1].decision["candidates"]["intercolumn_repeat_comparison"] == dict(
            reference_max_multiplicity=reference,
            candidate_max_multiplicity=proposed,
            accepted=False,
        )


def test_later_option_success_does_not_keep_intercolumn_repeat_rejection(monkeypatch):
    original = member(angle=0)
    original.metrics["max_top_penetration_multiplicity"] = 2
    original.satin_options += member(angle=45).satin_options
    calls = []

    def audit(trials, *args):
        calls.append(True)
        trials[0].metrics = metrics(
            coverage=0.98,
            spill_mm2=5,
            command_count=90,
            satin_blocks=1,
            max_top_penetration_multiplicity=3 if len(calls) == 1 else 2,
        )
        return True

    monkeypatch.setattr(consistency, "_audit_members", audit)
    assert (
        consistency._promote_fill_satin([original], StitchParams(), None, None, 12)
        == "center+zigzag"
    )
    assert len(calls) == 2
    assert original.decision["reason"] == "complete_fidelity_columns"
    assert "intercolumn_repeat_comparison" not in original.decision["candidates"]


def test_curved_letter_uses_actual_final_fill_and_preserves_broad_body(tmp_path, monkeypatch):
    from embroidery_rungs.stitching.digitizer import digitize
    from embroidery_rungs.svg_manager import load_svg_paths

    path = tmp_path / "letter.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 100 100">'
        '<g fill="#111111"><rect x="1" y="15" width="45" height="45"/>'
        '<g transform="translate(50,28) scale(.4)"><path d="M10 15L16 13L13 33'
        "C12 42 17 43 20 36L23 12L29 10L26 33C25 39 26 41 30 38L29 43"
        'C24 47 19 47 19 42C14 49 6 47 7 38Z"/></g></g></svg>'
    )
    svg = load_svg_paths(path)[0]
    params = StitchParams.for_fabric("stable", machine="brother-skitch-pp1")
    with monkeypatch.context() as context:
        context.setattr(consistency, "_promote_fill_satin", lambda *args: None)
        baseline, _ = digitize(svg, params)
    captured = []
    policy = consistency._color_policy

    def capture(groups, *args):
        captured.extend(m for members in groups.values() for m in members)
        return policy(groups, *args)

    monkeypatch.setattr(consistency, "_color_policy", capture)
    plan, _ = digitize(svg, params)
    old_letter = next(d for d in baseline.decisions if d["shape_profile"]["kind"] == "stroke")
    letter = next(d for d in plan.decisions if d["shape_profile"]["kind"] == "stroke")
    assert old_letter["method"] == "fill"
    assert letter["method"] == "satin" and letter["reason"] == "complete_fidelity_columns"
    assert letter["strategy_scope"] == "region"
    actual = letter["actual_top_metrics"]
    reference = letter["candidates"]["fill_policy_reference"]
    assert reference == old_letter["actual_top_metrics"]
    assert actual["coverage"] >= reference["coverage"] - 0.005
    assert actual["spill_mm2"] <= reference["spill_mm2"] + max(0.25, 0.02 * letter["area_mm2"])
    assert actual["command_count"] <= reference["command_count"]
    assert letter["candidates"]["fill_policy_comparison"]["accepted"]
    assert letter["candidates"]["fill_comparison"]["accepted"] is False
    assert plan.stats["coverage"] >= baseline.stats["coverage"]
    assert plan.stats["spill_mm2"] <= baseline.stats["spill_mm2"]
    assert len(plan.commands) <= len(baseline.commands)
    assert plan.stats["unsafe_connections"] == plan.stats["short_stitches"] == 0
    assert plan.stats["crowded_satin_penetrations"] == 0
    body = next(d for d in plan.decisions if d["shape_profile"]["kind"] == "wide_surface")
    old_body = next(d for d in baseline.decisions if d["shape_profile"]["kind"] == "wide_surface")
    assert body == old_body
    assert all(m.satin_options == () for m in captured)


def test_looped_letter_keeps_fill_when_directional_satin_adds_three_way_top_stack(tmp_path):
    from embroidery_rungs.stitching.digitizer import digitize
    from embroidery_rungs.stitching.quality import max_top_penetration_multiplicity
    from embroidery_rungs.svg_manager import load_svg_paths

    path = tmp_path / "looped-letter.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="80mm" viewBox="0 0 80 80">'
        '<g fill="none" stroke="#111111" stroke-linecap="round" stroke-linejoin="round">'
        '<ellipse cx="30" cy="33" rx="12" ry="14" stroke-width="4"/>'
        '<path d="M42 19 V56 C42 71 20 70 18 59" stroke-width="4"/></g></svg>'
    )
    params = StitchParams.for_fabric("stable", machine="brother-skitch-pp1", stabilizer="cutaway")
    plan, _ = digitize(load_svg_paths(path)[0], params)
    decision = plan.decisions[0]
    assert decision["method"] == "fill"
    assert decision["reason"] == "satin_intercolumn_repeats"
    assert max_top_penetration_multiplicity(plan) == 2
    assert decision["actual_top_metrics"]["max_top_penetration_multiplicity"] == 2
    assert decision["candidates"]["intercolumn_repeat_comparison"] == dict(
        reference_max_multiplicity=2, candidate_max_multiplicity=3, accepted=False
    )
    attempts = decision["candidates"]["directional_satin"]["attempts"]
    assert len(attempts) > 1
    assert any(a.get("max_top_penetration_multiplicity", 0) >= 3 for a in attempts)
    assert plan.stats["unsafe_connections"] == plan.stats["crowded_satin_penetrations"] == 0
