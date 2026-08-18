# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Verifies the REAL bundled seed library (archplus/tools/partslib/library/), not a
# tmp_path fixture. A malformed shipped manifest would otherwise reach a user
# as a silently empty panel with a console error nobody reads, so this test
# is the headless substitute for eyeballing the panel inside FreeCAD.
#
# Deliberately does NOT import partslib_object - it imports FreeCAD at module
# scope and would fail under plain pytest.
#
# These were written as guards that would arm themselves once real content
# landed under library/, back when it shipped empty. It no longer does: the
# catalogue now carries parts across every room in the vocabulary, so each
# loop below actually iterates and actually checks something.


import json
import os

from archplus.tools.partslib import geometry as partslib_geometry
from archplus.tools.partslib import index as partslib_index
from archplus.tools.partslib import manifest as partslib_manifest

_PARTSLIB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIBRARY_DIR = os.path.join(_PARTSLIB, "library")


def _scan():
    return partslib_index.scan(LIBRARY_DIR)


def test_scan_reports_zero_errors_for_the_shipped_library():
    index = _scan()
    assert index["errors"] == []


def test_every_entry_facet_value_exists_in_the_shipped_vocabulary():
    # Safety net, not an independent check today: validate_manifest() already
    # gates entry inclusion in scan(), so a part with a facet value outside
    # the vocabulary never reaches index["entries"] at all - it is excluded
    # and reported as a scan error first, which
    # test_scan_reports_zero_errors_for_the_shipped_library already catches.
    # This test only earns its keep if entry-inclusion and error-reporting
    # are ever decoupled from each other in a future refactor.
    index = _scan()
    facets = index["facets"]
    for entry in index["entries"]:
        for facet_name, value in (entry.get("facets") or {}).items():
            assert facet_name in facets, (
                "entry %r declares unknown facet %r" % (entry["id"], facet_name))
            allowed = partslib_manifest.facet_values(facets, facet_name)
            values = value if isinstance(value, list) else [value]
            for item in values:
                assert item in allowed, (
                    "entry %r declares unknown value %r for facet %r"
                    % (entry["id"], item, facet_name))


def test_every_entry_resolves_to_a_builder():
    # Local builder.py or the asset fallback - every part must end up with a
    # callable, and the fallback path must not raise for a part that has no
    # builder.py of its own.
    index = _scan()
    for entry in index["entries"]:
        manifest = partslib_manifest.load_manifest(entry["path"])
        assert callable(partslib_geometry.select_builder(
            manifest, entry["dir"])), entry["id"]


def test_facets_json_is_valid():
    # The one thing the shipped library still asserts positively even with
    # zero parts: the vocabulary itself (library/facets.json) is well-formed.
    # Real parts are authored against this file, so it must stay valid on
    # its own, independent of whether any part currently references it.
    with open(os.path.join(LIBRARY_DIR, "facets.json")) as handle:
        doc = json.load(handle)
    assert partslib_manifest.validate_facets(doc) == []


def test_the_library_is_not_empty():
    # Guards the loops below from silently going vacuous again if the
    # catalogue is ever emptied or the scan path breaks.
    assert len(_scan()["entries"]) > 20


def test_every_facet_icon_referenced_exists_on_disk():
    # facets.json names icons by bare filename; a value whose icon is
    # missing renders as a blank card in the category grid with nothing in
    # the console to say why. Four element icons shipped missing exactly
    # this way before the catalogue had parts to surface them.
    icon_dir = os.path.join(_PARTSLIB, "resources", "icons", "facets")
    facets = _scan()["facets"]
    missing = []
    for facet, spec in facets.items():
        for value in (spec.get("values") or {}):
            icon = partslib_manifest.facet_icon(facets, facet, value)
            if icon and not os.path.exists(os.path.join(icon_dir, icon)):
                missing.append("%s/%s -> %s" % (facet, value, icon))
    assert missing == []


def test_every_placement_host_is_a_known_host():
    from archplus.tools.partslib import placement as partslib_placement
    for entry in _scan()["entries"]:
        manifest = partslib_manifest.load_manifest(entry["path"])
        placement = manifest.get("placement") or {}
        host = placement.get("host", partslib_placement.DEFAULT_HOST)
        assert host in partslib_placement.HOSTS, (
            "%s declares unknown host %r" % (entry["id"], host))


def test_wall_and_ceiling_hosted_parts_exist():
    # Every part was floor-hosted for a long time, which left the wall and
    # ceiling branches of partslib_placement covered only by unit tests
    # with synthetic data. Keep at least one real part exercising a
    # non-floor host so that stays untrue.
    hosts = set()
    for entry in _scan()["entries"]:
        manifest = partslib_manifest.load_manifest(entry["path"])
        hosts.add((manifest.get("placement") or {}).get("host", "free"))
    assert "wall" in hosts


