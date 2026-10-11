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
    """The plan outline of `shape` as a thin slab, or None.

    The outline is what a section view may draw instead of the part's solid:
    the **filled outer boundary** of the shape's plan drawing. It is built by
    projecting the shape with the same hidden-line call Draft's Shape2DView
    uses, taking TechDraw's own outer-wire extractor over the result, and
    extruding that face a hair - a slab, not a bare wire, because OnlySolids
    views and the section cut both drop non-solid geometry.

    What it deliberately does not reproduce: loops nested inside the outer
    boundary - a smaller block on top of a bigger one, a table's top over its
    pedestal, a hole through a part. There the drawing is a filled footprint.
    Reproducing every loop was measured *bigger* than the solid's own drawing
    (the bed: 48 edges against 16), which is the opposite of what this
    feature exists to do. docs/TOOLS.md says the same to the user.

    Returns None whenever the outline cannot be trusted: no geometry, no
    outer wire, a degenerate face, or a shape whose own drawing reaches
    *outside* the outer wire (a part with two separate outlines, like a
    waste bin with an overhanging lid). Callers then draw the solid, which
    is always right and merely slower.

    A view drawing this value draws its silhouette - the face it was
    extruded from, which sits in the projection plane (z = 0) where Draft's
    own projected edges sit.
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
    return face.extrude(Vector(0, 0, thickness))


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
