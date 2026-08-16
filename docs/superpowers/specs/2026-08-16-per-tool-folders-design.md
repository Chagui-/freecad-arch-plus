# Per-tool folders — design

## Goal

ArchPlus has grown from one tool to four (Stairs, Doors, Windows, Parts
Library), and Parts Library alone is already 8 root-level modules plus its own
`partslib_builders/` subpackage. Everything still lives flat in the repo root.
This reorganizes the codebase into one folder per tool, with no behavior
change: same commands, same toolbar, same tests (relocated, not rewritten).

## Constraints

- FreeCAD adds only the add-on's root folder (`Mod/ArchPlus/`) to `sys.path`,
  never subfolders. Every tool folder must therefore be a real Python package
  (`__init__.py`) so it resolves via a dotted import from that root.
- Every `*_gui.py` does lazy, in-function imports of its sibling `*_object.py`
  (e.g. `import stairsplus_object` inside a method, not at module scope) to
  avoid pulling in `ArchComponent` at BIM-workbench-init time. This pattern is
  load-bearing (see the comment in `partslib_gui.py` above `refresh()`) and
  must be preserved, just rewritten as a package-relative import.
- Every module computes `_DIR = os.path.dirname(__file__)`, which today *is*
  the repo root, to locate the shared `Resources/` folder. Moving a file one
  level down breaks that unless the path is adjusted.

## Target layout

```
ArchPlus/
  InitGui.py
  stairs/    __init__.py  gui.py  object.py
  doors/     __init__.py  gui.py  object.py
  windows/   __init__.py  gui.py  object.py
  partslib/
    __init__.py
    gui.py  object.py  geometry.py  index.py  manifest.py  placement.py
    theme.py  thumbs.py
    builders/   (was partslib_builders/, contents unchanged)
    library/    (was root-level library/ — facets.json + part folders)
  Resources/   (unchanged — shared across all tools)
  tests/
    conftest.py   (unchanged home — shared fakes used by all tools)
    stairs/test_stairs.py
    doors/test_doors.py
    windows/test_windows.py
    partslib/test_library_content.py, test_partslib_geometry.py,
             test_partslib_index.py, test_partslib_manifest.py,
             test_partslib_placement.py, test_partslib_theme.py,
             test_partslib_thumbs.py
```

`library/` moves inside `partslib/` rather than staying at root: nothing
outside Parts Library touches it, so keeping it separate would leave the one
tool that most needs consolidating still split across two top-level
locations. `Resources/` stays shared at root since all four tools use it.

## Import wiring rules

Three call-site shapes change, each mechanically, aliasing preserved so
downstream references in the same file don't need touching:

1. **`InitGui.py`**: `import stairsplus_gui` → `import stairs.gui` (the
   registration side-effect still fires on import).
2. **Lazy in-function imports**: `import stairsplus_object` (inside a method
   body) → `from . import object as stairsplus_object`. The local name stays
   the same, so every `stairsplus_object.X` reference below the import is
   untouched.
3. **`tests/*.py`**: `import stairsplus_gui as sg` → `from stairs import gui
   as sg`. Same alias, so test bodies are untouched.

`partslib_geometry.py`'s `BUILDER_PACKAGE = "partslib_builders"` (used with
`importlib.import_module("%s.%s" % (BUILDER_PACKAGE, module_name))`) becomes
`"partslib.builders"` — an absolute dotted import, unaffected by which module
calls it.

## The `_DIR` / resource-path rule

- **Stairs/Doors/Windows** (no tool-local data folder): `_DIR =
  os.path.dirname(__file__)` becomes `_DIR =
  os.path.dirname(os.path.dirname(__file__))` — one level up, back to repo
  root, so `Resources/icons/...` paths keep resolving.
- **Parts Library** (has a tool-local data folder, `library/`, moving
  *with* it): needs **two** separate bases, because `Resources/` (shared,
  stays at root) and `library/` (tool-local, moves into `partslib/`) are no
  longer the same number of levels up from `partslib/*.py`:
  ```python
  _DIR = os.path.dirname(__file__)        # partslib/ itself
  _ROOT = os.path.dirname(_DIR)           # repo root
  ...
  LIBRARY_DIR = os.path.join(_DIR, "library")               # unchanged expression
  ICON = os.path.join(_ROOT, "Resources", "icons", "PartsLibrary.svg")  # was _DIR
  ```
  This applies to `partslib/object.py` (`LIBRARY_DIR`, and `getIcon()`'s
  `Resources` path) and `partslib/gui.py` (`ICON`, `_FACET_ICON_DIR`).
- The `if _DIR not in sys.path: sys.path.append(_DIR)` lines that ride along
  with every `_DIR` today become dead weight once imports are
  package-qualified (nothing needs `_DIR` on `sys.path` to resolve a relative
  import) — drop them.

## Tests + conftest

Nesting tests under `tests/<tool>/` means pytest's default import mode would
insert each subfolder — not `tests/` — onto `sys.path` for that file, breaking
the existing `from conftest import FakeObj, ...` line in
`test_doors.py`/`test_stairs.py`/`test_windows.py`. Fix: add `pythonpath =
tests` to `pytest.ini` (native option since pytest 7; this repo runs pytest
9.1.1). `from conftest import ...` then needs no changes anywhere.

`tests/partslib/test_library_content.py` computes `LIBRARY_DIR` and an
icon directory from `__file__`. Both need recomputing, and **not** by just
adding one more `dirname()` call to the old formula — `Resources/` and
`library/` no longer share a parent once `library/` nests under `partslib/`,
so the old `icon_dir = os.path.join(os.path.dirname(LIBRARY_DIR),
"Resources", ...)` trick (deriving one path from the other) breaks. Compute
each independently from the repo root:
```python
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIBRARY_DIR = os.path.join(_ROOT, "partslib", "library")
...
icon_dir = os.path.join(_ROOT, "Resources", "icons", "facets")  # was derived from LIBRARY_DIR
```

## Non-goals

- No behavior change: same `ArchPlus_*` command names, same toolbar, same
  panels.
- No change to `Resources/` location or contents.
- No edits to historical docs (`docs/superpowers/plans/2026-08-15-parts-library.md`,
  `docs/superpowers/specs/2026-08-15-parts-library-design.md`,
  `docs/PARTS-LIBRARY-VERIFICATION.md`) — they're dated records of what was
  built at the time, not living documentation. Only `README.md` (which tells
  contributors where to add new parts) gets its `library/...` and
  `partslib_builders/...` path references updated.
- `tests/README.md` isn't touched by the Parts Library pilot — it documents
  only the Stairs/Doors/Windows test files, which don't move in this pass.

## Rollout order

1. **Parts Library** (pilot — hardest case: 8 modules + a subpackage + a
   tool-local data folder + the `_DIR`/`_ROOT` split).
2. Verify: `uv run --with pytest --no-project pytest tests/ -q` green, then
   open FreeCAD and confirm the toolbar/panel/placement still work.
3. Repeat the same recipe for Stairs, Doors, Windows (each is just 2 files
   with no local data folder, so the `_DIR` fix is a single line each — these
   should go fast once the pattern is proven).
