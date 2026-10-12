from dataclasses import asdict

import numpy as np
import pytest
from svgelements import Matrix

from embroidery_rungs.stitching.analysis import adjust_for_sewing, analyze_regions
from embroidery_rungs.stitching.export import export_direct
from embroidery_rungs.stitching.params import StitchParams
from embroidery_rungs.stitching.planner import build_stitch_plan
from embroidery_rungs.svg_manager import load_svg_paths


@pytest.mark.parametrize("fabric", ["custom", "stable", "stretch", "textured"])
@pytest.mark.parametrize("weight", [30, 40, 60])
def test_normal_material_presets_keep_their_density(fabric, weight):
    requested = StitchParams.for_fabric(fabric, thread_weight=weight)
    effective, adjustments = adjust_for_sewing(requested)
    assert effective.satin_spacing_mm == requested.satin_spacing_mm
    assert effective.fill_spacing_mm == requested.fill_spacing_mm
    assert effective.pull_compensation_mm == requested.pull_compensation_mm
    assert not any(d["parameter"] in ("satin_spacing_mm", "fill_spacing_mm") for d in adjustments)


def test_auto_adjust_bounds_extremes_without_mutating_requested_parameters():
    requested = StitchParams(
        fabric="stretch",
        satin_spacing_mm=0.2,
        fill_spacing_mm=1.2,
        pull_compensation_mm=0.5,
        max_satin_width_mm=12,
        underlay=False,
    )
    original = asdict(requested)
    effective, adjustments = adjust_for_sewing(requested)
    assert asdict(requested) == original
    assert effective.satin_spacing_mm == 0.36
    assert effective.fill_spacing_mm == 0.562
    assert effective.pull_compensation_mm == 0.35
    assert effective.underlay
    assert effective.max_satin_width_mm == pytest.approx(7.1)
    assert {a["parameter"] for a in adjustments} == {
        "satin_spacing_mm",
        "fill_spacing_mm",
        "pull_compensation_mm",
        "underlay",
        "max_satin_width_mm",
    }
    assert all(set(a) == {"parameter", "requested", "effective", "reason"} for a in adjustments)


def test_explicit_opt_out_honors_parameters_but_cannot_bypass_machine_limits():
    requested = StitchParams(
        auto_adjust=False, fabric="stretch", fill_spacing_mm=1.2, underlay=False
    )
    effective, adjustments = adjust_for_sewing(requested)
    assert asdict(effective) == asdict(requested)
    assert adjustments == []
    with pytest.raises(ValueError, match="100 × 100"):
        adjust_for_sewing(
            StitchParams(auto_adjust=False, machine="brother-skitch-pp1", hoop_width_mm=120)
        )


def test_short_machine_length_headroom_keeps_valid_physical_parameters():
    effective, _ = adjust_for_sewing(StitchParams(max_stitch_mm=2, pull_compensation_mm=0.5))
    effective.validate()
    assert effective.max_satin_width_mm == 2


def test_analysis_counts_visible_color_topology_and_fine_region_area():
    labels = np.zeros((80, 100), dtype=np.uint8)
    labels[10:30, 10:60] = 1
    labels[15:25, 25:35] = 0
    labels[50, 10:70] = 2
    analysis = analyze_regions(labels, 10, StitchParams())
    assert analysis["category"] == "multicolor"
    assert analysis["color_count"] == analysis["region_count"] == 2
    assert analysis["hole_count"] == 1
    assert analysis["area_mm2"] == 9.6
    assert analysis["fine_region_area_ratio"] == 0.0625
    assert analyze_regions(np.rot90(labels), 10, StitchParams()) == analysis


def test_complex_geometry_does_not_change_the_material_density_policy():
    labels = np.zeros((80, 100), dtype=np.uint8)
    labels[::2, 10:90] = 1
    params = StitchParams.for_fabric("stable")
    analysis = analyze_regions(labels, 10, params)
    assert analysis["category"] == "complex"
    assert analysis["region_count"] == 40
    assert analysis["fine_region_area_ratio"] == 1
    effective, _ = adjust_for_sewing(params)
    assert effective.fill_spacing_mm == params.fill_spacing_mm


