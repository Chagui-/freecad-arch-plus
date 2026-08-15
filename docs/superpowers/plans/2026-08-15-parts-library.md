# Parts Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fourth ArchPlus tool — a dockable, searchable library of reusable BIM parts that inserts a single editable object per part.

**Architecture:** A part is a folder with a JSON manifest plus optional shape assets. A pure-Python core (manifest validation, faceted index, search) is testable headlessly; a FreeCAD layer (builders, thumbnails, the scripted object, placement, the dock panel) sits on top. Every geometry source becomes a bare `Part.Shape`, never a `DocumentObject`, so insertion produces exactly one object in the tree.

**Tech Stack:** Python 3, FreeCAD 1.1 (Arch/BIM modules, `Part`, `Draft`, `pivy.coin`, `pivy.quarter`), PySide (Qt6 shim), pytest via `uv`.

**Spec:** `docs/superpowers/specs/2026-08-15-parts-library-design.md`

## Global Constraints

- **License header:** every new `.py` file starts with `# SPDX-License-Identifier: LGPL-2.1-or-later` followed by a `#`-comment block explaining the module's purpose, matching `stairsplus_gui.py:1-8`.
- **FreeCAD version:** 1.1 only. BIM/Arch modules must be available.
- **Qt import style:** `from PySide import QtGui, QtCore` — never `PySide2` or `PySide6` directly. Matches `windowsplus_gui.py:21`.
- **Sibling imports:** modules add their own directory to `sys.path` before importing siblings, matching `windowsplus_gui.py:24-26`.
- **`partslib_manifest.py` and `partslib_index.py` MUST NOT import FreeCAD, FreeCADGui, Part, Draft, or PySide.** This is what makes them testable. A test asserts it.
- **Builder resolution:** builders resolve only from the `partslib_builders` package. A manifest never supplies a file path or import path.
- **`id` is immutable.** Never rename a part id once shipped — it is written into user documents.
- **Units:** millimetres throughout, matching the existing tools.
- **Schema version:** `SCHEMA_VERSION = 1`.
- **Default IFC type:** `"Building Element Proxy"`.
- **IfcProperties encoding:** `"Pset;;IfcType;;Value"` (`ArchComponent.py:2482`).
- **Test command:** `uv run --with pytest --no-project pytest tests/ -q` from the repo root. Neither system Python has pytest and `ensurepip` is unavailable, so plain venvs fail — use `uv`.
- **Branch:** `parts-library`. Commit after every task.

---

### Task 1: Spike — verify QuarterWidget and offscreen rendering

**Purpose:** Spec §12 risk 1. `pivy.quarter.QuarterWidget` is the riskiest widget in the plan and FreeCAD's own code imports it under `PySide2` (`OfflineRenderingUtils.py:485`) while ArchPlus uses the `PySide` shim. If it will not embed, the detail pane falls back to a static PNG and Task 14 changes shape. Find out before building anything.

**This is a throwaway spike.** The macro is not committed. The deliverable is a recorded answer.

**Files:**
- Create (throwaway, not committed): `/tmp/partslib_spike.FCMacro`

- [ ] **Step 1: Write the spike macro**

Create `/tmp/partslib_spike.FCMacro`:

```python
# Throwaway spike - do not commit.
# Q1: does QuarterWidget embed in a dock under FreeCAD 1.1's PySide shim?
# Q2: does SoOffscreenRenderer produce a PNG from a bare Part.Shape?
import os
import FreeCAD, FreeCADGui, Part
from PySide import QtGui
from pivy import coin

shape = Part.makeBox(360, 540, 400)

# --- Q2: offscreen render from a bare shape, no document, no 3D view ---
try:
    buf = shape.writeInventor(2, 0.01)
    inp = coin.SoInput()
    inp.setBuffer(buf)
    node = coin.SoDB.readAll(inp)
    root = coin.SoSeparator()
    root.addChild(coin.SoDirectionalLight())
    cam = coin.SoPerspectiveCamera()
    root.addChild(cam)
    root.addChild(node)
    region = coin.SbViewportRegion(256, 256)
    cam.viewAll(root, region)
    renderer = coin.SoOffscreenRenderer(region)
    renderer.setBackgroundColor(coin.SbColor(1.0, 1.0, 1.0))
    root.ref()
    ok = renderer.render(root)
    root.unref()
    out = os.path.join(os.path.expanduser("~"), "partslib_spike.png")
    if ok:
        renderer.writeToFile(out, "PNG")
    FreeCAD.Console.PrintMessage("SPIKE offscreen: ok=%s -> %s\n" % (ok, out))
except Exception as exc:
    FreeCAD.Console.PrintError("SPIKE offscreen FAILED: %r\n" % (exc,))

# --- Q1: QuarterWidget inside a QDockWidget ---
try:
    from pivy import quarter
    dock = QtGui.QDockWidget("Spike")
    view = quarter.QuarterWidget()
    view.setSceneGraph(node)
    dock.setWidget(view)
    FreeCADGui.getMainWindow().addDockWidget(
        QtGui.Qt.RightDockWidgetArea if hasattr(QtGui, "Qt") else 2, dock)
    FreeCAD.Console.PrintMessage("SPIKE quarter: embedded OK\n")
except Exception as exc:
    FreeCAD.Console.PrintError("SPIKE quarter FAILED: %r\n" % (exc,))
```

- [ ] **Step 2: Run it in FreeCAD**

Open FreeCAD 1.1 → Macro → Macros… → point at `/tmp/partslib_spike.FCMacro` → Execute.
Read the Report view (View → Panels → Report view).

- [ ] **Step 3: Record both answers in the spec**

Append to `docs/superpowers/specs/2026-08-15-parts-library-design.md` under §12, replacing risk 1 and risk 2 text with the observed result. Use exactly one of these outcomes per question:

- `SPIKE quarter: embedded OK` → live 3D preview is viable; Task 14 builds it.
- `SPIKE quarter FAILED` → record the exception; Task 14 uses a scaled `QLabel` + `QPixmap` of the cached thumbnail instead, and the live-preview rows are dropped from the §8 panel sketch.
- `SPIKE offscreen: ok=True` → runtime thumbnail generation is viable (Task 9).
- `SPIKE offscreen: ok=False` or an exception → Task 9 becomes an authoring-time-only script; committed thumbnails become mandatory rather than merely preferred.

- [ ] **Step 4: Commit the spec update**

```bash
git add docs/superpowers/specs/2026-08-15-parts-library-design.md
git commit -m "docs: record QuarterWidget and offscreen render spike results"
```

---

### Task 2: Test harness and facet vocabulary

**Files:**
- Create: `tests/conftest.py`
- Create: `pytest.ini`
- Create: `partslib_manifest.py`
- Create: `tests/test_partslib_manifest.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `SCHEMA_VERSION: int = 1`
  - `DEFAULT_IFC_TYPE: str = "Building Element Proxy"`
  - `IFC_TYPE_FACET_ORDER: tuple = ("element", "function")`
  - `validate_facets(doc: dict) -> list[str]` — returns error strings, empty when valid
  - `facet_is_multi(doc: dict, facet: str) -> bool`
  - `facet_values(doc: dict, facet: str) -> list[str]`

- [ ] **Step 1: Write the failing test**

Create `tests/conftest.py`:

```python
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

Create `pytest.ini`:

```ini
[pytest]
testpaths = tests
```

Create `tests/test_partslib_manifest.py`:

```python
import partslib_manifest as pm

FACETS = {
    "function": {"label": "Function", "multi": False,
                 "values": {"Sanitary": {}, "Seating": {}}},
    "element": {"label": "Element", "multi": False,
                "values": {"WC": {"ifcType": "Sanitary Terminal"},
                           "Chair": {"ifcType": "Furniture"}}},
    "room": {"label": "Room", "multi": True,
             "values": {"Bathroom": {}, "Kitchen": {}}},
}


def test_core_module_does_not_import_freecad():
    import inspect
    src = inspect.getsource(pm)
    for banned in ("import FreeCAD", "import Part", "from PySide"):
        assert banned not in src


def test_valid_vocabulary_has_no_errors():
    assert pm.validate_facets(FACETS) == []


def test_facet_without_values_is_an_error():
    errors = pm.validate_facets({"function": {"label": "Function"}})
    assert any("values" in e for e in errors)


def test_facet_values_must_be_a_mapping():
    errors = pm.validate_facets({"function": {"values": ["Sanitary"]}})
    assert any("values" in e for e in errors)


def test_multi_defaults_to_false():
    assert pm.facet_is_multi(FACETS, "element") is False
    assert pm.facet_is_multi(FACETS, "room") is True


def test_facet_values_are_listed_sorted():
    assert pm.facet_values(FACETS, "room") == ["Bathroom", "Kitchen"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --no-project pytest tests/test_partslib_manifest.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'partslib_manifest'`

- [ ] **Step 3: Write minimal implementation**

Create `partslib_manifest.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# PartsLib manifest - the part.json standard and its validation.
#
# This module is deliberately FREE OF FreeCAD IMPORTS so that manifest
# parsing, facet resolution and variant merging can be unit-tested headlessly
# under plain pytest. Do not import FreeCAD, Part or PySide here.

SCHEMA_VERSION = 1
DEFAULT_IFC_TYPE = "Building Element Proxy"

# Order in which facets are consulted for an IfcType mapping when the part
# does not declare one explicitly.
IFC_TYPE_FACET_ORDER = ("element", "function")


def validate_facets(doc):
    """Validate a facets.json document. Returns a list of error strings."""
    errors = []
    if not isinstance(doc, dict):
        return ["facets document must be an object"]
    for name, facet in doc.items():
        if not isinstance(facet, dict):
            errors.append("facet %r must be an object" % name)
            continue
        values = facet.get("values")
        if values is None:
            errors.append("facet %r has no 'values'" % name)
        elif not isinstance(values, dict):
            errors.append("facet %r 'values' must be an object" % name)
        multi = facet.get("multi", False)
        if not isinstance(multi, bool):
            errors.append("facet %r 'multi' must be a boolean" % name)
    return errors


def facet_is_multi(doc, facet):
    """True if the facet accepts several values per part."""
    return bool(doc.get(facet, {}).get("multi", False))


def facet_values(doc, facet):
    """Sorted list of allowed values for a facet."""
    return sorted(doc.get(facet, {}).get("values", {}))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --no-project pytest tests/test_partslib_manifest.py -q`
