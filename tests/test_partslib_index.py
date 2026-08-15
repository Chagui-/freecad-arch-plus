import json
import os

import partslib_index as px

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
