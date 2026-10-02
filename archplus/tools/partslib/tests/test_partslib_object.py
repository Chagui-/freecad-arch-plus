# SPDX-License-Identifier: LGPL-2.1-or-later
#
# The placed-part predicate: what counts as a library part in a document.
#
# A document's parts outlive the module that made them. FreeCAD can re-import
# a workbench's Python, and anything else that reloads partslib.object leaves
# every already-placed part holding a proxy of the PREVIOUS class object - so
# an isinstance check against the current class starts answering False for
# parts that are perfectly fine, and the editor refuses them with "X is not a
# placed library part". A real document showed exactly that after a session
# of reloading: 41 of its 43 parts unrecognised.

import types

from archplus.tools.partslib import object as partslib_object


class _OlderLibraryProxy:
    """What a re-import leaves behind: the same code, a DIFFERENT class."""

    Type = "LibraryPart"


def test_a_part_placed_before_a_reimport_is_still_a_library_part():
    part = types.SimpleNamespace(Label="Shower screen",
                                 Proxy=_OlderLibraryProxy())
    assert partslib_object.isLibraryPart(part)


def test_other_objects_are_not_library_parts():
    # The predicate has to keep discriminating: anything else in a document -
    # a wall's segment, a plain feature, an object with no proxy at all -
    # must answer False, or the editor opens on things it cannot edit.
    segment = types.SimpleNamespace(Label="Segments",
                                    Proxy=types.SimpleNamespace(Type="Wall"))
    plain = types.SimpleNamespace(Label="Box", Proxy=types.SimpleNamespace())
    assert not partslib_object.isLibraryPart(segment)
    assert not partslib_object.isLibraryPart(plain)
    assert not partslib_object.isLibraryPart(types.SimpleNamespace())