def test_diagonal_background_escape_does_not_become_a_false_closed_hole():
    labels = np.ones((9, 9), dtype=np.uint8)
    labels[np.arange(5), np.arange(5)] = 0
    assert analyze_regions(labels, 10, StitchParams())["hole_count"] == 0


def test_unequivocally_broad_region_preserves_coverage_and_holes_without_mat(tmp_path, monkeypatch):
    def unexpected_mat(*args, **kwargs):
        raise AssertionError("Broad fill should not need a medial axis")

    monkeypatch.setattr(
        "embroidery_rungs.stitching.consistency.compute_medial_axis", unexpected_mat
    )
    source = tmp_path / "broad.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="70mm" viewBox="0 0 80 70">'
        '<path fill-rule="evenodd" d="M10 10H70V60H10Z M30 25H50V45H30Z"/></svg>'
    )
    document, _ = load_svg_paths(source)
    _, plan = export_direct(document, tmp_path, "broad", StitchParams())
    assert {d["method"] for d in plan.decisions} == {"fill"}
    assert all(not d["mat_evaluated"] for d in plan.decisions)
    assert plan.stats["structural_coverage"] >= 0.999
    assert plan.stats["largest_gap_mm2"] <= 0.05
    assert plan.analysis["hole_count"] == 1
    assert plan.analysis["quality_status"] == "geometric_checks_passed"


@pytest.mark.parametrize(
    "metric,value", [("structural_coverage", 0.998), ("uncovered_max_mm", 0.501)]
)
def test_small_color_coverage_warning_cannot_be_diluted_into_passing_design_status(
    tmp_path, monkeypatch, metric, value
):
    from embroidery_rungs.stitching import digitizer

    measure = digitizer.measure_plan

    def small_color_gap(plan, target, *args, **kwargs):
        metrics, image = measure(plan, target, *args, **kwargs)
        if target.sum() < 1000:
            metrics[metric] = value
        return metrics, image

    monkeypatch.setattr(digitizer, "measure_plan", small_color_gap)
    source = tmp_path / "layers.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="70mm" viewBox="0 0 80 70">'
        '<rect x="5" y="5" width="40" height="30" fill="#ff0000"/>'
        '<rect x="60" y="40" width="2" height="2" fill="#0000ff"/></svg>'
    )
    svg, _ = load_svg_paths(source)
    plan, diagnostics = digitizer.digitize(svg, StitchParams())
    assert any(d[metric] == value for d in diagnostics)
    assert plan.stats["structural_coverage"] >= 0.999
    assert plan.stats["largest_gap_mm2"] <= 0.05
    assert any("Top-layer coverage" in warning for warning in plan.warnings)
    assert plan.analysis["quality_status"] == "needs_review"


def test_high_minimum_tie_ins_do_not_create_false_short_stitch_faults():
    plan = build_stitch_plan(
        [{"type": "running", "points": [[0, 0], [10, 0]]}],
        StitchParams(min_stitch_mm=0.5, underlay=False),
    )
    assert plan.stats["short_stitches"] == 0


@pytest.mark.parametrize("extra_region", [False, True])
def test_visible_region_budget_is_checked_before_canonical_allocation(
    tmp_path, monkeypatch, extra_region
):
    from embroidery_rungs.stitching import digitizer

    mask = np.zeros((128, 128), dtype=bool)
    mask[::2, ::2] = True
    mask[-1, -1] = extra_region
    rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
    rgba[..., 3] = mask * 255
    monkeypatch.setattr(digitizer, "rasterize_rgba", lambda *args, **kwargs: (rgba, Matrix()))
    called = False

    def canonical_selector(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("canonical allocation reached")

    monkeypatch.setattr(digitizer, "select_consistent_regions", canonical_selector)
    source = tmp_path / "placeholder.svg"
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>')
    svg, _ = load_svg_paths(source)
    if extra_region:
        with pytest.raises(ValueError, match="4097 visible regions.*4096.*Simplify"):
            digitizer.digitize(svg, StitchParams())
        assert not called
    else:
        with pytest.raises(AssertionError, match="canonical allocation reached"):
            digitizer.digitize(svg, StitchParams())
        assert called
