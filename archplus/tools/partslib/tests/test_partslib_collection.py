# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Collections - the optional collection.json that names a family of parts.
#
# What matters here is that a BAD collection can never hide the parts inside
# it: every failure path has to come back as an error string plus "no family",
# never as an exception that takes the scan down with it.

import json
import os

import pytest

from archplus.tools.partslib import collection as pc


def _library(tmp_path, layout):
    """Build a library tree. `layout` maps a relative path to file content:
    a dict is written as JSON, a string verbatim."""
    for relative, content in layout.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content) if isinstance(content, dict)
                        else content, encoding="utf8")
    return str(tmp_path)


def test_a_part_inherits_the_collection_above_it(tmp_path):
    library = _library(tmp_path, {
        "ikea-malm/collection.json": {"schema": 1, "label": "IKEA Malm",
                                      "description": "Bedroom range."},
        "ikea-malm/chest/part.json": {"name": "Chest"},
    })
    label, description, errors = pc.resolve(
        os.path.join(library, "ikea-malm", "chest"), library)
    assert (label, description, errors) == (
        "IKEA Malm", "Bedroom range.", [])


def test_the_nearest_collection_wins(tmp_path):
    library = _library(tmp_path, {
        "ikea/collection.json": {"label": "IKEA"},
        "ikea/malm/collection.json": {"label": "IKEA Malm"},
        "ikea/malm/chest/part.json": {"name": "Chest"},
    })
    label, _description, errors = pc.resolve(
        os.path.join(library, "ikea", "malm", "chest"), library)
    assert (label, errors) == ("IKEA Malm", [])


def test_a_part_with_no_collection_above_it_has_no_family(tmp_path):
    library = _library(tmp_path, {"loose/part.json": {"name": "Loose"}})
    assert pc.resolve(os.path.join(library, "loose"), library) == (
        None, None, [])


def test_the_search_stops_at_the_library_root(tmp_path):
    # A collection.json ABOVE the library must not leak in - the library
    # root is the boundary of what this add-on owns.
    (tmp_path / "outside").mkdir()
    (tmp_path / "collection.json").write_text(
        json.dumps({"label": "Outside"}), encoding="utf8")
    library = _library(tmp_path / "outside", {"part/part.json": {"n": 1}})
    assert pc.resolve(os.path.join(library, "part"), library) == (
        None, None, [])


def test_a_collection_at_the_library_root_applies(tmp_path):
    library = _library(tmp_path, {
        "collection.json": {"label": "House style"},
        "chair/part.json": {"name": "Chair"},
    })
    label, _d, errors = pc.resolve(os.path.join(library, "chair"), library)
    assert (label, errors) == ("House style", [])


def test_a_collection_without_a_label_yields_no_family_and_no_error(tmp_path):
    # basic/'s normal state: defined and documented, deliberately unlabelled,
    # so its parts carry no family line. Not a warning - an unlabelled
    # collection means "these parts belong to no brand".
    library = _library(tmp_path, {
        "basic/collection.json": {"schema": 1, "description": "Generic."},
        "basic/chair/part.json": {"name": "Chair"},
    })
    assert pc.resolve(os.path.join(library, "basic", "chair"), library) == (
        None, "Generic.", [])


def test_malformed_json_is_an_error_not_an_exception(tmp_path):
    library = _library(tmp_path, {
        "broken/collection.json": "{not json",
        "broken/chair/part.json": {"name": "Chair"},
    })
    label, description, errors = pc.resolve(
        os.path.join(library, "broken", "chair"), library)
    assert (label, description) == (None, None)
    assert len(errors) == 1
    assert "collection.json" in errors[0]


def test_a_non_string_label_is_an_error(tmp_path):
    library = _library(tmp_path, {
        "odd/collection.json": {"label": 7},
        "odd/chair/part.json": {"name": "Chair"},
    })
    label, _d, errors = pc.resolve(
        os.path.join(library, "odd", "chair"), library)
    assert label is None
    assert len(errors) == 1
    assert "label" in errors[0]


def test_an_unsupported_schema_is_an_error(tmp_path):
    library = _library(tmp_path, {
        "future/collection.json": {"schema": 99, "label": "Future"},
        "future/chair/part.json": {"name": "Chair"},
    })
    label, _d, errors = pc.resolve(
        os.path.join(library, "future", "chair"), library)
    assert label is None
    assert "schema" in errors[0]


def test_a_document_that_is_not_an_object_is_an_error(tmp_path):
    library = _library(tmp_path, {
        "odd/collection.json": "[1, 2, 3]",
        "odd/chair/part.json": {"name": "Chair"},
    })
    label, _d, errors = pc.resolve(
        os.path.join(library, "odd", "chair"), library)
    assert label is None
    assert errors


def test_the_cache_reads_one_collection_once(tmp_path):
    # A scan resolves every part; without the cache a 40-part collection
    # reads and parses the same file 40 times.
    library = _library(tmp_path, {
        "pack/collection.json": {"label": "Pack"},
        "pack/a/part.json": {"name": "A"},
        "pack/b/part.json": {"name": "B"},
    })
    cache = {}
    pc.resolve(os.path.join(library, "pack", "a"), library, cache)
    pc.resolve(os.path.join(library, "pack", "b"), library, cache)
    assert len(cache) == 1


def test_collection_paths_finds_every_collection_in_order(tmp_path):
    library = _library(tmp_path, {
        "b/collection.json": {"label": "B"},
        "a/collection.json": {"label": "A"},
        "a/part/part.json": {"name": "P"},
    })
    found = pc.collection_paths(library)
    assert found == sorted(found)
    assert len(found) == 2


def test_load_collection_raises_for_a_missing_file(tmp_path):
    with pytest.raises(ValueError):
        pc.load_collection(str(tmp_path / "nope.json"))
