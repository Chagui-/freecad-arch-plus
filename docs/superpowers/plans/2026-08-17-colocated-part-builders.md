# Colocated Part Builders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move each library part's geometry code into a `builder.py` beside its `part.json`, with a family folder owning the code those parts share, and resolve builders by file presence instead of by a manifest-declared symbol.

**Architecture:** The library tree becomes the import tree. `library/basic/television/builder.py` is imported as `archplus.tools.partslib.library.basic.television.builder` — no `__init__.py` needed, because Python namespace packages cover directories without one. A part with a `builder.py` uses it; a part without one falls back to the stock asset builder. Shared design-language code lives in `library/<family>/_shared.py`, reached as `from .. import _shared`, which resolves correctly at any tree depth. Cross-family geometry primitives stay central in `partslib/shapes.py`.

**Tech Stack:** Python 2/3-compatible style as used throughout ArchPlus (`%` formatting, no f-strings, no type annotations), pytest, FreeCAD 1.1 add-on conventions. `Part`/`FreeCAD` are imported *inside* functions, never at module scope, so the headless suite can import every module.

**Spec:** `docs/superpowers/specs/2026-08-17-colocated-part-builders-design.md`

## Global Constraints

- **Branch:** `partslib-colocated-builders` is already checked out. Never commit to `main`.
- **Python style:** match the surrounding code exactly — `%`-style formatting, no f-strings, no type hints, LGPL header on every new `.py` file:
  `# SPDX-License-Identifier: LGPL-2.1-or-later`
- **No FreeCAD at module scope.** `import Part` / `import FreeCAD` go *inside* the function that needs them. `conftest.py` installs a fake `Part` with only `LineSegment` and `Circle`, so any module-scope FreeCAD import breaks the whole suite.
- **`index.py` and `manifest.py` must stay free of FreeCAD imports.** They are unit-tested headlessly. `os.path` is fine.
- **Run the full suite** with `python3 -m pytest` from the repo root (`/mnt/c/Users/apeci/AppData/Roaming/FreeCAD/v1-1/Mod/ArchPlus`) — 31 parts are validated against the real shipped library by `test_library_content.py`.
- **Part ids** are `/`-joined lowercase slugs, each segment matching `^[a-z0-9][a-z0-9-]*$`: `basic/coffee-table`.
- **No automated test can execute a builder** (the fake `Part` has no `makeBox`, `makeCylinder`, or `makeCone`). Correctness of moved geometry rests on the reversibility check in Task 5's script — reversing the rewrite must recover the original source byte for byte — plus the manual FreeCAD pass at the end of this plan.

---

### Task 1: Move `_shapes.py` to `partslib/shapes.py`

`_shapes.py` is imported by all four family modules today and will be imported by 31 part builders and every family's `_shared.py`. It is public vocabulary, not a `builders/` internal, so it moves up and loses its underscore.

**Files:**
- Move: `archplus/tools/partslib/builders/_shapes.py` → `archplus/tools/partslib/shapes.py`
- Modify: `archplus/tools/partslib/builders/furniture.py:27`
- Modify: `archplus/tools/partslib/builders/kitchen.py:22`
- Modify: `archplus/tools/partslib/builders/sanitary.py:8`
- Modify: `archplus/tools/partslib/builders/fittings.py:19`
- Test: `archplus/tools/partslib/tests/test_shapes_module.py` (create)

**Interfaces:**
- Consumes: nothing
- Produces: module `archplus.tools.partslib.shapes`, importable headlessly, exposing `rounded_box(length, width, height, radius=0)`, `soften_top(shape, radius, z=None)`, `square_leg(height, size, chamfer=None)`, `roll_top(shape, radius, axis="y", z=None)`, `tapered_leg(height, bottom_radius, top_radius)`, `cut_box(shape, x, y, z, length, width, height)`, `cut_boxes(shape, boxes)`, `cushion(length, width, height, radius=None, edge=None)`, `bar(length, radius, along="x")`, `panel_reveal_boxes(...)`, `panel_reveal(...)`, `toe_kick(...)`, `door_seam(...)`, `oval(shape, scale_x, scale_y)`, `rotate(shape, axis, degrees, center=(0.0, 0.0, 0.0))`, `tube_elbow(tube_radius, bend_radius, angle=90.0)`, `vector(x, y, z)`, `place(shape, x, y, z)`, `fuse_all(shapes)`, `safe_fillet(shape, radius, edges)`

- [ ] **Step 1: Write the failing test**

Create `archplus/tools/partslib/tests/test_shapes_module.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Guards the public surface of the shared geometry vocabulary. Every part
# builder and every family's _shared.py imports this module by its absolute
# path, so losing a name here breaks parts that never mention it directly.

from archplus.tools.partslib import shapes


def test_shapes_is_importable_without_freecad():
    # Imported at module scope above: the assertion is that the import
    # itself did not raise under the fake Part in conftest.py.
    assert shapes.__name__ == "archplus.tools.partslib.shapes"


def test_the_public_massing_vocabulary_is_present():
    expected = [
        "rounded_box", "soften_top", "square_leg", "roll_top", "tapered_leg",
        "cut_box", "cut_boxes", "cushion", "bar", "panel_reveal_boxes",
        "panel_reveal", "toe_kick", "door_seam", "oval", "rotate",
        "tube_elbow", "vector", "place", "fuse_all", "safe_fillet",
    ]
    missing = [name for name in expected
               if not callable(getattr(shapes, name, None))]
    assert missing == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest archplus/tools/partslib/tests/test_shapes_module.py -v`
Expected: FAIL — `ImportError: cannot import name 'shapes' from 'archplus.tools.partslib'`

- [ ] **Step 3: Move the file**

```bash
git mv archplus/tools/partslib/builders/_shapes.py archplus/tools/partslib/shapes.py
```

Do not edit its contents.

- [ ] **Step 4: Update the four importers**

In each of `builders/furniture.py`, `builders/kitchen.py`, `builders/sanitary.py`, `builders/fittings.py`, replace the single line:

```python
from . import _shapes as sh
```

with:

```python
from archplus.tools.partslib import shapes as sh
```

