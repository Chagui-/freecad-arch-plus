# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Shared massing helpers for the library's part builders.
#
# Every part in this library is built from Part primitives (boxes, cones,
# cylinders) plus boolean ops and eased edges - never sculpted geometry.
# These helpers exist so that "rounded corner", "tapered leg", "softened
# cushion edge" and "oval basin" are each written once and reused across a
# dozen parts, rather than each builder hand-rolling its own edge-selection
# logic.
#
# No manifest ever names a symbol in this module, or any other: a part's
# geometry comes from a builder.py in its own folder, and a part with no
# builder.py is asset-only. This module is imported directly by whichever
# builder.py wants it (`from archplus.tools.partslib import shapes as sh`);
# it is never itself resolved through a manifest, which is what keeps it a
# shared internal helper rather than a second builder surface to keep
# secure.
#
# Eased edges are chamfered, not filleted (see soften_edges), and every
# easing is wrapped so a size the kernel cannot use - too large for the
# edge, an edge that is not there any more - degrades to a fillet, then to a
# sharp corner, rather than aborting the whole part's rebuild.

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


# A chamfer of size s removes s^2/2 of the corner per unit length, a fillet
# of radius r removes r^2*(1 - pi/4) = 0.215r^2; 0.66r is the size that takes
# the same material off, 0.59r the one whose bevel line sits as far from the
# corner point (d/sqrt(2) vs r*(sqrt(2)-1)). 0.6 sits between them, so the
# chamfer that replaces a fillet reads the same and leaves the part's mass
# and bounding box alone.
_CHAMFER_FOR_RADIUS = 0.6


def soften_edges(shape, radius, edges):
    """Ease `edges` of `shape`, or return `shape` unchanged on failure.

    A chamfer, not a fillet. The eased edges of a library part are
    decorative - a few millimetres at drawing scale - but a fillet turns
    each into a cylindrical, toroidal or spherical face, and those cost far
    more than the part itself downstream: FreeCAD's section pipeline
    (silhouette projection plus an optimal bounding box per shape) measured
    ~7x slower on filleted parts than on the same parts chamfered, and the
    chamfer booleans are cheaper to build as well (a king bed: 375ms
    filleted, 200ms chamfered).

    The fallbacks matter more than the chamfer: a shape whose corners the
    chamfer cannot join degrades to a fillet, then to its unsoftened self,
    so no builder loses its shape to a softening it did not need."""
    if not edges or radius is None or radius <= 0:
        return shape
    try:
        return shape.makeChamfer(radius * _CHAMFER_FOR_RADIUS, edges)
    except Exception:
        pass
    try:
        return shape.makeFillet(radius, edges)
    except Exception:
        return shape


def rounded_box(length, width, height, radius=0):
    """A box with its 4 vertical corner edges eased.

    `radius` is clamped so a caller cannot request an ease bigger than the
    box's own footprint - that is exactly the class of input that
    soften_edges would otherwise have to fall back on."""
    import Part

    box = Part.makeBox(length, width, height)
    if radius <= 0:
        return box
    clamped = min(radius, length / 2.0 - 0.1, width / 2.0 - 0.1)
    return soften_edges(box, clamped, _vertical_edges(box))


def soften_top(shape, radius, z=None):
    """Ease the horizontal edge loop(s) at the shape's top (or given `z`).

    Run this on a shape that still has a simple top face loop (a box, or a
    box after a cut that opens at the same top height) - it is what turns a
    flat-topped slab into a cushion/rim/mattress-like profile."""
    if radius is None or radius <= 0:
        return shape
    top_z = shape.BoundBox.ZMax if z is None else z
    return soften_edges(shape, radius, _edges_at_z(shape, top_z))


def square_leg(height, size, chamfer=None):
    """A square-section leg standing on the floor, corners eased.

    Square legs read better than turned ones at thumbnail size and in a
    plan drawing: a thin cylinder renders as a wire, while a square post of
    the same nominal size keeps a visible face and a shadowed face. The
    small chamfer stops it looking like raw stock."""
    if chamfer is None:
        chamfer = min(size * 0.12, 6.0)
    return rounded_box(size, size, height, radius=chamfer)


