# Tests

Unit tests for the pure logic in the ArchPlus GUI modules — no FreeCAD install
required. `conftest.py` lives at the repo root and injects lightweight fakes
for `FreeCAD`, `FreeCADGui`, `PySide`, `Part` and `Sketcher` into
`sys.modules`, so the modules import and the geometry builders run against a
stub kernel.

It sits at the repo root, not inside `archplus/`, for two reasons that both
have to hold at once. pytest only applies a `conftest.py` to tests beneath its
own directory, so it has to be at or above `archplus/` to reach every tool's
suite. And it puts its own directory on `sys.path`, which must be the *add-on
root* — the same directory FreeCAD adds — so that `archplus` resolves as a
package and `import archplus.tools.doors.gui` works. Moving it down into
`archplus/` would satisfy the first requirement and break the second.

Tests live beside the tool they cover rather than in a central tree, but the
framing is still one test file per tool:

- **`archplus/tools/windows/tests/test_windows.py`** / **`archplus/tools/doors/tests/test_doors.py`** —
  `WindowParts`/`DoorParts` geometry generation (frame + glass, hinged
  sashes, **sliding uses a slide mode not an arc**, double sashes, round =
  two concentric circles), plus the edit round-trip below.
- **`archplus/tools/stairs/tests/test_stairs.py`** — the edit round-trip, including the
  non-trivial break/turn reconstruction in `_loadFromObject`.

Alongside the per-tool suites, `archplus/common/tests/` covers the shared helpers used
across tools:

- **`test_spec.py`** — the shared spec-persistence helpers.
- **`test_widgets.py`** — the shared Qt widget helpers.
- **`test_geometry.py`** — the shared sketch-building helpers.
- **`test_lazy_imports.py`** — an AST guard ensuring `Part`, `Sketcher`,
  `ArchComponent`, `Arch`, `Draft` and `archplus.common.geometry` are never imported at
  module scope in the GUI modules.

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
`archplus.tools.windows.object` / `archplus.tools.doors.object`) is out of scope here — verify
that in FreeCAD.

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

On this development machine the `venv` route above FAILS outright — there is
no `python3.14-venv` package installed, so `python3 -m venv .venv` aborts
before pytest is ever invoked. What actually works here is `uv`, which
provisions its own interpreter and dependencies without touching the system
Python or needing a venv package at all:

```sh
uv run --no-project --with pytest python -m pytest -q
```
