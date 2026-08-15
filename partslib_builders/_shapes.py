# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Shared massing helpers for the furniture/sanitary builders.
#
# Every part in this library is built from Part primitives (boxes, cones,
# cylinders) plus boolean ops and fillets - never sculpted geometry. These
# helpers exist so that "rounded corner", "tapered leg", "softened cushion
# edge" and "oval basin" are each written once and reused across a dozen
# parts, rather than each builder hand-rolling its own edge-selection logic.
#
# No manifest ever names a symbol in this module directly: partslib_geometry
# only resolves "module.function" one level into partslib_builders, so a
# part.json can say "furniture.table" but never "_shapes.rounded_box". That
# is what keeps this a shared internal helper rather than a second builder
# surface to keep secure.
#
# Every fillet call is wrapped in a try/except that falls back to the
# unfilleted shape. There is no FreeCAD available in this development
# environment to exercise the OCC kernel against, so a fillet whose radius
# turns out too large for a given edge (or any other OCC edge case) must
# degrade to a sharp corner rather than abort the whole part's rebuild.

_TOL = 1e-4


def _vertical_edges(shape):
    """Edges running parallel to Z - the 4 corner edges of a box-like solid."""
    edges = []
    for edge in shape.Edges:
        verts = edge.Vertexes
        if len(verts) != 2:
            continue
        p1, p2 = verts[0].Point, verts[1].Point
        if (abs(p1.x - p2.x) < _TOL and abs(p1.y - p2.y) < _TOL
                and abs(p1.z - p2.z) > _TOL):
            edges.append(edge)
    return edges


def _edges_at_z(shape, z, tol=1e-3):
    """Every edge whose vertices all sit at height `z` - a horizontal loop."""
    edges = []
    for edge in shape.Edges:
        if all(abs(v.Point.z - z) < tol for v in edge.Vertexes):
            edges.append(edge)
    return edges


def safe_fillet(shape, radius, edges):
    """`shape.makeFillet(radius, edges)`, or `shape` unchanged on failure."""
    if not edges or radius is None or radius <= 0:
        return shape
    try:
        return shape.makeFillet(radius, edges)
    except Exception:
        return shape


def rounded_box(length, width, height, radius=0):
    """A box with its 4 vertical corner edges filleted.

    `radius` is clamped so a caller cannot request a fillet bigger than the
    box's own footprint - that is exactly the class of input that safe_fillet
    would otherwise have to fall back on."""
    import Part

    box = Part.makeBox(length, width, height)
    if radius <= 0:
        return box
    clamped = min(radius, length / 2.0 - 0.1, width / 2.0 - 0.1)
    return safe_fillet(box, clamped, _vertical_edges(box))


def soften_top(shape, radius, z=None):
    """Fillet the horizontal edge loop(s) at the shape's top (or given `z`).

    Run this on a shape that still has a simple top face loop (a box, or a
    box after a cut that opens at the same top height) - it is what turns a
    flat-topped slab into a cushion/rim/mattress-like profile."""
    if radius is None or radius <= 0:
        return shape
    top_z = shape.BoundBox.ZMax if z is None else z
    return safe_fillet(shape, radius, _edges_at_z(shape, top_z))


def tapered_leg(height, bottom_radius, top_radius):
    """A cone frustum standing on the floor (z=0 to z=height).

    Furniture legs read as turned/tapered rather than as plain cylinders
    whenever the two radii differ even slightly."""
    import Part

    return Part.makeCone(bottom_radius, top_radius, height)


def toe_kick(shape, width, depth, kick_height=15.0, kick_depth=40.0,
             margin=30.0):
    """Cut a shallow recess into the bottom-front of a cabinet carcass.

    This is the one detail that reads as "cabinet furniture" rather than "a
    box" on nearly every case good (nightstand, wardrobe, bookcase, vanity)
    without relying on a fillet: it is a single box subtraction, which is
    about as robust as an OCC boolean gets."""
    import Part
    import FreeCAD

    kick_width = width - 2.0 * margin
    if kick_width <= 0 or kick_height <= 0 or kick_depth <= 0:
        return shape
    notch = Part.makeBox(kick_width, kick_depth, kick_height)
    notch.translate(FreeCAD.Vector(margin, -1.0, -1.0))
    try:
        return shape.cut(notch)
    except Exception:
        return shape


def door_seam(shape, width, depth, height, seam_width=4.0, seam_depth=6.0,
              margin_top=0.08, margin_bottom=0.08):
    """Cut a thin vertical groove down the front centre - a suggested door
    split on a closed cabinet (wardrobe), without modelling actual doors."""
    import Part
    import FreeCAD

    top_margin = height * margin_top
    bottom_margin = height * margin_bottom
    groove_height = height - top_margin - bottom_margin
    seam_depth = min(seam_depth, depth)
    if groove_height <= 0 or seam_depth <= 0:
        return shape
    groove = Part.makeBox(seam_width, seam_depth, groove_height)
    groove.translate(FreeCAD.Vector(
        width / 2.0 - seam_width / 2.0, -1.0, bottom_margin))
    try:
        return shape.cut(groove)
    except Exception:
        return shape


def oval(shape, scale_x, scale_y):
    """Non-uniform XY scale - turns a circular cylinder/cone into an oval
    footprint, used for basin and toilet-bowl bodies."""
    import FreeCAD

    matrix = FreeCAD.Matrix()
    matrix.scale(scale_x, scale_y, 1.0)
    return shape.transformGeometry(matrix)


def vector(x, y, z):
    """A small convenience over FreeCAD.Vector, for callers translating a
    freshly-made Part shape in place (Part.Shape.translate, not place())."""
    import FreeCAD

    return FreeCAD.Vector(x, y, z)


def place(shape, x, y, z):
    """A translated copy of `shape` - never mutates the shape passed in."""
    import FreeCAD

    moved = shape.copy()
    moved.translate(FreeCAD.Vector(x, y, z))
    return moved


def fuse_all(shapes):
    """Fuse a list of shapes, cleaning up coincident faces where possible.

    `removeSplitter()` is itself wrapped: it is a cosmetic clean-up (fewer
    spurious edges from touching faces), never load-bearing, so a failure
    there must not lose the fused shape."""
    result = shapes[0]
    for extra in shapes[1:]:
        result = result.fuse(extra)
    try:
        return result.removeSplitter()
    except Exception:
        return result
