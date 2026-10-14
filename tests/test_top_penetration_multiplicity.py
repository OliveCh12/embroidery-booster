import numpy as np
import pyembroidery as pe
import pytest

from embroidery_rungs.stitching.planner import StitchBlock, StitchPlan
from embroidery_rungs.stitching.quality import max_top_penetration_multiplicity


def block(kind, command_range=None, *, closed=False, color_index=0):
    return StitchBlock(
        kind,
        np.zeros((3, 2)),
        0,
        color_index=color_index,
        command_range=command_range,
        closed=closed,
    )


def plan(commands, blocks):
    return StitchPlan(commands, blocks, (0, 0), {})


@pytest.mark.parametrize("kind", ["satin", "fill"])
def test_counts_emitted_integer_tenths_instead_of_block_points(kind):
    actual = plan(
        [[0, 0, pe.JUMP], [10, 10, pe.STITCH], [11, 10, pe.STITCH]],
        [block(kind, (0, 3))],
    )
    assert max_top_penetration_multiplicity(actual) == 1


def test_context_locks_travel_underlay_and_running_do_not_increase_top_visits():
    commands = [
        [10, 10, pe.STITCH],
        [10, 10, pe.STITCH],
        [20, 20, pe.STITCH],
        [10, 10, pe.STITCH],
        [10, 10, pe.STITCH],
        [30, 30, pe.STITCH],
        [10, 10, pe.STITCH],
        *[[10, 10, pe.STITCH] for _ in range(12)],
        [10, 10, pe.END],
    ]
    actual = plan(
        commands,
        [
            block("satin", (0, 4)),
            block("fill", (4, 7)),
            block("lock", (6, 10)),
            block("travel", (9, 13)),
            block("underlay", (12, 16)),
            block("running", (15, 19)),
        ],
    )
    assert max_top_penetration_multiplicity(actual) == 3


def test_overlapping_top_ranges_count_each_command_index_once():
    actual = plan(
        [
            [0, 0, pe.JUMP],
            [5, 5, pe.STITCH],
            [8, 8, pe.STITCH],
            [5, 5, pe.STITCH],
            [8, 8, pe.STITCH],
            [8, 8, pe.TRIM],
        ],
        [block("satin", (0, 4)), block("fill", (1, 5))],
    )
    assert max_top_penetration_multiplicity(actual) == 2


def test_color_filter_isolates_visits_at_shared_coordinates_and_overlapping_ranges():
    actual = plan(
        [
            [0, 0, pe.JUMP],
            [10, 10, pe.STITCH],
            [20, 20, pe.STITCH],
            [10, 10, pe.STITCH],
            [10, 10, pe.STITCH],
            [10, 10, pe.STITCH],
            [10, 10, pe.END],
        ],
        [block("satin", (0, 4), color_index=0), block("fill", (2, 6), color_index=1)],
    )
    assert max_top_penetration_multiplicity(actual) == 4
    assert max_top_penetration_multiplicity(actual, color_index=0) == 2
    assert max_top_penetration_multiplicity(actual, color_index=1) == 3
    assert max_top_penetration_multiplicity(actual, color_index=2) == 0


def test_a_real_closure_visit_counts_without_adding_context():
    actual = plan(
        [
            [0, 0, pe.JUMP],
            [0, 0, pe.STITCH],
            [10, 0, pe.STITCH],
            [10, 10, pe.STITCH],
            [0, 0, pe.STITCH],
            [0, 0, pe.TRIM],
            [0, 0, pe.END],
        ],
        [block("satin", (0, 5), closed=True)],
    )
    assert max_top_penetration_multiplicity(actual) == 2


def test_only_actual_stitch_codes_inside_top_ranges_are_counted():
    actual = plan(
        [
            [10, 10, pe.STITCH],
            [10, 10, pe.STITCH],
            [10, 10, pe.JUMP],
            [10, 10, pe.TRIM],
            [10, 10, pe.COLOR_CHANGE],
            [10, 10, pe.STITCH | (1 << 16)],
            [20, 20, pe.STITCH],
            [10, 10, pe.END],
        ],
        [block("satin", (0, 8))],
    )
    assert max_top_penetration_multiplicity(actual) == 2


@pytest.mark.parametrize(
    "commands,blocks",
    [
        ([], []),
        ([[0, 0, pe.STITCH]], []),
        ([[0, 0, pe.STITCH]], [block("satin")]),
        ([[0, 0, pe.JUMP]], [block("fill", (-1, 1))]),
    ],
)
def test_absent_top_stitches_have_zero_multiplicity(commands, blocks):
    assert max_top_penetration_multiplicity(plan(commands, blocks)) == 0
