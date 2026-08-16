# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Sanitary fixture builders - pure generation, no assets. Same primitive-
# massing philosophy as furniture.py: boxes, an oval-scaled cone for the
# toilet bowl and vanity basin, boolean cut/fuse, softened rim edges. Not
# vendor-accurate fixtures - a BIM-usable block for space planning.

from . import _shapes as sh


def toilet(params, assets, ctx):
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


def bathtub(params, assets, ctx):
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


def shower_base(params, assets, ctx):
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


def vanity(params, assets, ctx):
    """A vanity unit: two panelled doors with pulls, an overhanging
    countertop with an oval basin recessed into it, a backsplash and a tap.

    Params: Width, Depth, Height, BasinWidth, BasinDepth, BasinRecess,
    BacksplashHeight (mm), DoorCount (integer)."""
    import Part

    width = float(params.get("Width", 900))
    depth = float(params.get("Depth", 500))
    height = float(params.get("Height", 850))
    basin_width = float(params.get("BasinWidth", width * 0.5))
    basin_depth = float(params.get("BasinDepth", depth * 0.6))
    basin_recess = float(params.get("BasinRecess", 120))
    backsplash_height = float(params.get("BacksplashHeight", 100))
    door_count = max(int(params.get("DoorCount", 2)), 1)

    top_thickness = min(40.0, height * 0.05)
    overhang = min(15.0, depth * 0.03)
    carcass_width = width - 2 * overhang
    carcass_depth = depth - overhang
    carcass_height = height - top_thickness
    kick_height = min(60, height * 0.07)

    carcass = sh.rounded_box(carcass_width, carcass_depth, carcass_height,
                             radius=10)
    carcass = sh.toe_kick(carcass, carcass_width, carcass_depth,
                           kick_height=kick_height,
                           kick_depth=min(50, depth * 0.15))

    door_width = carcass_width / door_count
    for i in range(1, door_count):
        carcass = sh.cut_box(carcass, i * door_width - 2.0, -1.0, kick_height,
                             4.0, 7.0, carcass_height - kick_height)
    margin = min(35.0, door_width * 0.12)
    for i in range(door_count):
        carcass = sh.panel_reveal(
            carcass, i * door_width + margin, kick_height + margin,
            door_width - 2 * margin,
            carcass_height - kick_height - 2 * margin,
            groove=6.0, depth=8.0)
    # Inset both sides and at the front, flush at the back against the wall.
    carcass = sh.place(carcass, overhang, overhang, 0)

    pulls = [
        sh.place(sh.bar(min(110.0, door_width * 0.4), 6.0, along="x"),
                  overhang + (i + 0.5) * door_width
                  - min(110.0, door_width * 0.4) / 2.0,
                  overhang, carcass_height - kick_height * 1.2)
        for i in range(door_count)
    ]

    # Countertop slab, with the basin cut into it. Cutting the basin from
    # the thin top rather than the whole carcass keeps the boolean between
    # the scaled-cylinder basin and a small solid.
    top = sh.rounded_box(width, depth, top_thickness, radius=10)
    basin_radius_x = basin_width / 2.0
    basin_radius_y = basin_depth / 2.0
    recess_height = min(basin_recess, top_thickness * 3.0)
    if basin_radius_x > 0 and recess_height > 0:
        bowl_depth_below = max(recess_height - top_thickness, 0.0)
        basin = Part.makeCylinder(basin_radius_x, recess_height + 1)
        basin = sh.oval(basin, 1.0, basin_radius_y / basin_radius_x)
        basin = sh.place(basin, width / 2.0, depth / 2.0, -bowl_depth_below)
        try:
            top = top.cut(basin)
        except Exception:
            pass
    top = sh.soften_top(top, min(8.0, top_thickness * 0.25))
    top = sh.place(top, 0, 0, carcass_height)

    backsplash = sh.rounded_box(width, 20, backsplash_height, radius=6)
    backsplash = sh.soften_top(backsplash, 6)
    backsplash = sh.place(backsplash, 0, depth - 20, height)

    # Tap: a riser against the backsplash with a spout reaching the basin.
    tap_x = width / 2.0
    tap_y = depth - 55.0
    tap_height = min(220.0, backsplash_height * 2.0)
    riser = sh.place(Part.makeCylinder(16.0, tap_height), tap_x, tap_y, height)
    spout = sh.place(sh.bar(min(150.0, basin_depth * 0.5), 11.0, along="y"),
                      tap_x, tap_y - min(150.0, basin_depth * 0.5),
                      height + tap_height - 11.0)

    return sh.fuse_all([carcass, top, backsplash, riser, spout] + pulls)


