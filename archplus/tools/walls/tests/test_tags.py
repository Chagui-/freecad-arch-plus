# archplus/tools/walls/tests/test_tags.py
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# The tag a built run carries, which is what makes FreeCAD's element map
# meaningful: a boolean of tagged operands names its sub-elements after the
# operands' tags (`Face6;:M;CUT;:H65:8,F`), so a reference stored by mapped
# name finds the same run's face again after a rebuild. A tag of zero is the
# "no map at all" case this must never fall into, and two runs of one wall
# must never share a tag or their names would resolve to each other.

from archplus.tools.walls import object as walls_object


def test_edge_index_reads_the_sketch_edge_number():
    assert walls_object._edgeIndex("Edge1") == 1
    assert walls_object._edgeIndex("Edge12") == 12


def test_edge_index_is_zero_for_names_that_carry_none():
    # Legacy lowercase claims (pre-rename documents) and anything that is not
    # an edge name at all must not be read as an index.
    assert walls_object._edgeIndex("edge17") == 0
    assert walls_object._edgeIndex("Face3") == 0
    assert walls_object._edgeIndex("") == 0


def test_run_tag_is_a_claimed_edge_index():
    assert walls_object._runTag(["Edge7"], 0) == 7
    # The lowest edge of a mitered chain names the run, whichever order the
    # chain was traversed in.
    assert walls_object._runTag(["Edge12", "Edge3"], 1) == 3


def test_run_tag_falls_back_to_the_build_position():
    # A run whose claimed names carry no index (a legacy lowercase claim) and
    # one that builds nothing at all fall back the same way: to the run's
    # build position, never to zero — zero is an untagged operand, and an
    # untagged operand is a shape with no element map at all.
    assert walls_object._runTag(["edge17"], 0) == 1000000
    assert walls_object._runTag([], 1) == 1000001
    assert walls_object._runTag([""], 2) > 0


def test_run_tags_do_not_collide_between_runs():
    # One run named by an edge index and another by position must not meet:
    # a shared tag means shared mapped names, and a stored name then resolves
    # to the wrong run.
    tags = [walls_object._runTag(["Edge1"], 0), walls_object._runTag([], 0),
            walls_object._runTag(["Edge2"], 1)]
    assert len(set(tags)) == len(tags)
