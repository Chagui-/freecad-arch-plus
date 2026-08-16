# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Furniture builders - pure generation, no assets. Every shape is boxes and
# cone-frustum legs composed via the helpers in _shapes.py: rounded corners,
# softened cushion-like top edges, tapered legs, a toe-kick recess on case
# goods. This is deliberately primitive massing, not sculpted furniture - the
# goal is a floor-plan/BIM-usable block that reads as "table" or "wardrobe"
# rather than "box", not a showroom model.
#
# `table()` is reused by three manifests (dining table, coffee table, desk) -
# one builder serving several catalogue entries is the reuse the design spec
# calls out (Sec 6.1/6.4): the parts differ in their default dimensions and
# metadata, not in their geometry family.

from . import _shapes as sh


def table(params, assets, ctx):
    """A rectangular top on 4 tapered legs, tied by an apron frame.

    Params: Width, Depth, Height, TopThickness, LegRadius, ApronHeight,
    ApronThickness, ApronInset (mm).

    The apron is what separates a table from a slab on sticks. It is built
    as four rails rather than one solid block: a block under the top just
    reads as a thicker top, whereas an open frame leaves the daylight
    between the legs that the eye actually uses to read the shape."""
    width = float(params.get("Width", 1600))
    depth = float(params.get("Depth", 900))
    height = float(params.get("Height", 750))
    top_thickness = min(float(params.get("TopThickness", 30)), height - 10)
    leg_radius = float(params.get("LegRadius", 30))

    leg_height = max(height - top_thickness, 10.0)
    apron_height = min(float(params.get("ApronHeight", 70)),
                       leg_height * 0.35)
    apron_thickness = float(params.get("ApronThickness", 22))
    apron_inset = float(params.get("ApronInset", 45))

    top = sh.rounded_box(width, depth, top_thickness, radius=20)
    top = sh.soften_top(top, 5)
    top = sh.soften_top(top, 3, z=0)
    top = sh.place(top, 0, 0, leg_height)

    inset_x = min(leg_radius * 1.4 + 20, width / 2.0 - 5)
    inset_y = min(leg_radius * 1.4 + 20, depth / 2.0 - 5)
    legs = [
        sh.place(sh.tapered_leg(leg_height, leg_radius * 0.65, leg_radius),
                  x, y, 0)
        for x, y in ((inset_x, inset_y), (width - inset_x, inset_y),
                     (inset_x, depth - inset_y),
                     (width - inset_x, depth - inset_y))
    ]

    rails = []
    apron_z = leg_height - apron_height
    rail_length = width - 2 * apron_inset
    rail_depth = depth - 2 * apron_inset
    if apron_height > 0 and rail_length > 0 and rail_depth > 0:
        for y in (apron_inset, depth - apron_inset - apron_thickness):
            rails.append(sh.place(
                sh.rounded_box(rail_length, apron_thickness, apron_height),
                apron_inset, y, apron_z))
        for x in (apron_inset, width - apron_inset - apron_thickness):
            rails.append(sh.place(
                sh.rounded_box(apron_thickness, rail_depth, apron_height),
                x, apron_inset, apron_z))

    return sh.fuse_all([top] + legs + rails)


