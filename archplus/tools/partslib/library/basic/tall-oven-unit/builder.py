# SPDX-License-Identifier: LGPL-2.1-or-later
#
# A tall housing for a built-in oven and microwave - `oven-cabinet` one
# storey up. The appliances are their own schedule items on a plan, so they
# are cut into the unit's front rather than modelled as part of its massing.

from archplus.tools.partslib import shapes as sh
from .. import _shared

# The appliance front sizes the trade builds to: a 600mm oven and a 360mm
# microwave, both 600 wide, in a 600mm unit.
_OVEN_HEIGHT = 600.0
_MICROWAVE_HEIGHT = 360.0
# The band of unit between the two appliances, and the unit kept clear above
# the microwave for a cupboard rather than a filler.
_APPLIANCE_GAP = 100.0
_TOP_CLEARANCE = 150.0
# The carcass stands one pull radius back from the origin, so the handles -
# the frontmost thing on the part - still land inside the advertised Depth.
_HANDLE_PROTRUSION = _shared.PULL_RADIUS


def _appliance_levels(height, kick_height):
    """(oven_z, microwave_z) - the oven on the 600 line a tall housing puts
    it at (its top landing on the worktop line), the microwave above it."""
    oven_z = min(600.0, max(kick_height + 100.0, height - 1500.0))
    microwave_z = oven_z + _OVEN_HEIGHT + _APPLIANCE_GAP
    if microwave_z + _MICROWAVE_HEIGHT > height - _TOP_CLEARANCE:
        # A short unit cannot carry the gap as well; the microwave goes
        # straight on top of the oven rather than through the top of it.
        microwave_z = oven_z + _OVEN_HEIGHT
    return oven_z, microwave_z


def build(params, assets, ctx):
    """A tall unit with a built-in oven and microwave stacked in it.

    Params: Width, Depth, Height (mm).

    Recessed fronts, not outlined ones: an appliance front is proud of the
    door line rather than flush with it, and the recess is what puts a
    shadow round all four sides."""
    width = float(params.get("Width", 600))
    depth = float(params.get("Depth", 600))
    height = float(params.get("Height", 2100))
    kick_height = min(120.0, height * 0.06)
    oven_z, microwave_z = _appliance_levels(height, kick_height)
    microwave_top = microwave_z + _MICROWAVE_HEIGHT

    carcass = _shared.carcass(width, max(depth - _HANDLE_PROTRUSION, 1.0),
                              height, kick_height,
                              min(60.0, depth * 0.1))

    # One boolean for the two appliance fronts and their control strips.
    inset = min(18.0, width * 0.03)
    front = width - 2 * inset
    boxes = [
        (inset, -1.0, oven_z + inset, front, 12.0,
         _OVEN_HEIGHT - 2 * inset),
        (inset, -1.0, oven_z + _OVEN_HEIGHT - inset - 70.0, front, 16.0, 6.0),
        (inset, -1.0, microwave_z + inset, front, 12.0,
         _MICROWAVE_HEIGHT - 2 * inset),
        (inset, -1.0, microwave_top - inset - 30.0, front, 16.0, 5.0),
    ]
    carcass = sh.cut_boxes(carcass, boxes)

    # A cupboard below the oven and another above the microwave, so the two
    # appliances are a stack in a unit rather than the whole of it.
    carcass = _shared.doors(carcass, width, oven_z, 1, kick_height)
    carcass = _shared.doors(carcass, width, height, 1, microwave_top)
    pulls = (_shared.pulls(width, oven_z, 1, kick_height, 0.0)
             + _shared.pulls(width, height, 1, microwave_top, 0.0))
    return sh.place(sh.fuse_all([carcass] + pulls), 0, _HANDLE_PROTRUSION, 0)
