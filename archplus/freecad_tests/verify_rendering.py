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
from archplus.tools.partslib import thumbs as partslib_thumbs

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
    h.check("J2 the built shape measures what the manifest advertises",
            measured == {"Width": 400.0, "Depth": 350.0, "Height": 500.0},
            detail="measured=%r" % (measured,))
    h.check("J3 building a shape adds nothing to the document",
            len(doc.Objects) == before,
            detail="objects=%d" % len(doc.Objects))

    return h.failures()
