# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Furniture builders - pure generation, no assets. Every shape is boxes and
# square posts composed via the helpers in _shapes.py: rounded corners,
# softened cushion edges, panel reveals, a toe-kick recess on case goods.
# This is deliberately primitive massing, not sculpted furniture - the goal
# is a floor-plan/BIM-usable block that reads as "table" or "wardrobe"
# rather than "box", not a showroom model.
#
# Two rules learned from looking at the renders rather than the code:
#
# 1. SQUARE, NOT ROUND. Legs and posts are square section. A 36mm cylinder
#    renders as a single line with no shading to read, so a chair built on
#    turned legs came out looking like wire under a floating plank.
#
# 2. SOLID, NOT SCATTERED. Where a real object is one soft mass - a sofa -
#    it is modelled as one mass with seams cut into it, not as separate
#    floating pieces. Building a sofa's cushions as individual solids with
#    air around them made it read worse, not better.
#
# `table()` is reused by two manifests (dining table, coffee table) - one
# builder serving several catalogue entries is the reuse the design spec
# calls out (Sec 6.1/6.4): those parts differ in their default dimensions
# and metadata, not in their geometry family. A desk is NOT among them; it
# has a knee hole, a pedestal and a modesty panel, so it gets `desk()`.

from . import _shapes as sh


def table(params, assets, ctx):
    """A rectangular top on 4 square legs, tied by an apron frame.

    Params: Width, Depth, Height, TopThickness, LegRadius, ApronHeight,
    ApronThickness, ApronInset, ShelfHeight (mm).

    Legs are square posts, not turned cylinders: a thin cylinder renders as
    a wire at thumbnail size, while a square post of the same nominal size
    keeps a lit face and a shadowed one. `LegRadius` still drives the size
    (it is the half-width of the post) so existing manifests need no edit.

    The apron is what separates a table from a slab on sticks. It is built
    as four rails rather than one solid block: a block under the top just
    reads as a thicker top, whereas an open frame leaves the daylight
    between the legs that the eye actually uses to read the shape.

    `ShelfHeight` adds a lower shelf between the legs when non-zero - the
    detail that most distinguishes a coffee table from a scaled-down dining
    table, which is otherwise the same object."""
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
    shelf_height = float(params.get("ShelfHeight", 0))

    top = sh.rounded_box(width, depth, top_thickness, radius=20)
    top = sh.soften_top(top, 5)
    top = sh.soften_top(top, 3, z=0)
    top = sh.place(top, 0, 0, leg_height)

    leg_size = leg_radius * 2.0
    inset = min(apron_inset, width / 2.0 - leg_size, depth / 2.0 - leg_size)
    inset = max(inset, 0.0)
    legs = [
        sh.place(sh.square_leg(leg_height, leg_size), x, y, 0)
        for x, y in ((inset, inset),
                     (width - inset - leg_size, inset),
                     (inset, depth - inset - leg_size),
                     (width - inset - leg_size, depth - inset - leg_size))
    ]

    rails = []
    apron_z = leg_height - apron_height
    rail_length = width - 2 * inset
    rail_depth = depth - 2 * inset
    if apron_height > 0 and rail_length > 0 and rail_depth > 0:
        for y in (inset, depth - inset - apron_thickness):
            rails.append(sh.place(
                sh.rounded_box(rail_length, apron_thickness, apron_height),
                inset, y, apron_z))
        for x in (inset, width - inset - apron_thickness):
            rails.append(sh.place(
                sh.rounded_box(apron_thickness, rail_depth, apron_height),
                x, inset, apron_z))

    shelf = []
    if shelf_height > 0 and rail_length > 0 and rail_depth > 0:
        shelf_thickness = min(22.0, top_thickness * 0.8)
        shelf.append(sh.place(
            sh.rounded_box(rail_length, rail_depth, shelf_thickness,
                           radius=10),
            inset, inset, min(shelf_height, leg_height - shelf_thickness)))

    return sh.fuse_all([top] + legs + rails + shelf)


