from copy import deepcopy

from embroidery_rungs.routing import _dist, _endpoints, route_columns


def travel(elements):
    ends = [_endpoints(e) for e in elements]
    return sum(_dist(ends[i][1], ends[i + 1][0]) for i in range(len(ends) - 1))


def test_routing_preserves_elements_and_never_increases_travel():
    elements = [
        {"type": "running", "points": [(x, 0), (x + 2, 0)]} for x in [0, 50, 10, 40, 20, 30]
    ]
    original = deepcopy(elements)
    routed = route_columns(elements)
    assert elements == original
    assert len(routed) == len(elements)
    assert travel(routed) <= travel(elements)
    assert {tuple(sorted(e["points"])) for e in routed} == {tuple(e["points"]) for e in elements}
