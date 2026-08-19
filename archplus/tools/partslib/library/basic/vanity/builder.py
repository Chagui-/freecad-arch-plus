# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


def build(params, assets, ctx):
    """A vanity unit: two panelled doors with pulls, an overhanging
    countertop with an oval basin recessed into it, a backsplash and a tap.

    Params: Width, Depth, Height, BasinWidth, BasinDepth, BasinRecess,
    BacksplashHeight (mm), DoorCount (integer)."""
    import Part

    width = float(params.get("Width", 900))
    depth = float(params.get("Depth", 500))
    height = float(params.get("Height", 850))
    # The basin takes half the top: a 600 unit gets a 300 basin, a 900
    # unit a 450.
    basin_width = width * 0.5
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
    margin = min(35.0, door_width * 0.12)
    grooves = [
        (i * door_width - 2.0, -1.0, kick_height,
         4.0, 7.0, carcass_height - kick_height)
        for i in range(1, door_count)
    ]
    for i in range(door_count):
        grooves.extend(sh.panel_reveal_boxes(
            i * door_width + margin, kick_height + margin,
            door_width - 2 * margin,
            carcass_height - kick_height - 2 * margin,
            groove=6.0, depth=8.0))
    carcass = sh.cut_boxes(carcass, grooves)
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
