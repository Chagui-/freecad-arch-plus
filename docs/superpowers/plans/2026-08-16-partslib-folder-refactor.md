# Parts Library Folder Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move all 8 root-level `partslib_*.py` modules, `partslib_builders/`
and `library/` into one `partslib/` package, with zero behavior change —
same `ArchPlus_PartsLibrary` command, same toolbar, same tests (relocated,
not rewritten). This is the pilot tool for the larger "one folder per tool"
reorganization; Stairs/Doors/Windows follow the same recipe afterward.

**Architecture:** Pure mechanical move + import rewiring. Every cross-module
`import partslib_X` (module-scope or lazy in-function) becomes `from . import
X as partslib_X` — same local name, so nothing below the import line changes.
`InitGui.py` and `tests/*.py` switch from bare `import partslib_gui` /
`import partslib_geometry as pg` to package-qualified equivalents. Two path
constants (`Resources/` lookups, `library/`-relative lookups) need a
`_DIR`/`_ROOT` split since they move different distances from their own file.

**Tech Stack:** Python 3, pytest 9.1.1 (via `uv run --with pytest
--no-project`), FreeCAD 1.1 (BIM/Arch workbench) for the manual smoke test.

**Spec:** `docs/superpowers/specs/2026-08-16-per-tool-folders-design.md`

## Global Constraints

- No behavior change: command names, toolbar entries, and panel behavior are
  identical before and after.
- Every lazy in-function `import partslib_X` keeps its local name
  `partslib_X` after rewiring (`from . import X as partslib_X`), so call
  sites below the import are never touched.
- `Resources/` stays shared at repo root; only `library/` moves with
  Parts Library into `partslib/library/`.
- Don't touch `docs/superpowers/plans/2026-08-15-parts-library.md`,
  `docs/superpowers/specs/2026-08-15-parts-library-design.md`, or
  `docs/PARTS-LIBRARY-VERIFICATION.md` — dated historical records, not living
  docs. Only `README.md` gets path references updated.
