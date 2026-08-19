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
from archplus.tools.partslib import units as partslib_units

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


def test_a_hobs_width_follows_its_burner_count():
    # The only kitchen derivation left, and the shape "auto" is now limited
    # to: a count the user knows (4 burners) yielding a dimension they would
    # otherwise look up (600mm).
    assert _params("gas-hob")["Width"] is None
    assert _params("gas-hob")["BurnerCount"] == 4


def test_cabinet_door_counts_are_not_parameters():
    # They used to be declared "auto", which meant the property editor
    # showed 0 forever: no shape can report how many doors it has, so the
    # write-back had nothing to measure. The builder decides instead.
    for part_id in ("base-cabinet", "wall-cabinet", "wardrobe"):
        assert "DoorCount" not in _params(part_id), (
            "%s should let its builder decide the door count" % (part_id,))


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
    # available check: each auto param must be consumed by build() with its
    # own nearby None test.
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
            assert consumed, (
                "%s declares %s as auto but build() never tests it for None, "
                "so the builder would reach int(None) in FreeCAD"
                % (entry["id"], name))


def test_derived_furniture_dimensions_are_declared_auto():
    # Both survivors run the same way round: a count the user knows drives a
    # dimension they would otherwise have to look up.
    for part_id, count, dimension in (("sofa", "SeatCount", "Width"),
                                      ("chest-of-drawers", "DrawerCount",
                                       "Height")):
        merged = _params(part_id)
        assert merged[dimension] is None, (
            "%s should declare %s as auto" % (part_id, dimension))
        assert merged[count] is not None, (
            "%s needs a real %s to derive %s from"
            % (part_id, count, dimension))


def test_shelf_and_seat_counts_are_not_parameters():
    # Counts derived FROM a dimension the user already set are arithmetic,
    # not a control - and no shape can report them, so they read 0.
    for part_id, name in (("bookcase", "ShelfCount"),
                          ("media-unit", "ShelfCount"),
                          ("dining-table", "SeatCount")):
        assert name not in _params(part_id), (
            "%s should let its builder decide %s" % (part_id, name))


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


def test_a_curtain_is_just_a_width_and_a_height():
    # Fullness, rail diameter, header height and fold count were all things
    # nobody specifies about a curtain; the builder decides them now.
    assert sorted(_params("curtain")) == ["Height", "Width"]


def test_the_curtain_fabric_is_a_wave_not_a_row_of_bulges():
    # The fabric is a thin sheet whose plane waves in and out - not the fat
    # overlapping cylinders it used to be. The sampler that lays out that
    # wave is pure math with no Part dependency, so it is exercised here,
    # headlessly, rather than trusted from inside FreeCAD.
    from archplus.tools.partslib.library.basic.curtain import builder

    span, folds, fullness, thickness = 1500.0, 12, 110.0, 12.0
    points = builder._serpentine_samples(span, folds, fullness, thickness)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]

    # The wave runs the whole span and starts and ends on the centreline,
    # where the fabric meets the rail's end caps.
    assert xs[0] == 0.0
    assert xs[-1] == span
    assert abs(ys[0] - fullness / 2.0) < 1e-9
    assert abs(ys[-1] - fullness / 2.0) < 1e-9
    # Monotonic along the rail: the sheet never doubles back on itself.
    assert xs == sorted(xs)
    # Wave plus its own thickness stays inside the fullness envelope.
    assert min(ys) >= thickness / 2.0 - 1e-9
    assert max(ys) <= fullness - thickness / 2.0 + 1e-9
    # Twelve folds means twelve alternating bulges - not twelve tubes.
    bulges = sum(1 for i in range(1, len(ys) - 1)
                 if (ys[i] - ys[i - 1]) * (ys[i + 1] - ys[i]) < 0)
    assert bulges == folds


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


def test_every_shipped_length_reads_as_a_drawing_dimension():
    # The panel pins Length fields to cm (inches under an imperial schema)
    # because the whole catalogue is dimensioned at that scale. A part whose
    # default lands outside it - a 12 m partition, a 0.5 mm gasket - must say
    # so with a per-field "unit" override rather than ship a field reading
    # 1200.0 or 0.05. This is the check that arms itself when it does.
    index = _scan()
    for entry in index["entries"]:
        manifest = partslib_manifest.load_manifest(entry["path"])
        for name, spec in (partslib_manifest.param_specs(manifest)).items():
            if spec.get("type") != "Length":
                continue
            default = spec.get("default")
            if not isinstance(default, (int, float)):
                continue        # "auto" - measured from the built shape
            for imperial in (False, True):
                unit = partslib_units.display_unit(spec, imperial)
                assert partslib_units.is_readable(default, unit), (
                    "%s: %s default %s reads as %s"
                    % (entry["id"], name, default,
                       partslib_units.format_length(default, unit)))
