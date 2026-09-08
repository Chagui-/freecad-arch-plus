# archplus/tools/walls/tests/test_delete.py
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Headless tests for the view provider's delete cascade: deleting a wall
# or a segment in the GUI must remove its descendant segments, because
# FreeCAD's own delete never cascades and would orphan them with
# dangling Wall links. The shared sketch never follows.

import types

from archplus.tools.walls import object as walls_object


def _proxy(kind):
    return types.SimpleNamespace(Type=kind)


def _doc():
    removed = []

    class _Doc:
        def removeObject(self, name):
            removed.append(name)

    return _Doc(), removed


def _segment(name, doc, children=()):
    seg = types.SimpleNamespace(Name=name, Label=name,
                                Proxy=_proxy("WallSegment"),
                                Document=doc, Group=list(children))
    for child in children:
        child.Wall = seg
    return seg


def _root(doc, segments=()):
    return types.SimpleNamespace(Name="Wall", Proxy=_proxy("Wall"),
                                 Document=doc, Group=list(segments))


def _vobj(obj):
    return types.SimpleNamespace(Object=obj)


def _vp():
    return walls_object._ViewProviderWall.__new__(
        walls_object._ViewProviderWall)
def test_viewprovider_visibility_cascades_to_segments():
    """Hiding the wall root must hide its claimed segments: the root
    itself has no shape, so without the cascade the wall would still
    read as visible. Arch levels hide their direct children; this closes
    the chain down to the segments."""
    doc, _removed = _doc()
    nested = _segment("nested", doc)
    a = _segment("a", doc, [nested])
    root = _root(doc, [a])
    vobj = types.SimpleNamespace(Object=root, Visibility=True)
    vp = _vp()
    vos = {}
    for seg in (nested, a):
        vo = types.SimpleNamespace(Visibility=True)
        seg.ViewObject = vo
        vos[seg.Name] = vo
    vp.onChanged(vobj, "Visibility")
    assert all(vo.Visibility for vo in vos.values())
    vobj.Visibility = False
    vp.onChanged(vobj, "Visibility")
    assert not any(vo.Visibility for vo in vos.values())
    vobj.Visibility = True
    vp.onChanged(vobj, "Visibility")
    assert all(vo.Visibility for vo in vos.values())


def test_delete_root_cascades_to_all_segments():
    doc, removed = _doc()
    nested = _segment("nested", doc)
    a = _segment("a", doc, [nested])
    b = _segment("b", doc)
    root = _root(doc, [a, b])
    assert _vp().onDelete(_vobj(root), []) is True
    assert removed == ["a", "nested", "b"]


def test_delete_segment_cascades_to_its_children():
    doc, removed = _doc()
    nested = _segment("nested", doc)
    a = _segment("a", doc, [nested])
    _root(doc, [a])
    assert _vp().onDelete(_vobj(a), []) is True
    assert removed == ["nested"]


def test_delete_never_removes_the_shared_sketch():
    doc, removed = _doc()
    sketch = types.SimpleNamespace(Name="Sketch", Proxy=_proxy("Sketcher"))
    root = types.SimpleNamespace(Name="Wall", Proxy=_proxy("Wall"),
                                 Document=doc, Group=[], Base=sketch)
    assert _vp().onDelete(_vobj(root), []) is True
    assert removed == []


def test_delete_empty_wall_without_removals():
    doc, removed = _doc()
    root = _root(doc)
    assert _vp().onDelete(_vobj(root), []) is True
    assert removed == []
