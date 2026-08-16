# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Loose fittings and furnishings - television, mirror, floor lamp, curtain.
#
# These are the parts that are neither case goods nor sanitaryware: thin,
# mostly flat, and read almost entirely from their silhouette. The massing
# rules that serve the cabinets do not all transfer. In particular a screen
# or a mirror is a plane, so what makes it legible is the FRAME around it
# and the recess inside - not rounded corners, which at 20mm thickness are
# invisible anyway.
#
# The curtain is the one shape here a primitive really cannot describe, and
# the first attempt got it backwards: it cut grooves into a flat slab, which
# read exactly as what it was - a board with holes in it. Grooves SUBTRACT
# from a plane; folds DISPLACE it. It is now a row of overlapping vertical
# cylinders alternating front and back, fused into one serpentine body - a
# hanging plane curled into folds, which is what gathered cloth actually is.

from . import _shapes as sh


def television(params, assets, ctx):
    """A flat-screen TV, on a pedestal stand or wall-mounted.

    Params: Width, Height, PanelThickness, BezelWidth, StandHeight (mm),
    Mounted (0 for a stand, 1 for a wall bracket).

    `Height` is the panel alone; a stand adds `StandHeight` below it, so the
    two variants measure differently on purpose - a wall-mounted set has no
    floor footprint to schedule."""
    width = float(params.get("Width", 1230))
    height = float(params.get("Height", 710))
    panel = float(params.get("PanelThickness", 60))
    bezel = float(params.get("BezelWidth", 18))
    stand_height = float(params.get("StandHeight", 90))
    mounted = int(params.get("Mounted", 0))

    base_z = 0.0 if mounted else stand_height
    # A stand's foot is far deeper than the panel, so the panel sits in the
    # MIDDLE of that footprint and everything is measured from y=0. Laying
    # it out this way keeps the part's origin at its true minimum corner -
    # placement puts the origin on the picked point, so geometry reaching
    # back behind y=0 would land behind where the user clicked.
    foot_depth = panel * 3.2 if not mounted else panel
    panel_y = (foot_depth - panel) / 2.0 if not mounted else 0.0

    body = sh.rounded_box(width, panel, height, radius=6)
    # Screen recess in the front face: a screen is darker and set back
    # behind its bezel, and the recess is the only thing distinguishing a
    # television from a plain panel at this size.
    if width > 2 * bezel and height > 2 * bezel:
        body = sh.cut_box(body, bezel, -1.0, bezel,
                          width - 2 * bezel, panel * 0.45 + 1.0,
                          height - 2 * bezel)
    body = sh.place(body, 0, panel_y, base_z)

    parts = [body]
    if mounted:
        # Slim wall bracket behind the panel.
        parts.append(sh.place(
            sh.rounded_box(width * 0.3, 30.0, height * 0.4, radius=4),
            width * 0.35, panel, height * 0.3))
    else:
        # Pedestal: a neck on a wide foot plate.
        parts.append(sh.place(
            sh.rounded_box(width * 0.12, panel * 1.6, stand_height, radius=8),
            width * 0.44, (foot_depth - panel * 1.6) / 2.0, 0))
        parts.append(sh.place(
            sh.rounded_box(width * 0.34, foot_depth, 18.0, radius=12),
            width * 0.33, 0, 0))
    return sh.fuse_all(parts)


def mirror(params, assets, ctx):
    """A framed wall mirror. Wall-hosted.

    Params: Width, Height, Depth, FrameWidth (mm)."""
    width = float(params.get("Width", 600))
    height = float(params.get("Height", 800))
    depth = float(params.get("Depth", 30))
    frame = float(params.get("FrameWidth", 35))

    body = sh.rounded_box(width, depth, height, radius=6)
    # Glass set back inside the frame. Cut from the FRONT (-Y) face, which
    # is the face a wall-hosted part presents to the room.
    if width > 2 * frame and height > 2 * frame:
        body = sh.cut_box(body, frame, -1.0, frame,
                          width - 2 * frame, depth * 0.4 + 1.0,
                          height - 2 * frame)
    return body


