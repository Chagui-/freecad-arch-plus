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
