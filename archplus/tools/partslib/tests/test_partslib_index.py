import json
import os

from archplus.tools.partslib import index as px

FACETS = {
    "function": {"multi": False, "values": {"Sanitary": {}, "Seating": {}}},
    "element": {"multi": False, "values": {"WC": {}, "Chair": {}}},
    "room": {"multi": True, "values": {"Bathroom": {}, "Kitchen": {}}},
}


def _library(tmp_path, *parts, params=None):
    (tmp_path / "facets.json").write_text(json.dumps(FACETS), encoding="utf8")
    for part in parts:
        if params is not None:
            part = dict(part)
            part["params"] = params
        folder = tmp_path / part["id"]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "part.json").write_text(json.dumps(part), encoding="utf8")
    return str(tmp_path)


def _part(part_id, name, **over):
    data = {
        "schema": 1,
        "id": part_id,
        "name": name,
        "facets": {"function": "Sanitary", "element": "WC",
                   "room": ["Bathroom"]},
        # No builder.py on disk and a declared asset: an asset-only part,
        # which is what the fixture has always meant.
        "geometry": {"assets": {"body": "wc-360.brep"}},
    }
    data.update(over)
    return data


def _library_at(tmp_path, *folder_and_data):
    """Like _library, but the folder is given separately from the manifest.

    _library names each folder after part["id"], which is exactly what these
    tests must not rely on - the id is what is being derived."""
    (tmp_path / "facets.json").write_text(json.dumps(FACETS), encoding="utf8")
    for folder, data in folder_and_data:
        target = tmp_path / folder
        target.mkdir(parents=True, exist_ok=True)
        (target / "part.json").write_text(json.dumps(data), encoding="utf8")
    return str(tmp_path)


def _unnamed_part(name, **over):
    """A valid manifest with NO id, for folder-derivation tests."""
    data = {
        "schema": 1,
        "name": name,
        "facets": {"function": "Seating", "element": "Chair",
                   "room": ["Kitchen"]},
        "geometry": {"assets": {"body": "chair.brep"}},
    }
    data.update(over)
    return data


def test_core_module_does_not_import_freecad():
    import inspect
    src = inspect.getsource(px)
    for banned in ("import FreeCAD", "import Part", "from PySide"):
        assert banned not in src


def test_scan_finds_every_part(tmp_path):
    root = _library(tmp_path, _part("wc-a", "WC A"), _part("wc-b", "WC B"))
    index = px.scan(root)
    assert sorted(e["id"] for e in index["entries"]) == ["wc-a", "wc-b"]
    assert index["errors"] == []


def test_entries_carry_the_params_block_and_no_variants(tmp_path):
    library = _library(
        tmp_path, _part("wc-a", "WC A"),
        params={"Width": {"type": "Length", "default": 600,
                           "ui": "primary"}})
    entry = px.scan(library)["entries"][0]
    assert entry["params"] == {
        "Width": {"type": "Length", "default": 600, "ui": "primary"}}
    assert "variants" not in entry


def test_a_version_1_cache_is_rejected(tmp_path):
    path = tmp_path / "index.json"
    path.write_text(json.dumps({"version": 1, "facets": {}, "entries": []}),
                    encoding="utf8")
    assert px.load_cache(str(path)) is None


def test_duplicate_ids_are_an_error(tmp_path):
    root = _library(tmp_path, _part("wc-a", "WC A"))
    other = tmp_path / "elsewhere"
    other.mkdir()
    (other / "part.json").write_text(
        json.dumps(_part("wc-a", "Clash")), encoding="utf8")
    index = px.scan(root)
    assert any("wc-a" in e for e in index["errors"])


def test_invalid_manifest_is_reported_and_skipped(tmp_path):
    root = _library(tmp_path, _part("wc-a", "WC A"))
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "part.json").write_text(json.dumps({"id": "bad"}), encoding="utf8")
    index = px.scan(root)
    assert index["errors"]
    assert [e["id"] for e in index["entries"]] == ["wc-a"]


def test_missing_facets_file_is_an_error(tmp_path):
    folder = tmp_path / "wc-a"
    folder.mkdir()
    (folder / "part.json").write_text(
        json.dumps(_part("wc-a", "WC A")), encoding="utf8")
    index = px.scan(str(tmp_path))
    assert any("facets.json" in e for e in index["errors"])


def test_cache_roundtrips(tmp_path):
    root = _library(tmp_path, _part("wc-a", "WC A"))
    index = px.scan(root)
    cache_path = str(tmp_path / "index.json")
    px.save_cache(index, cache_path)
    assert px.load_cache(cache_path)["entries"][0]["id"] == "wc-a"