def test_every_part_lives_under_a_family_folder():
    # The library tree is also the import tree: a part's builder.py is
    # imported by the part's path. A part directly at the library root is
    # allowed by the rules (reserved for one-off imports) but nothing
    # shipped today is one - all 31 are the house style.
    for path in partslib_index.manifest_paths(LIBRARY_DIR):
        relative = os.path.relpath(os.path.dirname(path), LIBRARY_DIR)
        segments = relative.replace(os.sep, "/").split("/")
        assert segments[0] == "basic", (
            "%s is not under library/basic/" % (path,))
        assert len(segments) == 2, (
            "%s should be library/basic/<part>/, got %r" % (path, relative))


def test_every_shipped_id_is_derived_from_its_folder():
    # No shipped part pins an explicit id. The override exists for renames;
    # using it by default would let a folder and an id drift apart.
    index = _scan()
    for entry in index["entries"]:
        manifest = partslib_manifest.load_manifest(entry["path"])
        assert "id" not in manifest, (
            "%s pins an explicit id" % (entry["path"],))
        expected = os.path.relpath(
            entry["dir"], LIBRARY_DIR).replace(os.sep, "/")
        assert entry["id"] == expected


def test_shipped_ids_are_unique():
    index = _scan()
    ids = [e["id"] for e in index["entries"]]
    assert len(ids) == len(set(ids))
    assert len(ids) == 31


def test_every_local_builder_imports_and_exposes_build():
    # A builder.py that imports FreeCAD at module scope, or that names its
    # entry point anything but build(), fails here rather than at insert
    # time inside FreeCAD.
    index = _scan()
    checked = 0
    for entry in index["entries"]:
        if not partslib_geometry.has_local_builder(entry["dir"]):
            continue
        assert callable(partslib_geometry.load_local_builder(entry["dir"])), (
            "%s has no usable build()" % (entry["id"],))
        checked += 1
    assert checked > 0, "no part has a builder.py yet"


def _entry(index, part_id):
    """Match either a full id or a part folder within any family."""
    for entry in index["entries"]:
        if entry["id"] == part_id or entry["id"].endswith("/" + part_id):
            return entry
    raise AssertionError("no such part %r" % (part_id,))


def _params(part_id, overrides=None):
    """Merged params for one shipped part, as a builder would receive them."""
    index = _scan()
    data = partslib_manifest.load_manifest(_entry(index, part_id)["path"])
    return partslib_manifest.merge_params(data, overrides)


def test_derived_kitchen_and_sanitary_params_are_declared_auto():
    for part_id, name in (("base-cabinet", "DoorCount"),
                          ("wall-cabinet", "DoorCount"),
                          ("wardrobe", "DoorCount"),
                          ("gas-hob", "Width"),
                          ("vanity", "BasinWidth")):
        assert _params(part_id)[name] is None, (
            "%s should declare %s as auto" % (part_id, name))


def test_kitchen_and_sanitary_parts_declare_no_variants():
    index = _scan()
    for part_id in ("base-cabinet", "wall-cabinet", "wardrobe",
                    "gas-hob", "vanity"):
        data = partslib_manifest.load_manifest(_entry(index, part_id)["path"])
        assert "variants" not in data


def test_every_auto_param_is_derived_by_its_builder():
    # The suite cannot call build() - the builders reach shapes.py, which
    # needs Part - so a forgotten derivation would otherwise surface only
    # inside FreeCAD, as int(None). Reading the source is the weaker but
    # available check: each auto param must either be consumed by build(),
    # with its own nearby None test, or be reported by derived_params().
    import io
    import sys

    index = _scan()
    for entry in index["entries"]:
        data = partslib_manifest.load_manifest(entry["path"])
        auto = [name for name, spec
                in partslib_manifest.param_specs(data).items()
                if spec.get("default") == partslib_manifest.AUTO]
        if not auto:
            continue
        builder_path = os.path.join(entry["dir"], "builder.py")
        assert os.path.exists(builder_path), (
            "%s declares auto params but ships no builder.py"
            % (entry["id"],))
        with io.open(builder_path, "r", encoding="utf8") as handle:
            source = handle.read()
        lines = source.splitlines()
        builder = partslib_geometry.load_local_builder(entry["dir"])
        module = sys.modules[builder.__module__]
        reporter = getattr(module, "derived_params", None)
        reported = reporter({}) if callable(reporter) else {}
        for name in auto:
            fetch = 'params.get("%s")' % name
            consumed = False
            for line_no, line in enumerate(lines):
                if fetch not in line:
                    continue
                nearby = "\n".join(lines[line_no:line_no + 3])
                if "is None" in nearby:
                    consumed = True
                    break
            assert consumed or name in reported, (
                "%s declares %s as auto but it is neither consumed by build() "
                "with an associated None test nor reported by derived_params()"
                % (entry["id"], name))


