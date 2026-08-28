# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Headless tests for the wall task panels, driven through fakes exactly like
# test_stairs.py: the panel reads/writes object properties, so _collect /
# _loadFromObject carry the decisions worth testing here.

import types

from archplus.tools.walls import gui as wg
from conftest import FakeCombo, FakeNum, FakeCheck, quantity


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
    p.sketch = _FakeDataCombo(); p.rest = _FakeDataCombo()
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
