# Parts Library Single Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the ArchPlus Parts Library into one screen with room filter chips, give parts a collection/family name, and stop rebuilding geometry to recreate a preview image that is already committed on disk.

**Architecture:** `PartsLibraryPanel` loses its two-screen `QStackedWidget`; a wrapping row of room chips replaces the catalogue page. A new FreeCAD-free `collection.py` resolves each part's `collection.json` at scan time so the cached index carries a family name. Preview refresh becomes a decision (`thumbs.preview_plan`) rather than an unconditional pipeline: at manifest defaults the committed `thumbnail.jpg` is served directly, and `measure()` runs only when a field is actually waiting on it.

**Tech Stack:** Python 2/3-compatible style as used throughout the add-on, PySide (Qt) via FreeCAD 1.1, pytest with the repo-root `conftest.py` fakes.

**Spec:** `docs/superpowers/specs/2026-08-19-parts-library-single-screen-design.md`

## Global Constraints

- **Run tests with:** `uv run --no-project --with pytest python -m pytest -q` from the repo root. The system Python has no `pytest` and `python3 -m venv` fails here (no `python3.14-venv`). Baseline before any change: **314 passed**.
- **`collection.py`, `index.py` and `manifest.py` must stay free of `FreeCAD`, `FreeCADGui`, `Part`, `Sketcher` and `PySide` imports** — at module scope *and* inside functions. `archplus/common/tests/test_lazy_imports.py` is an AST guard over module-scope imports; the headless suite is what enforces the rest.
- **Every stylesheet selector that sets `background-color` must also set `color`, both from the same token set.** This is the structural rule stated at `gui.py:141`; it is what makes white-on-white impossible to reintroduce.
- **Licence header:** every new `.py` file starts with `# SPDX-License-Identifier: LGPL-2.1-or-later`.
- **Comments explain *why*, not *what*.** This codebase's comments carry the reasoning and the measurements behind a decision. Match that density — a new constant or branch that encodes a trade-off gets the trade-off written down.
- **Do not reformat or refactor code you are not otherwise changing.**
- Measured baselines to quote in comments where relevant (FreeCAD 1.1.1, all 31 parts, cold shape cache): `build_shape` 8.19 s total / 0.703 s worst; `measure` 4.34 s / 0.913 s worst; `render_shape` 2.82 s / 0.272 s worst; loading a committed `thumbnail.jpg` 0.001 s. Average click 0.496 s, worst 1.76 s.

---

### Task 1: `collection.py` — read and resolve `collection.json`

**Files:**
- Create: `archplus/tools/partslib/collection.py`
- Create: `archplus/tools/partslib/tests/test_partslib_collection.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `COLLECTION_FILENAME = "collection.json"`, `SCHEMA_VERSION = 1`
  - `load_collection(path) -> dict` (raises `ValueError`)
  - `validate_collection(data) -> list[str]`
  - `collection_paths(library_dir) -> list[str]`
  - `collection_path(part_dir, library_dir) -> str | None`
  - `resolve(part_dir, library_dir, cache=None) -> (label|None, description|None, list[str])`

- [ ] **Step 1: Write the failing tests**

Create `archplus/tools/partslib/tests/test_partslib_collection.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --no-project --with pytest python -m pytest archplus/tools/partslib/tests/test_partslib_collection.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'archplus.tools.partslib.collection'`

- [ ] **Step 3: Write the implementation**

Create `archplus/tools/partslib/collection.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --no-project --with pytest python -m pytest archplus/tools/partslib/tests/test_partslib_collection.py -q`
Expected: PASS, 13 tests.

- [ ] **Step 5: Run the whole suite**

Run: `uv run --no-project --with pytest python -m pytest -q`
Expected: 327 passed (314 baseline + 13).

- [ ] **Step 6: Commit**

```bash
git add archplus/tools/partslib/collection.py archplus/tools/partslib/tests/test_partslib_collection.py
git commit -m "Resolve a part's collection from the nearest collection.json"
```

---

### Task 2: Index carries the family; `facet_groups` replaces `category_tree`

**Files:**
- Modify: `archplus/tools/partslib/index.py`
- Modify: `archplus/tools/partslib/tests/test_partslib_index.py`
- Create: `archplus/tools/partslib/library/basic/collection.json`

**Interfaces:**
- Consumes: `collection.resolve`, `collection.collection_paths` (Task 1).
- Produces:
  - Every entry dict gains `"family"` (str|None) and `"familyDescription"` (str|None).
  - `index.facet_groups(entries, facets, facet="room") -> [{"value","label","icon","count"}]`
  - `index.collection_mtimes(library_dir) -> {path: mtime}`
  - `index.CACHE_VERSION == 3`
  - `index.category_tree` is **removed**.

- [ ] **Step 1: Write the failing tests**

Append to `archplus/tools/partslib/tests/test_partslib_index.py`. It already
has the helpers these use — `_library_at(tmp_path, *(folder, data))`,
`_unnamed_part(name, **over)`, `CATEGORY_ENTRIES`, `CATEGORY_FACETS` and
`_by_value(groups)` — plus `import json` and `import os` at the top. Do not
add a second library-building helper.

**Leave the nine existing `category_tree` tests in place.** `category_tree`
is not deleted in this task (its only caller, `gui._populateCategories`,
survives until Task 7); deleting it here would leave `gui.py` calling a
function that no longer exists, and no test imports that module, so the
suite would stay green over a broken panel. Task 7 removes the function, its
tests and its caller together.

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --no-project --with pytest python -m pytest archplus/tools/partslib/tests/test_partslib_index.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'facet_groups'`, plus `KeyError: 'family'`.

- [ ] **Step 3: Bump the cache version and import the new module**

In `archplus/tools/partslib/index.py`, change the imports and version:

```python
from . import collection as pc
from . import manifest as pm

FACETS_FILENAME = "facets.json"
MANIFEST_FILENAME = "part.json"
BUILDER_FILENAME = "builder.py"
CACHE_VERSION = 3
```

Extend the `save_cache` docstring's version history with one paragraph:

```
    CACHE_VERSION was bumped to 3 when entries started carrying "family" and
    "familyDescription". Like the 1 -> 2 bump and unlike the facetsMtime
    addition, a stale cache would hand the panel entries missing a key its
    card builder reads, so it must be refused outright rather than healed.
```

- [ ] **Step 4: Resolve the collection during the scan**

In `scan()`, create the cache before the manifest loop:

```python
    seen = {}
    # One dict for the whole scan: a 40-part collection would otherwise read
    # and parse its collection.json 40 times.
    collections = {}
    for path in manifest_paths(library_dir):
```

Then, in the same function, immediately before the `entries.append({...})` call:

```python
        family, family_description, family_errors = pc.resolve(
            part_dir, library_dir, collections)
        # A broken collection is reported but must NOT skip the part: the
        # parts are the library, the collection is a label on them.
        errors.extend(family_errors)

        entries.append({
            "id": part_id,
            "name": data["name"],
            "description": data.get("description", ""),
            "keywords": list(data.get("keywords", [])),
            "facets": data.get("facets", {}),
            "params": data.get("params", {}),
            "family": family,
            "familyDescription": family_description,
            "path": path,
            "dir": part_dir,
            "mtime": os.path.getmtime(path),
        })
```

Note `part_dir` is already bound earlier in the loop (it is used for the builder/asset check), and `"dir"` previously recomputed `os.path.dirname(path)` — use `part_dir` for both.

`family_errors` accumulates once per *part*, so two parts in one broken collection report it twice. That is deliberate: `errors` is a flat list the panel prints, and de-duplicating it here would need a second structure for no gain at this size.

- [ ] **Step 5: Track collection mtimes in the index and its cache**

At the end of `scan()`:

```python
    return {"facets": facets, "entries": entries,
            "errors": errors, "warnings": warnings,
            "facetsMtime": os.path.getmtime(facets_path),
            "collections": collection_mtimes(library_dir)}
```

Add the helper just below `manifest_paths()`:

```python
def collection_mtimes(library_dir):
    """{collection.json path: mtime} for the whole library.

    Editing a collection's label changes no part.json, so without this the
    cached index would keep serving the old family name until something
    else in the library happened to change."""
    return dict((path, os.path.getmtime(path))
                for path in pc.collection_paths(library_dir))
```

In `is_cache_valid()`, after the `facetsMtime` check:

```python
    if cache.get("collections") != collection_mtimes(library_dir):
        return False
```

In `save_cache()`, carry the key through:

```python
    payload = {"version": CACHE_VERSION,
               "facets": index["facets"],
               "entries": index["entries"],
               "facetsMtime": index.get("facetsMtime"),
               "collections": index.get("collections") or {}}
```

Also update the early-return in `scan()`'s `facets.json` failure branch so it has the same shape as the success return:

```python
        return {"facets": {}, "entries": [],
                "errors": ["%s: %s" % (FACETS_FILENAME, exc)],
                "warnings": [], "facetsMtime": None, "collections": {}}
```

- [ ] **Step 6: Make the family searchable**

In `index.py`, add a score band between keyword-substring and description:

```python
_SCORE_KEYWORD_SUBSTRING = 40
# A family match ranks below a keyword and above a description: typing
# "malm" should find the Malm range, but a part actually NAMED after the
# query still wins.
_SCORE_FAMILY_SUBSTRING = 30
_SCORE_DESCRIPTION = 20
```

and in `score()`, between the keyword and description checks:

```python
    family = (entry.get("family") or "").lower()
    if family and query in family:
        return _SCORE_FAMILY_SUBSTRING
```

- [ ] **Step 7: Add `facet_groups` beside `category_tree`**

`category_tree` STAYS for now — `gui._populateCategories` still calls it and
is not deleted until Task 7, and no test imports that module, so removing it
here would leave a broken panel behind a green suite. Add the new function
directly below it:

```python
def facet_groups(entries, facets, facet="room"):
    """One group per value of `facet` that at least one part declares.

    The primary half of what category_tree used to return - value, label,
    icon and a count of DISTINCT parts - with UNCLASSIFIED sorted last. A
    multi-valued facet legitimately puts one part in several groups, and a
    part declaring the same value twice must still be counted once, which is
    why the count goes through a set of ids rather than len(group_entries).

    The `children` half went with the catalogue screen that rendered it: the
    element level is no longer navigable, because 25 of the library's 36
    element values hold exactly one part."""
    groups = []
    for value, group_entries in group_by(entries, facet).items():
        groups.append({
            "value": value,
            "label": pm.facet_label(facets, facet, value),
            "icon": pm.facet_icon(facets, facet, value),
            "count": len(set(e["id"] for e in group_entries)),
        })
    groups.sort(key=lambda group: _sort_key(group["value"], group["label"]))
    return groups
```

- [ ] **Step 8: Add `basic/`'s collection**

Create `archplus/tools/partslib/library/basic/collection.json`:

```json
{
  "schema": 1,
  "description": "Generic parametric furniture and fittings, not modelled on any manufacturer's product."
}
```

No `label`, deliberately — see `validate_collection`'s docstring.

- [ ] **Step 9: Run the tests**

Run: `uv run --no-project --with pytest python -m pytest -q`
Expected: PASS. `test_library_content.py` scans the real library, so this also proves the new `basic/collection.json` parses and that no bundled part lost its entry.

- [ ] **Step 10: Commit**

```bash
git add archplus/tools/partslib/index.py archplus/tools/partslib/tests/test_partslib_index.py archplus/tools/partslib/library/basic/collection.json
git commit -m "Carry each part's collection through the index; group rooms without the element level"
```

---

### Task 3: `ParamForm` reports pristine and derived state

**Files:**
- Modify: `archplus/tools/partslib/paramform.py`
- Modify: `archplus/tools/partslib/tests/test_partslib_paramform.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `ParamForm.isPristine() -> bool`, `ParamForm.hasDerivedFields() -> bool`.

- [ ] **Step 1: Write the failing tests**

Append to `archplus/tools/partslib/tests/test_partslib_paramform.py`:

```python
class _Signal:
    """Stands in for a Qt Signal - conftest fakes QtCore.Signal as a
    function returning None, so an instance needs its own."""

    def __init__(self):
        self.count = 0

    def emit(self):
        self.count += 1


class _Field:
    """A spinbox as far as _setValueOf and setDerived need one."""

    def __init__(self):
        self.value = None
        self.blocked = []

    def blockSignals(self, state):
        self.blocked.append(state)

    def setMmValue(self, value):
        self.value = value

    def setStyleSheet(self, _sheet):
        pass

    def setToolTip(self, _text):
        pass


def _bare_form(auto=(), widgets=None):
    """A ParamForm with its Qt construction skipped.

    Built with object.__new__ the way the panels' edit round-trip tests are:
    what is under test is the pristine/derived bookkeeping, not layout."""
    form = object.__new__(pf.ParamForm)
    form._specs = {}
    form._tips = {}
    form._widgets = dict(widgets or {})
    form._auto = set(auto)
    form._pristine = True
    form.changed = _Signal()
    return form


def test_a_freshly_populated_form_is_pristine():
    form = _bare_form()
    assert form.isPristine()