def test_cache_is_valid_when_nothing_changed(tmp_path):
    root = _library(tmp_path, _part("wc-a", "WC A"))
    assert px.is_cache_valid(px.scan(root), root) is True


def test_cache_is_stale_when_a_manifest_changes(tmp_path):
    root = _library(tmp_path, _part("wc-a", "WC A"))
    index = px.scan(root)
    manifest = os.path.join(root, "wc-a", "part.json")
    os.utime(manifest, (0, 0))
    assert px.is_cache_valid(index, root) is False


def test_cache_is_stale_when_a_part_is_added(tmp_path):
    root = _library(tmp_path, _part("wc-a", "WC A"))
    index = px.scan(root)
    added = tmp_path / "wc-b"
    added.mkdir()
    (added / "part.json").write_text(
        json.dumps(_part("wc-b", "WC B")), encoding="utf8")
    assert px.is_cache_valid(index, root) is False


def test_load_cache_returns_none_when_absent(tmp_path):
    assert px.load_cache(str(tmp_path / "nope.json")) is None


def test_scan_records_the_vocabulary_mtime(tmp_path):
    root = _library(tmp_path, _part("wc-a", "WC A"))
    index = px.scan(root)
    assert index["facetsMtime"] == os.path.getmtime(
        os.path.join(root, "facets.json"))


def test_cache_is_stale_when_the_vocabulary_changes(tmp_path):
    root = _library(tmp_path, _part("wc-a", "WC A"))
    index = px.scan(root)
    os.utime(os.path.join(root, "facets.json"), (0, 0))
    assert px.is_cache_valid(index, root) is False


def test_saved_cache_still_validates_after_a_roundtrip(tmp_path):
    root = _library(tmp_path, _part("wc-a", "WC A"))
    cache_path = str(tmp_path / "index.json")
    px.save_cache(px.scan(root), cache_path)
    assert px.is_cache_valid(px.load_cache(cache_path), root) is True


ENTRIES = [
    {"id": "wc-a", "name": "Wall-hung WC", "description": "Rimless pan.",
     "keywords": ["toilet", "pan"],
     "facets": {"function": "Sanitary", "element": "WC",
                "room": ["Bathroom", "Kitchen"]}},
    {"id": "chair-a", "name": "Stacking chair", "description": "Café chair.",
     "keywords": ["seat"],
     "facets": {"function": "Seating", "element": "Chair",
                "room": ["Kitchen"]}},
    {"id": "misc-a", "name": "Mystery object", "description": "",
     "keywords": [], "facets": {"function": "Sanitary"}},
]


def test_empty_query_returns_everything_by_name():
    assert [e["id"] for e in px.search(ENTRIES, "")] == [
        "misc-a", "chair-a", "wc-a"]


def test_search_matches_the_name():
    assert [e["id"] for e in px.search(ENTRIES, "chair")] == ["chair-a"]


def test_search_matches_a_keyword():
    assert [e["id"] for e in px.search(ENTRIES, "toilet")] == ["wc-a"]


def test_search_matches_the_description():
    assert [e["id"] for e in px.search(ENTRIES, "rimless")] == ["wc-a"]


def test_search_is_case_insensitive():
    assert [e["id"] for e in px.search(ENTRIES, "WALL-HUNG")] == ["wc-a"]


def test_name_matches_outrank_description_matches():
    entries = [
        {"id": "desc", "name": "Basin", "description": "next to the chair",
         "keywords": [], "facets": {}},
        {"id": "name", "name": "Chair", "description": "",
         "keywords": [], "facets": {}},
    ]
    assert [e["id"] for e in px.search(entries, "chair")] == ["name", "desc"]


def test_search_excludes_non_matches():
    assert px.search(ENTRIES, "zzzz") == []


def test_group_by_single_valued_facet():
    groups = px.group_by(ENTRIES, "function")
    assert sorted(groups) == ["Sanitary", "Seating"]
    assert sorted(e["id"] for e in groups["Sanitary"]) == ["misc-a", "wc-a"]


def test_multi_valued_facet_puts_one_part_in_several_groups():
    groups = px.group_by(ENTRIES, "room")
    assert sorted(e["id"] for e in groups["Kitchen"]) == ["chair-a", "wc-a"]
    assert [e["id"] for e in groups["Bathroom"]] == ["wc-a"]


