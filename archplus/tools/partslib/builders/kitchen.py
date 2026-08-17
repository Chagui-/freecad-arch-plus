# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Kitchen builders - pure generation, no assets.
#
# Kitchen units are the most repetitive family in the library: nearly every
# one is a carcass with a toe kick, doors carrying a panel reveal, and a
# handle. `_carcass()` below does that once, and each public builder differs
# only in what sits on top (a worktop, nothing) and what is cut into the
# front (doors, an oven, a drawer bank).
#
# The two corner units are the exception and the only real geometry here.
# An L-shaped plan is one box with a rectangular notch cut out of the inside
# corner, which is both how the joinery reads and the most robust way to get
# an L out of OCC - no boolean between two overlapping solids whose shared
# face has to be resolved.
#
# WALL UNITS ARE WALL-HOSTED. They are the first parts in this library to
# declare `host: wall`, so their manifests carry an offset measured from the
# floor to the underside of the cabinet - the standard 1500mm to the bottom
# of a wall unit over a 900mm worktop.

from archplus.tools.partslib import shapes as sh


def _carcass(width, depth, height, kick_height, kick_depth, radius=8.0):
    """A cabinet box standing on a recessed plinth."""
    box = sh.rounded_box(width, depth, height, radius=radius)
    return sh.toe_kick(box, width, depth,
                       kick_height=kick_height, kick_depth=kick_depth,
                       margin=min(20.0, width * 0.04))


def _doors(shape, width, height, door_count, base_z, margin=None,
           groove=6.0, seam=4.0):
    """Cut door seams and a panel reveal into a carcass front."""
    if door_count < 1:
        return shape
    door_width = width / door_count
    if margin is None:
        margin = min(40.0, door_width * 0.12)
    # Seams between doors plus the reveal around each, subtracted together:
    # an 800mm two-door unit is nine boxes and one boolean.
    boxes = [
        (i * door_width - seam / 2.0, -1.0, base_z,
         seam, 8.0, height - base_z)
        for i in range(1, door_count)
    ]
    for i in range(door_count):
        boxes.extend(sh.panel_reveal_boxes(
            i * door_width + margin, base_z + margin,
            door_width - 2 * margin, height - base_z - 2 * margin,
            groove=groove, depth=8.0))
    return sh.cut_boxes(shape, boxes)


def _pulls(width, height, door_count, base_z, y, vertical=True):
    """One handle per door, centred on the door face so it adds no depth."""
    pulls = []
    if door_count < 1:
        return pulls
    door_width = width / door_count
    length = (height - base_z) * 0.22 if vertical else door_width * 0.35
    for i in range(door_count):
        # Handles sit toward the opening edge: outer doors open outward,
        # so their handles mirror about the middle of the run.
        inset = 40.0
        x = (i * door_width + door_width - inset if i < door_count / 2.0
             else i * door_width + inset)
        if vertical:
            pulls.append(sh.place(sh.bar(length, 7.0, along="z"), x, y,
                                  base_z + (height - base_z - length) / 2.0))
        else:
            pulls.append(sh.place(sh.bar(length, 7.0, along="x"),
                                  i * door_width + (door_width - length) / 2.0,
                                  y, height - 60.0))
    return pulls


def base_cabinet(params, assets, ctx):
    """A floor-standing kitchen unit with a worktop.

    Params: Width, Depth, Height, WorktopThickness, KickHeight (mm),
    DoorCount (integer).

    `Height` is the finished worktop height, so a run of these lines up with
    the 900mm standard without the caller doing arithmetic."""
    width = float(params.get("Width", 600))
    depth = float(params.get("Depth", 600))
    height = float(params.get("Height", 900))
    worktop = float(params.get("WorktopThickness", 40))
    kick_height = float(params.get("KickHeight", 100))
    door_count = max(int(params.get("DoorCount", 1)), 0)

    overhang = min(20.0, depth * 0.04)
    carcass_depth = depth - overhang
    carcass_height = height - worktop

    box = _carcass(width, carcass_depth, carcass_height,
                   kick_height, min(45.0, depth * 0.08))
    box = _doors(box, width, carcass_height, door_count, kick_height)
    box = sh.place(box, 0, overhang, 0)

    top = sh.rounded_box(width, depth, worktop, radius=6)
    top = sh.roll_top(top, min(worktop * 0.4, 12.0), axis="x")
    top = sh.place(top, 0, 0, carcass_height)

    pulls = _pulls(width, carcass_height, door_count, kick_height, overhang)
    return sh.fuse_all([box, top] + pulls)


