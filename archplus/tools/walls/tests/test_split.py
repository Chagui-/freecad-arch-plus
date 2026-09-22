# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Headless tests for the split/move command plumbing: selection gating,
# command activation and the picked-faces contract, driven through the
# conftest fakes like the panel tests.

import types

import FreeCAD
import Part

from archplus.tools.walls import gui as wg
from archplus.tools.walls import model
from archplus.tools.walls import object as walls_object


class _Seg(types.SimpleNamespace):
    """A segment stand-in. Real document objects hash by identity, and the
    claim resolver keys its result by the object it was handed, so these
    must stay hashable — SimpleNamespace's value equality makes it not."""

    __hash__ = object.__hash__


def _segment(name="Segments"):
    return _Seg(
        Name=name, Label=name, Group=[], InList=[], Wall=None,
        Proxy=types.SimpleNamespace(Type="Wall", Segment=True))


def _root(*segments):
    root = types.SimpleNamespace(
        Name="Wall", Label="Wall",
        Proxy=types.SimpleNamespace(Type="Wall", WALLS_PLUS=True),
        Group=list(segments), InList=[])
    for seg in segments:
        seg.Wall = root
        seg.InList = [root]
    return root


class _FakeFace:
    """A face modelled by its plane's x, so the box spans y and z to keep the
    suite's 1-D distance model intact."""

    def __init__(self, x):
        self.x = x
        self.BoundBox = types.SimpleNamespace(
            XMin=x, XMax=x,
            YMin=float("-inf"), YMax=float("inf"),
            ZMin=float("-inf"), ZMax=float("inf"))


class _FakeShape:
    def __init__(self, faces):
        self._faces = faces

    def getElement(self, name):
        if name not in self._faces:
            raise KeyError(name)
        return self._faces[name]

    def isNull(self):
        return False

    @property
    def Faces(self):
        return [self._faces[k] for k in sorted(self._faces)]


class _FakeVertex:
    def __init__(self, pnt):
        self.pnt = pnt

    def distToShape(self, face):
        return (abs(self.pnt.x - face.x), [], None)


def _sel(obj, subs=(), points=()):
    return types.SimpleNamespace(
        Object=obj, SubElementNames=tuple(subs),
        PickedPoints=tuple(points),
        HasSubObjects=bool(subs))


def test_is_root_distinguishes_wall_roots():
    assert walls_object.is_root(_root())
    assert not walls_object.is_root(_segment())
    assert not walls_object.is_root(types.SimpleNamespace(Name="Box"))
    # A regular Arch wall is typed "Wall" as well — its proxy class is even
    # called _Wall — but it owns the faces its picks report, so it must not
    # be taken for one of ours.
    assert not walls_object.is_root(types.SimpleNamespace(
        Name="Wall001", Proxy=types.SimpleNamespace(Type="Wall")))


def test_resolve_root_face_picks_nearest_segment(monkeypatch):
    monkeypatch.setattr(Part, "Vertex", _FakeVertex, raising=False)
    a = _segment("a")
    a.Shape = _FakeShape({"Face1": _FakeFace(0.0)})
    b = _segment("b")
    b.Shape = _FakeShape({"Face1": _FakeFace(100.0)})
    root = _root(a, b)
    resolved = walls_object.resolveRootFace(root, "Face1",
                                            FreeCAD.Vector(1.0, 0.0, 0.0))
    assert resolved == (a, ["Face1"])
    resolved = walls_object.resolveRootFace(root, "Face1",
                                            FreeCAD.Vector(99.0, 0.0, 0.0))
    assert resolved == (b, ["Face1"])


def test_resolve_root_face_rejects_a_far_point(monkeypatch):
    monkeypatch.setattr(Part, "Vertex", _FakeVertex, raising=False)
    a = _segment("a")
    a.Shape = _FakeShape({"Face1": _FakeFace(0.0)})
    b = _segment("b")
    b.Shape = _FakeShape({"Face1": _FakeFace(100.0)})
    root = _root(a, b)
    far = FreeCAD.Vector(1000.0, 0.0, 0.0)
    assert walls_object.resolveRootFace(root, "Face1", far) is None