- `tests/README.md` is not touched in this pass (it documents only the
  Stairs/Doors/Windows test files, which don't move yet).

---

### Task 1: Move Parts Library modules/data into `partslib/`, fix intra-package imports and path constants

**Files:**
- Create: `partslib/__init__.py`
- Move: `partslib_gui.py` → `partslib/gui.py`
- Move: `partslib_object.py` → `partslib/object.py`
- Move: `partslib_geometry.py` → `partslib/geometry.py`
- Move: `partslib_index.py` → `partslib/index.py`
- Move: `partslib_manifest.py` → `partslib/manifest.py`
- Move: `partslib_placement.py` → `partslib/placement.py`
- Move: `partslib_theme.py` → `partslib/theme.py`
- Move: `partslib_thumbs.py` → `partslib/thumbs.py`
- Move: `partslib_builders/` → `partslib/builders/` (directory, contents unchanged)
- Move: `library/` → `partslib/library/` (directory, contents unchanged)

**Interfaces:**
- Produces: the `partslib` package, importable as `partslib.gui`,
  `partslib.object`, `partslib.geometry`, `partslib.index`,
  `partslib.manifest`, `partslib.placement`, `partslib.theme`,
  `partslib.thumbs`, `partslib.builders.*`. `partslib.object.LIBRARY_DIR`
  keeps pointing at the real bundled library (now `partslib/library/`).
  Task 2 (tests) and Task 3 (`InitGui.py`) consume these names.

- [ ] **Step 1: Baseline — confirm the current suite is green before moving anything**

Run: `uv run --with pytest --no-project pytest tests/ -q`
Expected: PASS (all tests green — this is the safety net; note the pass
count so Task 2's rerun can be compared against it).

- [ ] **Step 2: Move the files and directories**

```bash
mkdir -p partslib
touch partslib/__init__.py
git mv partslib_gui.py partslib/gui.py
git mv partslib_object.py partslib/object.py
git mv partslib_geometry.py partslib/geometry.py
git mv partslib_index.py partslib/index.py
git mv partslib_manifest.py partslib/manifest.py
git mv partslib_placement.py partslib/placement.py
git mv partslib_theme.py partslib/theme.py
git mv partslib_thumbs.py partslib/thumbs.py
git mv partslib_builders partslib/builders
git mv library partslib/library
git add partslib/__init__.py
```

- [ ] **Step 3: Fix `partslib/index.py`'s import**

Change:
```python
import partslib_manifest as pm
```
to:
```python
from . import manifest as pm
```

- [ ] **Step 4: Fix `partslib/geometry.py`'s imports and builder package name**

Remove the now-unnecessary `sys.path` hack (lines near the top):
```python
_DIR = os.path.dirname(__file__)
if _DIR not in sys.path:
    sys.path.append(_DIR)

import partslib_manifest
```
becomes:
```python
from . import manifest as partslib_manifest
```
Also remove the top-of-file `import sys` — this file's only use of `sys` was
the `sys.path` hack just deleted (verified: no other `sys.` reference in the
file). Leave `import os` alone; it's used throughout for `os.path.join`/
`os.path.exists`/etc.

Change:
```python
BUILDER_PACKAGE = "partslib_builders"
```
to:
```python
BUILDER_PACKAGE = "partslib.builders"
```

- [ ] **Step 5: Fix `partslib/object.py`'s imports and split `_DIR`/`_ROOT`**

Change:
```python
_DIR = os.path.dirname(__file__)
if _DIR not in sys.path:
    sys.path.append(_DIR)

import partslib_geometry
import partslib_index
import partslib_manifest
```
to:
```python
_DIR = os.path.dirname(__file__)     # partslib/ itself
_ROOT = os.path.dirname(_DIR)        # repo root, for the shared Resources/

from . import geometry as partslib_geometry
from . import index as partslib_index
from . import manifest as partslib_manifest
```

`LIBRARY_DIR = os.path.join(_DIR, "library")` stays exactly as-is — `library/`
moved to `partslib/library/`, a sibling of this file, so `_DIR` (unchanged
meaning: this file's own directory) still resolves it correctly.

Also remove the top-of-file `import sys` — this file's only use of `sys` was
the `sys.path` hack just deleted (verified: no other `sys.` reference in the
file). Leave `import os` alone.

In `_ViewProviderLibraryPart.getIcon()`, change:
```python
        return os.path.join(_DIR, "Resources", "icons", "PartsLibrary.svg")
```
to:
```python
        return os.path.join(_ROOT, "Resources", "icons", "PartsLibrary.svg")
```

- [ ] **Step 6: Fix `partslib/gui.py`'s imports and split `_DIR`/`_ROOT`**

Change:
```python
_DIR = os.path.dirname(__file__)
if _DIR not in sys.path:
    sys.path.append(_DIR)

import partslib_index
import partslib_theme
import partslib_thumbs
```
to:
```python
_DIR = os.path.dirname(__file__)     # partslib/ itself
_ROOT = os.path.dirname(_DIR)        # repo root, for the shared Resources/

from . import index as partslib_index
from . import theme as partslib_theme
from . import thumbs as partslib_thumbs
```

Change:
```python
ICON = os.path.join(_DIR, "Resources", "icons", "PartsLibrary.svg")
_FACET_ICON_DIR = os.path.join(_DIR, "Resources", "icons", "facets")
```
to:
```python
ICON = os.path.join(_ROOT, "Resources", "icons", "PartsLibrary.svg")
_FACET_ICON_DIR = os.path.join(_ROOT, "Resources", "icons", "facets")
```

Also remove the top-of-file `import sys` — this file's only use of `sys` was
the `sys.path` hack just deleted (verified: no other `sys.` reference in the
file). Leave `import os` alone.

Then fix every lazy in-function import in this same file — each becomes
`from . import <module> as partslib_<module>`, same local name, nothing else
on the line or below it changes:

| Line (before move) | Before | After |
| --- | --- | --- |
| 478 | `import partslib_object` | `from . import object as partslib_object` |
| 480 | `import partslib_geometry` | `from . import geometry as partslib_geometry` |
| 550 | `import partslib_object` | `from . import object as partslib_object` |
| 921 | `import partslib_manifest` | `from . import manifest as partslib_manifest` |
| 1062 | `import partslib_manifest` | `from . import manifest as partslib_manifest` |
| 1073 | `import partslib_geometry` | `from . import geometry as partslib_geometry` |
| 1258 | `import partslib_geometry` | `from . import geometry as partslib_geometry` |
| 1259 | `import partslib_object` | `from . import object as partslib_object` |
| 1260 | `import partslib_placement` | `from . import placement as partslib_placement` |

(Line numbers are from the pre-move file for reference; find each by its
distinctive surrounding function — `refresh()`, `_fillCategoriesEmptyState()`,
`_thumbnailForGrid()`-ish helper, `_resolvedSelection()`, `_refreshPreview()`,
and `_onPlace()` — rather than by number, since the move shifts nothing but
Step 2 already ran.)

- [ ] **Step 7: Confirm `partslib/placement.py`, `partslib/theme.py`, `partslib/thumbs.py`, `partslib/manifest.py` need no import changes**

These four have no cross-module `partslib_*` imports (verified: `manifest.py`
only imports `copy`/`json`/`os`/`re`; `placement.py` and `theme.py` import
nothing from `partslib`; `thumbs.py` imports only `os`/`time` at module scope,
with a lazy `import partslib_geometry` inside one function — fix that one
the same way as Step 6's table: `from . import geometry as partslib_geometry`).

- [ ] **Step 8: Smoke-test the package imports without FreeCAD**

Run:
```bash
PYTHONPATH=. python3 -c "import partslib.manifest, partslib.index, partslib.geometry, partslib.placement, partslib.theme, partslib.thumbs; print('ok')"
```
Expected: prints `ok`. (`partslib.object` and `partslib.gui` import
`FreeCAD`/`ArchComponent`/`PySide` at module scope and are expected to fail
here — that's normal and matches their pre-move behavior; they're exercised
by the fake-module test harness in Task 2 instead.)

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: move Parts Library modules into partslib/ package"
```

---

### Task 2: Update tests to the new package layout, add `pythonpath` to pytest.ini, fix `test_library_content.py`'s path math

**Files:**
- Move: `tests/test_library_content.py` → `tests/partslib/test_library_content.py`
- Move: `tests/test_partslib_geometry.py` → `tests/partslib/test_partslib_geometry.py`
- Move: `tests/test_partslib_index.py` → `tests/partslib/test_partslib_index.py`
- Move: `tests/test_partslib_manifest.py` → `tests/partslib/test_partslib_manifest.py`
- Move: `tests/test_partslib_placement.py` → `tests/partslib/test_partslib_placement.py`
- Move: `tests/test_partslib_theme.py` → `tests/partslib/test_partslib_theme.py`
- Move: `tests/test_partslib_thumbs.py` → `tests/partslib/test_partslib_thumbs.py`
- Modify: `pytest.ini`

**Interfaces:**
- Consumes: `partslib.manifest`, `partslib.index`, `partslib.geometry`,
  `partslib.placement`, `partslib.theme`, `partslib.thumbs` from Task 1.
- Consumes: `tests/conftest.py`'s `from conftest import FakeObj, ...`-style
  plain module import, unchanged — fixed via `pythonpath = tests` below, not
  by editing `conftest.py` or the doors/stairs/windows tests that use it.

- [ ] **Step 1: Move the test files**

```bash
mkdir -p tests/partslib
git mv tests/test_library_content.py tests/partslib/test_library_content.py
git mv tests/test_partslib_geometry.py tests/partslib/test_partslib_geometry.py
git mv tests/test_partslib_index.py tests/partslib/test_partslib_index.py
git mv tests/test_partslib_manifest.py tests/partslib/test_partslib_manifest.py
git mv tests/test_partslib_placement.py tests/partslib/test_partslib_placement.py
git mv tests/test_partslib_theme.py tests/partslib/test_partslib_theme.py
git mv tests/test_partslib_thumbs.py tests/partslib/test_partslib_thumbs.py
```

- [ ] **Step 2: Fix each moved test file's import line**

`tests/partslib/test_partslib_geometry.py`:
```python
import partslib_geometry as pg
```
→
```python
from partslib import geometry as pg
```
(Also update the deeper-dotting example string on the "package prefix not
allowed" test — cosmetic, keeps it honest about the real package name:
`"partslib_builders.asset.single"` → `"partslib.builders.asset.single"`. The
test only checks that a 3-part dotted symbol is rejected, so this doesn't
change what's being verified.)

`tests/partslib/test_partslib_index.py`:
```python
import partslib_index as px
```
→
```python
from partslib import index as px
```

`tests/partslib/test_partslib_manifest.py`:
```python
import partslib_manifest as pm
```
→
```python
from partslib import manifest as pm
```

`tests/partslib/test_partslib_placement.py`:
```python
import partslib_placement as pp
```
→
```python
from partslib import placement as pp
```

`tests/partslib/test_partslib_theme.py`:
```python
import partslib_theme as pt
```
→
```python
from partslib import theme as pt
```
(This file also asserts, via `ast`/`inspect`, that `partslib_theme` has no
module-scope FreeCAD import — check its assertion message still makes sense
with the new name; update the string `"module-scope import of %r in
partslib_theme"` to `"module-scope import of %r in partslib.theme"` if it
names the module literally.)

`tests/partslib/test_partslib_thumbs.py`:
```python
import partslib_geometry as pg
import partslib_thumbs as pt
```
→
```python
from partslib import geometry as pg
from partslib import thumbs as pt
```

`tests/partslib/test_library_content.py` — imports:
```python
import partslib_geometry
import partslib_index
import partslib_manifest
```
→
```python
from partslib import geometry as partslib_geometry
from partslib import index as partslib_index
from partslib import manifest as partslib_manifest
```
and the one lazy import inside `test_every_placement_host_is_a_known_host`:
```python
    import partslib_placement
```
→
```python
    from partslib import placement as partslib_placement
```

- [ ] **Step 3: Fix `test_library_content.py`'s `LIBRARY_DIR` and icon-dir path math**

Change:
```python
LIBRARY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "library")
```
to:
```python
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIBRARY_DIR = os.path.join(_ROOT, "partslib", "library")
```

(Three `dirname()` calls now, not two: the file moved from `tests/` to
`tests/partslib/`, one level deeper, so reaching the repo root needs one more
step up. `library/` itself is `partslib/library`, not `library`.)

Change, in `test_every_facet_icon_referenced_exists_on_disk`:
```python
    icon_dir = os.path.join(os.path.dirname(LIBRARY_DIR),
                            "Resources", "icons", "facets")
```
to:
```python
    icon_dir = os.path.join(_ROOT, "Resources", "icons", "facets")
```

(Do **not** just add another `dirname()` to the old expression — `dirname(LIBRARY_DIR)`
now gives `_ROOT/partslib`, and `Resources/` lives at `_ROOT`, not
`_ROOT/partslib`. `Resources/` and `partslib/library/` no longer share a
parent, so each path must be computed independently from `_ROOT`.)

- [ ] **Step 4: Let `tests/` subfolders resolve `conftest.py` by plain import**

In `pytest.ini`, add a `pythonpath` line:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
pythonpath = tests
```

- [ ] **Step 5: Run the full suite and confirm it's green**

Run: `uv run --with pytest --no-project pytest tests/ -q`
Expected: PASS — same pass count as Task 1 Step 1's baseline (Stairs/Doors/
Windows tests are untouched and still pass; Parts Library tests now import
through the `partslib` package instead of flat names).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "test: relocate Parts Library tests under tests/partslib/, fix conftest resolution"
```

---

### Task 3: Point `InitGui.py` at the new package

**Files:**
- Modify: `InitGui.py`

**Interfaces:**
- Consumes: `partslib.gui` from Task 1 (import triggers `ArchPlus_PartsLibrary`
  command registration as a side effect, same as before).

- [ ] **Step 1: Update the import**

Change:
```python
        import stairsplus_gui   # noqa: F401
        import doorsplus_gui    # noqa: F401
        import windowsplus_gui  # noqa: F401
        import partslib_gui     # noqa: F401
```
to (only the Parts Library line changes in this pilot — the other three move
in the follow-up pass):
```python
        import stairsplus_gui   # noqa: F401
        import doorsplus_gui    # noqa: F401
        import windowsplus_gui  # noqa: F401
        import partslib.gui     # noqa: F401
```

- [ ] **Step 2: Syntax-check without FreeCAD**

Run: `python3 -m py_compile InitGui.py`
Expected: exits with no output (FreeCAD itself isn't importable here, but
this confirms the file parses; the real check is the manual FreeCAD smoke
test in Task 5).

- [ ] **Step 3: Commit**

```bash
git add InitGui.py
git commit -m "refactor: InitGui.py imports partslib.gui instead of partslib_gui"
```

---

### Task 4: Update README.md's `library/` and `partslib_builders/` path references

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the "Adding parts to the library" section's paths**

Every reference to a root-level `library/...` path becomes `partslib/
library/...`. Specifically, change each of these occurrences:

- `` alongside the faceted vocabulary (`library/facets.json`) and the `` →
  `` alongside the faceted vocabulary (`partslib/library/facets.json`) and the ``
- `` Add further part folders under `library/` (each with its own `part.json` `` →
  `` Add further part folders under `partslib/library/` (each with its own `part.json` ``
- `` A part is a folder under `library/` containing a `part.json` manifest. `` →
  `` A part is a folder under `partslib/library/` containing a `part.json` manifest. ``
- `` `library/furniture/my-stool/part.json`: `` →
  `` `partslib/library/furniture/my-stool/part.json`: ``
- `` - Every facet value must already exist in `library/facets.json` — an unknown `` →
  `` - Every facet value must already exist in `partslib/library/facets.json` — an unknown ``
- ```` library/sanitary/geberit-icon/ ```` (code block path) →
  ```` partslib/library/sanitary/geberit-icon/ ````
- `` So in practice you set it **once per element** in `library/facets.json` and `` →
  `` So in practice you set it **once per element** in `partslib/library/facets.json` and ``
- `` to `library/facets.json` *and* drop a matching 24×24 line-art SVG into `` →
  `` to `partslib/library/facets.json` *and* drop a matching 24×24 line-art SVG into ``

- [ ] **Step 2: Update the `partslib_builders/` references in the builder-writing section**

Change:
```
inside `partslib_builders/`. A manifest can never name a path or an import
```
to:
```
inside `partslib/builders/`. A manifest can never name a path or an import
```

Change the example file header comment:
```python
# partslib_builders/furniture.py
```
to:
```python
# partslib/builders/furniture.py
```

- [ ] **Step 3: Verify no stale root-level `library/` references remain**

Run: `grep -n "library/" README.md`
Expected: every remaining match reads `partslib/library/...`, not a bare
`library/...`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update README paths for partslib/library and partslib/builders"
```

---

### Task 5: Full verification (no code changes)

**Files:** none modified — this task only runs checks.

- [ ] **Step 1: Run the full automated suite one more time**

Run: `uv run --with pytest --no-project pytest tests/ -q`
Expected: PASS, same count as Task 1/Task 2's runs.

- [ ] **Step 2: Manual smoke test in FreeCAD**

Open FreeCAD 1.1, switch to the **BIM** workbench, and confirm:
1. The **ArchPlus** toolbar appears with all four tools, including the
   Parts Library icon (no console errors about a missing `partslib_gui`
   module).
2. Click **Parts Library** — the dock opens, the category grid populates
   (not the "nothing here yet" empty state).
3. Group by Room/Function/Element, and type in the search box — results
   update.
4. Select a part, confirm the preview and `W × D × H` readout render.
5. Click **Place**, click a floor or wall face — a part is inserted at the
   correct height/orientation.
6. Right-click the placed part → **Reload from library** — it rebuilds
   without error.

If anything in this checklist fails, that's a signal to stop and debug
before starting the Stairs/Doors/Windows follow-up pass — don't proceed on
a broken pilot.
