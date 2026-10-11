# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Section-view checks. Run inside a FreeCAD GUI session.
#
# A section view draws library parts as their cached plan outline instead of
# their solid. The outline is an optimisation, never a wrong drawing: it is
# the shape's filled outer boundary, used when the solid's own drawing stays
# inside it, and this module is where that claim is tested - on a real part, a
# part the cut passes through, a part rotated off-plan, and against Draft's
# own view, which must keep drawing the walls identically.

import FreeCAD
import Part

from archplus.common import geometry as common_geometry
from archplus.freecad_tests import _harness as h


def _a_part():
    """One placed library part with a real shape."""
    from archplus.tools.partslib import object as pobj

    doc = FreeCAD.ActiveDocument
    obj = doc.addObject("Part::FeaturePython", "OutlinePart")
    pobj._LibraryPart(obj)
    obj.Shape = Part.makeBox(600, 400, 700)
    return obj


def _visible_edges(shape, direction=None):
    """The edges Draft's getProjected keeps, as comparable tuples."""
    import TechDraw

    direction = direction or FreeCAD.Vector(0, 0, 1)
    groups = TechDraw.projectEx(shape, direction)
    out = []
    for group in groups[0:5]:
        if group.isNull():
            continue
        for edge in group.Edges:
            a, b = edge.Vertexes[0].Point, edge.Vertexes[-1].Point
            out.append(tuple(sorted(((round(a.x, 3), round(a.y, 3), round(a.z, 3)),
                                     (round(b.x, 3), round(b.y, 3), round(b.z, 3))))))
    return set(out)


def _walls_and_plane(doc):
    """A wall on a sketch, and a section plane through it - the smallest
    document whose section view has real geometry."""
    import Sketcher

    sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(0, 0, 0),
                                        FreeCAD.Vector(4000, 0, 0)), False)
    sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(4000, 0, 0),
                                        FreeCAD.Vector(4000, 3000, 0)), False)

    from archplus.tools.walls import object as wobj

    wall = wobj.makeWall(doc, sketch=sketch)
    plane = doc.addObject("App::FeaturePython", "Section")
    import ArchSectionPlane

    ArchSectionPlane._SectionPlane(plane)
    # The wall root has no shape of its own - its segments carry the geometry
    # - and Draft's gather does not descend into an ArchPlus wall root: the
    # root is not a Draft group, so `walls=True` does not make it one. A
    # section plane therefore has to reference the segments, which is what the
    # real documents do. Referencing the root alone leaves Draft's own view
    # raising IndexError on its empty material bucket, and this fixture would
    # compare two empty drawings.
    plane.Objects = list(wall.Group)
    plane.Placement.Base = FreeCAD.Vector(0, 0, 1200)
    doc.recompute()
    return wall, plane


def run():
    doc = h.fresh_doc("ArchPlusSections")
    part = _a_part()

    outline = common_geometry.plan_outline(part.Shape)
    h.check("a box gets an outline", outline is not None)
    h.check("the outline is a 1mm slab", outline is not None
            and abs(outline.BoundBox.ZLength - 1.0) < 1e-6
            and outline.Volume > 0)
    # Counted on the *drawing*, not the raw shapes: the slab's own edges are
    # three times its silhouette's (top loop, bottom loop, 1mm verticals), so
    # a raw count would say nothing about what a view has to draw.
    h.check("the outline draws no more edges than the solid",
            len(_visible_edges(outline)) <= len(_visible_edges(part.Shape)))

    # The outline is the filled outer boundary: a loop nested inside it (a
    # smaller block on top of a bigger one) is dropped on purpose, not
    # refused. Reproducing it was measured bigger than the solid's own
    # drawing, which is the thing this feature exists to shrink.
    nested = Part.makeCompound([Part.makeBox(600, 400, 300),
                                Part.makeBox(300, 200, 300,
                                             FreeCAD.Vector(150, 100, 300))])
    nested_outline = common_geometry.plan_outline(nested)
    h.check("a nested loop is dropped, not refused",
            nested_outline is not None
            and len(_visible_edges(nested_outline)) == 4)

    # A projection too small to be a usable outline is refused.
    h.check("a hairline projection gets no outline",
            common_geometry.plan_outline(Part.makeBox(0.5, 0.5, 10)) is None)

    # A shape with two separate outlines: the outer wire is one of them, so
    # the other reaches outside the outline and it must be refused.
    two = Part.makeCompound([Part.makeBox(400, 400, 300),
                             Part.makeBox(400, 400, 300,
                                          FreeCAD.Vector(2000, 0, 0))])
    h.check("a two-outline shape gets no outline",
            common_geometry.plan_outline(two) is None)

    # An empty shape is refused rather than raising.
    h.check("an empty shape gets no outline",
            common_geometry.plan_outline(Part.Shape()) is None)

    from archplus.tools.partslib import object as pobj

    proxy = part.Proxy
    first = proxy.planOutline(part)
    h.check("a placed part answers with an outline", first is not None)
    h.check("the outline is cached, not rebuilt",
            proxy.planOutline(part) is first)
    before = proxy._outline_key
    part.Shape = Part.makeBox(900, 400, 700)
    h.check("a rebuild drops the cache", proxy.planOutline(part) is not first)
    h.check("the new outline is cached too",
            proxy.planOutline(part) is proxy.planOutline(part))
    h.check("the key followed the rebuild", proxy._outline_key != before)

    empty = pobj._LibraryPart.__new__(pobj._LibraryPart)
    h.check("a part with no shape answers None",
            empty.planOutline(Part.Shape()) is None)

    wall, plane = _walls_and_plane(doc)

    # Draft's own view, as the reference behaviour.
    reference = doc.addObject("Part::Part2DObjectPython", "Reference")
    import Draft
    import draftobjects.shape2dview as s2v

    s2v.Shape2DView(reference)
    reference.Base = plane
    reference.FuseArch = True
    reference.ProjectionMode = "Solid"
    doc.recompute()

    from archplus.tools.sections import object as sobj

    view = sobj.makeSectionView(doc, base=plane)
    doc.recompute()

    h.check("the new view draws something", len(view.Shape.Edges) > 0)
    h.check("the new view draws exactly what Draft draws",
            _visible_edges(view.Shape) == _visible_edges(reference.Shape))
    h.check("the view keeps its own placement",
            view.Placement.Base == FreeCAD.Vector(0, 0, 0))

    # A plane with nothing to draw leaves an empty shape, not a stale one.
    import ArchSectionPlane

    empty = doc.addObject("App::FeaturePython", "EmptyPlane")
    ArchSectionPlane._SectionPlane(empty)
    bare = sobj.makeSectionView(doc, base=empty)
    doc.recompute()
    h.check("an empty plane draws nothing", bare.Shape.isNull()
            or len(bare.Shape.Edges) == 0)

    # No base at all must not raise into the recompute.
    nothing = sobj.makeSectionView(doc, base=None)
    doc.recompute()
    h.check("no base draws nothing", nothing.Shape.isNull()
            or len(nothing.Shape.Edges) == 0)

    FreeCAD.closeDocument(doc.Name)
    return h.failures()
