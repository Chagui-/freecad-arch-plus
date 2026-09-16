# archplus/tools/walls/tests/test_roles.py
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Role-typing contract for walls: both roles report Proxy.Type "Wall" —
# that is the string FreeCAD's FuseArch/JoinArch fuse paths filter on
# (draftobjects/shape2dview.py, ArchSectionPlane.getCutShapes), so any
# other type makes segments cut through a section individually, unfused.
# The root/segment distinction lives in the proxy's Segment flag.

import types

from archplus.tools.walls import object as walls_object


class _Obj:
    """Enough App-object surface for _Wall.setProperties()."""

    def __init__(self):
        self.PropertiesList = []
        self.Placement = types.SimpleNamespace(isIdentity=lambda: True)

    def addProperty(self, ptype, name, group="", doc=""):
        setattr(self, name, None)
        self.PropertiesList.append(name)

    def touch(self):
        pass


def _segment_obj():
    obj = _Obj()
    walls_object._Wall(obj, root=False)
    return obj


def _root_obj():
    obj = _Obj()
    walls_object._Wall(obj, root=True)
    return obj


def test_both_roles_report_wall_type():
    """Draft.getType() reads Proxy.Type; the FuseArch fuse only picks up
    objects reporting 'Wall', so segments must report it too."""
    assert _segment_obj().Proxy.Type == "Wall"
    assert _root_obj().Proxy.Type == "Wall"


def test_segment_flag_discriminates_roles():
    seg = _segment_obj()
    root = _root_obj()
    assert walls_object.is_segment(seg)
    assert not walls_object.is_root(seg)
    assert walls_object.is_root(root)
    assert not walls_object.is_segment(root)


def test_restored_legacy_segment_migrates_to_wall_type():
    """Documents saved before the retype carry the role in Type
    ('WallSegment'); restoring must set the Segment flag and report 'Wall'."""
    obj = _Obj()
    proxy = object.__new__(walls_object._Wall)
    proxy.Type = "WallSegment"
    proxy.onDocumentRestored(obj)
    obj.Proxy = proxy
    assert proxy.Type == "Wall"
    assert walls_object.is_segment(obj)
    assert proxy.Segment is True


def test_restored_legacy_root_migrates():
    obj = _Obj()
    proxy = object.__new__(walls_object._Wall)
    proxy.Type = "Wall"
    proxy.onDocumentRestored(obj)
    obj.Proxy = proxy
    assert proxy.Segment is False


def test_stock_arch_wall_is_neither_role():
    """A stock Arch wall reports Type 'Wall' with no WALLS_PLUS marker; the
    predicates must reject it (is_root already relied on the marker, and
    now the Segment flag must not make it a segment either)."""
    obj = _Obj()
    obj.Proxy = types.SimpleNamespace(Type="Wall")
    assert not walls_object.is_segment(obj)
    assert not walls_object.is_root(obj)
