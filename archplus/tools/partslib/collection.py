# SPDX-License-Identifier: LGPL-2.1-or-later
#
# PartsLib collections - the optional collection.json that gives a group of
# parts a family name ("IKEA Malm"), shown under the part name on its card.
#
# Like index.py and manifest.py, this module is deliberately FREE OF FREECAD
# IMPORTS - it is filesystem and JSON only, so the resolution rules can be
# unit-tested headlessly. Do not add FreeCAD, Part or PySide dependencies
# here.
#
# WHY A SEPARATE FILE PER COLLECTION rather than a "family" field in every
# part.json: the string would be repeated in every manifest of a pack and
# would drift - one part saying "IKEA Malm" and its neighbour "Ikea MALM".
# Authored once per collection, it cannot.

import json
import os

COLLECTION_FILENAME = "collection.json"
SCHEMA_VERSION = 1


def load_collection(path):
    """Read a collection.json. Raises ValueError if missing or malformed."""
    try:
        with open(path, "r", encoding="utf8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ValueError("cannot read %s: %s" % (path, exc))
    if not isinstance(data, dict):
        raise ValueError("%s: must be a JSON object" % (path,))
    return data


def validate_collection(data):
    """Errors in a loaded collection document; empty list means valid.

    `label` is OPTIONAL and its absence is not a warning: an unlabelled
    collection means "these parts belong to no brand", which is exactly
    library/basic/'s state. Badging all 31 generic parts with an identical
    "Basic" would repeat the low-information card line this whole change
    removes."""
    errors = []
    if data.get("schema") not in (None, SCHEMA_VERSION):
        errors.append("unsupported schema version %r (expected %d)"
                      % (data.get("schema"), SCHEMA_VERSION))
    for field in ("label", "description"):
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            errors.append("%r must be a string" % (field,))
    return errors


def collection_paths(library_dir):
    """Every collection.json under the library, in a stable order.

    Used for cache invalidation, the same way index.manifest_paths() is:
    editing a collection's label must make the cached index stale."""
    found = []
    for root, _dirs, files in os.walk(library_dir):
        if COLLECTION_FILENAME in files:
            found.append(os.path.join(root, COLLECTION_FILENAME))
    return sorted(found)


def collection_path(part_dir, library_dir):
    """The collection.json governing `part_dir`, or None.

    Searches upward from the part's PARENT (a collection.json inside a part
    folder would be a collection of one, which is not a thing) and stops
    after testing the library root, so a stray collection.json above the
    library cannot leak in. The nearest ancestor wins, which is what lets
    library/ikea/malm/ override library/ikea/."""
    part_dir = os.path.abspath(part_dir)
    library_dir = os.path.abspath(library_dir)
    current = os.path.dirname(part_dir)
    while True:
        candidate = os.path.join(current, COLLECTION_FILENAME)
        if os.path.exists(candidate):
            return candidate
        if os.path.normcase(current) == os.path.normcase(library_dir):
            return None
        parent = os.path.dirname(current)
        if parent == current:
            # Filesystem root reached without meeting library_dir: the part
            # is not under the library at all. Nothing to inherit.
            return None
        current = parent


def resolve(part_dir, library_dir, cache=None):
    """(label, description, errors) for one part's collection.

    `label` and `description` are None when there is no collection, when it
    declares neither, or when it is broken - a bad collection must never hide
    the parts inside it, so every failure returns "no family" alongside the
    error rather than raising.

    `cache` is an optional dict the caller reuses across a scan so one
    collection.json is read once instead of once per part in it."""
    path = collection_path(part_dir, library_dir)
    if path is None:
        return (None, None, [])
    if cache is not None and path in cache:
        return cache[path]

    try:
        data = load_collection(path)
    except ValueError as exc:
        result = (None, None, [str(exc)])
    else:
        errors = ["%s: %s" % (path, message)
                  for message in validate_collection(data)]
        if errors:
            result = (None, None, errors)
        else:
            result = (data.get("label") or None,
                      data.get("description") or None,
                      [])
    if cache is not None:
        cache[path] = result
    return result
