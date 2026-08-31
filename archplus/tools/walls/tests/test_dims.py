# archplus/tools/walls/tests/test_dims.py
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Headless tests for the wall length overlay: dimension geometry, run
# summaries, face-to-run selection mapping and overlay bookkeeping.
# dims.py imports FreeCAD/FreeCADGui only inside functions, so the
# conftest fakes carry the whole suite.

import types

import FreeCAD
import FreeCADGui
import pytest

from archplus.tools.walls import dims
from archplus.tools.walls import gui as walls_gui
from archplus.tools.walls import object as walls_object

UP = (0.0, 0.0, 1.0)


# --- dim geometry ------------------------------------------------------------

def test_polyline_length_sums_segments():
    pts = [(0, 0, 0), (1000, 0, 0), (1000, 500, 0)]
    assert dims.polyline_length(pts) == pytest.approx(1500.0)


def test_dim_lift_clears_the_top_edge():
    # 5 % of the height once that beats the 100 mm floor.
    assert dims.dim_lift(2800.0) == pytest.approx(2940.0)
    # the 100 mm floor for low walls.
    assert dims.dim_lift(1000.0) == pytest.approx(1100.0)


def test_dim_geometry_raises_a_straight_run():
    line, ticks, label = dims._dimGeometry([(0, 0, 0), (4000, 0, 0)], UP,
                                           2800.0)
    assert line == [(0.0, 0.0, 2940.0), (4000.0, 0.0, 2940.0)]
    assert label == (2000.0, 0.0, 2940.0)
    assert len(ticks) == 2


def test_dim_geometry_ticks_cross_the_ends_at_45_degrees():
    line, ticks, _label = dims._dimGeometry([(0, 0, 0), (4000, 0, 0)], UP,
                                            2800.0)
    for (a, b), end in zip(ticks, line):
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, (a[2] + b[2]) / 2.0)
        assert mid == pytest.approx(end)
        assert dims._dist(a, b) == pytest.approx(60.0)
        assert a[2] == b[2] == end[2]


def test_dim_geometry_follows_an_l_run():
    line, ticks, label = dims._dimGeometry(
        [(0, 0, 0), (4000, 0, 0), (4000, 3000, 0)], UP, 2800.0)
    assert len(line) == 3
    assert line[2] == (4000.0, 3000.0, 2940.0)
    # total 7000, so the arc-length midpoint sits at 3500 on the first leg.
    assert label == (3500.0, 0.0, 2940.0)
    assert len(ticks) == 2


def test_dim_geometry_rejects_degenerate_runs():
    with pytest.raises(ValueError):
        dims._dimGeometry([(0, 0, 0)], UP, 2800.0)


def test_format_length_falls_back_to_millimetres():
    # The conftest fake Units make Quantity() return None, which forces the
    # plain millimetre fallback — exactly the path this test pins.
    assert dims.format_length(2450.0) == "2450 mm"


# --- run summaries -----------------------------------------------------------

def _segment(name="Segments"):
    return types.SimpleNamespace(
        Name=name, Label=name, Group=[], InList=[], Wall=None,
        Base=None,
        Proxy=types.SimpleNamespace(Type="WallSegment"))


# A square wall's two first runs: along +X, then along +Y.
_RUNS = [([(0, 0, 0), (4000, 0, 0)], (0, 0, 1), 2800.0),
         ([(0, 0, 0), (0, 3000, 0)], (0, 0, 1), 2800.0)]


def test_run_dims_sums_run_lengths(monkeypatch):
    monkeypatch.setattr(walls_object, "segmentEdgeRuns",
                        lambda seg: _RUNS[:1])
    assert dims.run_dims(_segment()) == [
        ([(0, 0, 0), (4000, 0, 0)], 4000.0)]


def test_run_dims_skips_degenerate_runs(monkeypatch):
    monkeypatch.setattr(walls_object, "segmentEdgeRuns",
                        lambda seg: [([(0, 0, 0)], (0, 0, 1), 2800.0)])
    assert dims.run_dims(_segment()) == []


def test_run_dims_scope_picks_runs(monkeypatch):
    monkeypatch.setattr(walls_object, "segmentEdgeRuns", lambda seg: _RUNS)
    assert dims.run_dims(_segment(), {1}) == [
        ([(0, 0, 0), (0, 3000, 0)], 3000.0)]
    assert dims.run_dims(_segment()) == [
        ([(0, 0, 0), (4000, 0, 0)], 4000.0),
        ([(0, 0, 0), (0, 3000, 0)], 3000.0)]


