# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Sanitary fixture builders - pure generation, no assets. Same primitive-
# massing philosophy as furniture.py: boxes, an oval-scaled cone for the
# toilet bowl and vanity basin, boolean cut/fuse, softened rim edges. Not
# vendor-accurate fixtures - a BIM-usable block for space planning.

from . import _shapes as sh


def toilet(params, assets, ctx):
    """A close-coupled WC: an oval bowl with a cistern tank behind it.
    Params: BowlWidth, BowlDepth, BowlHeight, TankWidth, TankDepth,
    TankHeight (mm). Ships as a single common size - see the manifest."""
    import Part

    bowl_width = float(params.get("BowlWidth", 380))
    bowl_depth = float(params.get("BowlDepth", 480))
    bowl_height = float(params.get("BowlHeight", 400))
    tank_width = float(params.get("TankWidth", 380))
    tank_depth = float(params.get("TankDepth", 150))
    tank_height = float(params.get("TankHeight", 350))

    top_radius = bowl_width / 2.0
    base_radius = top_radius * 0.6
    bowl = Part.makeCone(base_radius, top_radius, bowl_height)
    # Deliberately NOT soften_top()'d here. Filleting the cone's circular
    # rim BEFORE the oval() scale below turns a simple torus-segment blend
    # into a distorted, non-uniformly-scaled NURBS surface - measured at
    # ~25s to tessellate in writeInventor() on real FreeCAD/OCC (see the
    # "still very slow" debugging thread), dwarfing every other part's
    # thumbnail attempt combined. The tank below still gets a softened rim
    # since it is a plain box, never non-uniformly scaled, so this is the
    # one edge in the whole library that must stay sharp.
    #
    # The cone (and its top rim edge) is centred on the origin; scaling Y
    # gives it an oval footprint, then place() recentres it onto the part's
    # own footprint at (bowl_width/2, bowl_depth/2).
    bowl = sh.oval(bowl, 1.0, bowl_depth / bowl_width)
    bowl = sh.place(bowl, bowl_width / 2.0, bowl_depth / 2.0, 0)

    tank = sh.rounded_box(tank_width, tank_depth, tank_height, radius=15)
    tank = sh.soften_top(tank, 8)
    tank = sh.place(tank, (bowl_width - tank_width) / 2.0, bowl_depth,
                     bowl_height)

    return sh.fuse_all([bowl, tank])


def bathtub(params, assets, ctx):
    """A rounded rectangular tub shell. Params: Width, Depth, Height,
    WallThickness, BottomThickness (mm)."""
    import Part

    width = float(params.get("Width", 1700))
    depth = float(params.get("Depth", 700))
    height = float(params.get("Height", 550))
    wall = float(params.get("WallThickness", 60))
    bottom = float(params.get("BottomThickness", 80))

    outer = sh.rounded_box(width, depth, height, radius=60)

    inner_width = max(width - 2 * wall, 10.0)
    inner_depth = max(depth - 2 * wall, 10.0)
    inner_height = max(height - bottom, 10.0) + 1
    cavity = Part.makeBox(inner_width, inner_depth, inner_height)
    cavity.translate(sh.vector(wall, wall, bottom))
    shell = outer.cut(cavity)
    return sh.soften_top(shell, 30)


def shower_base(params, assets, ctx):
    """A shallow shower tray with a recessed floor. Params: Width, Depth,
    Height, RimThickness, RecessDepth (mm)."""
    import Part

    width = float(params.get("Width", 900))
    depth = float(params.get("Depth", 900))
    height = float(params.get("Height", 100))
    rim = float(params.get("RimThickness", 40))
    recess_depth = float(params.get("RecessDepth", 40))

    tray = sh.rounded_box(width, depth, height, radius=30)

    inner_width = max(width - 2 * rim, 10.0)
    inner_depth = max(depth - 2 * rim, 10.0)
    recess_height = min(recess_depth, height - 10.0)
    if recess_height > 0:
        recess = Part.makeBox(inner_width, inner_depth, recess_height + 1)
        recess.translate(sh.vector(rim, rim, height - recess_height))
        tray = tray.cut(recess)
    return sh.soften_top(tray, 15)


def vanity(params, assets, ctx):
    """A cabinet with an oval basin recessed into the countertop and a low
    backsplash. Params: Width, Depth, Height, BasinWidth, BasinDepth,
    BasinRecess, BacksplashHeight (mm)."""
    import Part

    width = float(params.get("Width", 900))
    depth = float(params.get("Depth", 500))
    height = float(params.get("Height", 850))
    basin_width = float(params.get("BasinWidth", width * 0.5))
    basin_depth = float(params.get("BasinDepth", depth * 0.6))
    basin_recess = float(params.get("BasinRecess", 120))
    backsplash_height = float(params.get("BacksplashHeight", 100))

    carcass = sh.rounded_box(width, depth, height, radius=10)
    carcass = sh.toe_kick(carcass, width, depth,
                           kick_height=min(60, height * 0.07),
                           kick_depth=min(50, depth * 0.15))

    basin_radius_x = basin_width / 2.0
    basin_radius_y = basin_depth / 2.0
    recess_height = min(basin_recess, height - 10.0)
    if recess_height > 0 and basin_radius_x > 0:
        basin = Part.makeCylinder(basin_radius_x, recess_height + 1)
        basin = sh.oval(basin, 1.0, basin_radius_y / basin_radius_x)
        basin = sh.place(basin, width / 2.0, depth / 2.0,
                          height - recess_height)
        carcass = carcass.cut(basin)
    carcass = sh.soften_top(carcass, 8)

    backsplash = sh.rounded_box(width, 20, backsplash_height, radius=6)
    backsplash = sh.place(backsplash, 0, depth - 20, height)

    return sh.fuse_all([carcass, backsplash])