Expected: PASS, 6 passed

- [ ] **Step 5: Add cache dirs to .gitignore**

Append to `.gitignore`:

```
.cache/
.venv/
```

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py pytest.ini partslib_manifest.py tests/test_partslib_manifest.py .gitignore
git commit -m "feat: add partslib facet vocabulary validation and test harness"
```

---

### Task 3: Manifest validation

**Files:**
- Modify: `partslib_manifest.py`
- Modify: `tests/test_partslib_manifest.py`

**Interfaces:**
- Consumes: `validate_facets`, `facet_is_multi`, `SCHEMA_VERSION` from Task 2.
- Produces:
  - `REQUIRED_FIELDS: tuple`
  - `KNOWN_FIELDS: tuple`
  - `validate_manifest(data: dict, facets: dict) -> tuple[list[str], list[str]]` — `(errors, warnings)`
  - `load_manifest(path: str) -> dict` — raises `ValueError` on unreadable/invalid JSON

- [ ] **Step 1: Write the failing test**

Append to `tests/test_partslib_manifest.py`:

```python
import json

import pytest


def _part(**over):
    data = {
        "schema": 1,
        "id": "wc-geberit-icon",
        "name": "Wall-hung WC",
        "facets": {"function": "Sanitary", "element": "WC",
                   "room": ["Bathroom"]},
        "geometry": {"builder": "asset.single",
                     "assets": {"body": "wc-360.brep"}},
    }
    data.update(over)
    return data


def test_valid_manifest_has_no_errors():
    errors, warnings = pm.validate_manifest(_part(), FACETS)
    assert errors == []
    assert warnings == []


@pytest.mark.parametrize("field", ["schema", "id", "name", "facets", "geometry"])
def test_missing_required_field_is_an_error(field):
    data = _part()
    del data[field]
    errors, _ = pm.validate_manifest(data, FACETS)
    assert any(field in e for e in errors)


def test_future_schema_version_is_an_error():
    errors, _ = pm.validate_manifest(_part(schema=2), FACETS)
    assert any("schema" in e for e in errors)


def test_id_must_be_a_lowercase_slug():
    errors, _ = pm.validate_manifest(_part(id="WC Geberit"), FACETS)
    assert any("id" in e for e in errors)


def test_unknown_facet_is_an_error():
    data = _part(facets={"function": "Sanitary", "colour": "Blue"})
    errors, _ = pm.validate_manifest(data, FACETS)
    assert any("colour" in e for e in errors)


def test_unknown_facet_value_is_an_error():
    data = _part(facets={"function": "Plumbing"})
    errors, _ = pm.validate_manifest(data, FACETS)
    assert any("Plumbing" in e for e in errors)


def test_list_value_on_single_valued_facet_is_an_error():
    data = _part(facets={"function": ["Sanitary", "Seating"]})
    errors, _ = pm.validate_manifest(data, FACETS)
    assert any("function" in e for e in errors)


def test_multi_valued_facet_accepts_a_bare_string():
    data = _part(facets={"function": "Sanitary", "room": "Bathroom"})
    errors, _ = pm.validate_manifest(data, FACETS)
    assert errors == []


def test_geometry_without_builder_is_an_error():
    errors, _ = pm.validate_manifest(_part(geometry={}), FACETS)
    assert any("builder" in e for e in errors)


def test_unknown_top_level_field_is_a_warning_not_an_error():
    errors, warnings = pm.validate_manifest(_part(futureField=1), FACETS)
    assert errors == []
    assert any("futureField" in w for w in warnings)


def test_load_manifest_reads_json(tmp_path):
    path = tmp_path / "part.json"
    path.write_text(json.dumps(_part()), encoding="utf8")
    assert pm.load_manifest(str(path))["id"] == "wc-geberit-icon"


def test_load_manifest_raises_on_bad_json(tmp_path):
    path = tmp_path / "part.json"
    path.write_text("{not json", encoding="utf8")
    with pytest.raises(ValueError):
        pm.load_manifest(str(path))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --no-project pytest tests/test_partslib_manifest.py -q`
Expected: FAIL — `AttributeError: module 'partslib_manifest' has no attribute 'validate_manifest'`

- [ ] **Step 3: Write minimal implementation**

Add to `partslib_manifest.py` (imports go at the top of the file):

```python
import json
import re

REQUIRED_FIELDS = ("schema", "id", "name", "facets", "geometry")

