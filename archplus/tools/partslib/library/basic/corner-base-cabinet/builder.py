# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh
from .. import _shared


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
    full plan, so the unit still measures the depth it advertises. The L is
    a box rather than a block, with no top panel - the worktop, or the sink
    dropped in, is the top - so a sink's bowl hangs in its interior instead
    of in its material."""
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
    # The L is a box too, and a base unit has no top panel: the worktop is
    # its top, or the sink dropped into it. Two boxes rather than one L,
    # because an L is a union of two rectangles and a cut stays a box.
    void_z = kick_height + _shared.PANEL
    void_h = carcass_height - void_z + 1.0
    box = sh.cut_boxes(box, [
        (width - return_width + _shared.PANEL, _shared.PANEL, void_z,
         return_width - 2.0 * _shared.PANEL, depth - 2.0 * _shared.PANEL,
         void_h),
        (_shared.PANEL, depth - return_depth + _shared.PANEL, void_z,
         width - 2.0 * _shared.PANEL, return_depth - 2.0 * _shared.PANEL,
         void_h),
    ])
    # A door on the face the notch leaves pointing at the room, and its
    # handle at the door's outer edge. That plane is the only one in the
    # notch the reveal can mark (-Y), and it is where `face_depth` already
    # pointed: the door used to be marked a leg too far over, buried inside
    # the return leg's mass where nothing could see it.
    inset = 40.0
    box = sh.panel_reveal(box, inset,
                          kick_height + inset,
                          width - return_width - 2 * inset,
                          carcass_height - kick_height - 2 * inset,
                          groove=6.0, depth=8.0,
                          face_depth=depth - return_depth)

    carcass = [box]
    tops = []
    if with_worktop:
        # A millimetre into the carcass, as in base-cabinet: the top lands on
        # the box's edges now, and a coincident face there fuses to a
        # compound of two solids rather than to one part.
        top = _l_shape(width, depth, worktop + 1.0, 6.0)
        tops.append(sh.place(top, 0, 0, carcass_height - 1.0))

    pull = sh.place(sh.bar((carcass_height - kick_height) * 0.22, 7.0,
                            along="z"),
                     width - return_width - 40.0, depth - return_depth,
                     kick_height + (carcass_height - kick_height) * 0.4)
    # Same three roles as base-cabinet, and so the same three colours: the L is
    # the mass, the worktop the surface you use, the pull the hardware. The
    # door here is a groove cut into the L, so it has no piece of its own.
    return sh.fuse_all({
        "carcass": carcass,
        "top": tops,
        "fitting": [pull],
    }, ctx)
