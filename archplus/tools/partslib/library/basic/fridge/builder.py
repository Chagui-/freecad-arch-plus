# SPDX-License-Identifier: LGPL-2.1-or-later
#
# A freestanding fridge. Reading as a fridge and not as a tall cabinet is a
# massing problem, not a detailing one, and it comes down to two things no
# cabinet in this library has: its front is an APPLIED door slab standing
# proud of the body, with the body's own front face showing as a frame round
# it, and its handles are long grab bars standing off the door on posts
# rather than pulls lying on it.

from archplus.tools.partslib import shapes as sh

# The freezer's share of the front, taken off the bottom. The door split is
# the only thing a fridge-freezer changes about the box it stands in.
_FREEZER_SHARE = 0.3
# The gasket: the body's front face stays visible this wide all round each
# door slab. A door cut flush to the cabinet's edges is a cabinet door.
_GASKET = 12.0
_DOOR_THICKNESS = 60.0
_DOOR_SEAM = 6.0
# Handle hardware: a flat 42mm grab bar standing 35mm off the door face on
# two posts. Flat, because the bar is what says "fridge" from the front and a
# 30mm cylinder is a bare line at thumbnail scale.
_HANDLE_WIDTH = 42.0
_HANDLE_DEPTH = 26.0
_HANDLE_STANDOFF = 35.0
_POST_RADIUS = 8.0
_HANDLE_EDGE_INSET = 55.0
# A fridge door's handle is a long grab, not a cabinet pull - this share of
# its own door, capped so the freezer's does not run the whole height.
_HANDLE_SHARE = 0.55
_HANDLE_MAX = 700.0
# The plinth: a full-width recess, the vent gap a fridge stands on rather
# than a cabinet's inset toe kick.
_KICK_HEIGHT = 45.0
_KICK_DEPTH = 30.0
# The frontmost point of the part is the bar's own face, so the door plane
# sits the bar's depth and its standoff back from the origin, and everything
# else behind that. The advertised Depth therefore includes the handles,
# which is how an appliance is measured.
_DOOR_PLANE = _HANDLE_DEPTH + _HANDLE_STANDOFF


def _row_edges(height, kick_height, configuration):
    """The door row boundaries, top down, from the door head to the plinth."""
    shares = ([1.0 - _FREEZER_SHARE, _FREEZER_SHARE]
              if configuration == "fridge-freezer" else [1.0])
    top = height - _GASKET
    edges = [top]
    for share in shares:
        edges.append(edges[-1] - (top - kick_height) * share)
    return edges


def _handle(door_width, slab_height, slab_bottom):
    """One door's grab bar: a flat bar on two posts, standing off the door
    face on the opening side so the gap between bar and door reads."""
    length = min(_HANDLE_MAX, slab_height * _HANDLE_SHARE)
    if length <= 0:
        return []
    # On the opening edge: the slab's own edge, in from it by the inset.
    x = _GASKET + door_width - _HANDLE_EDGE_INSET
    bottom = slab_bottom + (slab_height - length) / 2.0
    parts = [sh.place(sh.rounded_box(_HANDLE_WIDTH, _HANDLE_DEPTH, length,
                                     radius=6),
                      x - _HANDLE_WIDTH / 2.0, 0.0, bottom)]
    # The posts run from the bar's back face to a millimetre inside the slab,
    # so the fuse has material to join rather than a coincident face.
    post_length = _DOOR_PLANE - _HANDLE_DEPTH + 1.0
    for fraction in (0.12, 0.88):
        parts.append(sh.place(sh.bar(post_length, _POST_RADIUS, along="y"),
                              x, _HANDLE_DEPTH, bottom + length * fraction))
    return parts


def build(params, assets, ctx):
    """A freestanding fridge or fridge-freezer: an insulated body with an
    applied door slab proud of its front, on standoff grab handles.

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

    body_depth = max(depth - _DOOR_PLANE - _DOOR_THICKNESS, 1.0)
    body = sh.rounded_box(width, body_depth, height, radius=12)
    body = sh.place(body, 0, _DOOR_PLANE + _DOOR_THICKNESS, 0)
    body = sh.cut_boxes(body, [
        (0.0, _DOOR_PLANE + _DOOR_THICKNESS - 1.0, -1.0,
         width, _KICK_DEPTH, _KICK_HEIGHT)])

    door_width = max(width - 2.0 * _GASKET, 1.0)
    edges = _row_edges(height, _KICK_HEIGHT, configuration)
    doors = []
    handles = []
    for index in range(len(edges) - 1):
        top, bottom = edges[index], edges[index + 1]
        low = bottom + (_DOOR_SEAM / 2.0 if bottom > _KICK_HEIGHT else 0.0)
        high = top - (_DOOR_SEAM / 2.0 if top < height - _GASKET else 0.0)
        slab_height = high - low
        if slab_height <= 0:
            continue
        # A millimetre deeper than it shows: the slab's back face sits just
        # inside the body rather than on it, which is the difference between
        # one part and a body with two doors floating in front of it.
        doors.append(sh.place(
            sh.rounded_box(door_width, _DOOR_THICKNESS + 1.0, slab_height,
                           radius=10),
            _GASKET, _DOOR_PLANE, low))
        handles.extend(_handle(door_width, slab_height, low))

    return sh.fuse_all([body] + doors + handles)
