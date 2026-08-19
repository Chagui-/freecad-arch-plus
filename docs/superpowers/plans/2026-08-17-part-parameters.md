# Part Parameters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the parts-library `variants` list and replace it with per-part declared parameters that the browser panel exposes, with coupled values derived by each part's own `builder.py`.

**Architecture:** `params` gains four optional keys (`ui`, `label`, `default: "auto"`, `options`). Pure logic stays in the FreeCAD-free modules (`manifest.py`, `index.py`, `geometry.py`) where it is unit-tested; the FreeCAD-bound modules (`object.py`, `gui.py`) only do property and widget plumbing. Work lands additively first (new manifest functions, then per-part content), so the suite stays green at every commit; `variants` is deleted from the schema only once no shipped manifest declares it.

**Tech Stack:** Python in the style used throughout ArchPlus (`%`-formatting, no f-strings, no type annotations), pytest, PySide (faked in tests by `conftest.py`), FreeCAD/OCC at runtime only.

**Spec:** `docs/superpowers/specs/2026-08-17-part-parameters-design.md`

## Global Constraints

- `SCHEMA_VERSION` stays **1**. Nothing is released; this is a clean break, not a migration.
- `manifest.py`, `index.py` and `geometry.py` must remain **free of FreeCAD, Part and PySide imports** — the headless suite depends on it.
- Builders import `Part`/`FreeCAD` **inside** `build()`, never at module scope.
- Style: no f-strings, no type annotations, `%`-formatting, 4-space indent, SPDX header on new files.
- Every part folder is `archplus/tools/partslib/library/basic/<part-id>/` holding `part.json`, `builder.py` (unless asset-only) and `thumbnail.jpg`. Builders are found by **file presence**; nothing names them.
- Run the suite with `uvx --with pytest pytest archplus -q` from the repo root. Neither `python3` nor `python3.11` has pytest installed; `uvx` is the only working runner. Baseline before this plan: **204 passed**.
- Commit after every task. The branch is `part-parameters`; never commit to `main`.

---

### Task 1: `manifest.py` — primary params, `"auto"`, `Choice` options

Additive only. `variants` still works after this task; nothing is deleted yet.

**Files:**
- Modify: `archplus/tools/partslib/manifest.py`
- Test: `archplus/tools/partslib/tests/test_partslib_manifest.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `AUTO = "auto"` and `PRIMARY_FALLBACK = 3` module constants
  - `primary_params(manifest) -> list` of param names
  - `choice_options(spec) -> dict` — the ordered `options` map of a `Choice` spec, `{}` otherwise
  - `resolve_placement(manifest, params) -> dict` — the effective `placement` block
  - `merge_params(resolved, overrides) -> dict` — unchanged signature; an `"auto"` default now yields `None`

- [ ] **Step 1: Write the failing tests**

Append to `archplus/tools/partslib/tests/test_partslib_manifest.py` (the module is already imported there as `pm`):

```python
# -- primary_params ---------------------------------------------------------

def _part_with_ui():
    return {
        "schema": 1, "name": "Cabinet",
        "facets": {}, "geometry": {},
        "params": {
            "Width": {"type": "Length", "default": 600, "ui": "primary"},
            "Depth": {"type": "Length", "default": 600, "ui": "primary"},
            "KickHeight": {"type": "Length", "default": 100},
            "DoorCount": {"type": "Integer", "default": "auto"},
        },
    }


def test_primary_params_are_the_ones_marked_in_declared_order():
    assert pm.primary_params(_part_with_ui()) == ["Width", "Depth"]


def test_primary_params_falls_back_to_the_first_three_declared():
    data = _part_with_ui()
    for spec in data["params"].values():
        spec.pop("ui", None)
    assert pm.primary_params(data) == ["Width", "Depth", "KickHeight"]


def test_primary_params_fallback_stops_at_what_exists():
    data = {"params": {"Width": {"type": "Length", "default": 600}}}
    assert pm.primary_params(data) == ["Width"]


def test_primary_params_is_empty_when_no_params_declared():
    assert pm.primary_params({"params": {}}) == []


# -- "auto" defaults --------------------------------------------------------

def test_merge_params_resolves_an_auto_default_to_none():
    merged = pm.merge_params(_part_with_ui(), None)
    assert merged["DoorCount"] is None
    assert merged["Width"] == 600


def test_merge_params_override_pins_an_auto_param():
    merged = pm.merge_params(_part_with_ui(), {"DoorCount": 3})
    assert merged["DoorCount"] == 3


def test_merge_params_still_drops_an_undeclared_override():
    merged = pm.merge_params(_part_with_ui(), {"Nonsense": 1})
    assert "Nonsense" not in merged


# -- Choice options and placement ------------------------------------------

def _part_with_choice():
    return {
        "schema": 1, "name": "Television",
        "facets": {}, "geometry": {},
        "placement": {"host": "floor", "offset": 0},
        "params": {
            "ScreenSize": {"type": "Integer", "default": 55, "ui": "primary"},
            "Mounting": {
                "type": "Choice", "default": "stand", "ui": "primary",
                "options": {
                    "stand": {"label": "On stand"},
                    "wall": {"label": "Wall-mounted",
                             "placement": {"host": "wall", "offset": 1100}},
                },
            },
        },
    }


def test_choice_options_returns_the_declared_map():
    spec = _part_with_choice()["params"]["Mounting"]
    assert list(pm.choice_options(spec)) == ["stand", "wall"]


def test_choice_options_is_empty_for_a_non_choice_param():
    assert pm.choice_options({"type": "Length", "default": 600}) == {}


def test_resolve_placement_returns_the_part_block_when_no_option_overrides():
    data = _part_with_choice()
    assert pm.resolve_placement(data, {"Mounting": "stand"}) == {
        "host": "floor", "offset": 0}


def test_resolve_placement_merges_a_selected_option_over_the_part():
    data = _part_with_choice()
    assert pm.resolve_placement(data, {"Mounting": "wall"}) == {
        "host": "wall", "offset": 1100}


def test_resolve_placement_merges_per_key():
    data = _part_with_choice()
    data["params"]["Mounting"]["options"]["wall"]["placement"] = {
        "host": "wall"}
    assert pm.resolve_placement(data, {"Mounting": "wall"}) == {
        "host": "wall", "offset": 0}


def test_resolve_placement_ignores_an_unknown_option_value():
    data = _part_with_choice()
    assert pm.resolve_placement(data, {"Mounting": "nope"}) == {
        "host": "floor", "offset": 0}


def test_resolve_placement_never_mutates_the_manifest():
    data = _part_with_choice()
    pm.resolve_placement(data, {"Mounting": "wall"})
    assert data["placement"] == {"host": "floor", "offset": 0}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uvx --with pytest pytest archplus/tools/partslib/tests/test_partslib_manifest.py -q`
Expected: FAIL with `AttributeError: module 'archplus.tools.partslib.manifest' has no attribute 'primary_params'`

- [ ] **Step 3: Add the constants**

In `archplus/tools/partslib/manifest.py`, beside `SCHEMA_VERSION`:

```python
# A param default of "auto" means the builder derives the value. It reaches
# the builder as None, so a builder that forgot to derive it fails loudly on
# int(None) rather than silently building the wrong thing.
AUTO = "auto"

# How many params a part that marks none gets promoted to the browser panel.
PRIMARY_FALLBACK = 3
```

- [ ] **Step 4: Add the three new functions**

Immediately after `param_specs`:

```python
def primary_params(manifest):
    """Ordered names of the params the browser panel shows.

    A part that marks none gets its first PRIMARY_FALLBACK declared params,
    so a panel is never empty and a lazily-authored manifest still works."""
    specs = param_specs(manifest)
    marked = [name for name, spec in specs.items()
              if (spec or {}).get("ui") == "primary"]
    if marked:
        return marked
    return list(specs)[:PRIMARY_FALLBACK]


def choice_options(spec):
    """The ordered options map of a Choice param spec, else {}."""
    if (spec or {}).get("type") != "Choice":
        return {}
    options = spec.get("options")
    return dict(options) if isinstance(options, dict) else {}


def resolve_placement(manifest, params):
    """The effective placement block for one set of param values.

    The part's own `placement` first, then each Choice param's SELECTED
    option's `placement` merged over it per key, in declared order. Merging
    per key is what lets an option say only `host` and keep the part's own
    `offset`.

    This is what a variant's placement override used to do, narrowed to one
    axis: a television on a stand is floor-hosted, the same television on a
    bracket is wall-hosted at a mounting height, and that is a choice the
    user makes rather than a second catalogue entry."""
    resolved = dict(manifest.get("placement") or {})
    params = params or {}
    for name, spec in param_specs(manifest).items():
        options = choice_options(spec)
        if not options:
            continue
        selected = options.get(params.get(name))
        if not isinstance(selected, dict):
            continue
        override = selected.get("placement")
        if isinstance(override, dict):
            resolved.update(override)
    return resolved
