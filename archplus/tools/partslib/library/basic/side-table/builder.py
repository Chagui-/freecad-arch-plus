# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


def build(params, assets, ctx):
    """A small occasional table: square top, four square legs, a lower
    shelf and a single shallow drawer in the apron.

    Params: Width, Depth, Height, TopThickness, LegSize, ShelfHeight,
    DrawerHeight (mm).

    Bespoke rather than `table()` at small numbers. A side table is taller
    relative to its top than a dining table and earns its keep from what is
    under the top - a shelf and a drawer - which a scaled-down dining table
    does not have."""
    width = float(params.get("Width", 450))
    depth = float(params.get("Depth", 450))
    height = float(params.get("Height", 550))
    top_thickness = float(params.get("TopThickness", 25))
    leg_size = float(params.get("LegSize", 45))
    shelf_height = float(params.get("ShelfHeight", 140))
    drawer_height = float(params.get("DrawerHeight", 90))

    leg_height = max(height - top_thickness, 10.0)
    inset = min(10.0, width * 0.03)

    top = sh.rounded_box(width, depth, top_thickness, radius=8)
    top = sh.roll_top(top, min(top_thickness * 0.4, 8.0), axis="x")
    top = sh.place(top, 0, 0, leg_height)

    legs = [
        sh.place(sh.square_leg(leg_height, leg_size), x, y, 0)
        for x, y in ((inset, inset),
                     (width - inset - leg_size, inset),
                     (inset, depth - inset - leg_size),
                     (width - inset - leg_size, depth - inset - leg_size))
    ]

    span_x = width - 2 * inset
    span_y = depth - 2 * inset
    drawer_z = leg_height - drawer_height
    box = sh.rounded_box(span_x, span_y, drawer_height, radius=4)
    margin = min(14.0, span_x * 0.05)
    box = sh.panel_reveal(box, margin, margin,
                          span_x - 2 * margin, drawer_height - 2 * margin,
                          groove=4.0, depth=6.0)
    box = sh.place(box, inset, inset, drawer_z)

    shelf = sh.place(
        sh.rounded_box(span_x, span_y, 18.0, radius=6),
        inset, inset, min(shelf_height, leg_height - 18.0))

    pull = sh.place(sh.bar(span_x * 0.3, 6.0, along="x"),
                     width / 2.0 - span_x * 0.15, inset,
                     drawer_z + drawer_height / 2.0)

    return sh.fuse_all([top] + legs + [box, shelf, pull])
