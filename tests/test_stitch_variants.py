import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pyembroidery as pe
import pytest

from embroidery_rungs import StitchParams, generate
from embroidery_rungs.stitching.digitizer import digitize, prepare_digitizing
from embroidery_rungs.stitching.variants import MAX_COMPARISON_REGIONS, recommend_variant
from embroidery_rungs.svg_manager import load_svg_paths


def _column(svg_file):
    return svg_file(
        '<rect x="2" y="2" width="36" height="4" fill="#101010"/>',
        width="40mm",
        height="12mm",
        viewbox="0 0 40 12",
    )


def _data(variant):
    return json.loads(Path(variant.direct.plan_path).read_text())


def test_comparison_shares_interpretation_and_lazy_geometry(svg_file, tmp_path, monkeypatch):
    from embroidery_rungs.stitching import consistency, digitizer

    counts = {}

    def track(module, name):
        original = getattr(module, name)

        def wrapped(*args, **kwargs):
            counts[name] = counts.get(name, 0) + 1
            return original(*args, **kwargs)

        monkeypatch.setattr(module, name, wrapped)

    for name in ("rasterize_rgba", "separate_colors", "analyze_regions", "design_symmetries"):
        track(digitizer, name)
    for name in ("canonical_regions", "compute_medial_axis"):
        track(consistency, name)
    result = generate(_column(svg_file), tmp_path / "out", compare_strategies=True)
    assert counts == {
        "rasterize_rgba": 1,
        "separate_colors": 1,
        "analyze_regions": 1,
        "design_symmetries": 1,
        "canonical_regions": 1,
        "compute_medial_axis": 1,
    }
    assert result.recommended_variant == "balanced"
    assert [variant.id for variant in result.variants] == [
        "balanced",
        "uniform_fill",
        "running_outline",
    ]
    assert result.variants[0].equivalent_strategies == ["satin_preferred", "uniform_satin"]
    assert result.direct is result.variants[0].direct
    assert Path(result.direct.pes_path).name == "shape_direct.pes"
    assert Path(result.variants[1].direct.pes_path).name == "shape_uniform_fill_direct.pes"


def test_variants_are_deterministic_and_machine_files_match_each_plan(svg_file, tmp_path):
    source = svg_file(
        '<rect x="2" y="2" width="30" height="4" fill="#dd1122"/>'
        '<rect x="7" y="12" width="10" height="6" fill="#1020cc"/>',
        width="40mm",
        height="24mm",
        viewbox="0 0 40 24",
    )
    params = StitchParams.for_fabric("stretch", stabilizer="cutaway", fill_angle_deg=30)
    first = generate(source, tmp_path / "first", stitch_params=params, compare_strategies=True)
    second = generate(source, tmp_path / "second", stitch_params=params, compare_strategies=True)
    assert first.recommended_variant == second.recommended_variant
    assert [v.id for v in first.variants] == [v.id for v in second.variants]
    fingerprints = set()
    for variant, repeated in zip(first.variants, second.variants, strict=True):
        data = _data(variant)
        assert data["commands"] == _data(repeated)["commands"]
        assert variant.quality == repeated.quality
        assert variant.quality["coverage"] == variant.direct.stats["coverage"]
        assert variant.direct.threads == first.direct.threads
        assert variant.direct.params.satin_spacing_mm == first.direct.params.satin_spacing_mm
        assert (
            variant.direct.params.pull_compensation_mm == first.direct.params.pull_compensation_mm
        )
        assert variant.direct.params.underlay == first.direct.params.underlay
        assert variant.direct.stats["unsafe_connections"] == 0
        assert variant.direct.stats["crowded_satin_penetrations"] == 0
        assert variant.direct.stats["short_stitches"] == 0
        commands = np.asarray(data["commands"])
        expected = commands[commands[:, 2] == pe.STITCH, :2]
        for filename in (variant.direct.pes_path, variant.direct.dst_path):
            pattern = pe.read(filename)
            actual = np.asarray(pattern.stitches)
            codes = actual[:, 2].astype(int) & pe.COMMAND_MASK
            assert np.array_equal(actual[codes == pe.STITCH, :2], expected)
            assert np.count_nonzero(codes == pe.COLOR_CHANGE) == len(data["threads"]) - 1
            if filename.endswith(".pes"):
                assert len(pattern.threadlist) == len(data["threads"])
        fingerprint = (tuple(map(tuple, data["commands"])), tuple(data["threads"]))
        assert fingerprint not in fingerprints
        fingerprints.add(fingerprint)
        if variant.id == "uniform_fill":
            assert variant.direct.params.auto_fill_angle is False
            assert all(
                d["fill_angle_deg"] == pytest.approx(30)
                for d in variant.direct.decisions
                if d["method"] == "fill"
            )


