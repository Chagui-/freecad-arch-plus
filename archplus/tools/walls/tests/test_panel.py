# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Headless tests for the wall task panels, driven through fakes exactly like
# test_stairs.py: the panel reads/writes object properties, so _collect /
# _loadFromObject carry the decisions worth testing here.

import os
import types

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
    p.sketch = _FakeDataCombo(); p.fallback = _FakeDataCombo()
    return p


def _root_obj(**over):
    values = dict(Width=300.0, Height=2800.0, Align="Center", Offset=0.0)
    values.update(over)
    ns = types.SimpleNamespace()
    for k, v in values.items():
        if k == "Align":
            ns.Align = v
        else:
            setattr(ns, k, quantity(v))
    return ns


def test_root_collect_reads_all_fields():
    p = _panel(wg.WallPlusTaskPanel, _root_obj())
    p.align.setCurrentText("Right")
    p.offset.setValue(50.0)
    p.width.setValue(400.0)
    got = p._collect()
    assert got["width"] == 400.0
    assert got["align"] == "Right"
    assert got["offset"] == 50.0


def test_root_load_pushes_object_values_onto_widgets():
    p = _panel(wg.WallPlusTaskPanel, _root_obj(Width=400.0, Align="Left"))
    p._loadFromObject()
    assert p.width.value() == 400.0
    assert p.align.currentText() == "Left"


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