def chair(params, assets, ctx):
    """A ladder-back dining chair: cushioned seat, two rear posts carrying a
    top rail and a mid rail, four legs and an H-stretcher.

    Params: Width, Depth, SeatHeight, SeatThickness, BackHeight,
    BackThickness, LegRadius (mm).

    The backrest is a frame, not a slab. Rear legs run all the way up to
    become the back posts - which is both how the joinery actually works and
    what gives the silhouette its open, unmistakably chair-shaped gap
    between seat and top rail."""
    width = float(params.get("Width", 450))
    depth = float(params.get("Depth", 450))
    seat_height = float(params.get("SeatHeight", 450))
    seat_thickness = float(params.get("SeatThickness", 40))
    back_height = float(params.get("BackHeight", 450))
    back_thickness = float(params.get("BackThickness", 40))
    leg_radius = float(params.get("LegRadius", 18))

    seat_top = seat_height + seat_thickness
    post_width = min(back_thickness, leg_radius * 2.4)
    inset_x = min(leg_radius * 1.6 + 15, width / 2.0 - 5)
    inset_y = min(leg_radius * 1.6 + 15, depth / 2.0 - 5)

    seat = sh.cushion(width, depth, seat_thickness,
                      radius=min(18, width * 0.06), edge=seat_thickness * 0.3)
    seat = sh.place(seat, 0, 0, seat_height)

    # Front legs stop at the seat; rear legs continue as the back posts.
    front_legs = [
        sh.place(sh.tapered_leg(seat_height, leg_radius * 0.65, leg_radius),
                  x, inset_y, 0)
        for x in (inset_x, width - inset_x)
    ]
    post_x = [inset_x - post_width / 2.0, width - inset_x - post_width / 2.0]
    post_y = depth - inset_y - post_width / 2.0
    posts = [
        sh.place(sh.rounded_box(post_width, post_width,
                                 seat_top + back_height, radius=4),
                  x, post_y, 0)
        for x in post_x
    ]

    # Rails span between the posts: a top rail at the head and a mid rail
    # low enough to leave the gap that reads as a ladder back.
    rail_span = width - 2 * inset_x + post_width
    rail_x = post_x[0]
    rail_thickness = max(post_width * 0.7, 12.0)
    top_rail_height = max(back_height * 0.22, 40.0)
    rails = [
        sh.place(sh.cushion(rail_span, rail_thickness, top_rail_height,
                            radius=8, edge=6),
                  rail_x, post_y + (post_width - rail_thickness) / 2.0,
                  seat_top + back_height - top_rail_height),
        sh.place(sh.rounded_box(rail_span, rail_thickness,
                                 top_rail_height * 0.6, radius=6),
                  rail_x, post_y + (post_width - rail_thickness) / 2.0,
                  seat_top + back_height * 0.42),
    ]

    # H-stretcher: a rod down each side, tied by one across the middle.
    stretcher_z = seat_height * 0.28
    stretcher_radius = max(leg_radius * 0.45, 5.0)
    side_length = depth - 2 * inset_y
    stretchers = [
        sh.place(sh.bar(side_length, stretcher_radius, along="y"),
                  x, inset_y, stretcher_z)
        for x in (inset_x, width - inset_x)
    ]
    stretchers.append(sh.place(
        sh.bar(width - 2 * inset_x, stretcher_radius, along="x"),
        inset_x, depth / 2.0, stretcher_z))

    return sh.fuse_all([seat] + front_legs + posts + rails + stretchers)


def bed(params, assets, ctx):
    """A mattress on a divan base, with a panelled headboard and pillows.

    Params: Width, Length, MattressHeight, HeadboardHeight,
    HeadboardThickness, BaseHeight (mm), PillowCount (integer).

    `Width`/`Length` describe the mattress itself; the headboard adds
    `HeadboardThickness` beyond `Length`, the same way a real headboard sits
    behind the mattress rather than eating into it.

    `BaseHeight` puts the mattress on a divan base instead of on the floor,
    so the part's overall height is BaseHeight + MattressHeight."""
    width = float(params.get("Width", 1800))
    length = float(params.get("Length", 2000))
    mattress_height = float(params.get("MattressHeight", 250))
    headboard_height = float(params.get("HeadboardHeight", 900))
    headboard_thickness = float(params.get("HeadboardThickness", 60))
    base_height = float(params.get("BaseHeight", 200))
    pillow_count = max(int(params.get("PillowCount", 2)), 0)

    # Divan base, inset all round so it reads as a plinth the mattress
    # overhangs rather than as one continuous block with the mattress.
    base_inset = min(30.0, width * 0.02)
    base = sh.rounded_box(width - 2 * base_inset, length - 2 * base_inset,
                          base_height, radius=8)
    base = sh.place(base, base_inset, base_inset, 0)

    mattress = sh.cushion(width, length, mattress_height,
                          radius=min(35, width * 0.03),
                          edge=mattress_height * 0.28)
    mattress = sh.place(mattress, 0, 0, base_height)

    headboard = sh.rounded_box(width, headboard_thickness, headboard_height,
                                radius=10)
    headboard = sh.soften_top(headboard, 10)
    # A recessed outline on the face turns the headboard from a plain board
    # into an upholstered/panelled one at the cost of four thin cuts.
    headboard = sh.panel_reveal(
        headboard, width * 0.08, base_height + mattress_height * 0.5,
        width * 0.84, headboard_height - base_height - mattress_height * 0.5
        - headboard_height * 0.08,
        groove=8.0, depth=headboard_thickness * 0.3)
    headboard = sh.place(headboard, 0, length, 0)

    pillows = []
    if pillow_count > 0:
        margin = width * 0.05
        gap = width * 0.03
        span = width - 2 * margin - gap * (pillow_count - 1)
        pillow_width = span / pillow_count
        pillow_depth = min(length * 0.2, 420.0)
        pillow_height = mattress_height * 0.42
        for i in range(pillow_count):
            pillows.append(sh.place(
                sh.cushion(pillow_width, pillow_depth, pillow_height,
                           radius=min(pillow_width, pillow_depth) * 0.28,
                           edge=pillow_height * 0.45),
                margin + i * (pillow_width + gap),
                length - pillow_depth - length * 0.03,
                base_height + mattress_height))

    return sh.fuse_all([base, mattress, headboard] + pillows)