def floor_lamp(params, assets, ctx):
    """A floor lamp: weighted base, slim stem, conical shade.

    Params: Height, BaseDiameter, StemDiameter, ShadeHeight, ShadeTopDiameter,
    ShadeBottomDiameter (mm)."""
    import Part

    height = float(params.get("Height", 1600))
    base_diameter = float(params.get("BaseDiameter", 300))
    stem_diameter = float(params.get("StemDiameter", 30))
    shade_height = float(params.get("ShadeHeight", 320))
    shade_top = float(params.get("ShadeTopDiameter", 260))
    shade_bottom = float(params.get("ShadeBottomDiameter", 380))

    radius = max(base_diameter, shade_bottom) / 2.0
    base_height = 25.0

    base = Part.makeCylinder(base_diameter / 2.0, base_height)
    base = sh.soften_top(base, base_height * 0.4)
    base = sh.place(base, radius, radius, 0)

    stem_height = max(height - shade_height, 10.0)
    stem = Part.makeCylinder(stem_diameter / 2.0, stem_height)
    stem = sh.place(stem, radius, radius, 0)

    # A cone frustum, wider at the bottom - the one place in this library
    # where a turned profile is the right answer rather than a square one.
    shade = Part.makeCone(shade_bottom / 2.0, shade_top / 2.0, shade_height)
    shade = sh.place(shade, radius, radius, stem_height)

    return sh.fuse_all([base, stem, shade])


def curtain(params, assets, ctx):
    """A curtain on a rail, gathered into folds. Wall-hosted.

    Params: Width, Height, Fullness, RailDiameter, HeaderHeight (mm),
    FoldCount (integer).

    The fabric is a serpentine of overlapping vertical cylinders, not a
    grooved slab - see the module notes. `Fullness` is the total depth the
    folds occupy, so it is what gives them room to bulge into."""
    import Part

    width = float(params.get("Width", 1600))
    height = float(params.get("Height", 2200))
    fullness = float(params.get("Fullness", 110))
    rail_diameter = float(params.get("RailDiameter", 28))
    header_height = float(params.get("HeaderHeight", 60))
    fold_count = max(int(params.get("FoldCount", 12)), 0)

    fabric_height = max(height - header_height, 10.0)
    # The rail is what defines the part's Width; the fabric hangs inside it,
    # so a curtain still measures exactly what the manifest advertises.
    overrun = min(80.0, width * 0.06)
    span = max(width - 2 * overrun, 10.0)

    # The fabric is a SERPENTINE, built by fusing a row of vertical
    # cylinders whose centres alternate front and back. Adjacent cylinders
    # overlap, so the union is one continuous wavy body - a hanging plane
    # curled into folds, which is what a gathered curtain actually is.
    #
    # The previous version cut grooves into a flat slab, and it read
    # exactly as what it was: a board with holes in it. Grooves SUBTRACT
    # from a plane; folds DISPLACE it. Only the second reads as cloth.
    if fold_count > 0:
        # r > span / (2 * n) guarantees neighbouring folds intersect; at
        # span / (1.7 * n) they overlap comfortably. Without that the
        # curtain would come apart into a row of loose columns.
        radius = min(span / (1.7 * fold_count), fullness / 2.0)
        radius = max(radius, 1.0)
        step = ((span - 2 * radius) / (fold_count - 1.0)
                if fold_count > 1 else 0.0)
        folds = []
        for i in range(fold_count):
            x = radius + i * step if fold_count > 1 else span / 2.0
            # Alternate which side of the rail each fold bulges toward.
            y = radius if (i % 2 == 0) else max(fullness - radius, radius)
            folds.append(sh.place(Part.makeCylinder(radius, fabric_height),
                                  x, y, 0))
        fabric = sh.fuse_all(folds)
    else:
        fabric = sh.rounded_box(span, fullness, fabric_height, radius=8)
    fabric = sh.place(fabric, overrun, 0, 0)

    rail_z = fabric_height + header_height / 2.0
    rail = Part.makeCylinder(rail_diameter / 2.0, width,
                             sh.vector(0, 0, 0), sh.vector(1, 0, 0))
    rail = sh.place(rail, 0, fullness / 2.0, rail_z)

    finial_length = rail_diameter * 0.9
    finials = [
        sh.place(Part.makeCylinder(rail_diameter * 0.75, finial_length,
                                   sh.vector(0, 0, 0), sh.vector(1, 0, 0)),
                  x, fullness / 2.0, rail_z)
        for x in (0.0, width - finial_length)
    ]

    return sh.fuse_all([fabric, rail] + finials)