def test_entries_missing_the_facet_are_unclassified():
    groups = px.group_by(ENTRIES, "room")
    assert [e["id"] for e in groups[px.UNCLASSIFIED]] == ["misc-a"]


# -- room/element fixtures, shared by the facet_groups tests --------------

CATEGORY_FACETS = {
    "room": {"label": "Room", "multi": True, "values": {
        "Bathroom": {"label": "Bathroom", "icon": "bathroom.svg"},
        "Kitchen": {"label": "Kitchen"},
        "Office": {"label": "Office"},
    }},
    "element": {"label": "Element", "multi": False, "values": {
        "WC": {"label": "Toilets"},
        "Basin": {"label": "Basins"},
        "Cabinet": {"label": "Cabinets"},
        "Chair": {"label": "Chairs"},
    }},
}

# Office is a vocabulary room that no part references - it must not appear.
# wc-a sits in both Bathroom and Kitchen. noroom-a has no room. noelement-a
# has no element. Kitchen's parts span three distinct elements.
CATEGORY_ENTRIES = [
    {"id": "wc-a", "name": "WC A",
     "facets": {"room": ["Bathroom", "Kitchen"], "element": "WC"}},
    {"id": "basin-a", "name": "Basin A",
     "facets": {"room": ["Bathroom"], "element": "Basin"}},
    {"id": "cabinet-a", "name": "Cabinet A",
     "facets": {"room": ["Kitchen"], "element": "Cabinet"}},
    {"id": "chair-a", "name": "Chair A",
     "facets": {"room": ["Kitchen"], "element": "Chair"}},
    {"id": "noroom-a", "name": "No Room A",
     "facets": {"element": "Chair"}},
    {"id": "noelement-a", "name": "No Element A",
     "facets": {"room": ["Bathroom"]}},
]


def _by_value(groups):
    return {g["value"]: g for g in groups}


def test_category_tree_is_gone():
    # It served the catalogue screen, which no longer exists.
    assert not hasattr(px, "category_tree")


def test_an_id_is_derived_from_the_folder_path(tmp_path):
    root = _library_at(
        tmp_path, ("basic/side-table", _unnamed_part("Side Table")))

    index = px.scan(root)

    assert index["errors"] == []
    assert [e["id"] for e in index["entries"]] == ["basic/side-table"]


def test_a_standalone_part_gets_a_one_segment_id(tmp_path):
    # Reserved for one-off imports: a part folder at the library root.
    root = _library_at(
        tmp_path, ("geberit-icon", _unnamed_part("Geberit Icon")))

    index = px.scan(root)

    assert index["errors"] == []
    assert [e["id"] for e in index["entries"]] == ["geberit-icon"]


def test_an_explicit_id_overrides_the_folder_path(tmp_path):
    # Pinning an id is how identity survives a folder rename.
    root = _library_at(tmp_path, (
        "basic/renamed-folder",
        _unnamed_part("Side Table", id="basic/side-table")))

    index = px.scan(root)

    assert index["errors"] == []
    assert [e["id"] for e in index["entries"]] == ["basic/side-table"]


def test_the_same_leaf_in_two_families_does_not_collide(tmp_path):
    # This is why ids are paths: every brand sells a chair.
    root = _library_at(
        tmp_path,
        ("basic/chair", _unnamed_part("Chair")),
        ("ikea-brimnes/chair", _unnamed_part("Chair")))

    index = px.scan(root)

    assert index["errors"] == []
    assert sorted(e["id"] for e in index["entries"]) == [
        "basic/chair", "ikea-brimnes/chair"]


def test_an_id_segment_containing_a_dot_is_reported(tmp_path):
    # A dot would split the dotted import path for builder.py.
    root = _library_at(tmp_path, ("basic/55.inch", _unnamed_part("Screen")))

    index = px.scan(root)

    assert index["entries"] == []
    assert index["errors"] != []


def test_a_part_with_no_builder_and_no_assets_is_an_error(tmp_path):
    # Forgetting builder.py would otherwise fall through to the asset
    # builder and fail with "declares no asset 'body'", which names the
    # wrong problem.
    root = _library_at(tmp_path, (
        "basic/forgot-the-builder",
        _unnamed_part("Forgot", geometry={})))

    index = px.scan(root)

    assert index["entries"] == []
    assert any("builder.py" in e for e in index["errors"]), index["errors"]


