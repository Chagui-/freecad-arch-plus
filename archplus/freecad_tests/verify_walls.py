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


def _vp_name(obj):
    return getattr(getattr(getattr(obj, "ViewObject", None), "Proxy", None),
                   "__class__", None).__name__


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
    h.check("W5 split-created segment carries the wall view provider",
            _vp_name(new) == "_ViewProviderWall"
            and _vp_name(wall) == "_ViewProviderWall"
            and _vp_name(rest) == "_ViewProviderWall")
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
            and _vp_name(wall2) == "_ViewProviderWall"
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
    h.check("W14 factory-built wall and segment carry the wall view provider",
            _vp_name(wall) == "_ViewProviderWall"
            and _vp_name(seg) == "_ViewProviderWall")
    h.check("W14 view provider nests segments under the wall",
            wall.ViewObject.Proxy.claimChildren() == list(wall.Group)
            and seg.ViewObject.Proxy.claimChildren() == [])


def _w15_split_gate(doc):
    sk = _line_sketch(doc, [
        ((0, 0), (4000, 0), False),
        ((0, 3000), (4000, 3000), False),
    ])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    seg = wall.Group[0]
    from archplus.tools.walls import gui as walls_gui
    import FreeCADGui
    FreeCADGui.Selection.clearSelection()
    h.check("W15 split command inactive without a segment selection",
            not walls_gui.WallSplitCommand().IsActive())
    FreeCADGui.Selection.addSelection(seg)
    h.check("W15 split command active with a segment selected",
            walls_gui.WallSplitCommand().IsActive())
    FreeCADGui.Selection.clearSelection()
    FreeCADGui.Selection.addSelection(seg, "Face1")
    h.check("W15 split command active with a segment face selected",
            walls_gui.WallSplitCommand().IsActive())
    FreeCADGui.Selection.clearSelection()
    FreeCADGui.Selection.addSelection(wall)
    h.check("W15 split command active with the wall root selected",
            walls_gui.WallSplitCommand().IsActive())
    FreeCADGui.Selection.clearSelection()
    FreeCADGui.Selection.addSelection(seg, "Face1")
    h.check("W15 selection gate accepts a picked segment face",
            walls_gui.wall_segment_selected())
    FreeCADGui.Selection.clearSelection()
    FreeCADGui.Selection.addSelection(wall)
    h.check("W15 selection gate accepts the wall root (3D picks of claimed "
            "children select it)",
            walls_gui.wall_segment_selected())
    FreeCADGui.Selection.clearSelection()
    h.check("W15 selection gate rejects an empty selection",
            not walls_gui.wall_segment_selected())
    h.check("W15 view provider offers no tree context-menu entry "
            "(the split entry is 3D-only)",
            not hasattr(walls_object._ViewProviderWall, "setupContextMenu")
            and not hasattr(wall.ViewObject.Proxy, "setupContextMenu")
            and not hasattr(seg.ViewObject.Proxy, "setupContextMenu"))