```

- [ ] **Step 5: Teach `merge_params` about `"auto"`**

Replace the final loop of `merge_params` with:

```python
    for name, spec in param_specs(resolved).items():
        default = spec.get("default")
        if default == AUTO:
            default = None
        value = overrides.get(name)
        merged[name] = value if value is not None else default
```

and add this paragraph to its docstring:

```
    A declared default of "auto" resolves to None, which is the builder's
    signal to derive the value from the other params. An override still
    wins, so typing a number into a derived field pins it.
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uvx --with pytest pytest archplus/tools/partslib/tests/test_partslib_manifest.py -q`
Expected: PASS, including every pre-existing variant test — nothing was removed.

- [ ] **Step 7: Run the whole suite**

Run: `uvx --with pytest pytest archplus -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add archplus/tools/partslib/manifest.py archplus/tools/partslib/tests/test_partslib_manifest.py
git commit -m "Add primary_params, auto defaults, Choice options and resolve_placement"
```

---

### Task 2: `geometry.py` — rename `resolved` to `manifest`, document the `None` contract

**Files:**
- Modify: `archplus/tools/partslib/geometry.py`
- Test: `archplus/tools/partslib/tests/test_partslib_geometry.py`

**Interfaces:**
- Consumes: `manifest.merge_params` (Task 1).
- Produces: `build_shape(manifest, part_dir, overrides=None)` and `select_builder(manifest, part_dir)` — same behaviour, first parameter renamed.

- [ ] **Step 1: Read the test file's existing helpers**

Run: `sed -n '1,100p' archplus/tools/partslib/tests/test_partslib_geometry.py`

Note the names of its fake-shape class and its monkeypatched builder helper.
The tests below use `_Shape` and `_manifest`; substitute the file's own names
if they differ, rather than adding duplicates.

- [ ] **Step 2: Write the failing tests**

Append to `archplus/tools/partslib/tests/test_partslib_geometry.py`:

```python
def test_an_auto_param_reaches_the_builder_as_none(tmp_path, monkeypatch):
    seen = {}

    def _builder(params, assets, ctx):
        seen.update(params)
        return _Shape()

    monkeypatch.setattr(pg, "select_builder",
                        lambda manifest, part_dir: _builder)
    pg.build_shape(
        {"geometry": {},
         "params": {"Width": {"type": "Length", "default": 600},
                    "DoorCount": {"type": "Integer", "default": "auto"}}},
        str(tmp_path))
    assert seen == {"Width": 600, "DoorCount": None}


def test_a_pinned_value_and_an_auto_param_key_differently(tmp_path, monkeypatch):
    builds = []

    def _builder(params, assets, ctx):
        builds.append(dict(params))
        return _Shape()

    monkeypatch.setattr(pg, "select_builder",
                        lambda manifest, part_dir: _builder)
    data = {"geometry": {},
            "params": {"DoorCount": {"type": "Integer", "default": "auto"}}}
    pg.build_shape(data, str(tmp_path))
    pg.build_shape(data, str(tmp_path), {"DoorCount": 2})
    assert len(builds) == 2
    assert builds[0]["DoorCount"] is None
    assert builds[1]["DoorCount"] == 2
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uvx --with pytest pytest archplus/tools/partslib/tests/test_partslib_geometry.py -q`
Expected: FAIL. If they already pass because Task 1 is in place, keep them
anyway — they are the regression guard for the `None` contract.

- [ ] **Step 4: Rename the parameter and document the contract**

In `geometry.py`, rename the first parameter of `select_builder` and
`build_shape` from `resolved` to `manifest`, updating every use inside those
two function bodies. In `select_builder`'s docstring, change

```
    `resolved` is retained deliberately for call-site stability and is no
```

to

```
    `manifest` is retained deliberately for call-site stability and is no
```

Add to `build_shape`'s docstring, immediately after the `overrides` paragraph:

```
    A param declared with the default "auto" reaches the builder as None.
    That is the builder's instruction to derive the value from the other
    params - "an 800mm cabinet has two doors" is design knowledge that
    belongs in the part's builder.py, not enumerated in its manifest.
    Builders must therefore test `params.get(name) is None` rather than
    relying on `params.get(name, fallback)`, whose fallback can no longer
    fire: the key is always present.
```

- [ ] **Step 5: Drop `variantLabel` from the cache key**

`build_shape`'s key still carries a component nothing will ever set again.
At `geometry.py:261`, delete the line

```python
           resolved.get("variantLabel"),
```

from the `key = (...)` tuple, and delete "which variant," from the docstring
paragraph above it that enumerates what the key contains.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uvx --with pytest pytest archplus/tools/partslib/tests/test_partslib_geometry.py -q`
Expected: PASS. The existing `test_different_variants_miss_the_cache` will now
FAIL — delete it; a variant label no longer exists to key on, and the two new
tests above cover what replaced it.

- [ ] **Step 7: Commit**

```bash
git add archplus/tools/partslib/geometry.py archplus/tools/partslib/tests/test_partslib_geometry.py
git commit -m "Rename build_shape's first argument to manifest and document the None contract"
```

---

### Task 3: Kitchen and sanitary coupled parts (5 parts)

Each part: delete `variants`, mark primaries, set the coupled param to
`"auto"`, and derive it in that part's own `builder.py`.

**Files:**
- Modify: `archplus/tools/partslib/library/basic/base-cabinet/{part.json,builder.py}`
- Modify: `archplus/tools/partslib/library/basic/wall-cabinet/{part.json,builder.py}`
- Modify: `archplus/tools/partslib/library/basic/wardrobe/{part.json,builder.py}`
- Modify: `archplus/tools/partslib/library/basic/gas-hob/{part.json,builder.py}`
- Modify: `archplus/tools/partslib/library/basic/vanity/{part.json,builder.py}`
- Test: `archplus/tools/partslib/tests/test_library_content.py`

**Interfaces:**
- Consumes: `manifest.merge_params` `"auto"` handling (Task 1).
- Produces: the `_entry(index, part_id)` and `_params(part_id, overrides=None)`
  test helpers, which Tasks 4, 5 and 6 reuse.

- [ ] **Step 1: Write the failing tests**

Append to `archplus/tools/partslib/tests/test_library_content.py`:

```python
def _entry(index, part_id):
    for entry in index["entries"]:
        if entry["id"] == part_id:
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uvx --with pytest pytest archplus/tools/partslib/tests/test_library_content.py -q`
Expected: FAIL with `base-cabinet should declare DoorCount as auto`.

- [ ] **Step 3: Edit the five manifests**

In each, delete the whole `"variants"` block and replace the `"params"` block
with the one below — the ordering is the UI ordering, so it matters.

`base-cabinet/part.json`:

```json
  "params": {
    "Width": { "type": "Length", "default": 600, "ui": "primary" },
    "Depth": { "type": "Length", "default": 600, "ui": "primary" },
    "Height": { "type": "Length", "default": 900, "ui": "primary" },
    "WorktopThickness": { "type": "Length", "default": 40 },
    "KickHeight": { "type": "Length", "default": 100 },
    "DoorCount": { "type": "Integer", "default": "auto", "label": "Doors" }
  },
```

`wall-cabinet/part.json`:

```json
  "params": {
    "Width": { "type": "Length", "default": 600, "ui": "primary" },
    "Height": { "type": "Length", "default": 720, "ui": "primary" },
    "Depth": { "type": "Length", "default": 350, "ui": "primary" },
    "DoorCount": { "type": "Integer", "default": "auto", "label": "Doors" }
  },
```

`wardrobe/part.json`:

```json
  "params": {
    "Width": { "type": "Length", "default": 1000, "ui": "primary" },
    "Height": { "type": "Length", "default": 2000, "ui": "primary" },
    "Depth": { "type": "Length", "default": 600, "ui": "primary" },
    "DoorCount": { "type": "Integer", "default": "auto", "label": "Doors" }
  },
```

`gas-hob/part.json` — the burner count is the chooser and the width follows:

