"""Array-based skeleton topology; never connect across background."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import label

_OFFSETS = np.array([(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)])


def get_skeleton_paths(skeleton, min_len_px=2.0, distance=None):
    """Trace each edge once, including disconnected loops; prune radius-sized spurs.

    Diagonal shortcuts around orthogonal connections create false triangular
    junctions. Omit them and give adjacent junction pixels a shared vertex.
    """
    rc = np.argwhere(skeleton)
    if not len(rc):
        return []
    grid = np.full(skeleton.shape, -1, dtype=np.int32)
    grid[tuple(rc.T)] = np.arange(len(rc))
    neighbors = np.full((len(rc), 8), -1, dtype=np.int32)
    h, w = skeleton.shape
    for k, (dr, dc) in enumerate(_OFFSETS):
        r, c = rc[:, 0] + dr, rc[:, 1] + dc
        valid = (r >= 0) & (r < h) & (c >= 0) & (c < w)
        if dr and dc:
            valid &= grid[np.clip(r, 0, h - 1), rc[:, 1]] < 0
            valid &= grid[rc[:, 0], np.clip(c, 0, w - 1)] < 0
        neighbors[valid, k] = grid[r[valid], c[valid]]
    degree = (neighbors >= 0).sum(axis=1)
    junction_img = np.zeros_like(skeleton, dtype=bool)
    junction_img[tuple(rc[degree > 2].T)] = True
    groups, count = label(junction_img, structure=np.ones((3, 3)))
    vertex = np.arange(len(rc), dtype=np.int32) + count
    is_junction = degree > 2
    vertex[is_junction] = groups[tuple(rc[is_junction].T)] - 1
    positions = {int(vertex[i]): rc[i].astype(float) for i in np.flatnonzero(degree != 2)}
    if count:
        counts = np.bincount(vertex[is_junction], minlength=count)
        rows = np.bincount(vertex[is_junction], weights=rc[is_junction, 0], minlength=count)
        cols = np.bincount(vertex[is_junction], weights=rc[is_junction, 1], minlength=count)
        for g in range(count):
            positions[g] = np.array([rows[g], cols[g]]) / counts[g]
    visited = np.zeros_like(neighbors, dtype=bool)
    paths = []

    def trace(start, slot):
        nodes = [start]
        prev, curr = start, int(neighbors[start, slot])
        visited[start, slot] = True
        while True:
            visited[curr, np.flatnonzero(neighbors[curr] == prev)] = True
            nodes.append(curr)
            if degree[curr] != 2 or curr == start:
                break
            forward = np.flatnonzero((neighbors[curr] >= 0) & (neighbors[curr] != prev))[0]
            if visited[curr, forward]:
                break
            visited[curr, forward] = True
            prev, curr = curr, int(neighbors[curr, forward])
        a, b = int(vertex[start]), int(vertex[curr])
        # Ignore a shortcut inside one collapsed junction, but retain a real
        # loop that leaves the cluster and returns to another of its pixels.
        if a == b and start != curr and np.all(vertex[nodes] == a):
            return
        points = rc[nodes].astype(float)
        points[0], points[-1] = positions.get(a, points[0]), positions.get(b, points[-1])
        length = float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())
        if len(points) < 2 or length < min_len_px:
            return
        if distance is not None and (degree[start] == 1) != (degree[curr] == 1):
            j = curr if degree[start] == 1 else start
            if length <= max(min_len_px, 1.6 * distance[tuple(rc[j])]):
                return
        paths.append({"points": points, "start_node": a, "end_node": b})

    for node in np.flatnonzero(degree != 2):
        for slot in np.flatnonzero(neighbors[node] >= 0):
            if not visited[node, slot]:
                trace(int(node), int(slot))
    for node, slot in np.argwhere((neighbors >= 0) & ~visited):
        if not visited[node, slot]:
            trace(int(node), int(slot))
    return merge_aligned_paths(paths)


def merge_aligned_paths(paths):
    """Join the most aligned pair at each vertex without losing cycles."""
    adjacency = {}
    for i, path in enumerate(paths):
        for side, key in enumerate(("start_node", "end_node")):
            adjacency.setdefault(path[key], []).append((i, side))
    links = {}
    for ends in adjacency.values():
        candidates = []
        for i, (a, sa) in enumerate(ends):
            pa = paths[a]["points"][:: 1 if sa == 0 else -1]
            va = pa[min(8, len(pa) - 1)] - pa[0]
            va /= max(np.linalg.norm(va), 1e-9)
            for b, sb in ends[i + 1 :]:
                if a == b:
                    continue
                pb = paths[b]["points"][:: 1 if sb == 0 else -1]
                vb = pb[min(8, len(pb) - 1)] - pb[0]
                vb /= max(np.linalg.norm(vb), 1e-9)
                score = float(va @ vb)
                if score < -0.5 or len(ends) == 2:
                    candidates.append((score, a, sa, b, sb))
        for _, a, sa, b, sb in sorted(candidates):
            if (a, sa) not in links and (b, sb) not in links:
                links[a, sa], links[b, sb] = (b, sb), (a, sa)
    merged, used = [], set()
    starts = [(i, s) for i in range(len(paths)) for s in (0, 1) if (i, s) not in links]
    starts += [(i, 0) for i in range(len(paths))]
    for first, side in starts:
        if first in used:
            continue
        i, enter, parts = first, side, []
        start_node = paths[i]["start_node" if enter == 0 else "end_node"]
        while i not in used:
            used.add(i)
            pts = paths[i]["points"][:: 1 if enter == 0 else -1]
            parts.append(pts if not parts else pts[1:])
            end_node = paths[i]["end_node" if enter == 0 else "start_node"]
            next_end = links.get((i, 1 - enter))
            if next_end is None:
                break
            i, enter = next_end
        merged.append({"points": np.vstack(parts), "start_node": start_node, "end_node": end_node})
    return merged


def segments_intersect(p1, p2, p3, p4):
    """Strict interior crossing; endpoint touches and collinearity are allowed."""
    a, b, c, d = (np.asarray(p, dtype=float) for p in (p1, p2, p3, p4))
    u, v, offset = b - a, d - c, c - a
    denom = u[0] * v[1] - u[1] * v[0]
    if abs(denom) < 1e-10:
        return False
    t = (offset[0] * v[1] - offset[1] * v[0]) / denom
    s = (offset[0] * u[1] - offset[1] * u[0]) / denom
    return bool(1e-6 < t < 1 - 1e-6 and 1e-6 < s < 1 - 1e-6)
