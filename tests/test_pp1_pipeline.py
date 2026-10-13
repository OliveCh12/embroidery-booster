import json
from pathlib import Path

import numpy as np
import pyembroidery as pe

from embroidery_rungs import StitchParams, generate


def test_pp1_combines_satin_and_fill_without_an_extra_spool_change(tmp_path):
    source = tmp_path / "mixed.svg"
    source.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="80mm" height="80mm" '
        'viewBox="0 0 80 80" fill="#000000">'
        '<rect x="8" y="10" width="4" height="42"/>'
        '<rect x="30" y="25" width="24" height="20"/></svg>'
    )
    direct = generate(
        source,
        tmp_path / "out",
        stitch_params=StitchParams.for_fabric("stable", machine="brother-skitch-pp1"),
    ).direct
    assert {decision["method"] for decision in direct.decisions} == {"satin", "fill"}
    assert len(direct.threads) == 1
    assert direct.stats["color_changes"] == 0
    assert direct.stats["structural_coverage"] >= 0.995
    assert direct.stats["unsafe_connections"] == 0
    assert direct.stats["short_stitches"] == 0
    assert direct.stats["max_stitch_mm"] <= direct.params.max_stitch_mm
    commands = np.asarray(json.loads(Path(direct.plan_path).read_text())["commands"])
    expected = commands[commands[:, 2] == pe.STITCH, :2]
    for path in (direct.pes_path, direct.dst_path):
        stitches = np.asarray(pe.read(path).stitches)
        codes = stitches[:, 2].astype(int) & pe.COMMAND_MASK
        assert np.array_equal(stitches[codes == pe.STITCH, :2], expected)
        assert not np.any(codes == pe.COLOR_CHANGE)
        assert np.max(np.abs(expected)) <= 500
