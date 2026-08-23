# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


def build(params, assets, ctx):
    """A dining chair: cushioned seat on four square legs, the rear pair
    running up as back posts carrying two broad rails.

    Params: Width, Depth (mm). Seat and back heights are fixed - 450 mm is
    what a dining chair is - and the rail and leg proportions scale from
    them.

    Everything here is square section and deliberately chunky. The first
    version used thin cylindrical legs and a thin-slatted back, and it
    rendered as a wire frame under a floating plank - at thumbnail size a
    round leg 36 mm across is a single line with no shading to read."""
    width = float(params.get("Width", 450))
    depth = float(params.get("Depth", 450))
    seat_height = float(params.get("SeatHeight", 450))
    seat_thickness = float(params.get("SeatThickness", 40))
    back_height = float(params.get("BackHeight", 450))
    back_thickness = float(params.get("BackThickness", 40))
    leg_radius = float(params.get("LegRadius", 18))

    seat_top = seat_height + seat_thickness
    # Posts are sized off LegRadius but made substantial: the first attempt
    # used thin cylinders and the chair rendered as a wire frame under a
    # floating plank. A square post of the same nominal size holds its own
    # against the seat slab.
    post = max(leg_radius * 2.2, 34.0)
    inset = min(12.0, width * 0.04)

    # Legs sit just inside the seat's own footprint, so the seat reads as
    # resting ON the frame rather than hovering over four separate sticks.
    front_y = inset
    rear_y = depth - inset - post
    left_x = inset
    right_x = width - inset - post

    front_legs = [
        sh.place(sh.square_leg(seat_height, post), x, front_y, 0)
        for x in (left_x, right_x)
    ]
    # Rear legs run the full height and become the back posts.
    posts = [
        sh.place(sh.square_leg(seat_top + back_height, post), x, rear_y, 0)
        for x in (left_x, right_x)
    ]

    seat = sh.cushion(width, depth, seat_thickness,
                      radius=min(18, width * 0.05),
                      edge=seat_thickness * 0.28)
    seat = sh.place(seat, 0, 0, seat_height)

    # Two broad rails, not thin slats - at thumbnail size a wide rail with
    # a gap under it reads as a chair back, while thin slats disappear.
    rail_span = right_x + post - left_x
    rail_thickness = max(back_thickness * 0.65, post * 0.8)
    rail_y = rear_y + (post - rail_thickness) / 2.0
    top_rail_height = max(back_height * 0.30, 70.0)
    mid_rail_height = top_rail_height * 0.72
    rails = [
        sh.place(sh.rounded_box(rail_span, rail_thickness, top_rail_height,
                                 radius=8),
                  left_x, rail_y, seat_top + back_height - top_rail_height),
        sh.place(sh.rounded_box(rail_span, rail_thickness, mid_rail_height,
                                 radius=8),
                  left_x, rail_y, seat_top + back_height * 0.30),
    ]

    # Side stretchers only, square section to match the legs. The old
    # cylindrical H-stretcher added a third kind of line to a shape that
    # only needs one.
    stretcher_z = seat_height * 0.26
    stretcher_size = max(post * 0.6, 16.0)
    stretcher_length = rear_y + post - front_y
    stretchers = [
        sh.place(sh.rounded_box(stretcher_size, stretcher_length,
                                 stretcher_size, radius=3),
                  x + (post - stretcher_size) / 2.0, front_y, stretcher_z)
        for x in (left_x, right_x)
    ]

    return sh.fuse_all(front_legs + posts + [seat] + rails + stretchers)