```json
  "params": {
    "BurnerCount": { "type": "Integer", "default": 4, "ui": "primary",
                     "label": "Burners" },
    "Width": { "type": "Length", "default": "auto", "ui": "primary" },
    "Depth": { "type": "Length", "default": 520, "ui": "primary" },
    "PlateThickness": { "type": "Length", "default": 40 },
    "BurnerHeight": { "type": "Length", "default": 25 }
  },
```

`vanity/part.json`:

```json
  "params": {
    "Width": { "type": "Length", "default": 600, "ui": "primary" },
    "Depth": { "type": "Length", "default": 500, "ui": "primary" },
    "Height": { "type": "Length", "default": 850 },
    "BasinWidth": { "type": "Length", "default": "auto" },
    "BasinDepth": { "type": "Length", "default": 300 },
    "BasinRecess": { "type": "Length", "default": 120 },
    "BacksplashHeight": { "type": "Length", "default": 100 },
    "DoorCount": { "type": "Integer", "default": 2, "label": "Doors" }
  },
```

- [ ] **Step 4: Add the derivations to the five builders**

Read each builder first; the snippets assume `width` is already defined above
the line being replaced, which is true for all five.

`base-cabinet/builder.py` — replace

```python
    door_count = max(int(params.get("DoorCount", 1)), 0)
```

with

```python
    door_count = params.get("DoorCount")
    if door_count is None:
        # One door up to 600mm; past that a single leaf is too wide to swing
        # in a galley, so the carcass is split.
        door_count = 1 if width < 700 else 2
    door_count = max(int(door_count), 0)
```

`wall-cabinet/builder.py` — replace its `DoorCount` line with the same rule:

```python
    door_count = params.get("DoorCount")
    if door_count is None:
        # One door up to 600mm; past that the carcass is split, same rule as
        # the base cabinet it sits above.
        door_count = 1 if width < 700 else 2
    door_count = max(int(door_count), 0)
```

`wardrobe/builder.py` — replace its `DoorCount` line with:

```python
    door_count = params.get("DoorCount")
    if door_count is None:
        # A wardrobe leaf runs about 600mm, and never fewer than two, so the
        # carcass reads as a wardrobe rather than a tall cupboard.
        door_count = max(2, int(-(-int(width) // 600)))
    door_count = max(int(door_count), 1)
```

`gas-hob/builder.py` — the derived param is `Width`, so resolve it before
anything reads it. Replace the `width` line with:

```python
    burner_count = max(int(params.get("BurnerCount", 4)), 1)
    width = params.get("Width")
    if width is None:
        # 150mm of hob per burner: the 4-burner 600mm and 5-burner 750mm
        # sizes every manufacturer ships.
        width = 150.0 * burner_count
    width = float(width)
```

and delete the later `burner_count = ...` line so it is not computed twice.

`vanity/builder.py` — replace its `BasinWidth` line with:

```python
    basin_width = params.get("BasinWidth")
    if basin_width is None:
        # The basin takes half the top: a 600 unit gets a 300 basin, a 900
        # unit a 450.
        basin_width = width * 0.5
    basin_width = float(basin_width)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uvx --with pytest pytest archplus/tools/partslib/tests/test_library_content.py -q`
Expected: PASS.

Note what this does NOT prove. Nothing in the headless suite calls `build()`:
the builders reach `shapes.py`, which needs `Part`, so the shipped library is
never actually built under pytest. A builder that declared a param `"auto"`
and forgot to derive it would pass every test here and die on `int(None)`
only inside FreeCAD. Step 6 adds the closest headless substitute.

- [ ] **Step 6: Add the headless guard that every `"auto"` param is derived**

Since the shapes cannot be built under pytest, assert on the builder's SOURCE
instead: a param declared `"auto"` must be read and tested for `None` in the
builder that receives it. Append to
`archplus/tools/partslib/tests/test_library_content.py`:

```python
def test_every_auto_param_is_derived_by_its_builder():
    # The suite cannot call build() - the builders reach shapes.py, which
    # needs Part - so a forgotten derivation would otherwise surface only
    # inside FreeCAD, as int(None). Reading the source is the weaker but
    # available check: the param must be fetched and tested for None.
    import io

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
        for name in auto:
            assert 'params.get("%s")' % name in source, (
                "%s declares %s as auto but its builder never reads it"
                % (entry["id"], name))
            assert "is None" in source, (
                "%s declares %s as auto but its builder never tests for None"
                % (entry["id"], name))
```

Run: `uvx --with pytest pytest archplus/tools/partslib/tests/test_library_content.py -q`
Expected: PASS. This test also arms itself for Tasks 4 and 5, which add more
`"auto"` params.

- [ ] **Step 7: Run the whole suite**

Run: `uvx --with pytest pytest archplus -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add archplus/tools/partslib/library/basic archplus/tools/partslib/tests/test_library_content.py
git commit -m "Derive door counts, hob width and basin width in their builders"
```

---

### Task 4: Furniture coupled parts (5 parts)

`dining-table` gains a `SeatCount` param it never had, derived from `Width`
alone. The spec says "SeatCount ← Width, Depth"; the three shipped sizes
(1200×800, 1600×900, 2000×1000) are separable by width alone, so depth carries
no extra information and is left out rather than written in unused.

**Files:**
- Modify: `archplus/tools/partslib/library/basic/sofa/{part.json,builder.py}`
- Modify: `archplus/tools/partslib/library/basic/dining-table/{part.json,builder.py}`
- Modify: `archplus/tools/partslib/library/basic/chest-of-drawers/{part.json,builder.py}`
- Modify: `archplus/tools/partslib/library/basic/bookcase/{part.json,builder.py}`
- Modify: `archplus/tools/partslib/library/basic/media-unit/{part.json,builder.py}`
- Test: `archplus/tools/partslib/tests/test_library_content.py`

**Interfaces:**
- Consumes: `manifest.merge_params` `"auto"` handling (Task 1); the `_entry`
  and `_params` helpers added in Task 3.
- Produces: nothing other tasks import.

- [ ] **Step 1: Write the failing tests**

Append to `archplus/tools/partslib/tests/test_library_content.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uvx --with pytest pytest archplus/tools/partslib/tests/test_library_content.py -q`
Expected: FAIL with `sofa should declare Width as auto`.

- [ ] **Step 3: Edit the five manifests**

Delete each `"variants"` block and replace each `"params"` block with:

`sofa/part.json`:

```json
  "params": {
    "SeatCount": { "type": "Integer", "default": 2, "ui": "primary",
                   "label": "Seats" },
    "Width": { "type": "Length", "default": "auto", "ui": "primary" },
    "Depth": { "type": "Length", "default": 900, "ui": "primary" },
    "SeatHeight": { "type": "Length", "default": 420 },
    "BackHeight": { "type": "Length", "default": 400 },
    "BackThickness": { "type": "Length", "default": 250 },
    "ArmWidth": { "type": "Length", "default": 220 },
    "ArmHeight": { "type": "Length", "default": 620 }
  },
```

`dining-table/part.json`:

```json
  "params": {
    "Width": { "type": "Length", "default": 1200, "ui": "primary" },
    "Depth": { "type": "Length", "default": 800, "ui": "primary" },
    "Height": { "type": "Length", "default": 750 },
    "SeatCount": { "type": "Integer", "default": "auto", "label": "Seats" },
    "TopThickness": { "type": "Length", "default": 30 },
    "LegRadius": { "type": "Length", "default": 35 },
    "ApronHeight": { "type": "Length", "default": 70 }
  },
```

`chest-of-drawers/part.json`:

```json
  "params": {
    "DrawerCount": { "type": "Integer", "default": 3, "ui": "primary",
                     "label": "Drawers" },
    "Width": { "type": "Length", "default": 900, "ui": "primary" },
    "Depth": { "type": "Length", "default": 450, "ui": "primary" },
    "Height": { "type": "Length", "default": "auto", "ui": "primary" },
    "TopThickness": { "type": "Length", "default": 30 },
    "PlinthHeight": { "type": "Length", "default": 70 }
  },
```

`bookcase/part.json`:

```json
  "params": {
    "Width": { "type": "Length", "default": 800, "ui": "primary" },
    "Height": { "type": "Length", "default": 1800, "ui": "primary" },
    "Depth": { "type": "Length", "default": 300, "ui": "primary" },
    "ShelfCount": { "type": "Integer", "default": "auto", "label": "Shelves" }
  },
```

`media-unit/part.json`:

