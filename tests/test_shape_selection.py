import json
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

import numpy as np
import pyembroidery as pe
import pytest
from shapely import intersects, linestrings
from shapely.geometry import Point
from svgelements import Matrix

from embroidery_rungs import StitchParams, generate
from embroidery_rungs.stitching import selection
from embroidery_rungs.stitching.quality import coverage_needs_review
from embroidery_rungs.svg_manager import UNITS_PER_MM

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/quality"


def assert_machine_quality(direct):
    stats = direct.stats
    assert stats["structural_coverage"] >= 0.999
    assert stats["largest_gap_mm2"] <= 0.05
    assert stats["uncovered_max_mm"] <= 0.5
    assert stats["unsafe_connections"] == stats["crowded_satin_penetrations"] == 0
    assert stats["short_stitches"] == stats["omitted_regions"] == 0
    assert stats["max_stitch_mm"] <= direct.params.max_stitch_mm
    data = json.loads(Path(direct.plan_path).read_text())
    commands = np.asarray(data["commands"])
    assert np.issubdtype(commands.dtype, np.integer)
    for run in data["top_layer_runs"]:
        if run["kind"] == "satin":
            points = commands[run["start"] : run["end"], :2] / 10
            assert np.linalg.norm(np.diff(points, axis=0), axis=1).max(initial=0) <= 7
    return data


@pytest.mark.parametrize("sample,kind", [("fine-ring", "outline"), ("thin", "stroke")])
@pytest.mark.parametrize("phase", [(0, 0), (5.1, 5.2), (5.02, 5.08)])
@pytest.mark.parametrize("spacing", [0.3, 0.5])
def test_fine_columns_preserve_fill_fidelity_across_grid_phases(
    tmp_path, sample, kind, phase, spacing
):
    artwork = ET.fromstring((EXAMPLES / f"{sample}.svg").read_text())
    content = "".join(ET.tostring(child, encoding="unicode") for child in artwork)
    source = tmp_path / "fine.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" '
        f'viewBox="0 0 100 100"><g transform="translate{phase} scale(.75)">'
        f"{content}</g></svg>"
    )
    params = StitchParams.for_fabric(
        "stable", machine="brother-skitch-pp1", satin_spacing_mm=spacing
    )
    direct = generate(source, tmp_path / "output", stitch_params=params).direct
    decision = direct.decisions[0]
    assert decision["auto_strategy"] == "balanced"
    assert decision["shape_profile"]["kind"] == kind
    assert decision["shape_profile"]["narrow"]
    assert decision["mat_coverage"] < 0.9
    assert decision["method"] == (
        "satin" if sample == "thin" and spacing == 0.3 and phase != (0, 0) else "fill"
    )
    comparison = decision["candidates"]["fill_comparison"]
    assert comparison["accepted"] == (decision["method"] == "satin")
    fill_params = replace(params, stitch_type="fill")
    if decision["method"] == "fill":
        assert decision["reason"] == "satin_fidelity_regression"
        fill_params = replace(
            fill_params, auto_fill_angle=False, fill_angle_deg=decision["fill_angle_deg"]
        )
    else:
        assert direct.stats["fill_regions"] == direct.stats["running_regions"] == 0
        assert direct.stats["underlay_stitches"] > 0
    fill = generate(source, tmp_path / "fill", stitch_params=fill_params).direct
    assert direct.stats["coverage"] >= fill.stats["coverage"] - 0.005
    assert direct.stats["spill_mm2"] <= fill.stats["spill_mm2"] + max(
        0.25, 0.02 * decision["area_mm2"]
    )
    data = assert_machine_quality(direct)
    if sample == "fine-ring":
        commands = np.asarray(data["commands"])
        sewn = (commands[:-1, 2] == pe.STITCH) & (commands[1:, 2] == pe.STITCH)
        segments = (
            np.stack([commands[:-1, :2], commands[1:, :2]], axis=1)[sewn] / 10 + data["origin_mm"]
        )
        center = np.array(phase) + np.array([40, 35]) * 0.75
        assert not intersects(linestrings(segments), Point(center).buffer(2.45)).any()


