from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pyembroidery as pe
import pytest

from embroidery_rungs import GenerationParams
from embroidery_rungs.image_processor import rasterize_rgba
from embroidery_rungs.inputs import prepare_artwork
from embroidery_rungs.stitching import consistency, selection, variants
from embroidery_rungs.stitching.digitizer import digitize
from embroidery_rungs.stitching.params import StitchParams
from embroidery_rungs.stitching.planner import (
    CandidateGeometryError,
    StitchBlock,
    StitchPlan,
    build_stitch_plan,
)
from embroidery_rungs.stitching.quality import max_top_penetration_multiplicity
from embroidery_rungs.svg_manager import load_svg_paths


def document(tmp_path, content):
    path = tmp_path / "strategy.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="70mm" '
        f'viewBox="0 0 80 70">{content}</svg>'
    )
    return load_svg_paths(path)[0]


def assert_machine_quality(plan):
    assert plan.stats["structural_coverage"] >= 0.999
    assert plan.stats["largest_gap_mm2"] <= 0.05
    assert plan.stats["crowded_satin_penetrations"] == 0
    assert plan.stats["unsafe_connections"] == plan.stats["short_stitches"] == 0
    assert plan.stats["max_stitch_mm"] <= plan.params.max_stitch_mm
    assert np.issubdtype(np.asarray(plan.commands).dtype, np.integer)


def test_balanced_is_the_default_and_unknown_automatic_strategy_is_rejected():
    assert StitchParams().auto_strategy == "balanced"
    with pytest.raises(ValueError, match="auto_strategy"):
        StitchParams(auto_strategy="unknown").validate()


def test_explicit_balanced_and_default_auto_emit_identical_machine_commands(tmp_path):
    svg = document(
        tmp_path,
        '<rect x="5" y="5" width="25" height="25"/><rect x="40" y="35" width="3" height="2"/>',
    )
    default, _ = digitize(svg, StitchParams())
    balanced, _ = digitize(svg, StitchParams(auto_strategy="balanced"))
    assert default.commands == balanced.commands
    assert default.decisions == balanced.decisions


def test_preferred_satin_evaluates_broader_columns_without_larger_floats(tmp_path):
    svg = document(tmp_path, '<rect x="10" y="10" width="32" height="12"/>')
    params = StitchParams.for_fabric("stable", machine="brother-skitch-pp1")
    balanced, _ = digitize(svg, params)
    preferred, _ = digitize(svg, replace(params, auto_strategy="satin_preferred"))
    assert {d["method"] for d in balanced.decisions} == {"fill"}
    assert {d["method"] for d in preferred.decisions} == {"satin"}
    assert preferred.decisions[0]["split_satin_columns"] == 2
    assert preferred.params.max_satin_width_mm == balanced.params.max_satin_width_mm == 7
    assert preferred.stats["max_stitch_mm"] <= 7
    assert_machine_quality(preferred)


def test_preferred_satin_preserves_small_valid_columns_beside_a_filled_body(tmp_path):
    svg = document(
        tmp_path,
        '<rect x="5" y="5" width="25" height="25"/><rect x="40" y="35" width="3" height="2"/>',
    )
    balanced, _ = digitize(svg, StitchParams())
    preferred, _ = digitize(svg, StitchParams(auto_strategy="satin_preferred"))
    assert {d["method"] for d in balanced.decisions} == {"fill"}
    assert {d["method"] for d in preferred.decisions} == {"satin", "fill"}
    assert next(d for d in preferred.decisions if d["area_mm2"] < 10)["method"] == "satin"
    assert_machine_quality(preferred)


@pytest.mark.parametrize("method", ["satin", "fill", "running"])
def test_automatic_strategy_does_not_change_explicit_stitch_methods(tmp_path, method):
    svg = document(tmp_path, '<rect x="10" y="10" width="50" height="7.8"/>')
    params = StitchParams(stitch_type=method)
    balanced, _ = digitize(svg, params)
    preferred, _ = digitize(svg, replace(params, auto_strategy="satin_preferred"))
    assert balanced.commands == preferred.commands
    assert {d["method"] for d in balanced.decisions} == {method}
    assert {d["method"] for d in preferred.decisions} == {method}


def test_preferred_satin_keeps_the_world_grid_audit_and_fill_fallback(tmp_path, monkeypatch):
    real = consistency.build_stitch_plan

    def reject_satin(elements, *args, **kwargs):
        if any(e["type"] == "satin" for e in elements):
            raise CandidateGeometryError("Quantized stitches leave their regions.")
        return real(elements, *args, **kwargs)

    monkeypatch.setattr(consistency, "build_stitch_plan", reject_satin)
    svg = document(tmp_path, '<rect x="10" y="10" width="32" height="12"/>')
    plan, _ = digitize(svg, StitchParams(auto_strategy="satin_preferred"))
    assert {d["method"] for d in plan.decisions} == {"fill"}
    assert plan.decisions[0]["split_satin_columns"] == 0
    assert_machine_quality(plan)


