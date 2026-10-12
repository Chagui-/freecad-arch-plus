# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Sketch-building helpers shared by the ArchPlus geometry builders.
#
# Kept separate from archplus/common/widgets.py on purpose: this module pulls in
# Part and Sketcher, so it must only ever be imported from inside a function
# (never at gui.py module scope), or BIM workbench init would drag those in.

import Part
import Sketcher


def add_rect(sketch, p1, p2, p3, p4):
    """Add a fully-constrained rectangle to `sketch`."""
    idx = sketch.GeometryCount
    sketch.addGeometry(Part.LineSegment(p1, p2))
    sketch.addGeometry(Part.LineSegment(p2, p3))
    sketch.addGeometry(Part.LineSegment(p3, p4))
    sketch.addGeometry(Part.LineSegment(p4, p1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", idx, 2, idx + 1, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", idx + 1, 2, idx + 2, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", idx + 2, 2, idx + 3, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", idx + 3, 2, idx, 1))
    sketch.addConstraint(Sketcher.Constraint("Horizontal", idx))
    sketch.addConstraint(Sketcher.Constraint("Horizontal", idx + 2))
    sketch.addConstraint(Sketcher.Constraint("Vertical", idx + 1))
    sketch.addConstraint(Sketcher.Constraint("Vertical", idx + 3))


def add_frame(sketch, outer_p1, outer_p2, outer_p3, outer_p4,
              inner_p1, inner_p2, inner_p3, inner_p4):
    """Add outer+inner rectangles forming a frame."""
    add_rect(sketch, outer_p1, outer_p2, outer_p3, outer_p4)
    add_rect(sketch, inner_p1, inner_p2, inner_p3, inner_p4)


def plan_outline(shape, thickness=1.0):
    """The plan outline of `shape` as a prism over its own height, or None.

    The outline is what a section view may draw instead of the part's solid:
    the **filled outer boundary** of the shape's plan drawing. It is built by
    projecting the shape with the same hidden-line call Draft's Shape2DView
    uses, taking TechDraw's own outer-wire extractor over the result, and
    extruding that face - a solid, not a bare wire, because OnlySolids views
    and the section cut both drop non-solid geometry.

    The prism is extruded from the shape's own base over the shape's own
    height, and is never thinner than `thickness`. That is what lets a
    section view put it in the same compound as everything else: hidden-line
    removal works in depth, so an outline that carried no height - a 1 mm
    slab in the projection plane - would sit *under* whatever the part stands
    on, and the floor slab or wall band above it would delete the part from
    the drawing. An outline is an optimisation, never a wrong drawing.

    What it deliberately does not reproduce: loops nested inside the outer
    boundary - a smaller block on top of a bigger one, a table's top over its
    pedestal, a hole through a part. There the drawing is a filled footprint.
    Keeping those inner loops was measured to draw roughly three times the
    footprint (the bed: 48 edges against the footprint's 16), which gives
    back much of the saving this feature exists to make. docs/TOOLS.md says
    the same to the user.

    Returns None whenever the outline cannot be trusted: no geometry, no
    outer wire, a degenerate face, or a shape whose own drawing reaches
    *outside* the outer wire (a part with two separate outlines, like a
    waste bin with an overhanging lid). Callers then draw the solid, which
    is always right and merely slower.

    A view drawing this value draws its silhouette: the boundary comes from
    the projected edges themselves, which lie in the projection plane where
    Draft's own projected edges sit, and the prism's height only decides what
    hides it.
    """
    import TechDraw
    from FreeCAD import Vector

    if shape is None or shape.isNull() or not shape.Faces:
        return None
    try:
        groups = TechDraw.projectEx(shape, Vector(0, 0, 1))
    except Exception:
        return None
    drawn = [e for g in groups[0:5] if not g.isNull() for e in g.Edges]
    if not drawn:
        return None
    try:
        wire = TechDraw.findOuterWire(drawn)
    except Exception:
        return None
    if wire is None:
        return None
    try:
        face = Part.Face(wire)
    except Exception:
        return None
    if face.isNull() or face.Area <= 1.0:
        return None
    if not _covers(face, drawn):
        return None
    # Moved onto the shape's own z only after the check above: `drawn` is
    # flat, so a face already lifted to the shape's height could not be
    # compared with it any more.
    box = shape.BoundBox
    return face.translate(Vector(0, 0, box.ZMin)).extrude(
        Vector(0, 0, max(box.ZLength, thickness)))


def _covers(face, drawn, tolerance=0.5):
    """True when the shape's own drawing stays inside `face`.

    Containment, not equality: a loop nested inside the face is covered, and
    dropping it is the documented simplification (see plan_outline). What
    this rejects is a drawing that reaches *outside* the outline.
    """
    for edge in drawn:
        for vertex in edge.Vertexes:
            try:
                distance = Part.Vertex(vertex.Point).distToShape(face)[0]
            except Exception:
                return False
            if distance > tolerance:
                return False
    return True
