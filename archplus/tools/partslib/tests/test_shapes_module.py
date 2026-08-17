# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Guards the public surface of the shared geometry vocabulary. Every part
# builder and every family's _shared.py imports this module by its absolute
# path, so losing a name here breaks parts that never mention it directly.

from archplus.tools.partslib import shapes


def test_shapes_is_importable_without_freecad():
    # Imported at module scope above: the assertion is that the import
    # itself did not raise under the fake Part in conftest.py.
    assert shapes.__name__ == "archplus.tools.partslib.shapes"


def test_the_public_massing_vocabulary_is_present():
    expected = [
        "rounded_box", "soften_top", "square_leg", "roll_top", "tapered_leg",
        "cut_box", "cut_boxes", "cushion", "bar", "panel_reveal_boxes",
        "panel_reveal", "toe_kick", "door_seam", "oval", "rotate",
        "tube_elbow", "vector", "place", "fuse_all", "safe_fillet",
    ]
    missing = [name for name in expected
               if not callable(getattr(shapes, name, None))]
    assert missing == []
