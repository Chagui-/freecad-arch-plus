# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Base-sketch visibility checks for the door/window task panels. Run inside
# a FreeCAD GUI session.
#
# makeWindow and the placement commands hide the construction sketch, but
# the task panels' live update (_apply) swaps a FRESHLY created sketch in
# as Base — and a new sketch is visible by default. These checks drive the
# real _apply and assert the resulting base sketch is hidden, the same
# contract the fakes-based unit tests hold.

from archplus.freecad_tests import _harness as h

import FreeCAD

from archplus.tools.doors import gui as dg
from archplus.tools.doors import object as do
from archplus.tools.windows import gui as wg
from archplus.tools.windows import object as wo


class _Combo:
    def __init__(self, text):
        self._t = text

    def currentText(self):
        return self._t


class _Num:
    def __init__(self, v):
        self._v = v

    def value(self):
        return self._v


class _Check:
    def __init__(self, v):
        self._v = v

    def isChecked(self):
        return self._v


def run():
    doc = h.fresh_doc()

    # --- Window: a panel rebuild (like a live update or accept) must leave
    # the new base sketch hidden, exactly like makeWindow does.
    spec = dict(shape="Rectangular", operation="Single casement",
                width=1200.0, height=1200.0, frameWidth=50.0, sashThk=45.0,
                frameDepth=100.0, swingSide="Left", swingDir="Inward",
                panelPos="Front")
    sketch, wp = wg._makeWindowGeometry(spec)
    win = wo.makeWindow(sketch, 1200.0, 1200.0, wp, name="Win")
    doc.recompute()
    h.check("window creation hides its base sketch",
            not win.Base.ViewObject.Visibility,
            detail="visible=%r" % win.Base.ViewObject.Visibility)

    old_base = win.Base
    p = object.__new__(wg.WindowsPlusTaskPanel)
    p.obj = win
    p._sketch = old_base
    p.shape = _Combo("Rectangular")
    p.operation = _Combo("Single casement")
    p.width = _Num(1200.0)
    p.height = _Num(1200.0)
    p.frameWidth = _Num(50.0)
    p.sashThk = _Num(45.0)
    p.frameDepth = _Num(100.0)
    p.swingSide = _Combo("Left")
    p.swingDir = _Combo("Inward")
    p.panelPos = _Combo("Front")
    p.opening = _Num(0)
    p.symbolPlan = _Check(True)
    p.symbolElev = _Check(False)
    p._apply()
    doc.recompute()
    h.check("window panel rebuild hides the new base sketch",
            win.Base is not old_base
            and not win.Base.ViewObject.Visibility,
            detail="swapped=%r visible=%r"
            % (win.Base is not old_base, win.Base.ViewObject.Visibility))

    # --- Door: same contract.
    dspec = dict(operation="Single swing", panelStyle="Solid",
                 width=900.0, height=2100.0, frameWidth=70.0, panelThk=45.0,
                 frameDepth=100.0, swingSide="Left", swingDir="Inward",
                 panelPos="Centered")
    sketch, dwp = dg._makeDoorGeometry(dspec)
    door = do.makeWindow(sketch, 900.0, 2100.0, dwp, name="Door")
    doc.recompute()
    h.check("door creation hides its base sketch",
            not door.Base.ViewObject.Visibility,
            detail="visible=%r" % door.Base.ViewObject.Visibility)

    old_base = door.Base
    p = object.__new__(dg.DoorsPlusTaskPanel)
    p.obj = door
    p._sketch = old_base
    p.operation = _Combo("Single swing")
    p.panelStyle = _Combo("Solid")
    p.width = _Num(900.0)
    p.height = _Num(2100.0)
    p.frameWidth = _Num(70.0)
    p.panelThk = _Num(45.0)
    p.frameDepth = _Num(100.0)
    p.swingSide = _Combo("Left")
    p.swingDir = _Combo("Inward")
    p.panelPos = _Combo("Centered")
    p.opening = _Num(0)
    p.symbolPlan = _Check(True)
    p.symbolElev = _Check(False)
    p._apply()
    doc.recompute()
    h.check("door panel rebuild hides the new base sketch",
            door.Base is not old_base
            and not door.Base.ViewObject.Visibility,
            detail="swapped=%r visible=%r"
            % (door.Base is not old_base, door.Base.ViewObject.Visibility))

    return h.failures()
