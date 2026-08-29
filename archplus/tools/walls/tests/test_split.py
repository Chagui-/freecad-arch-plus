# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Headless tests for the split/move command plumbing: 3D-view menu-hook
# gating, command activation and the picked-faces contract, driven through
# the conftest fakes like the panel tests.

import types

from archplus.tools.walls import gui as wg


def _segment(name="Segments"):
    return types.SimpleNamespace(
        Name=name, Label=name, Group=[], InList=[], Wall=None,
        Proxy=types.SimpleNamespace(Type="WallSegment"))


def _sel(obj, subs=(), points=()):
    return types.SimpleNamespace(
        Object=obj, SubElementNames=tuple(subs),
        PickedPoints=tuple(points),
        HasSubObjects=bool(subs))


def test_menu_hook_gates_on_recipient_and_selection(monkeypatch):
    hook = wg._WallMenuHook()
    monkeypatch.setattr(wg.FreeCADGui, "Selection", types.SimpleNamespace(
        getSelectionEx=lambda: [_sel(_segment())]))
    assert hook.modifyContextMenu("View") == [
        {"insert": "ArchPlus_WallSplit", "menuItem": "Std_Placement"}]
    assert hook.modifyContextMenu("Tree") is None
    monkeypatch.setattr(wg.FreeCADGui, "Selection", types.SimpleNamespace(
        getSelectionEx=lambda: []))
    assert hook.modifyContextMenu("View") is None


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


def test_choose_target_binds_the_choice_to_the_exact_option(monkeypatch):
    cmd = wg.WallSplitCommand()
    a = _segment("a")
    a.Label = "Seg"
    b = _segment("b")
    b.Label = "Seg"
    c = _segment("c")
    c.Label = "Other"
    cmd._targetOptions = lambda sources: [a, b, c]
    monkeypatch.setattr(wg.QtGui, "QInputDialog", types.SimpleNamespace(
        getItem=lambda parent, title, label, items, current, editable:
        (None, False)), raising=False)
    assert cmd._chooseTarget([(a, ("Edge1",))]) is None
    monkeypatch.setattr(wg.QtGui, "QInputDialog", types.SimpleNamespace(
        getItem=lambda parent, title, label, items, current, editable:
        ("<new segment>", True)), raising=False)
    assert cmd._chooseTarget([(a, ("Edge1",))]) is wg.NEW_SEGMENT
    monkeypatch.setattr(wg.QtGui, "QInputDialog", types.SimpleNamespace(
        getItem=lambda parent, title, label, items, current, editable:
        ("Seg", True)), raising=False)
    assert cmd._chooseTarget([(a, ("Edge1",))]) is a
    monkeypatch.setattr(wg.QtGui, "QInputDialog", types.SimpleNamespace(
        getItem=lambda parent, title, label, items, current, editable:
        ("Seg (2)", True)), raising=False)
    assert cmd._chooseTarget([(a, ("Edge1",))]) is b
    monkeypatch.setattr(wg.QtGui, "QInputDialog", types.SimpleNamespace(
        getItem=lambda parent, title, label, items, current, editable:
        ("Other", True)), raising=False)
    assert cmd._chooseTarget([(a, ("Edge1",))]) is c


def test_choose_target_suffixes_repeated_labels(monkeypatch):
    cmd = wg.WallSplitCommand()
    a = _segment("a")
    b = _segment("b")
    c = _segment("c")
    for seg in (a, b, c):
        seg.Label = "Seg"
    seen = {}

    def getItem(parent, title, label, items, current, editable):
        seen["items"] = list(items)
        return ("<new segment>", True)

    monkeypatch.setattr(wg.QtGui, "QInputDialog",
                        types.SimpleNamespace(getItem=getItem), raising=False)
    cmd._targetOptions = lambda sources: [a, b, c]
    cmd._chooseTarget([(a, ("Edge1",))])
    assert seen["items"] == ["<new segment>", "Seg", "Seg (2)", "Seg (3)"]


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
