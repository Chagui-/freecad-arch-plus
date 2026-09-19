# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Placement and IFC checks: Parts D (D1/D2/D3/D4/D10) and E (E1/E2) of
# docs/PARTS-LIBRARY-VERIFICATION.md. Placement goes through the same
# code path the browser's click-to-place uses, just with a computed point
# instead of a mouse.

import os
import tempfile

from archplus.freecad_tests import _harness as h

import Arch
import FreeCAD
import FreeCADGui
import Part
from FreeCAD import Vector

from archplus.tools.partslib import manifest as partslib_manifest
from archplus.tools.partslib import object as partslib_object
from archplus.tools.partslib import placement as partslib_placement


def _facets():
    return partslib_object.libraryIndex()["facets"]


def _entry(part_id):
    """resolveEntry returns (entry, facets)."""
    return partslib_object.resolveEntry(part_id)[0]


def _make(part_id, placement=None):
    return partslib_object.makePart(_entry(part_id), _facets(),
                                    placement=placement)


def _front_face(wall):
    for i, face in enumerate(wall.Shape.Faces):
        if face.normalAt(0, 0).isEqual(Vector(0.0, -1.0, 0.0), 1e-6):
            return i
    return 0


def _make_wall(doc):
    base = doc.addObject("Part::Feature", "WallBase")
    base.Shape = Part.LineSegment(Vector(0, 0, 0),
                                  Vector(2000, 0, 0)).toShape()
    return Arch.makeWall(base, width=200, height=2600), base


def run():
    doc = h.fresh_doc()

    # D1/D2 - one object, no children, correct metadata.
    cabinet = _make("basic/base-cabinet",
                    placement=FreeCAD.Placement(Vector(100, 200, 0),
                                                FreeCAD.Rotation()))
    h.check("D1 placing adds exactly one object with no children",
            len(doc.Objects) == 1 and not cabinet.OutList,
            detail="objects=%r" % ([o.Label for o in doc.Objects],))
    h.check("D2 PartId is the derived id and read-only",
            cabinet.PartId == "basic/base-cabinet"
            and cabinet.getEditorMode("PartId") == ["ReadOnly"],
            detail="PartId=%r" % (cabinet.PartId,))
    h.check("D2 Description and IfcType resolve from the facets",
            bool(cabinet.Description) and cabinet.IfcType == "Furniture",
            detail="Description=%r IfcType=%r"
            % (cabinet.Description[:20], cabinet.IfcType))
    h.check("D10 parameters live in the Parameters group",
            cabinet.getGroupOfProperty("Width") == "Parameters",
            detail="group=%r" % (cabinet.getGroupOfProperty("Width"),))

    # D3 - a property edit rebuilds in place.
    before = cabinet.Placement
    cabinet.Width = 800
    doc.recompute()
    h.check("D3 Width 800 rebuilds in place",
            cabinet.Width.Value == 800 and cabinet.Placement == before,
            detail="Width=%r Placement=%r" % (cabinet.Width.Value,
                                              cabinet.Placement))

    # D4 - wall-hosted placement through the placement module.
    wall, wall_base = _make_wall(doc)
    doc.recompute()  # the wall has no faces until it is built
    entry = _entry("basic/wall-cabinet")
    resolved = partslib_manifest.load_manifest(entry["path"])
    host = partslib_placement.host_of(resolved)
    offset = partslib_placement.offset_of(resolved)
    placement = partslib_placement.partPlacement(
        Vector(1000, 0, 0), (wall, _front_face(wall)), host, offset)
    h.check("D4 wall cabinet is wall-hosted at base + 1500 mm",
            host == "wall" and offset == 1500
            and abs(placement.Base.z - 1500.0) < 1e-6,
            detail="host=%r offset=%r z=%r"
            % (host, offset, placement.Base.z))
    doc.removeObject(wall.Name)
    doc.removeObject(wall_base.Name)

    # E1 - the IFC type resolution chain (no manifest declares its own).
    toilet = _make("basic/toilet")
    h.check("E1 toilet resolves to Sanitary Terminal",
            toilet.IfcType == "Sanitary Terminal",
            detail="IfcType=%r" % (toilet.IfcType,))

    # E2 - IFC export round-trips the types.
    out_path = os.path.join(tempfile.gettempdir(), "archplus_verify.ifc")
    if os.path.exists(out_path):
        os.remove(out_path)
    try:
        from importers import exportIFC
        exportIFC.export([cabinet, toilet], out_path)
        content = ""
        if os.path.exists(out_path):
            with open(out_path, encoding="utf-8", errors="replace") as f:
                content = f.read()
        upper = content.upper()
        # FreeCAD's exporter maps IfcType "Furniture" to the IFC4 entity
        # IfcFurnishingElement (IfcFurniture no longer exists in IFC4).
        h.check("E2 IFC export contains both mapped types",
                "IFCFURNISHINGELEMENT" in upper
                and "IFCSANITARYTERMINAL" in upper,
                detail="bytes=%d" % len(content))
    except Exception as exc:
        h.check("E2 IFC export completes", False, repr(exc))
    finally:
        if os.path.exists(out_path):
            os.remove(out_path)

    # D11 - FreeCAD's own transform tool must work on a placed part. The
    # command enters edit mode ViewProvider::Transform on the selected
    # object's view provider; getInEdit() reporting one afterwards is how
    # a script can see the gizmo started.
    doc = h.fresh_doc()
    bed = _make("basic/king-bed",
                placement=FreeCAD.Placement(Vector(100, 100, 0),
                                            FreeCAD.Rotation()))
    FreeCADGui.Selection.clearSelection()
    FreeCADGui.Selection.addSelection(doc.Name, bed.Name)
    try:
        FreeCADGui.runCommand("Std_TransformManip", 0)
        h.process_events(200)
        h.check("D11 transform tool enters transform edit mode",
                FreeCADGui.ActiveDocument.getInEdit() is not None,
                detail="inEdit=%r" % (FreeCADGui.ActiveDocument.getInEdit(),))
    finally:
        if FreeCADGui.ActiveDocument.getInEdit() is not None:
            FreeCADGui.ActiveDocument.resetEdit()
        FreeCADGui.Selection.clearSelection()

    _panel_placement_check()

    return h.failures()


