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


def plan_drawing(shape, clearance=1.0):
    """The plan drawing of `shape` as a cached substitute for its solid, or None.

    What a section view may draw instead of a placed library part's solid, and
    it draws what the solid draws: the part's own visible plan projection, from
    the same hidden-line call Draft's Shape2DView uses. Measured over the
    library (36 parts, edges a view then has to draw): the solids 985, this
    drawing 885, the filled footprint alone 448 - the footprint was what made
    furniture read as boxes, so a bed drew a rectangle instead of its mattress
    and pillows. What the substitution still saves is the part's `cut`, its
    place in the hidden-line pass, and the projection itself, all cached.

    Two pieces, because a view needs both:

    * a prism over the shape's plan boundary (TechDraw's own outer-wire
      extractor over the projection), from the shape's own base to
      `clearance` below its top. That volume is what keeps the view's
      hidden-line pass treating the substitute as the part: what hides the
      part hides it - a chair under a table stays hidden, substituted or not -
      and what the part hides stays hidden. The boundary is drawn by this
      prism, so its edges are left out of the flat ones below and the view
      draws it once; where the wire's own edges split a long boundary edge the
      substitute draws the pieces as well, on the same line - invisible in the
      drawing, and measured at 59 edges of 1001.
    * the shape's own visible plan edges, laid flat at the shape's own top:
      every feature the boundary alone would lose. Flat and `clearance` above
      the prism's top, so the prism cannot swallow them, and coplanar with each
      other, so none of them hides another.

    A prism no taller than `clearance` (a part thinner than the gap) gets no
    prism at all and draws every edge flat: the drawing is what matters, the
    volume only decides what hides it.

    Returns None when there is no drawing to cache: no geometry, a projection
    with no edges, or an outer wire that will not make a face. The caller then
    draws the solid, which draws the same thing and merely costs more.
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
    if face.isNull():
        return None
    box = shape.BoundBox
    pieces = []
    boundary = frozenset()
    if box.ZLength > clearance:
        try:
            pieces.append(face.extrude(Vector(0, 0, box.ZLength - clearance))
                          .translate(Vector(0, 0, box.ZMin)))
            boundary = frozenset(_edge_key(e) for e in wire.Edges)
        except Exception:
            # No prism: the whole drawing goes flat, so the part is drawn
            # exactly as its solid would be and only its occlusion is lost.
            pieces = []
    flat = [e for e in drawn if _edge_key(e) not in boundary]
    if flat:
        pieces.append(Part.makeCompound(flat).translate(Vector(0, 0, box.ZMax)))
    if not pieces:
        return None
    return Part.makeCompound(pieces)


def _edge_key(edge):
    """A projected edge as its two endpoints, so the boundary the prism already
    draws can be recognised in the edge pile and left out of the flat ones."""
    ends = []
    for vertex in (edge.Vertexes[0], edge.Vertexes[-1]):
        ends.append(tuple(round(c, 3) for c in vertex.Point))
    return tuple(sorted(ends))
