# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


def build(params, assets, ctx):
    """A low TV unit: a pair of doored cupboards flanking open shelf bays.

    Params: Width, Depth, Height, TopThickness, PlinthHeight, DoorWidth
    (mm), ShelfCount (integer).

    The open middle is the point - a media unit has to show its
    compartments, so this is the one case good in the library that is not a
    closed box with reveals cut into it."""
    import Part

    width = float(params.get("Width", 1600))
    depth = float(params.get("Depth", 400))
    height = float(params.get("Height", 500))
    top_thickness = float(params.get("TopThickness", 25))
    plinth_height = float(params.get("PlinthHeight", 60))
    door_width = float(params.get("DoorWidth", 420))
    shelf_count = params.get("ShelfCount")
    if shelf_count is None:
        # One open bay per metre of run: 1600 gives one, 2000 gives two.
        shelf_count = int(width // 1000)
    shelf_count = max(int(shelf_count), 0)

    carcass_height = height - top_thickness
    door_width = min(door_width, width * 0.35)
    wall = 18.0
    # Set the carcass back by the handle's projection so a proud pull still
    # measures inside the declared Depth, as the other case goods do.
    clearance = 8.0
    carcass_depth = depth - clearance

    box = sh.rounded_box(width, carcass_depth, carcass_height, radius=5)

    # Hollow out the middle bay, leaving the two end cupboards solid.
    bay_width = width - 2 * door_width - 2 * wall
    bay_height = carcass_height - plinth_height - wall
    shelves = []
    if bay_width > 0 and bay_height > 0:
        cavity = Part.makeBox(bay_width, carcass_depth - wall + 1.0, bay_height)
        cavity.translate(sh.vector(door_width + wall, -1.0, plinth_height))
        try:
            box = box.cut(cavity)
        except Exception:
            pass
        if shelf_count > 0:
            gap = bay_height / (shelf_count + 1.0)
            for i in range(1, shelf_count + 1):
                shelf = Part.makeBox(bay_width, carcass_depth - wall - 8.0, 16.0)
                shelf.translate(sh.vector(door_width + wall, 8.0,
                                          plinth_height + gap * i))
                shelves.append(shelf)

    # Doors on the two end cupboards.
    margin = min(30.0, door_width * 0.1)
    grooves = []
    for x in (0.0, width - door_width):
        grooves.extend(sh.panel_reveal_boxes(
            x + margin, plinth_height + margin,
            door_width - 2 * margin,
            carcass_height - plinth_height - 2 * margin,
            groove=5.0, depth=7.0))
    box = sh.cut_boxes(box, grooves)
    box = sh.toe_kick(box, width, carcass_depth, kick_height=plinth_height,
                      kick_depth=min(18.0, depth * 0.04),
                      margin=min(20.0, width * 0.02))
    box = sh.place(box, 0, clearance, 0)
    shelves = [sh.place(s, 0, clearance, 0) for s in shelves]

    top = sh.rounded_box(width, depth, top_thickness, radius=6)
    top = sh.roll_top(top, min(top_thickness * 0.4, 8.0), axis="x")
    top = sh.place(top, 0, 0, carcass_height)

    pulls = [
        sh.place(sh.bar(door_width * 0.3, 6.0, along="x"),
                  x + door_width * 0.35, clearance,
                  carcass_height - (carcass_height - plinth_height) * 0.22)
        for x in (0.0, width - door_width)
    ]

    return sh.fuse_all([box, top] + shelves + pulls)
