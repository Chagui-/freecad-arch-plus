# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Offscreen rendering and builder resolution: Parts I and J of
# docs/PARTS-LIBRARY-VERIFICATION.md (the former console snippets, now
# part of the automated pass).

import os
import tempfile

from archplus.freecad_tests import _harness as h

import FreeCAD
import Part

from archplus.tools.partslib import geometry as partslib_geometry
from archplus.tools.partslib import manifest as partslib_manifest
from archplus.tools.partslib import object as partslib_object
from archplus.tools.partslib import thumbs as partslib_thumbs

# A circle fills pi/4 of its own bounding box; a square fills all of it, and
# a square with eased corners fills 0.98 of it. Anything that reads as round
# lands on pi/4 to a couple of percent.
_CIRCLE_FILL = 3.14159265358979 / 4.0

_LIBRARY_DIR = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))


def run():
    # --- I1: the offscreen renderer writes a shaded box on white.
    out_path = os.path.join(tempfile.gettempdir(), "archplus_verify_thumb.png")
    if os.path.exists(out_path):
        os.remove(out_path)
    ok = partslib_thumbs.render_shape(Part.makeBox(360, 540, 400), out_path)
    h.check("I1 offscreen render succeeds and writes the file",
            ok and os.path.exists(out_path)
            and os.path.getsize(out_path) > 0,
            detail="rendered=%r bytes=%d"
            % (ok, os.path.getsize(out_path)
               if os.path.exists(out_path) else 0))

    # --- I2: a library part's thumbnail carries the palette.
    #
    # SoOffscreenRenderer paints ONE material per shape and a bare shape
    # carries no per-face appearance, so a part used to render as a single
    # grey mass however its faces were tagged. "More than one colour" does
    # not discriminate, because that grey mass is shaded - lit faces, dark
    # faces. HUE does: the palette's wood is brown and its glazing blue, so
    # a coloured render has strongly saturated pixels where a neutral one
    # has none. The measure is relative to the pixel's own brightness, so a
    # face in shadow counts the same as one in the light.
    entry = partslib_object.resolveEntry("basic/base-cabinet")[0]
    manifest = partslib_manifest.load_manifest(entry["path"])
    part_shape, part_roles = partslib_geometry.build_shape_and_roles(
        manifest, entry["dir"])
    part_path = os.path.join(tempfile.gettempdir(),
                             "archplus_verify_part_colours.png")
    if os.path.exists(part_path):
        os.remove(part_path)
    drawn = partslib_thumbs.render_shape(part_shape, part_path,
                                         roles=part_roles)
    from PySide import QtGui

    image = QtGui.QImage(part_path) if drawn else QtGui.QImage()
    h.check("I2 a part renders with its roles",
            drawn and not image.isNull(),
            detail="rendered=%r null=%r" % (drawn, image.isNull()))

    sampled = tinted = 0
    if not image.isNull():
        for y in range(0, image.height(), 2):
            for x in range(0, image.width(), 2):
                colour = image.pixelColor(x, y)
                channels = (colour.redF(), colour.greenF(), colour.blueF())
                sampled += 1
                brightest = max(channels)
                if brightest > 0.05 and \
                        (brightest - min(channels)) / brightest >= 0.25:
                    tinted += 1
    h.check("I2 the part is drawn in the palette, not one grey mass",
            sampled and tinted >= sampled * 0.05,
            detail="tinted %d of %d sampled pixels" % (tinted, sampled))

    # --- J1/J2/J3: builder resolution and measurement.
    part_dir = os.path.join(_LIBRARY_DIR, "archplus", "tools", "partslib",
                            "library", "basic", "nightstand")
    resolved = {"geometry": {},
                "params": {"Width": {"default": 400},
                           "Depth": {"default": 350},
                           "Height": {"default": 500}}}
    builder = partslib_geometry.select_builder(resolved, part_dir)
    module = getattr(builder, "__module__", "")
    h.check("J1 the nightstand's own builder is resolved",
            module == "archplus.tools.partslib.library.basic.nightstand.builder",
            detail="module=%r" % module)

    doc = h.fresh_doc()
    before = len(doc.Objects)
    shape = partslib_geometry.build_shape(resolved, part_dir)
    measured = partslib_geometry.measure(shape)
    # The advertised dimensions are the contract, not bit-exact floats: a
    # bounding box comes back from the kernel with noise in its last digits
    # (400.0000000000001 for a 400mm part), so any toleranced comparison has
    # to be a micron rather than an equality.
    advertised = {"Width": 400.0, "Depth": 350.0, "Height": 500.0}
    h.check("J2 the built shape measures what the manifest advertises",
            set(measured) == set(advertised)
            and all(abs(measured[k] - advertised[k]) < 1e-6
                    for k in advertised),
            detail="measured=%r" % (measured,))
    h.check("J3 building a shape adds nothing to the document",
            len(doc.Objects) == before,
            detail="objects=%d" % len(doc.Objects))

    # --- J4: the pedal bin is round, and its manifest says so.
    #
    # A round plan is one dimension, so the bin's Depth is derived from its
    # Width and the two must measure the same. Roundness is read off plan
    # sections rather than eyeballed: a circle fills pi/4 of its bounding
    # box at any height, a box fills all of it, so the ratio catches a body
    # that has quietly gone back to being square. The body tapers from the
    # lid to the floor, the lid overhangs the body's shoulder, and nothing
    # reaches outside the advertised footprint.
    entry = partslib_object.resolveEntry("basic/waste-bin")[0]
    manifest = partslib_manifest.load_manifest(entry["path"])
    bin_shape = partslib_geometry.build_shape(manifest, entry["dir"])
    dims = partslib_geometry.measure(bin_shape)
    width, depth, height = dims["Width"], dims["Depth"], dims["Height"]

    def plan(z):
        """(fill ratio, bounding box) of the shape's plan at height `z`."""
        # slice() hands back a list of wires, one per closed loop in the
        # section, so each has to become a face before it has an area.
        faces = [Part.Face(wire)
                 for wire in bin_shape.slice(FreeCAD.Vector(0, 0, 1), z)]
        box = Part.Compound(faces).BoundBox
        area = sum(face.Area for face in faces)
        return area / (box.XLength * box.YLength), box

    body_fill, body_box = plan(height * 0.4)
    lid_fill, lid_box = plan(height * 0.98)

    def solid(point):
        return bin_shape.isInside(FreeCAD.Vector(*point), 1e-6, False)

    rim = (width / 2.0 + width * 0.47, depth / 2.0, height * 0.98)
    shoulder = (width / 2.0 + width * 0.47, depth / 2.0, height * 0.70)
    corner = (width - 2.0, 2.0, height * 0.40)
    h.check("J4 the bin's plan is a circle at the body and at the lid",
            abs(width - depth) < 1e-6
            and abs(body_fill - _CIRCLE_FILL) < 0.02
            and abs(lid_fill - _CIRCLE_FILL) < 0.02,
            detail="plan=%.1fx%.1f fill=%.3f/%.3f (circle=%.3f)"
            % (width, depth, body_fill, lid_fill, _CIRCLE_FILL))
    h.check("J4 the body tapers from the lid down to the floor",
            body_box.XLength < lid_box.XLength - 1.0,
            detail="body=%.1f lid=%.1f" % (body_box.XLength, lid_box.XLength))
    h.check("J4 the lid overhangs the shoulder, inside the footprint",
            solid(rim) and not solid(shoulder) and not solid(corner),
            detail="rim=%s shoulder=%s corner=%s"
            % (solid(rim), solid(shoulder), solid(corner)))

    # --- J5: the shower base's curved corner is a real arc, and the tray
    # around it is still the tray the catalogue advertises.
    #
    # The corner is CUT here rather than filleted, and like every easing in
    # shapes.py the cut degrades to a sharp square corner rather than
    # aborting the build - so "curved" can quietly come back square, and
    # the recess can quietly break through the arc and leave the corner
    # with no rim. Both are read off the built shape: the plan section's
    # arc, and material 20mm inside it against the open recess 60mm inside
    # it, which is the same 40mm rim the straight edges get.
    #
    # The arc is one radius spanning both edges, so a curved tray is square
    # in plan: Depth is derived, and follows Width. A square tray keeps the
    # catalogue's own 900 depth whatever its width.
    entry = partslib_object.resolveEntry("basic/shower-base")[0]
    manifest = partslib_manifest.load_manifest(entry["path"])

    def tray(overrides):
        return partslib_geometry.build_shape(manifest, entry["dir"],
                                             overrides)

    def plan_arc(shape, z):
        """The widest circular edge in the shape's plan at height `z`."""
        radii = [edge.Curve.Radius
                 for wire in shape.slice(FreeCAD.Vector(0, 0, 1), z)
                 for edge in wire.Edges
                 if edge.Curve.__class__.__name__ == "Circle"]
        return max(radii) if radii else None

    def in_tray(shape, point):
        return shape.isInside(FreeCAD.Vector(*point), 1e-6, False)

    def sized(width, corner):
        return partslib_geometry.measure(
            tray({"Width": width, "Corner": corner}))

    curved_wider = sized(1000.0, "curved")
    square_wider = sized(1000.0, "square")
    h.check("J5 a curved tray is square, a square one keeps its depth",
            abs(curved_wider["Width"] - 1000.0) < 1e-6
            and abs(curved_wider["Depth"] - 1000.0) < 1e-6
            and abs(square_wider["Depth"] - 900.0) < 1e-6,
            detail="curved=%r square=%r" % (curved_wider, square_wider))

    square = tray({"Corner": "square"})
    curved = tray({"Corner": "curved"})
    advertised = {"Width": 900.0, "Depth": 900.0, "Height": 100.0}
    measured = partslib_geometry.measure(curved)
    outer_corner = (890.0, 10.0, 80.0)
    h.check("J5 only the curved tray gives its corner up, inside the size "
            "the manifest advertises",
            all(abs(measured[k] - value) < 1e-6
                for k, value in advertised.items())
            and in_tray(square, outer_corner)
            and not in_tray(curved, outer_corner),
            detail="measured=%r square=%s curved=%s"
            % (measured, in_tray(square, outer_corner),
               in_tray(curved, outer_corner)))

    radius = advertised["Width"] * 0.75
    h.check("J5 the corner's plan edge is an arc of three quarters of the side",
            abs((plan_arc(curved, 50.0) or 0.0) - radius) < 1e-6
            and (plan_arc(square, 50.0) or 0.0) < radius,
            detail="curved=%r square=%r three-quarters=%.1f"
            % (plan_arc(curved, 50.0), plan_arc(square, 50.0), radius))

    # The arc's centre is the tangent point 675mm in from both faces, so a
    # point 655mm from it is 20mm inside the tray's outline - rim - and one
    # 615mm from it is 60mm in, inside the recess's own concentric arc.
    rim_at = (advertised["Width"] - radius + (radius - 20.0) / 2 ** 0.5,
              radius - (radius - 20.0) / 2 ** 0.5, 80.0)
    recess_at = (advertised["Width"] - radius + (radius - 60.0) / 2 ** 0.5,
                 radius - (radius - 60.0) / 2 ** 0.5, 80.0)
    h.check("J5 the rim follows the arc, with the recess inside it",
            in_tray(curved, rim_at) and not in_tray(curved, recess_at),
            detail="rim=%s recess=%s at %r/%r"
            % (in_tray(curved, rim_at), in_tray(curved, recess_at),
               rim_at, recess_at))

    return h.failures()
