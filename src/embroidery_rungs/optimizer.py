"""Linear-time checkpoint selection on precomputed rails."""

from __future__ import annotations

import numpy as np


def checkpoint_indices(centers, widths, max_gap: float, adaptive: bool = False) -> list[int]:
    """Bound arc gaps and refine bends/width changes, without repeated geometry.

    Spacing / density is the maximum checkpoint gap, not stitch spacing. In
    auto mode, 15-degree turns and 15% width changes get extra checkpoints.
    At least three checkpoints avoid ambiguous two-rail/two-rung Ink/Stitch paths.
    """
    n = len(centers)
    if n <= 3:
        return list(range(n))
    arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(centers, axis=0), axis=1))]
    tangent = np.gradient(centers, axis=0)
    angles = np.unwrap(np.arctan2(tangent[:, 1], tangent[:, 0]))
    selected = [0]
    angle_limit, width_limit = (np.radians(15), 0.15) if adaptive else (np.radians(30), 0.3)
    for i in range(1, n - 1):
        last = selected[-1]
        # Look one node ahead to avoid overshooting the maximum spacing.
        if (
            arc[i + 1] - arc[last] > max_gap
            or abs(angles[i] - angles[last]) >= angle_limit
            or abs(widths[i] - widths[last]) > width_limit * max(widths[last], 1.0)
        ):
            selected.append(i)
    selected.append(n - 1)
    if len(selected) == 2:
        selected.insert(1, n // 2)
    return selected