def test_resolve_root_face_unique_without_point(monkeypatch):
    a = _segment("a")
    a.Shape = _FakeShape({"Face1": _FakeFace(0.0)})
    root = _root(a)
    assert walls_object.resolveRootFace(root, "Face1", None) == (a, ["Face1"])


def test_resolve_root_face_ambiguous_without_point(monkeypatch):
    a = _segment("a")
    a.Shape = _FakeShape({"Face1": _FakeFace(0.0)})
    b = _segment("b")
    b.Shape = _FakeShape({"Face1": _FakeFace(100.0)})
    root = _root(a, b)
    assert walls_object.resolveRootFace(root, "Face1", None) is None


def test_resolve_root_face_without_candidates_or_segments(monkeypatch):
    a = _segment("a")
    a.Shape = _FakeShape({"Face1": _FakeFace(0.0)})
    root = _root(a)
    assert walls_object.resolveRootFace(root, "Face9", None) is None
    empty = _root()
    assert walls_object.resolveRootFace(empty, "Face1", None) is None


def test_wall_segment_selected_gates_on_selection(monkeypatch):
    monkeypatch.setattr(wg.FreeCADGui, "Selection", types.SimpleNamespace(
        getSelectionEx=lambda: [_sel(_segment())]))
    assert wg.wall_segment_selected()
    monkeypatch.setattr(wg.FreeCADGui, "Selection", types.SimpleNamespace(
        getSelectionEx=lambda: [_sel(types.SimpleNamespace(
            Name="Box", Label="Box",
            Proxy=types.SimpleNamespace(Type="Part")))]))
    assert not wg.wall_segment_selected()
    monkeypatch.setattr(wg.FreeCADGui, "Selection", types.SimpleNamespace(
        getSelectionEx=lambda: []))
    assert not wg.wall_segment_selected()


def test_wall_segment_selected_accepts_wall_root(monkeypatch):
    monkeypatch.setattr(wg.FreeCADGui, "Selection", types.SimpleNamespace(
        getSelectionEx=lambda: [_sel(_root())]))
    assert wg.wall_segment_selected()


def test_split_command_active_only_for_segments(monkeypatch):
    cmd = wg.WallSplitCommand()
    monkeypatch.setattr(wg.FreeCADGui, "Selection", types.SimpleNamespace(
        getSelectionEx=lambda: [_sel(_segment())]))
    assert cmd.IsActive()
    monkeypatch.setattr(wg.FreeCADGui, "Selection", types.SimpleNamespace(
        getSelectionEx=lambda: [_sel(types.SimpleNamespace(
            Name="Box", Label="Box",
            Proxy=types.SimpleNamespace(Type="Part")))]))
    assert not cmd.IsActive()


def test_split_without_faces_maps_nothing():
    cmd = wg.WallSplitCommand()
    seg = _segment()
    seg.Base = None
    assert cmd._pickedEdges(seg, _sel(seg)) == []


def test_split_with_no_claims_maps_nothing():
    cmd = wg.WallSplitCommand()
    seg = _segment()
    seg.Base = types.SimpleNamespace(Shape=None)
    seg.Proxy._claimedEdges = lambda obj: []
    assert cmd._pickedEdges(seg, _sel(seg, subs=("Face1",))) == []


def test_a_click_on_the_far_face_still_matches_its_run(monkeypatch):
    """The far face of a Left-aligned wall sits exactly one Width from its
    baseline - the very edge of the band a pick is mapped through - so the
    match must not be decided by the last bit of the arithmetic.

    Measured on a real 300mm wall, every point of that face came out at
    300.000 from the run: a click a hair over it was reported as "face
    'Face2' of segment 'Segments-ext-f2b' is not on any claimed run; nothing
    to split there", while the near face (distance ~0) worked. The guard
    still has to refuse a face that is nowhere near the segment's runs."""
    run = ("Edge1", [(0.0, 0.0, 0.0), (4000.0, 0.0, 0.0)])
    monkeypatch.setattr(wg, "_claimedEdgePolylines", lambda obj: [run])
    monkeypatch.setattr(wg, "_projectToSketchPlane",
                        lambda point, base: point)
    monkeypatch.setattr(walls_object, "effectiveValues",
                        lambda obj: {"Width": 300.0, "Align": "Left"})
    seg = _segment()
    seg.Base = types.SimpleNamespace()
    cmd = wg.WallSplitCommand()

    for offset in (299.9996, 300.0, 300.0004):
        sel = _sel(seg, subs=("Face2",),
                   points=[FreeCAD.Vector(2000.0, offset, 0.0)])
        assert cmd._pickedEdges(seg, sel) == ["Edge1"], (
            "a click %.4f from the run is on the wall's face and must match"
            % offset)

    sel = _sel(seg, subs=("Face2",),
               points=[FreeCAD.Vector(2000.0, 900.0, 0.0)])
    assert cmd._pickedEdges(seg, sel) == [], (
        "a face nowhere near a run must still be refused")