def nightstand(params, assets, ctx):
    """A two-drawer bedside cabinet with an overhanging top and bar pulls.

    Params: Width, Depth, Height (mm), DrawerCount (integer).

    The overhanging top and the drawer reveals are what carry this: an
    unbroken box the size of a nightstand is just a box, whereas a top with
    a shadow line under it and two drawer fronts is unambiguous even at
    thumbnail size.

    The overhang is built INWARD - the top matches Width/Depth exactly and
    the carcass is inset behind it - so the part still measures the size the
    catalogue advertises. Handles are centred on the drawer face for the
    same reason: half-buried, they read as pulls without adding to the
    part's depth."""
    width = float(params.get("Width", 450))
    depth = float(params.get("Depth", 400))
    height = float(params.get("Height", 550))
    drawer_count = max(int(params.get("DrawerCount", 2)), 0)

    top_thickness = min(28.0, height * 0.06)
    overhang = min(12.0, width * 0.03)
    carcass_height = height - top_thickness

    carcass = sh.rounded_box(width - 2 * overhang, depth - overhang,
                             carcass_height, radius=8)
    carcass = sh.toe_kick(carcass, width - 2 * overhang, depth - overhang,
                           kick_height=min(30, height * 0.1),
                           kick_depth=min(40, depth * 0.2),
                           margin=min(25.0, width * 0.06))

    kick_top = min(30, height * 0.1)
    drawer_zone = carcass_height - kick_top
    if drawer_count > 0 and drawer_zone > 0:
        drawer_height = drawer_zone / drawer_count
        margin = min(18.0, width * 0.05)
        for i in range(drawer_count):
            z = kick_top + i * drawer_height
            carcass = sh.panel_reveal(
                carcass, margin, z + margin * 0.4,
                width - 2 * overhang - 2 * margin,
                drawer_height - margin * 0.8,
                groove=5.0, depth=7.0)
    # Inset on both sides and at the front; flush at the back, the way a
    # cabinet stands against a wall.
    carcass = sh.place(carcass, overhang, overhang, 0)

    top = sh.rounded_box(width, depth, top_thickness, radius=10)
    top = sh.soften_top(top, top_thickness * 0.3)
    top = sh.place(top, 0, 0, carcass_height)

    pulls = []
    if drawer_count > 0 and drawer_zone > 0:
        drawer_height = drawer_zone / drawer_count
        pull_length = (width - 2 * overhang) * 0.34
        pull_radius = 6.0
        for i in range(drawer_count):
            pulls.append(sh.place(
                sh.bar(pull_length, pull_radius, along="x"),
                (width - pull_length) / 2.0, overhang,
                kick_top + (i + 0.5) * drawer_height))

    return sh.fuse_all([carcass, top] + pulls)


