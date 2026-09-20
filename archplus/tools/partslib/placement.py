# SPDX-License-Identifier: LGPL-2.1-or-later
#
# PartsLib placement - where a part lands when you click.
#
# All four hosts run through ONE rule rather than four code paths: placement
# always orients from the picked face, and `host` decides only which way the
# offset runs and whether to snap to the host's base. That deliberately avoids
# raycasting to find the slab above, which is where host-aware placement
# usually turns expensive.
#
# The orientation half is a generalisation of _doorPlacement in
# doors/gui.py, which already solves picked-face orientation and base-Z
# snapping. A part's own origin is normalised at build time
# (partslib_geometry._Context.normalize), so nothing here needs to know about
# a vendor asset's arbitrary origin.

HOSTS = ("wall", "floor", "ceiling", "free")
DEFAULT_HOST = "free"

# Which way the manifest's offset runs from the reference surface.
_OFFSET_SIGN = {"wall": 1.0, "floor": 1.0, "ceiling": -1.0, "free": 0.0}

# Hosts that snap to the host object's base Z rather than the picked point.
_SNAPS_TO_HOST_BASE = ("wall",)

# How vertical a face has to be to count as a wall rather than a floor or a
# ceiling. A sloped face stays on the old path: nothing in the catalogue is
# placed on one, and tilting a part to a slope is the behaviour it had.
_VERTICAL = 0.5


def host_of(resolved):
    """The declared host, defaulting to 'free' for anything unrecognised."""
    host = (resolved.get("placement") or {}).get("host", DEFAULT_HOST)
    return host if host in HOSTS else DEFAULT_HOST


def offset_of(resolved):
    """Offset in mm from the reference surface."""
    try:
        return float((resolved.get("placement") or {}).get("offset", 0.0))
    except (TypeError, ValueError):
        return 0.0


def offset_sign(host):
    """+1 offsets up, -1 offsets down, 0 applies no offset."""
    return _OFFSET_SIGN.get(host, 0.0)


def offset_to_of(resolved):
    """Which part of the part the offset measures to: "bottom" (the default,
    its origin) or "top".

    A wall cabinet hangs from its underside, so its offset is to the bottom.
    A curtain's rail is what a person measures, and the fabric hangs below
    it, so its offset is to the TOP - without this the number in the
    manifest would mean the hem, which is not what its own description
    says."""
    value = (resolved.get("placement") or {}).get("offsetTo", "bottom")
    return "top" if value == "top" else "bottom"


def partPlacement(point, baseFace, host, offset, size=None, offset_to="bottom"):
    """Build the placement for a picked point.

    `baseFace` is a (object, faceIndex) tuple as handed back by the Snapper, or
    None when the user clicked empty space. `size` is the built shape's
    measured (width, depth, height) in mm, or None when the caller has not
    built one - it is what puts the part's CONTACT face on the picked face
    rather than its origin.

    A part's contact face is the one that meets the surface it is placed
    against: its bottom for a floor, its BACK for a wall, its top for a
    ceiling. A part is built upright with its bottom at the origin, so the
    floor case already worked and needed nothing; the wall case did not,
    because DraftGeomUtils.placement_from_face maps the part's local Z onto
    the face normal - right for a floor (normal +Z, part upright) and wrong
    for a wall, whose horizontal normal laid the part on its back with its
    width running through the wall's thickness.

    On a vertical face the part therefore only YAWS, and moves out along the
    normal by its own depth so its back plane lands where the user clicked.
    The offset still runs up from the host's base, so the picked point's Z is
    not what sets the height.

    `offset_to` is which end of the part that offset measures to - see
    offset_to_of."""
    import math

    import FreeCAD
    import DraftGeomUtils
    import WorkingPlane

    wp = WorkingPlane.get_working_plane()
    depth = 0.0
    height = 0.0
    if size is not None:
        try:
            depth = float(size[1])
            height = float(size[2])
        except (IndexError, TypeError, ValueError):
            depth = 0.0
            height = 0.0

    face = None
    if baseFace is not None:
        try:
            face = baseFace[0].Shape.Faces[baseFace[1]]
        except Exception:
            face = None

    shift = FreeCAD.Vector(0.0, 0.0, 0.0)
    placement = FreeCAD.Placement()
    normal = None
    if face is not None:
        try:
            normal = face.normalAt(0, 0)
        except Exception:
            normal = None

    if normal is not None and abs(normal.z) < _VERTICAL:
        # A wall-like face: stay upright, face the surface with the part's
        # back, and stand off it by the part's own depth.
        yaw = math.degrees(math.atan2(normal.x, -normal.y))
        placement.Rotation = FreeCAD.Rotation(
            FreeCAD.Vector(0.0, 0.0, 1.0), yaw)
        shift = FreeCAD.Vector(normal.x * depth, normal.y * depth, 0.0)
    elif face is not None:
        placement.Rotation = DraftGeomUtils.placement_from_face(
            face, vec_z=wp.axis).Rotation
        if host == "ceiling":
            # Hanging under a ceiling: upright, with the part's TOP on the
            # picked face, and the offset then running down from it.
            placement.Rotation = FreeCAD.Rotation(wp.u, wp.v, wp.axis, "ZYX")
            shift = FreeCAD.Vector(0.0, 0.0, -height)
    else:
        # Align the part's own axes to the working plane's, and nothing
        # more - the same rotation WorkingPlane.get_placement() builds for
        # itself, and the identity on the default XY plane.
        #
        # This deliberately does NOT copy _doorPlacement's
        # Rotation(wp.u, wp.axis, -wp.v, "XZY"). That maps the object's Y
        # onto world Z, which is right for a door: a door is a flat sketch
        # drawn in XY that has to be stood upright in a wall. A library
        # part is a solid already built upright - X wide, Y deep, Z tall -
        # so standing it up again tips it onto its face. It laid every part
        # in the library on its back.
        placement.Rotation = FreeCAD.Rotation(wp.u, wp.v, wp.axis, "ZYX")

    z = point.z
    if host in _SNAPS_TO_HOST_BASE and baseFace is not None:
        try:
            z = baseFace[0].Shape.BoundBox.ZMin
        except Exception:
            z = point.z
    z += offset_sign(host) * float(offset)
    if offset_to == "top":
        # The offset measures to the part's top, so the part hangs below it.
        z -= height

    placement.Base = FreeCAD.Vector(point.x + shift.x, point.y + shift.y,
                                    z + shift.z)
    return placement