```json
  "params": {
    "Width": { "type": "Length", "default": 1600, "ui": "primary" },
    "Height": { "type": "Length", "default": 500, "ui": "primary" },
    "Depth": { "type": "Length", "default": 400, "ui": "primary" },
    "TopThickness": { "type": "Length", "default": 25 },
    "PlinthHeight": { "type": "Length", "default": 60 },
    "DoorWidth": { "type": "Length", "default": 420 },
    "ShelfCount": { "type": "Integer", "default": "auto", "label": "Shelves" }
  },
```

- [ ] **Step 4: Add the derivations to the five builders**

`sofa/builder.py` — `Width` is derived, so resolve it before anything reads it.
Replace the `width` and `seat_count` lines with:

```python
    seat_count = max(int(params.get("SeatCount", 2)), 1)
    width = params.get("Width")
    if width is None:
        # 300mm of extra body per seat over a 1300mm single-seat shell - the
        # 1600 two-seater and 1900 three-seater sold everywhere.
        width = 1000.0 + 300.0 * seat_count
    width = float(width)
```

`dining-table/builder.py` — add, after `width` is defined:

```python
    seat_count = params.get("SeatCount")
    if seat_count is None:
        # 500mm of table edge per diner, both long sides laid: 1200 seats 4,
        # 1600 seats 6, 2000 seats 8.
        seat_count = 2 * int(width // 500)
    seat_count = max(int(seat_count), 2)
```

`SeatCount` drives no geometry — the table has no per-seat parts — so add a
line to the builder's docstring saying so:

```
    SeatCount is derived from Width and reported rather than built: the
    table has no per-seat geometry, but the number is what a user picks by.
```

`chest-of-drawers/builder.py` — `Height` is derived. Replace its `height` line
with:

```python
    drawer_count = max(int(params.get("DrawerCount", 3)), 0)
    height = params.get("Height")
    if height is None:
        # 200mm per drawer over a 200mm plinth-and-top allowance: 3 drawers
        # give 800, 4 give 1000.
        height = 200.0 + 200.0 * drawer_count
    height = float(height)
```

and delete the later `drawer_count = ...` line so it is not computed twice.

`bookcase/builder.py` — replace its `shelf_count` line with:

```python
    shelf_count = params.get("ShelfCount")
    if shelf_count is None:
        # A shelf bay is about 450mm, and the top of the carcass is not a
        # shelf, so an 1800 case carries three.
        shelf_count = int(height // 450) - 1
    shelf_count = max(int(shelf_count), 0)
```

`media-unit/builder.py` — replace its `shelf_count` line with:

```python
    shelf_count = params.get("ShelfCount")
    if shelf_count is None:
        # One open bay per metre of run: 1600 gives one, 2000 gives two.
        shelf_count = int(width // 1000)
    shelf_count = max(int(shelf_count), 0)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uvx --with pytest pytest archplus/tools/partslib/tests/test_library_content.py -q`
Expected: PASS.

- [ ] **Step 6: Run the whole suite**

Run: `uvx --with pytest pytest archplus -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add archplus/tools/partslib/library/basic archplus/tools/partslib/tests/test_library_content.py
git commit -m "Derive sofa width, table seats, chest height and shelf counts in their builders"
```

---

### Task 5: `television` and `curtain` — the `Choice` param and the missing grid cell

This task closes the first diagnostic symptom: a 65" television on a stand,
which the old flat variant list silently lacked.

**Files:**
- Modify: `archplus/tools/partslib/library/basic/television/{part.json,builder.py}`
- Modify: `archplus/tools/partslib/library/basic/curtain/{part.json,builder.py}`
- Test: `archplus/tools/partslib/tests/test_library_content.py`

**Interfaces:**
- Consumes: `manifest.resolve_placement` and `manifest.choice_options`
  (Task 1); the `_entry` and `_params` helpers from Task 3.
- Produces: nothing other tasks import.

- [ ] **Step 1: Write the failing tests**

Append to `archplus/tools/partslib/tests/test_library_content.py`:

```python
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
    assert partslib_manifest.resolve_placement(data, params)["host"] == "wall"


def test_television_size_drives_the_panel_dimensions():
    merged = _params("television")
    assert merged["Width"] is None
    assert merged["Height"] is None


def test_curtain_folds_are_derived():
    assert _params("curtain")["FoldCount"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uvx --with pytest pytest archplus/tools/partslib/tests/test_library_content.py -q`
Expected: FAIL with `KeyError: 'ScreenSize'`.

- [ ] **Step 3: Edit the two manifests**

`television/part.json` — delete `variants`, replace the `Mounted` integer with
a `Mounting` choice carrying the placement overrides, and derive `Width` and
`Height` from a new `ScreenSize` in inches (`Integer`, because `Length` is
mm-only):

```json
  "params": {
    "ScreenSize": { "type": "Integer", "default": 55, "ui": "primary",
                    "label": "Size (in)" },
    "Mounting": {
      "type": "Choice", "default": "stand", "ui": "primary",
      "options": {
        "stand": { "label": "On stand",
                   "placement": { "host": "floor", "offset": 0 } },
        "wall": { "label": "Wall-mounted",
                  "placement": { "host": "wall", "offset": 1100 } }
      }
    },
    "Width": { "type": "Length", "default": "auto" },
    "Height": { "type": "Length", "default": "auto" },
    "PanelThickness": { "type": "Length", "default": 60 },
    "BezelWidth": { "type": "Length", "default": 18 },
    "StandHeight": { "type": "Length", "default": 90 }
  },
  "placement": { "host": "floor", "offset": 0 },
```

`curtain/part.json`:

```json
  "params": {
    "Width": { "type": "Length", "default": 1600, "ui": "primary" },
    "Height": { "type": "Length", "default": 2200, "ui": "primary" },
    "Fullness": { "type": "Length", "default": 110 },
    "RailDiameter": { "type": "Length", "default": 28 },
    "HeaderHeight": { "type": "Length", "default": 60 },
    "FoldCount": { "type": "Integer", "default": "auto", "label": "Folds" }
  },
```

- [ ] **Step 4: Update the two builders**

`television/builder.py` — replace the `width`, `height`, `bezel` and `mounted`
lines with:

```python
    bezel = float(params.get("BezelWidth", 18))
    screen_size = max(int(params.get("ScreenSize", 55)), 1)
    # A screen is sold by its diagonal in inches at 16:9, so the panel's
    # outside dimensions are that diagonal split into sides plus a bezel on
    # each edge. 55 gives 1254 x 721, 65 gives 1475 x 845.
    diagonal = screen_size * 25.4
    width = params.get("Width")
    if width is None:
        width = diagonal * 16.0 / 18.357560 + 2.0 * bezel
    width = float(width)
    height = params.get("Height")
    if height is None:
        height = diagonal * 9.0 / 18.357560 + 2.0 * bezel
    height = float(height)
    mounted = 1 if params.get("Mounting") == "wall" else 0
```

taking care that `bezel` ends up defined exactly once. Update the docstring's
params line to:

```
    Params: ScreenSize (diagonal inches), Mounting ("stand" or "wall"),
    Width, Height, PanelThickness, BezelWidth, StandHeight (mm). Width and
    Height are derived from ScreenSize unless pinned.
```

`curtain/builder.py` — replace its `fold_count` line with:

```python
    fold_count = params.get("FoldCount")
    if fold_count is None:
        # One fold roughly every 133mm of rail: 1600 gives 12, 2400 gives 18.
        fold_count = int(width // 133)
    fold_count = max(int(fold_count), 2)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uvx --with pytest pytest archplus/tools/partslib/tests/test_library_content.py -q`
Expected: PASS.

- [ ] **Step 6: Run the whole suite**

Run: `uvx --with pytest pytest archplus -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add archplus/tools/partslib/library/basic archplus/tools/partslib/tests/test_library_content.py
git commit -m "Give the television a size and a mounting choice; derive curtain folds"
```

---

### Task 6: The remaining 19 parts — `ui` marks and the last variant lists

Eight parts still carry size-only variant lists; eleven never had any and need
only `ui` marks and key reordering. No builder changes in this task.

This closes the second diagnostic symptom: `shower-screen`'s "Bath screen" was
a size (800 × 1400), not a type, so the bath option had no size range at all.
Deleting the list makes every width reachable at every height.

**Files:**
- Modify: `archplus/tools/partslib/library/basic/<part>/part.json` for the 19 parts in the table below
- Test: `archplus/tools/partslib/tests/test_library_content.py`

**Interfaces:**
- Consumes: `manifest.primary_params` (Task 1); the `_entry` helper from Task 3.
- Produces: nothing other tasks import.

- [ ] **Step 1: Write the failing tests**

