"""Subresolution colours must be reported, not abort or disappear from the audit."""

import numpy as np
import pyembroidery as pe
import pytest

from embroidery_rungs import StitchParams
from embroidery_rungs.stitching.digitizer import digitize
from embroidery_rungs.stitching.planner import UnstitchableRegion
from embroidery_rungs.svg_manager import load_svg_paths


def _document(tmp_path, body):
    source = tmp_path / "small-colours.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="70mm" '
        f'viewBox="0 0 80 70">{body}</svg>'
    )
    return load_svg_paths(source)[0]


def test_whole_unsewable_colour_retains_missing_coverage_and_contiguous_ids(tmp_path):
    details = "".join(
        f'<rect x="{60 + x}" y="20" width=".08" height=".08" fill="#ff0000"/>' for x in range(12)
    )
    document = _document(
        tmp_path,
        '<rect x="10" y="30" width="40" height="4" fill="#0000ff"/>'
        '<rect x="10" y="40" width="40" height="4" fill="#00ff00"/>' + details,
    )
    plan, diagnostics = digitize(document, StitchParams())
    omitted = [d for d in diagnostics if d.get("omitted")]
    assert len(omitted) == 1
    assert omitted[0]["color"] == "#ff0000"
    assert omitted[0]["coverage"] == omitted[0]["structural_coverage"] == 0
    assert omitted[0]["structural_missing_mm2"] > 0
    assert plan.stats["structural_missing_mm2"] >= omitted[0]["structural_missing_mm2"]
    assert plan.stats["largest_gap_mm2"] >= omitted[0]["largest_gap_mm2"]
    assert plan.stats["omitted_colors"] == 1
    assert plan.stats["colors"] == 2
    assert plan.stats["color_changes"] == 1
    assert plan.threads == [d["color"] for d in diagnostics if not d.get("omitted")]
    assert any("Colour #ff0000" in warning and "omitted" in warning for warning in plan.warnings)
    assert [d["component"] for d in plan.decisions] == list(range(1, len(plan.decisions) + 1))
    assert all(d["color_index"] is None for d in plan.decisions if d["method"] == "omitted")
    commands = np.asarray(plan.commands)
    assert np.count_nonzero(commands[:, 2] == pe.COLOR_CHANGE) == 1
    assert commands[-1, 2] == pe.END


def test_no_stitchable_colour_has_clear_error(tmp_path):
    document = _document(tmp_path, '<rect x="60" y="20" width=".08" height=".08"/>')
    with pytest.raises(UnstitchableRegion, match="No colour.*enlarge"):
        digitize(document, StitchParams())
