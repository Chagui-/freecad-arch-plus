# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


# The two corner units are the exception and the only real geometry here.
# An L-shaped plan is one box with a rectangular notch cut out of the inside
# corner, which is both how the joinery reads and the most robust way to get
# an L out of OCC - no boolean between two overlapping solids whose shared
# face has to be resolved.


def build(params, assets, ctx):
    """An L-shaped corner base unit with a worktop following the same plan.

    Params: Width, Depth, Height, WorktopThickness, KickHeight, ReturnWidth,
    ReturnDepth (mm), Worktop (Choice of "with" or "without").

    `Width`/`Depth` are the two outer legs of the L, measured from the inside
    corner of the room; `ReturnWidth`/`ReturnDepth` are how deep each leg is.
    The notch is cut out of the FRONT-LEFT, so the unit wraps a corner at the
    back-right of its own footprint.

    Without the worktop the carcass stops one worktop thickness below
    `Height`, the 40mm a sink's rim fills - see base-cabinet, which explains
    why the top of a worktopless unit is where the work surface goes rather
    than where the carcass ends. Nothing else moves: the L already runs the
    full plan, so the unit still measures the depth it advertises."""
    width = float(params.get("Width", 900))
    depth = float(params.get("Depth", 900))
    height = float(params.get("Height", 900))
    worktop = float(params.get("WorktopThickness", 40))
    kick_height = float(params.get("KickHeight", 100))
    return_width = float(params.get("ReturnWidth", 600))
    return_depth = float(params.get("ReturnDepth", 600))
    with_worktop = (params.get("Worktop") or "with") != "without"

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

    parts = [box]
    if with_worktop:
        top = _l_shape(width, depth, worktop, 6.0)
        parts.append(sh.place(top, 0, 0, carcass_height))

    pull = sh.place(sh.bar((carcass_height - kick_height) * 0.22, 7.0,
                            along="z"),
                     width - 40.0, depth - return_depth,
                     kick_height + (carcass_height - kick_height) * 0.4)
    return sh.fuse_all(parts + [pull])