def test_dim_runs_build_label_and_geometry(monkeypatch):
    monkeypatch.setattr(walls_object, "segmentEdgeRuns",
                        lambda seg: _RUNS[:1])
    line, ticks, label_pt, text = dims._dimRuns(_segment())[0]
    assert line == [(0.0, 0.0, 2940.0), (4000.0, 0.0, 2940.0)]
    assert label_pt == (2000.0, 0.0, 2940.0)
    assert text == "4000 mm"  # the fake Units force the fallback format
    assert len(ticks) == 2


def test_dim_runs_skip_undrawable_runs(monkeypatch):
    monkeypatch.setattr(walls_object, "segmentEdgeRuns",
                        lambda seg: _RUNS[:1])

    def boom(*_args):
        raise ValueError("doubled back")

    monkeypatch.setattr(dims, "_dimGeometry", boom)
    assert dims._dimRuns(_segment()) == []


# --- selection mapping and bookkeeping ---------------------------------------

@pytest.fixture(autouse=True)
def _reset_overlay_state():
    dims._nodes.clear()
    yield
    dims._nodes.clear()


def _root(*segments):
    root = types.SimpleNamespace(
        Name="Wall", Label="Wall",
        Proxy=types.SimpleNamespace(Type="Wall"),
        Group=list(segments), InList=[])
    for seg in segments:
        seg.Wall = root
        seg.InList = [root]
    return root


def _sel(obj, subs=(), points=()):
    return types.SimpleNamespace(Object=obj, SubElementNames=tuple(subs),
                                 PickedPoints=tuple(points))


def _flat_projection(point, sketch):
    """Stand-in for _projectToSketchPlane: flatten onto z = 0 so the
    match distances stay in-plane like the real projection does."""
    return FreeCAD.Vector(point.x, point.y, 0.0)


def _with_runs(monkeypatch, runs=None, width=300.0):
    runs = _RUNS if runs is None else runs
    monkeypatch.setattr(walls_object, "segmentEdgeRuns", lambda seg: runs)
    monkeypatch.setattr(walls_object, "effectiveValues",
                        lambda seg: {"Width": width})
    monkeypatch.setattr(walls_gui, "_projectToSketchPlane",
                        _flat_projection)


def test_dim_scopes_direct_segment_without_faces(monkeypatch):
    a = _segment("a")
    monkeypatch.setattr(FreeCADGui, "Selection", types.SimpleNamespace(
        getSelectionEx=lambda: [_sel(a)]))
    assert dims._dimScopes() == [(a, None)]


def test_dim_scopes_maps_picked_faces_to_runs(monkeypatch):
    a = _segment("a")
    _with_runs(monkeypatch)
    sel = _sel(a, ("Face3",), (FreeCAD.Vector(2000.0, -100.0, 1400.0),))
    monkeypatch.setattr(FreeCADGui, "Selection", types.SimpleNamespace(
        getSelectionEx=lambda: [sel]))
    # the click sits 100 mm off the first run's baseline, 2000 mm off the
    # second's — inside the 300 mm wall width of run 0 only.
    assert dims._dimScopes() == [(a, {0})]


def test_dim_scopes_unmatched_faces_scope_nothing(monkeypatch):
    a = _segment("a")
    _with_runs(monkeypatch)
    sel = _sel(a, ("Face3",), (FreeCAD.Vector(20000.0, -100.0, 1400.0),))
    monkeypatch.setattr(FreeCADGui, "Selection", types.SimpleNamespace(
        getSelectionEx=lambda: [sel]))
    assert dims._dimScopes() == [(a, set())]


def test_dim_scopes_unions_scopes_across_faces(monkeypatch):
    a = _segment("a")
    _with_runs(monkeypatch)
    sel = _sel(a, ("Face1", "Face2"),
               (FreeCAD.Vector(2000.0, -100.0, 1400.0),    # on run 0
                FreeCAD.Vector(-100.0, 1500.0, 1400.0)))   # on run 1
    monkeypatch.setattr(FreeCADGui, "Selection", types.SimpleNamespace(
        getSelectionEx=lambda: [sel]))
    assert dims._dimScopes() == [(a, {0, 1})]


def test_dim_scopes_none_scope_absorbs(monkeypatch):
    a = _segment("a")
    _with_runs(monkeypatch)
    plain = _sel(a)
    picked = _sel(a, ("Face1",), (FreeCAD.Vector(2000.0, -100.0, 1400.0),))
    monkeypatch.setattr(FreeCADGui, "Selection", types.SimpleNamespace(
        getSelectionEx=lambda: [plain, picked]))
    assert dims._dimScopes() == [(a, None)]