def desk(params, assets, ctx):
    """An office desk: a top carried by a drawer pedestal at one end and a
    panel end at the other, closed at the back by a modesty panel.

    Params: Width, Depth, Height, TopThickness, PedestalWidth,
    PanelThickness (mm), DrawerCount (integer).

    Deliberately NOT `table()` with different numbers. A desk you sit at to
    work is a different object from a dining table: it has a knee hole with
    something solid either side of it, storage on one side, and a screen
    across the back. Four legs and an apron is the one arrangement it never
    has."""
    width = float(params.get("Width", 1400))
    depth = float(params.get("Depth", 700))
    height = float(params.get("Height", 750))
    top_thickness = min(float(params.get("TopThickness", 30)), height - 10)
    pedestal_width = float(params.get("PedestalWidth", 400))
    panel_thickness = float(params.get("PanelThickness", 30))
    drawer_count = max(int(params.get("DrawerCount", 3)), 0)

    under_height = max(height - top_thickness, 10.0)
    pedestal_width = min(pedestal_width, width * 0.4)
    # Both supports are set back from the front edge, so the top overhangs
    # them and the desk does not read as a solid block.
    setback = min(30.0, depth * 0.05)
    support_depth = depth - setback
    kick = min(60.0, under_height * 0.09)

    top = sh.rounded_box(width, depth, top_thickness, radius=12)
    top = sh.soften_top(top, 5)
    top = sh.soften_top(top, 4, z=0)
    top = sh.place(top, 0, 0, under_height)

    # Panel end (left): a solid gable, the way a desk actually stands.
    panel = sh.rounded_box(panel_thickness, support_depth, under_height,
                           radius=4)
    panel = sh.toe_kick(panel, panel_thickness, support_depth,
                         kick_height=kick, kick_depth=min(20.0, depth * 0.03),
                         margin=0.0)
    panel = sh.place(panel, 0, setback, 0)

    # Pedestal (right): a carcass of drawers.
    pedestal = sh.rounded_box(pedestal_width, support_depth, under_height,
                              radius=6)
    pedestal = sh.toe_kick(pedestal, pedestal_width, support_depth,
                            kick_height=kick,
                            kick_depth=min(25.0, depth * 0.04),
                            margin=min(15.0, pedestal_width * 0.05))
    pulls = []
    if drawer_count > 0:
        zone = under_height - kick
        drawer_height = zone / drawer_count
        margin = min(16.0, pedestal_width * 0.05)
        pull_length = pedestal_width * 0.42
        for i in range(drawer_count):
            z = kick + i * drawer_height
            pedestal = sh.panel_reveal(
                pedestal, margin, z + margin * 0.4,
                pedestal_width - 2 * margin, drawer_height - margin * 0.8,
                groove=5.0, depth=7.0)
            pulls.append(sh.place(
                sh.bar(pull_length, 6.0, along="x"),
                width - pedestal_width + (pedestal_width - pull_length) / 2.0,
                setback, kick + (i + 0.5) * drawer_height))
    pedestal = sh.place(pedestal, width - pedestal_width, setback, 0)

    # Modesty panel across the knee hole, set well back from the front.
    knee_width = width - panel_thickness - pedestal_width
    modesty = []
    if knee_width > 0:
        modesty_height = under_height * 0.55
        modesty.append(sh.place(
            sh.rounded_box(knee_width, panel_thickness * 0.6,
                           modesty_height, radius=3),
            panel_thickness, depth - panel_thickness * 0.6,
            under_height - modesty_height))

    return sh.fuse_all([top, panel, pedestal] + modesty + pulls)


def chair(params, assets, ctx):
    """A dining chair: cushioned seat on four square legs, the rear pair
    running up as back posts carrying two broad rails.

    Params: Width, Depth, SeatHeight, SeatThickness, BackHeight,
    BackThickness, LegRadius (mm).

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
    width = float(params.get("Width", 1900))
    depth = float(params.get("Depth", 900))
    seat_height = float(params.get("SeatHeight", 420))
    back_height = float(params.get("BackHeight", 400))
    back_thickness = float(params.get("BackThickness", 250))
    arm_width = float(params.get("ArmWidth", 220))
    arm_height = float(params.get("ArmHeight", 620))
    seat_count = max(int(params.get("SeatCount", 2)), 1)

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

    # Seat base: one solid block, softened on top the way the original did.
    base = sh.rounded_box(width, depth, seat_height - foot_height, radius=25)
    base = sh.soften_top(base, 14)
    base = sh.place(base, 0, 0, foot_height)
    parts.append(base)

    # Arms: a modest top fillet, roughly a fifth of the arm width. The
    # previous 0.42 was almost half the width, which rounded the top into
    # a near-semicircle - hence the sausage.
    for x in (0.0, width - arm_width):
        arm = sh.rounded_box(arm_width, depth, arm_height - foot_height,
                             radius=arm_width * 0.22)
        arm = sh.soften_top(arm, arm_width * 0.20)
        parts.append(sh.place(arm, x, 0, foot_height))

    # Back: a solid block between the arms, sitting on the seat.
    back = sh.rounded_box(inner_width, back_thickness, back_height, radius=20)
    back = sh.soften_top(back, 16)
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