def _w16_split_ux(doc):
    sk = _line_sketch(doc, [
        ((0, 0), (2000, 0), False),
        ((2000, 0), (4000, 0), False),
    ], name="SplitUX")
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    rest = wall.Group[0]
    import FreeCADGui
    from archplus.tools.walls import gui as walls_gui
    cmd = walls_gui.WallSplitCommand()

    FreeCADGui.Selection.clearSelection()
    FreeCADGui.Selection.addSelection(rest)
    captured = []
    orig = FreeCAD.Console.PrintWarning
    FreeCAD.Console.PrintWarning = captured.append
    try:
        cmd.Activated()
    finally:
        FreeCAD.Console.PrintWarning = orig
    h.check("W16 split without faces warns and creates nothing",
            any("Click one or more wall faces" in m for m in captured)
            and len(wall.Group) == 1
            and abs(rest.Shape.Volume
                    - _expected_volume(300, 2800, [2000, 2000])) < 1e-3)

    FreeCADGui.Selection.clearSelection()
    FreeCADGui.Selection.addSelection(rest, "Face1", 500.0, 0.0, 0.0)
    h.check("W16 split command active with a picked face", cmd.IsActive())
    cmd._chooseTarget = lambda sources: walls_gui.NEW_SEGMENT
    cmd.Activated()
    doc.recompute()
    new = [o for o in wall.Group if o is not rest]
    h.check("W16 picked-face split moves the picked run into a new sibling",
            len(new) == 1
            and abs(new[0].Shape.Volume
                    - _expected_volume(300, 2800, [2000])) < 1e-3
            and abs(rest.Shape.Volume
                    - _expected_volume(300, 2800, [2000])) < 1e-3)
    h.check("W16 split-created segment gets the wall view provider",
            _vp_name(new[0]) == "_ViewProviderWall")
    FreeCADGui.Selection.clearSelection()

    sk2 = _line_sketch(doc, [
        ((0, 0), (2000, 0), False),
        ((2000, 0), (4000, 0), False),
    ], name="SplitUX2")
    wall2 = walls_object.makeWall(doc, sketch=sk2)
    doc.recompute()
    a = walls_object.makeSegment(wall2, name="a")
    a.Edges = [(sk2, ("Edge1",))]
    a.Rest = False
    b = walls_object.makeSegment(wall2, name="b")
    b.Edges = [(sk2, ("Edge2",))]
    doc.recompute()
    rest2 = wall2.Group[0]
    h.check("W16 two explicit segments and a dormant rest child",
            abs(a.Shape.Volume - _expected_volume(300, 2800, [2000])) < 1e-3
            and abs(b.Shape.Volume - _expected_volume(300, 2800, [2000])) < 1e-3
            and rest2.Shape.Volume < 1e-3)
    options = cmd._targetOptions([(a, ("Edge1",))])
    h.check("W16 move targets list the other top-level segments only",
            b in options and rest2 in options and a not in options)
    FreeCADGui.Selection.clearSelection()
    FreeCADGui.Selection.addSelection(a, "Face1", 500.0, 0.0, 0.0)
    cmd._chooseTarget = lambda sources: b
    cmd.Activated()
    doc.recompute()
    h.check("W16 move to existing: source empties, target joins the runs",
            a.Shape.Volume < 1e-3
            and len(b.Shape.Solids) == 1
            and abs(b.Shape.Volume
                    - _expected_volume(300, 2800, [2000, 2000])) < 1e-3)
    FreeCADGui.Selection.clearSelection()

    sk3 = _line_sketch(doc, [
        ((0, 0), (2000, 0), False),
        ((2000, 0), (4000, 0), False),
    ], name="SplitUX3")
    wall3 = walls_object.makeWall(doc, sketch=sk3)
    doc.recompute()
    rest3 = wall3.Group[0]
    d = walls_object.makeSegment(wall3, name="d")
    d.Edges = [(sk3, ("Edge2",))]
    doc.recompute()
    FreeCADGui.Selection.clearSelection()
    FreeCADGui.Selection.addSelection(rest3, "Face1", 500.0, 0.0, 0.0)
    cmd._chooseTarget = lambda sources: d
    cmd.Activated()
    doc.recompute()
    h.check("W16 moving out of a rest source frees only the moved run",
            abs(d.Shape.Volume
                - _expected_volume(300, 2800, [2000, 2000])) < 1e-3
            and rest3.Shape.Volume < 1e-3
            and rest3.Rest)
    FreeCADGui.Selection.clearSelection()
    FreeCADGui.Selection.addSelection(b, "Face1", 2500.0, 0.0, 0.0)
    FreeCADGui.Selection.addSelection(d, "Face1", 500.0, 0.0, 0.0)
    captured = []
    orig = FreeCAD.Console.PrintWarning
    FreeCAD.Console.PrintWarning = captured.append
    try:
        cmd.Activated()
    finally:
        FreeCAD.Console.PrintWarning = orig
    h.check("W16 selection across walls aborts with a warning",
            any("several walls" in m for m in captured)
            and len(b.Shape.Solids) == 1
            and abs(b.Shape.Volume
                    - _expected_volume(300, 2800, [2000, 2000])) < 1e-3
            and abs(d.Shape.Volume
                    - _expected_volume(300, 2800, [2000, 2000])) < 1e-3)
    FreeCADGui.Selection.clearSelection()

    sk4 = _line_sketch(doc, [
        ((0, 0), (2000, 0), False),
        ((2000, 0), (4000, 0), False),
    ], name="SplitUX4")
    wall4 = walls_object.makeWall(doc, sketch=sk4)
    doc.recompute()
    a4 = walls_object.makeSegment(wall4, name="a4")
    a4.Edges = [(sk4, ("Edge1",))]
    a4.Rest = False
    b4 = walls_object.makeSegment(wall4, name="b4")
    b4.Edges = [(sk4, ("Edge2",))]
    doc.recompute()
    rest4 = wall4.Group[0]
    pnt = a4.Shape.getElement("Face1").CenterOfGravity
    FreeCADGui.Selection.clearSelection()
    FreeCADGui.Selection.addSelection(wall4, "Face1", pnt.x, pnt.y, pnt.z)
    h.check("W16 split command active with a picked root face", cmd.IsActive())
    cmd._chooseTarget = lambda sources: walls_gui.NEW_SEGMENT
    cmd.Activated()
    doc.recompute()
    new4 = [o for o in wall4.Group
            if o is not rest4 and o is not a4 and o is not b4]
    h.check("W16 root-face pick resolves to the owning segment and splits",
            len(new4) == 1
            and abs(new4[0].Shape.Volume
                    - _expected_volume(300, 2800, [2000])) < 1e-3
            and a4.Shape.Volume < 1e-3
            and abs(b4.Shape.Volume
                    - _expected_volume(300, 2800, [2000])) < 1e-3)
    FreeCADGui.Selection.clearSelection()

    sk5 = _line_sketch(doc, [
        ((0, 0), (2000, 0), False),
        ((2000, 0), (2000, 2000), False),
        ((2000, 2000), (0, 2000), False),
        ((0, 2000), (0, 0), False),
    ], name="SplitUX5")
    wall5 = walls_object.makeWall(doc, sketch=sk5)
    doc.recompute()
    a5 = walls_object.makeSegment(wall5, name="a5")
    a5.Edges = [(sk5, ("Edge1",))]
    a5.Rest = False
    b5 = walls_object.makeSegment(wall5, name="b5")
    b5.Edges = [(sk5, ("Edge2",))]
    b5.Rest = False
    doc.recompute()
    rest5 = wall5.Group[0]
    p_a = a5.Shape.getElement("Face1").CenterOfGravity
    p_b = b5.Shape.getElement("Face2").CenterOfGravity
    FreeCADGui.Selection.addSelection(wall5, "Face1", p_a.x, p_a.y, p_a.z)
    FreeCADGui.Selection.addSelection(wall5, "Face2", p_b.x, p_b.y, p_b.z)
    cmd._chooseTarget = lambda sources: walls_gui.NEW_SEGMENT
    cmd.Activated()
    doc.recompute()
    new5 = [o for o in wall5.Group
            if o is not rest5 and o is not a5 and o is not b5]
    h.check("W16 two root faces resolve to their own segments",
            len(new5) == 2
            and a5.Shape.Volume < 1e-3
            and b5.Shape.Volume < 1e-3
            and abs(sum(o.Shape.Volume for o in new5)
                    - 2 * _expected_volume(300, 2800, [2000])) < 1e-3)
    FreeCADGui.Selection.clearSelection()


