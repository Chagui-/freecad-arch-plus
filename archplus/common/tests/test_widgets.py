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


def test_items_that_fit_stay_on_one_row():
    positions, height = widgets.flow_positions(
        [(50, 20), (50, 20), (50, 20)], width=200, spacing=5)
    assert positions == [(0, 0), (55, 0), (110, 0)]
    assert height == 20


def test_an_item_that_would_overflow_starts_a_new_row():
    positions, height = widgets.flow_positions(
        [(80, 20), (80, 20), (80, 20)], width=200, spacing=5)
    assert positions == [(0, 0), (85, 0), (0, 25)]
    assert height == 45


def test_a_row_is_as_tall_as_its_tallest_item():
    positions, height = widgets.flow_positions(
        [(80, 20), (80, 40), (80, 20)], width=200, spacing=5)
    assert positions == [(0, 0), (85, 0), (0, 45)]
    assert height == 65


def test_an_item_wider_than_the_row_gets_a_row_to_itself():
    # It must still be PLACED. Dropping it would silently hide a room chip
    # in a narrow panel, which is worse than letting it overhang.
    positions, height = widgets.flow_positions(
        [(50, 20), (500, 20)], width=200, spacing=5)
    assert positions == [(0, 0), (0, 25)]
    assert height == 45


def test_no_items_is_no_height():
    assert widgets.flow_positions([], width=200, spacing=5) == ([], 0)
