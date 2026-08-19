# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh
from .. import _shared


def build(params, assets, ctx):
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
    # One door below 700mm; from 700mm up a single leaf is too wide to
    # swing in a galley, so the carcass is split. The rule follows the
    # width rather than being asked for: a door count that disagrees with
    # the carcass it hangs on is never what anyone wanted.
    door_count = 1 if width < 700 else 2

    overhang = min(20.0, depth * 0.04)
    carcass_depth = depth - overhang
    carcass_height = height - worktop

    box = _shared.carcass(width, carcass_depth, carcass_height,
                          kick_height, min(45.0, depth * 0.08))
    box = _shared.doors(box, width, carcass_height, door_count, kick_height)
    box = sh.place(box, 0, overhang, 0)

    top = sh.rounded_box(width, depth, worktop, radius=6)
    top = sh.roll_top(top, min(worktop * 0.4, 12.0), axis="x")
    top = sh.place(top, 0, 0, carcass_height)

    pulls = _shared.pulls(width, carcass_height, door_count, kick_height, overhang)
    return sh.fuse_all([box, top] + pulls)