def test_editing_a_field_dirties_the_form():
    form = _bare_form()
    form._onEdited("Width")
    assert not form.isPristine()
    assert form.changed.count == 1


def test_a_derived_value_arriving_leaves_the_form_pristine():
    # The whole reason this is a flag and not a value comparison: setDerived
    # writes measured numbers into the auto fields moments after a part is
    # selected, and a value comparison would then call an untouched form
    # edited - sending every part straight back to the slow render path.
    field = _Field()
    form = _bare_form(auto=["Height"], widgets={"Height": field})
    form.setDerived({"Height": 1230.0})

    assert field.value == 1230.0
    assert form.isPristine()
    assert form.changed.count == 0


def test_pinning_a_derived_field_dirties_the_form_and_clears_its_auto_flag():
    field = _Field()
    form = _bare_form(auto=["Height"], widgets={"Height": field})
    form._onEdited("Height")

    assert not form.isPristine()
    assert not form.hasDerivedFields()


def test_has_derived_fields_is_false_without_auto_params():
    # 27 of the 31 bundled parts. This is what spares them measure(), whose
    # optimalBoundingBox costs about as much as building the shape.
    assert not _bare_form().hasDerivedFields()


def test_has_derived_fields_is_true_while_one_is_unpinned():
    assert _bare_form(auto=["Width"]).hasDerivedFields()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --no-project --with pytest python -m pytest archplus/tools/partslib/tests/test_partslib_paramform.py -q`
Expected: FAIL — `AttributeError: 'ParamForm' object has no attribute 'isPristine'`

- [ ] **Step 3: Add the flag and the two accessors**

In `ParamForm.__init__`, after `self._auto = set()`:

```python
        self._auto = set()
        # See isPristine(). Initialised here so a form that is read before
        # its first setSpecs() still answers.
        self._pristine = True
```

At the very end of `setSpecs()` (after the `self._toggle.setArrowType(...)` line):

```python
        # A rebuild is a fresh part (or reset()), so nothing is edited yet.
        # This is also what makes reset() restore the committed thumbnail:
        # it goes through setSpecs, so the form comes back pristine.
        self._pristine = True
```

In `_onEdited()`, before the emit:

```python
    def _onEdited(self, name):
        if name in self._auto:
            self._auto.discard(name)
            widget = self._widgets.get(name)
            if widget is not None:
                widget.setStyleSheet("")
                widget.setToolTip(self._tips.get(name, ""))
        self._pristine = False
        self.changed.emit()
```

Add both accessors after `values()`:

```python
    def isPristine(self):
        """True while every field still holds its manifest default.

        A FLAG rather than a comparison of values against the manifest, on
        purpose: setDerived() writes measured numbers into the auto fields
        moments after a part is selected, so a value comparison would report
        an untouched form as edited. setDerived deliberately does not emit
        `changed`, and reset() goes through setSpecs, so both leave the form
        pristine.

        gui._refreshPreview reads this to decide whether the part's committed
        thumbnail.jpg already depicts these exact parameters - which, at the
        manifest's defaults, it does."""
        return self._pristine

    def hasDerivedFields(self):
        """True while some field still shows a value derived from the shape.

        setDerived() only ever writes into these, so when there are none,
        measuring the shape is pure waste - and measuring is not cheap:
        geometry.measure() calls optimalBoundingBox(), which costs about as
        much as building the shape (0.913s of the king bed's 1.76s click).
        27 of the 31 bundled parts declare no "auto" param at all."""
        return bool(self._auto)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --no-project --with pytest python -m pytest archplus/tools/partslib/tests/test_partslib_paramform.py -q`
Expected: PASS.

- [ ] **Step 5: Run the whole suite**

Run: `uv run --no-project --with pytest python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add archplus/tools/partslib/paramform.py archplus/tools/partslib/tests/test_partslib_paramform.py
git commit -m "Let the param form say whether it is untouched and whether anything derives from the shape"
```

---

### Task 4: `preview_plan` and the fast preview path

**Files:**
- Modify: `archplus/tools/partslib/thumbs.py`
- Modify: `archplus/tools/partslib/gui.py:1016-1055` (`_refreshPreview`)
- Modify: `archplus/tools/partslib/tests/test_partslib_thumbs.py`

**Interfaces:**
- Consumes: `ParamForm.isPristine()`, `ParamForm.hasDerivedFields()` (Task 3).
- Produces: `thumbs.preview_plan(pristine, has_derived_fields, thumbnail_usable) -> {"build": bool, "measure": bool, "render": bool, "use_thumbnail": bool}`; `PartsLibraryPanel._showCommittedThumbnail(thumbPath)`.

- [ ] **Step 1: Write the failing tests**

Append to `archplus/tools/partslib/tests/test_partslib_thumbs.py`:

```python
def test_an_untouched_part_with_a_thumbnail_touches_no_geometry():
    # 27 of the 31 bundled parts. The committed thumbnail IS the render of
    # the manifest defaults - ensure_thumbnail() builds the part at exactly
    # those values - so recreating it is 0.5s spent reproducing a file that
    # loads in 1ms.
    plan = pt.preview_plan(pristine=True, has_derived_fields=False,
                           thumbnail_usable=True)
    assert plan == {"build": False, "measure": False, "render": False,
                    "use_thumbnail": True}


def test_an_untouched_part_with_derived_fields_builds_but_does_not_render():
    # The other 4. Their Width/Height cannot be known without the shape, so
    # the build and the measurement stay - but the picture still comes off
    # disk, because the parameters are still the defaults.
    plan = pt.preview_plan(pristine=True, has_derived_fields=True,
                           thumbnail_usable=True)
    assert plan == {"build": True, "measure": True, "render": False,
                    "use_thumbnail": True}


def test_an_edited_part_goes_the_full_pipeline():
    plan = pt.preview_plan(pristine=False, has_derived_fields=True,
                           thumbnail_usable=True)
    assert plan == {"build": True, "measure": True, "render": True,
                    "use_thumbnail": False}


def test_an_edited_part_without_derived_fields_still_skips_measuring():
    # measure() runs optimalBoundingBox and setDerived() has nothing to write
    # it into, so this is waste on the EDITED path too, not only on selection.
    plan = pt.preview_plan(pristine=False, has_derived_fields=False,
                           thumbnail_usable=True)
    assert plan["measure"] is False
    assert plan["render"] is True


