import pytest

from embroidery_rungs.stitching import consistency, selection
from embroidery_rungs.stitching.params import StitchParams
from embroidery_rungs.stitching.planner import CandidateGeometryError
from embroidery_rungs.svg_manager import load_svg_paths


def _columns(tmp_path):
    source = tmp_path / "columns.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="50mm" '
        'viewBox="0 0 80 50"><rect x="5" y="5" width="35" height="3"/>'
        '<rect x="40" y="35" width="35" height="3"/></svg>'
    )
    svg, _ = load_svg_paths(source)
    from embroidery_rungs.image_processor import rasterize_rgba

    rgba, transform = rasterize_rgba(svg, dpi=305)
    return rgba[..., 3] >= 128, transform


def test_rejected_real_grid_satin_switches_the_whole_cohort_to_safe_fill(tmp_path, monkeypatch):
    real = consistency.build_stitch_plan

    def reject_satin(elements, *args, **kwargs):
        if any(element["type"] == "satin" for element in elements):
            raise CandidateGeometryError("Quantized stitches leave their regions.")
        return real(elements, *args, **kwargs)

    monkeypatch.setattr(consistency, "build_stitch_plan", reject_satin)
    mask, transform = _columns(tmp_path)
    selected, decisions = consistency.select_consistent_regions(
        mask, transform, StitchParams(), [40, 25], []
    )
    assert selected
    assert len(decisions) == 2
    assert {decision["method"] for decision in decisions} == {"fill"}
    assert len({decision["equivalence_group"] for decision in decisions}) == 1


def test_rejected_fill_is_reported_as_omitted_instead_of_exported(tmp_path, monkeypatch):
    def reject(*args, **kwargs):
        raise CandidateGeometryError("Quantized stitches leave their regions.")

    monkeypatch.setattr(consistency, "build_stitch_plan", reject)
    mask, transform = _columns(tmp_path)
    selected, decisions = consistency.select_consistent_regions(
        mask, transform, StitchParams(stitch_type="fill"), [40, 25], []
    )
    assert not selected
    assert {decision["method"] for decision in decisions} == {"omitted"}
    assert all("Quantized stitches leave" in d["actual_top_metrics"]["error"] for d in decisions)


def test_local_fill_geometry_rejection_is_recorded(tmp_path, monkeypatch):
    def reject(*args, **kwargs):
        raise CandidateGeometryError("Quantized stitches leave their regions.")

    monkeypatch.setattr(selection, "build_stitch_plan", reject)
    mask, transform = _columns(tmp_path)
    selected, decisions = selection.select_stitch_types(
        [], mask, transform, StitchParams(stitch_type="fill"), origin_mm=[40, 25]
    )
    assert not selected
    assert {decision["method"] for decision in decisions} == {"omitted"}
    assert all("Quantized stitches leave" in d["candidates"]["fill"]["error"] for d in decisions)


def test_candidate_audit_preserves_fatal_budget_and_hoop_errors(tmp_path, monkeypatch):
    def reject(*args, **kwargs):
        raise ValueError("Stitch budget exceeded")

    monkeypatch.setattr(consistency, "build_stitch_plan", reject)
    mask, transform = _columns(tmp_path)
    with pytest.raises(ValueError, match="Stitch budget exceeded"):
        consistency.select_consistent_regions(
            mask, transform, StitchParams(stitch_type="fill"), [40, 25], []
        )
