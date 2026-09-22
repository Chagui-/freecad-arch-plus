# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Role-colour checks for the parts library. Run inside a FreeCAD GUI session.
#
# A part is one fused solid, so its pieces are invisible in the shape: what
# says "this face is the door, that one the handle" is the role its builder
# gave the piece the face came from, and what the user sees is the colour
# palette.py paints that role with. Both halves are checked here, because
# either can break silently - a builder that was never tagged, or a role that
# is not in the palette.
#
# The cap is the user's own rule: at most three colours on any one part, two
# being the common case. That is asserted per part, and the distribution is
# reported, because "two is a big win and more than three is too many" is a
# design rule that one boolean cannot hold.
#
# The last checks are the ones that matter to a user: a placed part is
# painted face by face with the colour of its role - which is the appearance
# the 3D view draws, not merely a role list sitting on the object - and a
# Material set on the part beats the palette.

from archplus.freecad_tests import _harness as h

import FreeCAD

from archplus.tools.partslib import geometry as pgeo
from archplus.tools.partslib import index as pidx
from archplus.tools.partslib import manifest as pman
from archplus.tools.partslib import object as pobj
from archplus.tools.partslib import palette as pal


def _colours_of(roles):
    """(RGB, Transparency) per role - the palette is RGBA, and FreeCAD stores
    the inverse of alpha, so a role's colour and its see-through-ness are
    compared together."""
    seen = set()
    for role in roles:
        red, green, blue, alpha = pal.colour_for(role)
        seen.add(((round(red, 3), round(green, 3), round(blue, 3)),
                  round(1.0 - alpha, 3)))
    return sorted(seen)


def _rgb(colour):
    """The RGB of a palette entry, rounded the way _painted rounds it."""
    return tuple(round(channel, 3) for channel in colour[:3])


def _painted(obj):
    """(RGB, Transparency) per painted face: what the 3D view actually draws."""
    return sorted({((round(material.DiffuseColor[0], 3),
                     round(material.DiffuseColor[1], 3),
                     round(material.DiffuseColor[2], 3)),
                    round(material.Transparency, 3))
                   for material in obj.ViewObject.ShapeAppearance})


def run():
    doc = h.fresh_doc("ArchPlusPartColours")
    index = pidx.scan(pgeo.LIBRARY_DIR)

    distribution = {}
    checked = 0
    for entry in index["entries"]:
        if not pgeo.has_local_builder(entry["dir"]):
            continue
        manifest = pman.load_manifest(entry["path"])
        shape, roles = pgeo.build_shape_and_roles(manifest, entry["dir"])
        roles = list(roles or [])
        unknown = sorted(set(roles) - set(pal.ROLES))
        colours = pal.colours_used(roles)
        h.check("%s: a role per face, all from the palette, within three colours"
                % entry["id"],
                len(roles) == len(shape.Faces) and not unknown
                and len(colours) <= 3,
                "%d faces, %d roles, %d colours%s"
                % (len(shape.Faces), len(roles), len(colours),
                   ("; unknown " + ",".join(unknown)) if unknown else ""))
        distribution[len(colours)] = distribution.get(len(colours), 0) + 1
        checked += 1

    h.check("the whole shipped library declares roles",
            checked >= 30, "%d parts with a builder" % checked)
    h.check("no part uses more than three colours",
            not [count for count in distribution if count > 3],
            "parts by colour count: %s" % sorted(distribution.items()))
    h.check("most parts stay at two colours",
            distribution.get(2, 0) >= checked // 2,
            "parts by colour count: %s" % sorted(distribution.items()))
    h.check("the library uses wood and grey alike",
            len({pal.ROLE_COLOUR[role] for role in pal.ROLES}) >= 5,
            "palette: %s" % sorted(set(pal.ROLE_COLOUR.values())))

    # What a user actually sees, on a placed part: one material per face, and
    # the colours painted are exactly the colours its roles call for.
    found = pobj.resolveEntry("basic/base-cabinet")
    h.check("the base cabinet is in the library", found is not None)
    if found is None:
        return h.failures()
    entry, facets = found
    obj = pobj.makePart(entry, facets)
    doc.recompute()

    roles = obj.ViewObject.Proxy.partRoles()
    appearance = list(obj.ViewObject.ShapeAppearance)
    h.check("a placed part carries a role per face",
            len(roles) == len(obj.Shape.Faces) and bool(roles),
            "%d faces, %d roles" % (len(obj.Shape.Faces), len(roles)))
    h.check("it is painted one material per face",
            len(appearance) == len(obj.Shape.Faces),
            "%d faces, %d materials" % (len(obj.Shape.Faces), len(appearance)))
    h.check("the colours painted are the colours its roles call for",
            _painted(obj) == _colours_of(roles),
            "painted %s, roles %s" % (_painted(obj), _colours_of(roles)))
    h.check("the base cabinet reads as three materials",
            len(_painted(obj)) == 3, "%d colours" % len(_painted(obj)))
    h.check("its worktop is wood, not grey",
            _rgb(pal.colour_for("top")) in [colour for colour, _t in _painted(obj)],
            "painted %s" % _painted(obj))

    # Glazing is the one role that is not solid, and it has to be see-through
    # on a real part, not merely in the palette.
    screen = pobj.resolveEntry("basic/shower-screen")
    h.check("the shower screen is in the library", screen is not None)
    if screen is not None:
        pane = pobj.makePart(screen[0], screen[1])
        doc.recompute()
        pane_roles = pane.ViewObject.Proxy.partRoles()
        glass_faces = [index for index, role in enumerate(pane_roles)
                       if role == "glass"]
        frame_faces = [index for index, role in enumerate(pane_roles)
                       if role == "fitting"]
        appearance = pane.ViewObject.ShapeAppearance
        h.check("the shower screen's pane is glazed and see-through",
                bool(glass_faces) and bool(frame_faces)
                and all(appearance[i].Transparency > 0.5 for i in glass_faces)
                and all(appearance[i].Transparency == 0.0 for i in frame_faces)
                and all(appearance[i].DiffuseColor[2]
                        > appearance[i].DiffuseColor[0] for i in glass_faces),
                "%d glass faces at transparency %s, %d frame faces at %s"
                % (len(glass_faces),
                   sorted({appearance[i].Transparency for i in glass_faces}),
                   len(frame_faces),
                   sorted({appearance[i].Transparency for i in frame_faces})))

    # A Material set on the part wins, and visibly so: a per-face appearance
    # would otherwise override the whole-shape colour FreeCAD paints a
    # Material with, leaving the part in the palette's colours.
    material = doc.addObject("App::MaterialObjectPython", "PartMaterial")
    material.Material = {"Name": "Steel",
                         "DiffuseColor": "(0.5, 0.5, 0.6)",
                         "Transparency": "0"}
    obj.Material = material
    doc.recompute()
    obj.ViewObject.Proxy.colorize(obj)
    h.check("a Material on the part is painted rather than the palette",
            _painted(obj) == [((0.5, 0.5, 0.6), 0.0)],
            "painted %s" % _painted(obj))
    return h.failures()