def test_a_part_with_no_committed_thumbnail_falls_back_to_rendering():
    # A user-added part. Slow exactly once: the render path writes the jpg.
    plan = pt.preview_plan(pristine=True, has_derived_fields=False,
                           thumbnail_usable=False)
    assert plan == {"build": True, "measure": False, "render": True,
                    "use_thumbnail": False}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --no-project --with pytest python -m pytest archplus/tools/partslib/tests/test_partslib_thumbs.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'preview_plan'`

- [ ] **Step 3: Add `preview_plan` to `thumbs.py`**

Add near the top of `thumbs.py`, just below `thumbnail_path()`:

```python
def preview_plan(pristine, has_derived_fields, thumbnail_usable):
    """What a detail-pane refresh actually has to do.

    Returns {"build", "measure", "render", "use_thumbnail"} booleans. Split
    out as a pure function so the policy is testable without a GL context,
    and so the reasoning below lives in one place instead of being spread
    through a branchy _refreshPreview.

    Selecting a part used to run the whole pipeline every time - build the
    shape, measure it with optimalBoundingBox, tessellate, render offscreen,
    save a JPEG, load it back. Measured over the bundled 31 parts in FreeCAD
    1.1.1 with a cold shape cache, that is 0.496s on average and 1.76s at
    worst, of which the render is only 18%: build is 53% and measure 28%.
    (The 17-second writeInventor stall this module's other comments describe
    is long fixed - tessellation now peaks at 0.14s.)

    Two questions decide all four flags:

    - `pristine` - no field has been edited since the part was selected, so
      the committed thumbnail.jpg depicts EXACTLY these parameter values.
      Not an approximation: ensure_thumbnail() renders the part at its
      resolved manifest defaults, which is what a pristine form holds.
    - `has_derived_fields` - some field's value is derived from the shape
      ("default": "auto"), so the shape must be built and measured to fill
      it in, even when nothing will be rendered. Only 4 of the 31 bundled
      parts declare one; for the other 27 this is the difference between
      0.5s and 1ms.

    `thumbnail_usable` is the caller's business: it means both that the file
    exists and that a static image is what the pane wants (the live pivy
    preview, if it ever becomes available again, must not be replaced by a
    flat picture)."""
    if pristine and thumbnail_usable:
        return {"build": has_derived_fields,
                "measure": has_derived_fields,
                "render": False,
                "use_thumbnail": True}
    return {"build": True,
            "measure": has_derived_fields,
            "render": True,
            "use_thumbnail": False}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --no-project --with pytest python -m pytest archplus/tools/partslib/tests/test_partslib_thumbs.py -q`
Expected: PASS.

- [ ] **Step 5: Rewrite `_refreshPreview` to follow the plan**

Replace `_refreshPreview` in `gui.py` entirely with:

```python
    def _refreshPreview(self):
        """Show the selected part at the selected parameters.

        Not simply "build and render" any more - see
        partslib_thumbs.preview_plan for which of the four steps each state
        actually needs, and why."""
        from . import geometry as partslib_geometry

        selection = self._selection()
        if selection is None:
            return
        entry, manifest, overrides = selection

        thumbPath = partslib_thumbs.thumbnail_path(entry["dir"])
        # A live pivy preview must never be replaced by a flat picture, so
        # the committed thumbnail is only "usable" on the static path. On
        # FreeCAD 1.1 that is every session (Qt6 moved QOpenGLWidget out from
        # under pivy's QuarterWidget), but the guard keeps a future pivy fix
        # from silently downgrading the pane.
        thumbnailUsable = bool(
            not _PREVIEW_LIVE and os.path.exists(thumbPath))
        plan = partslib_thumbs.preview_plan(
            self.paramForm.isPristine(),
            self.paramForm.hasDerivedFields(),
            thumbnailUsable)

        timer = _Timer("previewing %r" % (entry["id"],))
        shape = None
        if plan["build"]:
            try:
                shape = partslib_geometry.build_shape(
                    manifest, entry["dir"], overrides)
            except Exception as exc:
                self.buildError.setText("Cannot build this part: %s" % exc)
                return
            timer.mark("build")
        self.buildError.setText("")

        if plan["measure"] and shape is not None:
            # An "auto" param can only be one of the shape's own dimensions
            # (manifest.AUTO_PARAM_NAMES), so measuring the built shape
            # reports every one of them - there is nothing else for a builder
            # to tell us.
            self.paramForm.setDerived(partslib_geometry.measure(shape))
            timer.mark("measure")

        if plan["use_thumbnail"]:
            self._showCommittedThumbnail(thumbPath)
        elif _PREVIEW_LIVE:
            try:
                self.preview.setSceneGraph(
                    partslib_thumbs.scene_from_shape(shape))
                self.preview.viewAll()
            except Exception as exc:
                FreeCAD.Console.PrintWarning(
                    "ArchPlus: live preview failed: %s\n" % (exc,))
        else:
            self._showStaticPreview(entry, shape, manifest, overrides)
        timer.mark("preview")
        timer.report()

    def _showCommittedThumbnail(self, thumbPath):
        """Put the part's committed thumbnail in the detail pane.

        Degrades to the placeholder rather than raising: an unreadable file
        must leave the pane usable, exactly as _showStaticPreview's last
        layer does."""
        pixmap = QtGui.QPixmap(thumbPath)
        if pixmap.isNull():
            self.preview.setPixmap(QtGui.QPixmap())
            self.preview.setText("No preview available")
            return
        self.preview.setPixmap(pixmap.scaledToHeight(
            _PREVIEW_HEIGHT, QtCore.Qt.SmoothTransformation))
```

Note the build-error contract is unchanged and self-maintaining: a part that cannot build cannot have had a thumbnail rendered either, so it has no `thumbnail.jpg`, so `plan["build"]` is True and the error surfaces exactly as before.

- [ ] **Step 6: Run the whole suite**

Run: `uv run --no-project --with pytest python -m pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add archplus/tools/partslib/thumbs.py archplus/tools/partslib/gui.py archplus/tools/partslib/tests/test_partslib_thumbs.py
git commit -m "Serve the committed thumbnail for an untouched part instead of rebuilding it"
```

---

### Task 5: Debounce the search box

**Files:**
- Modify: `archplus/tools/partslib/gui.py:345-390` (`_buildResultsScreen`) and `gui.py:392-450` (`_buildDetail`)

**Interfaces:**
- Consumes: nothing.
- Produces: `gui._DEBOUNCE_MS = 250`; `PartsLibraryPanel._searchTimer`.

- [ ] **Step 1: Add the shared interval constant**

In `gui.py`, next to `_PREVIEW_HEIGHT`:

```python
# How long the panel waits after the last keystroke before doing expensive
# work. Shared by the search field and the parameter form so the panel has
# ONE notion of "the user has stopped typing".
_DEBOUNCE_MS = 250
```

- [ ] **Step 2: Route the search field through a timer**

Replace the three search lines in `_buildResultsScreen`:

```python
        self.search = QtGui.QLineEdit()
        self.search.setPlaceholderText("Search…")
        self.search.textChanged.connect(self._repopulateGrid)
        v.addWidget(self.search)