def test_target_options_exclude_sources_and_ancestors():
    cmd = wg.WallSplitCommand()
    root = types.SimpleNamespace(
        Name="Wall", Label="Wall",
        Proxy=types.SimpleNamespace(Type="Wall", WALLS_PLUS=True),
        Group=[], InList=[])
    fallback = _segment("Segments")
    a = _segment("a")
    b = _segment("b")
    root.Group = [fallback, a, b]
    for seg in (fallback, a, b):
        seg.Wall = root
        seg.InList = [root]
    options = cmd._targetOptions([(a, ("Edge1",))])
    assert fallback in options and b in options and a not in options
    nested = _segment("nested")
    nested.Wall = root
    a.Group = [nested]
    nested.InList = [a]
    options = cmd._targetOptions([(nested, ("Edge1",))])
    assert fallback in options and b in options and a not in options
    root.Group = [a]
    assert cmd._targetOptions([(a, ("Edge1",))]) == []


def test_moving_faces_onto_the_fallback_stores_no_claims():
    """A fallback builds what no one else claims, so moving faces onto it
    must not leave an explicit list behind: that list is ignored, and the
    next recompute reports it as an ignored claim."""
    sk = types.SimpleNamespace()
    fallback = _segment("Segments")
    fallback.Fallback = True
    fallback.Edges = []
    fallback.Base = sk
    a = _segment("a")
    a.Fallback = False
    a.Edges = [(sk, ("Edge1",))]
    a.Base = sk
    root = _root(fallback, a)

    walls_object.moveSegmentEdges(a, fallback, ["Edge1"])

    nodes = [walls_object._claimNode(seg) for seg in root.Group
             if walls_object.is_segment(seg)]
    built, warnings = model.resolve_claims(nodes, ["Edge1", "Edge2"])
    assert warnings == []
    assert built[fallback] == frozenset(["Edge1", "Edge2"])
    assert built[a] == frozenset()


def test_moving_faces_off_the_fallback_forgets_them():
    """A move takes the edges away from the segment they came from, the
    fallback included.

    Leaving them behind in the fallback's own list looks harmless while it
    IS the fallback, because the resolver ignores that list and says so. But
    the moment the fallback moves to another segment the list wakes up,
    collides with the target that already took the edge, and the edge then
    builds NOWHERE - a run missing from the wall, reported as "claimed by
    several segments"."""
    sk = types.SimpleNamespace()
    fallback = _segment("Segments")
    fallback.Fallback = True
    fallback.Edges = [(sk, ("Edge1", "Edge2"))]
    fallback.Base = sk
    a = _segment("a")
    a.Fallback = False
    a.Edges = []
    a.Base = sk
    root = _root(fallback, a)

    walls_object.moveSegmentEdges(fallback, a, ["Edge1"])

    # Edge1 left the fallback's list; Edge2, which nobody moved, stays.
    assert [s for _l, subs in fallback.Edges for s in subs] == ["Edge2"]

    # The fallback moves to a third segment, so both are normal build again.
    third = _segment("third")
    third.Fallback = True
    third.Edges = []
    third.Base = sk
    third.Wall = root
    third.InList = [root]
    fallback.Fallback = False
    root.Group = [fallback, a, third]

    nodes = [walls_object._claimNode(seg) for seg in root.Group
             if walls_object.is_segment(seg)]
    built, warnings = model.resolve_claims(nodes, ["Edge1", "Edge2"])
    assert warnings == []
    assert built[a] == frozenset(["Edge1"])
    assert built[fallback] == frozenset(["Edge2"])
    assert built[third] == frozenset()


