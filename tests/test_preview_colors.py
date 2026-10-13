from xml.etree import ElementTree as ET

import numpy as np
import pyembroidery as pe

from embroidery_rungs.stitching.export import _preview_svg
from embroidery_rungs.stitching.planner import StitchBlock, StitchPlan


def test_static_preview_uses_active_thread_for_all_sewn_phases_and_omits_jumps(tmp_path):
    plan = StitchPlan(
        commands=[
            [10, 10, pe.JUMP],
            [10, 10, pe.STITCH],
            [20, 10, pe.STITCH],
            [20, 20, pe.STITCH],
            [20, 10, pe.STITCH],
            [20, 10, pe.TRIM],
            [20, 10, pe.COLOR_CHANGE],
            [70, 70, pe.JUMP],
            [70, 70, pe.STITCH],
            [80, 70, pe.STITCH],
            [80, 70, pe.TRIM],
            [90, 90, pe.JUMP],
            [90, 90, pe.STITCH],
            [95, 90, pe.STITCH],
            [95, 90, pe.END],
        ],
        blocks=[
            StitchBlock("underlay", np.array([[1, 1], [2, 1]]), 0),
            StitchBlock("travel", np.array([[2, 1], [2, 2]]), 0),
            StitchBlock("lock", np.array([[2, 2], [2, 1]]), 0),
            StitchBlock("fill", np.array([[7, 7], [8, 7]]), 1, color_index=1),
        ],
        origin_mm=(0, 0),
        stats={},
        threads=["#ff0000", "#0000ff"],
    )
    path = tmp_path / "preview.svg"
    _preview_svg(plan, (10, 10), path)
    paths = ET.parse(path).findall("{http://www.w3.org/2000/svg}path")
    assert [p.attrib["stroke"] for p in paths] == plan.threads
    assert paths[0].attrib["d"] == "M1.00,1.00 L2.00,1.00 L2.00,2.00 L2.00,1.00"
    assert paths[1].attrib["d"] == "M7.00,7.00 L8.00,7.00 M9.00,9.00 L9.50,9.00"
    assert all("stroke-dasharray" not in p.attrib for p in paths)