def test_dim_scopes_resolves_root_face_picks(monkeypatch):
    a = _segment("a")
    b = _segment("b")
    root = _root(a, b)
    _with_runs(monkeypatch)
    seen = []
    picks = []

    def fake_resolve(obj, name, point):
        seen.append((name, (point.x, point.y, point.z)))
        return {"Face1": (a, ["Face1"]), "Face2": (b, ["Face2"])}[name]

    def fake_pick(doc, obj, sub, occurrence=0):
        picks.append((sub, occurrence))
        return FreeCAD.Vector(2000.0, -100.0, 1400.0)

    monkeypatch.setattr(walls_object, "resolveRootFace", fake_resolve)
    monkeypatch.setattr(walls_gui, "_lastPick", fake_pick)
    monkeypatch.setattr(FreeCADGui, "Selection", types.SimpleNamespace(
        getSelectionEx=lambda: [_sel(root, ("Face1", "Face1", "Face2"))]))
    assert dims._dimScopes() == [(a, {0}), (b, {0})]
    assert seen == [("Face1", (2000.0, -100.0, 1400.0)),
                    ("Face1", (2000.0, -100.0, 1400.0)),
                    ("Face2", (2000.0, -100.0, 1400.0))]
    assert picks == [("Face1", 0), ("Face1", 1), ("Face2", 0)]


def test_dim_scopes_ignores_tree_roots_and_foreign_objects(monkeypatch):
    root = _root(_segment("a"))
    box = types.SimpleNamespace(
        Name="Box", Label="Box", Proxy=types.SimpleNamespace(Type="Part"))
    monkeypatch.setattr(FreeCADGui, "Selection", types.SimpleNamespace(
        getSelectionEx=lambda: [_sel(root), _sel(box)]))
    assert dims._dimScopes() == []


def test_sync_draws_and_clears_with_selection(monkeypatch):
    a = _segment("a")
    b = _segment("b")
    drawn, cleared = [], []
    monkeypatch.setattr(dims, "_dimScopes", lambda: [(a, None)])
    monkeypatch.setattr(dims, "addDim",
                        lambda seg, scope=None:
                            drawn.append((seg, scope)) or True)
    monkeypatch.setattr(dims, "removeDim", lambda seg: cleared.append(seg))
    dims.sync()
    assert drawn == [(a, None)]
    assert dims._nodes == {dims._key(a): (a, None)}
    monkeypatch.setattr(dims, "_dimScopes", lambda: [(b, {0})])
    dims.sync()
    assert cleared == [a]
    assert dims._nodes == {dims._key(b): (b, {0})}
    monkeypatch.setattr(dims, "_dimScopes", lambda: [])
    dims.sync()
    assert cleared == [a, b]
    assert dims._nodes == {}


def test_sync_redraws_when_the_run_scope_changes(monkeypatch):
    a = _segment("a")
    drawn, cleared = [], []
    monkeypatch.setattr(dims, "addDim",
                        lambda seg, scope=None: drawn.append(scope) or True)
    monkeypatch.setattr(dims, "removeDim", lambda seg: cleared.append(seg))
    dims._nodes[dims._key(a)] = (a, {0})
    monkeypatch.setattr(dims, "_dimScopes", lambda: [(a, {0, 1})])
    dims.sync()
    assert cleared == [a]
    assert drawn == [{0, 1}]
    assert dims._nodes == {dims._key(a): (a, {0, 1})}


def test_sync_skips_targets_that_cannot_draw(monkeypatch):
    a = _segment("a")
    monkeypatch.setattr(dims, "_dimScopes", lambda: [(a, None)])
    monkeypatch.setattr(dims, "addDim", lambda seg, scope=None: False)
    monkeypatch.setattr(dims, "removeDim", lambda seg: None)
    dims.sync()
    assert dims._nodes == {}


def test_sync_survives_scope_errors(monkeypatch):
    def boom():
        raise RuntimeError("no selection")

    monkeypatch.setattr(dims, "_dimScopes", boom)
    dims.sync()  # must not raise
    assert dims._nodes == {}


def test_refresh_redraws_only_dimmed_segments(monkeypatch):
    a = _segment("a")
    b = _segment("b")
    calls = []
    monkeypatch.setattr(dims, "removeDim",
                        lambda seg: calls.append(("rm", seg)))

    def fake_add(seg, scope=None):
        calls.append(("add", seg, scope))
        return True

    monkeypatch.setattr(dims, "addDim", fake_add)
    dims._nodes[dims._key(a)] = (a, {1})
    dims.refresh(a)
    assert calls == [("rm", a), ("add", a, {1})]
    assert dims._nodes == {dims._key(a): (a, {1})}
    calls.clear()
    dims.refresh(b)
    assert calls == []


def test_refresh_drops_segments_that_stop_drawing(monkeypatch):
    a = _segment("a")
    dims._nodes[dims._key(a)] = (a, None)
    monkeypatch.setattr(dims, "removeDim", lambda seg: None)
    monkeypatch.setattr(dims, "addDim", lambda seg, scope=None: False)
    dims.refresh(a)
    assert dims._nodes == {}
