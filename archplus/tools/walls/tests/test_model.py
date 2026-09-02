# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Pure wall-model tests: config inheritance, claim resolution, edge matching.
# model.py must stay importable without FreeCAD.

import pytest

from archplus.tools.walls import model


def _node(key, claimed=(), fallback=False, children=()):
    n = model.ClaimNode(key, claimed, fallback=fallback)
    n.children = list(children)
    return n


# --- effective_config ------------------------------------------------------

def test_config_leaf_overrides_parent():
    cfg = model.effective_config([
        {"Width": 200.0, "Height": None, "Align": "Inherit"},
        {"Width": 300.0, "Height": 2800.0, "Align": "Center"},
    ])
    assert cfg == {"Width": 200.0, "Height": 2800.0, "Align": "Center", "Offset": 0.0}


def test_config_zero_means_inherit():
    cfg = model.effective_config([
        {"Width": 0, "Height": 0, "Align": "Inherit"},
        {"Width": 400.0, "Height": 2600.0, "Align": "Left"},
    ])
    assert cfg["Width"] == 400.0 and cfg["Height"] == 2600.0 and cfg["Align"] == "Left"


def test_config_falls_back_to_defaults():
    cfg = model.effective_config([{"Width": None, "Height": None, "Align": None}])
    assert cfg == {"Width": 300.0, "Height": 2800.0, "Align": "Center", "Offset": 0.0}


def test_config_offset_comes_from_the_root_dict():
    cfg = model.effective_config([
        {"Width": 200.0},
        {"Width": 300.0, "Offset": 50.0},
    ])
    assert cfg["Offset"] == 50.0


# --- resolve_claims ----------------------------------------------------------

EDGES = ["Edge1", "Edge2", "Edge3", "Edge4"]


def test_fallback_child_claims_everything_unclaimed():
    fallback = _node("fallback", fallback=True)
    built, warnings = model.resolve_claims([fallback], EDGES)
    assert built[fallback.node] == frozenset(EDGES)
    assert warnings == []


def test_explicit_claim_beats_fallback():
    fallback = _node("fallback", fallback=True)
    ext = _node("ext", ("Edge1",))
    built, warnings = model.resolve_claims([fallback, ext], EDGES)
    assert built[ext.node] == frozenset(["Edge1"])
    assert built[fallback.node] == frozenset(["Edge2", "Edge3", "Edge4"])


def test_group_excludes_descendant_claims():
    fallback = _node("fallback", fallback=True)
    short = _node("short", ("Edge2",))
    fallback.children.append(short)
    built, warnings = model.resolve_claims([fallback], EDGES)
    assert built[short.node] == frozenset(["Edge2"])
    assert built[fallback.node] == frozenset(["Edge1", "Edge3", "Edge4"])


def test_conflicting_claims_build_nowhere_with_warning():
    a = _node("a", ("Edge1", "Edge2"))
    b = _node("b", ("Edge1",))
    built, warnings = model.resolve_claims([a, b], EDGES)
    assert built[a.node] == frozenset(["Edge2"])
    assert built[b.node] == frozenset()
    assert any("Edge1" in w for w in warnings)


def test_fallback_child_builds_nothing_on_conflicted_edges():
    fallback = _node("fallback", fallback=True)
    a = _node("a", ("Edge1",))
    b = _node("b", ("Edge1",))
    built, warnings = model.resolve_claims([fallback, a, b], EDGES)
    assert built[a.node] == frozenset()
    assert built[b.node] == frozenset()
    assert "Edge1" not in built[fallback.node]
    assert any("Edge1" in w for w in warnings)


def test_two_fallback_children_warns_and_keeps_first():
    r1 = _node("r1", fallback=True)
    r2 = _node("r2", fallback=True)
    built, warnings = model.resolve_claims([r1, r2], EDGES)
    assert built[r1.node] == frozenset(EDGES)
    assert built[r2.node] == frozenset()
    assert any("one fallback" in w for w in warnings)


def test_fallback_with_explicit_edges_warns_and_ignores_them():
    fallback = _node("fallback", ("Edge1",), fallback=True)
    built, warnings = model.resolve_claims([fallback], EDGES)
    assert built[fallback.node] == frozenset(EDGES)
    assert any("explicit" in w for w in warnings)


def test_nested_fallback_warns_and_treats_as_normal():
    fallback = _node("fallback", fallback=True)
    bad = _node("bad", ("Edge3",), fallback=True)
    fallback.children.append(bad)
    built, warnings = model.resolve_claims([fallback], EDGES)
    assert built[bad.node] == frozenset(["Edge3"])
    assert any("direct child" in w for w in warnings)


def test_no_fallback_leaves_new_edges_unbuilt():
    a = _node("a", ("Edge1",))
    built, warnings = model.resolve_claims([a], EDGES)
    assert built[a.node] == frozenset(["Edge1"])
    assert frozenset(["Edge2", "Edge3", "Edge4"]).isdisjoint(built[a.node])


def test_claim_on_missing_edge_warns_and_is_dropped():
    a = _node("a", ("Edge9",))
    built, warnings = model.resolve_claims([a], EDGES)
    assert built[a.node] == frozenset()
    assert any("Edge9" in w for w in warnings)


def test_descendant_claim_takes_the_edge_from_its_ancestor():
    group = _node("group", ("Edge1",))
    short = _node("short", ("Edge1",))
    group.children.append(short)
    built, warnings = model.resolve_claims([group], EDGES)
    assert built[short.node] == frozenset(["Edge1"])
    assert built[group.node] == frozenset()
    assert warnings == []


