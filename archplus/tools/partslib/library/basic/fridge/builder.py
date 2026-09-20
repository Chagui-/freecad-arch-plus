# SPDX-License-Identifier: LGPL-2.1-or-later
#
# A freestanding fridge-freezer. Reading as an appliance and not as a tall
# cabinet is a massing problem, not a detailing one, and it comes down to two
# things no cabinet in this library has: its front is an APPLIED door slab
# standing proud of the body, with the body's own front face showing as a
# frame round it, and its handles are long grab bars standing off the door on
# posts rather than pulls lying on it.

from archplus.tools.partslib import shapes as sh

# Every fridge here has a freezer - that is what a fridge IS, at this size -
# so the configuration is the DOOR ARRANGEMENT and never the appliance: the
# freezer's share of the front, taken off the bottom, is not a choice.
_FREEZER_SHARE = 0.3
# The gasket: the body's front face stays visible this wide all round each
# door slab. A door cut flush to the cabinet's edges is a cabinet door.
_GASKET = 12.0
_DOOR_THICKNESS = 60.0
# The gap between two doors: the row split, and the seam a door pair meets at.
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

# The door arrangements on offer. "single" is one door per compartment - the
# bottom-freezer layout - and "double" splits the fridge door into a pair
# that meets in the middle, which is what "double door" means on an
# appliance this size.
CONFIGURATIONS = ("single", "double")

# The size each arrangement ships at, straight from the catalogues: a
# single-door fridge-freezer is 600 wide, a double-door one 750, and both are
# 650 front to back. That is the difference a buyer would otherwise have to
# look up, which is what makes the arrangement a driver for Width and Depth
# rather than a decoration on a fixed box.
_DEFAULT_SIZES = {
    "single": (600.0, 650.0),
    "double": (750.0, 650.0),
}


def _default_size(configuration):
    """(width, depth) in mm for a fridge with this door arrangement."""
    return _DEFAULT_SIZES.get(configuration, _DEFAULT_SIZES["single"])


def _row_edges(height, kick_height):
    """The door row boundaries, top down: the fridge compartment and the
    freezer under it. There is no arrangement without both."""
    top = height - _GASKET
    fridge_height = (top - kick_height) * (1.0 - _FREEZER_SHARE)
    return [top, top - fridge_height, kick_height]


def _row_columns(configuration, row):
    """How many doors a row carries: the freezer is always one, the fridge
    is one or a facing pair."""
    if row == 0 and configuration == "double":
        return 2
    return 1


def _handle(door_x, door_width, slab_height, slab_bottom, side=1):
    """One door's grab bar: a flat bar on two posts, standing off the door
    face on the opening edge so the gap between bar and door reads.

    `side` is +1 for the door's right edge and -1 for its left, which is what
    makes a pair's handles face each other across the seam they meet at."""
    length = min(_HANDLE_MAX, slab_height * _HANDLE_SHARE)
    if length <= 0:
        return []
    if side > 0:
        x = door_x + door_width - _HANDLE_EDGE_INSET
    else:
        x = door_x + _HANDLE_EDGE_INSET
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
    """A freestanding fridge-freezer: an insulated body with applied door
    slabs proud of its front, on standoff grab handles.

    Params: Configuration (Choice of "single" or "double"), Width and Depth
    (both derived from the arrangement unless pinned; editing the
    arrangement discards pinned sizes - a double-door fridge at the
    single-door width would be two doors the width of one), Height (mm).

    A fridge always has a freezer here, so the configuration is the door
    arrangement and never the appliance - but it IS the size, because the
    two arrangements are different appliances: a pair of doors needs the
    wider box."""
    arrangement = params.get("Configuration") or "single"
    if arrangement not in CONFIGURATIONS:
        arrangement = "single"
    # The arrangement decides the size the same way the hob's burner count
    # decides the hob's: it is what the user knows, and 600 vs 750 wide is
    # what they would otherwise have to look up. A pinned value wins.
    width = params.get("Width")
    if width is None:
        width = _default_size(arrangement)[0]
    width = float(width)
    depth = params.get("Depth")
    if depth is None:
        depth = _default_size(arrangement)[1]
    depth = float(depth)
    height = float(params.get("Height", 1850))

    body_depth = max(depth - _DOOR_PLANE - _DOOR_THICKNESS, 1.0)
    body = sh.rounded_box(width, body_depth, height, radius=12)
    body = sh.place(body, 0, _DOOR_PLANE + _DOOR_THICKNESS, 0)
    body = sh.cut_boxes(body, [
        (0.0, _DOOR_PLANE + _DOOR_THICKNESS - 1.0, -1.0,
         width, _KICK_DEPTH, _KICK_HEIGHT)])

    front_width = max(width - 2.0 * _GASKET, 1.0)
    edges = _row_edges(height, _KICK_HEIGHT)
    doors = []
    handles = []
    for row in range(len(edges) - 1):
        top, bottom = edges[row], edges[row + 1]
        low = bottom + (_DOOR_SEAM / 2.0 if bottom > _KICK_HEIGHT else 0.0)
        high = top - (_DOOR_SEAM / 2.0 if top < height - _GASKET else 0.0)
        slab_height = high - low
        if slab_height <= 0:
            continue
        columns = _row_columns(arrangement, row)
        column_width = (front_width - _DOOR_SEAM * (columns - 1)) / columns
        for column in range(columns):
            door_x = _GASKET + column * (column_width + _DOOR_SEAM)
            # A millimetre deeper than it shows: the slab's back face sits
            # just inside the body rather than on it, which is the difference
            # between one part and a body with doors floating in front of it.
            doors.append(sh.place(
                sh.rounded_box(column_width, _DOOR_THICKNESS + 1.0,
                               slab_height, radius=10),
                door_x, _DOOR_PLANE, low))
            # A pair's handles flank the seam they meet at: the left door's
            # on its right edge, the right door's on its left.
            side = -1 if (columns > 1 and column == columns - 1) else 1
            handles.extend(_handle(door_x, column_width, slab_height, low,
                                   side))

    return sh.fuse_all([body] + doors + handles)
