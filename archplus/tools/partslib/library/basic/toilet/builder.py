# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


def build(params, assets, ctx):
    """A close-coupled back-to-wall WC: a D-shaped pan under a closed seat,
    with a full-height cistern, a flat lid and a recessed flush button.

    Params: BowlWidth, BowlDepth, BowlHeight, TankWidth, TankDepth,
    TankHeight, SeatThickness (mm). Ships as a single common size - see the
    manifest.

    Total height is BowlHeight + TankHeight; the seat sits within the
    bowl/cistern junction rather than adding to it."""
    import Part

    bowl_width = float(params.get("BowlWidth", 380))
    bowl_depth = float(params.get("BowlDepth", 480))
    bowl_height = float(params.get("BowlHeight", 400))
    tank_width = float(params.get("TankWidth", 380))
    tank_depth = float(params.get("TankDepth", 150))
    tank_height = float(params.get("TankHeight", 350))

    seat_thickness = float(params.get("SeatThickness", 45))

    # The bowl is a D-shaped pan: square across the back where the cistern
    # meets it, strongly rounded at the front. A rounded box whose corner
    # radius approaches half the width gives exactly that plan, and the
    # squared-off back is hidden behind the cistern anyway.
    #
    # This replaces a cone run through a non-uniform scale. That was wrong
    # twice over: a circular cone is not the shape of any modern WC pan,
    # and transformGeometry turned it into a BSpline surface that at one
    # point cost 17 seconds to tessellate for a thumbnail. There is now no
    # non-uniformly scaled geometry in this part at all.
    bowl = sh.rounded_box(bowl_width, bowl_depth, bowl_height,
                          radius=bowl_width * 0.46)
    # A LARGE fillet round the whole base, not a token eased edge. On the
    # reference the pan is visibly narrower where it meets the floor and
    # sweeps outward as it rises; without that the D-shaped extrusion just
    # reads as a lozenge-sectioned tube standing on the tiles. One fillet
    # on the bottom loop of a single solid buys that whole silhouette, and
    # is far more robust in OCC than fusing a narrow foot to a wide body
    # and trying to blend the step between them.
    bowl = sh.soften_top(bowl, min(bowl_height * 0.30, bowl_width * 0.30),
                         z=0)

    # Closed seat and lid: a slab following the pan's own outline, inset a
    # touch so its edge casts a line against the pan below. It stops at the
    # cistern's front face rather than running under it.
    # Inset enough that the pan's own rim shows as a band around the seat,
    # the way it does on the reference - at 6 mm it was invisible.
    seat_inset = min(16.0, bowl_width * 0.045)
    seat_width = bowl_width - 2 * seat_inset
    seat_depth = max(bowl_depth - tank_depth - seat_inset, 10.0)
    seat = sh.rounded_box(seat_width, seat_depth, seat_thickness,
                          radius=seat_width * 0.46)
    seat = sh.soften_top(seat, seat_thickness * 0.42)
    seat = sh.place(seat, seat_inset, seat_inset, bowl_height)

    # Cistern: a tall slab sitting on the back of the pan, its front face
    # rising clear of the seat.
    tank_lid_height = min(30.0, tank_height * 0.09)
    tank_body_height = tank_height - tank_lid_height
    tank_x = (bowl_width - tank_width) / 2.0
    tank_y = bowl_depth - tank_depth
    tank = sh.rounded_box(tank_width, tank_depth, tank_body_height,
                          radius=min(20.0, tank_width * 0.06))
    tank = sh.place(tank, tank_x, tank_y, bowl_height)

    lid = sh.rounded_box(tank_width, tank_depth, tank_lid_height,
                         radius=min(20.0, tank_width * 0.06))
    lid = sh.soften_top(lid, tank_lid_height * 0.4)
    lid = sh.place(lid, tank_x, tank_y, bowl_height + tank_body_height)

    body = sh.fuse_all([bowl, seat, tank, lid])

    # Flush button, recessed into the lid rather than standing proud - on
    # the reference it reads as a dark oval sunk into the ceramic.
    button = Part.makeCylinder(min(30.0, tank_width * 0.09), 12.0)
    button = sh.place(button, bowl_width / 2.0,
                       tank_y + tank_depth * 0.5,
                       bowl_height + tank_height - 6.0)
    try:
        body = body.cut(button)
    except Exception:
        pass
    return body