def shower_screen(params, assets, ctx):
    """A glass panel for a shower or over a bath: a pane in a slim profile,
    with a floor-to-top support post at the fixed edge.

    Params: Width, Height, GlassThickness, ProfileWidth (mm).

    Placed as a floor-hosted part rather than wall-hosted: a bath screen
    stands on the tub rim and a walk-in panel stands on the tray, and in
    both cases the thing you position is the foot of the post, not a fixing
    height up the wall."""
    width = float(params.get("Width", 900))
    height = float(params.get("Height", 1900))
    glass = float(params.get("GlassThickness", 8))
    profile = float(params.get("ProfileWidth", 30))

    glass = min(glass, profile)
    pane_width = max(width - profile, 10.0)

    # The post is at the wall end (+Y is the wall side for a floor part
    # standing against one), the pane runs out from it.
    post = sh.rounded_box(profile, profile, height, radius=3)
    post = sh.place(post, 0, 0, 0)

    pane = sh.rounded_box(pane_width, glass, height - profile * 0.3, radius=2)
    pane = sh.place(pane, profile, (profile - glass) / 2.0, 0)

    # A short bottom rail stiffens the free edge and gives the pane
    # something to read against at the floor.
    rail = sh.rounded_box(pane_width, profile * 0.8, profile * 0.8, radius=3)
    rail = sh.place(rail, profile, (profile - profile * 0.8) / 2.0, 0)

    return sh.fuse_all([post, pane, rail])


def towel_hook(params, assets, ctx):
    """A wall towel hook: a backplate and a single rod that runs out from
    the wall and curves upward at the tip. Wall-hosted.

    Params: PlateWidth, PlateHeight, PlateDepth, Projection, ArmDiameter,
    BendRadius (mm).

    The rod is one continuous piece - a straight length plus a real
    quarter-bend - not two cylinders butted at a right angle. A mitred
    corner reads as two pipes touching, which is what the first version
    looked like."""
    import Part

    plate_width = float(params.get("PlateWidth", 55))
    plate_height = float(params.get("PlateHeight", 55))
    plate_depth = float(params.get("PlateDepth", 12))
    projection = float(params.get("Projection", 65))
    arm_diameter = float(params.get("ArmDiameter", 14))
    bend_radius = float(params.get("BendRadius", 18))

    tube = arm_diameter / 2.0
    bend_radius = max(bend_radius, tube * 1.2)
    cx = plate_width / 2.0
    # The bend's centre of curvature sits directly above where the straight
    # arm ends, so the arc enters heading -Y and leaves heading +Z. Offset
    # by the tube radius as well as the bend radius, so the OUTSIDE of the
    # curve lands on y=0 rather than reaching behind the part's origin.
    arm_z = plate_height / 2.0
    centre_y = bend_radius + tube
    centre_z = arm_z + bend_radius

    plate = sh.rounded_box(plate_width, plate_depth, plate_height, radius=8)
    plate = sh.place(plate, 0, projection - plate_depth, 0)

    arm_length = max(projection - plate_depth - centre_y, tube)
    arm = Part.makeCylinder(tube, arm_length, sh.vector(0, 0, 0),
                            sh.vector(0, -1, 0))
    arm = sh.place(arm, cx, projection - plate_depth, arm_z)

    parts = [plate, arm]
    elbow = sh.tube_elbow(tube, bend_radius)
    if elbow is not None:
        # The quarter-bend is built in the XY plane running +X to +Y. One
        # 180-degree turn about (1, 0, -1) maps X to -Z and Y to -Y, which
        # lands the arc's ends exactly on the arm end and the upturned tip.
        elbow = sh.rotate(elbow, (1.0, 0.0, -1.0), 180.0)
        parts.append(sh.place(elbow, cx, centre_y, centre_z))
        # Short upturned tip continuing out of the bend.
        tip_length = tube * 2.2
        parts.append(sh.place(Part.makeCylinder(tube, tip_length),
                              cx, centre_y - bend_radius, centre_z))
    else:
        # No torus available: a straight peg still hangs a towel.
        parts.append(sh.place(Part.makeCylinder(tube, bend_radius * 1.6),
                              cx, centre_y, arm_z))

    return sh.fuse_all(parts)