def test_dining_table_reports_seats_for_its_shipped_sizes():
    # The one derivation the suite can actually execute: it is pure Python in
    # a module-level function, so it needs no Part and no FreeCAD.
    index = _scan()
    builder_dir = _entry(index, "dining-table")["dir"]
    module = partslib_geometry.load_local_builder(builder_dir).__module__
    import sys
    derived = sys.modules[module].derived_params
    assert derived({"Width": 1200})["SeatCount"] == 4
    assert derived({"Width": 1600})["SeatCount"] == 6
    assert derived({"Width": 2000})["SeatCount"] == 8
    assert derived({"Width": 300})["SeatCount"] == 2      # clamped floor


def test_derived_furniture_params_are_declared_auto():
    for part_id, name in (("sofa", "Width"),
                          ("dining-table", "SeatCount"),
                          ("chest-of-drawers", "Height"),
                          ("bookcase", "ShelfCount"),
                          ("media-unit", "ShelfCount")):
        assert _params(part_id)[name] is None, (
            "%s should declare %s as auto" % (part_id, name))


def test_furniture_parts_declare_no_variants():
    index = _scan()
    for part_id in ("sofa", "dining-table", "chest-of-drawers",
                    "bookcase", "media-unit"):
        data = partslib_manifest.load_manifest(_entry(index, part_id)["path"])
        assert "variants" not in data


def test_a_65_inch_television_on_a_stand_is_reachable():
    # The cell the old flat variant list silently lacked: it shipped
    # 55-on-stand, 55-wall and 65-wall, but never 65-on-stand.
    index = _scan()
    data = partslib_manifest.load_manifest(_entry(index, "television")["path"])
    params = partslib_manifest.merge_params(
        data, {"ScreenSize": 65, "Mounting": "stand"})
    assert params["ScreenSize"] == 65
    assert params["Mounting"] == "stand"
    assert partslib_manifest.resolve_placement(data, params) == {
        "host": "floor", "offset": 0}


def test_a_wall_mounted_television_is_wall_hosted():
    index = _scan()
    data = partslib_manifest.load_manifest(_entry(index, "television")["path"])
    params = partslib_manifest.merge_params(data, {"Mounting": "wall"})
    placement = partslib_manifest.resolve_placement(data, params)
    assert placement["host"] == "wall"
    # The old 65-inch wall variant used 1050; approved design deliberately
    # collapses both sizes to one 1100 offset, so per-size offsets must fail.
    assert placement["offset"] == 1100


def test_television_size_drives_the_panel_dimensions():
    merged = _params("television")
    assert merged["Width"] is None
    assert merged["Height"] is None


def test_curtain_folds_are_derived():
    assert _params("curtain")["FoldCount"] is None


def test_no_shipped_manifest_declares_variants():
    index = _scan()
    for entry in index["entries"]:
        data = partslib_manifest.load_manifest(entry["path"])
        assert "variants" not in data, (
            "%s still declares variants" % (entry["id"],))


def test_every_part_marks_at_least_one_primary_param_explicitly():
    index = _scan()
    for entry in index["entries"]:
        data = partslib_manifest.load_manifest(entry["path"])
        marked = [name for name, spec
                  in partslib_manifest.param_specs(data).items()
                  if (spec or {}).get("ui") == "primary"]
        assert marked, "%s marks no ui:primary param" % (entry["id"],)


def test_every_primary_param_name_is_declared():
    index = _scan()
    for entry in index["entries"]:
        data = partslib_manifest.load_manifest(entry["path"])
        specs = partslib_manifest.param_specs(data)
        for name in partslib_manifest.primary_params(data):
            assert name in specs, (
                "%s marks unknown primary %r" % (entry["id"], name))


def test_a_bath_width_screen_is_reachable_at_walk_in_height():
    # The old list offered "Bath screen" (800 x 1400) and two walk-in widths
    # at 1900, so an 800-wide screen at 1900 could not be expressed at all.
    index = _scan()
    data = partslib_manifest.load_manifest(
        _entry(index, "shower-screen")["path"])
    merged = partslib_manifest.merge_params(
        data, {"Width": 800, "Height": 1900})
    assert merged["Width"] == 800
    assert merged["Height"] == 1900