Absolute, not relative: these functions are about to move to two different tree depths (`library/basic/_shared.py` and `library/basic/<part>/builder.py`), and an absolute import is correct at both.

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest`
Expected: PASS, including the 2 new tests. `test_library_content.py` still reports zero scan errors for all 31 parts.

- [ ] **Step 6: Commit**

```bash
git add archplus/tools/partslib/shapes.py archplus/tools/partslib/builders/ archplus/tools/partslib/tests/test_shapes_module.py
git commit -m "refactor: promote _shapes to partslib/shapes as public vocabulary"
```

---

### Task 2: Move all 31 part folders into `library/basic/`

The category folders (`furniture/`, `kitchen/`, `sanitary/`, `fittings/`) are read by no code and cannot express a part that belongs to two rooms. They are replaced by one style family. Ids are still explicit in every manifest, so this task changes no behaviour.

**Files:**
- Create: `archplus/tools/partslib/library/basic/` (directory)
- Move: all 31 `archplus/tools/partslib/library/<category>/<part>/` → `archplus/tools/partslib/library/basic/<part>/`
- Delete: the four now-empty category directories
- Test: `archplus/tools/partslib/tests/test_library_content.py` (modify — add one test)

**Interfaces:**
- Consumes: nothing
- Produces: every part manifest at `library/basic/<part>/part.json`; `facets.json` stays at `library/facets.json`

- [ ] **Step 1: Write the failing test**

Append to `archplus/tools/partslib/tests/test_library_content.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest archplus/tools/partslib/tests/test_library_content.py::test_every_part_lives_under_a_family_folder -v`
Expected: FAIL — `library/fittings/curtain/part.json is not under library/basic/`

- [ ] **Step 3: Move the folders**

```bash
cd archplus/tools/partslib/library
mkdir basic
git mv fittings/* furniture/* kitchen/* sanitary/* basic/
rmdir fittings furniture kitchen sanitary
cd -
```

Verify 31 part folders landed and `facets.json` did not move:

```bash
ls archplus/tools/partslib/library/          # expect: basic  facets.json
ls archplus/tools/partslib/library/basic | wc -l   # expect: 31
```

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest`
Expected: PASS. `test_scan_reports_zero_errors_for_the_shipped_library` still passes — ids come from the manifests, which are unchanged. The on-disk index cache self-invalidates because every manifest path changed and `is_cache_valid` compares paths.

- [ ] **Step 5: Commit**

```bash
git add -A archplus/tools/partslib/library archplus/tools/partslib/tests/test_library_content.py
git commit -m "refactor: collapse library category folders into a single basic/ family

The category level was read by no code and could not express a part
belonging to two rooms - mirror declares room [Bathroom, Bedroom] and a
folder can only pick one. Browse taxonomy lives in facets."
```

---

### Task 3: Derive part ids from the library-relative path

**Files:**
- Modify: `archplus/tools/partslib/manifest.py:21` (`REQUIRED_FIELDS`), `:136-139` (id validation)
- Modify: `archplus/tools/partslib/index.py:58`
- Test: `archplus/tools/partslib/tests/test_partslib_manifest.py` (modify)
- Test: `archplus/tools/partslib/tests/test_partslib_index.py` (modify)

**Interfaces:**
- Consumes: nothing
- Produces:
  - `manifest.validate_part_id(part_id)` → `list` of error strings, empty when valid. Accepts `/`-joined slugs.
  - `index.scan(library_dir)` entries whose `"id"` is the library-relative folder path when the manifest omits `id`, and the manifest's `id` verbatim when present.

- [ ] **Step 1: Write the failing tests**

Append to `archplus/tools/partslib/tests/test_partslib_manifest.py`:

```python
def test_a_path_shaped_id_is_valid():
    assert pm.validate_part_id("basic/coffee-table") == []


def test_a_single_segment_id_is_valid():
    # A standalone part - one reserved for future one-off imports - sits at
    # the library root and so has a one-segment id.
    assert pm.validate_part_id("geberit-icon") == []


def test_an_uppercase_id_segment_is_rejected():
    assert pm.validate_part_id("basic/Coffee-Table") != []


def test_an_underscore_id_segment_is_rejected():
    assert pm.validate_part_id("basic/coffee_table") != []


def test_an_id_segment_containing_a_dot_is_rejected():
    # A dot would split the dotted import path used to load builder.py.
    assert pm.validate_part_id("basic/55.inch") != []


def test_an_empty_id_is_rejected():
    assert pm.validate_part_id("") != []


def test_a_manifest_without_an_id_is_valid():
    # The id is derived from the folder; only an explicit override is checked.
    data = _part()
    del data["id"]
    errors, _warnings = pm.validate_manifest(data, FACETS)
    assert [e for e in errors if "id" in e] == []
```

`FACETS` and `_part` are the module-level fixtures already in that file (lines 3 and 106).

Append to `archplus/tools/partslib/tests/test_partslib_index.py`. Note that this file imports `index as px`, uses a module-level `FACETS` whose only legal values are `function` ∈ {`Sanitary`, `Seating`}, `element` ∈ {`WC`, `Chair`}, `room` ∈ {`Bathroom`, `Kitchen`}, and that its existing `_library()` helper derives each folder name from `part["id"]` — which these tests cannot use, since the point is a manifest with no id. Add one helper beside `_library`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest archplus/tools/partslib/tests/test_partslib_manifest.py archplus/tools/partslib/tests/test_partslib_index.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'validate_part_id'`, and the index tests fail with `missing required field 'id'` reported as a scan error.

- [ ] **Step 3: Add `validate_part_id` and make `id` optional in `manifest.py`**

Change `REQUIRED_FIELDS` at line 21 from:

```python
REQUIRED_FIELDS = ("schema", "id", "name", "facets", "geometry")
```

to:

```python
# `id` is NOT required: it is derived from the part's folder path by
# index.scan(). A manifest may still declare one to pin identity across a
# folder rename, and it is validated when present.
REQUIRED_FIELDS = ("schema", "name", "facets", "geometry")

KNOWN_FIELDS = REQUIRED_FIELDS + ("id",) + (
```

(The existing `KNOWN_FIELDS = REQUIRED_FIELDS + (` line keeps its remaining
entries; `"id"` is added back so an explicit id is still a known field.)

Add this function next to `_ID_RE`:

```python
def validate_part_id(part_id):
    """Errors for a part id: '/'-joined lowercase slugs, or [] if valid.

    An id is a part's folder path relative to the library root, so it has one
    segment for a standalone part and two for a family member. Each segment
    must satisfy _ID_RE - which forbids '.', the one character that would
    split the dotted import path used to load the part's builder.py."""
    if not isinstance(part_id, str) or not part_id:
        return ["id %r must be a non-empty string" % (part_id,)]
    segments = part_id.split("/")
    if not all(_ID_RE.match(segment) for segment in segments):
        return ["id %r must be '/'-joined lowercase slugs [a-z0-9-]"
                % (part_id,)]
    return []
```

Replace the id check at lines 136-139:

```python
    part_id = data.get("id")
    if part_id is not None and not (
            isinstance(part_id, str) and _ID_RE.match(part_id)):
        errors.append("id %r must be a lowercase slug [a-z0-9-]" % (part_id,))
```

with:

```python
    if data.get("id") is not None:
        errors.extend(validate_part_id(data["id"]))
```

- [ ] **Step 4: Derive the id in `index.py`**

Replace line 58:

```python
        part_id = data["id"]
```

with:

```python
        # The folder path IS the id unless the manifest pins one. Deriving it
        # makes a collision unrepresentable: two parts cannot share a path,
        # and every brand sells a mirror.
        part_id = data.get("id") or os.path.relpath(
            os.path.dirname(path), library_dir).replace(os.sep, "/")
        id_errors = pm.validate_part_id(part_id)
        if id_errors:
            errors.extend("%s: %s" % (path, e) for e in id_errors)
            continue
```

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest`
Expected: PASS. All 31 shipped manifests still carry an explicit `id`, so ids are unchanged at this point — the derivation is proven by the new tmp_path tests only.

- [ ] **Step 6: Commit**

```bash
git add archplus/tools/partslib/manifest.py archplus/tools/partslib/index.py archplus/tools/partslib/tests/test_partslib_manifest.py archplus/tools/partslib/tests/test_partslib_index.py
git commit -m "feat: derive part ids from the library-relative folder path

Path ids are unique by construction, which matters as soon as a second
family exists. An explicit id still overrides, to pin identity across a
folder rename."
```

---

### Task 4: Local-first builder resolution

Installs `load_local_builder` and rewires `build_shape` to prefer a part's own `builder.py`. The `geometry.builder` symbol becomes a fallback so Tasks 5-8 can migrate parts one at a time without ever breaking the library. No part has a `builder.py` yet, so behaviour is unchanged by this task.

`LIBRARY_DIR` currently lives in `object.py:54`, which imports FreeCAD at module scope. `geometry.py` needs it for the containment guard and must stay headless, so the constant moves to `geometry.py` and `object.py` re-exports it (`gui.py:563` reads `partslib_object.LIBRARY_DIR`).

**Files:**
- Modify: `archplus/tools/partslib/geometry.py` (add constants + `load_local_builder`, rewire `build_shape`)
- Modify: `archplus/tools/partslib/object.py:54`
- Test: `archplus/tools/partslib/tests/test_partslib_geometry.py` (modify)

**Interfaces:**
- Consumes: nothing
- Produces:
  - `geometry.LIBRARY_DIR` — absolute path to `archplus/tools/partslib/library`
  - `geometry.LIBRARY_PACKAGE` — `"archplus.tools.partslib.library"`
  - `geometry.load_local_builder(part_dir)` → the part's `build` callable; raises `ValueError` when the directory is outside the library, a path segment contains `.`, the module will not import, or `build` is missing/not defined in that module
  - `geometry.has_local_builder(part_dir)` → `bool`, True when `<part_dir>/builder.py` exists
  - `build_shape` resolution order: local `builder.py` → `geometry.builder` symbol → `asset.single`

- [ ] **Step 1: Write the failing tests**

Add to `archplus/tools/partslib/tests/test_partslib_geometry.py`:

```python
import os
import sys

import pytest


@pytest.fixture
def fixture_library(tmp_path, monkeypatch):
    """A throwaway library root that is importable as a namespace package.

    Points geometry at tmp_path instead of the shipped library, so these
    tests never create or delete files under library/. tmp_path goes on
    sys.path so the fixture root imports as a top-level namespace package -
    no __init__.py anywhere, which is exactly how library/ works.
    """
    root = tmp_path / "fixturelib"
    root.mkdir()
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(pg, "LIBRARY_DIR", str(root))
    monkeypatch.setattr(pg, "LIBRARY_PACKAGE", "fixturelib")
    yield root
    for name in [n for n in list(sys.modules)
                 if n == "fixturelib" or n.startswith("fixturelib.")]:
        del sys.modules[name]


def _write_builder(part_dir, body="    return 'built'"):
    part_dir.mkdir(parents=True, exist_ok=True)
    (part_dir / "builder.py").write_text(
        "def build(params, assets, ctx):\n%s\n" % body)


def test_a_local_builder_resolves(fixture_library):
    part = fixture_library / "basic" / "television"
    _write_builder(part)

    builder = pg.load_local_builder(str(part))

    assert builder(None, None, None) == "built"


def test_a_local_builder_resolves_for_a_standalone_part(fixture_library):
    # One-off imports sit at the library root, so a one-segment path must
    # resolve too.
    part = fixture_library / "geberit-icon"
    _write_builder(part)

    assert callable(pg.load_local_builder(str(part)))


def test_a_part_directory_outside_the_library_is_rejected(
        fixture_library, tmp_path):
    outside = tmp_path / "elsewhere" / "evil"
    _write_builder(outside)

    with pytest.raises(ValueError):
        pg.load_local_builder(str(outside))


def test_the_library_root_itself_is_not_a_part(fixture_library):
    with pytest.raises(ValueError):
        pg.load_local_builder(str(fixture_library))


def test_a_dot_in_a_path_segment_is_rejected(fixture_library):
    part = fixture_library / "basic" / "55.inch"
    _write_builder(part)

    with pytest.raises(ValueError):
        pg.load_local_builder(str(part))


def test_a_builder_module_without_build_is_rejected(fixture_library):
    part = fixture_library / "basic" / "nobuild"
    part.mkdir(parents=True)
    (part / "builder.py").write_text("def make(params, assets, ctx):\n    pass\n")

    with pytest.raises(ValueError):
        pg.load_local_builder(str(part))


def test_an_imported_name_is_not_accepted_as_build(fixture_library):
    # `build` must be DEFINED here, not pulled in from elsewhere, so a
    # star-import cannot smuggle in a callable.
    part = fixture_library / "basic" / "imported"
    part.mkdir(parents=True)
    (part / "builder.py").write_text("from os.path import join as build\n")

    with pytest.raises(ValueError):
        pg.load_local_builder(str(part))


def test_has_local_builder_reports_file_presence(fixture_library):
    with_file = fixture_library / "basic" / "has-one"
    _write_builder(with_file)
    without = fixture_library / "basic" / "has-none"
    without.mkdir(parents=True)

    assert pg.has_local_builder(str(with_file)) is True
    assert pg.has_local_builder(str(without)) is False


def test_a_local_builder_wins_over_a_manifest_symbol(fixture_library):
    # This is what lets the migration proceed one part at a time: the moment
    # a part's builder.py lands it takes over, and a part without one still
    # resolves through its symbol.
    part = fixture_library / "basic" / "television"
    _write_builder(part, "    return 'local'")

    resolved = {"geometry": {"builder": "asset.single"}, "params": {}}
    builder = pg.select_builder(resolved, str(part))

    assert builder(None, None, None) == "local"


def test_a_part_with_no_local_builder_uses_its_symbol(fixture_library):
    part = fixture_library / "basic" / "vendor-chair"
    part.mkdir(parents=True)

    resolved = {"geometry": {"builder": "asset.single"}, "params": {}}

    assert pg.select_builder(resolved, str(part)) is pg.resolve_builder(
        "asset.single")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest archplus/tools/partslib/tests/test_partslib_geometry.py -v -k "local or standalone or dot_in or has_local or symbol"`
Expected: FAIL — `AttributeError: module 'archplus.tools.partslib.geometry' has no attribute 'load_local_builder'`

- [ ] **Step 3: Add the constants and resolvers to `geometry.py`**

After the existing `BUILDER_PACKAGE` / `CACHE_DIRNAME` lines, add:

```python
_DIR = os.path.dirname(os.path.abspath(__file__))
LIBRARY_DIR = os.path.join(_DIR, "library")
LIBRARY_PACKAGE = "archplus.tools.partslib.library"
BUILDER_MODULE = "builder"
BUILDER_FILENAME = BUILDER_MODULE + ".py"
```

`LIBRARY_DIR` lives here, not in `object.py`, because the containment guard needs it and this module must stay importable without FreeCAD.

After `resolve_builder`, add:

```python
def has_local_builder(part_dir):
    """True when this part folder carries its own builder.py."""
    return os.path.exists(os.path.join(part_dir, BUILDER_FILENAME))


def load_local_builder(part_dir):
    """Import a part folder's own builder.py and return its build().

    The manifest names NOTHING on this route - the module path is derived
    from where the part lives - so a manifest cannot point at code outside
    its own folder. The library tree is the import tree: no __init__.py is
    needed anywhere under it, because a directory without one is a namespace
    package, and `from .. import _shared` still resolves inside those."""
    base = os.path.abspath(LIBRARY_DIR)
    target = os.path.abspath(part_dir)

    # Containment, checked the same way AssetLoader.shape() checks asset
    # paths - including the ValueError, which commonpath raises for two
    # paths on different Windows drives.
    try:
        contained = os.path.commonpath([base, target]) == base
    except ValueError:
        contained = False
    if not contained or target == base:
        raise ValueError("part directory %r is not inside the library"
                         % (part_dir,))

    segments = os.path.relpath(target, base).replace("\\", "/").split("/")
    for segment in segments:
        if "." in segment:
            raise ValueError(
                "part folder %r cannot contain '.': it would split the "
                "import path" % (segment,))

    module_name = "%s.%s.%s" % (
        LIBRARY_PACKAGE, ".".join(segments), BUILDER_MODULE)
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ValueError("cannot import %s: %s" % (module_name, exc))

    builder = getattr(module, "build", None)
    # `in vars(module)` and not just getattr: an imported or inherited name
    # must not be usable as a builder. Same rule as resolve_builder.
    if "build" not in vars(module) or not callable(builder):
        raise ValueError("%s has no callable build()" % (module_name,))
    return builder


def select_builder(resolved, part_dir):
    """The callable that builds this part.

    Local-first: a part's own builder.py wins. The manifest's `builder`
    symbol is a transitional fallback while builders move into part folders
    (see the plan's Tasks 5-8); once every part has a builder.py it is
    removed and the last resort is the stock asset builder, which is what an
    asset-only part - one shipping no code at all - uses."""
    if has_local_builder(part_dir):
        return load_local_builder(part_dir)
    symbol = (resolved.get("geometry") or {}).get("builder")
    if symbol:
        return resolve_builder(symbol)
    return resolve_builder("asset.single")
```

- [ ] **Step 4: Rewire `build_shape`**

In `build_shape`, replace:

```python
    geometry = resolved.get("geometry") or {}
    symbol = geometry.get("builder")
    builder = resolve_builder(symbol)
    params = partslib_manifest.merge_params(resolved, overrides)
```

with:

```python
    geometry = resolved.get("geometry") or {}
    builder = select_builder(resolved, part_dir)
    params = partslib_manifest.merge_params(resolved, overrides)
```

Then in the cache key, replace `symbol` with the builder's own module name, so
a part that switches from a symbol to a local builder cannot get a stale hit:

```python
    key = (os.path.abspath(part_dir), getattr(builder, "__module__", ""),
           resolved.get("variantLabel"),
           repr(sorted(params.items(), key=lambda item: item[0])),
           repr(sorted((geometry.get("assets") or {}).items())))
```

- [ ] **Step 5: Re-export `LIBRARY_DIR` from `object.py`**

Replace `object.py:54`:

```python
LIBRARY_DIR = os.path.join(_DIR, "library")
```

with:

```python
# Defined in geometry.py, which needs it for the builder containment guard
# and must stay importable without FreeCAD. Re-exported here because
# gui.py reads partslib_object.LIBRARY_DIR.
LIBRARY_DIR = partslib_geometry.LIBRARY_DIR
```

- [ ] **Step 6: Fix the cache tests' monkeypatch target**

The cache tests at `test_partslib_geometry.py:129-183` patch `resolve_builder`, which `build_shape` no longer calls directly. In `_patched_builder`, replace:

```python
    monkeypatch.setattr(pg, "resolve_builder", lambda symbol: _build)
```

with:

```python
    monkeypatch.setattr(pg, "select_builder",
                        lambda resolved, part_dir: _build)
```

- [ ] **Step 7: Run the full suite**

Run: `python3 -m pytest`
Expected: PASS. All 31 parts still resolve through their `geometry.builder` symbol, because none has a `builder.py` yet.

- [ ] **Step 8: Commit**

```bash
git add archplus/tools/partslib/geometry.py archplus/tools/partslib/object.py archplus/tools/partslib/tests/test_partslib_geometry.py
git commit -m "feat: resolve a part's own builder.py ahead of its manifest symbol

Local-first resolution is what lets 1835 lines of builder code move one
part at a time: a part switches over the moment its file lands, and a part
not yet migrated keeps resolving through its symbol."
```

---

### Task 5: Extraction script, proven on `fittings.py` (4 parts)

Writes the one-shot extraction tool and applies it to the smallest family module first, so a systematic error surfaces on 4 parts rather than 31. The script AST-compares each extracted body against the original and refuses to write on any mismatch — the strongest check available, since no test can execute a builder.

**Files:**
- Create: `tools/extract_builders.py` (throwaway, deleted in Task 9)
- Create: `archplus/tools/partslib/library/basic/television/builder.py`
- Create: `archplus/tools/partslib/library/basic/mirror/builder.py`
- Create: `archplus/tools/partslib/library/basic/floor-lamp/builder.py`
- Create: `archplus/tools/partslib/library/basic/curtain/builder.py`
- Modify: `archplus/tools/partslib/builders/fittings.py` (delete the 4 functions)
- Test: `archplus/tools/partslib/tests/test_library_content.py` (modify — add one test)

**Interfaces:**
- Consumes: `geometry.has_local_builder`, `geometry.load_local_builder` (Task 4)
- Produces: `library/basic/<part>/builder.py` exposing `build(params, assets, ctx)`, importable headlessly. Each imports `from archplus.tools.partslib import shapes as sh` when its body references `sh.`

- [ ] **Step 1: Write the failing test**

Append to `archplus/tools/partslib/tests/test_library_content.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest archplus/tools/partslib/tests/test_library_content.py::test_every_local_builder_imports_and_exposes_build -v`
Expected: FAIL — `AssertionError: no part has a builder.py yet`

- [ ] **Step 3: Write the extraction script**

Create `tools/extract_builders.py`:

```python
#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# ONE-SHOT MIGRATION TOOL - delete after the builders have moved.
#
# Copies a builder function out of a family module into the owning part's
# folder as builder.py, renamed to build(). No test can execute a builder
# (conftest fakes Part), so this script is the correctness argument: it
# compares the AST of the function body it wrote against the AST of the
# body it read, and refuses to write anything on a mismatch.

import argparse
import ast
import json
import os
import sys

PARTSLIB = os.path.join("archplus", "tools", "partslib")
BUILDERS = os.path.join(PARTSLIB, "builders")
LIBRARY = os.path.join(PARTSLIB, "library", "basic")

# Family-module helpers that move to library/basic/_shared.py in Task 9.
# A body referencing one of these gets its calls rewritten and an import of
# the family module added. Keys are the private names in the family module;
# values are the public names in _shared.py.
SHARED_RENAMES = {
    "_carcass": "carcass",
    "_doors": "doors",
    "_pulls": "pulls",
}

HEADER = "# SPDX-License-Identifier: LGPL-2.1-or-later\n"


def part_dirs():
    """{part folder name: absolute path} for every part in the library."""
    found = {}
    for name in sorted(os.listdir(LIBRARY)):
        path = os.path.join(LIBRARY, name)
        if os.path.isfile(os.path.join(path, "part.json")):
            found[name] = path
    return found


def builder_symbol(part_path):
    with open(os.path.join(part_path, "part.json")) as fh:
        data = json.load(fh)
    return (data.get("geometry") or {}).get("builder")


def function_source(module_source, name):
    """(source text, ast node) for a top-level function, or raise."""
    tree = ast.parse(module_source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(module_source, node), node
    raise SystemExit("no top-level function %r found" % (name,))


def rewrite(source, func_name, rename_map):
    """Rename the def to build() and repoint shared-helper calls."""
    source = source.replace("def %s(" % func_name, "def build(", 1)
    for private, public in rename_map.items():
        source = source.replace("%s(" % private, "_shared.%s(" % public)
    return source


def unrewrite(source, func_name, rename_map):
    """Exactly reverse rewrite(), so the result can be compared verbatim."""
    source = source.replace("def build(", "def %s(" % func_name, 1)
    for private, public in rename_map.items():
        source = source.replace("_shared.%s(" % public, "%s(" % private)
    return source


def build_file(source, uses_shapes, uses_shared):
    lines = [HEADER, "\n"]
    if uses_shapes:
        lines.append("from archplus.tools.partslib import shapes as sh\n")
    if uses_shared:
        lines.append("from .. import _shared\n")
    if uses_shapes or uses_shared:
        lines.append("\n\n")
    lines.append(source.rstrip("\n") + "\n")
    return "".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("module", help="family module, e.g. fittings")
    parser.add_argument("--apply", action="store_true",
                        help="write files (default is a dry run)")
    parser.add_argument("--only", default="",
                        help="comma-separated part folder names; needed where "
                             "two parts share one function, which must not be "
                             "copied into both folders")
    args = parser.parse_args()
    only = [name for name in args.only.split(",") if name]

    module_path = os.path.join(BUILDERS, args.module + ".py")
    with open(module_path) as fh:
        module_source = fh.read()

    written = []
    for part_name, part_path in sorted(part_dirs().items()):
        symbol = builder_symbol(part_path)
        if not symbol or not symbol.startswith(args.module + "."):
            continue
        if only and part_name not in only:
            continue
        func_name = symbol.split(".", 1)[1]
        source, _node = function_source(module_source, func_name)

        renames = {name: public for name, public in SHARED_RENAMES.items()
                   if "%s(" % name in source}
        rewritten = rewrite(source, func_name, renames)
        contents = build_file(rewritten, "sh." in source, bool(renames))

        # The proof, in two parts.
        #
        # 1. It parses, and defines exactly one build(). Catches a rewrite
        #    that produced something Python cannot read.
        new_tree = ast.parse(contents)
        new_func = [n for n in new_tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "build"]
        if len(new_func) != 1:
            raise SystemExit("%s: rewrite did not produce exactly one build()"
                             % (part_name,))
        # 2. Reversing the rewrite recovers the original source EXACTLY.
        #    Stronger than comparing ASTs, and it holds for the renamed
        #    kitchen parts too: anything the rewrite touched beyond the def
        #    line and the helper calls shows up as a string difference.
        if unrewrite(rewritten, func_name, renames) != source:
            raise SystemExit("%s: rewrite is not reversible - it changed more "
                             "than the def line and the helper calls"
                             % (part_name,))
        extracted = ast.get_source_segment(contents, new_func[0])
        if unrewrite(extracted, func_name, renames) != source:
            raise SystemExit("%s: extracted body differs from the original"
                             % (part_name,))

        target = os.path.join(part_path, "builder.py")
        print("%-24s %-28s -> %s" % (part_name, symbol, target))
        if args.apply:
            with open(target, "w") as fh:
                fh.write(contents)
        written.append((part_name, func_name))

    print("\n%d part(s) %s" % (len(written),
                               "written" if args.apply else "matched (dry run)"))
    print("Remove from %s: %s" % (
        module_path, ", ".join(name for _part, name in written)))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Dry-run the script on `fittings`**

Run: `python3 tools/extract_builders.py fittings`
Expected output lists exactly 4 parts and no `SystemExit`:

```
curtain                  fittings.curtain             -> .../curtain/builder.py
floor-lamp               fittings.floor_lamp          -> .../floor-lamp/builder.py
mirror                   fittings.mirror              -> .../mirror/builder.py
television               fittings.television          -> .../television/builder.py

4 part(s) matched (dry run)
```

If it reports a body mismatch, stop and fix the script — do not hand-edit the output.

- [ ] **Step 5: Apply it**

Run: `python3 tools/extract_builders.py fittings --apply`

- [ ] **Step 6: Delete the four functions from `fittings.py`**

Remove `television`, `mirror`, `floor_lamp`, and `curtain` from `archplus/tools/partslib/builders/fittings.py`. The file's module docstring carries design prose that must not be lost:

- The paragraph about screens and mirrors being planes read from their frame and recess moves into `television/builder.py` and `mirror/builder.py` as a comment above `build`.
- The whole curtain paragraph ("Grooves SUBTRACT from a plane; folds DISPLACE it") moves into `curtain/builder.py`.

After removal `fittings.py` holds only its header and the `sh` import; leave it in place — Task 9 deletes it.

- [ ] **Step 7: Run the full suite**

Run: `python3 -m pytest`
Expected: PASS. The 4 fittings parts now resolve through their `builder.py`; the other 27 still use their symbols. `test_every_local_builder_imports_and_exposes_build` now checks 4 parts.

- [ ] **Step 8: Commit**

```bash
git add tools/extract_builders.py archplus/tools/partslib/library/basic archplus/tools/partslib/builders/fittings.py archplus/tools/partslib/tests/test_library_content.py
git commit -m "refactor: colocate the four fittings builders with their parts

Extraction is script-driven and AST-verified: no test can execute a
builder, so the script compares the body it writes against the body it
read and refuses to write on any mismatch."
```

---

### Task 6: Extract `kitchen.py` (6 parts)

Three of these reference the module-private `_carcass` / `_doors` / `_pulls`, so the script rewrites those calls to `_shared.carcass(...)` and adds `from .. import _shared`. `library/basic/_shared.py` does not exist until Task 9, so these three parts do not resolve until then — which is why this task's suite run tolerates it and Task 9 closes the loop.

**Files:**
- Create: `library/basic/{base-cabinet,wall-cabinet,oven-cabinet,corner-base-cabinet,corner-wall-cabinet,gas-hob}/builder.py`
- Modify: `archplus/tools/partslib/builders/kitchen.py` (delete the 6 public functions; keep `_carcass`, `_doors`, `_pulls` for Task 9)

**Interfaces:**
- Consumes: `tools/extract_builders.py` (Task 5)
- Produces: 6 `builder.py` files. `base-cabinet`, `wall-cabinet`, and `oven-cabinet` reference `_shared.carcass`, `_shared.doors`, `_shared.pulls`, satisfied in Task 9.

- [ ] **Step 1: Dry-run**

Run: `python3 tools/extract_builders.py kitchen`
Expected: 6 parts listed, no mismatch. `base-cabinet`, `wall-cabinet`, `oven-cabinet` are the ones whose output will carry `from .. import _shared`.

- [ ] **Step 2: Apply**

Run: `python3 tools/extract_builders.py kitchen --apply`

- [ ] **Step 3: Verify the shared-helper rewrite landed**

Run: `grep -n "_shared\." archplus/tools/partslib/library/basic/*/builder.py`
Expected: `_shared.carcass(`, `_shared.doors(`, `_shared.pulls(` in `base-cabinet`, and the matching subset in `wall-cabinet` and `oven-cabinet`. No bare `_carcass(` anywhere:

Run: `grep -rn "[^.]_carcass(\|[^.]_doors(\|[^.]_pulls(" archplus/tools/partslib/library/`
Expected: no output.

- [ ] **Step 4: Delete the 6 public functions from `kitchen.py`**

Remove `base_cabinet`, `oven_cabinet`, `corner_base_cabinet`, `wall_cabinet`, `corner_wall_cabinet`, and `hob`. **Keep** `_carcass`, `_doors`, and `_pulls` — Task 9 moves them.

Move this design prose out of the module docstring:
- The two-paragraph note on L-shaped corner plans ("one box with a rectangular notch cut out of the inside corner … no boolean between two overlapping solids") → `corner-base-cabinet/builder.py`, above `build`.
- The `WALL UNITS ARE WALL-HOSTED` paragraph → `wall-cabinet/builder.py`.
- The opening paragraph about a carcass with a toe kick, panel-reveal doors and a handle stays with `_carcass` and travels to `_shared.py` in Task 9.

- [ ] **Step 5: Run the suite**

Run: `python3 -m pytest -k "not test_every_local_builder"`
Expected: PASS.

Then run the local-builder check on its own:

Run: `python3 -m pytest archplus/tools/partslib/tests/test_library_content.py::test_every_local_builder_imports_and_exposes_build -v`
Expected: FAIL for `basic/base-cabinet`, `basic/wall-cabinet`, `basic/oven-cabinet` with `cannot import … no module named '_shared'`. This is the expected interim state; Task 9 resolves it. Record the failure in the commit message rather than working around it.

- [ ] **Step 6: Commit**

```bash
git add archplus/tools/partslib/library/basic archplus/tools/partslib/builders/kitchen.py
git commit -m "refactor: colocate the six kitchen builders with their parts

base-cabinet, wall-cabinet and oven-cabinet now import from .. import
_shared, which does not exist until the family module lands - so
test_every_local_builder_imports_and_exposes_build fails for those three
until the next commit."
```

---

### Task 7: Extract `sanitary.py` (7 parts)

**Files:**
- Create: `library/basic/{vanity,toilet,shower-base,bathtub,shower-screen,towel-hook,toilet-roll-holder}/builder.py`
- Modify: `archplus/tools/partslib/builders/sanitary.py` (delete all 7 functions)

**Interfaces:**
- Consumes: `tools/extract_builders.py` (Task 5)
- Produces: 7 `builder.py` files, each self-contained apart from `shapes`

- [ ] **Step 1: Dry-run**

Run: `python3 tools/extract_builders.py sanitary`
Expected: 7 parts listed, no mismatch, none needing `_shared`.

- [ ] **Step 2: Apply**

Run: `python3 tools/extract_builders.py sanitary --apply`

- [ ] **Step 3: Delete all 7 functions from `sanitary.py`**

Remove `vanity`, `toilet`, `shower_base`, `bathtub`, `shower_screen`, `towel_hook`, and `toilet_roll_holder`, carrying any function-specific prose from the module docstring into the matching `builder.py`.

- [ ] **Step 4: Run the suite**

Run: `python3 -m pytest -k "not test_every_local_builder"`
Expected: PASS.

Run: `python3 -m pytest archplus/tools/partslib/tests/test_library_content.py::test_every_local_builder_imports_and_exposes_build -v`
Expected: still only the 3 kitchen `_shared` failures from Task 6 — the 7 sanitary parts import cleanly.

- [ ] **Step 5: Commit**

```bash
git add archplus/tools/partslib/library/basic archplus/tools/partslib/builders/sanitary.py
git commit -m "refactor: colocate the seven sanitary builders with their parts"
```

---

### Task 8: Extract `furniture.py` (14 parts)

Ten parts extract normally. Four — `dining-table`, `coffee-table`, `king-bed`, `single-bed` — share `table` and `bed`, which move to `_shared.py`. Those four get a hand-written delegating `builder.py` instead of an extraction, because the shared function *is* the whole builder today.

**Files:**
- Create: `library/basic/{desk,basic-chair,nightstand,wardrobe,sofa,bookcase,side-table,armchair,chest-of-drawers,media-unit}/builder.py` (extracted)
- Create: `library/basic/{dining-table,coffee-table,king-bed,single-bed}/builder.py` (hand-written)
- Modify: `archplus/tools/partslib/builders/furniture.py` (delete the 10 extracted functions; keep `table` and `bed` for Task 9)

**Interfaces:**
- Consumes: `tools/extract_builders.py` (Task 5)
- Produces: 14 `builder.py` files. The four delegating ones call `_shared.table(params, assets, ctx)` / `_shared.bed(params, assets, ctx)`, satisfied in Task 9.

- [ ] **Step 1: Dry-run**

Run: `python3 tools/extract_builders.py furniture`
Expected: 14 parts listed. Note that `dining-table` and `coffee-table` both map to `furniture.table`, and `king-bed`/`single-bed` both to `furniture.bed` — the script would write the same body into two folders each. Do **not** apply it as-is.

- [ ] **Step 2: Apply to the ten unshared parts only**

Use the script's `--only` flag, which exists for exactly this case:

```bash
python3 tools/extract_builders.py furniture --apply --only \
  desk,basic-chair,nightstand,wardrobe,sofa,bookcase,side-table,armchair,chest-of-drawers,media-unit
```

Expected: `10 part(s) written`.

- [ ] **Step 3: Hand-write the four delegating builders**

Create `archplus/tools/partslib/library/basic/dining-table/builder.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# A dining table: the family's apron-framed table at seating height.
#
# This delegates rather than duplicating because the dining table and the
# coffee table are genuinely one design at two proportions today - the
# manifest's ShelfHeight is what distinguishes them. When a real difference
# appears, it belongs here rather than as another branch in _shared.table.

from .. import _shared


def build(params, assets, ctx):
    return _shared.table(params, assets, ctx)
```

Create `archplus/tools/partslib/library/basic/coffee-table/builder.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# A coffee table: the family's apron-framed table, low, with a lower shelf.
#
# Delegates to the shared table for the same reason dining-table does; the
# manifest's non-zero ShelfHeight is the only thing separating them today.

from .. import _shared


def build(params, assets, ctx):
    return _shared.table(params, assets, ctx)
```

Create `archplus/tools/partslib/library/basic/king-bed/builder.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# A king bed: the family's divan-based bed with a panelled headboard.
#
# Delegates to the shared bed - king and single are one design at two
# mattress widths today. A real per-size difference goes here.

from .. import _shared


def build(params, assets, ctx):
    return _shared.bed(params, assets, ctx)
```

Create `archplus/tools/partslib/library/basic/single-bed/builder.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# A single bed: the family's divan-based bed with a panelled headboard.
#
# Delegates to the shared bed for the same reason king-bed does.

from .. import _shared


def build(params, assets, ctx):
    return _shared.bed(params, assets, ctx)
```

- [ ] **Step 4: Delete the ten extracted functions from `furniture.py`**

Remove `desk`, `chair`, `nightstand`, `wardrobe`, `sofa`, `bookcase`, `side_table`, `armchair`, `chest_of_drawers`, and `media_unit`. **Keep** `table` and `bed`.

Carry each function's design prose into its `builder.py` — in particular the note in `table` about square posts reading better than thin cylinders at thumbnail size, and the note about `ShelfHeight` being what distinguishes a coffee table from a scaled dining table, both of which travel with `table` to `_shared.py`.

- [ ] **Step 5: Run the suite**

Run: `python3 -m pytest -k "not test_every_local_builder"`
Expected: PASS.

Run: `python3 -m pytest archplus/tools/partslib/tests/test_library_content.py::test_every_local_builder_imports_and_exposes_build -v`
Expected: FAIL for 7 parts now — the 3 kitchen ones plus the 4 delegating ones, all missing `_shared`. Task 9 fixes all 7.

- [ ] **Step 6: Commit**

```bash
git add archplus/tools/partslib/library/basic archplus/tools/partslib/builders/furniture.py
git commit -m "refactor: colocate the fourteen furniture builders with their parts

Ten are extracted; dining-table, coffee-table, king-bed and single-bed are
hand-written delegations, because the shared function is the entire builder
today and duplicating it into two folders each would fork it immediately."
```

---

### Task 9: Create `library/basic/_shared.py` and delete the family modules

Closes the 7 failing imports from Tasks 6 and 8 and empties `builders/` of family code.

**Files:**
- Create: `archplus/tools/partslib/library/basic/_shared.py`
- Delete: `archplus/tools/partslib/builders/furniture.py`, `kitchen.py`, `sanitary.py`, `fittings.py`
- Delete: `tools/extract_builders.py`
- Test: `archplus/tools/partslib/tests/test_library_content.py` (already written in Task 5)

**Interfaces:**
- Consumes: nothing
- Produces: `library/basic/_shared.py` exposing, with signatures identical to the originals apart from the dropped underscore:
  - `carcass(width, depth, height, kick_height, kick_depth, radius=8.0)`
  - `doors(shape, width, height, door_count, base_z, margin=None, groove=6.0, seam=4.0)`
  - `pulls(width, height, door_count, base_z, y, vertical=True)`
  - `table(params, assets, ctx)`
  - `bed(params, assets, ctx)`

- [ ] **Step 1: Create `_shared.py`**

Create `archplus/tools/partslib/library/basic/_shared.py` with the LGPL header, this docstring, an absolute `shapes` import, and the five functions moved verbatim from the family modules — `_carcass`, `_doors`, `_pulls` renamed to `carcass`, `doors`, `pulls` (they are no longer module-private), and `table` and `bed` unchanged:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# The basic family's design language - the massing decisions shared by more
# than one part in this family, as opposed to the primitives in
# partslib/shapes.py, which every family uses.
#
# Kitchen units are the most repetitive group here: nearly every one is a
# carcass with a toe kick, doors carrying a panel reveal, and a handle.
# carcass() does that once, and each part's builder differs only in what
# sits on top (a worktop, nothing) and what is cut into the front (doors, an
# oven, a drawer bank).
#
# table() and bed() are whole builders rather than helpers, because the two
# tables and the two beds in this family are each one design at two sizes
# today. Their parts delegate here; when a real difference appears it belongs
# in that part's builder.py, not as another branch in this file.

from archplus.tools.partslib import shapes as sh
```

Then paste, in this order: `carcass`, `doors`, `pulls` (from `kitchen.py`, de-underscored), `table`, `bed` (from `furniture.py`). Change nothing inside the function bodies. Keep the prose comments that travelled with `table` about square legs and `ShelfHeight`.

- [ ] **Step 2: Run the local-builder test to verify it now passes**

Run: `python3 -m pytest archplus/tools/partslib/tests/test_library_content.py::test_every_local_builder_imports_and_exposes_build -v`
Expected: PASS, checking all 31 parts.

- [ ] **Step 3: Verify no part still resolves through a symbol**

Run:

```bash
python3 - <<'EOF'
import os
from archplus.tools.partslib import geometry as pg, index as pi
idx = pi.scan(pg.LIBRARY_DIR)
missing = [e["id"] for e in idx["entries"]
           if not pg.has_local_builder(e["dir"])]
print("entries:", len(idx["entries"]))
print("without builder.py:", missing)
EOF
```

Expected: `entries: 31`, `without builder.py: []`

- [ ] **Step 4: Delete the four family modules and the script**

```bash
git rm archplus/tools/partslib/builders/furniture.py \
       archplus/tools/partslib/builders/kitchen.py \
       archplus/tools/partslib/builders/sanitary.py \
       archplus/tools/partslib/builders/fittings.py \
       tools/extract_builders.py
```

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest`
Expected: PASS. Every part resolves locally; `builders/` retains only `__init__.py`, `asset.py`, and `demo.py`.

- [ ] **Step 6: Commit**

```bash
git add archplus/tools/partslib/library/basic/_shared.py archplus/tools/partslib/builders
git commit -m "refactor: move the basic family's shared design language into _shared.py

Deletes the four family modules. All 31 parts now resolve through their own
builder.py, so the manifest symbol route is dead weight - removed next."
```

---

### Task 10: Delete the symbol mechanism

Every part now has a `builder.py`, so resolution collapses to the file-on-disk rule and the entire symbol apparatus goes.

**Files:**
- Modify: `archplus/tools/partslib/geometry.py` (delete `resolve_builder`, `_SYMBOL_RE`, `BUILDER_PACKAGE`, `import re`; simplify `select_builder`)
- Move: `archplus/tools/partslib/builders/asset.py` → `archplus/tools/partslib/asset.py`
- Delete: `archplus/tools/partslib/builders/demo.py`, `archplus/tools/partslib/builders/__init__.py`
- Modify: all 31 `archplus/tools/partslib/library/basic/*/part.json` (drop `geometry.builder`)
- Modify: `archplus/tools/partslib/manifest.py:147`
- Test: `archplus/tools/partslib/tests/test_partslib_geometry.py` (delete 8 tests, add 1)
- Test: `archplus/tools/partslib/tests/test_partslib_thumbs.py:99,121,140`
- Test: `archplus/tools/partslib/tests/test_library_content.py:59`

**Interfaces:**
- Consumes: nothing
- Produces: `geometry.select_builder(resolved, part_dir)` → local `build` when `builder.py` exists, else `asset.single`. `resolve_builder` no longer exists. `geometry.builder` is no longer a manifest field.

- [ ] **Step 1: Write the failing test**

Add to `archplus/tools/partslib/tests/test_partslib_geometry.py`:

```python
def test_a_part_without_a_builder_py_falls_back_to_the_asset_builder(
        fixture_library):
    # A part shipping no code at all IS an asset-only part. The absence of
    # builder.py is the guarantee, rather than a manifest string claiming it.
    from archplus.tools.partslib import asset

    part = fixture_library / "basic" / "vendor-chair"
    part.mkdir(parents=True)

    assert pg.select_builder({"geometry": {}}, str(part)) is asset.single


def test_a_manifest_builder_symbol_is_ignored(fixture_library):
    # The field is gone from the schema; a stale one must not resurrect a
    # resolution path that no longer exists.
    from archplus.tools.partslib import asset

    part = fixture_library / "basic" / "vendor-chair"
    part.mkdir(parents=True)

    resolved = {"geometry": {"builder": "anything.at.all"}}

    assert pg.select_builder(resolved, str(part)) is asset.single
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest archplus/tools/partslib/tests/test_partslib_geometry.py -v -k "falls_back or symbol_is_ignored"`
Expected: FAIL — `ImportError: cannot import name 'asset' from 'archplus.tools.partslib'`

- [ ] **Step 3: Move `asset.py` up and delete the rest of `builders/`**

```bash
git mv archplus/tools/partslib/builders/asset.py archplus/tools/partslib/asset.py
git rm archplus/tools/partslib/builders/demo.py archplus/tools/partslib/builders/__init__.py
```

Update the docstring in `asset.py` — it currently explains safety in terms of a manifest naming this builder. Replace its second paragraph with:

```python
# The stock builder for a part that ships no code of its own. A part folder
# with no builder.py IS an asset-only part: the absence of the file is what
# guarantees nothing from that folder executes, rather than a manifest
# string claiming it. That is the property that could let a user-supplied
# library be admitted as data only.
```

- [ ] **Step 4: Simplify `geometry.py`**

Delete `import re`, `BUILDER_PACKAGE`, `_SYMBOL_RE`, and the whole `resolve_builder` function. Add `from . import asset` beside the existing `from . import manifest as partslib_manifest`. Replace `select_builder` with:

```python
def select_builder(resolved, part_dir):
    """The callable that builds this part.

    The file on disk decides: a part with its own builder.py uses it, and a
    part without one is asset-only and uses the stock asset builder. The
    manifest names nothing, so it cannot point at code anywhere - which is a
    stronger guarantee than the symbol it replaced, because "this part ships
    no executable code" is now the absence of a file rather than a claim
    that has to be kept true."""
    if has_local_builder(part_dir):
        return load_local_builder(part_dir)
    return asset.single
```

`resolved` stays in the signature: it is what `build_shape` has in hand, and dropping it would churn the call site for no gain.

- [ ] **Step 5: Delete the obsolete tests**

From `test_partslib_geometry.py`, delete these 8, all of which test the removed mechanism:

`test_malformed_builder_symbols_are_rejected`, `test_unknown_builder_module_is_rejected`, `test_unknown_builder_function_is_rejected`, `test_stock_asset_builder_resolves`, `test_demo_builder_resolves`, `test_dunder_attribute_is_not_resolved_as_a_builder`, `test_dunder_init_is_not_resolved_as_a_builder`, and `test_a_part_with_no_local_builder_uses_its_symbol` (added in Task 4 for the transitional route).

Also delete `test_a_local_builder_wins_over_a_manifest_symbol` — superseded by `test_a_manifest_builder_symbol_is_ignored`.

In `_manifest()`, drop the now-meaningless parameter:

```python
def _manifest(params=None, variant=None):
    data = {
        "geometry": {},
        "params": params or {"Width": {"type": "Length", "default": 100}},
    }
    if variant is not None:
        data["variantLabel"] = variant
    return data
```

Update its call sites in the same file if any pass `builder=`.

- [ ] **Step 6: Drop the dead field from the thumbs tests**

At `test_partslib_thumbs.py` lines 99, 121, and 140, change:

```python
    resolved = {"geometry": {"builder": "demo.box"}, "params": {}}
```

to:

```python
    resolved = {"geometry": {}, "params": {}}
```

The symbol was never resolved in any of these three — each monkeypatches `FreeCAD` to `None` or replaces `build_shape` — so this is a rename of an unused placeholder.

- [ ] **Step 7: Drop `geometry.builder` from all 31 manifests**

```bash
python3 - <<'EOF'
import json, os
LIB = "archplus/tools/partslib/library/basic"
for name in sorted(os.listdir(LIB)):
    path = os.path.join(LIB, name, "part.json")
    if not os.path.isfile(path):
        continue
    with open(path) as fh:
        raw = fh.read()
    data = json.loads(raw)
    geometry = data.get("geometry") or {}
    if "builder" not in geometry:
        continue
    del geometry["builder"]
    data["geometry"] = geometry
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    print("cleaned", path)
EOF
```

Then confirm none remain:

Run: `grep -rn '"builder"' archplus/tools/partslib/library/`
Expected: no output.

Inspect one diff to confirm formatting matches the surrounding files:

Run: `git diff archplus/tools/partslib/library/basic/television/part.json`

- [ ] **Step 8: Stop validating `geometry.builder` in `manifest.py`**

Replace the block at lines 143-148:

```python
    geometry = data.get("geometry")
    if geometry is not None:
        if not isinstance(geometry, dict):
            errors.append("geometry must be an object")
        elif not isinstance(geometry.get("builder"), str):
            errors.append("geometry has no 'builder'")
```

with:

```python
    geometry = data.get("geometry")
    if geometry is not None and not isinstance(geometry, dict):
        # `geometry` stays required - it carries `assets` and `transform` -
        # but it names no builder. Which code runs is decided by whether the
        # part folder holds a builder.py, so there is nothing here to check.
        errors.append("geometry must be an object")
```

Remove `"builder"` from any manifest test that asserts the old error.

- [ ] **Step 9: Update the library-content builder test**

Replace `test_every_entry_geometry_builder_resolves` at `test_library_content.py:59` with:

```python
def test_every_entry_resolves_to_a_builder():
    # Local builder.py or the asset fallback - every part must end up with a
    # callable, and the fallback path must not raise for a part that has no
    # builder.py of its own.
    index = _scan()
    for entry in index["entries"]:
        resolved = partslib_manifest.resolve_variant(
            partslib_manifest.load_manifest(entry["path"]),
            entry["variants"][0])
        assert callable(partslib_geometry.select_builder(
            resolved, entry["dir"])), entry["id"]
```

- [ ] **Step 10: Run the full suite**

Run: `python3 -m pytest`
Expected: PASS. Confirm the mechanism is really gone:

Run: `grep -rn "resolve_builder\|_SYMBOL_RE\|BUILDER_PACKAGE" archplus/`
Expected: no output.

- [ ] **Step 11: Commit**

```bash
git add -A archplus/tools/partslib
git commit -m "refactor: resolve builders by file presence, deleting the symbol route

A manifest no longer names its builder. resolve_builder, _SYMBOL_RE, the
geometry.builder field, and the builders/ package are gone; asset.py moved
up and is imported. demo.py is deleted - its 'library ships empty'
rationale was stale and no test ever resolved it."
```

---

### Task 11: Drop the explicit `id` from all 31 manifests

**Files:**
- Modify: all 31 `archplus/tools/partslib/library/basic/*/part.json`
- Test: `archplus/tools/partslib/tests/test_library_content.py` (modify — add one test)

**Interfaces:**
- Consumes: `manifest.validate_part_id`, path-derived ids (Task 3)
- Produces: every shipped part's id is `basic/<folder>`

- [ ] **Step 1: Write the failing test**

Append to `archplus/tools/partslib/tests/test_library_content.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest archplus/tools/partslib/tests/test_library_content.py -v -k "derived_from_its_folder or ids_are_unique"`
Expected: FAIL — `.../television/part.json pins an explicit id`

- [ ] **Step 3: Strip the field**

```bash
python3 - <<'EOF'
import json, os
LIB = "archplus/tools/partslib/library/basic"
for name in sorted(os.listdir(LIB)):
    path = os.path.join(LIB, name, "part.json")
    if not os.path.isfile(path):
        continue
    with open(path) as fh:
        data = json.load(fh)
    if "id" not in data:
        continue
    assert data["id"] == name, (path, data["id"], name)
    del data["id"]
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    print("stripped", path)
EOF
```

The `assert` is the safety net: it refuses to strip an id that does not already match its folder, which would silently change that part's identity.

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest`
Expected: PASS, with all 31 ids now `basic/<folder>`.

- [ ] **Step 5: Commit**

```bash
git add -A archplus/tools/partslib
git commit -m "refactor: derive every shipped part id from its folder

Ids change from 'mirror' to 'basic/mirror'. A document saved before this
keeps its geometry - execute() warns and preserves the cached shape - but
loses parametric editing until the part is replaced. The library shipped
two days ago, so no compatibility shim is carried."
```

---

### Task 12: Scan-time builder check and builder reload on rescan

Two safety nets the colocated design needs. Without the first, a forgotten `builder.py` fails at insert time as "part declares no asset 'body'", which points at the wrong problem. Without the second, editing a `builder.py` appears to do nothing until FreeCAD restarts, because Python caches the imported module.

**Files:**
- Modify: `archplus/tools/partslib/index.py` (add the check to `scan`)
- Modify: `archplus/tools/partslib/geometry.py` (`clear_shape_cache`)
- Test: `archplus/tools/partslib/tests/test_partslib_index.py` (modify)
- Test: `archplus/tools/partslib/tests/test_partslib_geometry.py` (modify)

**Interfaces:**
- Consumes: `geometry.LIBRARY_PACKAGE` (Task 4)
- Produces: `scan()` reports an error for a part with neither a `builder.py` nor a non-empty `geometry.assets`; `clear_shape_cache()` also purges imported library builder modules from `sys.modules`

- [ ] **Step 1: Make the existing index fixtures satisfy the new rule**

This check would otherwise fail 12 existing tests. `_part()` in `test_partslib_index.py:22` produces `"geometry": {"builder": "asset.single"}` — a symbol that no longer means anything, no declared assets, and no `builder.py` on disk, so the new check would reject every fixture part. Turn the fixtures into genuine asset-only parts by changing `_part`'s geometry from:

```python
        "geometry": {"builder": "asset.single"},
```

to:

```python
        # No builder.py on disk and a declared asset: an asset-only part,
        # which is what the fixture has always meant.
        "geometry": {"assets": {"body": "wc-360.brep"}},
```

- [ ] **Step 2: Write the failing tests**

Append to `archplus/tools/partslib/tests/test_partslib_index.py`, reusing `_library_at` and `_unnamed_part` from Task 3:

```python
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
```

Append to `archplus/tools/partslib/tests/test_partslib_geometry.py`:

```python
def test_clearing_the_cache_forgets_imported_library_builders(fixture_library):
    part = fixture_library / "basic" / "editable"
    _write_builder(part, "    return 'first'")

    assert pg.load_local_builder(str(part))(None, None, None) == "first"

    (part / "builder.py").write_text(
        "def build(params, assets, ctx):\n    return 'second'\n")
    # Without the sys.modules purge the edit is invisible for the rest of
    # the session, which is the whole point of this call.
    pg.clear_shape_cache()

    assert pg.load_local_builder(str(part))(None, None, None) == "second"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest archplus/tools/partslib/tests/test_partslib_index.py archplus/tools/partslib/tests/test_partslib_geometry.py -v -k "no_builder_and_no_assets or builder_py_is_accepted or asset_only_part_needs or forgets_imported"`
Expected: FAIL — the index accepts the builder-less part, and the geometry test still returns `'first'` after the edit.

- [ ] **Step 4: Add the scan check to `index.py`**

Add near the other module constants:

```python
BUILDER_FILENAME = "builder.py"
```

In `scan`, after the id block added in Task 3 and before the entry is appended:

```python
        # A part builds either from its own code or from a declared asset.
        # Neither means the part cannot produce geometry, and catching it
        # here turns a misleading "declares no asset 'body'" at insert time
        # into a scan error. os.path only - this module stays FreeCAD-free.
        part_dir = os.path.dirname(path)
        geometry = data.get("geometry") or {}
        if (not os.path.exists(os.path.join(part_dir, BUILDER_FILENAME))
                and not (geometry.get("assets") or {})):
            errors.append(
                "%s: has no %s and declares no geometry.assets"
                % (path, BUILDER_FILENAME))
            continue
```

- [ ] **Step 5: Purge imported builders in `clear_shape_cache`**

Add `import sys` to `geometry.py`'s imports. Replace `clear_shape_cache` with:

```python
def clear_shape_cache():
    """Forget every remembered shape, and every imported part builder.

    Called whenever the library is rescanned. A part's params are part of
    the cache key, so editing a manifest already misses the cache - but
    editing a BUILDER, or an asset file on disk, would not, and a rescan is
    the user saying "re-read the library" in as many words.

    Now that a part's code lives in its own folder, authoring a part means
    editing that builder.py - and Python caches an imported module for the
    life of the session, so the import is a second stale cache. Dropping
    both is what makes "Rescan library" actually re-read an edited builder
    instead of appearing to do nothing until FreeCAD restarts."""
    _SHAPE_CACHE.clear()
    del _SHAPE_CACHE_ORDER[:]
    _forget_library_builders()


def _forget_library_builders():
    """Drop every imported module under the library package."""
    prefix = LIBRARY_PACKAGE + "."
    for name in [name for name in list(sys.modules)
                 if name == LIBRARY_PACKAGE or name.startswith(prefix)]:
        del sys.modules[name]
```

- [ ] **Step 6: Run the full suite**

Run: `python3 -m pytest`
Expected: PASS. All 31 shipped parts have a `builder.py`, so the new scan check passes for the real library.

- [ ] **Step 7: Commit**

```bash
git add archplus/tools/partslib/index.py archplus/tools/partslib/geometry.py archplus/tools/partslib/tests
git commit -m "feat: catch a missing builder.py at scan time and reload builders on rescan

The implicit asset fallback would otherwise report a forgotten builder.py
as 'declares no asset body'. And with code in part folders, sys.modules is
a second stale cache that a rescan has to drop."
```

---

### Task 13: Documentation

**Files:**
- Modify: `README.md` (§2b builder-writing, the add-a-part walkthrough at ~197 and ~242, the `partslib_builders/` path at 290-296)
- Modify: `docs/PARTS-LIBRARY-VERIFICATION.md` (stale paths at 360 and 376, the `demo.box` snippet in Part J at ~448-459, `partslib_builders/_shapes.py` at 20)
- Modify: `docs/superpowers/specs/2026-08-15-parts-library-design.md` (mark §6.3 and §6.4 superseded)

**Interfaces:**
- Consumes: the finished implementation
- Produces: docs that describe the shipped layout

- [ ] **Step 1: Rewrite README §2b**

Replace the "Write a builder (parametric geometry)" section. It currently opens with "Manifests reference geometry by symbol only — `"module.function"`, resolved inside `archplus/tools/partslib/builders/`". Replace that paragraph and its example with:

````markdown
### 2b. Write a builder (parametric geometry)

A part's geometry code lives in its own folder, next to its manifest. Create
`builder.py` beside `part.json` and give it a `build` function — nothing in
the manifest names it, and nothing needs registering:

```python
# archplus/tools/partslib/library/basic/bar-stool/builder.py
from archplus.tools.partslib import shapes as sh


def build(params, assets, ctx):
    """One docstring line, then the params it reads."""
    height = float(params.get("Height", 750))
    diameter = float(params.get("SeatDiameter", 340))
    ...
    return sh.fuse_all([seat] + legs)      # -> a Part.Shape
```

The contract is `def build(params, assets, ctx) -> Part.Shape`. Import
`Part`/`FreeCAD` *inside* the function, never at module scope, so the
headless test suite can import the module without FreeCAD present.

A part with **no** `builder.py` is an asset-only part: it is built by the
stock asset builder from the file named in `geometry.assets`. The absence of
the file is what guarantees no code from that folder runs.

`shapes.py` carries the shared massing primitives — `rounded_box`,
`square_leg`, `roll_top`, `panel_reveal_boxes`, `cut_boxes`, `toe_kick`,
`bar`, `tube_elbow`, `place`, `fuse_all`. Prefer them: every fillet in there
already falls back to a sharp edge rather than aborting the build when OCC
refuses.

Massing shared by several parts in the same family goes in the family's
`_shared.py`, reached as `from .. import _shared`. That relative import means
"my family" at any depth, so a part can later move into a sub-family folder
without editing its builder.
````

- [ ] **Step 2: Fix the README's example paths**

At line ~197, `archplus/tools/partslib/library/furniture/my-stool/part.json` becomes `archplus/tools/partslib/library/basic/my-stool/part.json`.

At line ~242, `archplus/tools/partslib/library/sanitary/geberit-icon/` becomes `archplus/tools/partslib/library/geberit-icon/` — a purchased single model with no family is exactly the standalone case, so use it to introduce that rule.

- [ ] **Step 3: Document the id break in the README**

Add to the parts-library section:

```markdown
> **One-time break (2026-08-17).** Part ids are now derived from the folder
> path, so `mirror` became `basic/mirror`. A document saved before this keeps
> its geometry — the object holds its own cached shape and ArchPlus warns
> `part 'mirror' is not in the library` rather than touching it — but its
> Parameters stop being editable. Delete and re-place the part to get
> parametric editing back.
```

- [ ] **Step 4: Fix `docs/PARTS-LIBRARY-VERIFICATION.md`**

- Line 20: `partslib_builders/_shapes.py` → `partslib/shapes.py`
- Lines 360 and 376: `library/furniture/base-cabinet/part.json` → `library/basic/base-cabinet/part.json`. This path was wrong twice over — `base-cabinet` was under `kitchen/`, not `furniture/`, which nothing caught because no code reads that level.
- Part J (~448-459): the `demo.box` snippet no longer resolves. Replace the `resolved` dict with `{"geometry": {}, "params": {...}}` and point the instruction at a real part directory, e.g. `library/basic/nightstand`, using `partslib_geometry.select_builder`.

- [ ] **Step 5: Mark the old spec superseded**

At the top of `docs/superpowers/specs/2026-08-15-parts-library-design.md`, add:

```markdown
> **Partially superseded (2026-08-17).** §6.4 "Builders are central, not
> per-part" and the builder-symbol half of §6.3 "Security" are replaced by
> `2026-08-17-colocated-part-builders-design.md`. Builders now live in each
> part's folder, resolved by file presence rather than by a manifest symbol.
> The zero-executable-code property §6.3 reserved for user-supplied libraries
> is kept and strengthened: an asset-only part is one with no `builder.py`.
```

- [ ] **Step 6: Verify no stale paths remain**

Run:

```bash
grep -rn "partslib_builders\|library/furniture\|library/kitchen\|library/sanitary\|library/fittings\|demo\.box" README.md docs/*.md
```

Expected: no output. (`docs/superpowers/plans/` and older specs are historical records — leave them.)

- [ ] **Step 7: Run the full suite one final time**

Run: `python3 -m pytest`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add README.md docs/PARTS-LIBRARY-VERIFICATION.md docs/superpowers/specs/2026-08-15-parts-library-design.md
git commit -m "docs: describe colocated builders and the family layout

Also fixes a path that was wrong before this work: the verification doc
told the reader to edit library/furniture/base-cabinet, but that part was
under kitchen/. Nothing caught it because no code read that level."
```

---

## Manual verification (required — no automated substitute)

`conftest.py` fakes `Part` with only `LineSegment` and `Circle`, so no test in this suite can execute a builder. Nothing above proves the geometry is unchanged. After Task 13, run the FreeCAD-side checks in `docs/PARTS-LIBRARY-VERIFICATION.md`, and specifically:

1. Open FreeCAD 1.1 with the ArchPlus add-on and open the Parts Library panel. All 31 parts appear with thumbnails.
2. Place one part from each former category — e.g. `nightstand`, `base-cabinet`, `bathtub`, `television` — and confirm each renders as it did before.
3. Place `base-cabinet` specifically: it is one of the three parts whose extracted body had `_carcass`/`_doors`/`_pulls` calls rewritten to `_shared.*`, so it is the highest-risk extraction.
4. Place `dining-table` and `coffee-table`: these use the hand-written delegations, and the two must still differ (the coffee table has a lower shelf).
5. Switch a variant on `wardrobe` and confirm the shape rebuilds.
6. Edit a `Parameters` value on any placed part and confirm it rebuilds.
7. Edit `library/basic/nightstand/builder.py` (change a dimension), click **Rescan library**, and confirm the change takes effect without restarting FreeCAD — this exercises Task 12's `sys.modules` purge.
