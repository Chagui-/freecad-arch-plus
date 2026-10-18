# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Targeted recomputes for the task panels' live paths.
#
# A panel that edits an object rebuilds not only that object but every
# dependent of it, and on a real plan the dependents are the drawings: the
# section views project whole floors, and the TechDraw views, dimensions and
# pages downstream of them rebuild on top of that. Measured on
# atahualpa_1984_alt-2, one wall segment width step cost 26.5 s of recompute
# plus 20.3 s of repaint, against 1.0 s for the wall itself. The drawings only
# need the *finished* state, which every panel's accept() provides, so a live
# path recomputes its own objects and leaves the rest of the document alone.

import FreeCAD


def recompute_only(objects):
    """Recompute just `objects`, falling back to the whole document.

    FreeCAD 1.1's Document.recompute(objs) is what makes a live edit cheap;
    older builds only take the document-wide form, and a failed call must
    still leave the model built rather than silently stale. No document at all
    (a live handler firing while the last one closes) is nothing to do."""
    doc = FreeCAD.ActiveDocument
    if doc is None:
        return
    try:
        return doc.recompute(objects)
    except TypeError:
        return doc.recompute()
