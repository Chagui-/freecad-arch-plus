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
# doorsplus_gui.py, which already solves picked-face orientation and base-Z
# snapping. A part's own origin is normalised at build time
# (partslib_geometry._Context.normalize), so nothing here needs to know about
# a vendor asset's arbitrary origin.

HOSTS = ("wall", "floor", "ceiling", "free")
DEFAULT_HOST = "free"

# Which way the manifest's offset runs from the reference surface.
_OFFSET_SIGN = {"wall": 1.0, "floor": 1.0, "ceiling": -1.0, "free": 0.0}

# Hosts that snap to the host object's base Z rather than the picked point.
_SNAPS_TO_HOST_BASE = ("wall",)


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


def partPlacement(point, baseFace, host, offset):
    """Build the placement for a picked point.

    `baseFace` is a (object, faceIndex) tuple as handed back by the Snapper, or
    None when the user clicked empty space."""
    import FreeCAD
    import DraftGeomUtils
    import WorkingPlane

    wp = WorkingPlane.get_working_plane()
    if baseFace is not None:
        face = baseFace[0].Shape.Faces[baseFace[1]]
        placement = DraftGeomUtils.placement_from_face(face, vec_z=wp.axis)
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
        placement = FreeCAD.Placement()
        placement.Rotation = FreeCAD.Rotation(wp.u, wp.v, wp.axis, "ZYX")

    z = point.z
    if host in _SNAPS_TO_HOST_BASE and baseFace is not None:
        try:
            z = baseFace[0].Shape.BoundBox.ZMin
        except Exception:
            z = point.z
    z += offset_sign(host) * float(offset)

    placement.Base = FreeCAD.Vector(point.x, point.y, z)
    return placement
