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

from . import manifest as pm

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
                "warnings": [], "facetsMtime": None}
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

        # The folder path IS the id unless the manifest pins one. Deriving it
        # makes a collision unrepresentable: two parts cannot share a path,
        # and every brand sells a mirror.
        part_id = data.get("id") or os.path.relpath(
            os.path.dirname(path), library_dir).replace(os.sep, "/")
        id_errors = pm.validate_part_id(part_id)
        if id_errors:
            errors.extend("%s: %s" % (path, e) for e in id_errors)
            continue

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
            "errors": errors, "warnings": warnings,
            "facetsMtime": os.path.getmtime(facets_path)}


def is_cache_valid(cache, library_dir):
    """True when no manifest has been added, removed or modified."""
    if not cache or cache.get("entries") is None:
        return False
    facets_path = os.path.join(library_dir, FACETS_FILENAME)
    if not os.path.exists(facets_path):
        return False
    if cache.get("facetsMtime") != os.path.getmtime(facets_path):
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
    regenerates them.

    facetsMtime was added without bumping CACHE_VERSION: a pre-existing cache
    on disk simply has no such key, so it reads back as None, compares
    unequal to the real facets.json mtime in is_cache_valid() and is treated
    as stale. That forces one rescan which then writes the key, so the
    migration is self-healing and needs no version gate."""
    payload = {"version": CACHE_VERSION,
               "facets": index["facets"],
               "entries": index["entries"],
               "facetsMtime": index.get("facetsMtime")}
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


UNCLASSIFIED = "(unclassified)"

# Match strength, strongest first. Name matches outrank keyword matches, which
# outrank description matches, so typing "chair" finds the chair rather than
# everything that mentions one.
_SCORE_NAME_EXACT = 100
_SCORE_NAME_PREFIX = 80
_SCORE_NAME_SUBSTRING = 60
_SCORE_KEYWORD_EXACT = 50
_SCORE_KEYWORD_SUBSTRING = 40
_SCORE_DESCRIPTION = 20


def score(entry, query):
    """Match strength of one entry against a query. 0 means no match."""
    query = (query or "").strip().lower()
    if not query:
        return 1

    name = (entry.get("name") or "").lower()
    if name == query:
        return _SCORE_NAME_EXACT
    if name.startswith(query):
        return _SCORE_NAME_PREFIX
    if query in name:
        return _SCORE_NAME_SUBSTRING

    keywords = [k.lower() for k in entry.get("keywords", [])]
    if any(query == k for k in keywords):
        return _SCORE_KEYWORD_EXACT
    if any(query in k for k in keywords):
        return _SCORE_KEYWORD_SUBSTRING

    if query in (entry.get("description") or "").lower():
        return _SCORE_DESCRIPTION
    return 0


def search(entries, query):
    """Entries matching `query`, best first, ties broken by name."""
    scored = [(score(e, query), e) for e in entries]
    matches = [(s, e) for s, e in scored if s > 0]
    matches.sort(key=lambda pair: (-pair[0], (pair[1].get("name") or "")))
    return [e for _s, e in matches]


def group_by(entries, facet):
    """Bucket entries by one facet value.

    A multi-valued facet legitimately places one entry in several buckets;
    entries that do not declare the facet land under UNCLASSIFIED."""
    groups = {}
    for entry in entries:
        value = (entry.get("facets") or {}).get(facet)
        if value is None or value == []:
            values = [UNCLASSIFIED]
        elif isinstance(value, list):
            values = value
        else:
            values = [value]
        for item in values:
            groups.setdefault(item, []).append(entry)
    return groups


def _sort_key(value, label):
    """UNCLASSIFIED always sorts last, everything else by its label."""
    return (value == UNCLASSIFIED, label)


def category_tree(entries, facets, primary="room", secondary="element"):
    """The two-level room/element tree the category screen renders.

    Only primary-facet values that at least one part actually declares are
    emitted - an empty room in the vocabulary is not advertised. `primary`
    is typically multi-valued, so one part is counted once under every
    group it belongs to. Within a group, `children` are the distinct
    `secondary` values of the parts in THAT group only, with counts scoped
    to the group; a part missing `secondary` lands under an UNCLASSIFIED
    child. A group's `count` is the number of distinct parts in it,
    computed independently of the children (it is not their sum)."""
    tree = []
    for value, group_entries in group_by(entries, primary).items():
        child_groups = group_by(group_entries, secondary)
        children = []
        for child_value, child_entries in child_groups.items():
            child_ids = set(e["id"] for e in child_entries)
            children.append({
                "value": child_value,
                "label": pm.facet_label(facets, secondary, child_value),
                "count": len(child_ids),
            })
        children.sort(key=lambda c: _sort_key(c["value"], c["label"]))

        part_ids = set(e["id"] for e in group_entries)
        tree.append({
            "value": value,
            "label": pm.facet_label(facets, primary, value),
            "icon": pm.facet_icon(facets, primary, value),
            "count": len(part_ids),
            "children": children,
        })

    tree.sort(key=lambda g: _sort_key(g["value"], g["label"]))
    return tree