def _panel_placement_check():
    """Placing from the library panel actually drops a part.

    Drives the panel's own pick loop - the move/click callbacks the Snapper
    invokes - because every check above calls makePart directly and so
    bypasses it entirely. That is how a NameError in those callbacks (a
    deleted state dict, #28) stopped panel placement with nothing noticing.

    The move is fed first: the callback that records the picked face only
    runs on a move, and the click reads what it left behind."""
    import pivy.coin as coin
    from archplus.tools.partslib import gui as partslib_gui

    doc = h.fresh_doc()
    before = len(doc.Objects)
    panel = partslib_gui.showPanel()
    h.process_events(400)
    panel.search.setText("nightstand")
    h.process_events(400)
    panel.grid.setCurrentRow(0)
    h.process_events(300)

    errors = []
    original_error = FreeCAD.Console.PrintError
    FreeCAD.Console.PrintError = lambda *a, **k: errors.append(" ".join(map(str, a)))
    try:
        panel._onPlace()
        h.process_events(300)

        class _Event:
            def getPosition(self): return (600, 400)
            def wasCtrlDown(self): return False
            def wasShiftDown(self): return False
            def getButton(self): return 1
            def getState(self): return coin.SoMouseButtonEvent.DOWN

        class _Cb:
            def getEvent(self): return _Event()

        if FreeCADGui.Snapper.callbackMove is not None:
            FreeCADGui.Snapper.callbackMove(_Cb())
        if FreeCADGui.Snapper.callbackClick is not None:
            FreeCADGui.Snapper.callbackClick(_Cb())
        h.process_events(500)
    finally:
        FreeCAD.Console.PrintError = original_error

    placed = [o for o in doc.Objects if partslib_object.isLibraryPart(o)]
    h.check("P1 placing from the library panel drops a part",
            len(placed) == 1 and len(doc.Objects) > before,
            detail="objects +%d, library parts %d, console errors %r"
                   % (len(doc.Objects) - before, len(placed), errors[:2]))
    h.check("P2 the pick callbacks raise nothing",
            not any("NameError" in e or "not defined" in e for e in errors),
            detail="errors=%r" % (errors[:3],))
    partslib_gui.closePanel() if hasattr(partslib_gui, "closePanel") else None
