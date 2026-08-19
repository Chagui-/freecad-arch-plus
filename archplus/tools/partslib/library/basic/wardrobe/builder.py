# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


def build(params, assets, ctx):
    """A two-door wardrobe: panelled doors, a centre seam, long vertical
    pulls, a plinth recess and a cornice.

    Params: Width, Depth, Height (mm), DoorCount (integer)."""
    width = float(params.get("Width", 1200))
    depth = float(params.get("Depth", 600))
    height = float(params.get("Height", 2000))
    # A wardrobe leaf runs about 600mm, and never fewer than two, so the
    # carcass reads as a wardrobe rather than a tall cupboard.
    door_count = max(2, int(-(-int(width) // 600)))

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
    margin = min(45.0, door_width * 0.12)
    # Seams between doors and the reveal around each: all one boolean.
    grooves = [
        (i * door_width - 2.5, -1.0, kick_height,
         5.0, 8.0, carcass_height - kick_height)
        for i in range(1, door_count)
    ]
    for i in range(door_count):
        grooves.extend(sh.panel_reveal_boxes(
            i * door_width + margin, kick_height + margin,
            door_width - 2 * margin,
            carcass_height - kick_height - 2 * margin,
            groove=8.0, depth=10.0))
    carcass = sh.cut_boxes(carcass, grooves)
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