def _edges_along(shape, axis, z, tol=1e-3):
    """Horizontal edges at height `z` running parallel to 'x' or 'y'."""
    edges = []
    for edge in shape.Edges:
        verts = edge.Vertexes
        if len(verts) != 2:
            continue
        p1, p2 = verts[0].Point, verts[1].Point
        if abs(p1.z - z) > tol or abs(p2.z - z) > tol:
            continue
        dx, dy = abs(p1.x - p2.x), abs(p1.y - p2.y)
        if axis == "x" and dx > tol and dy < tol:
            edges.append(edge)
        elif axis == "y" and dy > tol and dx < tol:
            edges.append(edge)
    return edges


def roll_top(shape, radius, axis="y", z=None):
    """Fillet only the top edges running along ONE axis - a rolled arm or a
    bullnose, continuous from one end of the shape to the other.

    Use this instead of soften_top() wherever the rounding is meant to
    read as a roll. soften_top() takes the whole top loop, so on a box it
    rounds all four top edges at once; if that box ALSO has filleted
    vertical corners, the four roundings collide at the corners and the
    blend visibly stops short, leaving a raised border round the top face
    like a picture frame. That is what made the sofa's arms look wrong.

    Rule of thumb, learned the same way: do not round a solid's plan
    corners AND its top edge. Pick whichever one the eye is meant to read
    - for an arm or a seat front, it is the roll."""
    top_z = shape.BoundBox.ZMax if z is None else z
    return soften_edges(shape, radius, _edges_along(shape, axis, top_z))


def tapered_leg(height, bottom_radius, top_radius):
    """A cone frustum standing on the floor (z=0 to z=height).

    Furniture legs read as turned/tapered rather than as plain cylinders
    whenever the two radii differ even slightly."""
    import Part

    return Part.makeCone(bottom_radius, top_radius, height)


def cut_box(shape, x, y, z, length, width, height):
    """Subtract an axis-aligned box at (x, y, z). `shape` on failure.

    The workhorse behind every recess, reveal and groove below: one box
    subtraction is about as robust as an OCC boolean gets, so details that
    could have been fillets or sweeps are cut instead wherever the result
    reads the same."""
    import Part

    if length <= 0 or width <= 0 or height <= 0:
        return shape
    notch = Part.makeBox(length, width, height)
    notch.translate(vector(x, y, z))
    try:
        return shape.cut(notch)
    except Exception:
        return shape


def cut_boxes(shape, boxes):
    """Subtract several axis-aligned boxes in ONE boolean.

    `boxes` is an iterable of (x, y, z, length, width, height).

    Cutting N boxes one at a time costs N booleans against a solid whose
    face count grows with every one of them. Cutting a single compound of
    all N costs one, and OCC is happy to take a compound as the tool. A
    drawer chest went from 20 cuts to 1 this way, which was most of the
    second-plus it took to build.

    Falls back to cutting one at a time if the compound cut is refused, so
    a kernel that dislikes a particular compound degrades to the old cost
    rather than to a missing part."""
    import Part

    tools = []
    for x, y, z, length, width, height in boxes:
        if length <= 0 or width <= 0 or height <= 0:
            continue
        box = Part.makeBox(length, width, height)
        box.translate(vector(x, y, z))
        tools.append(box)
    if not tools:
        return shape
    try:
        return shape.cut(Part.makeCompound(tools))
    except Exception:
        result = shape
        for tool in tools:
            try:
                result = result.cut(tool)
            except Exception:
                pass
        return result


def cushion(length, width, height, radius=None, edge=None):
    """A rounded box softened along BOTH its top and bottom edge loops.

    A seat or back cushion is pillowed on every side, not just the top -
    softening only the top leaves it reading as a slab with a rounded lip."""
    if radius is None:
        radius = min(length, width) * 0.12
    if edge is None:
        edge = min(height * 0.35, radius * 0.8)
    box = rounded_box(length, width, height, radius=radius)
    box = soften_top(box, edge)
    return soften_top(box, edge, z=0)


