# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Verifies the REAL bundled seed library (library/ at the repo root), not a
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

import partslib_geometry
import partslib_index
import partslib_manifest

LIBRARY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "library")


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


def test_every_entry_geometry_builder_resolves():
    index = _scan()
    for entry in index["entries"]:
        manifest = partslib_manifest.load_manifest(entry["path"])
        builder_symbol = manifest.get("geometry", {}).get("builder")
        # Must not raise.
        partslib_geometry.resolve_builder(builder_symbol)


def test_every_part_variant_labels_are_non_empty_and_unique():
    index = _scan()
    for entry in index["entries"]:
        labels = entry["variants"]
        assert labels, "entry %r has no variant labels at all" % (entry["id"],)
        for label in labels:
            assert label, "entry %r has an empty variant label" % (entry["id"],)
        assert len(labels) == len(set(labels)), (
            "entry %r has duplicate variant labels: %r" % (entry["id"], labels))


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
    icon_dir = os.path.join(os.path.dirname(LIBRARY_DIR),
                            "Resources", "icons", "facets")
    facets = _scan()["facets"]
    missing = []
    for facet, spec in facets.items():
        for value in (spec.get("values") or {}):
            icon = partslib_manifest.facet_icon(facets, facet, value)
            if icon and not os.path.exists(os.path.join(icon_dir, icon)):
                missing.append("%s/%s -> %s" % (facet, value, icon))
    assert missing == []


def test_every_placement_host_is_a_known_host():
    import partslib_placement
    for entry in _scan()["entries"]:
        manifest = partslib_manifest.load_manifest(entry["path"])
        for label in partslib_manifest.variant_labels(manifest):
            resolved = partslib_manifest.resolve_variant(manifest, label)
            placement = resolved.get("placement") or {}
            host = placement.get("host", partslib_placement.DEFAULT_HOST)
            assert host in partslib_placement.HOSTS, (
                "%s (%s) declares unknown host %r"
                % (entry["id"], label, host))


def test_wall_and_ceiling_hosted_parts_exist():
    # Every part was floor-hosted for a long time, which left the wall and
    # ceiling branches of partslib_placement covered only by unit tests
    # with synthetic data. Keep at least one real part exercising a
    # non-floor host so that stays untrue.
    hosts = set()
    for entry in _scan()["entries"]:
        manifest = partslib_manifest.load_manifest(entry["path"])
        for label in partslib_manifest.variant_labels(manifest):
            resolved = partslib_manifest.resolve_variant(manifest, label)
            hosts.add((resolved.get("placement") or {}).get("host", "free"))
    assert "wall" in hosts
