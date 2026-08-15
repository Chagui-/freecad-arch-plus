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
    """A rectangular top on 4 tapered legs. Params: Width, Depth, Height,
    TopThickness, LegRadius (mm)."""
    width = float(params.get("Width", 1600))
    depth = float(params.get("Depth", 900))
    height = float(params.get("Height", 750))
    top_thickness = min(float(params.get("TopThickness", 30)), height - 10)
    leg_radius = float(params.get("LegRadius", 30))

    leg_height = max(height - top_thickness, 10.0)

    top = sh.rounded_box(width, depth, top_thickness, radius=20)
    top = sh.soften_top(top, 4)
    top = sh.place(top, 0, 0, leg_height)

    inset_x = min(leg_radius * 1.4 + 20, width / 2.0 - 5)
    inset_y = min(leg_radius * 1.4 + 20, depth / 2.0 - 5)
    legs = [
        sh.place(sh.tapered_leg(leg_height, leg_radius * 0.7, leg_radius),
                  x, y, 0)
        for x, y in ((inset_x, inset_y), (width - inset_x, inset_y),
                     (inset_x, depth - inset_y),
                     (width - inset_x, depth - inset_y))
    ]
    return sh.fuse_all([top] + legs)


def chair(params, assets, ctx):
    """A seat and backrest on 4 tapered legs. Params: Width, Depth,
    SeatHeight, SeatThickness, BackHeight, BackThickness, LegRadius (mm)."""
    width = float(params.get("Width", 450))
    depth = float(params.get("Depth", 450))
    seat_height = float(params.get("SeatHeight", 450))
    seat_thickness = float(params.get("SeatThickness", 40))
    back_height = float(params.get("BackHeight", 450))
    back_thickness = float(params.get("BackThickness", 40))
    leg_radius = float(params.get("LegRadius", 18))

    seat = sh.rounded_box(width, depth, seat_thickness, radius=15)
    seat = sh.soften_top(seat, 6)
    seat = sh.place(seat, 0, 0, seat_height)

    back = sh.rounded_box(width, back_thickness, back_height, radius=12)
    back = sh.soften_top(back, 6)
    back = sh.place(back, 0, depth - back_thickness,
                     seat_height + seat_thickness)

    inset_x = min(leg_radius * 1.6 + 15, width / 2.0 - 5)
    inset_y = min(leg_radius * 1.6 + 15, depth / 2.0 - 5)
    legs = [
        sh.place(sh.tapered_leg(seat_height, leg_radius * 0.7, leg_radius),
                  x, y, 0)
        for x, y in ((inset_x, inset_y), (width - inset_x, inset_y),
                     (inset_x, depth - inset_y),
                     (width - inset_x, depth - inset_y))
    ]
    return sh.fuse_all([seat, back] + legs)


def bed(params, assets, ctx):
    """A mattress with a headboard behind it. Params: Width, Length,
    MattressHeight, HeadboardHeight, HeadboardThickness (mm).

    `Width`/`Length` describe the mattress itself; the headboard adds
    `HeadboardThickness` beyond `Length`, the same way a real headboard sits
    behind the mattress rather than eating into it."""
    width = float(params.get("Width", 1800))
    length = float(params.get("Length", 2000))
    mattress_height = float(params.get("MattressHeight", 250))
    headboard_height = float(params.get("HeadboardHeight", 900))
    headboard_thickness = float(params.get("HeadboardThickness", 60))

    mattress = sh.rounded_box(width, length, mattress_height, radius=25)
    mattress = sh.soften_top(mattress, 12)

    headboard = sh.rounded_box(width, headboard_thickness, headboard_height,
                                radius=10)
    headboard = sh.soften_top(headboard, 6)
    headboard = sh.place(headboard, 0, length, 0)

    return sh.fuse_all([mattress, headboard])


def nightstand(params, assets, ctx):
    """A small cabinet carcass with a toe-kick recess. Params: Width, Depth,
    Height (mm)."""
    width = float(params.get("Width", 450))
    depth = float(params.get("Depth", 400))
    height = float(params.get("Height", 550))

    carcass = sh.rounded_box(width, depth, height, radius=10)
    carcass = sh.soften_top(carcass, 4)
    carcass = sh.toe_kick(carcass, width, depth,
                           kick_height=min(30, height * 0.1),
                           kick_depth=min(40, depth * 0.2))
    return carcass


def wardrobe(params, assets, ctx):
    """A cabinet carcass with a toe-kick recess and a centre door seam.
    Params: Width, Depth, Height (mm)."""
    width = float(params.get("Width", 1200))
    depth = float(params.get("Depth", 600))
    height = float(params.get("Height", 2000))

    carcass = sh.rounded_box(width, depth, height, radius=10)
    carcass = sh.toe_kick(carcass, width, depth,
                           kick_height=min(60, height * 0.05),
                           kick_depth=min(50, depth * 0.15))
    carcass = sh.door_seam(carcass, width, depth, height)
    return carcass


def sofa(params, assets, ctx):
    """A seat base, backrest and two armrests. Params: Width, Depth,
    SeatHeight, BackHeight, BackThickness, ArmWidth, ArmHeight (mm)."""
    width = float(params.get("Width", 1900))
    depth = float(params.get("Depth", 900))
    seat_height = float(params.get("SeatHeight", 420))
    back_height = float(params.get("BackHeight", 400))
    back_thickness = float(params.get("BackThickness", 250))
    arm_width = float(params.get("ArmWidth", 220))
    arm_height = float(params.get("ArmHeight", 620))

    inner_width = max(width - 2 * arm_width, 100.0)

    base = sh.rounded_box(width, depth, seat_height, radius=25)
    base = sh.soften_top(base, 12)

    back = sh.rounded_box(inner_width, back_thickness, back_height, radius=20)
    back = sh.soften_top(back, 10)
    back = sh.place(back, arm_width, depth - back_thickness, seat_height)

    left_arm = sh.rounded_box(arm_width, depth, arm_height, radius=20)
    left_arm = sh.soften_top(left_arm, 10)

    right_arm = sh.place(left_arm, width - arm_width, 0, 0)

    return sh.fuse_all([base, back, left_arm, right_arm])


def bookcase(params, assets, ctx):
    """An open-front carcass with shelf dividers and a toe-kick recess.
    Params: Width, Depth, Height (mm), ShelfCount (integer)."""
    import Part

    width = float(params.get("Width", 900))
    depth = float(params.get("Depth", 300))
    height = float(params.get("Height", 1800))
    shelf_count = max(int(params.get("ShelfCount", 4)), 0)

    wall = 20.0
    back_thickness = 10.0
    shelf_thickness = 18.0

    carcass = sh.rounded_box(width, depth, height, radius=8)

    inner_width = max(width - 2 * wall, 10.0)
    inner_depth = max(depth - back_thickness, 10.0)
    inner_height = max(height - 2 * wall, 10.0)
    cavity = Part.makeBox(inner_width, inner_depth + 1, inner_height)
    cavity.translate(sh.vector(wall, -1.0, wall))
    carcass = carcass.cut(cavity)

    shelves = []
    if shelf_count > 0:
        gap = inner_height / (shelf_count + 1)
        for i in range(1, shelf_count + 1):
            shelf = Part.makeBox(inner_width, inner_depth, shelf_thickness)
            shelf.translate(sh.vector(wall, 0, wall + gap * i))
            shelves.append(shelf)

    carcass = sh.fuse_all([carcass] + shelves) if shelves else carcass
    carcass = sh.toe_kick(carcass, width, depth,
                           kick_height=min(40, height * 0.03),
                           kick_depth=min(40, depth * 0.5))
    return carcass
