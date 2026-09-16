# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Opening-transform convention checks (issue #13). Run inside a FreeCAD GUI
# session; measures real geometry from the real kernel, not string output.
#
# The window/door geometry engine (a copy of FreeCAD's ArchWindow) applies
# opening transforms per part: a part with Edge/Mode computes its own, a
# part without inherits the transform of the last moving part before it
# (the native FreeCAD convention). Moving glass therefore carries NO
# Edge/Mode of its own — if it did, the movement would be derived from the
# glass's own, smaller wire and the glass would lag its frame when opened.
#
# The checks measure the fused shape at Opening=100. Each glass sheet
# extrudes at a depth no other part shares, so its front/back face can be
# located in the fused solid by plane alone; that face's along-wall (X)
# extent proves whether the glass travelled exactly with its frame.

from archplus.freecad_tests import _harness as h

import FreeCAD
import FreeCADGui
import Part

from archplus.tools.doors import gui as dg
from archplus.tools.doors import object as do
from archplus.tools.walls import object as walls_object
from archplus.tools.windows import gui as wg
from archplus.tools.windows import object as wo


def _face_span(obj, z_plane):
    """Along-wall (X) extent of the face whose centroid sits at `z_plane`.

    Returns (xmin, xmax) or None if no face is found there. Parts extrude
    along -Z, so all expected planes are negative."""
    spans = []
    for face in obj.Shape.Faces:
        c = face.CenterOfGravity
        if abs(c.z - z_plane) > 1.0:
            continue
        if abs(face.normalAt(0, 0).z) < 0.99:
            continue
        b = face.BoundBox
        spans.append((b.XMin, b.XMax))
    if len(spans) != 1:
        return None
    return spans[0]


def _close(obj, z_plane, xmin, xmax, label):
    span = _face_span(obj, z_plane)
    ok = span is not None and abs(span[0] - xmin) < 1.0 \
        and abs(span[1] - xmax) < 1.0
    h.check(label, ok,
            detail="expected X span %.1f..%.1f at z=%.1f, measured %r"
            % (xmin, xmax, z_plane, span))


def _drive_pick(pos):
    """Drive one mouse move + left click through the Snapper's own handlers.

    The reposition tools run their pick inside Draft's point session, so the
    only faithful way to exercise them headlessly is to feed the coin event
    callbacks the session registers. Returns nothing; raises if the session
    was never armed."""
    import pivy.coin as coin

    class _Event:
        def __init__(self, pos):
            self._pos = pos

        def getPosition(self):
            return self._pos

        def wasCtrlDown(self):
            return False

        def wasShiftDown(self):
            return False

        def getButton(self):
            return 1

        def getState(self):
            return coin.SoMouseButtonEvent.DOWN

    class _Cb:
        def __init__(self, pos):
            self._ev = _Event(pos)

        def getEvent(self):
            return self._ev

    if FreeCADGui.Snapper.callbackMove is None:
        raise RuntimeError("the pick session was never armed")
    FreeCADGui.Snapper.callbackMove(_Cb(pos))
    FreeCADGui.Snapper.callbackClick(_Cb(pos))
    h.process_events(300)


def _reposition_target(doc, obj, label):
    """Reposition `obj` with a mouse pick over the wall and check where it
    lands.

    Draft's Snapper cannot resolve an ArchPlus wall root (it has no shape),
    so it intersects an infinite plane and hands the tool a point thousands
    of kilometres out; the pick's own surface coordinates are the usable
    ones. This check aims at the middle of the wall's front face, where the
    opening must end up — a regression to the raw Snapper point throws the
    window/door off the drawing entirely."""
    view = FreeCADGui.ActiveDocument.ActiveView
    view.viewFront()
    h.process_events(300)
    view.fitAll()
    h.process_events(300)
    w, ht = view.getSize()

    if getattr(FreeCADGui, "Snapper", None) is None:
        FreeCADGui.activateWorkbench("DraftWorkbench")
        h.process_events(300)

    if label.startswith("window"):
        wg.repositionWindow(obj, reopen=False)
    else:
        dg.repositionDoor(obj, reopen=False)
    h.process_events(300)
    _drive_pick((int(w * 0.5), int(ht * 0.5)))

    pl = obj.Base.Placement
    half = obj.Width.Value / 2.0
    on_face = abs(pl.Base.y + 150.0) < 1.0          # wall front face plane
    along = abs(pl.Base.x - (2000.0 - half)) < 200.0  # centred on the aim
    at_base = abs(pl.Base.z) < 1.0                  # snapped to the wall base
    h.check("%s repositioning lands on the picked wall face" % label,
            on_face and along and at_base,
            detail="base %s (want y=-150, x=%.1f, z=0)" % (pl.Base, 2000.0 - half))