Append to `archplus/tools/partslib/tests/test_library_content.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uvx --with pytest pytest archplus/tools/partslib/tests/test_library_content.py -q`
Expected: FAIL with `shower-screen still declares variants`.

- [ ] **Step 3: Delete the eight remaining variant lists**

Delete the `"variants"` block from `shower-screen`, `mirror`, `coffee-table`,
`nightstand`, `side-table`, `desk`, `bathtub` and `shower-base`. Keep the
part-level defaults each already declares; they are the defaults the panel
opens with.

- [ ] **Step 4: Mark primaries on all 19 parts**

Add `"ui": "primary"` to these params, reordering each `params` block so the
primaries come first in the order listed:

| part | mark `ui: "primary"` on |
|---|---|
| shower-screen | Width, Height |
| mirror | Width, Height |
| coffee-table | Width, Depth, Height |
| nightstand | Width, Depth, Height |
| side-table | Width, Depth, Height |
| desk | Width, Depth, Height |
| bathtub | Width, Depth, Height |
| shower-base | Width, Depth |
| armchair | Width, Depth, SeatHeight |
| basic-chair | Width, Depth, SeatHeight |
| corner-base-cabinet | Width, Depth, Height |
| corner-wall-cabinet | Width, Depth, Height |
| floor-lamp | Height, ShadeBottomDiameter, BaseDiameter |
| king-bed | Width, Length, BaseHeight |
| oven-cabinet | Width, Depth, Height |
| single-bed | Width, Length, BaseHeight |
| toilet | BowlWidth, BowlDepth, BowlHeight |
| toilet-roll-holder | PlateWidth, PlateHeight, ArmLength |
| towel-hook | PlateWidth, PlateHeight, Projection |

If a listed param does not exist in a manifest, mark the nearest equivalent
that does and say so in the commit message. Do not invent a param, and do not
add one no builder reads.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uvx --with pytest pytest archplus/tools/partslib/tests/test_library_content.py -q`
Expected: PASS.

- [ ] **Step 6: Run the whole suite**

Run: `uvx --with pytest pytest archplus -q`
Expected: PASS. `variants` is now unused by every shipped part but still
supported by the code; Task 7 removes the support.

- [ ] **Step 7: Commit**

```bash
git add archplus/tools/partslib/library/basic archplus/tools/partslib/tests/test_library_content.py
git commit -m "Mark primary params on every part and delete the last variant lists"
```

---

### Task 7: Delete `variants` from the schema, the resolver and the index

Only safe now that Task 6 left no shipped manifest declaring it.

**Files:**
- Modify: `archplus/tools/partslib/manifest.py`
- Modify: `archplus/tools/partslib/index.py`
- Test: `archplus/tools/partslib/tests/test_partslib_manifest.py`
- Test: `archplus/tools/partslib/tests/test_partslib_index.py`

**Interfaces:**
- Consumes: Task 1's functions.
- Produces: `index.scan()` entries carry `"params"` and no `"variants"`;
  `index.CACHE_VERSION == 2`. `manifest.variant_labels`,
  `manifest.resolve_variant` and `manifest.DEFAULT_VARIANT_LABEL` cease to
  exist.

- [ ] **Step 1: Delete the obsolete tests**

In `archplus/tools/partslib/tests/test_library_content.py`, delete
`test_every_part_variant_labels_are_non_empty_and_unique` (line 70) — it
asserts on `entry["variants"]`, which Step 5 removes.

Then, in the manifest tests:

In `archplus/tools/partslib/tests/test_partslib_manifest.py`, delete every test
that calls `pm.resolve_variant`, `pm.variant_labels` or
`pm.DEFAULT_VARIANT_LABEL`, plus the `_part_with_variants()` helper and the
`_resolved()` helper built on it. Rewrite the two `param_specs` tests that used
`_resolved()` to pass a plain manifest:

```python
def test_param_specs_returns_the_declared_params_block():
    assert pm.param_specs(_part_with_ui())["Width"] == {
        "type": "Length", "default": 600, "ui": "primary"}


def test_param_specs_is_empty_when_params_block_absent():
    assert pm.param_specs({"schema": 1, "name": "X"}) == {}
```

- [ ] **Step 2: Write the failing tests**

Append to `archplus/tools/partslib/tests/test_partslib_manifest.py`:

```python
def test_a_manifest_declaring_variants_is_rejected():
    data = _part_with_ui()
    data["variants"] = [{"label": "800 mm"}]
    errors, _warnings = pm.validate_manifest(data, {})
    assert any("variants" in error for error in errors)


def test_variants_is_an_error_not_an_ignored_unknown_field():
    data = _part_with_ui()
    data["variants"] = []
    errors, warnings = pm.validate_manifest(data, {})
    assert any("variants" in error for error in errors)
    assert not any("variants" in warning for warning in warnings)
```

In `archplus/tools/partslib/tests/test_partslib_index.py`, delete any test
asserting on an entry's `"variants"` key, then read the file's own
library-building fixture helper and append, adapting the helper's name and
arguments to what it actually is:

```python
def test_entries_carry_the_params_block_and_no_variants(tmp_path):
    library = _library(tmp_path, params={
        "Width": {"type": "Length", "default": 600, "ui": "primary"}})
    entry = pi.scan(str(library))["entries"][0]
    assert entry["params"] == {
        "Width": {"type": "Length", "default": 600, "ui": "primary"}}
    assert "variants" not in entry


def test_a_version_1_cache_is_rejected(tmp_path):
    path = tmp_path / "index.json"
    path.write_text(json.dumps({"version": 1, "facets": {}, "entries": []}),
                    encoding="utf8")
    assert pi.load_cache(str(path)) is None
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uvx --with pytest pytest archplus/tools/partslib/tests -q`
Expected: FAIL — `assert any("variants" in error ...)` is False, because
`variants` is still a known field.

- [ ] **Step 4: Remove variants from `manifest.py`**

Delete `DEFAULT_VARIANT_LABEL`, `variant_labels` and `resolve_variant`
entirely, and remove `"variants"` from `KNOWN_FIELDS`. In the module docstring,
change "facet resolution and variant merging" to "facet resolution and param
merging".

Add the rejection to `validate_manifest`, immediately after the
`_validate_part_facets` call:

```python
    if "variants" in data:
        # Not merely unsupported: a manifest still carrying a variant list is
        # one whose sizes and configuration have not been split into params,
        # so placing it would silently use the wrong defaults. A hard error
        # keeps it out of the index instead of quietly ignoring it.
        errors.append(
            "'variants' was removed; declare params with \"ui\", \"label\", "
            "\"default\": \"auto\" and \"options\" instead")
```

- [ ] **Step 5: Update `index.py`**

Change `CACHE_VERSION` to `2`. In `scan()`, replace

```python
            "variants": pm.variant_labels(data),
```

with

```python
            "params": data.get("params", {}),
```

and append to the `save_cache` docstring paragraph that explains why
`facetsMtime` was added without a version bump:

```
    CACHE_VERSION was bumped to 2 when entries stopped carrying "variants"
    and started carrying "params". Unlike the facetsMtime addition, a stale
    v1 cache would hand the panel a key that no longer exists, so it must be
    refused outright rather than healed.
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uvx --with pytest pytest archplus/tools/partslib/tests -q`
Expected: PASS.

- [ ] **Step 7: Run the whole suite**

Run: `uvx --with pytest pytest archplus -q`
Expected: PASS. If any test fails on `entry["variants"]` from a GUI-adjacent
module, leave it failing, note it in the commit message, and let Task 9 fix it.

- [ ] **Step 8: Commit**

```bash
git add archplus/tools/partslib/manifest.py archplus/tools/partslib/index.py archplus/tools/partslib/tests
git commit -m "Delete variants from the schema, the resolver and the index"
```

---

### Task 8: `object.py` — Choice properties and auto/pinned state

**Files:**
- Modify: `archplus/tools/partslib/object.py`
- Test: none headless. This module imports FreeCAD at module scope and cannot
  be imported under plain pytest; verification is the manual checklist in
  Step 7.

**Interfaces:**
- Consumes: `manifest.param_specs`, `manifest.choice_options`,
  `manifest.merge_params`, `manifest.AUTO` (Task 1);
  `geometry.build_shape(manifest, part_dir, overrides)` and
  `geometry.measure(shape)` (Task 2).
- Produces: `makePart(entry, facets, placement=None)` — the `variant` argument
  is gone; `PROP_AUTO_PARAMS = "AutoParams"`.

- [ ] **Step 1: Remove the variant property**

Delete `PROP_VARIANT` and every use of it:

- in `setPartProperties`, the `addProperty("App::PropertyEnumeration", PROP_VARIANT, ...)` block;
- in `_resolveCurrent`, the `resolve_variant(...)` call — it returns
  `partslib_manifest.load_manifest(entry["path"])` directly now;
- in `execute`, the `resolve_variant(...)` call — pass the loaded manifest
  straight to `build_shape`;
- in `onChanged`, the whole `if prop == PROP_VARIANT:` branch;
- in `makePart`, the `variant` parameter, the `labels` lookup and both
  `setattr(obj, PROP_VARIANT, ...)` calls;
- in `reloadFromLibrary`, the entire label-reconciliation block and both
  `setattr(obj, PROP_VARIANT, ...)` calls.

In `setPartProperties`, hide a legacy property rather than removing it:

```python
        # A document written before params replaced variants still carries a
        # Variant enumeration. Removing a document property is destructive,
        # so it stays - but it must stop looking like a live control.
        if "Variant" in obj.PropertiesList:
            obj.setEditorMode("Variant", 2)  # hidden
