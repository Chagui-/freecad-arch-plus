# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh
from .. import _shared

# The carcass stands one pull radius back from the origin, so the handles -
# the frontmost thing on the part - still land inside the advertised Depth.
_HANDLE_PROTRUSION = _shared.PULL_RADIUS
# A leaf splits at about this width; the same "a single leaf is too wide to
# swing" judgement the base units make, one storey up.
_LEAF_WIDTH = 300.0


def build(params, assets, ctx):
    """A tall pantry: a full-height carcass of larder doors, carried by the
    same carcass/doors/pulls the base units are built from.

    Params: Width, Depth, Height (mm).

    The front is split into two tiers and two or more leaves because a
    single 2.1m leaf is not a door anyone hangs, and the split is decided
    here rather than offered as a count for the reason `base_cabinet`
    decides its own door count: a count that disagrees with the carcass it
    hangs on is never what anyone wanted.

    No shelves are modelled inside - the doors are closed, and this family
    builds a carcass as one solid with its fronts cut into it, not as an
    open box behind them."""
    width = float(params.get("Width", 600))
    depth = float(params.get("Depth", 600))
    height = float(params.get("Height", 2100))
    kick_height = min(120.0, height * 0.06)

    leaves = max(2, int(round(width / _LEAF_WIDTH)))
    tier_z = kick_height + (height - kick_height) * 0.5

    carcass = _shared.carcass(width, max(depth - _HANDLE_PROTRUSION, 1.0),
                              height, kick_height,
                              min(60.0, depth * 0.1))
    carcass = _shared.doors(carcass, width, tier_z, leaves, kick_height)
    carcass = _shared.doors(carcass, width, height, leaves, tier_z)
    pulls = (_shared.pulls(width, tier_z, leaves, kick_height, 0.0)
             + _shared.pulls(width, height, leaves, tier_z, 0.0))
    return sh.place(sh.fuse_all([carcass] + pulls), 0, _HANDLE_PROTRUSION, 0)
