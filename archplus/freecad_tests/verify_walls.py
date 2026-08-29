# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Wall checks: creation, claims, config inheritance, split, sketch edits,
# hosted openings, reload. Mirrors the spec's verify list.

from archplus.freecad_tests import _harness as h

import FreeCAD
import Part

from archplus.tools.walls import object as walls_object


def _line_sketch(doc, lines, name="FloorPlan"):
    sk = doc.addObject("Sketcher::SketchObject", name)
    for (x1, y1), (x2, y2), construction in lines:
        sk.addGeometry(Part.LineSegment(FreeCAD.Vector(x1, y1, 0),
                                        FreeCAD.Vector(x2, y2, 0)),
                       construction)
    return sk


def _expected_volume(width, height, lengths):
    return width * height * sum(lengths)


def _w1_creation(doc):
    sk = _line_sketch(doc, [
        ((0, 0), (4000, 0), False),
        ((0, 3000), (4000, 3000), False),
        ((0, 6000), (4000, 6000), True),
    ])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    h.check("W1 root type and single child",
            wall.Proxy.Type == "Wall" and len(wall.Group) == 1)
    seg = wall.Group[0]
    h.check("W1 rest child defaults",
            seg.Proxy.Type == "WallSegment" and seg.Rest and seg.Wall is wall)
    h.check("W1 rest child builds 2 edges, construction excluded",
            abs(seg.Shape.Volume - _expected_volume(300, 2800, [4000, 4000])) < 1e-3)
    return wall, sk


def _w2_inheritance(doc):
    sk = _line_sketch(doc, [
        ((0, 0), (4000, 0), False),
        ((0, 3000), (4000, 3000), False),
    ])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    wall.Width = "400 mm"
    doc.recompute()
    rest = wall.Group[0]
    h.check("W2 root width change reaches the rest child",
            abs(rest.Shape.Volume - _expected_volume(400, 2800, [4000, 4000])) < 1e-3)
    ext = walls_object.makeSegment(wall, name="exterior")
    ext.Edges = [(sk, ("Edge2",))]
    doc.recompute()
    h.check("W2 explicit claim removed from rest",
            abs(rest.Shape.Volume - _expected_volume(400, 2800, [4000])) < 1e-3)
    h.check("W2 new sibling builds its claim",
            abs(ext.Shape.Volume - _expected_volume(400, 2800, [4000])) < 1e-3)
    short = walls_object.makeSegment(ext, name="short")
    short.Edges = [(sk, ("Edge1",))]
    short.Height = "2200 mm"
    doc.recompute()
    h.check("W2 nested child overrides height and inherits width",
            abs(short.Shape.Volume - _expected_volume(400, 2200, [4000])) < 1e-3)
    h.check("W2 ancestor excludes descendant claims (rest builds nothing)",
            rest.Shape.Volume < 1e-3)
    h.check("W2 sibling unaffected by nested child",
            abs(ext.Shape.Volume - _expected_volume(400, 2800, [4000])) < 1e-3)
    return wall, sk


def _w3_sketch_edits(doc):
    sk = _line_sketch(doc, [
        ((0, 0), (4000, 0), False),
        ((0, 3000), (4000, 3000), False),
    ])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    rest = wall.Group[0]
    sk.addGeometry(Part.LineSegment(FreeCAD.Vector(0, 6000, 0),
                                    FreeCAD.Vector(4000, 6000, 0)), False)
    doc.recompute()
    h.check("W3 new sketch edge lands in the rest child",
            abs(rest.Shape.Volume - _expected_volume(300, 2800, [4000] * 3)) < 1e-3)
    sk.delGeometry(2)
    doc.recompute()
    h.check("W3 deleted edge drops from the rest child",
            abs(rest.Shape.Volume - _expected_volume(300, 2800, [4000, 4000])) < 1e-3)
    sk.moveGeometry(0, 2, FreeCAD.Vector(5000, 0, 0))
    doc.recompute()
    h.check("W3 moved vertex: claim follows the edge",
            abs(rest.Shape.Volume - _expected_volume(300, 2800, [5000, 4000])) < 1e-3)
    return wall, sk