```

- [ ] **Step 2: Add `Choice` to the property type table**

Replace the `_PARAM_PROPERTY_TYPES` comment paragraph explaining why `Enum` is
absent — no longer true — with:

```python
# "Choice" maps to an enumeration whose allowed values come from the param's
# own `options` map. That is why it is expressible now and was not before:
# the schema previously had no way to declare them.
```

and add the entry to the dict:

```python
    "Choice": "App::PropertyEnumeration",
```

- [ ] **Step 3: Seed enumerations and skip `"auto"` seeds**

In `_declareParamProperties`, inside the seeding loop, replace the
`if is_new or reseed: setattr(obj, name, spec.get("default"))` block with:

```python
                options = partslib_manifest.choice_options(spec)
                if options:
                    # An enumeration needs its allowed values before its
                    # value, or the assignment below has nothing to match.
                    setattr(obj, name,
                            [(opt or {}).get("label") or value
                             for value, opt in options.items()])
                if is_new or reseed:
                    default = spec.get("default")
                    if options:
                        default = ((options.get(default) or {}).get("label")
                                   or default)
                    if default == partslib_manifest.AUTO:
                        # Nothing meaningful to seed: execute() writes the
                        # builder's answer in once the shape exists.
                        default = None
                    if default is not None:
                        setattr(obj, name, default)
```

- [ ] **Step 4: Read a Choice property back as its stable value**

Add at module level, beside the other helpers:

```python
def _paramValue(obj, name, spec):
    """One param property's value, as a builder expects it.

    A Choice property holds the option LABEL, because that is what the user
    reads in the property editor. Map it back to the stable value the
    manifest and the builder use - by label first, then by position - so
    renaming a label does not orphan an already-saved object."""
    value = getattr(obj, name)
    options = partslib_manifest.choice_options(spec)
    if not options:
        return value
    for option_value, option in options.items():
        if ((option or {}).get("label") or option_value) == value:
            return option_value
    try:
        labels = list(obj.getEnumerationsOfProperty(name))
        return list(options)[labels.index(value)]
    except Exception:
        return list(options)[0]
```

- [ ] **Step 5: Add `AutoParams` and the pinning rule**

Beside the other property-name constants:

```python
PROP_AUTO_PARAMS = "AutoParams"
```

In `setPartProperties`, right after `PROP_PART_ID` is declared:

```python
        if PROP_AUTO_PARAMS not in obj.PropertiesList:
            obj.addProperty("App::PropertyStringList", PROP_AUTO_PARAMS,
                            _PARAM_GROUP,
                            "Params still derived by the builder",
                            locked=True)
        obj.setEditorMode(PROP_AUTO_PARAMS, 2)  # hidden
```

In `_declareParamProperties`, inside the `self._reseeding` block and after the
seeding loop:

```python
            if reseed:
                setattr(obj, PROP_AUTO_PARAMS,
                        [name for name, spec in specs.items()
                         if spec.get("default") == partslib_manifest.AUTO])
```

In `execute`, replace the `overrides = {...}` comprehension and the
`build_shape` call with:

```python
            specs = partslib_manifest.param_specs(manifest)
            auto = set(getattr(obj, PROP_AUTO_PARAMS, ()) or ())
            overrides = {}
            for name in getattr(self, "_paramNames", ()):
                if name in obj.PropertiesList and name not in auto:
                    overrides[name] = _paramValue(obj, name, specs.get(name))
            shape = partslib_geometry.build_shape(
                manifest, entry["dir"], overrides)
```

and after `obj.Shape = shape` and the placement restore, write back what the
shape reports for derived dimensions:

```python
        # An "auto" param has no seeded value, so the editor would otherwise
        # show a meaningless zero. The built shape is the only thing that
        # knows what the builder actually derived, so its measurements are
        # what get written back - which covers Width/Depth/Height, the
        # dimensions users read. Assigning these fires onChanged() for each,
        # the same reentrancy _declareParamProperties() guards against, and
        # guarded the same way.
        if auto:
            measured = partslib_geometry.measure(shape)
            self._reseeding = True
            try:
                for name in auto:
                    if name in measured and name in obj.PropertiesList:
                        setattr(obj, name, measured[name])
            finally:
                self._reseeding = False
```

In `onChanged`, pin a derived param the moment it is edited:

```python
        elif prop in getattr(self, "_paramNames", ()):
            if ("Restore" not in obj.State
                    and not getattr(self, "_reseeding", False)):
                auto = list(getattr(obj, PROP_AUTO_PARAMS, ()) or ())
                if prop in auto:
                    # Editing a derived field is what pins it. "Reload from
                    # library" is the only way back to derived.
                    auto.remove(prop)
                    setattr(obj, PROP_AUTO_PARAMS, auto)
                self.execute(obj)
```

- [ ] **Step 6: Simplify `makePart` and `reloadFromLibrary`**

`makePart` loses its `variant` argument and its label juggling:

```python
def makePart(entry, facets, placement=None):
    """Create one library part object in the active document."""
    doc = FreeCAD.ActiveDocument
    if doc is None:
        raise RuntimeError("no active document")

    manifest = partslib_manifest.load_manifest(entry["path"])

    obj = doc.addObject("Part::FeaturePython", "LibraryPart")
    _LibraryPart(obj)
    if FreeCAD.GuiUp:
        _ViewProviderLibraryPart(obj.ViewObject)

    obj.Label = manifest.get("name", entry["id"])
    setattr(obj, PROP_PART_ID, entry["id"])
    obj.Proxy.setPartProperties(obj, manifest, reseed=True)
    _applyMetadata(obj, manifest, facets)

    if placement is not None:
        obj.Placement = placement

    obj.Proxy.execute(obj)
    return obj
```

`reloadFromLibrary` keeps its structure and error handling but drops the label
reconciliation entirely:

```python
    entry, facets = found
    try:
        manifest = partslib_manifest.load_manifest(entry["path"])
        # Reload means "take the library's current truth", so it discards
        # hand-edited Parameter values and returns every derived param to
        # derived. reseed=True is what does both.
        obj.Proxy.setPartProperties(obj, manifest, reseed=True)
        _applyMetadata(obj, manifest, facets)
    except Exception as exc:
        FreeCAD.Console.PrintError(
            "ArchPlus: cannot reload %s: %s\n" % (obj.Label, exc))
        return False