def bar(length, radius, along="x"):
    """A cylinder lying along an axis, starting at the origin.

    Used for handles and stretchers, where a thin round rod reads as
    hardware or joinery and a thin box just reads as another block."""
    import Part

    axis = {"x": vector(1, 0, 0),
            "y": vector(0, 1, 0)}.get(along, vector(0, 0, 1))
    return Part.makeCylinder(radius, length, vector(0, 0, 0), axis)


def panel_reveal_boxes(x, z, panel_width, panel_height, groove=6.0,
                       depth=8.0, face_depth=0.0):
    """The four groove boxes that outline one door or drawer front.

    Returned rather than cut, so a caller with several fronts to mark can
    gather every panel's boxes and subtract the lot in a single boolean -
    see cut_boxes(). A chest of drawers has five fronts, which is twenty
    boxes, which is one cut instead of twenty."""
    if panel_width <= 2 * groove or panel_height <= 2 * groove:
        return []
    y = face_depth - 1.0
    thickness = depth + 1.0
    return [
        # Left and right stiles, then top and bottom rails.
        (x, y, z, groove, thickness, panel_height),
        (x + panel_width - groove, y, z, groove, thickness, panel_height),
        (x, y, z, panel_width, thickness, groove),
        (x, y, z + panel_height - groove, panel_width, thickness, groove),
    ]


def panel_reveal(shape, x, z, panel_width, panel_height, groove=6.0,
                 depth=8.0, face_depth=0.0):
    """Cut a rectangular groove outline into a cabinet's front (-Y) face.

    An outline, not a recessed pocket: the four thin grooves alone are what
    make a flat slab read as a framed door or drawer front, without a
    pocket's larger cut through the middle of the carcass.

    Convenience wrapper for a caller with exactly one panel. Anything
    marking several should collect panel_reveal_boxes() and cut once."""
    return cut_boxes(shape, panel_reveal_boxes(
        x, z, panel_width, panel_height, groove, depth, face_depth))


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


def rotate(shape, axis, degrees, center=(0.0, 0.0, 0.0)):
    """A rotated COPY of `shape` - never mutates the shape passed in."""
    moved = shape.copy()
    moved.rotate(vector(*center), vector(*axis), degrees)
    return moved


def tube_elbow(tube_radius, bend_radius, angle=90.0):
    """A bend of round tube, lying in the XY plane, centred on the origin.

    The centreline is an arc of `bend_radius` running from
    (bend_radius, 0, 0) - where it heads +Y - round to (0, bend_radius, 0).
    Callers rotate() and place() it into position.

    This exists so a hook can actually BEND. Butting two cylinders at a
    right angle reads as two pipes that happen to touch, with a hard mitre
    line where a bent rod has a smooth curve - which is exactly the
    difference between something that looks like hardware and something
    that looks like a diagram of hardware.

    A torus segment is the cheapest true bend available: one primitive, no
    sweep along a wire, and no boolean. Returns None if the kernel refuses,
    so callers can fall back to a straight tube rather than lose the part."""
    import Part

    try:
        return Part.makeTorus(bend_radius, tube_radius, vector(0, 0, 0),
                              vector(0, 0, 1), -180.0, 180.0, angle)
    except Exception:
        return None


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


# The epsilon the role map is read with: a point this far inside a face is
# unambiguously in the piece that owns it, and far smaller than any face the
# library builds - the smallest features here are millimetre chamfers.
_ROLE_EPSILON = 0.05


