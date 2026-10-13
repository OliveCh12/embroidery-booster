from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from embroidery_rungs import GenerationParams
from embroidery_rungs.image_processor import rasterize_rgba
from embroidery_rungs.inputs import prepare_artwork
from embroidery_rungs.stitching import consistency, selection
from embroidery_rungs.stitching.digitizer import digitize
from embroidery_rungs.stitching.params import StitchParams
from embroidery_rungs.stitching.planner import CandidateGeometryError, build_stitch_plan
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


def test_preferred_nike_retains_fill_when_satin_coverage_and_regularity_fail(tmp_path):
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
    assert body["method"] == "fill"
    satin = body["candidates"]["satin"]
    assert satin["structural_coverage"] < 0.999
    assert satin["crowded_satin_penetrations"] > 0
    assert_machine_quality(plan)