def test_a_part_with_a_builder_py_is_accepted(tmp_path):
    root = _library_at(tmp_path, (
        "basic/has-a-builder",
        _unnamed_part("Has One", geometry={})))
    (tmp_path / "basic" / "has-a-builder" / "builder.py").write_text(
        "def build(params, assets, ctx):\n    return None\n")

    index = px.scan(root)

    assert index["errors"] == []
    assert [e["id"] for e in index["entries"]] == ["basic/has-a-builder"]


def test_an_asset_only_part_needs_no_builder_py(tmp_path):
    # No builder.py plus declared assets is exactly an asset-only part.
    root = _library_at(
        tmp_path, ("basic/vendor-chair", _unnamed_part("Vendor Chair")))

    index = px.scan(root)

    assert index["errors"] == []
    assert [e["id"] for e in index["entries"]] == ["basic/vendor-chair"]


def test_an_entry_carries_its_collections_label(tmp_path):
    library = _library_at(
        tmp_path, ("ikea-malm/chest", _unnamed_part("Malm chest")))
    (tmp_path / "ikea-malm" / "collection.json").write_text(
        json.dumps({"schema": 1, "label": "IKEA Malm",
                    "description": "Bedroom range."}), encoding="utf8")

    entry = px.scan(library)["entries"][0]
    assert entry["family"] == "IKEA Malm"
    assert entry["familyDescription"] == "Bedroom range."


def test_an_entry_with_no_collection_has_no_family(tmp_path):
    library = _library_at(
        tmp_path, ("loose/chair", _unnamed_part("Chair")))
    entry = px.scan(library)["entries"][0]
    assert entry["family"] is None
    assert entry["familyDescription"] is None


def test_an_unlabelled_collection_still_yields_no_family(tmp_path):
    # library/basic/'s state: defined and documented, deliberately unlabelled.
    library = _library_at(
        tmp_path, ("basic/chair", _unnamed_part("Chair")))
    (tmp_path / "basic" / "collection.json").write_text(
        json.dumps({"schema": 1, "description": "Generic."}), encoding="utf8")

    entry = px.scan(library)["entries"][0]
    assert entry["family"] is None
    assert entry["familyDescription"] == "Generic."


def test_a_broken_collection_reports_an_error_but_keeps_its_parts(tmp_path):
    library = _library_at(
        tmp_path, ("broken/chair", _unnamed_part("Chair")))
    (tmp_path / "broken" / "collection.json").write_text(
        "{not json", encoding="utf8")

    result = px.scan(library)
    assert len(result["entries"]) == 1        # the part is still there
    assert result["entries"][0]["family"] is None
    assert any("collection.json" in e for e in result["errors"])


def test_a_family_label_is_searchable():
    entries = [
        {"id": "a", "name": "Chest", "keywords": [], "description": "",
         "family": "IKEA Malm"},
        {"id": "b", "name": "Sofa", "keywords": [], "description": "",
         "family": None},
    ]
    assert [e["id"] for e in px.search(entries, "malm")] == ["a"]


def test_a_name_match_still_outranks_a_family_match():
    entries = [
        {"id": "a", "name": "Chest", "keywords": [], "description": "",
         "family": "Sofa collection"},
        {"id": "b", "name": "Sofa", "keywords": [], "description": "",
         "family": None},
    ]
    assert [e["id"] for e in px.search(entries, "sofa")] == ["b", "a"]


def test_an_entry_without_a_family_key_still_scores():
    # search() is called with hand-built entries all over this suite; a
    # missing "family" must read as "no family", not raise.
    assert px.score({"name": "Chair", "keywords": [], "description": ""},
                    "chair") > 0


def test_a_changed_collection_invalidates_the_cache(tmp_path):
    library = _library_at(
        tmp_path, ("pack/chair", _unnamed_part("Chair")))
    collection = tmp_path / "pack" / "collection.json"
    collection.write_text(json.dumps({"label": "One"}), encoding="utf8")

    index = px.scan(library)
    assert px.is_cache_valid(index, library)

    # Editing only the collection - no manifest touched - must still be seen.
    os.utime(str(collection), (2000000000, 2000000000))
    assert not px.is_cache_valid(index, library)


def test_an_added_collection_invalidates_the_cache(tmp_path):
    library = _library_at(
        tmp_path, ("pack/chair", _unnamed_part("Chair")))
    index = px.scan(library)
    assert px.is_cache_valid(index, library)

    (tmp_path / "pack" / "collection.json").write_text(
        json.dumps({"label": "New"}), encoding="utf8")
    assert not px.is_cache_valid(index, library)


