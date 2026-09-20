# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh
from .. import _shared


def build(params, assets, ctx):
    """A floor-standing kitchen unit with a worktop.

    Params: Width, Depth, Height, WorktopThickness, KickHeight (mm), Worktop
    (Choice of "with" or "without").

    `Height` is the finished worktop height, so a run of these lines up with
    the 900mm standard without the caller doing arithmetic.

    Without the worktop the carcass still stops one worktop thickness below
    `Height`: that 40mm is where the work surface goes, and a sink's rim is
    exactly that thick, so the unit it drops into supplies the hole and the
    sink supplies the top. The carcass then also takes the full depth - with
    no top to overhang it, the doors come forward to where the worktop's edge
    was, so the unit still measures the depth it advertises."""
    width = float(params.get("Width", 600))
    depth = float(params.get("Depth", 600))
    height = float(params.get("Height", 900))
    worktop = float(params.get("WorktopThickness", 40))
    kick_height = float(params.get("KickHeight", 100))
    with_worktop = (params.get("Worktop") or "with") != "without"
    # One door below 700mm; from 700mm up a single leaf is too wide to
    # swing in a galley, so the carcass is split. The rule follows the
    # width rather than being asked for: a door count that disagrees with
    # the carcass it hangs on is never what anyone wanted.
    door_count = 1 if width < 700 else 2

    # How far the carcass stands back from the part's front plane: under a
    # worktop it is the overhang that makes the top's edge, and with no top
    # it is the pull radius, because the handles are then the frontmost
    # thing on the part and the advertised Depth still has to hold them.
    front = min(20.0, depth * 0.04) if with_worktop else _shared.PULL_RADIUS
    carcass_depth = depth - front
    carcass_height = height - worktop

    box = _shared.carcass(width, carcass_depth, carcass_height,
                          kick_height, min(45.0, depth * 0.08))
    box = _shared.doors(box, width, carcass_height, door_count, kick_height)
    box = sh.place(box, 0, front, 0)

    parts = [box]
    if with_worktop:
        top = sh.rounded_box(width, depth, worktop, radius=6)
        top = sh.roll_top(top, min(worktop * 0.4, 12.0), axis="x")
        parts.append(sh.place(top, 0, 0, carcass_height))

    pulls = _shared.pulls(width, carcass_height, door_count, kick_height,
                          front)
    return sh.fuse_all(parts + pulls)