def _w4_panel(doc):
    sk = _line_sketch(doc, [((0, 0), (4000, 0), False)])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    from archplus.tools.walls import gui as walls_gui
    panel = walls_gui.WallPlusTaskPanel(wall)
    panel._loadFromObject()
    from archplus.common import widgets
    widgets.set_mm(panel.width, 450.0)
    panel.align.setCurrentText("Left")
    panel._apply()
    doc.recompute()
    h.check("W4 panel edits reach the wall and its child",
            abs(wall.Width.Value - 450.0) < 1e-9
            and wall.Align == "Left"
            and abs(wall.Group[0].Shape.Volume
                    - _expected_volume(450, 2800, [4000])) < 1e-3)
    panel.reject()


def _w5_split(doc):
    sk = _line_sketch(doc, [
        ((0, 0), (4000, 0), False),
        ((0, 3000), (4000, 3000), False),
    ])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    rest = wall.Group[0]
    walls_object.splitSegment(rest, ["Edge1"], name="exterior")
    doc.recompute()
    new = [o for o in wall.Group if o is not rest][0]
    h.check("W5 split moved the claim",
            abs(new.Shape.Volume - _expected_volume(300, 2800, [4000])) < 1e-3)
    h.check("W5 source keeps the remainder",
            abs(rest.Shape.Volume - _expected_volume(300, 2800, [4000])) < 1e-3)
    nested = walls_object.makeSegment(new, name="short")
    nested.Edges = [(sk, ("Edge2",))]
    nested.Height = "2200 mm"
    doc.recompute()
    h.check("W5 nesting after split inherits the group",
            abs(nested.Shape.Volume - _expected_volume(300, 2200, [4000])) < 1e-3
            and rest.Shape.Volume < 1e-3
            and abs(new.Shape.Volume - _expected_volume(300, 2800, [4000])) < 1e-3)
    wall.addObject(new)
    doc.recompute()
    h.check("W5 re-parenting preserves geometry",
            abs(nested.Shape.Volume - _expected_volume(300, 2200, [4000])) < 1e-3)
    from archplus.tools.walls import gui as walls_gui
    from archplus.tools.walls import model
    polys = walls_gui._claimedEdgePolylines(new)
    picked = model.match_edge([pts for _sub, pts in polys],
                              (2000.0, 0.0, 0.0), tol=5.0)
    h.check("W5 split helper matches a face pick to its edge",
            len(polys) == 1 and picked == 0 and polys[picked][0] == "Edge1")
    new.Width = "200 mm"
    doc.recompute()
    h.check("W5 nested child inherits the group width override",
            abs(nested.Shape.Volume - _expected_volume(200, 2200, [4000])) < 1e-3)
    new.removeObject(nested)
    wall.addObject(nested)
    h.check("W5 re-parenting marks the moved child for rebuild",
            "Touched" in nested.State)
    doc.recompute()
    h.check("W5 real re-parenting re-derives the inherited config",
            nested.Wall is wall
            and abs(nested.Shape.Volume - _expected_volume(300, 2200, [4000])) < 1e-3
            and abs(new.Shape.Volume - _expected_volume(200, 2800, [4000])) < 1e-3)
    return wall, sk


