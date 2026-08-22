# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Test harness bootstrap.
#
# The ArchPlus GUI modules import FreeCAD, FreeCADGui and PySide, none of which
# are available under a plain `pytest` run. Those modules are only *used* inside
# functions, never at import time, so we install lightweight fakes into
# sys.modules before the modules under test are imported. This lets us unit-test
# the pure logic — operation predicates, opening-mode mapping, the
# WindowParts/DoorParts geometry strings, and spec persistence — without a full
# FreeCAD install. The fakes are deliberately minimal: just enough surface for
# the code paths the tests exercise.

import os
import sys
import types

# Make the add-on modules (in the repo root) importable.
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# --- Qt widget stand-ins (installed into the fake PySide below) -----------
class _FakeWidget:
    """Enough QWidget for a panel class statement to execute."""

    def __init__(self, parent=None):
        self._parent = parent


class _FakeLayout:
    """Enough QLayout for a subclass's class statement to execute.

    FlowLayout's arithmetic lives in the pure flow_positions() and is tested
    directly; what this stub buys is that importing archplus.common.widgets
    headlessly does not explode on the class statement."""

    def __init__(self, parent=None):
        self._parent = parent

    def setContentsMargins(self, *margins):
        pass

    def setGeometry(self, rect):
        pass


class _FakeDoubleSpinBox(_FakeWidget):
    """QDoubleSpinBox as far as LengthSpinBox uses it.

    setValue() rounds to decimals() and clamps to the range because the real
    widget does, and LengthSpinBox's millimetre round-trip depends on both."""

    def __init__(self, parent=None):
        _FakeWidget.__init__(self, parent)
        self._value = 0.0
        self._decimals = 2
        self._min = 0.0
        self._max = 99.99
        self._tip = ""

    def setDecimals(self, places):
        self._decimals = int(places)

    def decimals(self):
        return self._decimals

    def setRange(self, low, high):
        self._min, self._max = float(low), float(high)

    def setValue(self, value):
        value = round(float(value), self._decimals)
        self._value = max(self._min, min(self._max, value))

    def value(self):
        return self._value

    def setToolTip(self, text):
        self._tip = text

    def toolTip(self):
        return self._tip

    def minimum(self):
        return self._min

    def maximum(self):
        return self._max

    def setMinimumWidth(self, pixels):
        # No font metrics exist headlessly, so LengthSpinBox's sizing falls
        # back to 0 here. What the tests cover is that asking for a width
        # cannot raise; the pixel arithmetic itself is GUI-only.
        self._minimum_width = pixels


# --- Fake geometry kernel objects -----------------------------------------
class _Vector:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = x, y, z

    def __repr__(self):
        return "Vector(%g, %g, %g)" % (self.x, self.y, self.z)


class _LineSegment:
    TypeId = "Part::GeomLineSegment"

    def __init__(self, p1, p2):
        self.p1, self.p2 = p1, p2


class _Circle:
    TypeId = "Part::GeomCircle"

    def __init__(self, center, normal, radius):
        self.center, self.normal, self.radius = center, normal, radius


class _Constraint:
    def __init__(self, *args):
        self.args = args


class _FakeSketch:
    """Records geometry and constraints the way Sketcher::SketchObject would,
    enough for the *Plus geometry builders to run and produce WindowParts."""

    def __init__(self):
        self.Geometry = []
        self.Constraints = []

    @property
    def GeometryCount(self):
        return len(self.Geometry)

    @property
    def ConstraintCount(self):
        return len(self.Constraints)

    def addGeometry(self, geo, *rest):
        self.Geometry.append(geo)
        return len(self.Geometry) - 1

    def addConstraint(self, con):
        self.Constraints.append(con)
        return len(self.Constraints) - 1

    def renameConstraint(self, idx, name):
        pass


class _FakeDocument:
    def addObject(self, otype, name):
        return _FakeSketch()

    def recompute(self):
        pass


