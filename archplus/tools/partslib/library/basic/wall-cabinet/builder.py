# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh
from .. import _shared


# WALL UNITS ARE WALL-HOSTED. They are the first parts in this library to
# declare `host: wall`, so their manifests carry an offset measured from the
# floor to the underside of the cabinet - the standard 1500mm to the bottom
# of a wall unit over a 900mm worktop.

def build(params, assets, ctx):
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
    box = _shared.doors(box, width, height, door_count, 0.0)
    box = sh.place(box, 0, clearance, 0)
    pulls = _shared.pulls(width, height, door_count, 0.0, clearance)
    # Handles on a wall unit sit at the BOTTOM of the door, within reach.
    pulls = [sh.place(p, 0, 0, -height * 0.30) for p in pulls]
    return sh.fuse_all([box] + pulls)
