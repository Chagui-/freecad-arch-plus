# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Section-view checks. Run inside a FreeCAD GUI session.
#
# A section view draws library parts as their cached plan outline instead of
# their solid. The outline is an optimisation, never a wrong drawing: it is
# used only when it covers everything the solid's own drawing shows, and this
# module is where that claim is tested - on a real part, a part the cut passes
# through, a part rotated off-plan, and against Draft's own view, which must
# keep drawing the walls identically.

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

    FreeCAD.closeDocument(doc.Name)
    return h.failures()