def oven_cabinet(params, assets, ctx):
    """A base unit housing a built-in oven, with a drawer beneath it.

    Params: Width, Depth, Height, WorktopThickness, KickHeight, OvenHeight
    (mm)."""
    width = float(params.get("Width", 600))
    depth = float(params.get("Depth", 600))
    height = float(params.get("Height", 900))
    worktop = float(params.get("WorktopThickness", 40))
    kick_height = float(params.get("KickHeight", 100))
    oven_height = float(params.get("OvenHeight", 590))

    overhang = min(20.0, depth * 0.04)
    carcass_depth = depth - overhang
    carcass_height = height - worktop
    oven_height = min(oven_height, carcass_height - kick_height - 60.0)

    box = _carcass(width, carcass_depth, carcass_height,
                   kick_height, min(45.0, depth * 0.08))

    # Oven sits at the top of the unit; the drawer takes what is left.
    oven_z = carcass_height - oven_height
    inset = min(18.0, width * 0.03)
    # Recess the whole oven front rather than outlining it: an appliance
    # front is proud of the door line, not flush with it, and the recess is
    # what puts a shadow round all four sides.
    boxes = [
        (inset, -1.0, oven_z + inset,
         width - 2 * inset, 12.0, oven_height - 2 * inset),
        # Control strip across the top of the oven, and its door line.
        (inset, -1.0, carcass_height - inset - 70.0,
         width - 2 * inset, 16.0, 6.0),
    ]
    drawer_zone = oven_z - kick_height
    if drawer_zone > 0:
        margin = min(16.0, width * 0.03)
        boxes.extend(sh.panel_reveal_boxes(
            margin, kick_height + margin,
            width - 2 * margin, drawer_zone - 2 * margin,
            groove=5.0, depth=7.0))
    box = sh.cut_boxes(box, boxes)
    box = sh.place(box, 0, overhang, 0)

    top = sh.rounded_box(width, depth, worktop, radius=6)
    top = sh.roll_top(top, min(worktop * 0.4, 12.0), axis="x")
    top = sh.place(top, 0, 0, carcass_height)

    handles = [
        # Oven door handle.
        sh.place(sh.bar(width * 0.7, 9.0, along="x"),
                 width * 0.15, overhang - 6.0,
                 carcass_height - oven_height * 0.18),
    ]
    if drawer_zone > 0:
        handles.append(sh.place(
            sh.bar(width * 0.4, 7.0, along="x"),
            width * 0.3, overhang, kick_height + drawer_zone * 0.5))
    return sh.fuse_all([box, top] + handles)


def corner_base_cabinet(params, assets, ctx):
    """An L-shaped corner base unit with a worktop following the same plan.

    Params: Width, Depth, Height, WorktopThickness, KickHeight, ReturnWidth,
    ReturnDepth (mm).

    `Width`/`Depth` are the two outer legs of the L, measured from the inside
    corner of the room; `ReturnWidth`/`ReturnDepth` are how deep each leg is.
    The notch is cut out of the FRONT-LEFT, so the unit wraps a corner at the
    back-right of its own footprint."""
    width = float(params.get("Width", 900))
    depth = float(params.get("Depth", 900))
    height = float(params.get("Height", 900))
    worktop = float(params.get("WorktopThickness", 40))
    kick_height = float(params.get("KickHeight", 100))
    return_width = float(params.get("ReturnWidth", 600))
    return_depth = float(params.get("ReturnDepth", 600))

    carcass_height = height - worktop
    return_width = min(return_width, width - 50.0)
    return_depth = min(return_depth, depth - 50.0)

    def _l_shape(w, d, h, radius):
        shape = sh.rounded_box(w, d, h, radius=radius)
        # The notch: everything in front of the return, on the left of it.
        return sh.cut_box(shape, -1.0, -1.0, -1.0,
                          w - return_width + 1.0, d - return_depth + 1.0,
                          h + 2.0)

    box = _l_shape(width, depth, carcass_height, 8.0)
    box = sh.toe_kick(box, width, depth, kick_height=kick_height,
                      kick_depth=min(45.0, depth * 0.05),
                      margin=width - return_width + 20.0)
    # One door on each leg of the L, on the two faces that actually face out.
    inset = 40.0
    box = sh.panel_reveal(box, width - return_width + inset,
                          kick_height + inset,
                          return_width - 2 * inset,
                          carcass_height - kick_height - 2 * inset,
                          groove=6.0, depth=8.0,
                          face_depth=depth - return_depth)

    top = _l_shape(width, depth, worktop, 6.0)
    top = sh.place(top, 0, 0, carcass_height)

    pull = sh.place(sh.bar((carcass_height - kick_height) * 0.22, 7.0,
                            along="z"),
                     width - 40.0, depth - return_depth,
                     kick_height + (carcass_height - kick_height) * 0.4)
    return sh.fuse_all([box, top, pull])