@pytest.mark.parametrize("choice", ["satin", "fill", "running"])
def test_explicit_method_is_never_overridden_by_comparison(svg_file, tmp_path, monkeypatch, choice):
    from embroidery_rungs import pipeline

    def unexpected(*args, **kwargs):
        raise AssertionError("Comparison must not run for an explicit stitch type.")

    monkeypatch.setattr(pipeline, "plan_variants", unexpected)
    result = generate(
        _column(svg_file),
        tmp_path / choice,
        stitch_params=StitchParams(stitch_type=choice),
        compare_strategies=True,
    )
    assert result.variants == []
    assert result.recommended_variant is None
    assert result.direct.params.stitch_type == choice


def test_failed_alternative_preserves_successful_balanced_result(svg_file, tmp_path, monkeypatch):
    from embroidery_rungs.stitching import variants

    original = variants.digitize

    def fail_fill(svg, params, **kwargs):
        if params.stitch_type == "fill":
            raise ValueError("Alternative exceeds its stitch budget.")
        return original(svg, params, **kwargs)

    monkeypatch.setattr(variants, "digitize", fail_fill)
    result = generate(_column(svg_file), tmp_path / "out", compare_strategies=True)
    assert result.recommended_variant == "balanced"
    assert [v.id for v in result.variants] == ["balanced", "running_outline"]
    assert result.skipped_variants == [
        {"id": "uniform_fill", "reason": "Alternative exceeds its stitch budget."}
    ]
    assert Path(result.direct.pes_path).is_file()


@pytest.mark.parametrize("region_count", [MAX_COMPARISON_REGIONS, MAX_COMPARISON_REGIONS + 1])
def test_comparison_region_budget_only_limits_alternatives(svg_file, monkeypatch, region_count):
    from embroidery_rungs.stitching import variants

    svg, _ = load_svg_paths(_column(svg_file))
    params = StitchParams()
    prepared = prepare_digitizing(svg, params)
    prepared.analysis["region_count"] = region_count
    baseline, _ = digitize(svg, params, prepared=prepared)
    original = variants.digitize
    calls = []

    def tracked(svg, params, **kwargs):
        calls.append(params.auto_strategy if params.stitch_type == "auto" else params.stitch_type)
        return original(svg, params, **kwargs)

    monkeypatch.setattr(variants, "prepare_digitizing", lambda *args: prepared)
    monkeypatch.setattr(variants, "digitize", tracked)
    candidates, recommended, skipped = variants.plan_variants(svg, params)
    assert candidates[0].plan.commands == baseline.commands
    assert candidates[0].plan.stats == baseline.stats
    assert candidates[0].plan.params == baseline.params
    assert recommended == "balanced"
    if region_count > MAX_COMPARISON_REGIONS:
        assert calls == ["balanced"]
        assert len(candidates) == 1
        assert skipped == [
            {
                "id": identifier,
                "reason": "comparison_region_budget",
                "region_count": region_count,
                "limit": MAX_COMPARISON_REGIONS,
            }
            for identifier in (
                "satin_preferred",
                "uniform_fill",
                "uniform_satin",
                "running_outline",
            )
        ]
        assert "comparison_limited" in candidates[0].reasons
        assert "no_meaningful_gain" not in candidates[0].reasons
    else:
        assert calls == ["balanced", "satin_preferred", "fill", "running"]
        assert skipped == []
        assert "comparison_limited" not in candidates[0].reasons


