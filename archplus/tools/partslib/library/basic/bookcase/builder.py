# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


def build(params, assets, ctx):
    """An open-front carcass with shelves, a recessed plinth and a cornice.

    Params: Width, Depth, Height (mm), ShelfCount (integer).

    Shelves stop slightly short of the front edge. That small setback is
    what puts a shadow line between shelf and carcass, so the shelves read
    as separate boards rather than as stripes painted on a slab."""
    import Part

    width = float(params.get("Width", 900))
    depth = float(params.get("Depth", 300))
    height = float(params.get("Height", 1800))
    shelf_count = max(int(params.get("ShelfCount", 4)), 0)

    wall = 20.0
    back_thickness = 10.0
    shelf_thickness = 18.0
    shelf_setback = 8.0

    cornice_height = min(30.0, height * 0.018)
    # Inward overhang again - cornice at full size, carcass inset - so the
    # bookcase measures its advertised Width/Depth.
    overhang = min(12.0, depth * 0.04)
    plinth_height = min(90.0, height * 0.05)
    carcass_width = width - 2 * overhang
    carcass_depth = depth - overhang
    carcass_height = height - cornice_height

    carcass = sh.rounded_box(carcass_width, carcass_depth, carcass_height,
                             radius=8)

    inner_width = max(carcass_width - 2 * wall, 10.0)
    inner_depth = max(carcass_depth - back_thickness, 10.0)
    inner_height = max(carcass_height - wall - plinth_height, 10.0)
    cavity = Part.makeBox(inner_width, inner_depth + 1, inner_height)
    cavity.translate(sh.vector(wall, -1.0, plinth_height))
    carcass = carcass.cut(cavity)

    shelves = []
    if shelf_count > 0:
        gap = inner_height / (shelf_count + 1)
        for i in range(1, shelf_count + 1):
            shelf = Part.makeBox(inner_width, inner_depth - shelf_setback,
                                 shelf_thickness)
            shelf.translate(sh.vector(wall, shelf_setback,
                                      plinth_height + gap * i))
            shelves.append(shelf)

    carcass = sh.fuse_all([carcass] + shelves) if shelves else carcass
    # Plinth recess: set the base back on all but the very bottom so the
    # case appears to stand on a shadow gap rather than sit flat.
    carcass = sh.toe_kick(carcass, carcass_width, carcass_depth,
                           kick_height=plinth_height * 0.55,
                           kick_depth=min(25, depth * 0.1),
                           margin=min(20.0, width * 0.03))
    carcass = sh.place(carcass, overhang, overhang, 0)

    cornice = sh.rounded_box(width, depth, cornice_height, radius=8)
    cornice = sh.soften_top(cornice, cornice_height * 0.35)
    cornice = sh.place(cornice, 0, 0, carcass_height)

    return sh.fuse_all([carcass, cornice])
