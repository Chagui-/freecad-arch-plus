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

from archplus.tools.partslib import shapes as sh


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