def _w6_hosting(doc):
    sk = _line_sketch(doc, [((0, 0), (4000, 0), False)])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    seg = wall.Group[0]
    full = seg.Shape.Volume

    from archplus.tools.windows import gui as wg
    from archplus.tools.windows import object as wo
    spec = dict(shape="Rectangular", operation="Fixed", width=1000,
                height=1000, frameWidth=50, sashThk=45, frameDepth=100,
                swingSide="Left", swingDir="Inward", panelPos="Front")
    wsk, wp = wg._makeWindowGeometry(spec)
    win = wo.makeWindow(wsk, 1000, 1000, wp, name="Win")
    wsk.Placement = FreeCAD.Placement(
        FreeCAD.Vector(1500, 0, 0),
        FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90))
    win.Hosts = [wall]
    wall.Subtractions = [win]
    doc.recompute()

    h.check("W6 hosted window cuts its segment",
            seg.Shape.Volume < full - 1000 * 300 * 1000 * 0.5)
    wsk.Placement = FreeCAD.Placement(
        FreeCAD.Vector(500, 0, 0),
        FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90))
    wg._recomputeWithHosts(win)
    h.check("W6 moved window re-cuts its segment",
            not seg.Shape.isInside(FreeCAD.Vector(1000, 0, 500), 1e-6, True)
            and seg.Shape.isInside(FreeCAD.Vector(2000, 0, 500), 1e-6, True))
    wall.Subtractions = []
    win.Hosts = []
    doc.recompute()
    h.check("W6 unhosting restores the segment",
            abs(seg.Shape.Volume - full) < 1e-3)

    sk2 = _line_sketch(doc, [
        ((0, 5000), (2000, 5000), False),
        ((2000, 5000), (4000, 5000), False),
    ], name="SplitRun")
    wall2 = walls_object.makeWall(doc, sketch=sk2, name="Wall2")
    doc.recompute()
    a, b = wall2.Group[0], walls_object.makeSegment(wall2, name="b")
    a.Edges = [(sk2, ("Edge1",))]
    a.Rest = False
    b.Edges = [(sk2, ("Edge2",))]
    doc.recompute()
    fa, fb = a.Shape.Volume, b.Shape.Volume
    wsk2, wp2 = wg._makeWindowGeometry(spec)
    win2 = wo.makeWindow(wsk2, 1000, 1000, wp2, name="Win2")
    wsk2.Placement = FreeCAD.Placement(
        FreeCAD.Vector(1500, 5000, 0),
        FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90))
    win2.Hosts = [wall2]
    wall2.Subtractions = [win2]
    doc.recompute()
    h.check("W6 spanning window cuts both collinear segments",
            a.Shape.Volume < fa - 100 and b.Shape.Volume < fb - 100)
    gb = b.Shape.Volume
    wsk3, wp3 = wg._makeWindowGeometry(spec)
    win3 = wo.makeWindow(wsk3, 1000, 1000, wp3, name="Win3")
    wsk3.Placement = FreeCAD.Placement(
        FreeCAD.Vector(3500, 5000, 0),
        FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90))
    win3.Hosts = [wall2]
    doc.recompute()
    h.check("W6 Hosts-only window cuts its segment",
            b.Shape.Volume < gb)
    return wall, sk


def _w7_reload(doc):
    sk = _line_sketch(doc, [
        ((0, 0), (4000, 0), False),
        ((0, 3000), (4000, 3000), False),
    ])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    walls_object.splitSegment(wall.Group[0], ["Edge1"], name="exterior")
    doc.recompute()
    from archplus.tools.walls import gui as walls_gui
    walls_gui._ensureVP(wall)
    for seg in wall.Group:
        walls_gui._ensureVP(seg)
    import os
    import tempfile
    path = os.path.join(tempfile.gettempdir(), "archplus_walls_reload.FCStd")
    if os.path.exists(path):
        os.remove(path)
    doc.saveAs(path)
    FreeCAD.closeDocument(doc.Name)
    doc2 = FreeCAD.openDocument(path)
    doc2.recompute()
    wall2 = doc2.getObject("Wall")
    ok = wall2 is not None and len(wall2.Group) == 2
    for seg in (wall2.Group if ok else []):
        ok = ok and abs(seg.Shape.Volume - _expected_volume(300, 2800, [4000])) < 1e-3
        ok = ok and seg.Proxy.Type == "WallSegment" and seg.Wall is wall2
    h.check("W7 reload preserves tree, claims and inheritance", ok)
    h.check("W7 restored view provider nests the segments",
            wall2 is not None
            and wall2.ViewObject.Proxy.claimChildren() == list(wall2.Group))
    FreeCAD.closeDocument(doc2.Name)


def _w8_placed_sketch(doc):
    sk = _line_sketch(doc, [
        ((0, 0), (4000, 0), False),
        ((0, 3000), (4000, 3000), False),
    ])
    sk.Placement = FreeCAD.Placement(FreeCAD.Vector(0, 0, 2800),
                                     FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90))
    doc.recompute()
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    seg = wall.Group[0]
    bb = seg.Shape.BoundBox
    h.check("W8 placed sketch: volume and placement match the sketch",
            abs(seg.Shape.Volume - _expected_volume(300, 2800, [4000, 4000])) < 1e-3
            and abs(bb.XMin) < 1.0 and abs(bb.XMax - 4000) < 1.0
            and abs(bb.YMin + 2800) < 1.0 and abs(bb.YMax) < 1.0
            and abs(bb.ZMin - 2650) < 1.0 and abs(bb.ZMax - 5950) < 1.0,
            "bbox %s" % bb)


