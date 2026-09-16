# archplus/tools/walls/tests/test_face_pick.py
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Headless tests for resolvePickedFace. FreeCAD attributes the pick of a
# claimed segment's face to the wall root and indexes the face across the
# faces of ALL claimed children, so the raw pair cannot index any shape —
# the root has none. Doors, windows and library-part placement used to index
# it directly and raised IndexError on every mouse move over a wall.

import types

import Part
import pytest

from archplus.tools.walls import object as walls_object


def _proxy(kind):
    return types.SimpleNamespace(Type=kind)


def _face(x, y, z):
    """Stands in for a planar face: the pick test only needs the distance
    from the pick point to the face, so the box is the face's own point."""
    return types.SimpleNamespace(
        point=(x, y, z),
        BoundBox=types.SimpleNamespace(XMin=x, XMax=x, YMin=y, YMax=y,
                                       ZMin=z, ZMax=z))


class _Vertex:
    def __init__(self, point):
        self.point = (point.x, point.y, point.z)

    def distToShape(self, face):
        dist = sum((a - b) ** 2 for a, b in zip(self.point, face.point)) ** 0.5
        return (dist, [], [])


@pytest.fixture
def vertex(monkeypatch):
    """resolveRootFace measures the pick point against each face; the harness
    has no geometry kernel, so the distance is Euclidean over the stub faces."""
    monkeypatch.setattr(Part, "Vertex", _Vertex, raising=False)


def _segment(name, faces):
    return types.SimpleNamespace(
        Name=name, Label=name,
        Proxy=types.SimpleNamespace(Type="Wall", Segment=True),
        Shape=types.SimpleNamespace(isNull=lambda: False, Faces=list(faces)),
        Group=[])


def _root(segments):
    return types.SimpleNamespace(
        Name="Wall", Proxy=types.SimpleNamespace(Type="Wall", WALLS_PLUS=True),
        Shape=types.SimpleNamespace(isNull=lambda: True, Faces=[]),
        Group=list(segments))


def test_root_pick_maps_onto_the_segment_holding_the_face(vertex):
    near = _segment("Segments", [_face(0, 0, 0), _face(100, 0, 0)])
    far = _segment("Thin", [_face(0, 500, 0)])
    root = _root([near, far])

    # The reported index counts across all claimed children, so it says
    # nothing about any one segment: the pick point decides.
    assert walls_object.resolvePickedFace(root, 999, 100.0, 0.0, 0.0) == (near, 1)
    assert walls_object.resolvePickedFace(root, 999, 0.0, 500.0, 0.0) == (far, 0)


def test_segment_named_pick_resolves_across_the_whole_wall(vertex):
    # FreeCAD can name a segment and still count the index across every
    # object the wall claims: a hover on the wall's big face came back as
    # "Segments Face121" while that segment has 36 faces.
    near = _segment("Segments", [_face(0, 0, 0), _face(100, 0, 0)])
    far = _segment("Thin", [_face(0, 500, 0)])
    root = _root([near, far])
    near.Wall = root
    far.Wall = root

    assert walls_object.resolvePickedFace(near, 120, 100.0, 0.0, 0.0) == (near, 1)
    assert walls_object.resolvePickedFace(near, 120, 0.0, 500.0, 0.0) == (far, 0)


def test_arch_wall_pick_keeps_its_own_face_index():
    # A regular Arch wall is typed "Wall" too, but it owns the faces its
    # picks report: rerouting it through a wall-wide resolution found no
    # segments and dropped the snap entirely.
    arch = types.SimpleNamespace(
        Name="Wall001", Proxy=types.SimpleNamespace(Type="Wall"),
        Shape=types.SimpleNamespace(isNull=lambda: False,
                                    Faces=[_face(0, 0, 0)] * 6))
    assert walls_object.resolvePickedFace(arch, 2, 0.0, 0.0, 0.0) == (arch, 2)


def test_pick_a_shape_can_carry_comes_back_unchanged():
    stairs = types.SimpleNamespace(
        Name="Stairs",
        Shape=types.SimpleNamespace(isNull=lambda: False,
                                    Faces=[_face(0, 0, 0)] * 3))
    assert walls_object.resolvePickedFace(stairs, 2, 0.0, 0.0, 0.0) == (stairs, 2)


def test_pick_with_no_usable_face_resolves_to_none(vertex):
    assert walls_object.resolvePickedFace(None, 0) is None
    root = _root([_segment("Segments", [_face(0, 0, 0)])])
    assert walls_object.resolvePickedFace(root, 0, 900.0, 900.0, 0.0) is None
    plain = types.SimpleNamespace(
        Name="Sketch",
        Shape=types.SimpleNamespace(isNull=lambda: False, Faces=[]))
    assert walls_object.resolvePickedFace(plain, 3, 0.0, 0.0, 0.0) is None
