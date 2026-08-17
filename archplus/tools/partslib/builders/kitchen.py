# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Kitchen builders - pure generation, no assets.
#
# Kitchen units are the most repetitive family in the library: nearly every
# one is a carcass with a toe kick, doors carrying a panel reveal, and a
# handle. `_carcass()` below does that once, and each public builder differs
# only in what sits on top (a worktop, nothing) and what is cut into the
# front (doors, an oven, a drawer bank).

from archplus.tools.partslib import shapes as sh


def _carcass(width, depth, height, kick_height, kick_depth, radius=8.0):
    """A cabinet box standing on a recessed plinth."""
    box = sh.rounded_box(width, depth, height, radius=radius)
    return sh.toe_kick(box, width, depth,
                       kick_height=kick_height, kick_depth=kick_depth,
                       margin=min(20.0, width * 0.04))


def _doors(shape, width, height, door_count, base_z, margin=None,
           groove=6.0, seam=4.0):
    """Cut door seams and a panel reveal into a carcass front."""
    if door_count < 1:
        return shape
    door_width = width / door_count
    if margin is None:
        margin = min(40.0, door_width * 0.12)
    # Seams between doors plus the reveal around each, subtracted together:
    # an 800mm two-door unit is nine boxes and one boolean.
    boxes = [
        (i * door_width - seam / 2.0, -1.0, base_z,
         seam, 8.0, height - base_z)
        for i in range(1, door_count)
    ]
    for i in range(door_count):
        boxes.extend(sh.panel_reveal_boxes(
            i * door_width + margin, base_z + margin,
            door_width - 2 * margin, height - base_z - 2 * margin,
            groove=groove, depth=8.0))
    return sh.cut_boxes(shape, boxes)


def _pulls(width, height, door_count, base_z, y, vertical=True):
    """One handle per door, centred on the door face so it adds no depth."""
    pulls = []
    if door_count < 1:
        return pulls
    door_width = width / door_count
    length = (height - base_z) * 0.22 if vertical else door_width * 0.35
    for i in range(door_count):
        # Handles sit toward the opening edge: outer doors open outward,
        # so their handles mirror about the middle of the run.
        inset = 40.0
        x = (i * door_width + door_width - inset if i < door_count / 2.0
             else i * door_width + inset)
        if vertical:
            pulls.append(sh.place(sh.bar(length, 7.0, along="z"), x, y,
                                  base_z + (height - base_z - length) / 2.0))
        else:
            pulls.append(sh.place(sh.bar(length, 7.0, along="x"),
                                  i * door_width + (door_width - length) / 2.0,
                                  y, height - 60.0))
    return pulls