def _w9_align_offset(doc):
    sk = _line_sketch(doc, [((0, 0), (4000, 0), False)])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    seg = wall.Group[0]
    wall.Align = "Left"
    wall.Offset = "100 mm"
    doc.recompute()
    bb = seg.Shape.BoundBox
    h.check("W9 Left builds left of travel with offset",
            abs(seg.Shape.Volume - _expected_volume(300, 2800, [4000])) < 1e-3
            and abs(bb.YMin - 100) < 1.0 and abs(bb.YMax - 400) < 1.0,
            "bbox %s" % bb)
    wall.Align = "Right"
    doc.recompute()
    bb = seg.Shape.BoundBox
    h.check("W9 Right builds right of travel with offset",
            abs(seg.Shape.Volume - _expected_volume(300, 2800, [4000])) < 1e-3
            and abs(bb.YMin + 400) < 1.0 and abs(bb.YMax + 100) < 1.0,
            "bbox %s" % bb)
    rev = _line_sketch(doc, [((4000, 0), (0, 0), False)], name="RevPlan")
    wall2 = walls_object.makeWall(doc, sketch=rev, name="Wall2")
    wall2.Align = "Left"
    doc.recompute()
    bb = wall2.Group[0].Shape.BoundBox
    h.check("W9 Left follows the edge travel direction",
            abs(bb.YMin + 300) < 1.0 and abs(bb.YMax) < 1.0,
            "bbox %s" % bb)


def _w10_arc(doc):
    import math
    sk = doc.addObject("Sketcher::SketchObject", "ArcPlan")
    sk.addGeometry(Part.ArcOfCircle(
        Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 2000),
        0.0, math.pi / 2), False)
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    seg = wall.Group[0]
    area = (math.pi / 2) / 2.0 * (2150.0 ** 2 - 1850.0 ** 2)
    expected = area * 2800.0
    h.check("W10 arc wall matches the annular-sector volume",
            abs(seg.Shape.Volume - expected) < 1e-6 * expected,
            "volume %.3f vs expected %.3f" % (seg.Shape.Volume, expected))


def _w11_delete_segment(doc):
    sk = _line_sketch(doc, [
        ((0, 0), (4000, 0), False),
        ((0, 3000), (4000, 3000), False),
    ])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    rest = wall.Group[0]
    ext = walls_object.makeSegment(wall, name="exterior")
    ext.Edges = [(sk, ("Edge2",))]
    doc.recompute()
    h.check("W11 explicit sibling and rest child each build one edge",
            len(wall.Group) == 2
            and abs(ext.Shape.Volume - _expected_volume(300, 2800, [4000])) < 1e-3
            and abs(rest.Shape.Volume - _expected_volume(300, 2800, [4000])) < 1e-3)
    doc.removeObject(ext.Name)
    doc.recompute()
    h.check("W11 deleting a segment frees its edge for the rest child",
            len(wall.Group) == 1
            and abs(rest.Shape.Volume
                    - _expected_volume(300, 2800, [4000, 4000])) < 1e-3)


def _w12_closed_corner(doc):
    L, W, H = 4000.0, 300.0, 2800.0
    sk = _line_sketch(doc, [
        ((-2000, -2000), (2000, -2000), False),
        ((2000, -2000), (2000, 2000), False),
        ((2000, 2000), (-2000, 2000), False),
        ((-2000, 2000), (-2000, -2000), False),
    ])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    seg = wall.Group[0]
    expected = ((L + W) ** 2 - (L - W) ** 2) * H
    bb = seg.Shape.BoundBox
    h.check("W12 closed square: one mitered ring solid",
            len(seg.Shape.Solids) == 1
            and abs(seg.Shape.Volume - expected) < 1e-6 * expected,
            "volume %.3f expected %.3f solids %d"
            % (seg.Shape.Volume, expected, len(seg.Shape.Solids)))
    h.check("W12 closed square: bbox (L+W) per side, centered on sketch",
            abs(bb.XMin + (L + W) / 2) < 1e-3
            and abs(bb.XMax - (L + W) / 2) < 1e-3
            and abs(bb.YMin + (L + W) / 2) < 1e-3
            and abs(bb.YMax - (L + W) / 2) < 1e-3,
            "bbox %s" % bb)