def wardrobe(params, assets, ctx):
    """A two-door wardrobe: panelled doors, a centre seam, long vertical
    pulls, a plinth recess and a cornice.

    Params: Width, Depth, Height (mm), DoorCount (integer)."""
    width = float(params.get("Width", 1200))
    depth = float(params.get("Depth", 600))
    height = float(params.get("Height", 2000))
    door_count = max(int(params.get("DoorCount", 2)), 1)

    cornice_height = min(40.0, height * 0.025)
    # Overhang built INWARD: the cornice is the full advertised Width/Depth
    # and the carcass is inset behind it, so the wardrobe still measures
    # exactly what the catalogue says it does.
    overhang = min(15.0, depth * 0.03)
    carcass_width = width - 2 * overhang
    carcass_depth = depth - overhang
    carcass_height = height - cornice_height
    kick_height = min(60, height * 0.05)

    carcass = sh.rounded_box(carcass_width, carcass_depth, carcass_height,
                             radius=10)
    carcass = sh.toe_kick(carcass, carcass_width, carcass_depth,
                           kick_height=kick_height,
                           kick_depth=min(50, depth * 0.15))

    # Seams between doors, then a recessed outline on each door face.
    door_width = carcass_width / door_count
    for i in range(1, door_count):
        carcass = sh.cut_box(carcass, i * door_width - 2.5, -1.0, kick_height,
                             5.0, 8.0, carcass_height - kick_height)
    margin = min(45.0, door_width * 0.12)
    for i in range(door_count):
        carcass = sh.panel_reveal(
            carcass, i * door_width + margin, kick_height + margin,
            door_width - 2 * margin,
            carcass_height - kick_height - 2 * margin,
            groove=8.0, depth=10.0)
    carcass = sh.place(carcass, overhang, overhang, 0)

    cornice = sh.rounded_box(width, depth, cornice_height, radius=10)
    cornice = sh.soften_top(cornice, cornice_height * 0.3)
    cornice = sh.place(cornice, 0, 0, carcass_height)

    # Long vertical pulls, set just inside the meeting stiles of each door
    # pair and centred on the door face so they do not add to the depth.
    pull_length = (carcass_height - kick_height) * 0.3
    pull_z = kick_height + (carcass_height - kick_height - pull_length) / 2.0
    pulls = [
        sh.place(sh.bar(pull_length, 8.0, along="z"),
                  overhang + i * door_width
                  + (door_width - 35.0 if i < door_count - 1 else 35.0),
                  overhang, pull_z)
        for i in range(door_count)
    ]

    return sh.fuse_all([carcass, cornice] + pulls)


def sofa(params, assets, ctx):
    """A sofa with separate seat and back cushions, rolled arms and feet.

    Params: Width, Depth, SeatHeight, BackHeight, BackThickness, ArmWidth,
    ArmHeight (mm), SeatCount (integer).

    Cushions are the whole point of this one. A sofa's silhouette is
    read from the gaps - between the cushions, under the arms, above the
    seat - so the geometry here is deliberately several separate pieces
    with air between them rather than one fused mass. The frame is dropped
    to a plinth on feet so the sofa does not look poured onto the floor."""
    width = float(params.get("Width", 1900))
    depth = float(params.get("Depth", 900))
    seat_height = float(params.get("SeatHeight", 420))
    back_height = float(params.get("BackHeight", 400))
    back_thickness = float(params.get("BackThickness", 250))
    arm_width = float(params.get("ArmWidth", 220))
    arm_height = float(params.get("ArmHeight", 620))
    seat_count = max(int(params.get("SeatCount", 2)), 1)

    inner_width = max(width - 2 * arm_width, 100.0)
    foot_height = min(70.0, seat_height * 0.18)
    foot_radius = min(28.0, arm_width * 0.16)
    # The frame's own top, below the seat cushions that sit on it. The
    # cushion then makes up exactly the difference, so the top of the seat
    # lands on SeatHeight rather than somewhere above it.
    deck_height = seat_height * 0.55
    cushion_height = max(seat_height - foot_height - deck_height, 60.0)
    seat_top = foot_height + deck_height + cushion_height
    back_top = seat_top + back_height

    parts = []

    # Feet, then the plinth/frame they carry.
    for x, y in ((arm_width * 0.5, depth * 0.08),
                 (width - arm_width * 0.5, depth * 0.08),
                 (arm_width * 0.5, depth * 0.92),
                 (width - arm_width * 0.5, depth * 0.92)):
        parts.append(sh.place(
            sh.tapered_leg(foot_height, foot_radius * 0.7, foot_radius),
            x, y, 0))

    frame = sh.rounded_box(width, depth, deck_height, radius=25)
    parts.append(sh.place(frame, 0, 0, foot_height))

    # Rolled arms: a strong top fillet is what turns a slab into an arm.
    arm_depth = depth
    for x in (0.0, width - arm_width):
        arm = sh.rounded_box(arm_width, arm_depth,
                             arm_height - foot_height, radius=arm_width * 0.35)
        arm = sh.soften_top(arm, arm_width * 0.42)
        parts.append(sh.place(arm, x, 0, foot_height))

    # Back: a frame panel running the full height of the back, so the back
    # cushions have something to lean against rather than floating above
    # the arms.
    back = sh.rounded_box(inner_width, back_thickness * 0.45,
                          back_top - foot_height, radius=18)
    back = sh.soften_top(back, 14)
    parts.append(sh.place(back, arm_width,
                          depth - back_thickness * 0.45, foot_height))

    # Seat cushions across the width, with a visible gap between each.
    gap = min(18.0, inner_width * 0.012)
    seat_span = inner_width - gap * (seat_count - 1)
    seat_width = seat_span / seat_count
    seat_depth = depth - back_thickness
    for i in range(seat_count):
        parts.append(sh.place(
            sh.cushion(seat_width, seat_depth, cushion_height,
                       radius=min(seat_width, seat_depth) * 0.09,
                       edge=cushion_height * 0.32),
            arm_width + i * (seat_width + gap), 0,
            foot_height + deck_height))

    # Back cushions, one per seat, leaning on the back panel.
    back_cushion_height = back_height
    back_cushion_depth = back_thickness * 0.55
    back_cushion_z = seat_top
    for i in range(seat_count):
        parts.append(sh.place(
            sh.cushion(seat_width, back_cushion_depth, back_cushion_height,
                       radius=min(seat_width, back_cushion_depth) * 0.16,
                       edge=back_cushion_depth * 0.38),
            arm_width + i * (seat_width + gap),
            depth - back_thickness, back_cushion_z))

    return sh.fuse_all(parts)