def _w17_bim_context_menu(doc):
    sk = _line_sketch(doc, [((0, 0), (4000, 0), False)], name="CtxMenu")
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    seg = wall.Group[0]
    import FreeCADGui
    from archplus.tools.walls import gui as walls_gui
    h.check("W17 old workbench-manipulator hook is gone",
            not hasattr(FreeCADGui, "_ArchPlusWallsMenuHook"))
    wb = FreeCADGui.getWorkbench("BIMWorkbench")
    if not h.check("W17 BIM workbench exposes a callable ContextMenu handler",
                   wb is not None
                   and callable(getattr(wb, "ContextMenu", None))):
        return
    FreeCADGui.Selection.clearSelection()
    FreeCADGui.Selection.addSelection(seg, "Face1")
    h.check("W17 selection gate accepts a segment face",
            walls_gui.wall_segment_selected())
    if not hasattr(wb, "snapmenu"):
        wb.snapmenu = []

    def _run_handler():
        recorded = []
        orig_append = wb.appendContextMenu
        wb.appendContextMenu = lambda *args: recorded.append(args)
        threw = None
        try:
            wb.ContextMenu("View")
        except Exception as exc:
            threw = exc
        finally:
            wb.appendContextMenu = orig_append
        return threw, recorded

    threw_sel, recorded_sel = _run_handler()
    FreeCADGui.Selection.clearSelection()
    threw_empty, recorded_empty = _run_handler()
    if threw_sel is None and threw_empty is None:
        detail = "with segment face: %r; empty selection: %r" % (
            recorded_sel, recorded_empty)
    else:
        detail = "handler raised: %r" % (threw_sel or threw_empty,)
    h.check("W17 wrapped BIM handler appends the split command",
            threw_sel is None and threw_empty is None
            and ("", ["ArchPlus_WallSplit"]) in recorded_sel
            and ("", ["ArchPlus_WallSplit"]) in recorded_empty,
            detail)


