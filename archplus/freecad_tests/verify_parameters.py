# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Parameter form and display-unit checks: Parts P and U of
# docs/PARTS-LIBRARY-VERIFICATION.md. The derived-field checks use the
# chest of drawers (DrawerCount drives a derived Height) - the one shipped
# part whose declared params and an auto field line up for the pin/reset
# flow.

from archplus.freecad_tests import _harness as h

from archplus.tools.partslib import gui as partslib_gui


def _select(panel, query):
    panel.search.setText(query)
    h.process_events(400)
    panel.grid.setCurrentRow(0)
    h.process_events(300)


def _field(form, name):
    return form._widgets.get(name)


def _type_text(widget, text):
    """Simulate typing into a length field, then accept it."""
    widget.lineEdit().setText(text)
    widget.interpretText()


def _edit(form, name, value=None, text=None):
    """Set a field and report the edit the way a user finishing would."""
    widget = _field(form, name)
    if widget is None:
        return None
    if text is not None:
        _type_text(widget, text)
    elif value is not None:
        widget.setValue(value)
    form._onEdited(name)
    return widget


def run():
    panel = partslib_gui.showPanel()

    # --- chest of drawers: all fields flat, derived Height.
    _select(panel, "chest of drawers")
    form = panel.paramForm
    h.check("P1 DrawerCount/Width/Depth are editable fields",
            all(_field(form, n) is not None
                for n in ("DrawerCount", "Width", "Depth")))
    h.check("P1 Height is visible in the same flat list and starts "
            "derived (auto)",
            _field(form, "Height") is not None
            and "Height" in form._auto,
            detail="widgets=%r auto=%r"
            % (sorted(form._widgets), sorted(form._auto)))

    # --- pinning and reset.
    _edit(form, "Height", value=100)
    h.check("P4 editing Height pins it (no longer derived)",
            "Height" not in form._auto)
    h.check("P6 the pinned value is the edited value",
            _field(form, "Height").value() == 100,
            detail="value=%r" % (_field(form, "Height").value(),))
    form._resetButton.click()
    h.check("P4 Reset restores the derived state",
            "Height" in form._auto and form.isPristine())

    # --- editing a driver param.
    h.mark("before Width edit")
    width = _edit(form, "Width", value=80)
    h.mark("after Width edit")
    h.check("P5 Width 80 edits to 800 mm",
            width is not None and width.mmValue() == 800,
            detail="mmValue=%r" % (width.mmValue() if width else None,))

    # --- units, on the base cabinet (Width default 600 mm).
    _select(panel, "base cabinet")
    form = panel.paramForm
    width = _field(form, "Width")
    h.check("U1 Width shows centimetres",
            width is not None and width.unit() == "cm"
            and width.text() == "60.0 cm",
            detail="unit=%r text=%r"
            % (width.unit() if width else None,
               width.text() if width else None))
    _type_text(width, "800 mm")
    h.check("U2 typing 800 mm settles on 80.0 cm",
            width.text() == "80.0 cm" and width.mmValue() == 800,
            detail="text=%r mm=%r" % (width.text(), width.mmValue()))
    _type_text(width, "2 ft")
    h.check("U5 typing 2 ft builds 610 mm, not a rounded 609.6",
            width.mmValue() == 610,
            detail="text=%r mm=%r" % (width.text(), width.mmValue()))
    before = width.mmValue()
    _type_text(width, "abc")
    h.check("U4 nonsense input is refused, value unchanged",
            width.mmValue() == before,
            detail="mm=%r text=%r" % (width.mmValue(), width.text()))

    # --- television Mounting choice.
    _select(panel, "television")
    mounting = _field(panel.paramForm, "Mounting")
    h.check("P9 Mounting is a choice with Wall-mounted",
            mounting is not None
            and any("Wall" in mounting.itemText(i)
                    for i in range(mounting.count())),
            detail="items=%r" % ([mounting.itemText(i)
                                  for i in range(mounting.count())]
                                 if mounting else None))

    # --- king bed reads in the pinned display unit.
    _select(panel, "king bed")
    width = _field(panel.paramForm, "Width")
    h.check("U6 King bed Width reads 180.0 cm / 1800 mm",
            width is not None
            and width.text() == "180.0 cm" and width.mmValue() == 1800,
            detail="text=%r mm=%r"
            % (width.text() if width else None,
               width.mmValue() if width else None))

    return h.failures()
