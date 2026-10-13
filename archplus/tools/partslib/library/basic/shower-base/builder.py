# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh

# The depth a square tray falls back to - the catalogue's own 900 tray -
# and the share of the side the curved corner's radius takes. Three
# quarters of a 900mm side is a 675mm arc, which leaves 225mm of straight
# shoulder on each of the edges it joins: a quarter-round tray rather than
# a clipped corner. The arc is one radius across both edges, so a curved
# tray is square in plan and its depth follows its width.
_DEFAULT_DEPTH = 900.0
_CORNER_SHARE = 0.75


def _round_corner(shape, length, width, height, radius):
    """Cut the corner at (length, 0) of `shape` back to a `radius` arc.

    `shape` is an extent of `length` x `width` standing on the origin, so
    the corner being replaced is its front-right plan corner - which is the
    outer corner of a tray, the one that stands free of the two walls of
    the shower and diagonally opposite the waste. The arc is tangent to
    both faces it joins, so the two meet it without a kink, and a kernel
    that refuses the boolean leaves the corner square, which is the same
    degradation every easing in shapes.py takes.

    A cut, not a fillet: the radius a tray asks for here is three quarters
    of its side, and a fillet that big turns the corner into a cylindrical
    face the section pipeline pays for, where a boolean against primitives
    is both cheaper and more robust. `radius` is clamped so a caller cannot
    ask for an arc longer than either edge it lands on - and no further, so
    that the recess's arc, asked for at the tray's radius less the rim,
    stays concentric with the tray's own and the rim keeps one width round
    the whole curve."""
    import Part

    radius = min(radius, length, width)
    if radius <= 0:
        return shape
    # The cutter is a box over the corner quadrant, less the disc the corner
    # is rounded to: what is left of the box is the sliver outside the arc.
    # Both the box and the disc overhang the tray in z, and the box grows
    # 1mm past the tray's two edges, so every plane the boolean meets is
    # either the arc itself or clear of the tray - never a face of the tool
    # lying in a face of the tray.
    growth = 1.0
    try:
        corner = Part.makeBox(radius + growth, radius + growth, height + 2.0)
        corner.translate(sh.vector(length - radius, -growth, -1.0))
        disc = Part.makeCylinder(radius, height + 2.0,
                                 sh.vector(length - radius, radius, -1.0))
        return shape.cut(corner.cut(disc))
    except Exception:
        return shape


def build(params, assets, ctx):
    """A shallow shower tray: coved recess, upstand rim and a corner waste.

    Params: Width, Depth, Height, RimThickness, RecessDepth (mm), Corner
    ("square" or "curved"). Depth is derived: a curved corner is one arc
    spanning both edges, so a curved tray is square and its depth follows
    its width, where a square tray keeps the 900 the catalogue ships."""
    import Part

    width = float(params.get("Width", 900))
    corner = params.get("Corner") or "square"
    depth = params.get("Depth")
    if depth is None:
        depth = width if corner == "curved" else _DEFAULT_DEPTH
    depth = float(depth)
    height = float(params.get("Height", 100))
    rim = float(params.get("RimThickness", 40))
    recess_depth = float(params.get("RecessDepth", 40))

    tray = sh.rounded_box(width, depth, height, radius=30)
    # The tray's plan profile first: one corner rounded off, or all four
    # left as the rounded box gave them.
    corner_radius = 0.0
    if corner == "curved":
        # The radius comes off the short side, which a curved tray has made
        # equal on both: a pinned depth that breaks the square would take
        # the arc off the shorter edge and leave the shoulders lopsided.
        corner_radius = min(width, depth) * _CORNER_SHARE
        tray = _round_corner(tray, width, depth, height, corner_radius)
    # Narrower foot, so the tray reads as sitting proud of the floor.
    tray = sh.toe_kick(tray, width, depth,
                        kick_height=min(20.0, height * 0.2),
                        kick_depth=min(12.0, rim * 0.3),
                        margin=min(40.0, width * 0.05))

    inner_width = max(width - 2 * rim, 10.0)
    inner_depth = max(depth - 2 * rim, 10.0)
    recess_height = min(recess_depth, height - 10.0)
    if recess_height > 0:
        # A coved recess rather than a square-cut one: the rounded corners
        # and the softened floor edge are what a moulded tray actually
        # looks like, and what stops it reading as a box with a hole.
        recess = sh.rounded_box(inner_width, inner_depth, recess_height + 1,
                                radius=min(60.0, inner_width * 0.08))
        # The rim is the same width the whole way round, so the recess's
        # corner is the tray's arc inset by the rim - concentric with it,
        # not a second radius. Without this the arc would break through
        # into the recess and leave the curved corner with no rim at all.
        recess = _round_corner(recess, inner_width, inner_depth,
                               recess_height + 1, corner_radius - rim)
        recess = sh.soften_top(recess, min(20.0, recess_height * 0.45), z=0)
        recess = sh.place(recess, rim, rim, height - recess_height)
        try:
            tray = tray.cut(recess)
        except Exception:
            pass

    tray = sh.soften_top(tray, min(12.0, rim * 0.3))

    # Waste at the back-left corner of the recess, not the middle: a
    # centre drain is a wet-room detail, whereas a tray drains to one end
    # so the floor can fall towards it and the trap can reach a wall.
    waste_radius = min(45.0, inner_width * 0.06)
    waste_x = rim + inner_width * 0.16
    waste_y = depth - rim - inner_depth * 0.16
    # The bottom of the drain - the floor you look down onto - and so the
    # top of the slab of tray the waste is set into.
    waste_floor = height - recess_height - height * 0.3
    waste = Part.makeCylinder(waste_radius, height * 0.6)
    waste = sh.place(waste, waste_x, waste_y, waste_floor)
    try:
        tray = tray.cut(waste)
    except Exception:
        pass

    # The waste is a fitting: a slab of the tray under the drain comes out
    # of the body and is fused back as its own piece, so the face you see
    # down the drain is hardware and the tray around it stays carcass.
    wastes = []
    # Square about the drain and wide enough to take the whole of it - not
    # a disc, whose wall would land on the drain's own and leave one face
    # shared by two pieces - but held inside the recess, and no deeper than
    # the tray under the drain, so the fuse puts back what was cut.
    slab_height = min(height * 0.1, waste_floor)
    slab_half = min(waste_radius * 1.6, waste_x - rim, width - rim - waste_x,
                    waste_y - rim, depth - rim - waste_y)
    if slab_height > 0 and slab_half > 0:
        slab_width = slab_half * 2.0
        slab_x = waste_x - slab_half
        slab_y = waste_y - slab_half
        slab_z = waste_floor - slab_height
        slab = Part.makeBox(slab_width, slab_width, slab_height)
        slab.translate(sh.vector(slab_x, slab_y, slab_z))
        tray = sh.cut_box(tray, slab_x, slab_y, slab_z,
                          slab_width, slab_width, slab_height)
        wastes.append(slab)

    # Two roles, and so two colours: the tray is the moulded mass, the waste
    # the hardware set into it.
    return sh.fuse_all({
        "shell": [tray],
        "fitting": wastes,
    }, ctx)
