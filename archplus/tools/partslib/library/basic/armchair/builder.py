# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


def build(params, assets, ctx):
    """A single upholstered armchair: winged back, rolled arms, one deep
    seat cushion, on short square feet.

    Params: Width, Depth, SeatHeight, BackHeight, BackThickness, ArmWidth,
    ArmHeight (mm).

    Bespoke rather than `sofa()` with SeatCount 1. An armchair is
    proportioned differently - deeper relative to its width, with a taller
    back and arms that are thick relative to the seat between them - so
    driving it off the sofa's ratios gives a stubby two-seater, not a
    chair. Same construction rules though: solid masses, seams cut in,
    rolled along one axis only."""
    import Part

    width = float(params.get("Width", 900))
    depth = float(params.get("Depth", 880))
    seat_height = float(params.get("SeatHeight", 420))
    back_height = float(params.get("BackHeight", 460))
    back_thickness = float(params.get("BackThickness", 220))
    arm_width = float(params.get("ArmWidth", 200))
    arm_height = float(params.get("ArmHeight", 640))

    inner_width = max(width - 2 * arm_width, 100.0)
    foot_height = min(60.0, seat_height * 0.14)
    foot_size = min(55.0, arm_width * 0.30)

    parts = []
    for x, y in ((arm_width * 0.25, depth * 0.07),
                 (width - arm_width * 0.25 - foot_size, depth * 0.07),
                 (arm_width * 0.25, depth * 0.93 - foot_size),
                 (width - arm_width * 0.25 - foot_size,
                  depth * 0.93 - foot_size)):
        parts.append(sh.place(sh.square_leg(foot_height, foot_size), x, y, 0))

    base = Part.makeBox(width, depth, seat_height - foot_height)
    base = sh.roll_top(base, min(30.0, depth * 0.05), axis="x")
    parts.append(sh.place(base, 0, 0, foot_height))

    for x in (0.0, width - arm_width):
        arm = Part.makeBox(arm_width, depth, arm_height - foot_height)
        arm = sh.roll_top(arm, arm_width * 0.44, axis="y")
        parts.append(sh.place(arm, x, 0, foot_height))

    back = Part.makeBox(inner_width, back_thickness, back_height)
    back = sh.roll_top(back, min(back_thickness * 0.44, 90.0), axis="x")
    parts.append(sh.place(back, arm_width, depth - back_thickness,
                          seat_height))

    body = sh.fuse_all(parts)

    # A single seam where the seat cushion meets the frame at the front,
    # and one across the base of the back cushion.
    seam = 12.0
    seat_front = depth - back_thickness
    body = sh.cut_box(body, arm_width, seat_front - seam,
                      seat_height - 22.0, inner_width, seam, 40.0)
    body = sh.cut_box(body, arm_width, seat_front - seam * 1.5,
                      seat_height, inner_width, seam * 1.5 + 6.0, seam)
    return body