def _segment_claims(seg):
    out = []
    for _link, subs in getattr(seg, "Edges", None) or []:
        out.extend(subs)
    return out


def _w18_segment_miter(doc):
    sk = _line_sketch(doc, [
        ((0, 0), (1000, 0), False),
        ((1000, 0), (1000, 1000), False),
        ((1000, 1000), (0, 1000), False),
        ((0, 1000), (0, 0), False),
    ])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    rest = wall.Group[0]
    walls_object.splitSegment(rest, ["Edge2"])
    doc.recompute()
    segs = walls_object.all_segments(wall)
    seg_new = [s for s in segs if _segment_claims(s) == ["Edge2"]][0]
    seg_rest = [s for s in segs if s is not seg_new][0]
    height = 2800.0
    h.check("W18 split corner builds valid solids",
            seg_new.Shape.isValid() and seg_rest.Shape.isValid())
    h.check("W18 split segment volume is exact",
            abs(seg_new.Shape.Volume - 300000.0 * height) < 1.0)
    h.check("W18 rest volume is exact",
            abs(seg_rest.Shape.Volume - 900000.0 * height) < 1.0)
    common = seg_new.Shape.common(seg_rest.Shape).Volume
    h.check("W18 corner seam leaves no overlap", common < 1e-6,
            detail="overlap volume %s" % common)
    empty = 0
    for gx in range(-4, 5):
        for gy in range(-4, 5):
            p = FreeCAD.Vector(1000 + gx * 25.0, gy * 25.0, height / 2.0)
            if not (seg_new.Shape.isInside(p, 1e-7, True)
                    or seg_rest.Shape.isInside(p, 1e-7, True)):
                empty += 1
    h.check("W18 corner region has no gap", empty == 0,
            detail="%d empty grid points" % empty)


