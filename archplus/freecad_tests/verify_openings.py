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

from archplus.tools.doors import gui as dg
from archplus.tools.doors import object as do
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

    return h.failures()
