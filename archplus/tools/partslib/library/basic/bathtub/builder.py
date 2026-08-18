# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


def build(params, assets, ctx):
    """A tub with a rounded basin, an overhanging rim and a drain.

    Params: Width, Depth, Height, WallThickness, BottomThickness (mm).

    The cavity is a rounded box, not a plain one, so the basin has the
    coved corners a real tub has - a square-cornered hole reads as a sink
    cut into a block. The rim is a separate slab so there is a visible
    lip around the top rather than a raw cut edge."""
    import Part

    width = float(params.get("Width", 1700))
    depth = float(params.get("Depth", 700))
    height = float(params.get("Height", 550))
    wall = float(params.get("WallThickness", 60))
    bottom = float(params.get("BottomThickness", 80))

    rim_thickness = min(28.0, height * 0.06)
    # Overhang built inward: the rim is the advertised Width/Depth and the
    # body is inset behind it, so the tub measures what it claims to.
    rim_overhang = min(14.0, wall * 0.25)
    body_width = width - 2 * rim_overhang
    body_depth = depth - 2 * rim_overhang
    body_height = height - rim_thickness

    body = sh.rounded_box(body_width, body_depth, body_height, radius=60)
    # Slight plinth recess at the floor: tubs sit on a base narrower than
    # their rim, and the shadow gap is most of what sells that.
    body = sh.toe_kick(body, body_width, body_depth,
                        kick_height=min(45.0, height * 0.09),
                        kick_depth=min(18.0, wall * 0.3),
                        margin=min(60.0, width * 0.05))
    body = sh.place(body, rim_overhang, rim_overhang, 0)

    rim = sh.rounded_box(width, depth, rim_thickness, radius=60)
    rim = sh.soften_top(rim, rim_thickness * 0.4)
    rim = sh.place(rim, 0, 0, body_height)

    tub = sh.fuse_all([body, rim])

    inner_width = max(width - 2 * wall, 10.0)
    inner_depth = max(depth - 2 * wall, 10.0)
    inner_height = max(height - bottom, 10.0)
    cavity = sh.rounded_box(inner_width, inner_depth, inner_height + 1,
                            radius=min(90.0, inner_depth * 0.3))
    cavity = sh.soften_top(cavity, min(60.0, inner_height * 0.4), z=0)
    cavity = sh.place(cavity, wall, wall, bottom)
    try:
        tub = tub.cut(cavity)
    except Exception:
        pass

    # Drain well at one end, where a real tub puts it.
    drain = Part.makeCylinder(min(45.0, inner_depth * 0.09), bottom * 0.5)
    drain = sh.place(drain, width - wall - inner_width * 0.12, depth / 2.0,
                      bottom - bottom * 0.5)
    try:
        tub = tub.cut(drain)
    except Exception:
        pass
    return tub
