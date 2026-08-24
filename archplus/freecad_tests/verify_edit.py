# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Edit checks: opening a placed part in the edit task panel and editing its
# parameters - Part L of docs/PARTS-LIBRARY-VERIFICATION.md (L1-L6).
#
# Everything here goes through the same routing the double-click and the
# context-menu entry use (gui.editPart), so covering that one path covers
# all three.

from archplus.freecad_tests import _harness as h

import FreeCAD

from archplus.tools.partslib import object as partslib_object
from archplus.tools.partslib import gui as partslib_gui


def _facets():
    return partslib_object.libraryIndex()["facets"]


def _entry(part_id):
    return partslib_object.resolveEntry(part_id)[0]


def _make(part_id, placement=None):
    return partslib_object.makePart(_entry(part_id), _facets(),
                                    placement=placement)


def run():
    doc = h.fresh_doc()
    bed = _make("basic/king-bed")
    chest = _make("basic/chest-of-drawers")

    # L1 - entering edit loads the part's current values onto the task
    # panel. The king bed declares nothing derived, so nothing shows as
    # derived - the form must reflect the OBJECT, not guess.
    ok = partslib_gui.editPart(bed)
    panel = partslib_gui._editPanel
    h.process_events(100)
    displayed = panel.editForm.displayed() if panel is not None else {}
    auto = panel.editForm.autoNames() if panel is not None else set()
    h.check("L1 editPart opens a task panel with current values",
            ok and panel is not None and panel.obj is bed
            and abs(displayed.get("Width", 0.0) - 1800.0) < 0.1
            and abs(displayed.get("Length", 0.0) - 2000.0) < 0.1
            and auto == set(),
            detail="ok=%r panel=%r obj=%r displayed=%r auto=%r"
            % (ok, panel is not None, getattr(panel, "obj", None),
               displayed, auto))

    # L2 - editing a field rebuilds the placed part live, and pins the
    # field on the object.
    panel.editForm.setField("Width", 1600.0)
    h.process_events(500)  # the live apply is debounced
    h.check("L2 editing a field rebuilds the placed part live",
            abs(bed.Width.Value - 1600.0) < 0.1
            and "Width" not in (bed.AutoParams or [])
            and abs(bed.Shape.BoundBox.XLength - 1600.0) < 0.1,
            detail="Width=%.1f AutoParams=%r XLength=%.1f"
            % (bed.Width.Value, bed.AutoParams,
               bed.Shape.BoundBox.XLength))

    # L3 - Reset puts the field back to the manifest's answer.
    panel.editForm.reset()
    h.process_events(500)
    h.check("L3 Reset restores the manifest default",
            abs(bed.Width.Value - 1800.0) < 0.1,
            detail="Width=%.1f" % (bed.Width.Value,))

    # L4 - Apply commits the whole edit session as one undo step.
    panel.editForm.setField("Width", 1600.0)
    h.process_events(500)
    panel._onApply()
    h.process_events(100)
    h.check("L4 Apply commits the edited value",
            abs(bed.Width.Value - 1600.0) < 0.1
            and "Width" not in (bed.AutoParams or [])
            and panel.obj is None,
            detail="Width=%.1f AutoParams=%r obj=%r"
            % (bed.Width.Value, bed.AutoParams, getattr(panel, "obj", None)))
    undoable = bool(doc.UndoNames)
    if undoable:
        doc.undo()
    h.check("L4 the committed edit is one undo step",
            undoable and abs(bed.Width.Value - 1800.0) < 0.1,
            detail="undoable=%r Width=%.1f"
            % (undoable, bed.Width.Value))
    if undoable:
        doc.redo()
        h.check("L4 redo restores the edited value",
                abs(bed.Width.Value - 1600.0) < 0.1,
                detail="Width=%.1f" % (bed.Width.Value,))

    # L5 - a derived field loads as derived, and Discard rolls the whole
    # session back: the pin is gone, the derived value is back.
    derived_before = chest.Height.Value
    partslib_gui.editPart(chest)
    panel = partslib_gui._editPanel
    h.process_events(100)
    displayed = panel.editForm.displayed() if panel is not None else {}
    auto = panel.editForm.autoNames() if panel is not None else set()
    # 1 mm of tolerance: the cm field rounds the property's 800.3866 mm to
    # a displayed 800.0, by design.
    h.check("L5 the chest's derived Height loads as derived",
            "Height" in auto
            and abs(displayed.get("Height", 0.0) - derived_before) < 1.0,
            detail="derived_before=%r auto=%r displayed=%r"
            % (derived_before, auto, displayed))
    panel.editForm.setField("Height", 700.0)
    h.process_events(500)
    pinned_before_discard = abs(chest.Height.Value - 700.0) < 0.1
    panel._onDiscard()
    h.process_events(100)
    h.check("L5 Discard rolls the edit back and closes the panel",
            pinned_before_discard
            and abs(chest.Height.Value - derived_before) < 0.1
            and "Height" in (chest.AutoParams or [])
            and panel.obj is None,
            detail="pinned_before=%r Height=%.1f AutoParams=%r obj=%r"
            % (pinned_before_discard, chest.Height.Value,
               chest.AutoParams, getattr(panel, "obj", None)))

    # L6 - one edit at a time; a second part must not hijack the session.
    partslib_gui.editPart(bed)
    panel = partslib_gui._editPanel
    second = partslib_gui.editPart(chest)
    h.check("L6 a second edit refuses while one is open",
            not second and panel.obj is bed,
            detail="second=%r obj=%r"
            % (second, getattr(panel, "obj", None)))
    panel._onDiscard()
    h.process_events(100)

    return h.failures()
