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
  stairsplus_object.py   (compat shim only — re-exports from stairs/object.py)
  doorsplus_object.py    (compat shim only — re-exports from doors/object.py)
  windowsplus_object.py  (compat shim only — re-exports from windows/object.py)
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
  root, so `Resources/icons/...` paths keep resolving. This applies to all
  three `_gui.py` files (module-level `_DIR`, used for `ICON` and a
  `_refImage`/`_setRefImage` dimension-reference-icon helper) and to
  `stairsplus_object.py`'s `_ViewProviderStairsPlus.getIcon()`, which computes
  `os.path.dirname(__file__)` **inline** inside the method rather than as a
  module constant — same one-level-up fix, just not from a shared `_DIR`
  name. `doorsplus_object.py` and `windowsplus_object.py` need **no** path fix
  at all: their `getIcon()` methods return FreeCAD's built-in `Arch_rc` Qt
  resource paths (`:/icons/Arch_Window_Tree.svg`), not filesystem paths.
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
   tool-local data folder + the `_DIR`/`_ROOT` split). **Done** — merged via
   the `partslib-folder-refactor` branch (this branch); 162/162 tests green;
   manual FreeCAD smoke test confirmed working.
2. Verify: `uv run --with pytest --no-project pytest tests/ -q` green, then
   open FreeCAD and confirm the toolbar/panel/placement still work.
3. Repeat the same recipe for Stairs, Doors, Windows (each is just 2 files
   with no local data folder, so the `_DIR` fix is a single line each — these
   should go fast once the pattern is proven). Continues on this same branch
   rather than a fresh one, per the user's choice.

## Addendum: backward compatibility for Stairs/Doors/Windows (Parts Library did not need this)

Parts Library was new enough (landed 3 commits before this refactor) that no
real saved `.FCStd` documents referenced it, so the pilot didn't need to
address this. Stairs/Doors/Windows are different: they've existed since near
the start of this repo's history, and the user confirmed real project files
exist that place these objects and are still opened/edited.

**The problem:** each tool's `_object.py` defines two classes assigned as a
document object's `Proxy`/`ViewObject.Proxy` (`_StairsPlus` /
`_ViewProviderStairsPlus` for Stairs; `_Window` / `_ViewProviderWindow`,
independently, for both Doors and Windows — same class names, different
modules, since `ArchWindow.py` was copied once per tool per the README).
FreeCAD's `App::PropertyPythonObject` persists a scripted object's Proxy via
Python's standard pickle protocol, which records the class by
**module path + qualified name** (e.g. `stairsplus_object._StairsPlus`), not
by file location. Moving the module breaks that lookup: on reopen, FreeCAD
cannot import `stairsplus_object` (it no longer exists), the Proxy fails to
reconstruct, and that object loses its custom recompute/double-click-to-edit/
icon behavior. The cached `obj.Shape` still renders (FreeCAD persists the
shape itself separately), so nothing looks broken until the user tries to
edit the object — a silent, delayed failure, which is the worst kind for a
backward-compatibility break.

**Decision (confirmed with the user, since real files exist): keep a thin
compatibility shim at each old flat module path.** Each shim's only job is
re-exporting the exact two classes FreeCAD's pickler will ask for, from
their new home:

```python
# stairsplus_object.py (repo root — DO NOT DELETE)
#
# Backward-compatibility shim. Documents saved before the per-tool-folder
# reorganization pickle their Stairs object's Proxy by this exact module
# path ("stairsplus_object._StairsPlus" / "_ViewProviderStairsPlus").
# Python's unpickler resolves the class via plain `getattr(import(module),
# name)`, regardless of that class's own __module__ attribute — so this
# shim only needs to keep existing and keep exposing these two names for
# as long as any such document might still be opened. The real
# implementation lives in stairs/object.py now.
from stairs.object import _StairsPlus, _ViewProviderStairsPlus  # noqa: F401
```

Only `_object.py` needs a shim — `_gui.py` modules hold Command classes
(registered by string name via `FreeCADGui.addCommand`) and Task panel
classes (transient UI, built on demand), neither of which FreeCAD ever
pickles into a document. Doors and Windows each get their own shim
(`doorsplus_object.py` re-exporting from `doors.object`, `windowsplus_object.py`
re-exporting from `windows.object`) — the shared class names (`_Window`,
`_ViewProviderWindow`) stay distinct because they resolve through two
different module names, exactly as they already do today (the two tools'
existing `_Window` classes are already separate classes under separate
module names, before this refactor).

**Cost if this decision is later found wrong:** none expected — this is
strictly additive (three small permanent files, never imported by new code,
only by the unpickler for old documents) and costs nothing at runtime for
anyone opening a post-refactor document. If a shim class's implementation
ever needs to diverge from `stairs/object.py`'s real class for some future
reason, that would be a sign the shim has outlived its purpose and the
compatibility contract needs revisiting — not expected any time soon.
