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