KNOWN_FIELDS = REQUIRED_FIELDS + (
    "description", "keywords", "ifcType", "ifcProperties",
    "params", "placement", "variants",
)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def load_manifest(path):
    """Read a part.json. Raises ValueError if it is missing or malformed."""
    try:
        with open(path, "r", encoding="utf8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ValueError("cannot read manifest %s: %s" % (path, exc))
    if not isinstance(data, dict):
        raise ValueError("manifest %s must be an object" % path)
    return data


def validate_manifest(data, facets):
    """Validate one part manifest against a facet vocabulary.

    Returns (errors, warnings). Unknown top-level fields are warnings so that
    a manifest written against a later schema still loads."""
    errors = []
    warnings = []

    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append("missing required field %r" % field)

    if data.get("schema") not in (None, SCHEMA_VERSION):
        errors.append("unsupported schema version %r (expected %d)"
                      % (data.get("schema"), SCHEMA_VERSION))

    part_id = data.get("id")
    if part_id is not None and not (
            isinstance(part_id, str) and _ID_RE.match(part_id)):
        errors.append("id %r must be a lowercase slug [a-z0-9-]" % (part_id,))

    errors.extend(_validate_part_facets(data.get("facets"), facets))

    geometry = data.get("geometry")
    if geometry is not None:
        if not isinstance(geometry, dict):
            errors.append("geometry must be an object")
        elif not isinstance(geometry.get("builder"), str):
            errors.append("geometry has no 'builder'")

    for field in data:
        if field not in KNOWN_FIELDS:
            warnings.append("unknown field %r (ignored)" % field)

    return errors, warnings


def _validate_part_facets(declared, facets):
    """Check a manifest's facets block against the vocabulary."""
    if declared is None:
        return []
    if not isinstance(declared, dict):
        return ["facets must be an object"]

    errors = []
    for name, value in declared.items():
        if name not in facets:
            errors.append("unknown facet %r" % name)
            continue
        multi = facet_is_multi(facets, name)
        if isinstance(value, list):
            if not multi:
                errors.append("facet %r is single-valued, got a list" % name)
                continue
            values = value
        else:
            values = [value]
        allowed = facets[name].get("values", {})
        for item in values:
            if item not in allowed:
                errors.append("facet %r has unknown value %r" % (name, item))
    return errors
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --no-project pytest tests/test_partslib_manifest.py -q`
Expected: PASS, 22 passed

- [ ] **Step 5: Commit**

```bash
git add partslib_manifest.py tests/test_partslib_manifest.py
git commit -m "feat: validate part manifests against the facet vocabulary"
```

---

### Task 4: Variant merging and IfcType resolution

**Files:**
- Modify: `partslib_manifest.py`
- Modify: `tests/test_partslib_manifest.py`

**Interfaces:**
- Consumes: `IFC_TYPE_FACET_ORDER`, `DEFAULT_IFC_TYPE` from Task 2.
- Produces:
  - `variant_labels(manifest: dict) -> list[str]` — `["Default"]` when the part declares none
  - `resolve_variant(manifest: dict, label: str) -> dict` — a manifest-shaped dict with `geometry.assets`, `params` and `ifcProperties` merged variant-over-part; raises `KeyError` for an unknown label
  - `resolve_ifc_type(manifest: dict, facets: dict) -> str`
  - `derived_metric_names() -> tuple` — `("Width", "Depth", "Height")`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_partslib_manifest.py`:

```python
def _part_with_variants():
    return _part(
        params={"Width": {"type": "Length", "default": 360}},
        ifcProperties={"Manufacturer": "Pset_X;;IfcLabel;;Geberit"},
        variants=[
            {"label": "360 mm",
             "assets": {"body": "wc-360.brep"},
             "ifcProperties": {"ModelReference": "Pset_X;;IfcLabel;;204060"}},
            {"label": "490 mm",
             "assets": {"body": "wc-490.brep"},
             "params": {"Width": {"type": "Length", "default": 490}},
             "ifcProperties": {"ModelReference": "Pset_X;;IfcLabel;;204070"}},
        ])


def test_part_without_variants_has_one_default():
    assert pm.variant_labels(_part()) == ["Default"]


def test_variant_labels_are_listed_in_declared_order():
    assert pm.variant_labels(_part_with_variants()) == ["360 mm", "490 mm"]


def test_resolving_default_variant_returns_the_part_unchanged():
    resolved = pm.resolve_variant(_part(), "Default")
    assert resolved["geometry"]["assets"] == {"body": "wc-360.brep"}


def test_variant_assets_override_part_assets():
    resolved = pm.resolve_variant(_part_with_variants(), "490 mm")
    assert resolved["geometry"]["assets"] == {"body": "wc-490.brep"}


def test_variant_ifc_properties_merge_over_part_level():
    resolved = pm.resolve_variant(_part_with_variants(), "360 mm")
    assert resolved["ifcProperties"]["Manufacturer"] == "Pset_X;;IfcLabel;;Geberit"
    assert resolved["ifcProperties"]["ModelReference"] == "Pset_X;;IfcLabel;;204060"


def test_variant_params_override_part_params():
    resolved = pm.resolve_variant(_part_with_variants(), "490 mm")
    assert resolved["params"]["Width"]["default"] == 490


def test_resolving_leaves_the_original_manifest_untouched():
    data = _part_with_variants()
    pm.resolve_variant(data, "490 mm")
    assert data["geometry"]["assets"] == {"body": "wc-360.brep"}


def test_unknown_variant_label_raises():
    with pytest.raises(KeyError):
        pm.resolve_variant(_part_with_variants(), "999 mm")


def test_explicit_ifc_type_wins():
    data = _part(ifcType="Furniture")
    assert pm.resolve_ifc_type(data, FACETS) == "Furniture"


def test_ifc_type_comes_from_element_facet():
    assert pm.resolve_ifc_type(_part(), FACETS) == "Sanitary Terminal"


def test_ifc_type_falls_back_to_function_facet():
    facets = {"function": {"values": {"Seating": {"ifcType": "Furniture"}}}}
    data = _part(facets={"function": "Seating"})
    assert pm.resolve_ifc_type(data, facets) == "Furniture"


def test_ifc_type_falls_back_to_the_default():
    facets = {"function": {"values": {"Seating": {}}}}
    data = _part(facets={"function": "Seating"})
    assert pm.resolve_ifc_type(data, facets) == pm.DEFAULT_IFC_TYPE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --no-project pytest tests/test_partslib_manifest.py -q`
Expected: FAIL — `AttributeError: module 'partslib_manifest' has no attribute 'variant_labels'`

- [ ] **Step 3: Write minimal implementation**

Add `import copy` to the top of `partslib_manifest.py`, then append:

```python
DEFAULT_VARIANT_LABEL = "Default"


def derived_metric_names():
    """Measurements computed from the built shape, never authored."""
    return ("Width", "Depth", "Height")


def variant_labels(manifest):
    """Ordered variant labels. A part with none gets one implicit default."""
    variants = manifest.get("variants") or []
    if not variants:
        return [DEFAULT_VARIANT_LABEL]
    return [v.get("label", "Variant %d" % i) for i, v in enumerate(variants)]


def resolve_variant(manifest, label):
    """Return a manifest-shaped dict with one variant's overrides applied.

    Merges variant-over-part for `geometry.assets`, `params` and
    `ifcProperties`. The input manifest is never mutated."""
    resolved = copy.deepcopy(manifest)
    variants = resolved.pop("variants", None) or []

    if not variants:
        if label != DEFAULT_VARIANT_LABEL:
            raise KeyError("unknown variant %r" % (label,))
        return resolved

    labels = variant_labels(manifest)
    if label not in labels:
        raise KeyError("unknown variant %r" % (label,))
    variant = copy.deepcopy(variants[labels.index(label)])

    if "assets" in variant:
        resolved.setdefault("geometry", {}).setdefault("assets", {}).update(
            variant["assets"])
    for key in ("params", "ifcProperties"):
        if key in variant:
            resolved.setdefault(key, {}).update(variant[key])
    resolved["variantLabel"] = label
    return resolved


def resolve_ifc_type(manifest, facets):
    """Explicit ifcType, else a facet mapping, else the default."""
    explicit = manifest.get("ifcType")
    if explicit:
        return explicit

    declared = manifest.get("facets") or {}
    for facet in IFC_TYPE_FACET_ORDER:
        value = declared.get(facet)
        if isinstance(value, list):
            value = value[0] if value else None
        if value is None:
            continue
        mapped = facets.get(facet, {}).get("values", {}).get(value, {})
        if mapped.get("ifcType"):
            return mapped["ifcType"]
    return DEFAULT_IFC_TYPE
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --no-project pytest tests/test_partslib_manifest.py -q`
Expected: PASS, 34 passed

- [ ] **Step 5: Commit**

```bash
git add partslib_manifest.py tests/test_partslib_manifest.py
git commit -m "feat: add variant merging and IfcType resolution"
```

---

### Task 5: Library index and cache

**Files:**
- Create: `partslib_index.py`
- Create: `tests/test_partslib_index.py`

**Interfaces:**
- Consumes: `load_manifest`, `validate_manifest`, `validate_facets` from Tasks 2-4.
- Produces:
  - `FACETS_FILENAME = "facets.json"`, `MANIFEST_FILENAME = "part.json"`
  - `scan(library_dir: str) -> dict` — `{"facets": dict, "entries": list, "errors": list, "warnings": list}`. Each entry: `{"id", "name", "description", "keywords", "facets", "path", "dir", "mtime", "variants"}`
  - `is_cache_valid(cache: dict, library_dir: str) -> bool`
  - `save_cache(index: dict, path: str) -> None`
  - `load_cache(path: str) -> dict | None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_partslib_index.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --no-project pytest tests/test_partslib_index.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'partslib_index'`

- [ ] **Step 3: Write minimal implementation**

Create `partslib_index.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# PartsLib index - scans the bundled library, validates every manifest and
# caches the result so that browsing never touches geometry.
#
# Like partslib_manifest, this module is deliberately FREE OF FreeCAD IMPORTS
# so the index, its cache invalidation and its search can be unit-tested
# headlessly. Do not import FreeCAD, Part or PySide here.

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --no-project pytest tests/test_partslib_index.py -q`
Expected: PASS, 11 passed

- [ ] **Step 5: Commit**

```bash
git add partslib_index.py tests/test_partslib_index.py
git commit -m "feat: add partslib library index with mtime cache invalidation"
```

---

### Task 6: Search and faceted grouping

**Files:**
- Modify: `partslib_index.py`
- Modify: `tests/test_partslib_index.py`

**Interfaces:**
- Consumes: entry dicts from Task 5.
- Produces:
  - `UNCLASSIFIED = "(unclassified)"`
  - `score(entry: dict, query: str) -> int`
  - `search(entries: list, query: str) -> list` — ranked, score 0 excluded, empty query returns all sorted by name
  - `group_by(entries: list, facet: str) -> dict[str, list]` — multi-valued facets place an entry in several groups

- [ ] **Step 1: Write the failing test**

Append to `tests/test_partslib_index.py`:

```python
ENTRIES = [
    {"id": "wc-a", "name": "Wall-hung WC", "description": "Rimless pan.",
     "keywords": ["toilet", "pan"],
     "facets": {"function": "Sanitary", "element": "WC",
                "room": ["Bathroom", "Kitchen"]}},
    {"id": "chair-a", "name": "Stacking chair", "description": "Café chair.",
     "keywords": ["seat"],
     "facets": {"function": "Seating", "element": "Chair",
                "room": ["Kitchen"]}},
    {"id": "misc-a", "name": "Mystery object", "description": "",
     "keywords": [], "facets": {"function": "Sanitary"}},
]


def test_empty_query_returns_everything_by_name():
    assert [e["id"] for e in px.search(ENTRIES, "")] == [
        "misc-a", "chair-a", "wc-a"]


def test_search_matches_the_name():
    assert [e["id"] for e in px.search(ENTRIES, "chair")] == ["chair-a"]


def test_search_matches_a_keyword():
    assert [e["id"] for e in px.search(ENTRIES, "toilet")] == ["wc-a"]


def test_search_matches_the_description():
    assert [e["id"] for e in px.search(ENTRIES, "rimless")] == ["wc-a"]


def test_search_is_case_insensitive():
    assert [e["id"] for e in px.search(ENTRIES, "WALL-HUNG")] == ["wc-a"]


def test_name_matches_outrank_description_matches():
    entries = [
        {"id": "desc", "name": "Basin", "description": "next to the chair",
         "keywords": [], "facets": {}},
        {"id": "name", "name": "Chair", "description": "",
         "keywords": [], "facets": {}},
    ]
    assert [e["id"] for e in px.search(entries, "chair")] == ["name", "desc"]


def test_search_excludes_non_matches():
    assert px.search(ENTRIES, "zzzz") == []


def test_group_by_single_valued_facet():
    groups = px.group_by(ENTRIES, "function")
    assert sorted(groups) == ["Sanitary", "Seating"]
    assert sorted(e["id"] for e in groups["Sanitary"]) == ["misc-a", "wc-a"]


def test_multi_valued_facet_puts_one_part_in_several_groups():
    groups = px.group_by(ENTRIES, "room")
    assert sorted(e["id"] for e in groups["Kitchen"]) == ["chair-a", "wc-a"]
    assert [e["id"] for e in groups["Bathroom"]] == ["wc-a"]


def test_entries_missing_the_facet_are_unclassified():
    groups = px.group_by(ENTRIES, "room")
    assert [e["id"] for e in groups[px.UNCLASSIFIED]] == ["misc-a"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --no-project pytest tests/test_partslib_index.py -q`
Expected: FAIL — `AttributeError: module 'partslib_index' has no attribute 'search'`

- [ ] **Step 3: Write minimal implementation**

Append to `partslib_index.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --no-project pytest tests/ -q`
Expected: PASS, 55 passed

- [ ] **Step 5: Commit**

```bash
git add partslib_index.py tests/test_partslib_index.py
git commit -m "feat: add partslib search ranking and faceted grouping"
```

---

### Task 7: Builder registry, asset loading and BREP cache

**Files:**
- Create: `partslib_geometry.py`
- Create: `partslib_builders/__init__.py`
- Create: `tests/test_partslib_geometry.py`

**Interfaces:**
- Consumes: resolved manifests from Task 4.
- Produces:
  - `BUILDER_PACKAGE = "partslib_builders"`
  - `resolve_builder(symbol: str)` — `"module.function"` → callable; raises `ValueError` on a malformed symbol, a path-like symbol, or an unknown module/function
  - `class AssetLoader` — `AssetLoader(part_dir, assets_map)`, method `shape(name) -> Part.Shape`, caches into `<part_dir>/.cache/<name>.brep`
  - `build_shape(resolved_manifest: dict, part_dir: str) -> Part.Shape`
  - `measure(shape) -> dict` — `{"Width", "Depth", "Height"}` in mm from the bounding box

Note: `resolve_builder`'s rejection rules are pure string handling and are unit-tested headlessly. Shape building needs FreeCAD and is verified manually in Task 8.

- [ ] **Step 1: Write the failing test**

Create `tests/test_partslib_geometry.py`:

```python
import pytest

import partslib_geometry as pg


@pytest.mark.parametrize("symbol", [
    "asset",                      # no function part
    "",                           # empty
    "asset.single.extra",         # too many parts
    "../evil.run",                # path traversal
    "/abs/path.run",              # absolute path
    "partslib_builders.asset.single",  # package prefix not allowed
])
def test_malformed_builder_symbols_are_rejected(symbol):
    with pytest.raises(ValueError):
        pg.resolve_builder(symbol)


def test_unknown_builder_module_is_rejected():
    with pytest.raises(ValueError):
        pg.resolve_builder("nosuchmodule.single")


def test_unknown_builder_function_is_rejected():
    with pytest.raises(ValueError):
        pg.resolve_builder("asset.nosuchfunction")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --no-project pytest tests/test_partslib_geometry.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'partslib_geometry'`

- [ ] **Step 3: Write minimal implementation**

Create `partslib_builders/__init__.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Curated part builders. Every builder in this package is repo code, reviewed
# alongside the rest of ArchPlus. Manifests reference builders by symbol
# ("module.function") and can never name a path or an import target outside
# this package - that is what keeps a manifest from executing arbitrary code.
#
# Builder contract:
#     def build(params, assets, ctx) -> Part.Shape
```

Create `partslib_geometry.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# PartsLib geometry - resolves builders, loads shape assets and caches them.
#
# Every source format becomes a bare Part.Shape, never a DocumentObject. That
# is what keeps insertion to a single object in the tree: File > Insert copies
# every sketch and body into the document root and FreeCAD's delete does not
# cascade, so removing the top object would orphan the rest.

import importlib
import os
import re
import sys

_DIR = os.path.dirname(__file__)
if _DIR not in sys.path:
    sys.path.append(_DIR)

BUILDER_PACKAGE = "partslib_builders"
CACHE_DIRNAME = ".cache"

_SYMBOL_RE = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")


def resolve_builder(symbol):
    """Turn a "module.function" symbol into a callable.

    Only names inside the partslib_builders package resolve. Anything
    path-like, dotted deeper than one level, or absent raises ValueError."""
    if not isinstance(symbol, str) or not _SYMBOL_RE.match(symbol):
        raise ValueError("invalid builder symbol %r" % (symbol,))

    module_name, function_name = symbol.split(".")
    try:
        module = importlib.import_module(
            "%s.%s" % (BUILDER_PACKAGE, module_name))
    except ImportError as exc:
        raise ValueError("unknown builder module %r: %s" % (module_name, exc))

    builder = getattr(module, function_name, None)
    if not callable(builder):
        raise ValueError("builder %r has no callable %r"
                         % (module_name, function_name))
    return builder


class AssetLoader:
    """Lazily loads a part's shape assets, caching parsed results as BREP.

    STEP translation is slow; BREP is the format FreeCAD itself stores shapes
    in (ArchReference reads .brp blobs straight out of FCStd archives), so the
    first load of a STEP writes a .brep beside it under .cache/."""

    def __init__(self, part_dir, assets_map):
        self._dir = part_dir
        self._assets = assets_map or {}
        self._shapes = {}

    def shape(self, name):
        """Return the named asset as a Part.Shape."""
        if name in self._shapes:
            return self._shapes[name]

        filename = self._assets.get(name)
        if not filename:
            raise ValueError("part declares no asset %r" % (name,))
        if os.path.isabs(filename) or ".." in filename.split(os.sep):
            raise ValueError("asset %r must be a name inside the part folder"
                             % (filename,))

        source = os.path.join(self._dir, filename)
        if not os.path.exists(source):
            raise ValueError("missing asset file %s" % source)

        shape = self._read(source)
        self._shapes[name] = shape
        return shape

    def _read(self, source):
        import Part

        if source.lower().endswith(".brep"):
            return Part.Shape(Part.read(source))

        cache_dir = os.path.join(self._dir, CACHE_DIRNAME)
        cached = os.path.join(
            cache_dir, os.path.splitext(os.path.basename(source))[0] + ".brep")
        if (os.path.exists(cached)
                and os.path.getmtime(cached) >= os.path.getmtime(source)):
            return Part.Shape(Part.read(cached))

        shape = Part.read(source)
        try:
            if not os.path.isdir(cache_dir):
                os.makedirs(cache_dir)
            shape.exportBrep(cached)
        except Exception:
            pass  # a cache miss is never fatal
        return shape


def measure(shape):
    """Derived measurements, in mm, from the built shape's bounding box.

    Measurements are never authored in a manifest - deriving them is what
    stops a part's stated size disagreeing with its geometry."""
    box = shape.BoundBox
    return {"Width": box.XLength, "Depth": box.YLength, "Height": box.ZLength}


def build_shape(resolved, part_dir):
    """Build one resolved variant's shape."""
    geometry = resolved.get("geometry") or {}
    builder = resolve_builder(geometry.get("builder"))
    assets = AssetLoader(part_dir, geometry.get("assets"))
    params = {name: spec.get("default")
              for name, spec in (resolved.get("params") or {}).items()}
    return builder(params, assets, _Context(geometry))


class _Context:
    """Normalisation helpers handed to every builder as `ctx`."""

    def __init__(self, geometry):
        self.transform = geometry.get("transform") or {}

    def normalize(self, shape, params=None):
        """Apply the manifest's transform: unit scale, rotation, anchor.

        A part's origin is normalised ONCE here, at build time, which is why
        placement never has to know about a vendor asset's arbitrary origin."""
        import FreeCAD

        shape = shape.copy()
        scale = float(self.transform.get("unitScale", 1.0))
        if scale != 1.0:
            matrix = FreeCAD.Matrix()
            matrix.scale(scale, scale, scale)
            shape = shape.transformGeometry(matrix)

        rotate = self.transform.get("rotate")
        if rotate:
            placement = FreeCAD.Placement()
            placement.Rotation = FreeCAD.Rotation(
                float(rotate[0]), float(rotate[1]), float(rotate[2]))
            shape.Placement = placement.multiply(shape.Placement)

        anchor = self.transform.get("anchor")
        if anchor:
            shape.translate(_anchor_offset(shape, anchor))
        return shape


# Anchor names map to a fraction of the bounding box along each axis:
# 0.0 = minimum face, 0.5 = centre, 1.0 = maximum face.
_ANCHOR_FRACTIONS = {
    "center": (0.5, 0.5, 0.5),
    "bottom-center": (0.5, 0.5, 0.0),
    "top-center": (0.5, 0.5, 1.0),
    "back-bottom-center": (0.5, 1.0, 0.0),
    "front-bottom-center": (0.5, 0.0, 0.0),
    "back-center": (0.5, 1.0, 0.5),
    "front-center": (0.5, 0.0, 0.5),
    "origin": None,
}


def _anchor_offset(shape, anchor):
    """Translation that moves `anchor` on the shape to the global origin."""
    import FreeCAD

    if anchor not in _ANCHOR_FRACTIONS:
        raise ValueError("unknown anchor %r" % (anchor,))
    fractions = _ANCHOR_FRACTIONS[anchor]
    if fractions is None:
        return FreeCAD.Vector(0, 0, 0)

    box = shape.BoundBox
    fx, fy, fz = fractions
    return FreeCAD.Vector(
        -(box.XMin + box.XLength * fx),
        -(box.YMin + box.YLength * fy),
        -(box.ZMin + box.ZLength * fz))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --no-project pytest tests/test_partslib_geometry.py -q`
Expected: PASS, 8 passed

- [ ] **Step 5: Commit**

```bash
git add partslib_geometry.py partslib_builders/__init__.py tests/test_partslib_geometry.py
git commit -m "feat: add builder registry, asset loader and BREP cache"
```

---

### Task 8: The `asset.single` builder

**Files:**
- Create: `partslib_builders/asset.py`
- Create: `partslib_builders/demo.py`
- Modify: `tests/test_partslib_geometry.py`

**Interfaces:**
- Consumes: `AssetLoader`, `_Context`, `resolve_builder` from Task 7.
- Produces:
  - `partslib_builders.asset.single(params, assets, ctx) -> Part.Shape` — the stock builder every third-party asset part uses; requires an asset named `body`
  - `partslib_builders.demo.box(params, assets, ctx) -> Part.Shape` — a pure-generation reference builder taking `Width`, `Depth`, `Height`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_partslib_geometry.py`:

```python
def test_stock_asset_builder_resolves():
    assert callable(pg.resolve_builder("asset.single"))


def test_demo_builder_resolves():
    assert callable(pg.resolve_builder("demo.box"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --no-project pytest tests/test_partslib_geometry.py -q`
Expected: FAIL — `ValueError: unknown builder module 'asset'`

- [ ] **Step 3: Write minimal implementation**

Create `partslib_builders/asset.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# The stock asset builder. A part backed by a downloaded STEP/BREP file needs
# no code of its own - it names this builder and supplies metadata, which is
# what makes third-party content safe: an asset-only part executes no
# library-supplied code at all.

ASSET_NAME = "body"


def single(params, assets, ctx):
    """Load the part's single shape asset and normalise it.

    The manifest's geometry.transform decides unit scale, rotation and anchor;
    see partslib_geometry._Context.normalize."""
    return ctx.normalize(assets.shape(ASSET_NAME), params)
```

Create `partslib_builders/demo.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Reference builder for pure generation - no assets, geometry computed from
# parameters. Kept as the worked example of the builder contract.


def box(params, assets, ctx):
    """A parametric box. Params: Width, Depth, Height (mm)."""
    import Part

    width = float(params.get("Width", 600))
    depth = float(params.get("Depth", 600))
    height = float(params.get("Height", 720))
    return Part.makeBox(width, depth, height)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --no-project pytest tests/ -q`
Expected: PASS, 65 passed

- [ ] **Step 5: Verify shape building inside FreeCAD**

This needs FreeCAD, so it is a manual check. Open FreeCAD 1.1 → View → Panels → Python console, and run:

```python
import sys
sys.path.append(r"C:\Users\apeci\AppData\Roaming\FreeCAD\v1-1\Mod\ArchPlus")
import partslib_geometry as pg

resolved = {"geometry": {"builder": "demo.box"},
            "params": {"Width": {"default": 500},
                       "Depth": {"default": 400},
                       "Height": {"default": 300}}}
shape = pg.build_shape(resolved, ".")
print(pg.measure(shape))
```

Expected output: `{'Width': 500.0, 'Depth': 400.0, 'Height': 300.0}`
Confirm that `len(FreeCAD.ActiveDocument.Objects)` is unchanged — building a shape must not add anything to the document.

- [ ] **Step 6: Commit**

```bash
git add partslib_builders/asset.py partslib_builders/demo.py tests/test_partslib_geometry.py
git commit -m "feat: add stock asset builder and reference generation builder"
```

---

### Task 9: Thumbnail rendering

**Files:**
- Create: `partslib_thumbs.py`

**Interfaces:**
- Consumes: `measure`, `build_shape` from Tasks 7-8.
- Produces:
  - `THUMBNAIL_FILENAME = "thumbnail.png"`
  - `THUMBNAIL_SIZE = 256`
  - `thumbnail_path(part_dir: str) -> str`
  - `render_shape(shape, out_path: str, size: int = THUMBNAIL_SIZE) -> bool` — returns False rather than raising when no GL context is available
  - `ensure_thumbnail(entry: dict, resolved: dict) -> str | None` — path to an existing or freshly rendered thumbnail, else None

**Gate:** if Task 1 recorded `SPIKE offscreen: ok=False`, `render_shape` still ships but `ensure_thumbnail` only ever returns committed thumbnails. The code below already degrades that way.

- [ ] **Step 1: Write the implementation**

Create `partslib_thumbs.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# PartsLib thumbnails - offscreen PNG rendering from a bare Part.Shape.
#
# Thumbnails are committed to the repo so a fresh clone opens to a populated
# grid. Runtime rendering is a fallback for a part whose thumbnail is missing,
# and it is never fatal: SoOffscreenRenderer needs a GL context and fails on
# some drivers, so every failure path returns False instead of raising.
#
# The technique follows FreeCAD's own OfflineRenderingUtils.render().

import os

THUMBNAIL_FILENAME = "thumbnail.png"
THUMBNAIL_SIZE = 256
_BACKGROUND = (1.0, 1.0, 1.0)

# Tessellation for writeInventor: (deviation, angular deviation). Coarse
# enough to render fast, fine enough for a 256px thumbnail.
_TESSELLATION = (2, 0.01)


def thumbnail_path(part_dir):
    """Where a part's committed thumbnail lives."""
    return os.path.join(part_dir, THUMBNAIL_FILENAME)


def scene_from_shape(shape):
    """Build a Coin scene graph from a bare Part.Shape - no document needed."""
    from pivy import coin

    buf = shape.writeInventor(*_TESSELLATION)
    reader = coin.SoInput()
    reader.setBuffer(buf)
    return coin.SoDB.readAll(reader)


def render_shape(shape, out_path, size=THUMBNAIL_SIZE):
    """Render `shape` to a PNG. Returns True on success, False otherwise."""
    try:
        from pivy import coin

        node = scene_from_shape(shape)
        root = coin.SoSeparator()
        root.addChild(coin.SoDirectionalLight())
        camera = coin.SoPerspectiveCamera()
        root.addChild(camera)
        root.addChild(node)

        region = coin.SbViewportRegion(size, size)
        camera.viewAll(root, region)

        renderer = coin.SoOffscreenRenderer(region)
        renderer.setBackgroundColor(coin.SbColor(*_BACKGROUND))

        root.ref()
        try:
            ok = renderer.render(root)
        finally:
            root.unref()

        if not ok:
            return False

        folder = os.path.dirname(out_path)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        renderer.writeToFile(out_path, "PNG")
        return os.path.exists(out_path)
    except Exception as exc:
        import FreeCAD
        FreeCAD.Console.PrintWarning(
            "ArchPlus: thumbnail render failed: %s\n" % (exc,))
        return False


def ensure_thumbnail(entry, resolved):
    """Path to the part's thumbnail, rendering one if it is missing."""
    import partslib_geometry

    path = thumbnail_path(entry["dir"])
    if os.path.exists(path):
        return path
    try:
        shape = partslib_geometry.build_shape(resolved, entry["dir"])
    except Exception as exc:
        import FreeCAD
        FreeCAD.Console.PrintWarning(
            "ArchPlus: cannot build %s for a thumbnail: %s\n"
            % (entry["id"], exc))
        return None
    return path if render_shape(shape, path) else None
```

- [ ] **Step 2: Verify in FreeCAD**

FreeCAD Python console:

```python
import sys
sys.path.append(r"C:\Users\apeci\AppData\Roaming\FreeCAD\v1-1\Mod\ArchPlus")
import Part, partslib_thumbs as pt
print(pt.render_shape(Part.makeBox(360, 540, 400),
                      r"C:\Users\apeci\thumb_test.png"))
```

Expected: prints `True`, and `thumb_test.png` shows a shaded box on white.
If it prints `False`, that matches Task 1's `ok=False` outcome — committed thumbnails become mandatory. Record that in the spec and continue.

- [ ] **Step 3: Commit**

```bash
git add partslib_thumbs.py
git commit -m "feat: add offscreen thumbnail rendering from a bare shape"
```

---

### Task 10: The ArchPlus_Part object

**Files:**
- Create: `partslib_object.py`

**Interfaces:**
- Consumes: `load_manifest`, `resolve_variant`, `variant_labels`, `resolve_ifc_type` (Tasks 3-4); `build_shape`, `measure` (Tasks 7-8).
- Produces:
  - `class _LibraryPart` — the `Part::FeaturePython` proxy
  - `class _ViewProviderLibraryPart`
  - `makePart(entry: dict, facets: dict, variant: str | None = None, placement=None)` — creates and returns the document object
  - `resolveEntry(part_id: str) -> tuple[dict, dict] | None` — `(entry, facets)` from the shared index, or None
  - `PROP_PART_ID = "PartId"`, `PROP_VARIANT = "Variant"`

- [ ] **Step 1: Write the implementation**

Create `partslib_object.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# LibraryPart - one document object per inserted library part.
#
# Subclasses ArchComponent.Component so the object inherits Description, Tag,
# Material, IfcType, IfcData and IfcProperties, and so IfcProperties
# round-trips into IFC property sets on export.
#
# CACHE SEMANTICS: the cached shape needs no property of its own, because
# FreeCAD already persists obj.Shape in the FCStd. When the library cannot be
# resolved, execute() returns WITHOUT touching obj.Shape, so the saved geometry
# stays on screen for anyone opening the file without ArchPlus. Nothing
# rebuilds on document open - a corrected library part must never silently
# alter drawings that have already been issued. Rebuilding is the explicit
# "Reload from library" command.

import os
import sys

import FreeCAD
import ArchComponent

_DIR = os.path.dirname(__file__)
if _DIR not in sys.path:
    sys.path.append(_DIR)

import partslib_geometry
import partslib_index
import partslib_manifest

PROP_PART_ID = "PartId"
PROP_VARIANT = "Variant"
_PARAM_GROUP = "Part"

LIBRARY_DIR = os.path.join(_DIR, "library")

_INDEX = None


def libraryIndex(force=False):
    """The scanned library index, cached for the session."""
    global _INDEX
    if _INDEX is None or force:
        _INDEX = partslib_index.scan(LIBRARY_DIR)
        for message in _INDEX["errors"]:
            FreeCAD.Console.PrintError("ArchPlus library: %s\n" % message)
    return _INDEX


def resolveEntry(partId):
    """Find an indexed entry by id. Returns (entry, facets) or None."""
    index = libraryIndex()
    for entry in index["entries"]:
        if entry["id"] == partId:
            return entry, index["facets"]
    return None


class _LibraryPart(ArchComponent.Component):
    """A single library part instance."""

    def __init__(self, obj):
        ArchComponent.Component.__init__(self, obj)
        self.setPartProperties(obj)
        obj.Proxy = self
        self.Type = "LibraryPart"

    def setPartProperties(self, obj):
        if PROP_PART_ID not in obj.PropertiesList:
            obj.addProperty("App::PropertyString", PROP_PART_ID, _PARAM_GROUP,
                            "Library part this object was created from")
            obj.setEditorMode(PROP_PART_ID, 1)  # read-only
        if PROP_VARIANT not in obj.PropertiesList:
            obj.addProperty("App::PropertyEnumeration", PROP_VARIANT,
                            _PARAM_GROUP, "Which variant of the part to build")

    def onDocumentRestored(self, obj):
        ArchComponent.Component.onDocumentRestored(self, obj)
        self.setPartProperties(obj)
        self.Type = "LibraryPart"

    def execute(self, obj):
        """Rebuild from the library, or leave the cached shape alone."""
        partId = getattr(obj, PROP_PART_ID, "")
        if not partId:
            return

        found = resolveEntry(partId)
        if found is None:
            FreeCAD.Console.PrintWarning(
                "ArchPlus: part %r is not in the library; keeping the cached "
                "shape for %s\n" % (partId, obj.Label))
            return  # DO NOT touch obj.Shape - this is the cache

        entry, _facets = found
        try:
            manifest = partslib_manifest.load_manifest(entry["path"])
            resolved = partslib_manifest.resolve_variant(
                manifest, getattr(obj, PROP_VARIANT, None)
                or partslib_manifest.DEFAULT_VARIANT_LABEL)
            shape = partslib_geometry.build_shape(resolved, entry["dir"])
        except Exception as exc:
            FreeCAD.Console.PrintError(
                "ArchPlus: cannot rebuild %s: %s\n" % (obj.Label, exc))
            return  # cache again

        placement = obj.Placement
        obj.Shape = shape
        obj.Placement = placement


class _ViewProviderLibraryPart(ArchComponent.ViewProviderComponent):

    def __init__(self, vobj):
        ArchComponent.ViewProviderComponent.__init__(self, vobj)
        vobj.Proxy = self

    def getIcon(self):
        return os.path.join(_DIR, "Resources", "icons", "PartsLibrary.svg")

    def setEdit(self, vobj, mode):
        return False


def _applyMetadata(obj, resolved, facets):
    """Write description, IfcType and IfcProperties onto the object."""
    obj.Description = resolved.get("description", "")
    ifcType = partslib_manifest.resolve_ifc_type(resolved, facets)
    try:
        obj.IfcType = ifcType
    except Exception:
        FreeCAD.Console.PrintWarning(
            "ArchPlus: IfcType %r not accepted; leaving the default\n"
            % (ifcType,))
    properties = resolved.get("ifcProperties") or {}
    if properties:
        obj.IfcProperties = dict(properties)


def makePart(entry, facets, variant=None, placement=None):
    """Create one library part object in the active document."""
    doc = FreeCAD.ActiveDocument
    if doc is None:
        raise RuntimeError("no active document")

    manifest = partslib_manifest.load_manifest(entry["path"])
    labels = partslib_manifest.variant_labels(manifest)
    variant = variant or labels[0]
    resolved = partslib_manifest.resolve_variant(manifest, variant)

    obj = doc.addObject("Part::FeaturePython", "LibraryPart")
    _LibraryPart(obj)
    if FreeCAD.GuiUp:
        _ViewProviderLibraryPart(obj.ViewObject)

    obj.Label = manifest.get("name", entry["id"])
    setattr(obj, PROP_PART_ID, entry["id"])
    setattr(obj, PROP_VARIANT, labels)
    setattr(obj, PROP_VARIANT, variant)
    _applyMetadata(obj, resolved, facets)

    if placement is not None:
        obj.Placement = placement

    obj.Proxy.execute(obj)
    return obj
```

- [ ] **Step 2: Add the toolbar icon**

Create `Resources/icons/PartsLibrary.svg` — a 64×64 SVG matching the visual weight of `Resources/icons/WindowsPlus.svg`. Open `WindowsPlus.svg`, copy its root `<svg>` element and stroke widths, and draw a simple 3×3 grid of squares with the top-left square filled.

- [ ] **Step 3: Verify in FreeCAD**

Requires Task 15's seed content, so this check runs after Task 15. Record here that the verification is deferred; do not skip it.

- [ ] **Step 4: Commit**

```bash
git add partslib_object.py Resources/icons/PartsLibrary.svg
git commit -m "feat: add LibraryPart document object with cache-preserving execute"
```

---

### Task 11: Variant switching and Reload from library

**Files:**
- Modify: `partslib_object.py`

**Interfaces:**
- Consumes: `_LibraryPart`, `resolveEntry`, `libraryIndex` from Task 10.
- Produces:
  - `_LibraryPart.onChanged(obj, prop)` — rebuilds when `Variant` changes
  - `_ViewProviderLibraryPart.setupContextMenu(vobj, menu)` — adds **Reload from library**
  - `reloadFromLibrary(obj) -> bool`

- [ ] **Step 1: Write the implementation**

Add to `_LibraryPart` in `partslib_object.py`:

```python
    def onChanged(self, obj, prop):
        """Switching Variant rebuilds in place, preserving placement."""
        if prop == PROP_VARIANT and not getattr(self, "_rebuilding", False):
            self._rebuilding = True
            try:
                self.execute(obj)
            finally:
                self._rebuilding = False
        else:
            ArchComponent.Component.onChanged(self, obj, prop)
```

Add at module level:

```python
def reloadFromLibrary(obj):
    """Force one object to rebuild from the current library contents.

    This is deliberately explicit. Automatic rebuilding on document open would
    let a corrected library part silently change drawings already issued."""
    libraryIndex(force=True)
    partId = getattr(obj, PROP_PART_ID, "")
    found = resolveEntry(partId)
    if found is None:
        FreeCAD.Console.PrintError(
            "ArchPlus: part %r is not in the library\n" % (partId,))
        return False

    entry, facets = found
    manifest = partslib_manifest.load_manifest(entry["path"])
    labels = partslib_manifest.variant_labels(manifest)
    current = getattr(obj, PROP_VARIANT, None)
    setattr(obj, PROP_VARIANT, labels)
    if current in labels:
        setattr(obj, PROP_VARIANT, current)

    resolved = partslib_manifest.resolve_variant(
        manifest, getattr(obj, PROP_VARIANT, labels[0]))
    _applyMetadata(obj, resolved, facets)
    obj.Proxy.execute(obj)
    obj.Document.recompute()
    return True
```

Add to `_ViewProviderLibraryPart`:

```python
    def setupContextMenu(self, vobj, menu):
        from PySide import QtGui

        action = QtGui.QAction("Reload from library", menu)
        action.triggered.connect(lambda: reloadFromLibrary(vobj.Object))
        menu.addAction(action)
```

- [ ] **Step 2: Verify in FreeCAD**

Deferred to Task 15 alongside Task 10's check, since both need seed content.

- [ ] **Step 3: Commit**

```bash
git add partslib_object.py
git commit -m "feat: add variant switching and explicit reload from library"
```

---

### Task 12: Placement

**Files:**
- Create: `partslib_placement.py`
- Create: `tests/test_partslib_placement.py`

**Interfaces:**
- Consumes: `placement` block from a resolved manifest (Task 4).
- Produces:
  - `HOSTS = ("wall", "floor", "ceiling", "free")`
  - `DEFAULT_HOST = "free"`
  - `host_of(resolved: dict) -> str`, `offset_of(resolved: dict) -> float`
  - `offset_sign(host: str) -> float` — `+1` up, `-1` down, `0` none
  - `partPlacement(point, baseFace, host, offset)` — the FreeCAD placement

The host rules are pure arithmetic and are unit-tested; the geometry needs FreeCAD and is checked manually.

- [ ] **Step 1: Write the failing test**

Create `tests/test_partslib_placement.py`:

```python
import pytest

import partslib_placement as pp


def test_missing_placement_block_defaults_to_free():
    assert pp.host_of({}) == "free"
    assert pp.offset_of({}) == 0.0


def test_host_and_offset_are_read_from_the_manifest():
    resolved = {"placement": {"host": "wall", "offset": 400}}
    assert pp.host_of(resolved) == "wall"
    assert pp.offset_of(resolved) == 400.0


def test_unknown_host_falls_back_to_free():
    assert pp.host_of({"placement": {"host": "moon"}}) == "free"


@pytest.mark.parametrize("host,sign", [
    ("wall", 1.0), ("floor", 1.0), ("ceiling", -1.0), ("free", 0.0)])
def test_offset_direction_per_host(host, sign):
    assert pp.offset_sign(host) == sign


def test_every_host_has_a_sign():
    for host in pp.HOSTS:
        assert pp.offset_sign(host) in (-1.0, 0.0, 1.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --with pytest --no-project pytest tests/test_partslib_placement.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'partslib_placement'`

- [ ] **Step 3: Write minimal implementation**

Create `partslib_placement.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# PartsLib placement - where a part lands when you click.
#
# All four hosts run through ONE rule rather than four code paths: placement
# always orients from the picked face, and `host` decides only which way the
# offset runs and whether to snap to the host's base. That deliberately avoids
# raycasting to find the slab above, which is where host-aware placement
# usually turns expensive.
#
# The orientation half is a generalisation of _doorPlacement in
# doorsplus_gui.py, which already solves picked-face orientation and base-Z
# snapping. A part's own origin is normalised at build time
# (partslib_geometry._Context.normalize), so nothing here needs to know about
# a vendor asset's arbitrary origin.

HOSTS = ("wall", "floor", "ceiling", "free")
DEFAULT_HOST = "free"

# Which way the manifest's offset runs from the reference surface.
_OFFSET_SIGN = {"wall": 1.0, "floor": 1.0, "ceiling": -1.0, "free": 0.0}

# Hosts that snap to the host object's base Z rather than the picked point.
_SNAPS_TO_HOST_BASE = ("wall",)


def host_of(resolved):
    """The declared host, defaulting to 'free' for anything unrecognised."""
    host = (resolved.get("placement") or {}).get("host", DEFAULT_HOST)
    return host if host in HOSTS else DEFAULT_HOST


def offset_of(resolved):
    """Offset in mm from the reference surface."""
    try:
        return float((resolved.get("placement") or {}).get("offset", 0.0))
    except (TypeError, ValueError):
        return 0.0


def offset_sign(host):
    """+1 offsets up, -1 offsets down, 0 applies no offset."""
    return _OFFSET_SIGN.get(host, 0.0)


def partPlacement(point, baseFace, host, offset):
    """Build the placement for a picked point.

    `baseFace` is a (object, faceIndex) tuple as handed back by the Snapper, or
    None when the user clicked empty space."""
    import FreeCAD
    import DraftGeomUtils
    import WorkingPlane

    wp = WorkingPlane.get_working_plane()
    if baseFace is not None:
        face = baseFace[0].Shape.Faces[baseFace[1]]
        placement = DraftGeomUtils.placement_from_face(face, vec_z=wp.axis)
    else:
        placement = FreeCAD.Placement()
        placement.Rotation = FreeCAD.Rotation(wp.u, wp.axis, -wp.v, "XZY")

    z = point.z
    if host in _SNAPS_TO_HOST_BASE and baseFace is not None:
        try:
            z = baseFace[0].Shape.BoundBox.ZMin
        except Exception:
            z = point.z
    z += offset_sign(host) * float(offset)

    placement.Base = FreeCAD.Vector(point.x, point.y, z)
    return placement
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --with pytest --no-project pytest tests/ -q`
Expected: PASS, 73 passed

- [ ] **Step 5: Commit**

```bash
git add partslib_placement.py tests/test_partslib_placement.py
git commit -m "feat: add host-aware placement rules for library parts"
```

---

### Task 13: The dock panel — browsing

**Files:**
- Create: `partslib_gui.py`
- Modify: `InitGui.py:22`

**Interfaces:**
- Consumes: `libraryIndex` (Task 10); `search`, `group_by`, `UNCLASSIFIED` (Task 6); `ensure_thumbnail` (Task 9).
- Produces:
  - `class PartsLibraryPanel(QtGui.QDockWidget)` — with `refresh()`, `currentEntry() -> dict | None`, and a `selectionChanged` behaviour hook `_onSelect()`
  - `class PartsLibraryCommand` — registered as `ArchPlus_PartsLibrary`
  - `showPanel() -> PartsLibraryPanel` — creates or raises the singleton

- [ ] **Step 1: Write the implementation**

Create `partslib_gui.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# PartsLibrary - a dockable browser for the bundled BIM parts library.
#
# Unlike the other ArchPlus tools this is NOT a Task panel: it is a QDockWidget
# that stays open across insertions, so the pick -> place -> pick loop a
# library exists for does not require reopening the tool between parts.
#
# Browsing never loads geometry. The grid is built from the cached index and
# committed PNG thumbnails; a shape is only built when a part is previewed or
# placed.

import os
import sys

import FreeCAD
import FreeCADGui
from PySide import QtGui, QtCore

_DIR = os.path.dirname(__file__)
if _DIR not in sys.path:
    sys.path.append(_DIR)

import partslib_index
import partslib_object
import partslib_thumbs

ICON = os.path.join(_DIR, "Resources", "icons", "PartsLibrary.svg")

GROUP_FACETS = ("function", "element", "room")
DEFAULT_GROUP_FACET = "function"
_PREF_PATH = "User parameter:BaseApp/Preferences/Mod/ArchPlus"
_PREF_GROUP_KEY = "PartsLibraryGroupBy"

_THUMB_SIZE = 96

_panel = None


def _prefs():
    return FreeCAD.ParamGet(_PREF_PATH)


class PartsLibraryPanel(QtGui.QDockWidget):
    """The library browser dock."""

    def __init__(self, parent=None):
        super(PartsLibraryPanel, self).__init__("ArchPlus Library", parent)
        self.setObjectName("ArchPlusPartsLibrary")
        self._entries = []
        self._buildUi()
        self.refresh()

    # -- construction ----------------------------------------------------
    def _buildUi(self):
        body = QtGui.QWidget()
        layout = QtGui.QVBoxLayout(body)

        self.search = QtGui.QLineEdit()
        self.search.setPlaceholderText("Search…")
        self.search.textChanged.connect(self._repopulate)
        layout.addWidget(self.search)

        groupRow = QtGui.QHBoxLayout()
        groupRow.addWidget(QtGui.QLabel("Group by:"))
        self.groupBy = QtGui.QComboBox()
        self.groupBy.addItems([f.capitalize() for f in GROUP_FACETS])
        stored = _prefs().GetString(_PREF_GROUP_KEY, DEFAULT_GROUP_FACET)
        if stored in GROUP_FACETS:
            self.groupBy.setCurrentIndex(GROUP_FACETS.index(stored))
        self.groupBy.currentIndexChanged.connect(self._onGroupChanged)
        groupRow.addWidget(self.groupBy, 1)
        layout.addLayout(groupRow)

        splitter = QtGui.QSplitter(QtCore.Qt.Horizontal)
        self.tree = QtGui.QListWidget()
        self.tree.setMaximumWidth(140)
        self.tree.currentItemChanged.connect(self._repopulateGrid)
        splitter.addWidget(self.tree)

        self.grid = QtGui.QListWidget()
        self.grid.setViewMode(QtGui.QListView.IconMode)
        self.grid.setIconSize(QtCore.QSize(_THUMB_SIZE, _THUMB_SIZE))
        self.grid.setResizeMode(QtGui.QListView.Adjust)
        self.grid.setMovement(QtGui.QListView.Static)
        self.grid.setSpacing(6)
        self.grid.currentItemChanged.connect(self._onSelect)
        splitter.addWidget(self.grid)
        layout.addWidget(splitter, 1)

        self.setWidget(body)

    # -- data ------------------------------------------------------------
    def refresh(self):
        """Rescan the library and rebuild the whole view."""
        index = partslib_object.libraryIndex(force=True)
        self._entries = index["entries"]
        self._facets = index["facets"]
        self._repopulate()

    def _groupFacet(self):
        return GROUP_FACETS[self.groupBy.currentIndex()]

    def _onGroupChanged(self, *args):
        _prefs().SetString(_PREF_GROUP_KEY, self._groupFacet())
        self._repopulate()

    def _repopulate(self, *args):
        """Rebuild the group list, preserving the selected group if possible."""
        previous = self.tree.currentItem().text() if self.tree.currentItem() \
            else None
        matches = partslib_index.search(self._entries, self.search.text())
        self._groups = partslib_index.group_by(matches, self._groupFacet())

        self.tree.blockSignals(True)
        self.tree.clear()
        for name in sorted(self._groups):
            self.tree.addItem(name)
        self.tree.blockSignals(False)

        if self.tree.count():
            row = 0
            if previous:
                found = self.tree.findItems(previous, QtCore.Qt.MatchExactly)
                if found:
                    row = self.tree.row(found[0])
            self.tree.setCurrentRow(row)
        self._repopulateGrid()

    def _repopulateGrid(self, *args):
        self.grid.clear()
        item = self.tree.currentItem()
        if item is None:
            return
        for entry in sorted(self._groups.get(item.text(), []),
                            key=lambda e: e["name"]):
            cell = QtGui.QListWidgetItem(entry["name"])
            cell.setData(QtCore.Qt.UserRole, entry["id"])
            thumb = os.path.join(entry["dir"],
                                 partslib_thumbs.THUMBNAIL_FILENAME)
            if os.path.exists(thumb):
                cell.setIcon(QtGui.QIcon(thumb))
            cell.setToolTip(entry.get("description") or entry["name"])
            self.grid.addItem(cell)

    def currentEntry(self):
        """The selected entry dict, or None."""
        item = self.grid.currentItem()
        if item is None:
            return None
        partId = item.data(QtCore.Qt.UserRole)
        for entry in self._entries:
            if entry["id"] == partId:
                return entry
        return None

    def _onSelect(self, *args):
        """Extended in Task 14 to drive the detail pane."""
        pass


def showPanel():
    """Create the dock, or raise it if it already exists."""
    global _panel
    main = FreeCADGui.getMainWindow()
    if _panel is None:
        _panel = PartsLibraryPanel(main)
        main.addDockWidget(QtCore.Qt.RightDockWidgetArea, _panel)
    else:
        _panel.refresh()
    _panel.show()
    _panel.raise_()
    return _panel


class PartsLibraryCommand:
    """ArchPlus_PartsLibrary - open the parts library browser."""

    def GetResources(self):
        return {"Pixmap": ICON,
                "MenuText": "Parts Library",
                "ToolTip": "Browse and place reusable BIM parts"}

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        showPanel()


# Register the command (FreeCAD 1.1 has no removeCommand; addCommand is a
# no-op when the name already exists).
if FreeCAD.GuiUp:
    FreeCADGui.addCommand("ArchPlus_PartsLibrary", PartsLibraryCommand())
```

- [ ] **Step 2: Wire it into the toolbar**

In `InitGui.py:22`, change:

```python
    commands = ["ArchPlus_Stairs", "ArchPlus_Doors", "ArchPlus_Windows"]
```

to:

```python
    commands = ["ArchPlus_Stairs", "ArchPlus_Doors", "ArchPlus_Windows",
                "ArchPlus_PartsLibrary"]
```

And in `add_ui()`, after the `import windowsplus_gui` line, add:

```python
        import partslib_gui     # noqa: F401
```

- [ ] **Step 3: Verify in FreeCAD**

Deferred to Task 15, which supplies the content the grid needs.

- [ ] **Step 4: Commit**

```bash
git add partslib_gui.py InitGui.py
git commit -m "feat: add Parts Library dock panel with faceted browsing"
```

---

### Task 14: The detail pane and placing

**Files:**
- Modify: `partslib_gui.py`

**Interfaces:**
- Consumes: `PartsLibraryPanel` (Task 13); `makePart` (Task 10); `host_of`, `offset_of`, `partPlacement` (Task 12); `build_shape`, `measure` (Tasks 7-8); `scene_from_shape` (Task 9).
- Produces:
  - `PartsLibraryPanel._buildDetail()`, `_onSelect()`, `_onVariantChanged()`, `_onPlace()`
  - `PREVIEW_LIVE: bool` — set from Task 1's spike result

**Gate:** set `PREVIEW_LIVE = True` only if Task 1 recorded `SPIKE quarter: embedded OK`. Otherwise set it `False`; the code below then shows a scaled thumbnail instead, and no other change is needed.

- [ ] **Step 1: Write the implementation**

Add near the top of `partslib_gui.py`, after `_THUMB_SIZE`:

```python
# Set from the Task 1 spike: True when pivy.quarter.QuarterWidget embeds
# under FreeCAD 1.1's PySide shim, False to fall back to a static image.
PREVIEW_LIVE = True

_PREVIEW_HEIGHT = 180
```

Add these methods to `PartsLibraryPanel`, and call `self._buildDetail(layout)` from `_buildUi` immediately before `self.setWidget(body)`:

```python
    def _buildDetail(self, layout):
        """Preview, measurements, description, variant picker and Place."""
        if PREVIEW_LIVE:
            from pivy import quarter
            self.preview = quarter.QuarterWidget()
        else:
            self.preview = QtGui.QLabel()
            self.preview.setAlignment(QtCore.Qt.AlignCenter)
        self.preview.setMinimumHeight(_PREVIEW_HEIGHT)
        layout.addWidget(self.preview)

        variantRow = QtGui.QHBoxLayout()
        variantRow.addWidget(QtGui.QLabel("Variant:"))
        self.variant = QtGui.QComboBox()
        self.variant.currentIndexChanged.connect(self._onVariantChanged)
        variantRow.addWidget(self.variant, 1)
        layout.addLayout(variantRow)

        self.metrics = QtGui.QLabel("")
        layout.addWidget(self.metrics)

        self.description = QtGui.QLabel("")
        self.description.setWordWrap(True)
        layout.addWidget(self.description)

        self.placeButton = QtGui.QPushButton("Place")
        self.placeButton.setEnabled(False)
        self.placeButton.clicked.connect(self._onPlace)
        layout.addWidget(self.placeButton)

    def _onSelect(self, *args):
        entry = self.currentEntry()
        self.placeButton.setEnabled(entry is not None)
        if entry is None:
            self.variant.clear()
            self.metrics.setText("")
            self.description.setText("")
            return

        self.description.setText(entry.get("description") or "")
        self.variant.blockSignals(True)
        self.variant.clear()
        self.variant.addItems(entry["variants"])
        self.variant.blockSignals(False)
        self._refreshPreview()

    def _onVariantChanged(self, *args):
        self._refreshPreview()

    def _resolvedSelection(self):
        """(entry, resolved manifest) for the current selection, or None."""
        import partslib_manifest

        entry = self.currentEntry()
        if entry is None:
            return None
        manifest = partslib_manifest.load_manifest(entry["path"])
        label = self.variant.currentText() or entry["variants"][0]
        return entry, partslib_manifest.resolve_variant(manifest, label)

    def _refreshPreview(self):
        """Build the selected variant and show it with its measurements."""
        import partslib_geometry

        selection = self._resolvedSelection()
        if selection is None:
            return
        entry, resolved = selection
        try:
            shape = partslib_geometry.build_shape(resolved, entry["dir"])
        except Exception as exc:
            self.metrics.setText("Cannot build this part: %s" % exc)
            return

        metrics = partslib_geometry.measure(shape)
        self.metrics.setText("W %.0f   D %.0f   H %.0f mm"
                             % (metrics["Width"], metrics["Depth"],
                                metrics["Height"]))

        if PREVIEW_LIVE:
            try:
                self.preview.setSceneGraph(
                    partslib_thumbs.scene_from_shape(shape))
                self.preview.viewAll()
            except Exception as exc:
                FreeCAD.Console.PrintWarning(
                    "ArchPlus: live preview failed: %s\n" % (exc,))
        else:
            thumb = os.path.join(entry["dir"],
                                 partslib_thumbs.THUMBNAIL_FILENAME)
            if os.path.exists(thumb):
                self.preview.setPixmap(QtGui.QPixmap(thumb).scaledToHeight(
                    _PREVIEW_HEIGHT, QtCore.Qt.SmoothTransformation))

    def _onPlace(self):
        """Pick a point in the 3D view, then create the part there."""
        import partslib_placement

        selection = self._resolvedSelection()
        if selection is None:
            return
        entry, resolved = selection
        host = partslib_placement.host_of(resolved)
        offset = partslib_placement.offset_of(resolved)
        variant = self.variant.currentText() or entry["variants"][0]

        # The Snapper's callback does NOT hand back the picked face - only the
        # movecallback's `info` dict carries it. Capture it there and read it
        # back on click, exactly as repositionDoor does
        # (doorsplus_gui.py:922-934).
        doc = FreeCAD.ActiveDocument
        state = {"face": None}

        def moved(point, info):
            if info and "Face" in info.get("Component", ""):
                target = doc.getObject(info["Object"])
                try:
                    index = int(info["Component"][4:]) - 1
                except (ValueError, IndexError):
                    state["face"] = None
                else:
                    state["face"] = [target, index]
            else:
                state["face"] = None

        def placed(point=None, obj=None):
            FreeCADGui.Snapper.off()
            if point is None:
                return
            placement = partslib_placement.partPlacement(
                point, state["face"], host, offset)
            doc.openTransaction("Place library part")
            try:
                partslib_object.makePart(
                    entry, self._facets, variant=variant, placement=placement)
                doc.commitTransaction()
            except Exception as exc:
                doc.abortTransaction()
                FreeCAD.Console.PrintError(
                    "ArchPlus: cannot place %s: %s\n" % (entry["id"], exc))
            doc.recompute()

        FreeCADGui.Snapper.getPoint(callback=placed, movecallback=moved)
```

- [ ] **Step 2: Verify in FreeCAD**

Deferred to Task 15.

- [ ] **Step 3: Commit**

```bash
git add partslib_gui.py
git commit -m "feat: add detail pane, live preview and click-to-place"
```

---

### Task 15: Seed library content, end-to-end verification and docs

**Files:**
- Create: `library/facets.json`
- Create: `library/furniture/base-cabinet/part.json`
- Create: `library/sanitary/wc-demo/part.json`
- Modify: `README.md`

**Interfaces:**
- Consumes: everything above.
- Produces: a working library that exercises both builder flavours — one generated part with variants, one asset-shaped part.

- [ ] **Step 1: Write the vocabulary**

Create `library/facets.json`:

```json
{
  "function": {
    "label": "Function",
    "multi": false,
    "values": {
      "Sanitary": { "ifcType": "Sanitary Terminal" },
      "Seating": { "ifcType": "Furniture" },
      "Storage": { "ifcType": "Furniture" },
      "Lighting": { "ifcType": "Lighting Fixture" }
    }
  },
  "element": {
    "label": "Element",
    "multi": false,
    "values": {
      "WC": { "ifcType": "Sanitary Terminal" },
      "Basin": { "ifcType": "Sanitary Terminal" },
      "Cabinet": { "ifcType": "Furniture" },
      "Chair": { "ifcType": "Furniture" }
    }
  },
  "room": {
    "label": "Room",
    "multi": true,
    "values": {
      "Bathroom": {},
      "Cloakroom": {},
      "Kitchen": {},
      "Bedroom": {},
      "Office": {}
    }
  }
}
```

- [ ] **Step 2: Write a generated part with variants**

Create `library/furniture/base-cabinet/part.json`:

```json
{
  "schema": 1,
  "id": "base-cabinet",
  "name": "Base cabinet",
  "description": "Parametric kitchen base carcass. Sits on the floor.",
  "keywords": ["cabinet", "carcass", "kitchen", "unit"],
  "facets": {
    "function": "Storage",
    "element": "Cabinet",
    "room": ["Kitchen", "Office"]
  },
  "params": {
    "Width": { "type": "Length", "default": 600 },
    "Depth": { "type": "Length", "default": 560 },
    "Height": { "type": "Length", "default": 720 }
  },
  "placement": { "host": "floor", "offset": 0 },
  "variants": [
    { "label": "600 mm", "params": { "Width": { "type": "Length", "default": 600 } } },
    { "label": "800 mm", "params": { "Width": { "type": "Length", "default": 800 } } },
    { "label": "1000 mm", "params": { "Width": { "type": "Length", "default": 1000 } } }
  ],
  "geometry": { "builder": "demo.box" },
  "ifcProperties": {
    "Reference": "Pset_ManufacturerTypeInformation;;IfcLabel;;ArchPlus demo"
  }
}
```

- [ ] **Step 3: Write a wall-hosted part**

Create `library/sanitary/wc-demo/part.json`. It uses `demo.box` rather than a
vendor asset so the seed library carries no binaries; replacing `geometry` with
`{"builder": "asset.single", "assets": {"body": "wc-360.brep"}}` is the whole
change needed once a real asset exists.

```json
{
  "schema": 1,
  "id": "wc-demo",
  "name": "Wall-hung WC (demo)",
  "description": "Placeholder wall-hung pan. Demonstrates wall hosting at a 400 mm mounting height.",
  "keywords": ["toilet", "wc", "pan"],
  "facets": {
    "function": "Sanitary",
    "element": "WC",
    "room": ["Bathroom", "Cloakroom"]
  },
  "params": {
    "Width": { "type": "Length", "default": 360 },
    "Depth": { "type": "Length", "default": 540 },
    "Height": { "type": "Length", "default": 400 }
  },
  "placement": { "host": "wall", "offset": 400 },
  "geometry": { "builder": "demo.box" }
}
```

- [ ] **Step 4: Run the full test suite**

Run: `uv run --with pytest --no-project pytest tests/ -q`
Expected: PASS, 73 passed

- [ ] **Step 5: End-to-end verification in FreeCAD**

This is the deferred verification for Tasks 10, 11, 13 and 14. Restart FreeCAD 1.1, switch to the **BIM** workbench, and work through every line:

1. The **ArchPlus** toolbar shows a fourth button with the Parts Library icon.
2. Create a new document and draw an Arch Wall (BIM → Wall), so there is a wall face to click.
3. Click **Parts Library**. A dock appears on the right titled "ArchPlus Library".
4. The group list shows `Sanitary`, `Storage`. The grid shows the parts in the selected group.
5. Switch **Group by** to `Room`. `Bathroom`, `Cloakroom`, `Kitchen`, `Office` appear, and **Wall-hung WC (demo) appears under both Bathroom and Cloakroom** — this is the multi-valued facet working.
6. Type `toilet` in the search box. Only the WC remains, matched on its keyword.
7. Clear the search. Select **Base cabinet**. The detail pane shows a preview, `W 600  D 560  H 720 mm`, and the description.
8. Change **Variant** to `800 mm`. The measurements change to `W 800`.
9. Click **Place**, then click a point on the floor. Exactly ONE object named "Base cabinet" appears in the tree — expand it and confirm it has **no children**.
10. Select it. In the property editor confirm `PartId` = `base-cabinet` (greyed out), `Variant` = `800 mm`, `Description` is populated, `IfcType` = `Furniture`.
11. Change `Variant` to `1000 mm` in the property editor. The object rebuilds in place and keeps its position.
12. Select the WC in the panel, click **Place**, then click a wall face. It lands at the wall base + 400 mm and orients to the wall.
13. The dock is still open. Place a second cabinet without reopening anything.
14. Right-click the placed part in the tree → **Reload from library** runs without error.
15. Save the document, close it, reopen it. The parts still render, and nothing rebuilt on open.
16. Delete a placed part. Confirm the tree is left completely clean — no orphaned objects.

Fix anything that fails before continuing. Record step 5, 9 and 16 outcomes in the commit message.

- [ ] **Step 6: Document the tool**

In `README.md`, add a `## Features (Parts Library)` section after the Windows
section, and add a Parts Library bullet to the **Usage** list. Cover: the
dockable browser that stays open, faceted grouping with multi-valued rooms,
search, live preview with derived measurements, variants, host-aware
click-to-place, single-object insertion with no tree pollution, and
**Reload from library**. Match the existing sections' bullet style.

Also update the intro paragraph, which currently reads "It currently provides
enhanced parametric **Stairs**, **Doors**, and **Windows** tools" — add the
Parts Library, noting it is a content library rather than a modified copy of a
native Arch module.

- [ ] **Step 7: Commit**

```bash
git add library README.md
git commit -m "feat: add seed parts library content and document the tool"
```

---

## Self-Review

**Spec coverage.** Every section maps to a task: §3 standard → Tasks 3-4; §4 facets → Tasks 2-4, 6; §5 object → Tasks 10-11; §6 geometry → Tasks 7-8; §7 placement → Task 12; §8 panel → Tasks 13-14; §9 index/caches/thumbnails → Tasks 5, 9; §10 modules → all; §11 testing → Tasks 2-8, 12; §12 risks → Task 1 gates risks 1-2, Task 15 step 5 covers risk 4.

Two spec items are deliberately partial and named as such:

- **§9 BREP sizing (risk 3)** has no task, because the seed content in Task 15 ships no binary assets — there is nothing to measure yet. The measurement is due when the first vendor asset lands.
- **§5.1 per-param object properties** are not created by `makePart`; `params` currently reach the builder through the manifest only, so editing a dimension on a placed object is not yet possible (variant switching is). Closing this means adding one `App::PropertyLength` per declared param in `_LibraryPart.setPartProperties` and reading them back in `execute()`. Flagged rather than silently dropped.

**Placeholder scan.** No TBD/TODO markers. Every code step carries real code. The three "deferred to Task 15" verification steps name the exact task and are all discharged by Task 15 step 5.

**Type consistency.** `resolve_variant` returns a manifest-shaped dict used identically in Tasks 10 and 14. `partPlacement(point, baseFace, host, offset)` matches its Task 14 call site. `entry` dicts carry the same keys (`id`, `name`, `description`, `keywords`, `facets`, `variants`, `path`, `dir`, `mtime`) everywhere they are consumed. `THUMBNAIL_FILENAME` is referenced from `partslib_thumbs` in both GUI tasks.
