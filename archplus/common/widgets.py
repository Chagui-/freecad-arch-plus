# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Qt widget helpers shared by the ArchPlus task panels.
#
# Kept separate from archplus/common/geometry.py on purpose: this module pulls in
# PySide, that one pulls in Part/Sketcher. Merging them would mean importing
# either drags in both, which would defeat the lazy-import discipline the
# gui modules rely on to stay out of BIM workbench init.

import os

import FreeCAD
import FreeCADGui
from PySide import QtGui, QtCore


def mm(w):
    """Read a length widget's value in millimetres (FreeCAD's base unit)."""
    try:
        return float(w.property("value").Value)
    except Exception:
        return float(w.value())


def set_mm(w, value):
    """Set a length widget from a value in millimetres."""
    try:
        w.setProperty("value", FreeCAD.Units.Quantity("%.6f mm" % float(value)))
    except Exception:
        w.setValue(float(value))


def length_input(default):
    """A unit-aware length input. Gui::QuantitySpinBox shows/parses values in
    the user's configured unit schema (mm, cm, inch, ...) while storing the
    value internally in mm. Falls back to a plain mm spinbox if the FreeCAD
    widget can't be created (e.g. no GUI)."""
    try:
        w = FreeCADGui.UiLoader().createWidget("Gui::QuantitySpinBox")
        w.setProperty("value", FreeCAD.Units.Quantity("%.6f mm" % float(default)))
        return w
    except Exception:
        w = QtGui.QDoubleSpinBox()
        w.setRange(0, 1_000_000)
        w.setDecimals(1)
        w.setSuffix(" mm")
        w.setValue(default)
        return w


def set_ref_image(lbl, icon_dir, name, size):
    """Set (or clear) a reference SVG on an existing label."""
    path = os.path.join(icon_dir, name + ".svg")
    if os.path.exists(path):
        lbl.setPixmap(QtGui.QIcon(path).pixmap(size))
    else:
        lbl.clear()


def ref_image(icon_dir, name, size):
    """A centered QLabel holding a reference SVG (or empty if missing)."""
    lbl = QtGui.QLabel()
    lbl.setAlignment(QtCore.Qt.AlignCenter)
    set_ref_image(lbl, icon_dir, name, size)
    return lbl


# Default gap between flowed items, in pixels.
FLOW_SPACING = 6


def flow_positions(sizes, width, spacing=FLOW_SPACING):
    """Left-to-right, top-to-bottom positions for `sizes` within `width`.

    `sizes` is a sequence of (w, h). Returns (positions, total_height), where
    positions is a list of (x, y) in the same order.

    Split out from FlowLayout below for the same reason theme.py splits
    is_dark_theme_name() out of read_is_dark_theme(): the arithmetic is where
    the bugs are, and this way it is unit-testable with no Qt process at all.

    An item wider than `width` is placed on a row of its own rather than
    dropped - a room chip that overhangs a narrow panel is bad, a room chip
    that silently vanishes is worse."""
    positions = []
    x = y = 0
    row_height = 0
    for item_width, item_height in sizes:
        if positions and x + item_width > width:
            x = 0
            y += row_height + spacing
            row_height = 0
        positions.append((x, y))
        x += item_width + spacing
        row_height = max(row_height, item_height)
    return positions, (y + row_height if positions else 0)


class FlowLayout(QtGui.QLayout):
    """A QLayout that wraps its items onto as many rows as it needs.

    Qt ships no wrapping box layout, and QHBoxLayout cannot wrap - which is
    why the parts library's room chips need this. It reflows from
    heightForWidth(), so nothing has to watch resize events; the panel's
    old hand-rolled category reflow (and its viewport eventFilter) went
    away with the screen it served.

    All the arithmetic is in flow_positions() above, which is tested; what
    is left here is Qt bookkeeping."""

    def __init__(self, parent=None, spacing=FLOW_SPACING):
        QtGui.QLayout.__init__(self, parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    # -- the five methods QLayout requires a subclass to provide -----------
    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def sizeHint(self):
        return self.minimumSize()

    # -- wrapping ----------------------------------------------------------
    def expandingDirections(self):
        return QtCore.Qt.Orientations(QtCore.Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        _positions, height = flow_positions(
            self._sizes(), width, self._spacing)
        return height

    def setGeometry(self, rect):
        QtGui.QLayout.setGeometry(self, rect)
        positions, _height = flow_positions(
            self._sizes(), rect.width(), self._spacing)
        for item, (x, y) in zip(self._items, positions):
            size = item.sizeHint()
            item.setGeometry(QtCore.QRect(
                rect.x() + x, rect.y() + y, size.width(), size.height()))

    def minimumSize(self):
        # As wide as the widest single item and as tall as one row: the
        # layout can always wrap, so anything more would stop the panel
        # being narrowed.
        width = height = 0
        for item in self._items:
            size = item.minimumSize()
            width = max(width, size.width())
            height = max(height, size.height())
        return QtCore.QSize(width, height)

    def _sizes(self):
        return [(item.sizeHint().width(), item.sizeHint().height())
                for item in self._items]
