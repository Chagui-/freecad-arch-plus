# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Pure wall-model tests: config inheritance, claim resolution, edge matching.
# model.py must stay importable without FreeCAD.

from archplus.tools.walls import model


def _node(key, claimed=(), rest=False, children=()):
    n = model.ClaimNode(key, claimed, rest=rest)
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


def test_rest_child_claims_everything_unclaimed():
    rest = _node("rest", rest=True)
    built, warnings = model.resolve_claims([rest], EDGES)
    assert built[rest.node] == frozenset(EDGES)
    assert warnings == []


def test_explicit_claim_beats_rest():
    rest = _node("rest", rest=True)
    ext = _node("ext", ("Edge1",))
    built, warnings = model.resolve_claims([rest, ext], EDGES)
    assert built[ext.node] == frozenset(["Edge1"])
    assert built[rest.node] == frozenset(["Edge2", "Edge3", "Edge4"])


def test_group_excludes_descendant_claims():
    rest = _node("rest", rest=True)
    short = _node("short", ("Edge2",))
    rest.children.append(short)
    built, warnings = model.resolve_claims([rest], EDGES)
    assert built[short.node] == frozenset(["Edge2"])
    assert built[rest.node] == frozenset(["Edge1", "Edge3", "Edge4"])


def test_conflicting_claims_build_nowhere_with_warning():
    a = _node("a", ("Edge1", "Edge2"))
    b = _node("b", ("Edge1",))
    built, warnings = model.resolve_claims([a, b], EDGES)
    assert built[a.node] == frozenset(["Edge2"])
    assert built[b.node] == frozenset()
    assert any("Edge1" in w for w in warnings)


def test_two_rest_children_warns_and_keeps_first():
    r1 = _node("r1", rest=True)
    r2 = _node("r2", rest=True)
    built, warnings = model.resolve_claims([r1, r2], EDGES)
    assert built[r1.node] == frozenset(EDGES)
    assert built[r2.node] == frozenset()
    assert any("one rest" in w for w in warnings)


def test_rest_with_explicit_edges_warns_and_ignores_them():
    rest = _node("rest", ("Edge1",), rest=True)
    built, warnings = model.resolve_claims([rest], EDGES)
    assert built[rest.node] == frozenset(EDGES)
    assert any("explicit" in w for w in warnings)


def test_nested_rest_warns_and_treats_as_normal():
    rest = _node("rest", rest=True)
    bad = _node("bad", ("Edge3",), rest=True)
    rest.children.append(bad)
    built, warnings = model.resolve_claims([rest], EDGES)
    assert built[bad.node] == frozenset(["Edge3"])
    assert any("direct child" in w for w in warnings)


def test_no_rest_leaves_new_edges_unbuilt():
    a = _node("a", ("Edge1",))
    built, warnings = model.resolve_claims([a], EDGES)
    assert built[a.node] == frozenset(["Edge1"])
    assert frozenset(["Edge2", "Edge3", "Edge4"]).isdisjoint(built[a.node])


def test_claim_on_missing_edge_warns_and_is_dropped():
    a = _node("a", ("Edge9",))
    built, warnings = model.resolve_claims([a], EDGES)
    assert built[a.node] == frozenset()
    assert any("Edge9" in w for w in warnings)


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
