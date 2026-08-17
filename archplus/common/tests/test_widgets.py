# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Tests for the shared ArchPlus Qt widget helpers. The conftest fakes make
# PySide an empty module, so the tests that need a Qt class monkeypatch one in.

import os

from archplus.common import widgets
from conftest import FakeNum, quantity


def test_mm_reads_a_freecad_quantity_property():
    class QuantityWidget:
        def property(self, name):
            assert name == "value"
            return quantity(900.0)

    assert widgets.mm(QuantityWidget()) == 900.0


def test_mm_falls_back_to_a_plain_value():
    assert widgets.mm(FakeNum(750.0)) == 750.0


def test_set_mm_falls_back_to_set_value():
    w = FakeNum(0.0)
    widgets.set_mm(w, 2100.0)
    assert w.value() == 2100.0


def test_length_input_falls_back_to_a_millimetre_spinbox(monkeypatch):
    # The fake FreeCADGui has no UiLoader, so the Gui::QuantitySpinBox branch
    # raises and the plain-spinbox fallback runs.
    from PySide import QtGui

    class SpinBox:
        def setRange(self, lo, hi):
            self.range = (lo, hi)

        def setDecimals(self, d):
            self.decimals = d

        def setSuffix(self, s):
            self.suffix = s

        def setValue(self, v):
            self.v = v

    monkeypatch.setattr(QtGui, "QDoubleSpinBox", SpinBox, raising=False)
    w = widgets.length_input(2100.0)
    assert w.v == 2100.0
    assert w.suffix == " mm"


class _Label:
    def __init__(self):
        self.pixmap = None
        self.cleared = False

    def setPixmap(self, p):
        self.pixmap = p

    def clear(self):
        self.cleared = True


def test_set_ref_image_clears_the_label_when_the_icon_is_missing():
    lbl = _Label()
    widgets.set_ref_image(lbl, "/nonexistent", "absent", (10, 10))
    assert lbl.cleared
    assert lbl.pixmap is None


def test_set_ref_image_sets_a_pixmap_when_the_icon_exists(tmp_path, monkeypatch):
    from PySide import QtGui

    icon = tmp_path / "ref.svg"
    icon.write_text("<svg/>")

    class FakeIcon:
        def __init__(self, path):
            self.path = path

        def pixmap(self, size):
            return ("pixmap", self.path, size)

    monkeypatch.setattr(QtGui, "QIcon", FakeIcon, raising=False)
    lbl = _Label()
    widgets.set_ref_image(lbl, str(tmp_path), "ref", (10, 10))
    assert lbl.pixmap == ("pixmap", os.path.join(str(tmp_path), "ref.svg"), (10, 10))
    assert not lbl.cleared