def wall_cabinet(params, assets, ctx):
    """A wall-hung kitchen unit. Wall-hosted - see the module notes.

    Params: Width, Depth, Height (mm), DoorCount (integer)."""
    width = float(params.get("Width", 600))
    depth = float(params.get("Depth", 350))
    height = float(params.get("Height", 720))
    door_count = max(int(params.get("DoorCount", 1)), 0)

    # The carcass is set back by the handle's own projection, so a proud
    # handle still lands inside the Depth the catalogue advertises - the
    # same inward-overhang rule the case goods in furniture.py follow.
    clearance = 8.0
    box = sh.rounded_box(width, depth - clearance, height, radius=6)
    box = _doors(box, width, height, door_count, 0.0)
    box = sh.place(box, 0, clearance, 0)
    pulls = _pulls(width, height, door_count, 0.0, clearance)
    # Handles on a wall unit sit at the BOTTOM of the door, within reach.
    pulls = [sh.place(p, 0, 0, -height * 0.30) for p in pulls]
    return sh.fuse_all([box] + pulls)


def corner_wall_cabinet(params, assets, ctx):
    """An L-shaped wall-hung corner unit. Wall-hosted.

    Params: Width, Depth, Height, ReturnWidth, ReturnDepth (mm)."""
    width = float(params.get("Width", 600))
    depth = float(params.get("Depth", 600))
    height = float(params.get("Height", 720))
    return_width = float(params.get("ReturnWidth", 350))
    return_depth = float(params.get("ReturnDepth", 350))

    return_width = min(return_width, width - 50.0)
    return_depth = min(return_depth, depth - 50.0)

    box = sh.rounded_box(width, depth, height, radius=6)
    box = sh.cut_box(box, -1.0, -1.0, -1.0,
                     width - return_width + 1.0, depth - return_depth + 1.0,
                     height + 2.0)
    inset = 35.0
    box = sh.panel_reveal(box, width - return_width + inset, inset,
                          return_width - 2 * inset, height - 2 * inset,
                          groove=6.0, depth=8.0,
                          face_depth=depth - return_depth)
    pull = sh.place(sh.bar(height * 0.22, 7.0, along="z"),
                     width - 40.0, depth - return_depth, height * 0.12)
    return sh.fuse_all([box, pull])


def hob(params, assets, ctx):
    """A gas hob to drop into a worktop: a plate with burners and knobs.

    Params: Width, Depth, PlateThickness, BurnerHeight (mm), BurnerCount
    (integer - 4 or 5, laid out in two columns).

    Placed as its own part rather than modelled into `base_cabinet` because
    on a plan the hob is a separate schedule item, and it rarely sits on the
    unit whose width matches it."""
    import Part

    width = float(params.get("Width", 600))
    depth = float(params.get("Depth", 520))
    plate = float(params.get("PlateThickness", 40))
    burner_height = float(params.get("BurnerHeight", 25))
    burner_count = max(int(params.get("BurnerCount", 4)), 1)

    body = sh.rounded_box(width, depth, plate, radius=10)
    body = sh.roll_top(body, min(plate * 0.3, 8.0), axis="x")

    burners = []
    columns = 2
    rows = int((burner_count + columns - 1) / columns)
    burner_radius = min(width / (columns * 2.6), depth / (rows * 2.6))
    made = 0
    for row in range(rows):
        for column in range(columns):
            if made >= burner_count:
                break
            x = width * (column + 1) / (columns + 1.0)
            y = depth * (row + 1) / (rows + 1.0) * 0.92 + depth * 0.06
            burners.append(sh.place(
                Part.makeCylinder(burner_radius, burner_height), x, y, plate))
            burners.append(sh.place(
                Part.makeCylinder(burner_radius * 0.42, burner_height * 1.5),
                x, y, plate))
            made += 1

    # Control knobs on the plate near the front edge. Deliberately standing
    # UP rather than projecting forward: a forward-facing knob would push
    # the part past its declared Depth, and on a hob dropped into a worktop
    # the controls are on the top surface anyway.
    knobs = []
    knob_radius = min(14.0, width * 0.03)
    for i in range(burner_count):
        x = width * (i + 1) / (burner_count + 1.0)
        knobs.append(sh.place(Part.makeCylinder(knob_radius, 12.0),
                              x, knob_radius * 1.6, plate))

    return sh.fuse_all([body] + burners + knobs)