def test_target_labels_suffix_repeats():
    cmd = wg.WallSplitCommand()
    segs = []
    for name in ("a", "b", "c"):
        seg = _segment(name)
        seg.Label = "Seg"
        segs.append(seg)
    assert cmd._targetLabels(segs) == ["Seg", "Seg (2)", "Seg (3)"]


def test_choose_target_binds_rows_to_options(monkeypatch):
    cmd = wg.WallSplitCommand()
    a = _segment("a")
    a.Label = "Seg"
    b = _segment("b")
    b.Label = "Seg"
    c = _segment("c")
    c.Label = "Other"
    cmd._targetOptions = lambda sources: [a, b, c]
    captured = {}

    def picker(rows, segs):
        captured["rows"] = list(rows)
        captured["segs"] = list(segs)
        return captured.get("return")

    monkeypatch.setattr(cmd, "_runPicker", picker)
    captured["return"] = None
    assert cmd._chooseTarget([(a, ("Edge1",))]) is None
    captured["return"] = wg.NEW_SEGMENT
    assert cmd._chooseTarget([(a, ("Edge1",))]) is wg.NEW_SEGMENT
    captured["return"] = b
    assert cmd._chooseTarget([(a, ("Edge1",))]) is b
    assert captured["rows"] == ["<new segment>", "Seg", "Seg (2)", "Other"]
    assert captured["segs"] == [wg.NEW_SEGMENT, a, b, c]


class _RecordingDoc:
    def __init__(self):
        self.calls = []

    def openTransaction(self, name):
        self.calls.append(("open", name))

    def recompute(self):
        self.calls.append(("recompute",))

    def commitTransaction(self):
        self.calls.append(("commit",))


def test_activated_aborts_when_sources_span_several_walls(monkeypatch):
    cmd = wg.WallSplitCommand()
    root_a = types.SimpleNamespace(Name="Wall", Proxy=types.SimpleNamespace(
        Type="Wall", WALLS_PLUS=True), Group=[], InList=[])
    root_b = types.SimpleNamespace(Name="Wall2", Proxy=types.SimpleNamespace(
        Type="Wall", WALLS_PLUS=True), Group=[], InList=[])
    a = _segment("a")
    a.Wall = root_a
    b = _segment("b")
    b.Wall = root_b
    doc = _RecordingDoc()
    monkeypatch.setattr(wg.FreeCAD, "ActiveDocument", doc)
    monkeypatch.setattr(wg.FreeCADGui, "Selection", types.SimpleNamespace(
        getSelectionEx=lambda: [_sel(a), _sel(b)]))
    cmd._pickedEdges = lambda obj, sel: ["Edge1"]
    dialog = []
    cmd._chooseTarget = lambda sources: dialog.append(sources)
    captured = []
    monkeypatch.setattr(wg.FreeCAD.Console, "PrintWarning",
                        captured.append)
    cmd.Activated()
    assert any("several walls" in m for m in captured)
    assert doc.calls == []
    assert dialog == []


def test_activated_cancels_before_opening_a_transaction(monkeypatch):
    cmd = wg.WallSplitCommand()
    root = types.SimpleNamespace(Name="Wall", Proxy=types.SimpleNamespace(
        Type="Wall", WALLS_PLUS=True), Group=[], InList=[])
    a = _segment("a")
    a.Wall = root
    doc = _RecordingDoc()
    monkeypatch.setattr(wg.FreeCAD, "ActiveDocument", doc)
    monkeypatch.setattr(wg.FreeCADGui, "Selection", types.SimpleNamespace(
        getSelectionEx=lambda: [_sel(a)]))
    cmd._pickedEdges = lambda obj, sel: ["Edge1"]
    cmd._chooseTarget = lambda sources: None
    cmd.Activated()
    assert doc.calls == []



def test_recorder_keeps_one_point_per_face_occurrence(monkeypatch):
    r = wg._PickPointRecorder()
    monkeypatch.setattr(wg, "_recorder", r)
    r.addSelection("D", "Wall", "Face1", (1, 2, 3))
    r.addSelection("D", "Wall", "Face1", (4, 5, 6))
    r.addSelection("D", "Wall", "Face2", (7, 8, 9))
    assert wg._lastPick("D", "Wall", "Face1", 0) is not None
    assert wg._lastPick("D", "Wall", "Face1", 1) is not None
    assert wg._lastPick("D", "Wall", "Face1", 2) is None
    assert wg._lastPick("D", "Wall", "Face2", 0) is not None
    assert wg._lastPick("D", "Wall", "Face9", 0) is None