```

- [ ] **Step 7: Verify by hand in FreeCAD**

There is no headless test for this module. Open FreeCAD, run the Parts Library
tool, and confirm each of these, recording the result in the commit message:

1. Placing a base cabinet gives a `Parameters` group with `Width`, `Depth`,
   `Height`, `WorktopThickness`, `KickHeight`, `Doors` — and no `Variant`.
2. Setting `Width` to 800 rebuilds it with two doors.
3. Setting `Doors` to 3 rebuilds with three doors, and that value survives a
   further change to `Width`.
4. Right-click → "Reload from library" returns `Doors` to derived.
5. Placing a television shows `Mounting` as a two-value dropdown reading
   "On stand" / "Wall-mounted".
6. A document saved before this change still shows its geometry on open, and
   its `Variant` property is hidden.

- [ ] **Step 8: Commit**

```bash
git add archplus/tools/partslib/object.py
git commit -m "Replace the Variant property with Choice properties and AutoParams"
```

---

### Task 9: `paramform.py` and the browser panel

**Files:**
- Create: `archplus/tools/partslib/paramform.py`
- Modify: `archplus/tools/partslib/gui.py`
- Modify: `archplus/tools/partslib/thumbs.py`
- Test: none headless (conftest fakes PySide); verification is Step 6.

**Interfaces:**
- Consumes: `manifest.param_specs`, `primary_params`, `choice_options`,
  `merge_params`, `resolve_placement`, `AUTO` (Task 1);
  `object.makePart(entry, facets, placement=None)` (Task 8).
- Produces: `paramform.ParamForm(parent, tokens)` with `setSpecs(specs, primary)`,
  `values() -> dict`, `reset()`, and a `changed` signal.

- [ ] **Step 1: Create `archplus/tools/partslib/paramform.py`**

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# PartsLib param form - the browser panel's editor for one part's params.
#
# Split out of gui.py, which is already long. Every DECISION this makes -
# which params are primary, in what order, which are derived - comes from
# manifest.py, which is FreeCAD-free and unit-tested. What is left here is
# widget construction and value read-back, which the headless suite cannot
# exercise because conftest fakes PySide.

from PySide import QtCore, QtGui

from . import manifest as partslib_manifest


class ParamForm(QtGui.QWidget):
    """Primary params in a row, the rest behind a collapsed expander."""

    changed = QtCore.Signal()

    def __init__(self, parent=None, tokens=None):
        QtGui.QWidget.__init__(self, parent)
        self._tokens = tokens or {}
        self._specs = {}
        self._widgets = {}
        self._auto = set()
        # Remembered for the session, not per part: a user who opens the
        # expander is telling us they work in detail, and re-collapsing it on
        # every selection would fight them.
        self._expanded = False

        layout = QtGui.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._primaryRow = QtGui.QGridLayout()
        layout.addLayout(self._primaryRow)

        controls = QtGui.QHBoxLayout()
        self._toggle = QtGui.QToolButton()
        self._toggle.setAutoRaise(True)
        self._toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self._toggle.setArrowType(QtCore.Qt.RightArrow)
        self._toggle.clicked.connect(self._onToggle)
        controls.addWidget(self._toggle)
        controls.addStretch(1)
        self._resetButton = QtGui.QPushButton("Reset")
        self._resetButton.setFlat(True)
        self._resetButton.clicked.connect(self.reset)
        controls.addWidget(self._resetButton)
        layout.addLayout(controls)

        self._more = QtGui.QWidget()
        self._moreRow = QtGui.QGridLayout(self._more)
        self._moreRow.setContentsMargins(0, 0, 0, 0)
        self._more.setVisible(False)
        layout.addWidget(self._more)

    def setSpecs(self, specs, primary):
        """Rebuild for one part. `primary` is manifest.primary_params()."""
        self._specs = dict(specs or {})
        self._widgets = {}
        self._auto = set(
            name for name, spec in self._specs.items()
            if (spec or {}).get("default") == partslib_manifest.AUTO)
        _clearGrid(self._primaryRow)
        _clearGrid(self._moreRow)

        primary = [name for name in (primary or []) if name in self._specs]
        secondary = [name for name in self._specs if name not in primary]

        for column, name in enumerate(primary):
            self._addField(self._primaryRow, 0, column, name)
        for row, name in enumerate(secondary):
            self._addField(self._moreRow, row, 0, name)

        self._toggle.setVisible(bool(secondary))
        self._toggle.setText("More parameters (%d)" % len(secondary))
        self._more.setVisible(bool(secondary) and self._expanded)
        self._toggle.setArrowType(
            QtCore.Qt.DownArrow if self._expanded else QtCore.Qt.RightArrow)

    def values(self):
        """{name: value} for every PINNED field.

        A derived field is omitted rather than sent as its displayed value,
        because sending it would pin it - merge_params() treats any present
        override as the user's answer."""
        out = {}
        for name, widget in self._widgets.items():
            if name in self._auto:
                continue
            out[name] = _valueOf(widget, self._specs.get(name) or {})
        return out

    def reset(self):
        """Back to manifest defaults, which also restores derived fields."""
        self.setSpecs(self._specs,
                      partslib_manifest.primary_params(
                          {"params": self._specs}))
        self.changed.emit()

    def _addField(self, grid, row, column, name):
        spec = self._specs.get(name) or {}
        caption = QtGui.QLabel(spec.get("label") or name)
        widget = _widgetFor(spec)
        if name in self._auto:
            widget.setStyleSheet(
                "font-style: italic; color: %s;"
                % (self._tokens.get("text_dim", "#888888"),))
            widget.setToolTip("Derived from the other parameters. "
                              "Editing this pins it.")
        _connect(widget, name, self._onEdited)
        self._widgets[name] = widget
        grid.addWidget(caption, row, column * 2)
        grid.addWidget(widget, row, column * 2 + 1)

    def _onEdited(self, name):
        if name in self._auto:
            self._auto.discard(name)
            widget = self._widgets.get(name)
            if widget is not None:
                widget.setStyleSheet("")
                widget.setToolTip("")
        self.changed.emit()

    def _onToggle(self):
        self._expanded = not self._expanded
        self._more.setVisible(self._expanded)
        self._toggle.setArrowType(
            QtCore.Qt.DownArrow if self._expanded else QtCore.Qt.RightArrow)


def _widgetFor(spec):
    """One editor widget for a param spec, seeded from its default."""
    kind = spec.get("type")
    default = spec.get("default")
    if default == partslib_manifest.AUTO:
        default = None

    if kind == "Choice":
        widget = QtGui.QComboBox()
        options = partslib_manifest.choice_options(spec)
        for value, option in options.items():
            widget.addItem((option or {}).get("label") or value, value)
        if default is not None and default in options:
            widget.setCurrentIndex(list(options).index(default))
        return widget
    if kind == "Bool":
        widget = QtGui.QCheckBox()
        widget.setChecked(bool(default))
        return widget
    if kind == "String":
        widget = QtGui.QLineEdit()
        widget.setText(default or "")
        return widget
    if kind == "Integer":
        widget = QtGui.QSpinBox()
        widget.setRange(0, 9999)
        widget.setValue(int(default or 0))
        return widget

    widget = QtGui.QDoubleSpinBox()
    widget.setRange(0.0, 100000.0)
    widget.setDecimals(0)
    widget.setSuffix(" deg" if kind == "Angle" else " mm")
    widget.setValue(float(default or 0))
    return widget


def _connect(widget, name, slot):
    """Wire whichever change signal this widget class actually has."""
    for signal in ("valueChanged", "currentIndexChanged", "textEdited",
                   "toggled"):
        handler = getattr(widget, signal, None)
        if handler is not None:
            handler.connect(lambda *args: slot(name))
            return


def _valueOf(widget, spec):
    if spec.get("type") == "Choice":
        return widget.itemData(widget.currentIndex())
    for reader in ("value", "text", "isChecked"):
        method = getattr(widget, reader, None)
        if method is not None:
            return method()
    return None


def _clearGrid(grid):
    while grid.count():
        item = grid.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
```

- [ ] **Step 2: Delete the chip machinery from `gui.py`**

Delete `MAX_VARIANT_CHIPS`, `_setVariantChips`, `_currentVariantLabel` and
`_onVariantChanged` (currently `gui.py:971-1057`), the `variantRow` /
`variantGroup` / `variantCombo` construction in the detail pane
(`gui.py:391-399`), `_sanitizeVariantLabel` (`gui.py:239-246`), and the
`#VariantChip` / `#VariantCaption` / `#VariantCombo` rules in the stylesheet
(`gui.py:144-170`).

- [ ] **Step 3: Add the form and the debounce**

In the detail pane, where the `variantRow` block was:

```python
        from . import paramform as partslib_paramform

        self.paramForm = partslib_paramform.ParamForm(self, self._tokens)
        self.paramForm.changed.connect(self._onParamsChanged)
        layout.addWidget(self.paramForm)

        # Rebuilding is not cheap and every keystroke in a spin box would
        # queue one, so a burst of edits coalesces into a single build.
        self._paramTimer = QtCore.QTimer(self)
        self._paramTimer.setSingleShot(True)
        self._paramTimer.setInterval(250)
        self._paramTimer.timeout.connect(self._refreshPreview)
```

and add the slot beside the other handlers:

```python
    def _onParamsChanged(self):
        self._paramTimer.start()
```

Replace the two `self._setVariantChips(...)` calls in the selection handler.
The empty-selection one (`gui.py:961`) becomes:

```python
            self.paramForm.setSpecs({}, [])
```

and the populated one (`gui.py:968`) becomes:

```python
        shaped = {"params": entry.get("params") or {}}
        self.paramForm.setSpecs(
            partslib_manifest.param_specs(shaped),
            partslib_manifest.primary_params(shaped))
```

- [ ] **Step 4: Replace `_resolvedSelection`**

```python
    def _selection(self):
        """(entry, manifest, overrides) for the current selection, or None."""
        from . import manifest as partslib_manifest

        entry = self.currentEntry()
        if entry is None:
            return None
        manifest = partslib_manifest.load_manifest(entry["path"])
        return entry, manifest, self.paramForm.values()
```

Update every caller — `_refreshPreview`, the thumbnail render and the place
handler — to unpack three values and pass `overrides` through to
`partslib_geometry.build_shape(manifest, entry["dir"], overrides)`.

In the place handler (`gui.py:1258-1266`), replace

```python
        host = partslib_placement.host_of(resolved)
        offset = partslib_placement.offset_of(resolved)
```

with

```python
        # A Choice option can move the part between hosts - a television on a
        # stand is floor-hosted, the same television on a bracket is not.
        params = partslib_manifest.merge_params(manifest, overrides)
        effective = {"placement": partslib_manifest.resolve_placement(
            manifest, params)}
        host = partslib_placement.host_of(effective)
        offset = partslib_placement.offset_of(effective)
```

Delete the `variant = self._currentVariantLabel() or ...` line
(`gui.py:1267`) and drop `variant=variant` from the `makePart` call
(`gui.py:1344`).

- [ ] **Step 5: Re-key the preview cache and the grid card**

Replace `_renderVariantPreview`'s cache filename with a hash of the merged
params, renaming the method to `_renderParamPreview` and updating its one
caller:

```python
    def _paramCacheKey(self, manifest, overrides):
        """A stable short filename fragment for one set of param values."""
        import hashlib

        from . import manifest as partslib_manifest

        params = partslib_manifest.merge_params(manifest, overrides)
        blob = repr(sorted((str(k), str(v)) for k, v in params.items()))
        return hashlib.sha1(blob.encode("utf8")).hexdigest()[:12]
```

`thumbs.py` keys nothing by variant — its only two mentions are prose, at
lines 22 and 215, both reading "the detail pane's per-variant preview".
Change both to "the detail pane's per-parameter preview".

In the grid card (`gui.py:839-850`), replace the variants line with the primary
param labels, keeping the block's existing font, alignment and dim colour and
renaming the local from `variants` to `adjustable`:

```python
        shaped = {"params": entry.get("params") or {}}
        specs = partslib_manifest.param_specs(shaped)
        adjustable = QtGui.QLabel(" | ".join(
            (specs.get(name) or {}).get("label") or name
            for name in partslib_manifest.primary_params(shaped)))
```

- [ ] **Step 6: Verify by hand in FreeCAD**

1. Selecting a base cabinet shows `Width`, `Depth`, `Height` as editable
   fields with `More parameters (3)` collapsed beneath them.
2. Typing 800 into `Width` rebuilds the preview once, not per keystroke, and
   the W/D/H readout updates.
3. Expanding shows `WorktopThickness`, `KickHeight` and a dimmed italic
   `Doors`; editing `Doors` un-dims it.
4. `Reset` restores every field and re-dims `Doors`.
5. A television shows `Size (in)` and a `Mounting` dropdown; choosing
   "Wall-mounted" makes "Place in 3D view" host it on a wall.
6. Grid cards read `Width | Depth | Height` under the part name.

- [ ] **Step 7: Run the whole suite**

Run: `uvx --with pytest pytest archplus -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add archplus/tools/partslib/paramform.py archplus/tools/partslib/gui.py archplus/tools/partslib/thumbs.py
git commit -m "Replace the variant chips with a param form in the browser panel"
```

---

### Task 10: Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/PARTS-LIBRARY-VERIFICATION.md`
- Modify: `docs/superpowers/specs/2026-08-15-parts-library-design.md`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Update the manifest reference in `README.md`**

Find the `part.json` field table and worked example (search for `"variants"`).
Remove the `variants` row and any variant example block, and add these rows:

| key | meaning |
|---|---|
| `params.<name>.ui` | `"primary"` shows the param in the browser panel. Absent means it sits behind "More parameters". |
| `params.<name>.label` | Display name. The key itself stays the builder argument and the property name. |
| `params.<name>.default` | A number, a string, or `"auto"` — meaning the builder derives it. |
| `params.<name>.options` | `Choice` only: ordered value to `{label, placement?}`. A selected option's `placement` merges per key over the part's. |

with this worked example:

```json
"params": {
  "Width":     { "type": "Length",  "default": 600,    "ui": "primary" },
  "DoorCount": { "type": "Integer", "default": "auto", "label": "Doors" },
  "Mounting":  { "type": "Choice",  "default": "stand", "ui": "primary",
                 "options": {
                   "stand": { "label": "On stand" },
                   "wall":  { "label": "Wall-mounted",
                              "placement": { "host": "wall", "offset": 1100 } }
                 } }
}
```

- [ ] **Step 1b: Fix the two genuinely stale prose references**

Independent of the docs work, two code comments still describe the deleted
mechanism and are the only stale ones left:

- `archplus/tools/partslib/geometry.py` — the shape-cache docstring ends
  "...Parameter or switching a variant." Nothing can switch a variant now;
  make it "...editing a Parameter."
- `archplus/tools/partslib/library/basic/television/builder.py` — the docstring
  says "the two variants measure differently on purpose". It means the two
  mountings: a wall-mounted set has no floor footprint to schedule. Reword to
  "the two mountings".

- [ ] **Step 2: Document the `None` contract in README §2b**

After the paragraph ending "so the headless test suite can import the module
without FreeCAD present.", add this text and code block:

A param declared with `"default": "auto"` arrives as `None`. That is the
instruction to derive it — "an 800mm cabinet has two doors" is design
knowledge, and it belongs here rather than enumerated in the manifest.
Because the key is always present, `params.get(name, fallback)` no longer
protects you; test for `None` explicitly:

    door_count = params.get("DoorCount")
    if door_count is None:
        door_count = 1 if width < 700 else 2
    door_count = max(int(door_count), 0)

Render that snippet as a fenced `python` block in the README itself; it is
shown indented here only to keep this plan's own fences balanced.

- [ ] **Step 3: Rewrite the variant steps in `docs/PARTS-LIBRARY-VERIFICATION.md`**

Run `grep -n variant docs/PARTS-LIBRARY-VERIFICATION.md` and replace each
manual step that switches variants with the equivalent param edit. The six
checks from Task 8 Step 7 and the six from Task 9 Step 6 are the replacement
content — fold them in rather than inventing new ones.

- [ ] **Step 4: Amend the superseded spec**

At the top of `docs/superpowers/specs/2026-08-15-parts-library-design.md`,
directly under the title:

```markdown
> **Amended 2026-08-17.** §5.3 (Variants) and the `variants` row of the
> manifest table no longer describe the system: `variants` was removed and
> replaced by per-part declared parameters. See
> `2026-08-17-part-parameters-design.md`.
```

- [ ] **Step 5: Verify no stale references remain**

The naive check — grep for `variant` and expect nothing — is WRONG, and chasing
it would delete load-bearing code. Several references must survive:

| survives in | why it must |
|---|---|
| `manifest.py` | the rejection error text a stale manifest gets, the `field != "variants"` exclusion that stops double-reporting, and a docstring recording what a variant's placement override used to do |
| `tests/test_partslib_manifest.py`, `tests/test_partslib_index.py`, `tests/test_library_content.py` | the tests that assert `variants` is now rejected and absent — the guards for this whole change |
| `object.py` | the legacy-`Variant` property hide, which must keep working for old documents |
| `index.py` | the `CACHE_VERSION` 2 rationale |
| `docs/superpowers/plans/*`, `docs/superpowers/specs/*` | historical planning records |
| `archplus/tools/stairs/object.py` | a different tool, unrelated and pre-existing |

Note also that `grep variant` matches `invariant`, so any check must exclude it.

Run this instead, which lists only files where a reference should NOT survive:

```bash
grep -rn "variant" archplus README.md docs/PARTS-LIBRARY-VERIFICATION.md   | grep -vi invariant   | grep -v "/tests/\|manifest.py\|index.py\|object.py\|docs/superpowers/"
```

Expected: no hits. Fix what it finds; touch nothing in the table above.

- [ ] **Step 6: Run the whole suite**

Run: `uvx --with pytest pytest archplus -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add README.md docs
git commit -m "Document params, auto defaults and Choice options; retire the variant docs"
```
