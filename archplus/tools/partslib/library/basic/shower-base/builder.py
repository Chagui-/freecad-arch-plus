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
    waste = Part.makeCylinder(waste_radius, height * 0.6)
    waste = sh.place(waste,
                      rim + inner_width * 0.16,
                      depth - rim - inner_depth * 0.16,
                      height - recess_height - height * 0.3)
    try:
        tray = tray.cut(waste)
    except Exception:
        pass
    return tray