@pytest.mark.parametrize("sample", ["tight-curve", "sharp-corner"])
def test_balanced_recovers_complete_directional_columns(tmp_path, sample):
    params = StitchParams.for_fabric("stable", machine="brother-skitch-pp1")
    direct = generate(EXAMPLES / f"{sample}.svg", tmp_path, stitch_params=params).direct
    decision = direct.decisions[0]
    assert decision["method"] == "satin"
    assert decision["reason"] == "complete_directional_columns"
    assert decision["shape_profile"]["kind"] == "stroke"
    assert coverage_needs_review(decision["candidates"]["satin"])
    assert not coverage_needs_review(decision["candidates"]["directional_satin"])
    assert decision["candidates"]["fill_comparison"]["accepted"]
    assert direct.stats["coverage"] >= decision["candidates"]["fill_reference"]["coverage"] - 0.005
    assert 0 < decision["directional_satin_columns"] <= 64
    assert direct.stats["fill_regions"] == 0
    assert_machine_quality(direct)


@pytest.mark.parametrize("reject_all", [False, True])
def test_directional_candidates_continue_after_fill_fidelity_rejection(monkeypatch, reject_all):
    mask = np.zeros((80, 100), dtype=bool)
    mask[10:60, 10:20] = True
    mask[10:60, 60:70] = True
    mask[10:20, 10:70] = True
    scale = 10
    transform = Matrix.scale(scale / UNITS_PER_MM)
    params = StitchParams(auto_fill_angle=False, fill_angle_deg=0)
    calls = []
    options = []

    def columns(source, angle, compensation):
        return [
            {
                "type": "satin",
                "rail_a": np.array([[1.1, 1.1], [1.1, 3], [1.1, 5.8]]),
                "rail_b": np.array([[1.9, 1.1], [1.9, 3], [1.9, 5.8]]),
                "directional_satin_angle_deg": angle,
            }
        ]

    def audit(elements):
        metrics = {
            "coverage": 0.99,
            "structural_coverage": 1.0,
            "largest_gap_mm2": 0.0,
            "uncovered_max_mm": 0.0,
            "spill_mm2": 1.0,
            "unsafe_connections": 0,
            "omitted_regions": 0,
            "crowded_satin_penetrations": 0,
        }
        if elements[0]["type"] == "fill":
            calls.append("fill")
        else:
            angle = elements[0]["directional_satin_angle_deg"]
            calls.append(angle)
            if reject_all or angle != 45:
                metrics["spill_mm2"] = 3.0
        return metrics

    monkeypatch.setattr(selection, "directional_columns", columns)
    selected, decisions = selection.select_stitch_types(
        [], mask, transform, params, satin_audit=audit, satin_options=options
    )
    decision = decisions[0]
    assert decision["shape_profile"]["kind"] == "stroke"
    attempts = decision["candidates"]["directional_satin"]["attempts"]
    assert len(options) == len(attempts)
    assert [option["sweep_angle_deg"] for option in options] == [
        attempt["sweep_angle_deg"] for attempt in attempts
    ]
    assert all(option["kind"] == "directional" for option in options)
    assert all(option["reason"] == "complete_directional_columns" for option in options)
    assert all(option["directional_satin_columns"] == 1 for option in options)
    assert all(option["split_satin_columns"] == 0 for option in options)
    assert all(
        option["canonical_satin_angle_deg"] == option["sweep_angle_deg"] for option in options
    )
    assert all(not coverage_needs_review(attempt) for attempt in attempts)
    assert all(
        attempt["unsafe_connections"] == attempt["crowded_satin_penetrations"] == 0
        for attempt in attempts
    )
    if reject_all:
        assert calls == [0, "fill", 45, 135, 90]
        assert decision["method"] == "fill"
        assert decision["reason"] == "satin_fidelity_regression"
        assert [attempt["fill_fidelity_passed"] for attempt in attempts] == [False] * 4
        assert all(element["type"] == "fill" for element in selected)
    else:
        assert calls == [0, "fill", 45]
        assert decision["method"] == "satin"
        assert decision["reason"] == "complete_directional_columns"
        assert [attempt["fill_fidelity_passed"] for attempt in attempts] == [False, True]
        assert decision["canonical_satin_angle_deg"] == 45
        assert all(element["type"] == "satin" for element in selected)
    assert decision["candidates"]["fill_comparison"]["accepted"] == (not reject_all)