def test_recorder_remove_drops_first_occurrence(monkeypatch):
    r = wg._PickPointRecorder()
    monkeypatch.setattr(wg, "_recorder", r)
    r.addSelection("D", "Wall", "Face1", (1, 2, 3))
    r.addSelection("D", "Wall", "Face1", (4, 5, 6))
    r.removeSelection("D", "Wall", "Face1")
    assert wg._lastPick("D", "Wall", "Face1", 0) is not None
    assert wg._lastPick("D", "Wall", "Face1", 1) is None
    r.removeSelection("D", "Wall", "Face1")
    assert wg._lastPick("D", "Wall", "Face1", 0) is None


def test_recorder_clear_document_only(monkeypatch):
    r = wg._PickPointRecorder()
    monkeypatch.setattr(wg, "_recorder", r)
    r.addSelection("D", "Wall", "Face1", (1, 2, 3))
    r.addSelection("E", "Wall", "Face1", (4, 5, 6))
    r.clearSelection("D")
    assert wg._lastPick("D", "Wall", "Face1") is None
    assert wg._lastPick("E", "Wall", "Face1") is not None


def test_observer_expands_tree_click_to_all_faces():
    obs = wg._WallSelectionObserver()
    seg = _segment("a")
    seg.Shape = types.SimpleNamespace(
        isNull=lambda: False,
        Faces=[object(), object(), object()])
    added = []
    gui = types.SimpleNamespace(
        Selection=types.SimpleNamespace(
            getSelectionEx=lambda: [types.SimpleNamespace(
                Object=seg, SubElementNames=[])],
            addSelection=lambda o, sub: added.append(sub)))
    obs._selectFaces(gui, seg)
    assert added == ["Face1", "Face2", "Face3"]


def test_observer_skips_expansion_when_faces_already_selected():
    obs = wg._WallSelectionObserver()
    seg = _segment("a")
    seg.Shape = types.SimpleNamespace(
        isNull=lambda: False,
        Faces=[object(), object()])
    added = []
    gui = types.SimpleNamespace(
        Selection=types.SimpleNamespace(
            getSelectionEx=lambda: [types.SimpleNamespace(
                Object=seg, SubElementNames=["Face1"])],
            addSelection=lambda o, sub: added.append(sub)))
    obs._selectFaces(gui, seg)
    assert added == []


def test_observer_redirects_root_pick_to_owning_segment(monkeypatch):
    obs = wg._WallSelectionObserver()
    root = types.SimpleNamespace(Name="Wall", Label="Wall")
    seg = _segment("a")
    removed = []
    added = []
    gui = types.SimpleNamespace(
        Selection=types.SimpleNamespace(
            getSelectionEx=lambda: [types.SimpleNamespace(
                Object=root, SubElementNames=["Face2"])],
            removeSelection=lambda o, sub: removed.append((o, sub)),
            addSelection=lambda o, sub, *pnt: added.append((o, sub, pnt))))
    monkeypatch.setattr(walls_object, "resolveRootFace",
                        lambda root_, sub, point: (seg, [sub]))
    obs._redirect(gui, root, "Face2", (1.0, 2.0, 3.0))
    assert removed == [(root, "Face2")]
    assert len(added) == 1 and added[0][0] is seg and added[0][1] == "Face2"
    assert tuple(round(v, 3) for v in added[0][2]) == (1.0, 2.0, 3.0)


def test_observer_skips_redirect_for_stale_selection(monkeypatch):
    obs = wg._WallSelectionObserver()
    root = types.SimpleNamespace(Name="Wall", Label="Wall")
    seg = _segment("a")
    calls = []
    gui = types.SimpleNamespace(
        Selection=types.SimpleNamespace(
            getSelectionEx=lambda: [],
            removeSelection=lambda o, sub: calls.append("rm"),
            addSelection=lambda o, sub, *pnt: calls.append("add")))
    monkeypatch.setattr(walls_object, "resolveRootFace",
                        lambda root_, sub, point: (seg, [sub]))
    obs._redirect(gui, root, "Face2", (1.0, 2.0, 3.0))
    assert calls == []
