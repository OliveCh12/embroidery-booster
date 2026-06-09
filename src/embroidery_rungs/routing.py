"""Order satin columns to minimize travel (jump) stitches.

Ink/Stitch stitches objects in document order, jumping from the end of one
satin column to the start of the next. Each column can be entered from either
end, so this is a path-TSP with two-state nodes. We solve it with nearest
-neighbour + 2-opt, which is fast (tens of columns) and near-optimal in
practice. The result is the same columns, reordered and individually reversed
so the design stitches with the shortest possible travel.
"""

import math
import logging

logger = logging.getLogger(__name__)


def _dist(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _endpoints(column):
    """Centre of each cap of a column: (start, end) in image coords."""
    a0, b0 = column["rail_a"][0], column["rail_b"][0]
    a1, b1 = column["rail_a"][-1], column["rail_b"][-1]
    start = ((a0[0] + b0[0]) / 2.0, (a0[1] + b0[1]) / 2.0)
    end = ((a1[0] + b1[0]) / 2.0, (a1[1] + b1[1]) / 2.0)
    return start, end


def _total_travel(seq):
    return sum(_dist(seq[k]["exit"], seq[k + 1]["enter"]) for k in range(len(seq) - 1))


def _nearest_neighbour(ends):
    """Greedy chain. ``ends[i] = (start, end)``. Returns a sequence of dicts."""
    n = len(ends)
    visited = [False] * n

    # Start from the top-left-most endpoint (a natural origin for embroidery).
    start_col, start_end = min(
        ((i, k) for i in range(n) for k in (0, 1)),
        key=lambda t: ends[t[0]][t[1]][0] + ends[t[0]][t[1]][1])

    seq = []

    def visit(i, enter_k):
        visited[i] = True
        enter, exit_ = ends[i][enter_k], ends[i][1 - enter_k]
        seq.append({"col": i, "rev": enter_k == 1, "enter": enter, "exit": exit_})
        return exit_

    current = visit(start_col, start_end)
    for _ in range(n - 1):
        best_i, best_k, best_d = -1, 0, math.inf
        for i in range(n):
            if visited[i]:
                continue
            for k in (0, 1):
                d = _dist(current, ends[i][k])
                if d < best_d:
                    best_i, best_k, best_d = i, k, d
        current = visit(best_i, best_k)
    return seq


def _two_opt(seq, max_passes=20):
    """Improve the chain in place. Reversing a sub-path flips each column's
    direction; internal jumps are preserved, so only the two boundary jumps of
    a reversed segment change (cheap delta)."""
    n = len(seq)
    for _ in range(max_passes):
        improved = False
        for i in range(n - 1):
            for j in range(i + 1, n):
                old = (_dist(seq[i - 1]["exit"], seq[i]["enter"]) if i > 0 else 0.0)
                old += (_dist(seq[j]["exit"], seq[j + 1]["enter"]) if j < n - 1 else 0.0)
                new = (_dist(seq[i - 1]["exit"], seq[j]["exit"]) if i > 0 else 0.0)
                new += (_dist(seq[i]["enter"], seq[j + 1]["enter"]) if j < n - 1 else 0.0)
                if new + 1e-9 < old:
                    segment = seq[i:j + 1][::-1]
                    for e in segment:
                        e["rev"] = not e["rev"]
                        e["enter"], e["exit"] = e["exit"], e["enter"]
                    seq[i:j + 1] = segment
                    improved = True
        if not improved:
            break
    return seq


def route_columns(columns):
    """Reorder and reverse columns to minimize travel between them."""
    if len(columns) <= 1:
        return columns

    ends = [_endpoints(c) for c in columns]

    # Baseline: travel in the original document order (each entered at its start).
    baseline = sum(_dist(ends[k][1], ends[k + 1][0]) for k in range(len(ends) - 1))

    seq = _nearest_neighbour(ends)
    _two_opt(seq)
    after = _total_travel(seq)
    pct = 100 * (baseline - after) / baseline if baseline > 1e-6 else 0.0
    logger.info(f"Routed {len(columns)} satin columns: "
                f"travel {baseline:.0f}px -> {after:.0f}px (-{pct:.0f}%)")

    ordered = []
    for e in seq:
        c = columns[e["col"]]
        if e["rev"]:
            ordered.append({
                "rail_a": c["rail_a"][::-1],
                "rail_b": c["rail_b"][::-1],
                "rungs": list(reversed(c["rungs"])),
            })
        else:
            ordered.append(c)
    return ordered
