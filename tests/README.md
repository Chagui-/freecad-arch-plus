# Tests

Unit tests for the pure logic in the ArchPlus GUI modules — no FreeCAD install
required. `conftest.py` injects lightweight fakes for `FreeCAD`, `FreeCADGui`,
`PySide`, `Part` and `Sketcher` into `sys.modules`, so the modules import and
the geometry builders run against a stub kernel.

One test file per tool:

- **`test_windows.py`** / **`test_doors.py`** — `WindowParts`/`DoorParts`
  geometry generation (frame + glass, hinged sashes, **sliding uses a slide
  mode not an arc**, double sashes, round = two concentric circles), plus the
  edit round-trip below.
- **`test_stairs.py`** — the edit round-trip, including the non-trivial
  break/turn reconstruction in `_loadFromObject`.

## The edit round-trip

These tests drive each panel's real `_loadFromObject()` then `_collect()`
against fake widgets (the panel is built with `object.__new__`, so Qt setup is
skipped). They assert that:

1. opening a fully-configured object for edit reproduces **every** field, and
2. changing **one** field leaves all the others unchanged.

Fields with no native property (operation, frame width/depth, swing, position,
style, shape) must survive an edit. Windows and doors persist a JSON spec on
the object; stairs round-trips through native ArchStairs properties.

Geometry that needs the real kernel (the actual solid built by
`windowsplus_object` / `doorsplus_object`) is out of scope here — verify that
in FreeCAD.

## Running

```sh
python3 -m pytest
```

If the system Python lacks `pytest`, use a virtualenv (any Python 3.8+):

```sh
python3 -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python -m pytest
```

FreeCAD's bundled Python works too, since the fakes shadow the real modules
during the test run.
