# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


def build(params, assets, ctx):
    """A sofa: solid base, back and arms, with cushion divisions cut in.

    Params: Width, Depth, SeatHeight, BackHeight, BackThickness, ArmWidth,
    ArmHeight (mm), SeatCount (integer).

    This is deliberately close to simple massing. An earlier version built
    the cushions as separate floating solids with air around them, and it
    read worse, not better: the seat cushions flattened into loose tiles
    and the heavily-filleted arms turned into sausages laid on a slab. A
    sofa is a large soft mass, so the mass is modelled solid and the
    cushions are suggested by seams cut into it - the same trick the
    wardrobe uses for its doors. Only the feet are separate, because
    lifting the frame off the floor is what stops it looking poured."""
    import Part

    seat_count = max(int(params.get("SeatCount", 2)), 1)
    width = params.get("Width")
    if width is None:
        # 300mm of extra body per seat over a 1300mm single-seat shell - the
        # 1600 two-seater and 1900 three-seater sold everywhere.
        width = 1000.0 + 300.0 * seat_count
    width = float(width)
    depth = float(params.get("Depth", 900))
    seat_height = float(params.get("SeatHeight", 420))
    back_height = float(params.get("BackHeight", 400))
    back_thickness = float(params.get("BackThickness", 250))
    arm_width = float(params.get("ArmWidth", 220))
    arm_height = float(params.get("ArmHeight", 620))

    inner_width = max(width - 2 * arm_width, 100.0)
    foot_height = min(55.0, seat_height * 0.13)
    foot_size = min(60.0, arm_width * 0.32)

    parts = []

    # Feet at the four corners, inset so a shadow gap shows under the frame.
    for x, y in ((arm_width * 0.25, depth * 0.06),
                 (width - arm_width * 0.25 - foot_size, depth * 0.06),
                 (arm_width * 0.25, depth * 0.94 - foot_size),
                 (width - arm_width * 0.25 - foot_size,
                  depth * 0.94 - foot_size)):
        parts.append(sh.place(sh.square_leg(foot_height, foot_size), x, y, 0))

    # Every upholstered block below is a PLAIN box rolled along one axis,
    # never a rounded_box that is then softened on top. Doing both put a
    # raised border round the top face of each arm - the roll died at the
    # corner fillets instead of running through - which is the single
    # thing that made this sofa look wrong. See shapes.roll_top.

    # Seat base: rolled along its front edge.
    base = Part.makeBox(width, depth, seat_height - foot_height)
    base = sh.roll_top(base, min(30.0, depth * 0.05), axis="x")
    parts.append(sh.place(base, 0, 0, foot_height))

    # Arms: rolled front-to-back, so the roll runs the full depth of the
    # arm and reads as one continuous surface.
    for x in (0.0, width - arm_width):
        arm = Part.makeBox(arm_width, depth, arm_height - foot_height)
        arm = sh.roll_top(arm, arm_width * 0.44, axis="y")
        parts.append(sh.place(arm, x, 0, foot_height))

    # Back: rolled along its length, matching the arms.
    back = Part.makeBox(inner_width, back_thickness, back_height)
    back = sh.roll_top(back, min(back_thickness * 0.44, 90.0), axis="x")
    back = sh.place(back, arm_width, depth - back_thickness, seat_height)
    parts.append(back)

    sofa_body = sh.fuse_all(parts)

    # Cushion seams, cut into the assembled mass: one groove per division
    # across the seat, carried up the face of the back, plus a groove along
    # the front where the seat cushions meet the frame.
    seam = min(14.0, inner_width * 0.008)
    seat_span = inner_width / seat_count
    seat_front = depth - back_thickness
    for i in range(1, seat_count):
        x = arm_width + i * seat_span - seam / 2.0
        sofa_body = sh.cut_box(sofa_body, x, -1.0, seat_height - 22.0,
                               seam, seat_front + 1.0, 40.0)
        sofa_body = sh.cut_box(sofa_body, x,
                               depth - back_thickness - 1.0,
                               seat_height, seam, 18.0, back_height * 0.92)
    sofa_body = sh.cut_box(sofa_body, arm_width, seat_front - seam,
                           seat_height - 22.0, inner_width, seam, 40.0)

    return sofa_body