def test_satin_option_collector_copies_rails_and_metrics_without_mutating_selection():
    mask = np.zeros((100, 60), dtype=bool)
    mask[10:90, 10:30] = True
    transform = Matrix.scale(10 / UNITS_PER_MM)
    params = StitchParams()
    elements = [
        {
            "type": "satin",
            "rail_a": np.array([[1.05, 1.05], [1.05, 4.9], [1.05, 8.95]]),
            "rail_b": np.array([[2.95, 1.05], [2.95, 4.9], [2.95, 8.95]]),
        }
    ]
    original = {key: elements[0][key].copy() for key in ("rail_a", "rail_b")}
    metrics = {
        "coverage": 1.0,
        "structural_coverage": 1.0,
        "largest_gap_mm2": 0.0,
        "uncovered_max_mm": 0.0,
        "spill_mm2": 0.0,
        "unsafe_connections": 0,
        "omitted_regions": 0,
        "crowded_satin_penetrations": 0,
        "detail": {"marks": ["safe"]},
    }
    calls = []

    def audit(selected):
        calls.append(len(selected))
        return metrics

    baseline, baseline_decisions = selection.select_stitch_types(
        elements, mask, transform, params, satin_audit=audit
    )
    options = []
    selected, decisions = selection.select_stitch_types(
        elements, mask, transform, params, satin_audit=audit, satin_options=options
    )
    assert calls == [1, 1]
    assert decisions == baseline_decisions
    assert len(options) == 1
    option = options[0]
    assert option["kind"] == "mat"
    assert option["sweep_angle_deg"] is None
    assert option["reason"] == decisions[0]["reason"]
    assert option["split_satin_columns"] == option["directional_satin_columns"] == 0
    assert option["canonical_satin_angle_deg"] is None
    assert isinstance(option["elements"], tuple)
    for key in ("rail_a", "rail_b"):
        np.testing.assert_array_equal(elements[0][key], original[key])
        np.testing.assert_array_equal(selected[0][key], baseline[0][key])
        np.testing.assert_array_equal(option["elements"][0][key], selected[0][key])
        assert elements[0][key].flags.writeable
        assert selected[0][key].flags.writeable
        assert not option["elements"][0][key].flags.writeable
        assert not np.shares_memory(option["elements"][0][key], selected[0][key])
    assert option["metrics"] == metrics
    metrics["detail"]["marks"].append("changed")
    assert option["metrics"]["detail"]["marks"] == ["safe"]


@pytest.mark.parametrize("sample,kind", [("star", "wide_surface"), ("holes", "outline")])
def test_broad_surfaces_keep_fill_without_new_directional_candidates(tmp_path, sample, kind):
    params = StitchParams.for_fabric("stable", machine="brother-skitch-pp1")
    direct = generate(EXAMPLES / f"{sample}.svg", tmp_path, stitch_params=params).direct
    decision = direct.decisions[0]
    assert decision["method"] == "fill"
    assert decision["shape_profile"]["kind"] == kind
    assert not decision["shape_profile"]["narrow"]
    assert "directional_satin" not in decision["candidates"]
    assert direct.stats["satin_regions"] == 0
    assert_machine_quality(direct)


def test_narrow_outline_still_rejects_real_incomplete_satin(tmp_path):
    params = StitchParams.for_fabric(
        "stable", machine="brother-skitch-pp1", satin_spacing_mm=1.2, auto_adjust=False
    )
    direct = generate(EXAMPLES / "ring.svg", tmp_path, stitch_params=params).direct
    decision = direct.decisions[0]
    assert decision["shape_profile"]["kind"] == "outline"
    assert decision["shape_profile"]["narrow"]
    assert decision["method"] == "fill"
    assert coverage_needs_review(decision["candidates"]["satin"])
    attempts = decision["candidates"]["directional_satin"]["attempts"]
    assert attempts
    assert all(coverage_needs_review(attempt) for attempt in attempts)
    assert direct.params.satin_spacing_mm == 1.2
    assert direct.stats["satin_regions"] == 0
    assert_machine_quality(direct)


@pytest.mark.parametrize(
    "content,kind",
    [
        ('<circle cx="15" cy="15" r="2"/>', "round_detail"),
        ('<rect x="10" y="10" width="4" height="4"/>', "compact"),
    ],
)
def test_decisions_describe_compact_and_round_details(tmp_path, content, kind):
    source = tmp_path / "detail.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="40mm" height="40mm" '
        f'viewBox="0 0 40 40">{content}</svg>'
    )
    params = StitchParams.for_fabric("stable", machine="brother-skitch-pp1")
    direct = generate(source, tmp_path / "output", stitch_params=params).direct
    profile = direct.decisions[0]["shape_profile"]
    assert profile["kind"] == kind
    assert profile["narrow"]
    assert profile["hole_count"] == 0
    assert profile["area_width_ratio"] < 3
    assert profile["safe_satin_width_mm"] == 7
    assert_machine_quality(direct)
