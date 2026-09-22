# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


def build(params, assets, ctx):
    """A shallow shower tray: coved recess, upstand rim and a centre waste.

    Params: Width, Depth, Height, RimThickness, RecessDepth (mm)."""
    import Part

    width = float(params.get("Width", 900))
    depth = float(params.get("Depth", 900))
    height = float(params.get("Height", 100))
    rim = float(params.get("RimThickness", 40))
    recess_depth = float(params.get("RecessDepth", 40))

    tray = sh.rounded_box(width, depth, height, radius=30)
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