```

with:

```python
        self.search = QtGui.QLineEdit()
        self.search.setPlaceholderText("Search…")
        # DEBOUNCED, not wired straight to _repopulateGrid. Repopulating
        # selects row 0, which fires _onSelect -> _refreshPreview, so an
        # undebounced field ran a whole preview for every keystroke: typing
        # "cabinet" cost seven of them, and before the thumbnail fast path
        # that was three to four seconds of frozen UI. The parameter form
        # has had this treatment since it was written; the search field
        # never got it.
        self._searchTimer = QtCore.QTimer(self)
        self._searchTimer.setSingleShot(True)
        self._searchTimer.setInterval(_DEBOUNCE_MS)
        self._searchTimer.timeout.connect(self._repopulateGrid)
        self.search.textChanged.connect(self._searchTimer.start)
        v.addWidget(self.search)
```

`QTimer.start()` restarts a running single-shot timer, so holding a key down schedules exactly one repopulate.

- [ ] **Step 3: Point the param timer at the same constant**

In `_buildDetail`, change:

```python
        self._paramTimer.setInterval(250)
```

to:

```python
        self._paramTimer.setInterval(_DEBOUNCE_MS)
```

- [ ] **Step 4: Run the whole suite**

Run: `uv run --no-project --with pytest python -m pytest -q`
Expected: PASS (no test covers this directly — it is verified live in Task 9).

- [ ] **Step 5: Commit**

```bash
git add archplus/tools/partslib/gui.py
git commit -m "Debounce the search field so a keystroke no longer runs a preview"
```

---

### Task 6: `FlowLayout` for the chip row

**Files:**
- Modify: `archplus/common/widgets.py`
- Modify: `archplus/common/tests/test_widgets.py`
- Modify: `conftest.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `widgets.flow_positions(sizes, width, spacing=6) -> ([(x, y)], total_height)`; `widgets.FlowLayout(parent=None, spacing=6)`.

- [ ] **Step 1: Write the failing tests**

Append to `archplus/common/tests/test_widgets.py`:

```python
def test_items_that_fit_stay_on_one_row():
    positions, height = widgets.flow_positions(
        [(50, 20), (50, 20), (50, 20)], width=200, spacing=5)
    assert positions == [(0, 0), (55, 0), (110, 0)]
    assert height == 20


def test_an_item_that_would_overflow_starts_a_new_row():
    positions, height = widgets.flow_positions(
        [(80, 20), (80, 20), (80, 20)], width=200, spacing=5)
    assert positions == [(0, 0), (85, 0), (0, 25)]
    assert height == 45


def test_a_row_is_as_tall_as_its_tallest_item():
    positions, height = widgets.flow_positions(
        [(80, 20), (80, 40), (80, 20)], width=200, spacing=5)
    assert positions == [(0, 0), (85, 0), (0, 45)]
    assert height == 65


def test_an_item_wider_than_the_row_gets_a_row_to_itself():
    # It must still be PLACED. Dropping it would silently hide a room chip
    # in a narrow panel, which is worse than letting it overhang.
    positions, height = widgets.flow_positions(
        [(50, 20), (500, 20)], width=200, spacing=5)
    assert positions == [(0, 0), (0, 25)]
    assert height == 45


def test_no_items_is_no_height():
    assert widgets.flow_positions([], width=200, spacing=5) == ([], 0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --no-project --with pytest python -m pytest archplus/common/tests/test_widgets.py -q`
Expected: FAIL — `AttributeError: module 'archplus.common.widgets' has no attribute 'flow_positions'`

- [ ] **Step 3: Implement the pure geometry**

Add to `archplus/common/widgets.py`:

```python
# Default gap between flowed items, in pixels.
FLOW_SPACING = 6


def flow_positions(sizes, width, spacing=FLOW_SPACING):
    """Left-to-right, top-to-bottom positions for `sizes` within `width`.

    `sizes` is a sequence of (w, h). Returns (positions, total_height), where
    positions is a list of (x, y) in the same order.

    Split out from FlowLayout below for the same reason theme.py splits
    is_dark_theme_name() out of read_is_dark_theme(): the arithmetic is where
    the bugs are, and this way it is unit-testable with no Qt process at all.

    An item wider than `width` is placed on a row of its own rather than
    dropped - a room chip that overhangs a narrow panel is bad, a room chip
    that silently vanishes is worse."""
    positions = []
    x = y = 0
    row_height = 0
    for item_width, item_height in sizes:
        if positions and x + item_width > width:
            x = 0
            y += row_height + spacing
            row_height = 0
        positions.append((x, y))
        x += item_width + spacing
        row_height = max(row_height, item_height)
    return positions, (y + row_height if positions else 0)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --no-project --with pytest python -m pytest archplus/common/tests/test_widgets.py -q`
Expected: PASS.

- [ ] **Step 5: Teach the conftest fake about `QLayout`**

`widgets.py` does `from PySide import QtGui, QtCore` at module scope, and the
conftest fake's `QtGui` has only `QWidget`, `QDoubleSpinBox` and
`QValidator`. Subclassing `QtGui.QLayout` would therefore fail at import
time and take `test_widgets.py` down with it. Add the stand-in alongside the
existing ones in `conftest.py`:

```python
class _FakeLayout:
    """Enough QLayout for a subclass's class statement to execute.

    FlowLayout's arithmetic lives in the pure flow_positions() and is tested
    directly; what this stub buys is that importing archplus.common.widgets
    headlessly does not explode on the class statement."""

    def __init__(self, parent=None):
        self._parent = parent

    def setContentsMargins(self, *margins):
        pass

    def setGeometry(self, rect):
        pass
```

and register it in `_install_fakes()` beside `qtgui.QWidget`:

```python
    qtgui.QLayout = _FakeLayout
```

- [ ] **Step 6: Add the QLayout shell**

Also in `archplus/common/widgets.py` — this half is GUI-only and is verified in Task 9, not by pytest:

