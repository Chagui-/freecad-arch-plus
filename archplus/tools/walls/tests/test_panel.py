# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Headless tests for the wall task panels, driven through fakes exactly like
# test_stairs.py: the panel reads/writes object properties, so _collect /
# _loadFromObject carry the decisions worth testing here.

import os
import types

import FreeCAD

from archplus.tools.walls import gui as wg
from conftest import FakeCombo, FakeNum, FakeCheck, quantity


def test_icon_wiring_resolves_to_real_files():
    """The panel constructors and both commands consume these constants at
    runtime, but no headless test runs those constructors (they build real
    Qt widgets), so the wiring itself is the contract."""
    assert os.path.isfile(wg.ICON)
    assert os.path.isfile(wg._SPLIT_ICON)
    assert os.path.isdir(wg._ICON_DIR)
    assert wg.WallSplitCommand().GetResources()["Pixmap"] == wg._SPLIT_ICON


class _FakeLine:
    """A QLineEdit stand-in: holds one string."""

    def __init__(self, v=""):
        self._v = v

    def text(self):
        return self._v

    def setText(self, v):
        self._v = v


class _FakeDataCombo(FakeCombo):
    """A QComboBox stand-in that also carries currentData()."""

    def __init__(self, value=""):
        FakeCombo.__init__(self, value)
        self._data = None

    def currentData(self):
        return self._data


def _panel(cls, obj):
    p = object.__new__(cls)
    p.obj, p._building = obj, True
    p.width = FakeNum(); p.height = FakeNum()
    p.align = FakeCombo(["Center", "Left", "Right"])
    p.offset = FakeNum(); p.tag = _FakeLine()
    p.fuse = FakeCheck()
    p.sketch = _FakeDataCombo(); p.fallback = _FakeDataCombo()
    return p


def _root_obj(**over):
    values = dict(Width=300.0, Height=2800.0, Align="Center", Offset=0.0)
    values.update(over)
    ns = types.SimpleNamespace()
    for k, v in values.items():
        if k in ("Align", "Fuse"):
            setattr(ns, k, v)
        else:
            setattr(ns, k, quantity(v))
    return ns


def test_root_collect_reads_all_fields():
    p = _panel(wg.WallPlusTaskPanel, _root_obj())
    p.align.setCurrentText("Right")
    p.offset.setValue(50.0)
    p.width.setValue(400.0)
    p.fuse.setChecked(True)
    got = p._collect()
    assert got["width"] == 400.0
    assert got["align"] == "Right"
    assert got["offset"] == 50.0
    assert got["fuse"] is True


def test_root_load_pushes_object_values_onto_widgets():
    p = _panel(wg.WallPlusTaskPanel, _root_obj(Width=400.0, Align="Left"))
    p._loadFromObject()
    assert p.width.value() == 400.0
    assert p.align.currentText() == "Left"
    assert p.fuse.isChecked() is False


def test_root_load_checks_fuse_for_a_fusing_wall():
    p = _panel(wg.WallPlusTaskPanel, _root_obj(Fuse=True))
    p._loadFromObject()
    assert p.fuse.isChecked() is True


def _seg_obj(**over):
    values = dict(Width=200.0, Height=0.0, Align="Inherit")
    values.update(over)
    ns = types.SimpleNamespace()
    for k, v in values.items():
        if k == "Align":
            ns.Align = v
        else:
            setattr(ns, k, quantity(v))
    return ns


def _seg_panel(obj):
    p = object.__new__(wg.WallSegmentTaskPanel)
    p.obj, p._building = obj, True
    p.overrideW = FakeCheck(); p.overrideH = FakeCheck()
    p.width = FakeNum(); p.height = FakeNum()
    p.align = FakeCombo(["Inherit", "Center", "Left", "Right"])
    p.stats = FakeCheck()
    return p


def test_segment_collect_overrides_only_checked_fields():
    p = _seg_panel(_seg_obj())
    p.overrideW.setChecked(True); p.width.setValue(250.0)
    p.overrideH.setChecked(False)
    p.align.setCurrentText("Inherit")
    got = p._collect()
    assert got == {"width": 250.0, "height": 0.0, "align": "Inherit"}


def test_segment_load_checks_override_for_nonzero_width():
    p = _seg_panel(_seg_obj(Width=200.0, Height=0.0, Align="Inherit"))
    p._loadFromObject()
    assert p.overrideW.isChecked() is True
    assert p.overrideH.isChecked() is False
    assert p.width.value() == 200.0
    assert p.align.currentText() == "Inherit"


class _FakeWallObject:
    """Enough of a wall object for wall_root() / all_segments(): the role
    lives in the proxy, the tree in Group, the root link in Wall."""

    def __init__(self, name, segment=False):
        self.Name = name
        self.Proxy = types.SimpleNamespace(Type="Wall", Segment=segment)
        self.Group = []
        self.Wall = None


class _RecordingDoc:
    """A document that records what a live path asked it to recompute."""

    def __init__(self):
        self.calls = []

    def recompute(self, objects=None):
        self.calls.append(objects)


def _wall_tree():
    root = _FakeWallObject("Wall")
    outer = _FakeWallObject("SegA", segment=True)
    nested = _FakeWallObject("SegB", segment=True)
    sibling = _FakeWallObject("SegC", segment=True)
    outer.Group = [nested]
    root.Group = [outer, sibling]
    for seg in (outer, nested, sibling):
        seg.Wall = root
    return root, outer, nested, sibling


def test_a_live_panel_edit_recomputes_the_wall_and_nothing_else(monkeypatch):
    """The wall's own objects and nothing else: everything downstream of them
    — the section views, the TechDraw pages — is what made one spinner step
    cost ~45s on a real plan, and it only needs the finished wall, which
    accept()'s document recompute builds."""
    doc = _RecordingDoc()
    monkeypatch.setattr(FreeCAD, "ActiveDocument", doc)
    root, outer, nested, sibling = _wall_tree()

    wg._refreshLive(outer)

    assert doc.calls == [[root, outer, nested, sibling]]


def test_a_root_edit_targets_the_whole_wall(monkeypatch):
    doc = _RecordingDoc()
    monkeypatch.setattr(FreeCAD, "ActiveDocument", doc)
    root, outer, nested, sibling = _wall_tree()

    wg._refreshLive(root)

    assert doc.calls == [[root, outer, nested, sibling]]


def test_no_object_recomputes_nothing(monkeypatch):
    """accept() and reject() call _apply() on a panel whose object may already
    be cleared: that must not recompute anything at all."""
    doc = _RecordingDoc()
    monkeypatch.setattr(FreeCAD, "ActiveDocument", doc)

    wg._refreshLive(None)

    assert doc.calls == []