def test_unrelated_duplicate_claim_still_builds_nowhere():
    group = _node("group", ("Edge1",))
    short = _node("short", ("Edge1",))
    group.children.append(short)
    other = _node("other", ("Edge1",))
    built, warnings = model.resolve_claims([group, other], EDGES)
    assert built[group.node] == frozenset()
    assert built[short.node] == frozenset()
    assert built[other.node] == frozenset()
    assert any("Edge1" in w for w in warnings)


# --- match_edge --------------------------------------------------------------

def test_match_edge_finds_nearest_polyline():
    polylines = [
        [(0.0, 0.0, 0.0), (4000.0, 0.0, 0.0)],
        [(0.0, 3000.0, 0.0), (4000.0, 3000.0, 0.0)],
    ]
    assert model.match_edge(polylines, (2000.0, 3025.0, 0.0)) == 1
    assert model.match_edge(polylines, (2000.0, 10.0, 0.0)) == 0


def test_match_edge_respects_tolerance():
    polylines = [[(0.0, 0.0, 0.0), (4000.0, 0.0, 0.0)]]
    assert model.match_edge(polylines, (2000.0, 50.0, 0.0), tol=1.0) is None
    assert model.match_edge(polylines, (2000.0, 0.5, 0.0), tol=1.0) == 0


def test_match_edge_empty_inputs():
    assert model.match_edge([], (0.0, 0.0, 0.0)) is None


# --- chain_runs --------------------------------------------------------------

def test_chain_runs_splits_a_square_into_four_runs():
    links = [
        ([(0, 0, 0), (2000, 0, 0)], True),
        ([(2000, 0, 0), (2000, 2000, 0)], True),
        ([(2000, 2000, 0), (0, 2000, 0)], True),
        ([(0, 2000, 0), (0, 0, 0)], True),
    ]
    runs = model.chain_runs(links)
    assert len(runs) == 4
    assert runs[0] == [(0.0, 0.0, 0.0), (2000.0, 0.0, 0.0)]
    assert runs[1] == [(2000.0, 0.0, 0.0), (2000.0, 2000.0, 0.0)]
    assert runs[2] == [(2000.0, 2000.0, 0.0), (0.0, 2000.0, 0.0)]
    assert runs[3] == [(0.0, 2000.0, 0.0), (0.0, 0.0, 0.0)]


def test_chain_runs_merges_collinear_edges_into_one_run():
    links = [
        ([(0, 0, 0), (1000, 0, 0)], True),
        ([(1000, 0, 0), (2500, 0, 0)], True),
        ([(2500, 0, 0), (4000, 0, 0)], True),
    ]
    assert model.chain_runs(links) == [
        [(0, 0, 0), (1000, 0, 0), (2500, 0, 0), (4000, 0, 0)]]


def test_chain_runs_orders_unordered_and_reversed_links():
    links = [
        ([(4000, 3000, 0), (4000, 0, 0)], True),   # stored end-to-start
        ([(0, 0, 0), (1000, 0, 0)], True),
        ([(2500, 0, 0), (4000, 0, 0)], True),
        ([(1000, 0, 0), (2500, 0, 0)], True),
    ]
    runs = model.chain_runs(links)
    assert runs == [
        [(0, 0, 0), (1000, 0, 0), (2500, 0, 0), (4000, 0, 0)],
        [(4000, 0, 0), (4000, 3000, 0)],
    ]


def test_chain_runs_orders_mixed_direction_links():
    # A closed loop drawn the way sketches are really drawn: edges stored
    # in mixed directions, and not only in seed position. chain_runs must
    # reverse individual links to find one consistent traversal.
    links = [
        ([(0, 0, 0), (4000, 0, 0)], True),        # top, along the travel
        ([(0, 3000, 0), (4000, 3000, 0)], True),  # bottom, stored against it
        ([(4000, 0, 0), (4000, 3000, 0)], True),  # right, along
        ([(0, 3000, 0), (0, 0, 0)], True),        # left, stored against it
    ]
    runs = model.chain_runs(links)
    assert runs == [
        [(0, 0, 0), (4000, 0, 0)],
        [(4000, 0, 0), (4000, 3000, 0)],
        [(4000, 3000, 0), (0, 3000, 0)],
        [(0, 3000, 0), (0, 0, 0)],
    ]


def test_chain_runs_keeps_arcs_solo():
    arc = [(0.0, 0.0, 0.0), (500.0, 500.0, 0.0), (1000.0, 0.0, 0.0)]
    links = [
        ([(-1000, 0, 0), (0, 0, 0)], True),
        (arc, False),
        ([(1000, 0, 0), (2000, 0, 0)], True),
    ]
    runs = model.chain_runs(links)
    assert len(runs) == 3
    assert runs[1] == arc


def test_chain_runs_splits_at_direction_changes_only():
    links = [
        ([(0, 0, 0), (1000, 0, 0)], True),
        ([(1000, 0, 0), (1000, 800, 0)], True),
        ([(1000, 800, 0), (1800, 800, 0)], True),
    ]
    runs = model.chain_runs(links)
    assert runs == [
        [(0, 0, 0), (1000, 0, 0)],
        [(1000, 0, 0), (1000, 800, 0)],
        [(1000, 800, 0), (1800, 800, 0)],
    ]


def test_chain_runs_rejects_unorderable_links():
    links = [
        ([(0, 0, 0), (1000, 0, 0)], True),
        ([(5000, 5000, 0), (6000, 5000, 0)], True),
    ]
    with pytest.raises(ValueError):
        model.chain_runs(links)


def test_chain_runs_rejects_empty_links():
    with pytest.raises(ValueError):
        model.chain_runs([])