def bookcase(params, assets, ctx):
    """An open-front carcass with shelves, a recessed plinth and a cornice.

    Params: Width, Depth, Height (mm), ShelfCount (integer).

    Shelves stop slightly short of the front edge. That small setback is
    what puts a shadow line between shelf and carcass, so the shelves read
    as separate boards rather than as stripes painted on a slab."""
    import Part

    width = float(params.get("Width", 900))
    depth = float(params.get("Depth", 300))
    height = float(params.get("Height", 1800))
    shelf_count = max(int(params.get("ShelfCount", 4)), 0)

    wall = 20.0
    back_thickness = 10.0
    shelf_thickness = 18.0
    shelf_setback = 8.0

    cornice_height = min(30.0, height * 0.018)
    # Inward overhang again - cornice at full size, carcass inset - so the
    # bookcase measures its advertised Width/Depth.
    overhang = min(12.0, depth * 0.04)
    plinth_height = min(90.0, height * 0.05)
    carcass_width = width - 2 * overhang
    carcass_depth = depth - overhang
    carcass_height = height - cornice_height

    carcass = sh.rounded_box(carcass_width, carcass_depth, carcass_height,
                             radius=8)

    inner_width = max(carcass_width - 2 * wall, 10.0)
    inner_depth = max(carcass_depth - back_thickness, 10.0)
    inner_height = max(carcass_height - wall - plinth_height, 10.0)
    cavity = Part.makeBox(inner_width, inner_depth + 1, inner_height)
    cavity.translate(sh.vector(wall, -1.0, plinth_height))
    carcass = carcass.cut(cavity)

    shelves = []
    if shelf_count > 0:
        gap = inner_height / (shelf_count + 1)
        for i in range(1, shelf_count + 1):
            shelf = Part.makeBox(inner_width, inner_depth - shelf_setback,
                                 shelf_thickness)
            shelf.translate(sh.vector(wall, shelf_setback,
                                      plinth_height + gap * i))
            shelves.append(shelf)

    carcass = sh.fuse_all([carcass] + shelves) if shelves else carcass
    # Plinth recess: set the base back on all but the very bottom so the
    # case appears to stand on a shadow gap rather than sit flat.
    carcass = sh.toe_kick(carcass, carcass_width, carcass_depth,
                           kick_height=plinth_height * 0.55,
                           kick_depth=min(25, depth * 0.1),
                           margin=min(20.0, width * 0.03))
    carcass = sh.place(carcass, overhang, overhang, 0)

    cornice = sh.rounded_box(width, depth, cornice_height, radius=8)
    cornice = sh.soften_top(cornice, cornice_height * 0.35)
    cornice = sh.place(cornice, 0, 0, carcass_height)

    return sh.fuse_all([carcass, cornice])
