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


def run():
    doc = h.fresh_doc()
    _w1_creation(doc)
    _w2_inheritance(doc)
    _w3_sketch_edits(doc)
