# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


def build(params, assets, ctx):
    """A wide chest: two half-width drawers over full-width ones, on a
    recessed plinth, with an overhanging top.

    Params: Width, Depth, Height, TopThickness, PlinthHeight (mm),
    DrawerCount (integer, the full-width rows below the split top row).

    Bespoke rather than `nightstand()` at chest proportions. The split top
    row is the detail that makes a chest read as a chest at a glance, and
    it is meaningless on a 450mm nightstand."""
    width = float(params.get("Width", 900))
    depth = float(params.get("Depth", 450))
    height = float(params.get("Height", 800))
    top_thickness = float(params.get("TopThickness", 30))
    plinth_height = float(params.get("PlinthHeight", 70))
    drawer_count = max(int(params.get("DrawerCount", 3)), 0)

    overhang = min(14.0, width * 0.02)
    carcass_width = width - 2 * overhang
    carcass_depth = depth - overhang
    carcass_height = height - top_thickness

    box = sh.rounded_box(carcass_width, carcass_depth, carcass_height,
                         radius=6)
    box = sh.toe_kick(box, carcass_width, carcass_depth,
                      kick_height=plinth_height,
                      kick_depth=min(20.0, depth * 0.04),
                      margin=min(18.0, carcass_width * 0.03))

    margin = min(16.0, carcass_width * 0.02)
    rows = drawer_count + 1
    zone = carcass_height - plinth_height
    pulls = []
    # Every drawer front's grooves are gathered and subtracted in ONE
    # boolean at the end - five fronts is twenty boxes, and cutting them
    # one at a time was most of this part's build time.
    grooves = []
    if rows > 0 and zone > 0:
        row_height = zone / rows
        # Top row: two half-width drawers side by side.
        half = carcass_width / 2.0
        for i in range(2):
            grooves.extend(sh.panel_reveal_boxes(
                i * half + margin,
                plinth_height + (rows - 1) * row_height + margin,
                half - 2 * margin, row_height - 2 * margin,
                groove=5.0, depth=7.0))
            pulls.append(sh.place(
                sh.bar(half * 0.34, 6.0, along="x"),
                overhang + i * half + half * 0.33, overhang,
                plinth_height + (rows - 0.5) * row_height))
        # Full-width rows beneath.
        for i in range(drawer_count):
            grooves.extend(sh.panel_reveal_boxes(
                margin, plinth_height + i * row_height + margin,
                carcass_width - 2 * margin, row_height - 2 * margin,
                groove=5.0, depth=7.0))
            pulls.append(sh.place(
                sh.bar(carcass_width * 0.28, 6.0, along="x"),
                overhang + carcass_width * 0.36, overhang,
                plinth_height + (i + 0.5) * row_height))
    box = sh.cut_boxes(box, grooves)
    box = sh.place(box, overhang, overhang, 0)

    top = sh.rounded_box(width, depth, top_thickness, radius=8)
    top = sh.roll_top(top, min(top_thickness * 0.4, 10.0), axis="x")
    top = sh.place(top, 0, 0, carcass_height)

    return sh.fuse_all([box, top] + pulls)
