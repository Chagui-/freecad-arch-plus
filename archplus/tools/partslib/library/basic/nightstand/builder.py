# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


def build(params, assets, ctx):
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
        grooves = []
        for i in range(drawer_count):
            z = kick_top + i * drawer_height
            grooves.extend(sh.panel_reveal_boxes(
                margin, z + margin * 0.4,
                width - 2 * overhang - 2 * margin,
                drawer_height - margin * 0.8,
                groove=5.0, depth=7.0))
        carcass = sh.cut_boxes(carcass, grooves)
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