def fuse_all(groups, ctx=None):
    """Fuse pieces grouped by role, and say which face came from which piece.

    `groups` is {role: [shape, ...]} - the roles a part is made of, and each
    role's pieces. Grouping them reorders the fuse, since a role's pieces are
    fused together: that cannot change the solid (a union is a union) but it
    can change how the result's faces are subdivided, and removeSplitter()
    below normalises most of that back. Volume, bounding box and solid count
    are identical either way, which is what the parts' own verification
    compares - a face count that moves is a subdivision, not a shape.

    The roles come back on `ctx` (geometry._Context) as one role per face of
    the result, which is what the view provider paints (see palette.py).
    They cannot be read off the fused shape afterwards, because the pieces
    are gone by then - and a fused face's own surface is not a reliable
    substitute either, since removeSplitter() refits the coplanar faces it
    merges, and a refit surface matches no piece at all. So the map is made
    here, while the pieces still exist, by looking just inside each face.

    A part that is one shape (nothing to fuse) is returned untouched rather
    than run through removeSplitter, so a builder with no pieces to group
    keeps the shape it built byte for byte."""
    from archplus.tools.partslib.palette import colour_for

    pieces = []
    for role, shapes in groups.items():
        colour_for(role)        # a typo'd role is a build error, not a colour
        for shape in shapes:
            pieces.append((role, shape))
    if not pieces:
        raise ValueError("fuse_all() was given no pieces")

    if len(pieces) == 1:
        result = pieces[0][1]
    else:
        result = pieces[0][1]
        for _role, extra in pieces[1:]:
            result = result.fuse(extra)
        try:
            result = result.removeSplitter()
        except Exception:
            pass

    if ctx is not None:
        ctx.roles = _face_roles(result, pieces)
    return result


def _face_roles(shape, pieces):
    """One role per face of `shape`, read from the pieces it was fused from.

    Pieces are tried smallest first: where two of them meet - a handle on a
    door, a cushion pressed into a frame - the smaller is the detail that
    face belongs to, and the common case is then found in a try or two."""
    order = sorted(range(len(pieces)), key=lambda i: pieces[i][1].Volume)
    return [_face_role(face, pieces, order) for face in shape.Faces]


def _face_role(face, pieces, order):
    """The role of the piece that owns one face of a fused shape."""
    import Part

    for point, normal in _face_probes(face):
        # Just inside the face is in the piece whose surface this is, and not
        # in a piece the face merely touches - which is what makes this work
        # where comparing surfaces does not.
        for epsilon in (_ROLE_EPSILON, _ROLE_EPSILON / 10.0):
            inside = point - normal * epsilon
            for index in order:
                role, piece = pieces[index]
                if not _bounding_box_contains(piece, inside):
                    continue
                try:
                    if piece.isInside(inside, 0.0, False):
                        return role
                except Exception:
                    continue

    # Fallbacks, for the few faces whose inside-point lands in no piece at
    # all - a face thinner than the epsilon, a concave corner. Nearest
    # surface first, then the part's largest piece: either way the face stays
    # on a piece of its own part, which is all a colour needs.
    best, best_distance = None, None
    for index in order:
        role, piece = pieces[index]
        try:
            distance = piece.distToShape(Part.Vertex(face.CenterOfMass))[0]
        except Exception:
            continue
        if best_distance is None or distance < best_distance:
            best, best_distance = role, distance
    if best is not None:
        return best
    return pieces[order[-1]][0]


def _face_probes(face):
    """Points ON a face, each with the face's normal there.

    More than one, because a face's centre of mass is not always on it: the
    centre of a ring - a mirror's front ring, the rim of a hole - falls in the
    hole, and an inside-point taken from there lands in whatever is behind.
    The midpoint of the face's parameter range is on a ring's surface, and a
    vertex is on a face whose trim the midpoint misses."""
    probes = []
    for u, v in _face_uv_candidates(face):
        try:
            probes.append((face.valueAt(u, v), face.normalAt(u, v)))
        except Exception:
            continue
    return probes


def _face_uv_candidates(face):
    """UV parameters worth probing on a face, most representative first."""
    candidates = []
    try:
        candidates.append(face.Surface.parameter(face.CenterOfMass))
    except Exception:
        pass
    try:
        u0, u1, v0, v1 = face.ParameterRange
        candidates.append(((u0 + u1) / 2.0, (v0 + v1) / 2.0))
    except Exception:
        pass
    for vertex in list(face.Vertexes)[:3]:
        try:
            candidates.append(face.Surface.parameter(vertex.Point))
        except Exception:
            continue
    return candidates


def _bounding_box_contains(piece, point):
    """A cheap rejection before the kernel call. A bounding box is
    conservative, so this never skips the piece that owns the point."""
    box = piece.BoundBox
    return (box.XMin <= point.x <= box.XMax
            and box.YMin <= point.y <= box.YMax
            and box.ZMin <= point.z <= box.ZMax)