```python
class FlowLayout(QtGui.QLayout):
    """A QLayout that wraps its items onto as many rows as it needs.

    Qt ships no wrapping box layout, and QHBoxLayout cannot wrap - which is
    why the parts library's room chips need this. It reflows from
    heightForWidth(), so nothing has to watch resize events; the panel's
    old hand-rolled category reflow (and its viewport eventFilter) went
    away with the screen it served.

    All the arithmetic is in flow_positions() above, which is tested; what
    is left here is Qt bookkeeping."""

    def __init__(self, parent=None, spacing=FLOW_SPACING):
        QtGui.QLayout.__init__(self, parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    # -- the five methods QLayout requires a subclass to provide -----------
    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def sizeHint(self):
        return self.minimumSize()

    # -- wrapping ----------------------------------------------------------
    def expandingDirections(self):
        return QtCore.Qt.Orientations(QtCore.Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        _positions, height = flow_positions(
            self._sizes(), width, self._spacing)
        return height

    def setGeometry(self, rect):
        QtGui.QLayout.setGeometry(self, rect)
        positions, _height = flow_positions(
            self._sizes(), rect.width(), self._spacing)
        for item, (x, y) in zip(self._items, positions):
            size = item.sizeHint()
            item.setGeometry(QtCore.QRect(
                rect.x() + x, rect.y() + y, size.width(), size.height()))

    def minimumSize(self):
        # As wide as the widest single item and as tall as one row: the
        # layout can always wrap, so anything more would stop the panel
        # being narrowed.
        width = height = 0
        for item in self._items:
            size = item.minimumSize()
            width = max(width, size.width())
            height = max(height, size.height())
        return QtCore.QSize(width, height)

    def _sizes(self):
        return [(item.sizeHint().width(), item.sizeHint().height())
                for item in self._items]
```

`archplus/common/widgets.py` already imports both `QtGui` and `QtCore`, so no import change is needed.

- [ ] **Step 7: Run the whole suite**

Run: `uv run --no-project --with pytest python -m pytest -q`
Expected: PASS. In particular `archplus/common/tests/test_widgets.py` must still import — that is what proves the `_FakeLayout` stub is sufficient.

- [ ] **Step 8: Commit**

```bash
git add archplus/common/widgets.py archplus/common/tests/test_widgets.py conftest.py
git commit -m "Add a wrapping flow layout for the parts library's room chips"
```

---

### Task 7: One screen — room chips replace the catalogue

**Files:**
- Modify: `archplus/tools/partslib/gui.py` (the bulk of the change)
- Modify: `archplus/tools/partslib/index.py` (delete `category_tree`)
- Modify: `archplus/tools/partslib/tests/test_partslib_index.py` (delete its tests)

**Interfaces:**
- Consumes: `index.facet_groups` (Task 2), `widgets.FlowLayout` (Task 6).
- Produces: `PartsLibraryPanel._populateChips()`, `PartsLibraryPanel._onChipSelected(room)`; the panel no longer has `self.stack`, `self.categoriesScreen`, `self.resultsScreen` or `self.breadcrumb`.

- [ ] **Step 1: Delete the catalogue screen**

Remove these methods and attributes from `gui.py` entirely:

`_buildCategoriesScreen`, `_populateCategories`, `_fillCategoriesEmptyState`, `_makeRoomCard`, `_reflowCategories`, `_columnCountFor`, `eventFilter`, `_showCategories`, `_updateBreadcrumb`, `_addBreadcrumbSegment`, `_addBreadcrumbSeparator`, `_roomLabel`, `_elementLabel`; the `_CARD_TARGET_WIDTH` constant; and the `self._categoriesStack` / `self._categoryCards` / `self._categoryColumns` / `self._categories` state wherever it is assigned or read.

Also delete `index.category_tree` and its nine tests in
`archplus/tools/partslib/tests/test_partslib_index.py` (the block under the
`# -- category_tree` header). It has no caller once `_populateCategories` is
gone, and leaving a second, richer grouping function around invites someone
to rebuild the catalogue screen by accident. `facet_groups` (Task 2) already
carries every behaviour worth keeping. Add one guard test in its place:

```python
def test_category_tree_is_gone():
    # It served the catalogue screen, which no longer exists.
    assert not hasattr(px, "category_tree")
```

Remove the now-dead `QFrame#RoomCard`, `QPushButton#RoomHeader`, `QPushButton#ElementRow`, `QPushButton#BreadcrumbSegment`, `QFrame#HairlineRule` and `QWidget#CategoriesContainer` rules from `_STYLESHEET_TEMPLATE` (keep `QFrame#PartCard`, which the grid still uses).

- [ ] **Step 2: Rewrite `_buildUi` with no stack**

```python
    def _buildUi(self):
        outer = QtGui.QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        # Theme FIRST: _applyTheme() is what assigns self._tokens, and the
        # detail pane hands those tokens to ParamForm as it is constructed.
        self._applyTheme()

        # There is no QStackedWidget here any more. The panel used to open
        # on a catalogue page of room cards listing element rows - but 25 of
        # the library's 36 element rows lead to exactly one part, so the page
        # was two clicks to reach a single card. The rooms survive as filter
        # chips above the grid; the element facet stays in part.json, feeding
        # search and the IFC type mapping, and is simply not navigable.
        self.chipRow = QtGui.QWidget()
        self.chipLayout = archplus_widgets.FlowLayout(self.chipRow)
        outer.addWidget(self.chipRow)

        self.search = QtGui.QLineEdit()
        ...  # as built in Task 5, moved here from _buildResultsScreen
        outer.addWidget(self.search)

        splitter = QtGui.QSplitter(QtCore.Qt.Horizontal)
        ...  # grid + gridStack + sidebar, unchanged from _buildResultsScreen
        outer.addWidget(splitter, 1)
```

Fold the whole body of `_buildResultsScreen` into `_buildUi` (the grid, `gridStack`, `resultsEmptyState`, splitter and sidebar are all unchanged) and delete `_buildResultsScreen`. Add the import at the top of `gui.py`:

```python
from archplus.common import widgets as archplus_widgets
```

Rename the `QWidget#ResultsScreen` stylesheet selector to `QWidget#ArchPlusPartsLibrary` if `ResultsScreen` no longer names a widget, or set `self.setObjectName("ArchPlusPartsLibrary")` — whichever the existing `_applyTheme` already relies on. Do not leave a selector naming a widget that no longer exists.

- [ ] **Step 3: Build the chips**

Add these two methods where `_populateCategories` used to be:

