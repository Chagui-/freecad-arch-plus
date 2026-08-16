# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Sanitary fixture builders - pure generation, no assets. Same primitive-
# massing philosophy as furniture.py: boxes, an oval-scaled cone for the
# toilet bowl and vanity basin, boolean cut/fuse, softened rim edges. Not
# vendor-accurate fixtures - a BIM-usable block for space planning.

from . import _shapes as sh


def toilet(params, assets, ctx):
    """A close-coupled WC: an oval bowl under a closed seat, with a cistern,
    an overhanging lid and a flush button.

    Params: BowlWidth, BowlDepth, BowlHeight, TankWidth, TankDepth,
    TankHeight, SeatThickness (mm). Ships as a single common size - see the
    manifest.

    Note the total height is BowlHeight + TankHeight as before; the seat
    sits within the bowl/tank junction rather than adding to it."""
    import Part

    bowl_width = float(params.get("BowlWidth", 380))
    bowl_depth = float(params.get("BowlDepth", 480))
    bowl_height = float(params.get("BowlHeight", 400))
    tank_width = float(params.get("TankWidth", 380))
    tank_depth = float(params.get("TankDepth", 150))
    tank_height = float(params.get("TankHeight", 350))

    seat_thickness = float(params.get("SeatThickness", 45))

    top_radius = bowl_width / 2.0
    base_radius = top_radius * 0.6
    bowl = Part.makeCone(base_radius, top_radius, bowl_height)
    # Deliberately NOT soften_top()'d here. oval() below runs the cone
    # through transformGeometry, so the bowl is already a BSpline surface -
    # by far the most expensive thing in this library to tessellate for a
    # thumbnail. (The dominant cost turned out to be the mesh tolerance, now
    # fixed in partslib_thumbs._tessellation_for; filleting the rim first
    # only piles a scaled blend surface on top of that.) A sharp rim is
    # invisible at thumbnail size and irrelevant on a blueprint, so this is
    # the one edge in the library that stays sharp. The tank below is a
    # plain box, never non-uniformly scaled, and still gets its rim
    # softened.
    #
    # The cone (and its top rim edge) is centred on the origin; scaling Y
    # gives it an oval footprint, then place() recentres it onto the part's
    # own footprint at (bowl_width/2, bowl_depth/2).
    bowl = sh.oval(bowl, 1.0, bowl_depth / bowl_width)
    bowl = sh.place(bowl, bowl_width / 2.0, bowl_depth / 2.0, 0)

    # Closed seat and lid: one oval slab slightly proud of the rim. Built
    # the same way as the bowl - scaled cylinder, never filleted - for the
    # same tessellation reason, and deliberately NOT cut into a ring: two
    # non-uniformly scaled solids meeting in a boolean is exactly the kind
    # of surface that made this part cost 17 seconds before.
    seat = Part.makeCylinder(top_radius, seat_thickness)
    seat = sh.oval(seat, 1.0, bowl_depth / bowl_width)
    seat = sh.place(seat, bowl_width / 2.0, bowl_depth / 2.0, bowl_height)

    tank_lid_height = min(30.0, tank_height * 0.09)
    tank_body_height = tank_height - tank_lid_height
    tank = sh.rounded_box(tank_width, tank_depth, tank_body_height, radius=15)
    tank = sh.place(tank, (bowl_width - tank_width) / 2.0, bowl_depth,
                     bowl_height)

    # The lid overhangs the cistern at the FRONT only - which is both where
    # a real cistern lid projects and the one direction that does not push
    # the part past the BowlWidth/TankDepth the catalogue advertises.
    lid_overhang = min(12.0, tank_depth * 0.08)
    lid = sh.rounded_box(tank_width, tank_depth + lid_overhang,
                         tank_lid_height, radius=12)
    lid = sh.soften_top(lid, tank_lid_height * 0.35)
    lid = sh.place(lid, (bowl_width - tank_width) / 2.0,
                    bowl_depth - lid_overhang,
                    bowl_height + tank_body_height)

    button = Part.makeCylinder(min(28.0, tank_width * 0.09), 6.0)
    button = sh.place(button, bowl_width / 2.0,
                       bowl_depth + tank_depth * 0.45,
                       bowl_height + tank_height)

    return sh.fuse_all([bowl, seat, tank, lid, button])


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

    waste = Part.makeCylinder(min(45.0, inner_width * 0.06),
                              height * 0.6)
    waste = sh.place(waste, width / 2.0, depth / 2.0,
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