def test_shared_geometry_cache_is_lazy_and_never_shares_mutable_plans(tmp_path, monkeypatch):
    calls = dict(canonical=0, mat=0, columns=0, polygons=0)

    def counted(module, name, counter):
        real = getattr(module, name)

        def wrapper(*args, **kwargs):
            calls[counter] += 1
            return real(*args, **kwargs)

        monkeypatch.setattr(module, name, wrapper)

    counted(consistency, "canonical_regions", "canonical")
    counted(consistency, "compute_medial_axis", "mat")
    counted(consistency, "generate_columns", "columns")
    counted(consistency, "mask_polygons", "polygons")
    counted(selection, "mask_polygons", "polygons")
    svg = document(tmp_path, '<rect x="10" y="10" width="32" height="12"/>')
    rgba, transform = rasterize_rgba(svg, dpi=305)
    mask = rgba[..., 3] >= 128
    original = mask.copy()
    params = StitchParams.for_fabric("stable", machine="brother-skitch-pp1")
    geometry_cache = {}
    consistency.select_consistent_regions(
        mask, transform, params, [40, 35], [], geometry_cache=geometry_cache
    )
    assert calls == dict(canonical=1, mat=0, columns=0, polygons=2)
    preferred = replace(params, auto_strategy="satin_preferred")
    selected, decisions = consistency.select_consistent_regions(
        mask, transform, preferred, [40, 35], [], geometry_cache=geometry_cache
    )
    expected = build_stitch_plan(selected, preferred, origin_mm=[40, 35]).commands
    assert decisions[0]["method"] == "satin"
    assert calls == dict(canonical=1, mat=1, columns=1, polygons=2)
    selected[0]["rail_a"][0] += [1, 1]
    selected[0]["underlay"] = False
    again, again_decisions = consistency.select_consistent_regions(
        mask, transform, preferred, [40, 35], [], geometry_cache=geometry_cache
    )
    assert build_stitch_plan(again, preferred, origin_mm=[40, 35]).commands == expected
    assert again_decisions == decisions
    assert calls == dict(canonical=1, mat=1, columns=1, polygons=2)
    np.testing.assert_array_equal(mask, original)
    assert mask.flags.writeable
    assert not geometry_cache["members"][0]["mask"].flags.writeable
    for element in geometry_cache["members"][0]["mat"]:
        for value in element.values():
            if isinstance(value, np.ndarray):
                assert not value.flags.writeable


def test_geometry_cache_is_invalidated_when_source_geometry_changes(tmp_path, monkeypatch):
    calls = 0
    real = consistency.canonical_regions

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(consistency, "canonical_regions", counted)
    rgba, transform = rasterize_rgba(
        document(tmp_path, '<rect x="10" y="10" width="40" height="4"/>'), dpi=305
    )
    mask = rgba[..., 3] >= 128
    params, cache = StitchParams(), {}
    for source in (mask, mask.copy(), np.roll(mask, 12, axis=1)):
        consistency.select_consistent_regions(
            source, transform, params, [40, 35], [], geometry_cache=cache
        )
    assert calls == 2


def test_preferred_nike_replaces_incomplete_mat_with_audited_directional_satin(tmp_path):
    source = Path(__file__).resolve().parents[1] / "examples/nike.svg"
    params = StitchParams.for_fabric(
        "stable", machine="brother-skitch-pp1", auto_strategy="satin_preferred"
    )
    prepared, _, _ = prepare_artwork(
        source,
        tmp_path,
        GenerationParams(design_width_mm=80, fit_to_hoop=True),
        params,
        preserve_colors=True,
    )
    plan, _ = digitize(load_svg_paths(prepared)[0], params)
    body = max(plan.decisions, key=lambda d: d["area_mm2"])
    assert body["mat_evaluated"]
    assert body["method"] == "satin"
    assert body["reason"] == "complete_directional_columns"
    assert body["directional_satin_columns"] == 3
    assert body["candidates"]["satin"]["structural_coverage"] < 0.999
    directional = body["candidates"]["directional_satin"]
    assert directional["structural_coverage"] >= 0.999
    assert directional["crowded_satin_penetrations"] == directional["unsafe_connections"] == 0
    assert_machine_quality(plan)


def test_equivalent_fallback_satin_regions_keep_the_same_direction_and_foundation(tmp_path):
    svg = document(
        tmp_path,
        '<path d="M5 5H30V9H9V30H5Z"/><path d="M75 65H50V61H71V40H75Z"/>',
    )
    params = StitchParams.for_fabric("stable", machine="brother-skitch-pp1", stitch_type="satin")
    plan, _ = digitize(svg, params)
    assert {d["method"] for d in plan.decisions} == {"satin"}
    assert {d["reason"] for d in plan.decisions} == {"complete_directional_columns"}
    assert len({d["equivalence_group"] for d in plan.decisions}) == 1
    assert len({d["canonical_satin_angle_deg"] for d in plan.decisions}) == 1
    assert len({d["satin_angle_deg"] for d in plan.decisions}) == 1
    assert len({d["underlay_strategy"] for d in plan.decisions}) == 1
    assert_machine_quality(plan)


