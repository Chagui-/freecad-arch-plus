import json
import os

from tools.partslib import index as px

FACETS = {
    "function": {"multi": False, "values": {"Sanitary": {}, "Seating": {}}},
    "element": {"multi": False, "values": {"WC": {}, "Chair": {}}},
    "room": {"multi": True, "values": {"Bathroom": {}, "Kitchen": {}}},
}


def _library(tmp_path, *parts):
    (tmp_path / "facets.json").write_text(json.dumps(FACETS), encoding="utf8")
    for part in parts:
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
        "geometry": {"builder": "asset.single"},
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


def test_scan_records_variant_labels(tmp_path):
    part = _part("wc-a", "WC A", variants=[{"label": "360 mm"},
                                           {"label": "490 mm"}])
    index = px.scan(_library(tmp_path, part))
    assert index["entries"][0]["variants"] == ["360 mm", "490 mm"]


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


# -- category_tree ------------------------------------------------------

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


def test_category_tree_omits_a_room_with_no_parts():
    tree = px.category_tree(CATEGORY_ENTRIES, CATEGORY_FACETS)
    assert "Office" not in [g["value"] for g in tree]


def test_category_tree_orders_rooms_by_label_then_unclassified_last():
    tree = px.category_tree(CATEGORY_ENTRIES, CATEGORY_FACETS)
    assert [g["value"] for g in tree] == ["Bathroom", "Kitchen", px.UNCLASSIFIED]


def test_category_tree_room_labels_and_icons():
    groups = _by_value(px.category_tree(CATEGORY_ENTRIES, CATEGORY_FACETS))
    assert groups["Bathroom"]["label"] == "Bathroom"
    assert groups["Bathroom"]["icon"] == "bathroom.svg"
    assert groups["Kitchen"]["icon"] is None


def test_category_tree_counts_a_multi_room_part_once_per_room():
    groups = _by_value(px.category_tree(CATEGORY_ENTRIES, CATEGORY_FACETS))
    assert groups["Bathroom"]["count"] == 3  # wc-a, basin-a, noelement-a
    assert groups["Kitchen"]["count"] == 3   # wc-a, cabinet-a, chair-a


def test_category_tree_part_missing_primary_is_unclassified():
    groups = _by_value(px.category_tree(CATEGORY_ENTRIES, CATEGORY_FACETS))
    unclassified = groups[px.UNCLASSIFIED]
    assert unclassified["count"] == 1
    assert [c["value"] for c in unclassified["children"]] == ["Chair"]


def test_category_tree_children_are_scoped_to_their_room():
    groups = _by_value(px.category_tree(CATEGORY_ENTRIES, CATEGORY_FACETS))
    kitchen_children = sorted(c["value"] for c in groups["Kitchen"]["children"])
    assert kitchen_children == ["Cabinet", "Chair", "WC"]
    for child in groups["Kitchen"]["children"]:
        assert child["count"] == 1


def test_category_tree_part_missing_secondary_is_unclassified_child():
    groups = _by_value(px.category_tree(CATEGORY_ENTRIES, CATEGORY_FACETS))
    bathroom_children = {c["value"]: c for c in groups["Bathroom"]["children"]}
    assert px.UNCLASSIFIED in bathroom_children
    assert bathroom_children[px.UNCLASSIFIED]["count"] == 1


def test_category_tree_children_ordered_alphabetically_unclassified_last():
    groups = _by_value(px.category_tree(CATEGORY_ENTRIES, CATEGORY_FACETS))
    values = [c["value"] for c in groups["Bathroom"]["children"]]
    assert values[-1] == px.UNCLASSIFIED
    assert values[:-1] == sorted(values[:-1])


def test_category_tree_child_labels_come_from_the_element_facet():
    groups = _by_value(px.category_tree(CATEGORY_ENTRIES, CATEGORY_FACETS))
    labels = {c["value"]: c["label"] for c in groups["Kitchen"]["children"]}
    assert labels == {"WC": "Toilets", "Cabinet": "Cabinets", "Chair": "Chairs"}