def _w19_mixed_width_miter(doc):
    sk = _line_sketch(doc, [
        ((0, 0), (1000, 0), False),
        ((1000, 0), (1000, 1000), False),
        ((1000, 1000), (0, 1000), False),
        ((0, 1000), (0, 0), False),
    ])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    rest = wall.Group[0]
    walls_object.splitSegment(rest, ["Edge2"])
    doc.recompute()
    segs = walls_object.all_segments(wall)
    seg_new = [s for s in segs if _segment_claims(s) == ["Edge2"]][0]
    seg_rest = [s for s in segs if s is not seg_new][0]
    seg_new.Width = 200
    doc.recompute()
    height = 2800.0
    h.check("W19 narrowed segment volume is exact",
            abs(seg_new.Shape.Volume - 200000.0 * height) < 1.0)
    h.check("W19 rest area is invariant to the neighbor width",
            abs(seg_rest.Shape.Volume - 900000.0 * height) < 1.0)
    common = seg_new.Shape.common(seg_rest.Shape).Volume
    h.check("W19 mixed-width seam leaves no overlap", common < 1e-6,
            detail="overlap volume %s" % common)
    slant = (seg_new.Shape.isInside(FreeCAD.Vector(1060, -80, height / 2.0),
                                    1e-7, True)
             and seg_rest.Shape.isInside(FreeCAD.Vector(940, 80, height / 2.0),
                                         1e-7, True)
             and not seg_rest.Shape.isInside(
                 FreeCAD.Vector(1060, -80, height / 2.0), 1e-7, True)
             and not seg_new.Shape.isInside(
                 FreeCAD.Vector(940, 80, height / 2.0), 1e-7, True))
    h.check("W19 seam slant gives the wider segment the larger share",
            slant)
    seg_new.Width = 300
    doc.recompute()
    h.check("W19 width restore rebuilds both sides of the seam",
            abs(seg_new.Shape.Volume - 300000.0 * height) < 1.0
            and abs(seg_rest.Shape.Volume - 900000.0 * height) < 1.0)


def _w20_butt_fallbacks(doc):
    sk = _line_sketch(doc, [((0, 0), (1000, 0), False)])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    rest = wall.Group[0]
    h.check("W20 open sketch end builds a butt-ended band",
            rest.Shape.isValid()
            and abs(rest.Shape.Volume - 300000.0 * 2800.0) < 1.0)
    sk2 = _line_sketch(doc, [
        ((0, 0), (1000, 0), False),
        ((1000, 0), (1000, 1000), False),
        ((1000, 0), (2000, -500), False),
    ], name="TPlan")
    wall2 = walls_object.makeWall(doc, sketch=sk2)
    doc.recompute()
    rest2 = wall2.Group[0]
    walls_object.splitSegment(rest2, ["Edge2"])
    walls_object.splitSegment(rest2, ["Edge3"])
    doc.recompute()
    segs = walls_object.all_segments(wall2)
    expected = sorted([300.0 * 1000.0 * 2800.0,
                       300.0 * 1000.0 * 2800.0,
                       300.0 * 1118.0339878225 * 2800.0])
    got = sorted(s.Shape.Volume for s in segs)
    ok = (len(segs) == 3
          and all(s.Shape.isValid() for s in segs)
          and all(abs(g - e) < 2.0 for g, e in zip(got, expected)))
    h.check("W20 three segments at one vertex keep exact butt bands", ok,
            detail="volumes %s" % [round(s.Shape.Volume, 1) for s in segs])


def _w21_segment_panel_toggle(doc):
    sk = _line_sketch(doc, [((0, 0), (4000, 0), False)])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    from archplus.tools.walls import gui as walls_gui
    from archplus.common import widgets
    panel = walls_gui.WallSegmentTaskPanel(wall.Group[0])
    try:
        h.check("W21 width field starts disabled while inheriting",
                not panel.width.isEnabled())
        panel.overrideW.setChecked(True)
        h.check("W21 checking the override enables the field immediately",
                panel.width.isEnabled())
        h.check("W21 the field pre-fills with the inherited value",
                abs(widgets.mm(panel.width) - 300.0) < 1e-6)
        panel.overrideW.setChecked(False)
        h.check("W21 unchecking disables the field again",
                not panel.width.isEnabled())
    finally:
        panel.reject()


