# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Headless tests for the split/move command plumbing: selection gating,
# command activation and the picked-faces contract, driven through the
# conftest fakes like the panel tests.

import types

import FreeCAD
import Part

from archplus.tools.walls import gui as wg
from archplus.tools.walls import object as walls_object


def _segment(name="Segments"):
    return types.SimpleNamespace(
        Name=name, Label=name, Group=[], InList=[], Wall=None,
        Proxy=types.SimpleNamespace(Type="WallSegment"))


def _root(*segments):
    root = types.SimpleNamespace(
        Name="Wall", Label="Wall",
        Proxy=types.SimpleNamespace(Type="Wall"),
        Group=list(segments), InList=[])
    for seg in segments:
        seg.Wall = root
        seg.InList = [root]
    return root


class _FakeFace:
    def __init__(self, x):
        self.x = x


class _FakeShape:
    def __init__(self, faces):
        self._faces = faces

    def getElement(self, name):
        if name not in self._faces:
            raise KeyError(name)
        return self._faces[name]


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


def test_target_options_exclude_sources_and_ancestors():
    cmd = wg.WallSplitCommand()
    root = types.SimpleNamespace(
        Name="Wall", Label="Wall",
        Proxy=types.SimpleNamespace(Type="Wall"),
        Group=[], InList=[])
    rest = _segment("Segments")
    a = _segment("a")
    b = _segment("b")
    root.Group = [rest, a, b]
    for seg in (rest, a, b):
        seg.Wall = root
        seg.InList = [root]
    options = cmd._targetOptions([(a, ("Edge1",))])
    assert rest in options and b in options and a not in options
    nested = _segment("nested")
    nested.Wall = root
    a.Group = [nested]
    nested.InList = [a]
    options = cmd._targetOptions([(nested, ("Edge1",))])
    assert rest in options and b in options and a not in options
    root.Group = [a]
    assert cmd._targetOptions([(a, ("Edge1",))]) == []


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
        Type="Wall"), Group=[], InList=[])
    root_b = types.SimpleNamespace(Name="Wall2", Proxy=types.SimpleNamespace(
        Type="Wall"), Group=[], InList=[])
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
        Type="Wall"), Group=[], InList=[])
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