def toilet_roll_holder(params, assets, ctx):
    """A wall toilet-roll holder: backplate, an arm out from the wall, and
    the roll on a spindle running PARALLEL to the wall. Wall-hosted.

    Params: PlateWidth, PlateHeight, PlateDepth, ArmLength, RollDiameter,
    RollWidth, CoreDiameter (mm).

    The spindle direction is the whole point. The first version ran the arm
    and the spindle along the same axis, so the roll hung off the end of a
    stick like a paint roller. On a real holder the arm projects from the
    wall and the roll turns on an axis across it."""
    import Part

    plate_width = float(params.get("PlateWidth", 50))
    plate_height = float(params.get("PlateHeight", 50))
    plate_depth = float(params.get("PlateDepth", 12))
    arm_length = float(params.get("ArmLength", 70))
    roll_diameter = float(params.get("RollDiameter", 115))
    roll_width = float(params.get("RollWidth", 100))
    core_diameter = float(params.get("CoreDiameter", 45))

    roll_radius = roll_diameter / 2.0
    spindle_radius = max(core_diameter * 0.28, 6.0)

    # Lay the part out so its minimum corner is the origin: the roll is the
    # widest thing in Y and Z, so those extents set the envelope.
    depth = roll_radius + arm_length + plate_depth
    axis_y = roll_radius
    axis_z = roll_radius

    plate = sh.rounded_box(plate_width, plate_depth, plate_height, radius=6)
    plate = sh.place(plate, 0, depth - plate_depth,
                      axis_z - plate_height / 2.0)

    arm = Part.makeCylinder(spindle_radius * 1.3, arm_length,
                            sh.vector(0, 0, 0), sh.vector(0, -1, 0))
    arm = sh.place(arm, plate_width / 2.0, depth - plate_depth, axis_z)

    # Spindle runs across the arm, cantilevered so a roll can slide on.
    spindle_length = roll_width + 14.0
    spindle = Part.makeCylinder(spindle_radius, spindle_length,
                                sh.vector(0, 0, 0), sh.vector(1, 0, 0))
    spindle = sh.place(spindle, plate_width / 2.0, axis_y, axis_z)

    roll = Part.makeCylinder(roll_radius, roll_width,
                             sh.vector(0, 0, 0), sh.vector(1, 0, 0))
    roll = sh.place(roll, plate_width / 2.0 + 7.0, axis_y, axis_z)
    core = Part.makeCylinder(core_diameter / 2.0, roll_width + 4.0,
                             sh.vector(0, 0, 0), sh.vector(1, 0, 0))
    core = sh.place(core, plate_width / 2.0 + 5.0, axis_y, axis_z)
    try:
        roll = roll.cut(core)
    except Exception:
        pass

    return sh.fuse_all([plate, arm, spindle, roll])