def test_failed_comparison_export_preserves_all_previous_outputs(svg_file, tmp_path, monkeypatch):
    from embroidery_rungs import pipeline

    source = _column(svg_file)
    output = tmp_path / "out"
    generate(source, output)
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    original = pipeline.export_plan

    def fail_alternative(svg, stage, stem, *args, **kwargs):
        if "uniform_fill" in stem:
            raise OSError("Disk failure during alternative export.")
        return original(svg, stage, stem, *args, **kwargs)

    monkeypatch.setattr(pipeline, "export_plan", fail_alternative)
    with pytest.raises(OSError, match="Disk failure"):
        generate(source, output, compare_strategies=True)
    assert {path.name: path.read_bytes() for path in output.iterdir()} == before
    assert not list(output.glob(".embroidery-*"))


def test_prepared_artwork_rejects_palette_or_source_changes(svg_file):
    svg, _ = load_svg_paths(_column(svg_file))
    prepared = prepare_digitizing(svg, StitchParams())
    assert not prepared.labels.flags.writeable
    with pytest.raises(ValueError, match="Prepared artwork must match"):
        digitize(svg, StitchParams(max_colors=2), prepared=prepared)
    other, _ = load_svg_paths(_column(svg_file))
    with pytest.raises(ValueError, match="Prepared artwork must match"):
        digitize(other, StitchParams(), prepared=prepared)


def test_reusing_geometry_does_not_mutate_previous_plan_or_artwork(svg_file):
    svg, _ = load_svg_paths(_column(svg_file))
    params = StitchParams()
    prepared = prepare_digitizing(svg, params)
    labels = prepared.labels.copy()
    balanced, _ = digitize(svg, params, prepared=prepared)
    commands = deepcopy(balanced.commands)
    decisions = deepcopy(balanced.decisions)
    blocks = [block.points.copy() for block in balanced.blocks]
    digitize(svg, StitchParams(auto_strategy="satin_preferred"), prepared=prepared)
    digitize(svg, StitchParams(stitch_type="fill", auto_fill_angle=False), prepared=prepared)
    assert balanced.commands == commands
    assert balanced.decisions == decisions
    assert all(
        np.array_equal(block.points, points)
        for block, points in zip(balanced.blocks, blocks, strict=True)
    )
    assert np.array_equal(prepared.labels, labels)


def test_warm_geometry_cache_matches_independent_satin_preference(svg_file):
    source = svg_file(
        '<rect x="2" y="2" width="32" height="12" fill="#101010"/>',
        width="36mm",
        height="16mm",
        viewbox="0 0 36 16",
    )
    svg, _ = load_svg_paths(source)
    baseline = StitchParams.for_fabric(machine="brother-skitch-pp1")
    prepared = prepare_digitizing(svg, baseline)
    digitize(svg, baseline, prepared=prepared)
    preferred = StitchParams.for_fabric(
        machine="brother-skitch-pp1", auto_strategy="satin_preferred"
    )
    warm, warm_layers = digitize(svg, preferred, prepared=prepared)
    fresh, fresh_layers = digitize(svg, preferred)
    assert warm.commands == fresh.commands
    assert warm.decisions == fresh.decisions
    assert warm.stats == fresh.stats
    assert warm_layers == fresh_layers
    assert warm.stats["satin_regions"] > 0


def _candidate(identifier, **overrides):
    quality = {
        "unsafe_connections": 0,
        "crowded_satin_penetrations": 0,
        "short_stitches": 0,
        "omitted_colors": 0,
        "omitted_regions": 0,
        "failed_coverage_layers": 0,
        "largest_gap_mm2": 0,
        "structural_missing_mm2": 0,
        "uncovered_max_mm": 0.2,
        "coverage": 1.0,
        "structural_coverage": 1.0,
        "spill_mm2": 2,
        "status": "geometric_checks_passed",
        "method_area_mm2": {"satin": 0, "fill": 100, "running": 0, "omitted": 0},
        "trims": 2,
        "jump_length_mm": 20,
    }
    quality.update(overrides)
    return SimpleNamespace(id=identifier, quality=quality)


def test_recommendation_keeps_balanced_ties_and_ignores_raw_stitch_count():
    balanced = _candidate("balanced", stitches=5000)
    fill = _candidate("uniform_fill", stitches=300)
    assert recommend_variant([balanced, fill]) == "balanced"


