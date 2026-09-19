# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh

# The freezer's share of the front, taken off the bottom. The door split is
# the only thing a fridge-freezer changes about the box it stands in.
_FREEZER_SHARE = 0.3
# The gap two stacked doors leave between them, the height of the seam
# `_shared.doors()` cuts between columns.
_DOOR_SEAM = 4.0
# Handle hardware: bar radius, how far the pull's centre sits from the
# opening edge, and the longest pull that still looks like a fridge handle.
_HANDLE_RADIUS = 8.0
_HANDLE_INSET = 45.0
_HANDLE_MAX = 240.0


def _row_edges(height, kick_height, configuration):
    """The door row boundaries, top down, from the unit top to the kick."""
    shares = ([1.0 - _FREEZER_SHARE, _FREEZER_SHARE]
              if configuration == "fridge-freezer" else [1.0])
    edges = [height]
    for share in shares:
        edges.append(edges[-1] - (height - kick_height) * share)
    return edges


def build(params, assets, ctx):
    """A freestanding fridge or fridge-freezer: a tall insulated box with
    recessed door fronts, bar handles and a compressor plinth.

    Params: Width, Depth, Height (mm), Configuration (Choice of "fridge" or
    "fridge-freezer").

    The configuration changes the door split and never a dimension: both
    configurations are the same box, so a width typed to fit a gap survives
    switching between them."""
    width = float(params.get("Width", 600))
    depth = float(params.get("Depth", 650))
    height = float(params.get("Height", 1850))
    configuration = params.get("Configuration") or "fridge"
    if configuration not in ("fridge", "fridge-freezer"):
        configuration = "fridge"

    # The handles are the frontmost thing on the part, so the cabinet is
    # built one handle radius back from the origin and shifted forward at the
    # end: the advertised Depth then includes the handles, which is how an
    # appliance is measured.
    body_depth = max(depth - _HANDLE_RADIUS, 1.0)
    kick_height = min(80.0, height * 0.05)
    margin = min(35.0, width * 0.06)

    box = sh.rounded_box(width, body_depth, height, radius=10)
    box = sh.toe_kick(box, width, body_depth, kick_height=kick_height,
                      kick_depth=min(40.0, body_depth * 0.07))

    edges = _row_edges(height, kick_height, configuration)
    cuts = []
    pulls = []
    for index in range(len(edges) - 1):
        top, bottom = edges[index], edges[index + 1]
        low = bottom + (_DOOR_SEAM / 2.0 if bottom > kick_height else margin)
        high = top - (_DOOR_SEAM / 2.0 if top < height else margin)
        panel_height = high - low
        if panel_height <= 0:
            continue
        if bottom > kick_height:
            cuts.append((margin, -1.0, bottom - _DOOR_SEAM / 2.0,
                         width - 2 * margin, 10.0, _DOOR_SEAM))
        cuts.extend(sh.panel_reveal_boxes(
            margin, low, width - 2 * margin, panel_height,
            groove=6.0, depth=10.0))
        # One vertical pull per door on the opening edge, sized to its own
        # door so the freezer's short one does not look borrowed.
        length = min(_HANDLE_MAX, panel_height * 0.3)
        pulls.append(sh.place(
            sh.bar(length, _HANDLE_RADIUS, along="z"),
            width - min(_HANDLE_INSET, width * 0.08), 0.0,
            low + (panel_height - length) / 2.0))

    box = sh.cut_boxes(box, cuts)
    return sh.place(sh.fuse_all([box] + pulls), 0, _HANDLE_RADIUS, 0)