def _w22_edit_highlight(doc):
    sk = _line_sketch(doc, [((0, 0), (4000, 0), False)])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    seg = wall.Group[0]
    vobj = seg.ViewObject
    from pivy import coin
    vobj.Proxy.setEdit(vobj)
    try:
        named = [ch for ch in (vobj.RootNode.getChildren() or [])
                 if ch.getName() == "ArchPlusSegmentHighlight"]
        coords = [ch for ch in (named[0].getChildren() if named else [])
                  if isinstance(ch, coin.SoCoordinate3)]
        h.check("W22 editing a segment highlights its faces",
                len(named) == 1 and coords
                and coords[0].point.getNum() > 0)
        walls_object.effectiveValues(seg)
        seg.Width = 200
        doc.recompute()
        named2 = [ch for ch in (vobj.RootNode.getChildren() or [])
                  if ch.getName() == "ArchPlusSegmentHighlight"]
        h.check("W22 the highlight follows shape changes",
                len(named2) == 1
                and named2[0] is not None
                and [ch for ch in named2[0].getChildren()
                     if isinstance(ch, coin.SoCoordinate3)][0]
                .point.getNum() > 0)
        seg.Width = 300
        doc.recompute()
    finally:
        vobj.Proxy.unsetEdit(vobj)
    named3 = [ch for ch in (vobj.RootNode.getChildren() or [])
              if ch.getName() == "ArchPlusSegmentHighlight"]
    h.check("W22 closing the edit removes the highlight", len(named3) == 0)


def _w23_highlight_selection_lifecycle(doc):
    import FreeCADGui
    sk = _line_sketch(doc, [((0, 0), (4000, 0), False)])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    seg = wall.Group[0]
    vobj = seg.ViewObject
    from pivy import coin

    def highlights():
        return [ch for ch in (vobj.RootNode.getChildren() or [])
                if ch.getName() == walls_object.FACE_HIGHLIGHT]

    FreeCADGui.Selection.addSelection(seg)
    vobj.Proxy.setEdit(vobj)
    try:
        h.check("W23 the edited segment starts highlighted",
                len(highlights()) == 1)
        FreeCADGui.Selection.clearSelection()
        h.check("W23 deselecting the segment drops the edit highlight",
                len(highlights()) == 0)
        FreeCADGui.Selection.addSelection(seg)
        h.check("W23 reselecting the segment restores the highlight",
                len(highlights()) == 1)
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(wall)
        h.check("W23 selecting the wall counts as selecting the segment",
                len(highlights()) == 1)
        ok = walls_object.addFaceHighlight(
            seg.ViewObject, walls_object.PREVIEW_HIGHLIGHT,
            (0.95, 0.55, 0.10), 0.55)
        previewed = [ch for ch in (vobj.RootNode.getChildren() or [])
                     if ch.getName() == walls_object.PREVIEW_HIGHLIGHT]
        h.check("W23 the preview overlay coexists with the edit highlight",
                ok and len(previewed) == 1 and len(highlights()) == 1)
        walls_object.removeFaceHighlight(
            seg.ViewObject, walls_object.PREVIEW_HIGHLIGHT)
        previewed2 = [ch for ch in (vobj.RootNode.getChildren() or [])
                      if ch.getName() == walls_object.PREVIEW_HIGHLIGHT]
        h.check("W23 removing the preview leaves the edit highlight",
                len(previewed2) == 0 and len(highlights()) == 1)
    finally:
        FreeCADGui.Selection.clearSelection()
        vobj.Proxy.unsetEdit(vobj)
    h.check("W23 closing the edit removes the highlight", len(highlights()) == 0)
    FreeCADGui.Selection.clearSelection()
    FreeCADGui.Selection.addSelection(seg)
    h.check("W23 selection changes after close do not resurrect it",
            len(highlights()) == 0)
    FreeCADGui.Selection.clearSelection()


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
    _w15_split_gate(doc)
    _w16_split_ux(doc)
    _w17_bim_context_menu(doc)
    _w18_segment_miter(doc)
    _w19_mixed_width_miter(doc)
    _w20_butt_fallbacks(doc)
    _w21_segment_panel_toggle(doc)
    _w22_edit_highlight(doc)
    _w23_highlight_selection_lifecycle(doc)
    doc = h.fresh_doc()
    _w7_reload(doc)