def test_outline_is_never_recommended_in_place_of_surface_coverage():
    balanced = _candidate("balanced", status="needs_review", omitted_regions=1)
    outline = _candidate("running_outline")
    assert recommend_variant([balanced, outline]) == "balanced"


def test_complete_satin_comparison_reuses_an_independently_equivalent_strict_plan(
    svg_file, tmp_path, monkeypatch
):
    from embroidery_rungs.stitching import variants

    source = _column(svg_file)
    strict = generate(source, tmp_path / "strict", stitch_params=StitchParams(stitch_type="satin"))
    original = variants.digitize

    def avoid_repeating_satin(svg, params, **kwargs):
        assert params.stitch_type != "satin"
        return original(svg, params, **kwargs)

    monkeypatch.setattr(variants, "digitize", avoid_repeating_satin)
    compared = generate(source, tmp_path / "compared", compare_strategies=True)
    match = next(v for v in compared.variants if "uniform_satin" in v.equivalent_strategies)
    strict_data = json.loads(Path(strict.direct.plan_path).read_text())
    assert _data(match)["commands"] == strict_data["commands"]
    assert match.quality["purpose"] == "surface"
    outline = next(v for v in compared.variants if v.id == "running_outline")
    assert outline.quality["purpose"] == "outline"


def test_coverage_distances_below_structural_tolerance_are_equivalent():
    balanced = _candidate("balanced", uncovered_max_mm=0.236)
    fill = _candidate("uniform_fill", uncovered_max_mm=0.118)
    assert recommend_variant([balanced, fill]) == "balanced"


def test_qualified_result_wins_over_review_only_when_machine_hazards_do_not_worsen():
    balanced = _candidate("balanced", status="needs_review")
    fill = _candidate("uniform_fill", coverage=0.9)
    assert recommend_variant([balanced, fill]) == "uniform_fill"
    fill.quality["unsafe_connections"] = 1
    assert recommend_variant([balanced, fill]) == "balanced"


@pytest.mark.parametrize(
    "fault",
    [
        {"crowded_satin_penetrations": 1},
        {"short_stitches": 1},
        {"unsafe_connections": 1},
        {"failed_coverage_layers": 1, "largest_gap_mm2": 0.1},
        {"coverage": 0.99},
        {"spill_mm2": 8},
        {"trims": 15},
        {"jump_length_mm": 100},
        {"status": "needs_review"},
    ],
)
def test_prettier_satin_cannot_override_quality_or_excessive_travel(fault):
    balanced = _candidate("balanced")
    satin = _candidate(
        "satin_preferred",
        method_area_mm2={"satin": 100, "fill": 0, "running": 0, "omitted": 0},
        **fault,
    )
    assert recommend_variant([balanced, satin]) == "balanced"


def test_recommendation_accepts_meaningful_safe_satin_area_gain():
    balanced = _candidate("balanced")
    satin = _candidate(
        "satin_preferred",
        method_area_mm2={"satin": 20, "fill": 80, "running": 0, "omitted": 0},
        coverage=0.995,
    )
    assert recommend_variant([balanced, satin]) == "satin_preferred"
    satin.quality["coverage"] = 0.994
    assert recommend_variant([balanced, satin]) == "balanced"
    satin.quality["coverage"] = 1.0
    satin.quality["method_area_mm2"] = {"satin": 0.5, "fill": 99.5, "running": 0, "omitted": 0}
    assert recommend_variant([balanced, satin]) == "balanced"


def test_uniform_fill_can_improve_gaps_without_claiming_passed_sew_quality():
    balanced = _candidate(
        "balanced",
        failed_coverage_layers=1,
        largest_gap_mm2=0.5,
        structural_missing_mm2=0.5,
        status="needs_review",
    )
    fill = deepcopy(balanced)
    fill.id = "uniform_fill"
    fill.quality["largest_gap_mm2"] = 0.1
    fill.quality["structural_missing_mm2"] = 0.1
    assert recommend_variant([balanced, fill]) == "uniform_fill"
    assert fill.quality["status"] == "needs_review"


def test_comparison_flag_must_be_boolean(svg_file, tmp_path):
    output = tmp_path / "invalid"
    with pytest.raises(ValueError, match="compare_strategies must be a boolean"):
        generate(_column(svg_file), output, compare_strategies=1)
    assert not output.exists()