def _install_fakes():
    # Installing these stubs REPLACES the real modules in sys.modules. This
    # file sits at the add-on root, which FreeCAD puts on sys.path, so a stray
    # `import conftest` inside a live FreeCAD session could otherwise destroy
    # the real bindings. Only ever shadow when we are genuinely under pytest.
    if "pytest" not in sys.modules:
        return

    # FreeCAD
    freecad = types.ModuleType("FreeCAD")
    freecad.Vector = _Vector
    freecad.ActiveDocument = _FakeDocument()
    freecad.Console = types.SimpleNamespace(
        PrintError=lambda *a, **k: None,
        PrintMessage=lambda *a, **k: None,
        PrintWarning=lambda *a, **k: None,
    )
    freecad.Units = types.SimpleNamespace(Quantity=lambda *a, **k: None)
    freecad.newDocument = lambda *a, **k: _FakeDocument()
    sys.modules["FreeCAD"] = freecad

    # FreeCADGui — the modules register their commands at import time
    # (listCommands/addCommand); everything else is inside interactive code
    # paths the tests don't exercise.
    freecadgui = types.ModuleType("FreeCADGui")
    freecadgui.listCommands = lambda: []
    freecadgui.addCommand = lambda name, obj: None
    sys.modules["FreeCADGui"] = freecadgui

    # PySide.QtGui / QtCore — placeholders. Most widgets are never built in
    # the tested code paths, but paramform.LengthSpinBox subclasses
    # QDoubleSpinBox and carries real logic (the millimetre boundary and the
    # validator states), so the stand-in below implements the parts of that
    # class the logic leans on: rounding to decimals() and clamping to the
    # range, both of which real QDoubleSpinBox.setValue() does.
    pyside = types.ModuleType("PySide")
    qtgui = types.ModuleType("PySide.QtGui")
    qtcore = types.ModuleType("PySide.QtCore")
    qtgui.QWidget = _FakeWidget
    qtgui.QLayout = _FakeLayout
    qtgui.QDoubleSpinBox = _FakeDoubleSpinBox
    qtgui.QValidator = types.SimpleNamespace(
        Invalid="invalid", Intermediate="intermediate",
        Acceptable="acceptable")
    qtcore.Signal = lambda *a, **k: None
    pyside.QtGui = qtgui
    pyside.QtCore = qtcore
    sys.modules["PySide"] = pyside
    sys.modules["PySide.QtGui"] = qtgui
    sys.modules["PySide.QtCore"] = qtcore

    # Geometry kernel
    part = types.ModuleType("Part")
    part.LineSegment = _LineSegment
    part.Circle = _Circle
    sys.modules["Part"] = part

    sketcher = types.ModuleType("Sketcher")
    sketcher.Constraint = _Constraint
    sys.modules["Sketcher"] = sketcher


_install_fakes()


import pytest  # noqa: E402  (must follow the fake-module install)


class FakeObj:
    """Mimics a FreeCAD App object's dynamic-property behaviour, enough for
    storeSpec()/readSpec(): addProperty creates the attribute, setEditorMode is
    a no-op, and getattr/setattr work as usual."""

    def addProperty(self, ptype, name, group="", doc=""):
        setattr(self, name, "")
        return self

    def setEditorMode(self, name, mode):
        pass


@pytest.fixture
def fake_obj():
    return FakeObj()


# --- Minimal widget fakes -------------------------------------------------
# The edit round-trip tests drive the panels' real _loadFromObject() and
# _collect() against these stand-ins (constructed via object.__new__, so the
# heavy Qt __init__ is skipped). They only need to hold a value the way the
# corresponding Qt widget would.
class FakeCombo:
    def __init__(self, value=""):
        self._v = value

    def currentText(self):
        return self._v

    def setCurrentText(self, value):
        self._v = value


class FakeNum:
    """Stands in for a Gui::QuantitySpinBox or QSpinBox. _mm/_setmm fall back
    to value()/setValue() when the quantity API (property('value')) is absent."""

    def __init__(self, value=0.0):
        self._v = value

    def value(self):
        return self._v

    def setValue(self, value):
        self._v = value

    def setMaximum(self, _):
        pass

    def setMinimum(self, _):
        pass


class FakeCheck:
    def __init__(self, value=False):
        self._v = value

    def isChecked(self):
        return self._v

    def setChecked(self, value):
        self._v = bool(value)


def quantity(value):
    """A FreeCAD-style quantity property: has a .Value."""
    return types.SimpleNamespace(Value=float(value))


def fake_base(z=0.0, geometry=None):
    """A base-sketch stand-in: a Placement (for sill height) and optional
    Geometry list (for round-shape inference on legacy objects)."""
    return types.SimpleNamespace(
        Placement=types.SimpleNamespace(Base=types.SimpleNamespace(z=z)),
        Geometry=geometry or [],
    )
