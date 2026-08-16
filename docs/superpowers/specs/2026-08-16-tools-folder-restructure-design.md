# Tools folder restructure — design

## Goal

Group the four toolbar tools under a single `tools/` package, give each tool its
own `resources/` and `tests/`, and extract the small set of helpers that are
verifiably identical across tools into a new `common/` package.

This supersedes the layout from `2026-08-16-per-tool-folders-design.md`, which
put the four tool packages flat in the repo root.

Two things motivate the change:

- A `common/` package is being added. With a flat root, `doors/`, `windows/`,
  `stairs/`, `partslib/` and `common/` are five sibling packages where one is
  not a tool. `tools/` + `common/` makes that distinction structural.
- Backward-compatibility shims can now be deleted (see Constraints), so the
  root gets smaller rather than larger.

## Constraints

- **FreeCAD adds only the add-on root (`Mod/ArchPlus/`) to `sys.path`**, never
  subfolders. `tools/` and every tool folder must be a real Python package with
  `__init__.py`, resolved by dotted import from that root.
- **Pickled Proxy paths break, and that is accepted.** FreeCAD resolves a saved
  object's Proxy via the module path recorded at save time. Moving the classes
  to `tools.doors.object` invalidates documents that recorded `doors.object`,
  and deleting the root shims invalidates documents that recorded
  `doorsplus_object`. The user has confirmed only one document references this
  add-on and that breaking it is acceptable. **Consequence to expect: that
  document's ArchPlus objects will not resolve on open and must be rebuilt.**
- **Lazy in-function imports are load-bearing.** Every `gui.py` imports its
  sibling `object.py` inside a function, not at module scope, to keep
  `ArchComponent` out of BIM-workbench-init time. This pattern is preserved
  verbatim, and it also dictates the split of `common/` into separate modules
  (see Common extraction).
- **Doors and Windows are intentionally divergent.** Their near-duplication is
  by design, not accident. This restructure extracts only helpers verified
  identical today; it does not introduce a shared base class or unify
  `object.py`.

## Target layout

```
ArchPlus/
  InitGui.py   conftest.py   pytest.ini   README.md   LICENSE
  common/
    __init__.py  widgets.py  spec.py  geometry.py
    tests/  __init__.py  test_widgets.py  test_spec.py  test_geometry.py
  tools/
    __init__.py
    doors/     __init__.py  gui.py  object.py  resources/icons/  tests/test_doors.py
    windows/   __init__.py  gui.py  object.py  resources/icons/  tests/test_windows.py
    stairs/    __init__.py  gui.py  object.py  resources/icons/  tests/test_stairs.py
    partslib/  __init__.py  gui.py  object.py  geometry.py  index.py  manifest.py
               placement.py  theme.py  thumbs.py
               builders/  library/  resources/icons/facets/
               tests/  __init__.py  test_library_content.py
                       test_partslib_geometry.py  test_partslib_index.py
                       test_partslib_manifest.py  test_partslib_placement.py
                       test_partslib_theme.py  test_partslib_thumbs.py
  docs/
    images/    (was Resources/images/)
```

Deleted outright: `doorsplus_object.py`, `windowsplus_object.py`,
`stairsplus_object.py`, the top-level `Resources/` tree, and the top-level
`tests/` directory.

`partslib/library/` stays inside the partslib package, unchanged. It is already
resolved relative to the package directory, so the move does not affect it.

## Resource ownership

Every icon has exactly one consuming tool; nothing is genuinely shared. This is
what makes per-tool `resources/` viable rather than merely tidy.

| Destination | Files |
|---|---|
| `tools/doors/resources/icons/` | `DoorsPlus.svg`, `dimensions_ref_door.svg` |
| `tools/windows/resources/icons/` | `WindowsPlus.svg`, `dimensions_ref_window.svg` |
| `tools/stairs/resources/icons/` | `StairsPlus.svg`, `dimensions_ref_straight.svg`, `dimensions_ref_quarterturn.svg`, `dimensions_ref_halfturn.svg`, `steps_ref.svg` |
| `tools/partslib/resources/icons/` | `PartsLibrary.svg`, `facets/` (32 files) |
| `docs/images/` | `toolbar.jpg`, `stairs_dialog_1.jpg`, `stairs_dialog_2.jpg`, `stairs_quarter_turn.jpg`, `doors_dialog_1.jpg`, `doors_dialog_2.jpg`, `doors_double_swing.jpg` |

The `.jpg` files are README screenshots, never loaded by code, so they belong
with the documentation rather than in a code package.

There is no `common/paths.py`. With resources owned per tool, path resolution
becomes `os.path.join(os.path.dirname(__file__), "resources", "icons", ...)` —
shallower than the current `dirname(dirname(__file__))` form and not worth a
shared abstraction.

## Path and import rewiring

Mechanical, but these specific sites must all be covered:

