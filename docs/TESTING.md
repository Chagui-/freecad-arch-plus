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

The parts library panel (`archplus/tools/partslib/gui.py`) follows the same
split in intent, but there is no widget test in it: `conftest.py` installs
its Qt/FreeCAD fakes unconditionally, so no test in this suite can construct
a real widget, offscreen or otherwise. What the branch actually did was pull
the panel's logic out into pure functions and test those instead —
`flow_positions`, `preview_plan`, `facet_groups`, `isPristine` /
`hasDerivedFields`, and collection resolution are all genuinely covered by
the `test_partslib_*.py` files. What that leaves with no automated coverage
is narrow but real: `_onChipSelected`'s same-room guard, `_populateChips`'s
retired-room reconciliation, and `detailFamily`'s show/hide. Those three are
covered only by the manual checklist in `docs/PARTS-LIBRARY-VERIFICATION.md`.

The edit panel's form bookkeeping (`loadValues` / `autoNames` / `setField` /
`displayed`) is the exception: it runs against the same minimal field fakes
the existing `_bare_form` ParamForm tests use, so its pinning and derived
styling are unit-tested in `test_partslib_paramform.py`. The edit session
itself — the task panel, the transaction, the live rebuild of the placed
object, Apply/Discard — is a FreeCAD-GUI concern and is covered by
`verify_edit.py` (checks L1-L6).

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