def _reposition_checks(doc):
    sk = doc.addObject("Sketcher::SketchObject", "RepositionPlan")
    sk.addGeometry(Part.LineSegment(FreeCAD.Vector(0, 0, 0),
                                    FreeCAD.Vector(4000, 0, 0)), False)
    doc.recompute()
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()

    spec = dict(shape="Rectangular", operation="Fixed", width=1000,
                height=1000, frameWidth=50, sashThk=45, frameDepth=100,
                swingSide="Left", swingDir="Inward", panelPos="Front")
    wsk, wp = wg._makeWindowGeometry(spec)
    win = wo.makeWindow(wsk, 1000.0, 1000.0, wp, name="RepositionWin")
    win.Hosts = [wall]
    wall.Subtractions = [win]
    doc.recompute()
    _reposition_target(doc, win, "window")

    dspec = dict(operation="Single swing", panelStyle="Solid", width=900.0,
                 height=2100.0, frameWidth=70.0, panelThk=45.0,
                 frameDepth=100.0, swingSide="Left", swingDir="Inward",
                 panelPos="Centered")
    dsk, dwp = dg._makeDoorGeometry(dspec)
    door = do.makeWindow(dsk, 900.0, 2100.0, dwp, name="RepositionDoor")
    door.Hosts = [wall]
    wall.Subtractions = [win, door]
    doc.recompute()
    _reposition_target(doc, door, "door")


def _segment_rebuild_checks(doc):
    """A reposition rebuilds only the segments the opening reached, and a
    move onto another wall drops the cut left behind on the old one."""
    plan = doc.addObject("Sketcher::SketchObject", "RebuildPlan")
    runs = 6
    for i in range(runs):
        plan.addGeometry(Part.LineSegment(FreeCAD.Vector(i * 4000, 0, 0),
                                          FreeCAD.Vector((i + 1) * 4000, 0, 0)),
                         False)
    doc.recompute()
    wall = walls_object.makeWall(doc, sketch=plan)
    doc.recompute()
    for i in range(1, runs):
        seg = walls_object.makeSegment(wall, name="R%d" % i)
        seg.Edges = [(plan, ("Edge%d" % (i + 1),))]
    doc.recompute()
    segments = walls_object.all_segments(wall)

    spec = dict(shape="Rectangular", operation="Fixed", width=1000,
                height=1000, frameWidth=50, sashThk=45, frameDepth=100,
                swingSide="Left", swingDir="Inward", panelPos="Front")
    wsk, wp = wg._makeWindowGeometry(spec)
    win = wo.makeWindow(wsk, 1000.0, 1000.0, wp, name="RebuildWin")
    # sit it inside the first run
    wsk.Placement = FreeCAD.Placement(FreeCAD.Vector(1500, 0, 0),
                                      FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90))
    win.Hosts = [wall]
    wall.Subtractions = [win]
    doc.recompute()

    rebuilt = []
    original = walls_object._Wall._buildSegment

    def recording_build(self, obj):
        rebuilt.append(obj.Name)
        return original(self, obj)

    walls_object._Wall._buildSegment = recording_build
    try:
        old_pl = FreeCAD.Placement(win.Base.Placement)
        win.Base.Placement = FreeCAD.Placement(
            FreeCAD.Vector(2500, 0, 0), old_pl.Rotation)
        swept = wg._opening_sweep(win, old_pl, win.Base.Placement)
        wg._recomputeWithHosts(win, swept)
    finally:
        walls_object._Wall._buildSegment = original
    h.check("a reposition rebuilds only the segments it reached",
            len(rebuilt) == 1 and rebuilt[0] == segments[0].Name,
            detail="rebuilt %r of %d segments" % (rebuilt, len(segments)))
    cut = segments[0].Shape.Volume

    # ... and moving it onto another wall leaves no cut behind
    other = doc.addObject("Sketcher::SketchObject", "OtherPlan")
    other.addGeometry(Part.LineSegment(FreeCAD.Vector(0, 6000, 0),
                                       FreeCAD.Vector(4000, 6000, 0)), False)
    doc.recompute()
    wall2 = walls_object.makeWall(doc, sketch=other, name="Wall2")
    doc.recompute()
    win.Base.Placement = FreeCAD.Placement(
        FreeCAD.Vector(1500, 6000, 0), FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90))
    win.Hosts = [wall2]
    wall2.Subtractions = [win]
    wall.Subtractions = []
    wg._recomputeWithHosts(win)
    untouched = abs(segments[0].Shape.Volume
                    - 300.0 * 2800.0 * 4000.0) < 1e-3
    h.check("moving a window to another wall restores the old segment",
            untouched and segments[0].Shape.Volume > cut,
            detail="volume %.3e (cut was %.3e, full %.3e)"
            % (segments[0].Shape.Volume, cut, 300.0 * 2800.0 * 4000.0))


