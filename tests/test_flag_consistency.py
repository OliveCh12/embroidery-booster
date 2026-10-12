"""A multicolor half-turn fixture checks policies and actual exported stitches."""

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pyembroidery as pe
import pytest
from scipy.ndimage import distance_transform_edt, label

from embroidery_rungs import GenerationParams, StitchParams, generate
from embroidery_rungs.colors import separate_colors
from embroidery_rungs.image_processor import rasterize_rgba
from embroidery_rungs.svg_manager import UNITS_PER_MM, load_svg_paths

FLAG = Path(__file__).resolve().parents[1] / "examples/quality/union-jack.svg"


def _regions_and_segments(document, data):
    svg, _ = load_svg_paths(document)
    rgba, transform = rasterize_rgba(svg, 305)
    labels, colors, _ = separate_colors(rgba, data["params"]["max_colors"])
    inverse = ~transform
    matrix = np.array([[inverse.a, inverse.b], [inverse.c, inverse.d]]) / UNITS_PER_MM
    offset = np.array([inverse.e, inverse.f]) / UNITS_PER_MM
    commands = np.asarray(data["commands"])
    codes = commands[:, 2].astype(int) & pe.COMMAND_MASK
    points = commands[:, :2] / 10 + data["origin_mm"]
    vectors = np.diff(points, axis=0)
    midpoints = (points[:-1] + points[1:]) / 2
    pixels = np.rint(
        midpoints
        * UNITS_PER_MM
        @ np.array([[transform.a, transform.b], [transform.c, transform.d]])
        + [transform.e, transform.f]
    ).astype(int)
    pixels[:, 0] = pixels[:, 0].clip(0, labels.shape[1] - 1)
    pixels[:, 1] = pixels[:, 1].clip(0, labels.shape[0] - 1)
    top = np.zeros(len(commands), dtype=bool)
    kinds = np.full(len(commands), "", dtype=object)
    for run in data["top_layer_runs"]:
        top[run["start"] : run["end"]] = True
        kinds[run["start"] : run["end"]] = run["kind"]
    sewn = (codes[:-1] == pe.STITCH) & (codes[1:] == pe.STITCH)
    color_ids = np.cumsum(codes == pe.COLOR_CHANGE)[:-1]
    regions = []
    segments = defaultdict(dict)
    for color_index, color in enumerate(colors, 1):
        components, count = label(labels == color_index)
        nearest = distance_transform_edt(
            components == 0, return_distances=False, return_indices=True
        )
        assigned = components[
            nearest[0, pixels[:, 1], pixels[:, 0]], nearest[1, pixels[:, 1], pixels[:, 0]]
        ]
        for component in range(1, count + 1):
            decision = next(
                d
                for d in data["decisions"]
                if d["color"] == color and d["source_component"] == component
            )
            ys, xs = np.nonzero(components == component)
            regions.append(
                {**decision, "centroid": np.array([xs.mean(), ys.mean()]) @ matrix + offset}
            )
            selected = sewn & (assigned == component) & (color_ids == data["threads"].index(color))
            top_segments = selected & top[:-1] & top[1:]
            segments[decision["component"]] = {
                "top": vectors[top_segments],
                "kinds": set(kinds[:-1][top_segments]),
                "support": vectors[selected & ~top[:-1] & ~top[1:]],
            }
    ys, xs = np.nonzero(labels)
    center = np.array([(xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2]) @ matrix + offset
    return regions, segments, center


def _aligned_fraction(vectors, angle, *, minimum=2.0, minimum_count=4):
    lengths = np.linalg.norm(vectors, axis=1)
    vectors, lengths = vectors[lengths > minimum], lengths[lengths > minimum]
    assert len(vectors) >= minimum_count
    radians = np.radians(angle)
    normal = np.array([-np.sin(radians), np.cos(radians)])
    aligned = np.abs(vectors @ normal) / lengths < np.sin(np.radians(4))
    return lengths[aligned].sum() / lengths.sum()


@pytest.mark.parametrize("width", [80, 94])
def test_union_jack_half_turn_policy_matches_actual_machine_stitches(tmp_path, width):
    settings = StitchParams.for_fabric(
        "stable", machine="brother-skitch-pp1", stabilizer="cutaway", thread_weight=40
    )
    result = generate(
        FLAG,
        tmp_path / "flag",
        GenerationParams(design_width_mm=width),
        method="direct",
        stitch_params=settings,
    )
    direct = result.direct
    data = json.loads(Path(direct.plan_path).read_text())
    assert set(data["threads"]) == {"#c8102e", "#ffffff", "#012169"}
    assert direct.stats["color_changes"] == 2
    assert direct.stats["omitted_regions"] == 0
    assert direct.stats["structural_coverage"] >= 0.999
    assert direct.stats["largest_gap_mm2"] <= 0.05
    assert direct.stats["crowded_satin_penetrations"] == 0
    commands = np.asarray(data["commands"])
    sewn = (commands[:-1, 2] == pe.STITCH) & (commands[1:, 2] == pe.STITCH)
    lengths = np.linalg.norm(np.diff(commands[:, :2], axis=0), axis=1)[sewn] / 10
    assert lengths.min() >= settings.min_stitch_mm - 0.001
    assert lengths.max() <= settings.max_stitch_mm + 0.001
    for path in (direct.pes_path, direct.dst_path):
        machine = pe.read(path)
        actual = np.asarray(machine.stitches)
        codes = actual[:, 2].astype(int) & pe.COMMAND_MASK
        np.testing.assert_array_equal(
            actual[codes == pe.STITCH, :2], commands[commands[:, 2] == pe.STITCH, :2]
        )
        assert np.count_nonzero(codes == pe.COLOR_CHANGE) == 2
    assert [thread.hex_color().lower() for thread in pe.read(direct.pes_path).threadlist] == data[
        "threads"
    ]

    regions, segments, center = _regions_and_segments(result.original_path, data)
    pairs = 0
    for first in regions:
        candidates = [region for region in regions if region["color"] == first["color"]]
        second = min(
            candidates,
            key=lambda region: np.linalg.norm(
                region["centroid"] - (2 * center - first["centroid"])
            ),
        )
        if first["component"] >= second["component"]:
            continue
        pairs += 1
        assert np.linalg.norm(second["centroid"] - (2 * center - first["centroid"])) < 0.3
        assert first["equivalence_group"] == second["equivalence_group"]
        assert first["equivalent_regions"] >= 2
        for key in (
            "method",
            "satin_spacing_mm",
            "fill_spacing_mm",
            "pull_compensation_mm",
            "underlay",
            "underlay_strategy",
        ):
            assert first[key] == second[key], (first["component"], second["component"], key)
        for region in (first, second):
            actual = segments[region["component"]]
            assert actual["kinds"] == {region["method"]}
            assert region["actual_top_metrics"]["structural_coverage"] >= 0.999
            if region["method"] == "fill":
                # Inspect long emitted tatami rows, excluding short finish contours.
                assert _aligned_fraction(actual["top"], region["fill_angle_deg"]) > 0.85
                if "cross" in region["underlay_strategy"]:
                    # Support includes edge walks and travel as well as cross
                    # rows; the cross foundation need not dominate a narrow arm.
                    assert (
                        _aligned_fraction(
                            actual["support"],
                            region["fill_angle_deg"] + 90,
                            minimum=1.5,
                            minimum_count=1,
                        )
                        > 0.1
                    )
        if first["method"] == "fill":
            assert first["fill_angle_deg"] % 180 == pytest.approx(second["fill_angle_deg"] % 180)
    assert pairs == 8