```python
    # -- room chips --------------------------------------------------------
    def _populateChips(self):
        """(Re)build the room filter chips from the current index.

        `All` comes first and is selected on open, then one chip per room
        that at least one part declares, with its facet icon and part count.
        They are exclusive - this is a filter, not a multi-select - which is
        what an auto-exclusive QButtonGroup gives for free."""
        while self.chipLayout.count():
            item = self.chipLayout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        self._chipGroup = QtGui.QButtonGroup(self)
        self._chipGroup.setExclusive(True)

        groups = partslib_index.facet_groups(
            self._entries, self._facets, "room")
        self._addChip("All", len(self._entries), None, None)
        for group in groups:
            self._addChip(group["label"], group["count"],
                          group["icon"], group["value"])

    def _addChip(self, label, count, iconName, room):
        """One filter chip. `room` is None for the All chip."""
        chip = QtGui.QToolButton()
        chip.setObjectName("RoomChip")
        chip.setCheckable(True)
        chip.setAutoRaise(True)
        chip.setCursor(QtCore.Qt.PointingHandCursor)
        chip.setText("%s · %d" % (label, count))
        chip.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        iconPath = self._facetIconPath(iconName)
        if iconPath:
            chip.setIcon(QtGui.QIcon(iconPath))
            chip.setIconSize(QtCore.QSize(16, 16))
        chip.setChecked(room == self._filterRoom)
        chip.clicked.connect(
            lambda *args, r=room: self._onChipSelected(r))
        self._chipGroup.addButton(chip)
        self.chipLayout.addWidget(chip)

    def _onChipSelected(self, room):
        self._filterRoom = room
        self._repopulateGrid()
```

- [ ] **Step 4: Drop the element filter and rewire `refresh`**

`self._filterElement` has no control left. Remove the attribute, its initialisation, and the element clause in `_filteredEntries`:

```python
    def _filteredEntries(self):
        matches = partslib_index.search(self._entries, self.search.text())
        if self._filterRoom is not None:
            matches = [e for e in matches
                       if self._facetMatches(e, "room", self._filterRoom)]
        return matches
```

In `refresh()`, replace the `_populateCategories()` / `_updateBreadcrumb()` pair with `self._populateChips()`, and keep the timer marks:

```python
        self._populateChips()
        timer.mark("chips")

        self._repopulateGrid()
        timer.mark("grid")
```

- [ ] **Step 5: Merge the two empty states**

`_fillResultsEmptyState` now covers both "the library is empty" and "nothing matches this search". Give it the library path the deleted `_fillCategoriesEmptyState` used to show, since an empty library is exactly when the user needs to know where parts go:

```python
    def _fillResultsEmptyState(self):
        """(Re)build the empty-state message shown in place of the grid.

        One message now serves both cases the two screens used to split: an
        empty library and a search that matches nothing. The library path
        appears only for the former - it is the answer to "where do I put
        parts?", and noise next to a mistyped search."""
        from . import object as partslib_object

        layout = self.resultsEmptyState.layout()
        if layout is None:
            layout = QtGui.QVBoxLayout(self.resultsEmptyState)
            layout.setAlignment(QtCore.Qt.AlignCenter)
        else:
            _clearLayout(layout)

        empty = not self._entries
        message = QtGui.QLabel("No parts in the library yet" if empty
                               else "No parts match this search")
        message.setAlignment(QtCore.Qt.AlignCenter)
        message.setWordWrap(True)
        message.setStyleSheet("color: %s;" % self._tokens["text"])
        layout.addWidget(message)

        if empty:
            path = QtGui.QLabel(
                os.path.abspath(partslib_object.LIBRARY_DIR))
            path.setAlignment(QtCore.Qt.AlignCenter)
            path.setWordWrap(True)
            pathFont = path.font()
            pathFont.setPointSize(max(7, pathFont.pointSize() - 1))
            path.setFont(pathFont)
            path.setStyleSheet("color: %s;" % self._tokens["text_dim"])
            layout.addWidget(path)
```

- [ ] **Step 6: Style the chips**

Add to `_STYLESHEET_TEMPLATE`. Both rules set `background-color` **and** `color` from the same token set, per the structural rule above them:

```
    QToolButton#RoomChip {
        background-color: %(page_bg)s;
        color: %(text)s;
        border: 1px solid %(border)s;
        border-radius: 11px;
        padding: 3px 10px;
    }
    QToolButton#RoomChip:hover {
        background-color: %(page_bg)s;
        color: %(accent)s;
        border-color: %(accent)s;
    }
    QToolButton#RoomChip:checked {
        background-color: %(accent)s;
        color: %(accent_text)s;
        border-color: %(accent)s;
    }
```

- [ ] **Step 7: Update the module docstring**

The docstring at the top of `gui.py` describes a two-screen browser. Replace its first paragraph with a description of the single screen (chips, search, grid, detail), keeping the note that browsing never loads geometry — and correct that note's "committed PNG thumbnails" to JPEG while you are there.

- [ ] **Step 8: Run the whole suite**

Run: `uv run --no-project --with pytest python -m pytest -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add archplus/tools/partslib/gui.py archplus/tools/partslib/index.py archplus/tools/partslib/tests/test_partslib_index.py
git commit -m "Collapse the parts library onto one screen with room filter chips"
```

---

### Task 8: Card content — drop the parameter line, show the family

**Files:**
- Modify: `archplus/tools/partslib/gui.py` (`_makePartCard`, `_onSelect`, `_buildDetail`)

**Interfaces:**
- Consumes: `entry["family"]`, `entry["familyDescription"]` (Task 2).
- Produces: nothing new.

- [ ] **Step 1: Rewrite `_makePartCard`**

Replace the parameter-label block (everything from `from . import manifest as partslib_manifest` to `v.addWidget(adjustable)`) with the family line, and update the docstring:

```python
    def _makePartCard(self, entry):
        """Square thumbnail, name, and - when its collection declares one -
        the family it belongs to.

        There used to be a monospaced line of the part's primary parameter
        LABELS here ("Width | Depth | Height"), with no values: it restated
        the column headings of a form the user had not opened. A card's job
        is recognition, which the thumbnail does; the detail pane states
        dimensions properly, as editable fields."""
        card = QtGui.QFrame()
        card.setObjectName("PartCard")
        card.setProperty("selected", False)
        card.setToolTip(entry.get("description") or entry["name"])
        v = QtGui.QVBoxLayout(card)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(4)

        thumb = QtGui.QLabel()
        thumb.setFixedSize(_THUMB_SIZE, _THUMB_SIZE)
        thumb.setAlignment(QtCore.Qt.AlignCenter)
        thumbPath = partslib_thumbs.thumbnail_path(entry["dir"])
        if not os.path.exists(thumbPath):
            if self._renderThumbnails:
                thumbPath = self._ensureGridThumbnail(entry) or thumbPath
        if os.path.exists(thumbPath):
            pixmap = QtGui.QPixmap(thumbPath)
            if not pixmap.isNull():
                thumb.setPixmap(pixmap.scaled(
                    _THUMB_SIZE, _THUMB_SIZE, QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation))
        v.addWidget(thumb, 0, QtCore.Qt.AlignHCenter)

        name = QtGui.QLabel(entry["name"])
        name.setAlignment(QtCore.Qt.AlignHCenter)
        name.setWordWrap(True)
        v.addWidget(name)

        # Only where the collection declares a label. An unlabelled
        # collection - which is what library/basic/ is - leaves the card at
        # thumbnail-plus-name and correspondingly shorter, because an
        # identical "Basic" under all 31 generic parts would be exactly the
        # noise the parameter line was removed for.
        family = entry.get("family")
        if family:
            familyLabel = QtGui.QLabel(family)
            familyLabel.setAlignment(QtCore.Qt.AlignHCenter)
            familyLabel.setWordWrap(True)
            familyFont = familyLabel.font()
            familyFont.setPointSize(max(7, familyFont.pointSize() - 1))
            familyLabel.setFont(familyFont)
            familyLabel.setStyleSheet(
                "color: %s;" % self._tokens["text_dim"])
            familyLabel.setToolTip(entry.get("familyDescription") or "")
            v.addWidget(familyLabel)

        return card
```