def run():
    doc = h.fresh_doc()

    # --- Window: single sliding, defaults (w=1200 h=1200 jw=50 sash=45 ---
    # frame=100). The sliding half (Wire4) spans half+tol .. w-jw-tol and
    # slides one chord (540 mm) toward -X at 100%; its glass (Wire5) spans
    # half+sfw .. w-jw-sfw and extrudes at z = -(fthk + pt/2), a depth no
    # other part shares.
    w = 1200.0
    jw = 50.0
    pt = 45.0
    tol = jw / 10
    sfw = jw * 0.6
    half = w / 2
    slide = (w - jw - tol) - (half + tol)      # the sash's chord: 540
    glass_left = half + sfw - slide            # glass sheet, closed at 630
    glass_right = w - jw - sfw - slide         # closed at 1120, then slid
    glass_z = -((100.0 - pt) + pt / 2)         # -(fthk + pt/2) = -77.5

    spec = dict(shape="Rectangular", operation="Single sliding", width=w,
                height=1200.0, frameWidth=jw, sashThk=45.0, frameDepth=100.0,
                swingSide="Left", swingDir="Inward", panelPos="Front")
    sketch, wp = wg._makeWindowGeometry(spec)
    win = wo.makeWindow(sketch, w, 1200.0, wp, name="Win")
    win.Opening = 100
    doc.recompute()
    _close(win, glass_z, glass_left, glass_right,
           "sliding window glass travels exactly with its sash (inherits "
           "the sash's transform)")

    # The fixed half (Wire3) must not move: its glass spans jw+sfw ..
    # half-sfw regardless of the opening, at z = -pt/2.
    _close(win, -pt / 2, jw + sfw, half - sfw,
           "fixed window glass does not move")

    # --- Door: single sliding glass, defaults (w=900 h=2100 jw=70 -------
    # panel=45 frame=100, centred leaf, Mode10 slides toward -X). The leaf
    # frame (Wire2) spans jw+tol .. w-jw-tol and slides one chord (753 mm);
    # its glass (Wire3) spans jw+h2 .. w-jw-h2 and extrudes at
    # z = -(panelZ + pt/2), a depth no other part shares. ("+V" in an
    # offset field adds obj.Offset, which is 0, so the plane is fixed.)
    w2 = 900.0
    jw2 = 70.0
    h2 = jw2
    pt2 = 45.0
    tol2 = jw2 / 10
    slide2 = (w2 - jw2 - tol2) - jw2          # the leaf's chord: 753
    glass2_left = (jw2 + h2) - slide2         # glass sheet, closed at 140
    glass2_right = (w2 - jw2 - h2) - slide2   # closed at 760, then slid
    glass2_z = -((100.0 - pt2) / 2 + pt2 / 2)   # -(27.5 + 22.5) = -50.0

    dspec = dict(operation="Sliding (single)", panelStyle="Glass (full)",
                 width=w2, height=2100.0, frameWidth=jw2, panelThk=pt2,
                 frameDepth=100.0, swingSide="Left", swingDir="Inward",
                 panelPos="Centered")
    sketch, dwp = dg._makeDoorGeometry(dspec)
    door = do.makeWindow(sketch, w2, 2100.0, dwp, name="Door")
    door.Frame = pt2            # makeDoor does the same; drives "+V" offsets
    door.Opening = 100
    doc.recompute()
    _close(door, glass2_z, glass2_left, glass2_right,
           "sliding door glass travels exactly with its leaf (inherits "
           "the leaf frame's transform)")

    _reposition_checks(h.fresh_doc())
    _segment_rebuild_checks(h.fresh_doc())

    return h.failures()
