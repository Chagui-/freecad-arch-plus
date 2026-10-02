# SPDX-License-Identifier: LGPL-2.1-or-later
#
# The order a wall builds its claimed sketch edges in. A segment fuses one
# extrusion per edge chain and then subtracts its openings, and every one of
# those booleans hands the result its own sub-element order — so the order
# the inputs go in is the order the built shape reports its faces, edges and
# vertices in. That order must be a property of the sketch (its geometry
# order), never of the edge subnames as strings: a string sort puts Edge10
# before Edge2, so adding a run to the sketch reorders every wall on it and
# shifts every sub-element index the wall hands out. TechDraw dimensions on
# a section view reference exactly those indices, so they read a different
# piece of the wall.

import types

from archplus.tools.walls import object as walls_object


class _Sketch:
    def __init__(self, count):
        self.Shape = types.SimpleNamespace(
            ElementMap={"g%d" % i: "Edge%d" % i for i in range(1, count + 1)})


class _Proxy(walls_object._Wall):
    """A real proxy (the claim resolution is its method) without the
    document-object half of _Wall.__init__."""

    def __init__(self, **attrs):
        self.__dict__.update(attrs)


class _Seg(types.SimpleNamespace):
    """Segments hash by identity (the claim resolver keys its result by the
    object it was handed), which SimpleNamespace's value equality defeats."""

    __hash__ = object.__hash__


def _segment(name, edges=(), fallback=False):
    return _Seg(
        Name=name, Label=name, Group=[], InList=[], Wall=None,
        Edges=[(None, tuple(edges))] if edges else [],
        Fallback=fallback, Base=None,
        Proxy=_Proxy(Type="Wall", Segment=True))


def _wall(sketch, *segments):
    root = types.SimpleNamespace(
        Name="Wall", Label="Wall", Base=sketch, Edges=[], Fallback=False,
        Group=list(segments), InList=[],
        Proxy=types.SimpleNamespace(Type="Wall", WALLS_PLUS=True))
    for seg in segments:
        seg.Wall = root
        seg.Base = sketch
        seg.InList = [root]
    return root


def _order(seg):
    return walls_object.claimedEdges(seg)


def test_claims_resolve_in_sketch_order_not_string_order():
    """Edge19 before Edge2 is the string sort leaking into the build order."""
    sk = _Sketch(19)
    seg = _segment("a", ["Edge19", "Edge2", "Edge3", "Edge10"])
    _wall(sk, seg)
    assert _order(seg) == ["Edge2", "Edge3", "Edge10", "Edge19"]


def test_fallback_builds_the_unclaimed_edges_in_sketch_order():
    sk = _Sketch(12)
    fallback = _segment("fallback", fallback=True)
    taken = _segment("taken", ["Edge1", "Edge2"])
    _wall(sk, fallback, taken)
    assert _order(fallback) == ["Edge%d" % i for i in range(3, 13)]


def test_adding_a_run_leaves_the_earlier_build_order_alone():
    """The regression that matters: appending an edge to the sketch must
    not disturb the order the wall already builds its runs in, because the
    built shape's sub-element indices follow that order."""
    before_sk = _Sketch(9)
    before = _segment("fallback", fallback=True)
    _wall(before_sk, before)
    before_order = _order(before)

    after_sk = _Sketch(10)
    after = _segment("fallback", fallback=True)
    _wall(after_sk, after)

    assert before_order == ["Edge%d" % i for i in range(1, 10)]
    assert _order(after) == ["Edge%d" % i for i in range(1, 11)]
    assert _order(after)[:len(before_order)] == before_order