| Site | Change |
|---|---|
| `doors/gui.py:22`, `windows/gui.py:25`, `stairs/gui.py:17` | `_DIR` drops one `dirname()`; `"Resources"` → `"resources"` |
| `doors/gui.py:24,668`; `windows/gui.py:27,789`; `stairs/gui.py:19,315` | icon paths retarget to the tool's own `resources/icons/` |
| `stairs/object.py:2824` | builds its icon path inline, not from `_DIR` — needs its own edit |
| `partslib/gui.py:29-30,45-46`; `partslib/object.py:22-23,292` | `_ROOT` is deleted; `_FACET_ICON_DIR` and `ICON` resolve from `_DIR` |
| `InitGui.py:39-42` | imports become `tools.stairs.gui`, `tools.doors.gui`, `tools.windows.gui`, `tools.partslib.gui` |
| `tests/partslib/test_library_content.py:24-25,100` | `_ROOT` anchor and the facets-icon path follow the new locations |
| `README.md:416` | prose reference to `Resources/icons/facets/` updated |

`InitGui.py` keeps its closure-variable structure and its `commands` list
unchanged — command names (`ArchPlus_Stairs` and friends) are registered by the
`gui` modules and are not affected by the move.

Relative imports within each tool package (`from . import gui`,
`from .object import ...`) are unaffected, since the package-internal structure
does not change.

## Common extraction

Extract only what was verified identical by AST comparison. Everything else
stays where it is.

**`common/widgets.py`** — used by doors, windows, stairs:

- `_mm(w)`, `_setmm(w, mm)`, `_len(self, default)` — identical across all three;
  the only textual differences are docstrings present in stairs.
- `_refImage(self, name, size)` — identical between doors and windows. Stairs
  splits it into `_refImage` plus `_setRefImage`, because stairs re-targets the
  image when the layout changes. The shared version takes the icon directory as
  a parameter and keeps the `_setRefImage` split, so stairs loses nothing.

**`common/spec.py`** — used by doors and windows:

- `storeSpec(obj, spec)`, `readSpec(obj)` — byte-identical module-level
  functions. The `SPEC_PROP = "ArchPlusSpec"` constant they depend on is also
  identical in both, and moves with them.

**`common/geometry.py`** — used by doors and windows:

- `_rect(p1, p2, p3, p4)`, `_addFrame(...)` — byte-identical *bodies*, but they
  are **closures** nested inside `_makeDoorGeometry` / `_makeWindowGeometry`,
  not module-level functions. Each captures the enclosing scope's sketch object
  `s`. The extracted versions therefore take it as an explicit first parameter:
  `add_rect(s, p1, p2, p3, p4)` and
  `add_frame(s, outer_p1..outer_p4, inner_p1..inner_p4)`. This is the only
  signature change in the extraction; every other helper moves unchanged apart
  from losing its `self`.

Three modules rather than one, deliberately: `widgets.py` pulls in PySide,
`geometry.py` pulls in `Part`/`Sketcher`. A single combined module would make
importing either drag in both, defeating the lazy-import constraint above.

**Deliberately not extracted.** These share a name across doors and windows but
differ in body, and the differences are the designed divergence — opening
semantics and sill-versus-floor datum:

`_openingModeFor`, `_operationIsSliding`, `_hostBaseZ`, `_place`, `_move`.

`_openingModeInv` *is* identical, but it is the inverse of `_openingModeFor`,
which is not. Splitting a matched pair across two locations would be worse than
leaving both in place, so it stays with its partner.

## Test harness

`tests/conftest.py` moves to a repo-root `conftest.py`, contents unchanged.
This is forced rather than stylistic: pytest applies a conftest only to tests
beneath its own directory, so the FreeCAD / FreeCADGui / PySide / Part /
Sketcher fakes would not reach `tools/*/tests/` from the current location.

The `_ROOT` computation inside that conftest changes from
`dirname(dirname(abspath(__file__)))` to `dirname(abspath(__file__))`, since the
file is now one level higher.

`pytest.ini` drops both `testpaths` and `pythonpath` and relies on rootdir
discovery, so tests are collected from `tools/` and `common/` alike.

Test file contents are relocated, not rewritten, except for the import paths
they reference and the two path anchors in `test_library_content.py`. Keeping
the assertions untouched is what makes the suite a meaningful check on step 1.

New tests are written only for the three `common/` modules, covering the
extracted helpers directly.

## Implementation sequence

**Step 1 — relocation.** All moves, path fixes, and import rewiring. No logic
changes. Shims and `Resources/` deleted.

Acceptance:
- The existing test suite passes with assertions unchanged.
- ArchPlus loads in FreeCAD and all four toolbar buttons appear and open their
  dialogs. **This requires a manual check by the user; it cannot be automated
  from the development environment.**

**Step 2 — extraction.** Create `common/`, move the verified-identical helpers,
convert the original call sites to delegations, add tests for `common/`.

Acceptance:
- Full suite passes.
- No behavior change in any tool.

The two steps stay separate commits. Combining them would bury roughly 70 lines
of logic change inside a large volume of path churn, making the diff
unreviewable.

## Out of scope

**The `rotdata` / `slidevec` leak in `doors/object.py:402-403`.** Those two
variables are initialized once before the per-leaf loop, whereas
`windows/object.py:407-408` resets them inside it. Both are applied per leaf at
`doors/object.py:622-625`, so any door part following an opening leaf without
its own opening mode inherits the previous leaf's rotation and slide.

This is a genuine bug, but it is unrelated to the restructure and deserves its
own commit with its own regression test. It is recorded here so it is not lost.

**Unifying `doors/object.py` and `windows/object.py`.** They are ~1790 lines
each and differ by fewer than 100 diff lines, but the divergence is intentional
and expected to widen. Out of scope by design, not by oversight.