- [ ] **Step 2: Add the family line to the detail pane**

In `_buildDetail`, immediately after `layout.addWidget(self.detailName)`:

```python
        self.detailFamily = QtGui.QLabel("")
        self.detailFamily.setWordWrap(True)
        familyFont = self.detailFamily.font()
        familyFont.setPointSize(max(7, familyFont.pointSize() - 1))
        self.detailFamily.setFont(familyFont)
        self.detailFamily.setStyleSheet(
            "color: %s;" % self._tokens["text_dim"])
        layout.addWidget(self.detailFamily)
```

In `_onSelect`, set it in both branches. In the `entry is None` branch, alongside `self.detailName.setText("")`:

```python
            self.detailFamily.setText("")
```

and after `self.detailName.setText(entry["name"])`:

```python
        self.detailFamily.setText(entry.get("family") or "")
        self.detailFamily.setToolTip(entry.get("familyDescription") or "")
        # An empty label still occupies a layout row; hide it so an
        # unlabelled collection leaves no gap under the part name.
        self.detailFamily.setVisible(bool(entry.get("family")))
```

- [ ] **Step 3: Run the whole suite**

Run: `uv run --no-project --with pytest python -m pytest -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add archplus/tools/partslib/gui.py
git commit -m "Show a part's family on its card instead of a line of parameter names"
```

---

### Task 9: Documentation and live verification

**Files:**
- Modify: `docs/TESTING.md`
- Modify: `docs/PARTS-LIBRARY-VERIFICATION.md`
- Modify: `README.md` (the parts-library section)

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Record how to run the tests here**

In `docs/TESTING.md`, under "Running", add `uv` as the option that works on this machine — `python3 -m venv` fails without `python3.14-venv`:

```sh
uv run --no-project --with pytest python -m pytest -q
```

- [ ] **Step 2: Document `collection.json`**

Add a section to `docs/PARTS-LIBRARY-VERIFICATION.md` (and to whichever README section explains how to add a part) covering: where `collection.json` goes, its three fields, that `label` is optional and its absence means no family line, and that the nearest ancestor wins.

- [ ] **Step 3: Update the screenshots and prose for one screen**

Any passage describing the catalogue page, room cards, element rows or the breadcrumb is now wrong. Rewrite it for chips-plus-grid. Screenshots under `docs/images/` showing the old catalogue need retaking or removing — do not leave an image of a screen that no longer exists.

- [ ] **Step 4: Verify in a live FreeCAD session**

The `freecad` MCP server must be running. This covers everything pytest cannot: real widgets, a real GL context, and the actual click cost.

Through `mcp__freecad__execute_code`, and by driving the panel by hand:

1. Open the Parts Library. Confirm it opens **directly onto the grid** — no catalogue page.
2. Confirm the chip row reads `All · 31`, `Bathroom · 8`, `Bedroom · 10`, `Dining · 2`, `Kitchen · 6`, `Living · 8`, `Office · 2`, each with its facet icon, and that `All` is selected.
3. Narrow the panel until the chips wrap to a second row; confirm none disappears or overlaps.
4. Click each chip; confirm the grid filters and that clicking `All` restores 31 cards.
5. Confirm no card shows a `Width | Depth | Height` line, and that no card shows a family line (`basic/` is unlabelled).
6. Click through several parts. Confirm previews appear **immediately** — time a sweep and confirm it is around 1.7 s, not 15 s. Compare a served thumbnail against a rendered preview for the same part and confirm they look the same.
7. Select `Chest of drawers`, `Gas hob`, `Sofa` and `Television`: confirm their derived Width/Height fields still populate.
8. Edit a parameter on any part; confirm the preview re-renders and now reflects the edit, and that `Reset` returns both the fields and the preview to the default.
9. Type `cabinet` into the search box one character at a time; confirm the UI does not freeze between keystrokes.
10. Place a part in the 3D view; confirm placement is unaffected.
11. Temporarily add a `label` to `library/basic/collection.json`, hit **Rescan library**, and confirm every card gains the family line and that searching for the label finds parts. Then remove it and rescan again.
12. Switch FreeCAD between a light and a dark theme; confirm chips are legible in both, checked and unchecked.

- [ ] **Step 5: Commit**

```bash
git add docs README.md
git commit -m "Document collections and the single-screen parts library"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
| --- | --- |
| 1. One screen, chips, deletions, `facet_groups`, `FlowLayout` | 2, 6, 7 |
| 2. Card content, family line, detail pane | 8 |
| 3. `collection.json`, resolution, `basic/`'s file | 1, 2 |
| 4a. Measure only when derived fields wait | 3, 4 |
| 4b. Pristine serves the thumbnail | 3, 4 |
| 4c. Search debounce | 5 |
| 5. `collection.py` module boundary | 1 |
| Data model: `family`, `CACHE_VERSION` 3, cache invalidation | 2 |
| Error handling table | 1 (rows 1–4), 7 (row 5 — `_facetIconPath` already degrades), 2 (row 6 — `UNCLASSIFIED` gets a chip from `facet_groups`) |
| Testing | 1, 2, 3, 4, 6, 9 |
| Migration / docs | 2, 9 |

**Two spec items intentionally not their own task:** the family joining the search haystack is folded into Task 2 step 6 (it is an `index.py` change and belongs with the other one), and the `element`-stays-in-data requirement is a deletion, covered by Task 7 step 4.

**Type consistency:** `resolve()` returns `(label, description, errors)` in Task 1 and is unpacked in that order in Task 2. `facet_groups` produces `{"value","label","icon","count"}` in Task 2 and all four are read in Task 7 step 3. `preview_plan` returns the same four keys in Task 4's tests, its implementation, and `_refreshPreview`. `isPristine`/`hasDerivedFields` are defined in Task 3 and called in Task 4. `flow_positions(sizes, width, spacing)` is defined and called with that signature in Task 6.