def _w13_closed_align(doc):
    L, W, H = 4000.0, 300.0, 2800.0
    sk = _line_sketch(doc, [
        ((-2000, -2000), (-2000, 2000), False),
        ((-2000, 2000), (2000, 2000), False),
        ((2000, 2000), (2000, -2000), False),
        ((2000, -2000), (-2000, -2000), False),
    ])
    wall = walls_object.makeWall(doc, sketch=sk)
    wall.Align = "Left"
    doc.recompute()
    seg = wall.Group[0]
    expected = ((L + 2 * W) ** 2 - L ** 2) * H
    bb = seg.Shape.BoundBox
    h.check("W13 closed square Left: outward ring, no gaps",
            len(seg.Shape.Solids) == 1
            and abs(seg.Shape.Volume - expected) < 1e-6 * expected
            and abs(bb.XMin + (L + 2 * W) / 2) < 1e-3
            and abs(bb.XMax - (L + 2 * W) / 2) < 1e-3
            and abs(bb.YMin + (L + 2 * W) / 2) < 1e-3
            and abs(bb.YMax - (L + 2 * W) / 2) < 1e-3,
            "volume %.3f expected %.3f bbox %s"
            % (seg.Shape.Volume, expected, bb))


def _w14_view_provider(doc):
    sk = _line_sketch(doc, [((0, 0), (4000, 0), False)])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    seg = wall.Group[0]
    from archplus.tools.walls import gui as walls_gui
    walls_gui._ensureVP(wall)
    walls_gui._ensureVP(seg)
    h.check("W14 view provider nests segments under the wall",
            wall.ViewObject.Proxy.claimChildren() == list(wall.Group)
            and seg.ViewObject.Proxy.claimChildren() == [])


def _w15_split_context_menu(doc):
    sk = _line_sketch(doc, [
        ((0, 0), (4000, 0), False),
        ((0, 3000), (4000, 3000), False),
    ])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    seg = wall.Group[0]
    from archplus.tools.walls import gui as walls_gui
    from PySide import QtGui
    import FreeCADGui
    walls_gui._ensureVP(wall)
    walls_gui._ensureVP(seg)
    FreeCADGui.Selection.clearSelection()
    h.check("W15 split command inactive without a segment selection",
            not walls_gui.WallSplitCommand().IsActive())
    FreeCADGui.Selection.addSelection(seg)
    h.check("W15 split command active with a segment selected",
            walls_gui.WallSplitCommand().IsActive())
    FreeCADGui.Selection.clearSelection()
    FreeCADGui.Selection.addSelection(wall)
    h.check("W15 split command active with the wall root selected",
            walls_gui.WallSplitCommand().IsActive())
    FreeCADGui.Selection.clearSelection()
    seg_menu = QtGui.QMenu()
    seg.ViewObject.Proxy.setupContextMenu(seg.ViewObject, seg_menu)
    root_menu = QtGui.QMenu()
    wall.ViewObject.Proxy.setupContextMenu(wall.ViewObject, root_menu)
    h.check("W15 context menu offers Split segment on segments only",
            any(a.text() == "Split segment" for a in seg_menu.actions())
            and not any(a.text() == "Split segment"
                        for a in root_menu.actions()))


def run():
    doc = h.fresh_doc()
    _w1_creation(doc)
    _w2_inheritance(doc)
    _w3_sketch_edits(doc)
    _w4_panel(doc)
    _w5_split(doc)
    _w6_hosting(doc)
    _w8_placed_sketch(doc)
    _w9_align_offset(doc)
    _w10_arc(doc)
    _w11_delete_segment(doc)
    _w12_closed_corner(doc)
    _w13_closed_align(doc)
    _w14_view_provider(doc)
    _w15_split_context_menu(doc)
    doc = h.fresh_doc()
    _w7_reload(doc)
