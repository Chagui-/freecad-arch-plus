# Tests

Unit tests for the pure logic in the ArchPlus GUI modules — no FreeCAD install
required. `conftest.py` lives at the repo root and injects lightweight fakes
for `FreeCAD`, `FreeCADGui`, `PySide`, `Part` and `Sketcher` into
`sys.modules`, so the modules import and the geometry builders run against a
stub kernel. It sits at the root rather than inside any one tool's tests
because pytest only applies a `conftest.py` to tests beneath its own
directory — the root is the one place above both `tools/` and `common/` that
reaches every tool's test suite.

Tests live beside the tool they cover rather than in a central tree, but the
framing is still one test file per tool:

- **`tools/windows/tests/test_windows.py`** / **`tools/doors/tests/test_doors.py`** —
  `WindowParts`/`DoorParts` geometry generation (frame + glass, hinged
  sashes, **sliding uses a slide mode not an arc**, double sashes, round =
  two concentric circles), plus the edit round-trip below.
- **`tools/stairs/tests/test_stairs.py`** — the edit round-trip, including the
  non-trivial break/turn reconstruction in `_loadFromObject`.

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
`windows.object` / `doors.object`) is out of scope here — verify that
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
