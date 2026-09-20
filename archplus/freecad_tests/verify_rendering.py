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

    return h.failures()