def _recommendation_candidate(identifier, **overrides):
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


@pytest.mark.parametrize("identifier", ["satin_preferred", "uniform_satin"])
@pytest.mark.parametrize("improved_rank", [False, True])
@pytest.mark.parametrize(
    "old_peak,new_peak,accepted", [(2, 3, False), (1, 2, True), (3, 3, True), (3, 4, False)]
)
def test_satin_recommendation_preserves_top_visit_limit_even_with_better_safety_rank(
    identifier, improved_rank, old_peak, new_peak, accepted
):
    balanced = _recommendation_candidate(
        "balanced",
        status="needs_review" if improved_rank else "geometric_checks_passed",
        max_top_penetration_multiplicity=old_peak,
    )
    satin = _recommendation_candidate(
        identifier,
        method_area_mm2={"satin": 20, "fill": 80, "running": 0, "omitted": 0},
        max_top_penetration_multiplicity=new_peak,
    )
    if improved_rank:
        assert variants._safety_rank(satin.quality) < variants._safety_rank(balanced.quality)
    else:
        assert variants._safety_rank(satin.quality) == variants._safety_rank(balanced.quality)
    assert variants.recommend_variant([balanced, satin]) == (identifier if accepted else "balanced")


@pytest.mark.parametrize("identifier", ["satin_preferred", "uniform_satin"])
@pytest.mark.parametrize("missing", ["both", "reference", "candidate"])
def test_satin_recommendation_keeps_compatibility_with_missing_optional_visit_metrics(
    identifier, missing
):
    balanced = _recommendation_candidate("balanced", max_top_penetration_multiplicity=2)
    satin = _recommendation_candidate(
        identifier,
        method_area_mm2={"satin": 20, "fill": 80, "running": 0, "omitted": 0},
        max_top_penetration_multiplicity=3,
    )
    if missing in ("both", "reference"):
        balanced.quality.pop("max_top_penetration_multiplicity")
    if missing in ("both", "candidate"):
        satin.quality.pop("max_top_penetration_multiplicity")
    assert variants.recommend_variant([balanced, satin]) == identifier


@pytest.mark.parametrize("identifier", ["satin_preferred", "uniform_satin"])
@pytest.mark.parametrize("improved_rank", [False, True])
@pytest.mark.parametrize(
    "candidate_peaks,accepted",
    [
        ({"#0000ff": 1, "#ff0000": 3}, False),
        ({"#0000ff": 3, "#ff0000": 2}, True),
    ],
)
def test_satin_recommendation_matches_thread_colors_instead_of_palette_positions(
    identifier, improved_rank, candidate_peaks, accepted
):
    balanced = _recommendation_candidate(
        "balanced",
        status="needs_review" if improved_rank else "geometric_checks_passed",
        max_top_penetration_multiplicity=3,
        top_penetration_multiplicity_by_color={"#ff0000": 2, "#0000ff": 3},
    )
    satin = _recommendation_candidate(
        identifier,
        method_area_mm2={"satin": 20, "fill": 80, "running": 0, "omitted": 0},
        max_top_penetration_multiplicity=3,
        top_penetration_multiplicity_by_color=candidate_peaks,
    )
    assert variants.recommend_variant([balanced, satin]) == (identifier if accepted else "balanced")


def test_variant_quality_uses_per_thread_top_visits_without_aggregating_shared_coordinates():
    commands = [
        [0, 0, pe.JUMP],
        [10, 10, pe.STITCH],
        [20, 20, pe.STITCH],
        [10, 10, pe.STITCH],
        [10, 10, pe.COLOR_CHANGE],
        [10, 10, pe.JUMP],
        [10, 10, pe.STITCH],
        [30, 30, pe.STITCH],
        [10, 10, pe.STITCH],
        [30, 30, pe.STITCH],
        [10, 10, pe.STITCH],
        [10, 10, pe.END],
    ]
    blocks = [
        StitchBlock(
            "satin", np.asarray(commands[:4])[:, :2] / 10, 0, command_range=(0, 4), color_index=0
        ),
        StitchBlock(
            "fill", np.asarray(commands[5:11])[:, :2] / 10, 1, command_range=(5, 11), color_index=1
        ),
    ]
    plan = StitchPlan(commands, blocks, (0, 0), {}, threads=["#ff0000", "#0000ff"])
    quality = variants._quality(plan, [])
    assert max_top_penetration_multiplicity(plan) == 5
    assert quality["max_top_penetration_multiplicity"] == 3
    assert quality["top_penetration_multiplicity_by_color"] == {"#ff0000": 2, "#0000ff": 3}