def test_a_library_with_no_collections_stays_cache_valid(tmp_path):
    # Both sides of the comparison are empty dicts - this must not read as
    # a difference and force a rescan on every single open.
    library = _library_at(
        tmp_path, ("loose/chair", _unnamed_part("Chair")))
    index = px.scan(library)
    assert px.is_cache_valid(index, library)


def test_a_version_two_cache_is_refused(tmp_path):
    # v2 entries have no "family" key; handing one to the panel would be a
    # KeyError at card-build time, so it must be rejected outright rather
    # than healed - the same call made when variants became params.
    library = _library_at(
        tmp_path, ("pack/chair", _unnamed_part("Chair")))
    path = str(tmp_path / "cache.json")
    px.save_cache(px.scan(library), path)
    with open(path, encoding="utf8") as handle:
        payload = json.load(handle)
    payload["version"] = 2
    with open(path, "w", encoding="utf8") as handle:
        json.dump(payload, handle)

    assert px.load_cache(path) is None


def test_a_saved_cache_round_trips_its_collection_mtimes(tmp_path):
    library = _library_at(
        tmp_path, ("pack/chair", _unnamed_part("Chair")))
    (tmp_path / "pack" / "collection.json").write_text(
        json.dumps({"label": "Pack"}), encoding="utf8")
    path = str(tmp_path / "cache.json")
    px.save_cache(px.scan(library), path)

    assert px.is_cache_valid(px.load_cache(path), library)


def test_collection_mtimes_skips_a_file_deleted_after_the_walk(
        tmp_path, monkeypatch):
    # The walk (collection_paths) and the stat (getmtime) are two separate
    # filesystem reads; something can delete the file in between. Simulate
    # that race by handing collection_mtimes a path the walk "found" that no
    # longer exists by the time it stats - it must not raise.
    library = _library_at(
        tmp_path, ("pack/chair", _unnamed_part("Chair")))
    collection_path = tmp_path / "pack" / "collection.json"
    collection_path.write_text(
        json.dumps({"label": "Pack"}), encoding="utf8")
    vanished = str(collection_path)
    collection_path.unlink()
    monkeypatch.setattr(px.pc, "collection_paths", lambda library_dir: [vanished])

    assert px.collection_mtimes(library) == {}


# -- facet_groups ---------------------------------------------------------

def test_facet_groups_omits_a_room_with_no_parts():
    # Office is in CATEGORY_FACETS' vocabulary but no part references it.
    groups = px.facet_groups(CATEGORY_ENTRIES, CATEGORY_FACETS, "room")
    assert "Office" not in [g["value"] for g in groups]


def test_facet_groups_labels_and_icons_come_from_the_facet():
    groups = _by_value(
        px.facet_groups(CATEGORY_ENTRIES, CATEGORY_FACETS, "room"))
    assert groups["Bathroom"]["label"] == "Bathroom"
    assert groups["Bathroom"]["icon"] == "bathroom.svg"
    assert groups["Kitchen"]["icon"] is None


def test_facet_groups_counts_a_multi_room_part_in_each_of_its_rooms():
    # wc-a is in both Bathroom and Kitchen; each count includes it once.
    groups = _by_value(
        px.facet_groups(CATEGORY_ENTRIES, CATEGORY_FACETS, "room"))
    assert groups["Bathroom"]["count"] == 3     # wc-a, basin-a, noelement-a
    assert groups["Kitchen"]["count"] == 3      # wc-a, cabinet-a, chair-a


def test_facet_groups_counts_a_repeated_value_once():
    # The count is DISTINCT parts, not facet declarations.
    entries = [{"id": "a", "facets": {"room": ["Living", "Living"]}}]
    groups = px.facet_groups(entries, {"room": {"values": {}}}, "room")
    assert [g["count"] for g in groups] == [1]


def test_facet_groups_puts_a_part_with_no_room_under_unclassified():
    groups = _by_value(
        px.facet_groups(CATEGORY_ENTRIES, CATEGORY_FACETS, "room"))
    assert groups[px.UNCLASSIFIED]["count"] == 1    # noroom-a


def test_facet_groups_orders_by_label_with_unclassified_last():
    groups = px.facet_groups(CATEGORY_ENTRIES, CATEGORY_FACETS, "room")
    assert [g["value"] for g in groups] == [
        "Bathroom", "Kitchen", px.UNCLASSIFIED]


def test_facet_groups_has_no_children_key():
    # The element level went with the catalogue screen. A leftover children
    # key would invite a future caller to rebuild it.
    groups = px.facet_groups(CATEGORY_ENTRIES, CATEGORY_FACETS, "room")
    assert all("children" not in g for g in groups)
