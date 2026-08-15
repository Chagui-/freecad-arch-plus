# SPDX-License-Identifier: LGPL-2.1-or-later
#
# PartsLib index - scans the bundled library, validates every manifest and
# caches the result so that browsing never touches geometry.
#
# Like partslib_manifest, this module is deliberately FREE OF FreeCAD IMPORTS
# so the index, its cache invalidation and its search can be unit-tested
# headlessly. Do not add FreeCAD, Part or PySide dependencies here.

import json
import os

import partslib_manifest as pm

FACETS_FILENAME = "facets.json"
MANIFEST_FILENAME = "part.json"
CACHE_VERSION = 1


def manifest_paths(library_dir):
    """Every part.json under the library, in a stable order."""
    found = []
    for root, _dirs, files in os.walk(library_dir):
        if MANIFEST_FILENAME in files:
            found.append(os.path.join(root, MANIFEST_FILENAME))
    return sorted(found)


def scan(library_dir):
    """Read the vocabulary and every manifest under `library_dir`."""
    errors = []
    warnings = []
    entries = []

    facets_path = os.path.join(library_dir, FACETS_FILENAME)
    try:
        facets = pm.load_manifest(facets_path)
    except ValueError as exc:
        return {"facets": {}, "entries": [],
                "errors": ["%s: %s" % (FACETS_FILENAME, exc)],
                "warnings": []}
    errors.extend(pm.validate_facets(facets))

    seen = {}
    for path in manifest_paths(library_dir):
        try:
            data = pm.load_manifest(path)
        except ValueError as exc:
            errors.append(str(exc))
            continue

        part_errors, part_warnings = pm.validate_manifest(data, facets)
        warnings.extend("%s: %s" % (path, w) for w in part_warnings)
        if part_errors:
            errors.extend("%s: %s" % (path, e) for e in part_errors)
            continue

        part_id = data["id"]
        if part_id in seen:
            errors.append("duplicate id %r in %s and %s"
                          % (part_id, seen[part_id], path))
            continue
        seen[part_id] = path

        entries.append({
            "id": part_id,
            "name": data["name"],
            "description": data.get("description", ""),
            "keywords": list(data.get("keywords", [])),
            "facets": data.get("facets", {}),
            "variants": pm.variant_labels(data),
            "path": path,
            "dir": os.path.dirname(path),
            "mtime": os.path.getmtime(path),
        })

    return {"facets": facets, "entries": entries,
            "errors": errors, "warnings": warnings}


def is_cache_valid(cache, library_dir):
    """True when no manifest has been added, removed or modified."""
    if not cache or cache.get("entries") is None:
        return False
    cached = {e["path"]: e["mtime"] for e in cache["entries"]}
    # A manifest that failed validation is absent from entries, so a library
    # containing one always reads as stale and rescans. That is correct - the
    # rescan is what reports its errors again.
    for path in manifest_paths(library_dir):
        if path not in cached:
            return False
    for path, mtime in cached.items():
        if not os.path.exists(path) or os.path.getmtime(path) != mtime:
            return False
    return True


def save_cache(index, path):
    """Persist an index. Errors and warnings are not cached - a rescan
    regenerates them."""
    payload = {"version": CACHE_VERSION,
               "facets": index["facets"],
               "entries": index["entries"]}
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with open(path, "w", encoding="utf8") as handle:
        json.dump(payload, handle)


def load_cache(path):
    """Read a cached index, or None when absent or unusable."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf8") as handle:
            cache = json.load(handle)
    except (OSError, ValueError):
        return None
    if cache.get("version") != CACHE_VERSION:
        return None
    return cache
