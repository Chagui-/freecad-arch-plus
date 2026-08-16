# Tools Folder Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Group ArchPlus's four toolbar tools under a `tools/` package — each owning its `resources/` and `tests/` — and extract the verifiably-identical helpers into a new `common/` package.

**Architecture:** Two phases. Tasks 1-6 are a pure relocation: files move, path constants and imports are rewired, no logic changes; the untouched test suite is the check. Tasks 7-9 extract shared helpers behind TDD, converting the original definitions into thin delegations so every existing call site and test keeps working.

**Tech Stack:** Python 3.11/3.14, pytest 9.x, FreeCAD 1.1 add-on (PySide/Qt, Part, Sketcher, ArchComponent).

**Spec:** `docs/superpowers/specs/2026-08-16-tools-folder-restructure-design.md`

## Global Constraints

- **The test suite must report exactly `162 passed` after every task.** That is the current baseline. Tasks 1-6 change no assertions, so any deviation is a regression. Tasks 7-9 add tests, so the count rises — each task states its own expected number.
- **pytest is not on `PATH` in this WSL environment.** Create the venv once, then use it for every `pytest` command in this plan:
  ```bash
  python3.14 -m venv /tmp/archplus-venv && /tmp/archplus-venv/bin/pip -q install pytest
  ```
  Every `pytest -q` below means `/tmp/archplus-venv/bin/pytest -q`, run from the repo root.
- **FreeCAD adds only the add-on root (`Mod/ArchPlus/`) to `sys.path`.** `tools/` and every tool folder must contain `__init__.py`. Existing `__init__.py` files in this repo are empty — keep new ones empty too.
- **Lazy in-function imports are load-bearing.** Every `gui.py` imports its sibling `object.py`, and `Part`/`Sketcher`, *inside functions* rather than at module scope, so `ArchComponent` is not pulled in during BIM workbench `Initialize()`. Never hoist such an import to module scope. This directly dictates where `common.geometry` may be imported (Task 9).
- **Doors and Windows are intentionally divergent.** Do not unify `object.py`, and do not extract any helper this plan does not name.
- **Use `git mv`** for every relocation so history follows the files.
- **Pickled Proxy paths break by accepted decision.** The user has one document referencing this add-on and has accepted that its ArchPlus objects will not resolve after this work. Do not add compatibility shims.

---

### Task 1: Move the test harness to the repo root

Prerequisite for every later task: once tests live under `tools/*/tests/`, a conftest inside `tests/` can no longer reach them, because pytest applies a conftest only to tests beneath its own directory.

**Files:**
- Move: `tests/conftest.py` → `conftest.py`
- Modify: `conftest.py:19` (the `_ROOT` computation)
- Modify: `pytest.ini`

**Interfaces:**
- Consumes: nothing.
- Produces: a repo-root `conftest.py` exporting the fixtures and fakes every later task relies on — `FakeObj`, `FakeCombo`, `FakeNum`, `FakeCheck`, `_FakeSketch`, `quantity(value)`, `fake_base(z, geometry)`, and the `fake_obj` fixture.

- [ ] **Step 1: Confirm the baseline before changing anything**

Run: `pytest -q`
Expected: `162 passed`

- [ ] **Step 2: Move the conftest to the root**

```bash
git mv tests/conftest.py conftest.py
```

- [ ] **Step 3: Fix the `_ROOT` computation**

The file sits one level higher now, so it needs one fewer `dirname`. In `conftest.py`, replace:

```python
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
```

with:

```python
_ROOT = os.path.dirname(os.path.abspath(__file__))
```

- [ ] **Step 4: Simplify `pytest.ini`**

Replace the entire file with:

```ini
[pytest]
python_files = test_*.py
```

`testpaths = tests` is dropped so pytest discovers `tools/` and `common/` in later tasks. `pythonpath = tests` is dropped because it existed only to make `from conftest import ...` resolve; with the conftest at the root, pytest prepends the rootdir to `sys.path` and those imports resolve there instead. (Verified: the suite passes unchanged after exactly this edit.)

- [ ] **Step 5: Run the suite**

Run: `pytest -q`
Expected: `162 passed`

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: move pytest conftest to the repo root"
```

---

### Task 2: Move Doors into tools/

**Files:**
- Create: `tools/__init__.py`, `tools/doors/tests/__init__.py`
- Move: `doors/{__init__,gui,object}.py` → `tools/doors/`
- Move: `Resources/icons/DoorsPlus.svg`, `Resources/icons/dimensions_ref_door.svg` → `tools/doors/resources/icons/`
- Move: `tests/doors/test_doors.py` → `tools/doors/tests/test_doors.py`
- Delete: `doorsplus_object.py`
- Modify: `tools/doors/gui.py:22,24,668`
- Modify: `tools/doors/tests/test_doors.py:5`
- Modify: `InitGui.py:40`

**Interfaces:**
- Consumes: the root `conftest.py` from Task 1.
- Produces: the package `tools.doors` with `tools.doors.gui` and `tools.doors.object`. Establishes the layout pattern Tasks 3-5 repeat verbatim.

- [ ] **Step 1: Create the package skeleton**

```bash
mkdir -p tools/doors/resources/icons tools/doors/tests
touch tools/__init__.py tools/doors/tests/__init__.py
```

- [ ] **Step 2: Move the code, icons, tests, and drop the shim**

```bash
git mv doors/__init__.py doors/gui.py doors/object.py tools/doors/
git mv Resources/icons/DoorsPlus.svg tools/doors/resources/icons/
git mv Resources/icons/dimensions_ref_door.svg tools/doors/resources/icons/
git mv tests/doors/test_doors.py tools/doors/tests/test_doors.py
git rm -q doorsplus_object.py
find doors tests/doors -name "__pycache__" -type d -exec rm -rf {} +
rmdir doors tests/doors
```

The `find` is required: every `pytest` run regenerates `__pycache__/` in these
folders, and `rmdir` refuses a non-empty directory. `rmdir` is kept rather than
`rm -rf` on purpose — if anything *other* than bytecode is still there, it
should fail loudly rather than delete a file a `git mv` missed.

`doorsplus_object.py` is deleted rather than kept: per the Global Constraints, Proxy-path compatibility is explicitly out of scope.

- [ ] **Step 3: Retarget the path constants in `tools/doors/gui.py`**

Line 22 — the file is one level deeper, so `_DIR` needs one fewer `dirname`, and it now points at the tool folder rather than the repo root. Replace:

```python
_DIR = os.path.dirname(os.path.dirname(__file__))     # repo root, for Resources/
```

with:

```python
_DIR = os.path.dirname(__file__)     # tools/doors/, for resources/
```

Lines 24 and 668 — retarget both to the tool's own lowercase `resources/`:

```python
ICON = os.path.join(_DIR, "resources", "icons", "DoorsPlus.svg")
```

```python
        path = os.path.join(_DIR, "resources", "icons", name + ".svg")
```

- [ ] **Step 4: Fix the test import**

In `tools/doors/tests/test_doors.py:5`, replace:

```python
from doors import gui as dg
```

with:

```python
from tools.doors import gui as dg
```

Leave line 6 (`from conftest import ...`) alone — it still resolves via the root conftest.

- [ ] **Step 5: Fix the InitGui import**

In `InitGui.py:40`, replace:

```python
        import doors.gui        # noqa: F401
```

with:

```python
        import tools.doors.gui  # noqa: F401
```

- [ ] **Step 6: Run the suite**

Run: `pytest -q`
Expected: `162 passed`

- [ ] **Step 7: Verify the icons actually resolve at the new paths**

Run:
```bash
python3 -c "import os; d='tools/doors/resources/icons'; print(sorted(os.listdir(d)))"
```
Expected: `['DoorsPlus.svg', 'dimensions_ref_door.svg']`

A green suite does not cover this — no test loads an icon — so check it directly.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: move Doors into tools/doors with its own resources and tests"
```

---

### Task 3: Move Windows into tools/

Identical in shape to Task 2, with different files and line numbers.

**Files:**
- Create: `tools/windows/tests/__init__.py`
- Move: `windows/{__init__,gui,object}.py` → `tools/windows/`
- Move: `Resources/icons/WindowsPlus.svg`, `Resources/icons/dimensions_ref_window.svg` → `tools/windows/resources/icons/`
- Move: `tests/windows/test_windows.py` → `tools/windows/tests/test_windows.py`
- Delete: `windowsplus_object.py`
- Modify: `tools/windows/gui.py:25,27,789`
- Modify: `tools/windows/tests/test_windows.py:8`
- Modify: `InitGui.py:41`

**Interfaces:**
- Consumes: `tools/__init__.py` from Task 2.
- Produces: the package `tools.windows` with `tools.windows.gui` and `tools.windows.object`.

- [ ] **Step 1: Create the package skeleton**

```bash
mkdir -p tools/windows/resources/icons tools/windows/tests
touch tools/windows/tests/__init__.py
```

- [ ] **Step 2: Move the code, icons, tests, and drop the shim**

```bash
git mv windows/__init__.py windows/gui.py windows/object.py tools/windows/
git mv Resources/icons/WindowsPlus.svg tools/windows/resources/icons/
git mv Resources/icons/dimensions_ref_window.svg tools/windows/resources/icons/
git mv tests/windows/test_windows.py tools/windows/tests/test_windows.py
git rm -q windowsplus_object.py
find windows tests/windows -name "__pycache__" -type d -exec rm -rf {} +
rmdir windows tests/windows
```

The `find` clears the bytecode `pytest` regenerates on every run; `rmdir` then
fails loudly if anything unexpected remains.

- [ ] **Step 3: Retarget the path constants in `tools/windows/gui.py`**

Line 25 — replace:

```python
_DIR = os.path.dirname(os.path.dirname(__file__))     # repo root, for Resources/
```

with:

```python
_DIR = os.path.dirname(__file__)     # tools/windows/, for resources/
```

Lines 27 and 789:

```python
ICON = os.path.join(_DIR, "resources", "icons", "WindowsPlus.svg")
```

```python
        path = os.path.join(_DIR, "resources", "icons", name + ".svg")
```

- [ ] **Step 4: Fix the test import**

In `tools/windows/tests/test_windows.py:8`, replace:

```python
from windows import gui as wg
```

with:

```python
from tools.windows import gui as wg
```

- [ ] **Step 5: Fix the InitGui import**

In `InitGui.py:41`, replace:

```python
        import windows.gui      # noqa: F401
```

with:

```python
        import tools.windows.gui  # noqa: F401
```

- [ ] **Step 6: Run the suite**

Run: `pytest -q`
Expected: `162 passed`

- [ ] **Step 7: Verify the icons resolve**

Run:
```bash
python3 -c "import os; print(sorted(os.listdir('tools/windows/resources/icons')))"
```
Expected: `['WindowsPlus.svg', 'dimensions_ref_window.svg']`

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: move Windows into tools/windows with its own resources and tests"
```

---

### Task 4: Move Stairs into tools/

Same shape again, plus one extra edit: `stairs/object.py` builds its icon path inline instead of from `_DIR`, so a search-and-replace on `_DIR` alone will miss it.

**Files:**
- Create: `tools/stairs/tests/__init__.py`
- Move: `stairs/{__init__,gui,object}.py` → `tools/stairs/`
- Move: `Resources/icons/StairsPlus.svg`, `dimensions_ref_straight.svg`, `dimensions_ref_quarterturn.svg`, `dimensions_ref_halfturn.svg`, `steps_ref.svg` → `tools/stairs/resources/icons/`
- Move: `tests/stairs/test_stairs.py` → `tools/stairs/tests/test_stairs.py`
- Delete: `stairsplus_object.py`
- Modify: `tools/stairs/gui.py:17,19,315`
- Modify: `tools/stairs/object.py:2824`
- Modify: `tools/stairs/tests/test_stairs.py:9`
- Modify: `InitGui.py:39`

**Interfaces:**
- Consumes: `tools/__init__.py` from Task 2.
- Produces: the package `tools.stairs` with `tools.stairs.gui` and `tools.stairs.object`.

- [ ] **Step 1: Create the package skeleton**

```bash
mkdir -p tools/stairs/resources/icons tools/stairs/tests
touch tools/stairs/tests/__init__.py
```

- [ ] **Step 2: Move the code, icons, tests, and drop the shim**

```bash
git mv stairs/__init__.py stairs/gui.py stairs/object.py tools/stairs/
git mv Resources/icons/StairsPlus.svg tools/stairs/resources/icons/
git mv Resources/icons/dimensions_ref_straight.svg tools/stairs/resources/icons/
git mv Resources/icons/dimensions_ref_quarterturn.svg tools/stairs/resources/icons/
git mv Resources/icons/dimensions_ref_halfturn.svg tools/stairs/resources/icons/
git mv Resources/icons/steps_ref.svg tools/stairs/resources/icons/
git mv tests/stairs/test_stairs.py tools/stairs/tests/test_stairs.py
git rm -q stairsplus_object.py
find stairs tests/stairs -name "__pycache__" -type d -exec rm -rf {} +
rmdir stairs tests/stairs
```

The `find` clears the bytecode `pytest` regenerates on every run; `rmdir` then
fails loudly if anything unexpected remains.

- [ ] **Step 3: Retarget the path constants in `tools/stairs/gui.py`**

Line 17 — replace:

```python
_DIR = os.path.dirname(os.path.dirname(__file__))     # repo root, for Resources/
```

with:

```python
_DIR = os.path.dirname(__file__)     # tools/stairs/, for resources/
```

Line 19:

```python
ICON = os.path.join(_DIR, "resources", "icons", "StairsPlus.svg")
```

Line 315 — this one is inside `_setRefImage`, not `_refImage` (stairs splits the two so it can re-target the image when the shape changes):

```python
        path = os.path.join(_DIR, "resources", "icons", name + ".svg")
```

- [ ] **Step 4: Fix the inline icon path in `tools/stairs/object.py`**

This is the edit most easily missed — it does not use `_DIR`. At line 2824, replace:

```python
        return os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "Resources", "icons", "StairsPlus.svg")
```

with:

```python
        return os.path.join(os.path.dirname(__file__),
                            "resources", "icons", "StairsPlus.svg")
```

- [ ] **Step 5: Fix the test import**

In `tools/stairs/tests/test_stairs.py:9`, replace:

```python
from stairs import gui as sg
```

with:

```python
from tools.stairs import gui as sg
```

- [ ] **Step 6: Fix the InitGui import**

In `InitGui.py:39`, replace:

```python
        import stairs.gui       # noqa: F401
```

with:

```python
        import tools.stairs.gui  # noqa: F401
```

- [ ] **Step 7: Run the suite**

Run: `pytest -q`
Expected: `162 passed`

- [ ] **Step 8: Verify the icons resolve and no stale `Resources` reference survives in stairs**

Run:
```bash
python3 -c "import os; print(sorted(os.listdir('tools/stairs/resources/icons')))"
grep -rn "Resources" tools/stairs/ || echo "clean"
```
Expected: the five stairs SVGs listed, then `clean`.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: move Stairs into tools/stairs with its own resources and tests"
```

---

### Task 5: Move Parts Library into tools/

Largest move by file count, but structurally the same. Two differences: there is no compatibility shim to delete, and `partslib` carries a `_ROOT` constant (pointing at the repo root for the shared `Resources/`) that is deleted outright rather than adjusted.

`partslib/library/` and `partslib/builders/` move as-is. `LIBRARY_DIR` at `partslib/object.py:55` is already `os.path.join(_DIR, "library")` — package-relative — so it needs no edit.

**Files:**
- Create: `tools/partslib/tests/__init__.py`
- Move: `partslib/` (all 9 modules plus `builders/` and `library/`) → `tools/partslib/`
- Move: `Resources/icons/PartsLibrary.svg` and `Resources/icons/facets/` → `tools/partslib/resources/icons/`
- Move: all 7 files from `tests/partslib/` → `tools/partslib/tests/`
- Move: `tests/README.md` → `docs/TESTING.md`, and rewrite its paths
- Modify: `tools/partslib/gui.py:30,45,46`
- Modify: `tools/partslib/object.py:23,292`
- Modify: `tools/partslib/tests/*.py` — the `from partslib import ...` lines
- Modify: `tools/partslib/tests/test_library_content.py:24,25,100`
- Modify: `InitGui.py:42`

**Interfaces:**
- Consumes: `tools/__init__.py` from Task 2.
- Produces: the package `tools.partslib`, with `tools.partslib.object.LIBRARY_DIR` still resolving to the bundled library.

- [ ] **Step 1: Create the package skeleton**

```bash
mkdir -p tools/partslib/resources/icons tools/partslib/tests
touch tools/partslib/tests/__init__.py
```

- [ ] **Step 2: Move the package, icons, and tests**

```bash
git mv partslib tools/partslib
git mv Resources/icons/PartsLibrary.svg tools/partslib/resources/icons/
git mv Resources/icons/facets tools/partslib/resources/icons/facets
for f in tests/partslib/*.py; do git mv "$f" tools/partslib/tests/; done
git mv tests/README.md docs/TESTING.md
find tests -name "__pycache__" -type d -exec rm -rf {} +
rmdir tests/partslib tests
```

`git mv partslib tools/partslib` moves `builders/` and `library/` with it.

`tests/README.md` is a tracked document describing the test layout. It is the
last file in `tests/`, so it must move before the directory can be removed —
`docs/` is its home now that no single `tests/` tree remains. Its contents are
updated in the next step.

The `find` clears the bytecode `pytest` regenerates on every run; `rmdir` then
fails loudly if anything unexpected remains.

- [ ] **Step 2b: Update the relocated testing document**

`docs/TESTING.md` describes the old layout throughout and is now wrong in three
ways. Fix all of them:

1. The intro says `conftest.py` injects the fakes — say it now lives at the repo
   root, and why: pytest applies a conftest only to tests beneath its own
   directory, so it must sit above `tools/` and `common/` to reach both.
2. Every test path it names moves. Rewrite `tests/windows/test_windows.py` →
   `tools/windows/tests/test_windows.py`, `tests/doors/test_doors.py` →
   `tools/doors/tests/test_doors.py`, `tests/stairs/test_stairs.py` →
   `tools/stairs/tests/test_stairs.py`, and any `tests/partslib/...` path to its
   `tools/partslib/tests/...` equivalent.
3. The "one test file per tool" framing still holds, but tests now live beside
   the tool they cover rather than in a central tree — say so.

Do not document `common/tests/` here; it does not exist until Task 7.

Run afterwards to confirm no stale path survives:

```bash
grep -n "tests/windows\|tests/doors\|tests/stairs\|tests/partslib" docs/TESTING.md || echo "clean"
```
Expected: `clean`

- [ ] **Step 3: Delete `_ROOT` and retarget the icon constants in `tools/partslib/gui.py`**

Line 30 — delete this line entirely:

```python
_ROOT = os.path.dirname(_DIR)        # repo root, for the shared Resources/
```

`_DIR = os.path.dirname(__file__)` on line 29 stays as-is; it already points at the package.

Lines 45-46 — resolve from `_DIR` and the lowercase folder:

```python
ICON = os.path.join(_DIR, "resources", "icons", "PartsLibrary.svg")
_FACET_ICON_DIR = os.path.join(_DIR, "resources", "icons", "facets")
```

- [ ] **Step 4: Delete `_ROOT` and retarget the icon in `tools/partslib/object.py`**

Line 23 — delete entirely:

```python
_ROOT = os.path.dirname(_DIR)        # repo root, for the shared Resources/
```

Line 292:

```python
        return os.path.join(_DIR, "resources", "icons", "PartsLibrary.svg")
```

- [ ] **Step 5: Fix the test imports**

Across the seven files in `tools/partslib/tests/`, replace every `from partslib import` with `from tools.partslib import`. There are 8 occurrences — 7 at module scope and one inside a function at `test_library_content.py:112`, which a line-range edit would miss:

```bash
grep -rln "from partslib import" tools/partslib/tests/ | xargs sed -i 's/from partslib import/from tools.partslib import/g'
grep -rn "from partslib import" tools/partslib/tests/ || echo "all rewritten"
```
Expected: `all rewritten`

- [ ] **Step 6: Fix the path anchors in `tools/partslib/tests/test_library_content.py`**

The file is now at `tools/partslib/tests/`, so the old three-`dirname` climb to the repo root should become a two-`dirname` climb to the package. Replace lines 24-25:

```python
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIBRARY_DIR = os.path.join(_ROOT, "partslib", "library")
```

with:

```python
_PARTSLIB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIBRARY_DIR = os.path.join(_PARTSLIB, "library")
```

And line 100:

```python
    icon_dir = os.path.join(_PARTSLIB, "resources", "icons", "facets")
```

- [ ] **Step 7: Fix the InitGui import**

In `InitGui.py:42`, replace:

```python
        import partslib.gui     # noqa: F401
```

with:

```python
        import tools.partslib.gui  # noqa: F401
```

- [ ] **Step 8: Run the suite**

Run: `pytest -q`
Expected: `162 passed`

The parts-library tests scan the real library folder and check every facet icon exists, so a green run here is a genuine check that both `library/` and `resources/icons/facets/` landed correctly.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: move Parts Library into tools/partslib with its own resources and tests"
```

---

### Task 6: Retire the top-level Resources tree

At this point `Resources/icons/` should be empty and only `Resources/images/` remains — seven README screenshots that no code ever loads.

**Files:**
- Move: `Resources/images/*.jpg` → `docs/images/`
- Delete: `Resources/`
- Modify: `README.md` — the seven `<img src>` paths, plus the prose reference at line 416

**Interfaces:**
- Consumes: Tasks 2-5 having emptied `Resources/icons/`.
- Produces: a repo with no top-level `Resources/`.

- [ ] **Step 1: Confirm only images remain**

Run:
```bash
find Resources -type f | sort
```
Expected: exactly the seven `.jpg` files under `Resources/images/`. If any `.svg` is still listed, an earlier task missed a file — go back and fix that task rather than moving the stray here.

- [ ] **Step 2: Move the screenshots into docs**

```bash
mkdir -p docs/images
git mv Resources/images/toolbar.jpg docs/images/
git mv Resources/images/stairs_dialog_1.jpg docs/images/
git mv Resources/images/stairs_dialog_2.jpg docs/images/
git mv Resources/images/stairs_quarter_turn.jpg docs/images/
git mv Resources/images/doors_dialog_1.jpg docs/images/
git mv Resources/images/doors_dialog_2.jpg docs/images/
git mv Resources/images/doors_double_swing.jpg docs/images/
rmdir Resources/images Resources/icons Resources
```

- [ ] **Step 3: Update the README image paths**

```bash
sed -i 's|src="Resources/images/|src="docs/images/|g' README.md
```

- [ ] **Step 4: Update the README prose reference**

Line 416 names the old facet-icon location. Replace `Resources/icons/facets/` with `tools/partslib/resources/icons/facets/`.

- [ ] **Step 5: Verify nothing references the old tree**

Run:
```bash
grep -rn "Resources/" --include="*.py" --include="*.md" . | grep -v docs/superpowers || echo "clean"
```
Expected: `clean`. (The spec and plan under `docs/superpowers/` legitimately discuss the old paths, so they are excluded.)

- [ ] **Step 6: Clear stale bytecode from the old module locations**

Not correctness-critical — Python will not import from these — but they are confusing leftovers naming modules that no longer exist:

```bash
find . -name "__pycache__" -type d -not -path "./.git/*" -exec rm -rf {} +
```

- [ ] **Step 7: Run the suite**

Run: `pytest -q`
Expected: `162 passed`

- [ ] **Step 8: MANUAL CHECK — load the add-on in FreeCAD**

**This cannot be automated and must be done by the user.** Relocation is now complete, and nothing in the test suite exercises FreeCAD's import of `InitGui.py`, the icon loading, or the toolbar wiring.

Start FreeCAD, switch to the BIM workbench, and confirm:
1. The **ArchPlus** toolbar appears with four buttons, each showing its icon (not a blank placeholder).
2. Each of the four opens its dialog without error.
3. In the Stairs and Doors dialogs, the reference diagram images render.
4. The Report view shows no `ArchPlus:` error line.

If icons are blank, a `resources/` path is wrong — recheck the retargeted constant for that tool. If the toolbar is missing entirely, an `InitGui.py` import is wrong.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: retire the top-level Resources tree"
```

---

### Task 7: Extract common/spec.py

First extraction task. `storeSpec` and `readSpec` are byte-identical module-level functions in both tools, as is the `SPEC_PROP` constant they depend on.

**Files:**
- Create: `common/__init__.py`, `common/spec.py`, `common/tests/__init__.py`, `common/tests/test_spec.py`
- Modify: `tools/doors/gui.py:14,33-60`
- Modify: `tools/windows/gui.py:17,57-84`

**Interfaces:**
- Consumes: the `fake_obj` fixture from the root `conftest.py`.
- Produces: `common.spec` exporting `SPEC_PROP` (the string `"ArchPlusSpec"`), `storeSpec(obj, spec) -> None`, and `readSpec(obj) -> dict | None`. Both tool modules re-export all three, so `dg.storeSpec` / `wg.readSpec` keep working for existing tests.

- [ ] **Step 1: Write the failing test**

Create `common/tests/__init__.py` (empty) and `common/tests/test_spec.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Tests for the shared ArchPlus spec-persistence helpers, extracted from the
# byte-identical copies that lived in the Doors and Windows panels.

from common import spec


def test_store_then_read_round_trips(fake_obj):
    payload = {"operation": "Single swing", "width": 900}
    spec.storeSpec(fake_obj, payload)
    assert spec.readSpec(fake_obj) == payload


def test_store_creates_the_property_when_it_is_absent(fake_obj):
    assert not hasattr(fake_obj, spec.SPEC_PROP)
    spec.storeSpec(fake_obj, {"a": 1})
    assert hasattr(fake_obj, spec.SPEC_PROP)


def test_store_on_none_is_a_no_op():
    spec.storeSpec(None, {"a": 1})   # must not raise


def test_read_returns_none_when_nothing_was_stored(fake_obj):
    assert spec.readSpec(fake_obj) is None


def test_read_returns_none_on_malformed_json(fake_obj):
    setattr(fake_obj, spec.SPEC_PROP, "{not json")
    assert spec.readSpec(fake_obj) is None


def test_read_returns_none_when_the_json_is_not_a_dict(fake_obj):
    setattr(fake_obj, spec.SPEC_PROP, "[1, 2, 3]")
    assert spec.readSpec(fake_obj) is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest common/tests/test_spec.py -q`
Expected: FAIL — collection error, `ModuleNotFoundError: No module named 'common'`

- [ ] **Step 3: Create the package and the module**

Create `common/__init__.py` (empty), then `common/spec.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Persistence of the ArchPlus creation spec on a FreeCAD object.
#
# The native Window object only stores Width/Height/Frame. The remaining panel
# settings are serialized to JSON in a single hidden string property so the
# panel can be reopened with every field intact. Doors and Windows shared
# byte-identical copies of this before it was extracted here.

import json

SPEC_PROP = "ArchPlusSpec"


def storeSpec(obj, spec):
    """Persist the ArchPlus creation spec on the object as JSON."""
    if obj is None:
        return
    if not hasattr(obj, SPEC_PROP):
        obj.addProperty("App::PropertyString", SPEC_PROP, "ArchPlus",
                        "Serialized ArchPlus settings (internal)")
        try:
            obj.setEditorMode(SPEC_PROP, 2)   # hidden from the property editor
        except Exception:
            pass
    setattr(obj, SPEC_PROP, json.dumps(spec))


def readSpec(obj):
    """Return the stored ArchPlus spec dict, or None if absent/unreadable."""
    raw = getattr(obj, SPEC_PROP, "") or ""
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except Exception:
        return None
    return d if isinstance(d, dict) else None
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest common/tests/test_spec.py -q`
Expected: `6 passed`

- [ ] **Step 5: Delegate from Doors**

In `tools/doors/gui.py`, delete the `SPEC_PROP` assignment (line 33) and the whole `storeSpec` and `readSpec` definitions (lines 36-60), leaving the explanatory comment block above them in place. Replace them with a re-export so `dg.storeSpec` and `dg.readSpec` keep resolving for the existing tests:

```python
from common.spec import SPEC_PROP, storeSpec, readSpec  # noqa: F401
```

Then delete `import json` at line 14 — lines 47 and 56 were its only users.

- [ ] **Step 6: Delegate from Windows**

Same edit in `tools/windows/gui.py`: delete `SPEC_PROP` (line 57) and the `storeSpec`/`readSpec` definitions (lines 60-84), add the same re-export line, and delete `import json` at line 17.

- [ ] **Step 7: Confirm no stray json usage remains**

Run:
```bash
grep -n "json" tools/doors/gui.py tools/windows/gui.py || echo "clean"
```
Expected: `clean`. If anything is listed, restore that file's `import json` instead of deleting it.

- [ ] **Step 8: Run the whole suite**

Run: `pytest -q`
Expected: `168 passed` (162 baseline + 6 new)

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: extract shared spec persistence into common/spec.py"
```

---

### Task 8: Extract common/widgets.py

`_mm`, `_setmm` and `_len` are identical across Doors, Windows *and* Stairs — the only textual differences are docstrings that Stairs carries. `_refImage` is identical in Doors and Windows; Stairs splits it into `_refImage` plus `_setRefImage` so it can re-target the diagram when the shape changes. The extracted form keeps that split, so Stairs loses nothing.

The panel methods stay in place as one-line delegations. That keeps every call site and every existing test working untouched.

**Files:**
- Create: `common/widgets.py`, `common/tests/test_widgets.py`
- Modify: `tools/doors/gui.py` — add `_ICON_DIR`; methods `_len` (638), `_mm` (652), `_setmm` (659), `_refImage` (665)
- Modify: `tools/windows/gui.py` — add `_ICON_DIR`; methods `_len` (722), `_mm` (736), `_setmm` (743), `_refImage` (786)
- Modify: `tools/stairs/gui.py` — add `_ICON_DIR`; methods `_len` (239), `_mm` (257), `_setmm` (265), `_refImage` (306), `_setRefImage` (313)

Line numbers are from before Task 7's edits shifted them; locate the methods by name, not by number.

**Interfaces:**
- Consumes: `FakeNum` and `quantity` from the root `conftest.py`.
- Produces: `common.widgets` exporting `mm(w) -> float`, `set_mm(w, value) -> None`, `length_input(default) -> QWidget`, `set_ref_image(lbl, icon_dir, name, size) -> None`, and `ref_image(icon_dir, name, size) -> QLabel`.

- [ ] **Step 1: Write the failing test**

Create `common/tests/test_widgets.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Tests for the shared ArchPlus Qt widget helpers. The conftest fakes make
# PySide an empty module, so the tests that need a Qt class monkeypatch one in.

import os

from common import widgets
from conftest import FakeNum, quantity


def test_mm_reads_a_freecad_quantity_property():
    class QuantityWidget:
        def property(self, name):
            assert name == "value"
            return quantity(900.0)

    assert widgets.mm(QuantityWidget()) == 900.0


def test_mm_falls_back_to_a_plain_value():
    assert widgets.mm(FakeNum(750.0)) == 750.0


def test_set_mm_falls_back_to_set_value():
    w = FakeNum(0.0)
    widgets.set_mm(w, 2100.0)
    assert w.value() == 2100.0


def test_length_input_falls_back_to_a_millimetre_spinbox(monkeypatch):
    # The fake FreeCADGui has no UiLoader, so the Gui::QuantitySpinBox branch
    # raises and the plain-spinbox fallback runs.
    from PySide import QtGui

    class SpinBox:
        def setRange(self, lo, hi):
            self.range = (lo, hi)

        def setDecimals(self, d):
            self.decimals = d

        def setSuffix(self, s):
            self.suffix = s

        def setValue(self, v):
            self.v = v

    monkeypatch.setattr(QtGui, "QDoubleSpinBox", SpinBox, raising=False)
    w = widgets.length_input(2100.0)
    assert w.v == 2100.0
    assert w.suffix == " mm"


class _Label:
    def __init__(self):
        self.pixmap = None
        self.cleared = False

    def setPixmap(self, p):
        self.pixmap = p

    def clear(self):
        self.cleared = True


def test_set_ref_image_clears_the_label_when_the_icon_is_missing():
    lbl = _Label()
    widgets.set_ref_image(lbl, "/nonexistent", "absent", (10, 10))
    assert lbl.cleared
    assert lbl.pixmap is None


def test_set_ref_image_sets_a_pixmap_when_the_icon_exists(tmp_path, monkeypatch):
    from PySide import QtGui

    icon = tmp_path / "ref.svg"
    icon.write_text("<svg/>")

    class FakeIcon:
        def __init__(self, path):
            self.path = path

        def pixmap(self, size):
            return ("pixmap", self.path, size)

    monkeypatch.setattr(QtGui, "QIcon", FakeIcon, raising=False)
    lbl = _Label()
    widgets.set_ref_image(lbl, str(tmp_path), "ref", (10, 10))
    assert lbl.pixmap == ("pixmap", os.path.join(str(tmp_path), "ref.svg"), (10, 10))
    assert not lbl.cleared
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest common/tests/test_widgets.py -q`
Expected: FAIL — collection error, `ImportError: cannot import name 'widgets' from 'common'`

- [ ] **Step 3: Write the module**

Create `common/widgets.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Qt widget helpers shared by the ArchPlus task panels.
#
# Kept separate from common/geometry.py on purpose: this module pulls in
# PySide, that one pulls in Part/Sketcher. Merging them would mean importing
# either drags in both, which would defeat the lazy-import discipline the
# gui modules rely on to stay out of BIM workbench init.

import os

import FreeCAD
import FreeCADGui
from PySide import QtGui, QtCore


def mm(w):
    """Read a length widget's value in millimetres (FreeCAD's base unit)."""
    try:
        return float(w.property("value").Value)
    except Exception:
        return float(w.value())


def set_mm(w, value):
    """Set a length widget from a value in millimetres."""
    try:
        w.setProperty("value", FreeCAD.Units.Quantity("%.6f mm" % float(value)))
    except Exception:
        w.setValue(float(value))


def length_input(default):
    """A unit-aware length input. Gui::QuantitySpinBox shows/parses values in
    the user's configured unit schema (mm, cm, inch, ...) while storing the
    value internally in mm. Falls back to a plain mm spinbox if the FreeCAD
    widget can't be created (e.g. no GUI)."""
    try:
        w = FreeCADGui.UiLoader().createWidget("Gui::QuantitySpinBox")
        w.setProperty("value", FreeCAD.Units.Quantity("%.6f mm" % float(default)))
        return w
    except Exception:
        w = QtGui.QDoubleSpinBox()
        w.setRange(0, 1_000_000)
        w.setDecimals(1)
        w.setSuffix(" mm")
        w.setValue(default)
        return w


def set_ref_image(lbl, icon_dir, name, size):
    """Set (or clear) a reference SVG on an existing label."""
    path = os.path.join(icon_dir, name + ".svg")
    if os.path.exists(path):
        lbl.setPixmap(QtGui.QIcon(path).pixmap(size))
    else:
        lbl.clear()


def ref_image(icon_dir, name, size):
    """A centered QLabel holding a reference SVG (or empty if missing)."""
    lbl = QtGui.QLabel()
    lbl.setAlignment(QtCore.Qt.AlignCenter)
    set_ref_image(lbl, icon_dir, name, size)
    return lbl
```

One deliberate unification: the Doors and Windows `_refImage` did nothing when the icon was missing, whereas Stairs called `lbl.clear()`. The Stairs form is adopted for all three. This changes no behaviour for Doors and Windows — their labels are freshly constructed by `ref_image()` and therefore already empty, so clearing one is a no-op. The `clear()` branch only matters to Stairs, which re-targets an existing label via `set_ref_image()` when the stair shape changes.

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest common/tests/test_widgets.py -q`
Expected: `6 passed`

- [ ] **Step 5: Delegate from Doors**

In `tools/doors/gui.py`, add below the `ICON` assignment:

```python
_ICON_DIR = os.path.join(_DIR, "resources", "icons")
```

Add to the module-scope imports (safe here — this module already imports PySide and FreeCADGui at module scope):

```python
from common import widgets
```

Then replace the four method bodies, keeping their names and decorators:

```python
    def _len(self, default):
        return widgets.length_input(default)

    @staticmethod
    def _mm(w):
        return widgets.mm(w)

    @staticmethod
    def _setmm(w, mm):
        widgets.set_mm(w, mm)

    def _refImage(self, name, size):
        return widgets.ref_image(_ICON_DIR, name, size)
```

- [ ] **Step 6: Delegate from Windows**

In `tools/windows/gui.py`, add below the `ICON` assignment:

```python
_ICON_DIR = os.path.join(_DIR, "resources", "icons")
```

Add to the module-scope imports:

```python
from common import widgets
```

Then replace the four method bodies:

```python
    def _len(self, default):
        return widgets.length_input(default)

    @staticmethod
    def _mm(w):
        return widgets.mm(w)

    @staticmethod
    def _setmm(w, mm):
        widgets.set_mm(w, mm)

    def _refImage(self, name, size):
        return widgets.ref_image(_ICON_DIR, name, size)
```

- [ ] **Step 7: Delegate from Stairs**

Same again in `tools/stairs/gui.py`, with the extra `_setRefImage` method. Add `_ICON_DIR` and `from common import widgets`, then:

```python
    def _len(self, default):
        return widgets.length_input(default)

    @staticmethod
    def _mm(w):
        return widgets.mm(w)

    @staticmethod
    def _setmm(w, mm):
        widgets.set_mm(w, mm)

    def _refImage(self, name, size):
        return widgets.ref_image(_ICON_DIR, name, size)

    def _setRefImage(self, lbl, name, size):
        widgets.set_ref_image(lbl, _ICON_DIR, name, size)
```

- [ ] **Step 8: Run the whole suite**

Run: `pytest -q`
Expected: `174 passed` (168 from Task 7 + 6 new)

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: extract shared Qt widget helpers into common/widgets.py"
```

---

### Task 9: Extract common/geometry.py

`_rect` and `_addFrame` have byte-identical bodies in Doors and Windows, but they are **closures** nested inside `_makeDoorGeometry` / `_makeWindowGeometry`, capturing the enclosing scope's sketch object `s`. The extracted functions therefore take the sketch as an explicit first parameter.

Rather than rewrite every `_rect(...)` call inside those long geometry builders, keep the nested names as two-line wrappers that bind `s`. That single-sources the logic while leaving dozens of call sites untouched — far less risk for the same benefit.

**Files:**
- Create: `common/geometry.py`, `common/tests/test_geometry.py`
- Modify: `tools/doors/gui.py` — the nested `_rect` / `_addFrame` in `_makeDoorGeometry`
- Modify: `tools/windows/gui.py` — the nested `_rect` / `_addFrame` in `_makeWindowGeometry`

**All line numbers quoted in this task are from before Tasks 7 and 8 edited these files.** Task 7 deletes roughly 25 lines near the top of each `gui.py`, shifting everything below it upward. Locate `_makeDoorGeometry`, `_makeWindowGeometry`, and the nested `_rect` / `_addFrame` **by name**, and treat the numbers below as approximate.

**Interfaces:**
- Consumes: `_FakeSketch` from the root `conftest.py`, plus the faked `Part` and `Sketcher` modules it installs.
- Produces: `common.geometry` exporting `add_rect(sketch, p1, p2, p3, p4) -> None` and `add_frame(sketch, outer_p1, outer_p2, outer_p3, outer_p4, inner_p1, inner_p2, inner_p3, inner_p4) -> None`.

- [ ] **Step 1: Write the failing test**

Create `common/tests/test_geometry.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Tests for the shared sketch-building helpers, extracted from the identical
# closures that lived inside the Doors and Windows geometry builders.

import FreeCAD

from common import geometry
from conftest import _FakeSketch

V = FreeCAD.Vector
CORNERS = (V(0, 0, 0), V(10, 0, 0), V(10, 10, 0), V(0, 10, 0))
INNER = (V(1, 1, 0), V(9, 1, 0), V(9, 9, 0), V(1, 9, 0))


def test_add_rect_adds_four_lines():
    s = _FakeSketch()
    geometry.add_rect(s, *CORNERS)
    assert s.GeometryCount == 4


def test_add_rect_adds_four_coincidences_and_four_alignments():
    s = _FakeSketch()
    geometry.add_rect(s, *CORNERS)
    kinds = [c.args[0] for c in s.Constraints]
    assert kinds.count("Coincident") == 4
    assert kinds.count("Horizontal") == 2
    assert kinds.count("Vertical") == 2


def test_add_rect_closes_the_loop_back_to_the_first_edge():
    s = _FakeSketch()
    geometry.add_rect(s, *CORNERS)
    assert s.Constraints[3].args == ("Coincident", 3, 2, 0, 1)


def test_add_rect_offsets_indices_from_existing_geometry():
    s = _FakeSketch()
    geometry.add_rect(s, *CORNERS)
    geometry.add_rect(s, *INNER)
    # The second rectangle's first coincidence must start at index 4, not 0.
    assert s.Constraints[8].args == ("Coincident", 4, 2, 5, 1)


def test_add_frame_adds_an_outer_and_an_inner_rectangle():
    s = _FakeSketch()
    geometry.add_frame(s, *CORNERS, *INNER)
    assert s.GeometryCount == 8
    assert s.ConstraintCount == 16
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest common/tests/test_geometry.py -q`
Expected: FAIL — collection error, `ImportError: cannot import name 'geometry' from 'common'`

- [ ] **Step 3: Write the module**

Create `common/geometry.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Sketch-building helpers shared by the ArchPlus geometry builders.
#
# Kept separate from common/widgets.py on purpose: this module pulls in
# Part and Sketcher, so it must only ever be imported from inside a function
# (never at gui.py module scope), or BIM workbench init would drag those in.

import Part
import Sketcher


def add_rect(sketch, p1, p2, p3, p4):
    """Add a fully-constrained rectangle to `sketch`."""
    idx = sketch.GeometryCount
    sketch.addGeometry(Part.LineSegment(p1, p2))
    sketch.addGeometry(Part.LineSegment(p2, p3))
    sketch.addGeometry(Part.LineSegment(p3, p4))
    sketch.addGeometry(Part.LineSegment(p4, p1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", idx, 2, idx + 1, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", idx + 1, 2, idx + 2, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", idx + 2, 2, idx + 3, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", idx + 3, 2, idx, 1))
    sketch.addConstraint(Sketcher.Constraint("Horizontal", idx))
    sketch.addConstraint(Sketcher.Constraint("Horizontal", idx + 2))
    sketch.addConstraint(Sketcher.Constraint("Vertical", idx + 1))
    sketch.addConstraint(Sketcher.Constraint("Vertical", idx + 3))


def add_frame(sketch, outer_p1, outer_p2, outer_p3, outer_p4,
              inner_p1, inner_p2, inner_p3, inner_p4):
    """Add outer+inner rectangles forming a frame."""
    add_rect(sketch, outer_p1, outer_p2, outer_p3, outer_p4)
    add_rect(sketch, inner_p1, inner_p2, inner_p3, inner_p4)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest common/tests/test_geometry.py -q`
Expected: `5 passed`

- [ ] **Step 5: Delegate from Doors**

In `tools/doors/gui.py`, add this next to the existing in-function `import Part` / `import Sketcher` at lines 150-151, inside `_makeDoorGeometry` — **not** at module scope:

```python
    from common import geometry as archplus_geometry
```

Then replace the two nested definitions (lines 182-201) with wrappers that bind the local sketch:

```python
    # --- Helper: add a rectangle to the sketch ---
    def _rect(p1, p2, p3, p4):
        archplus_geometry.add_rect(s, p1, p2, p3, p4)

    def _addFrame(outer_p1, outer_p2, outer_p3, outer_p4,
                  inner_p1, inner_p2, inner_p3, inner_p4):
        """Add outer+inner rectangles forming a frame."""
        archplus_geometry.add_frame(s, outer_p1, outer_p2, outer_p3, outer_p4,
                                    inner_p1, inner_p2, inner_p3, inner_p4)
```

Every existing `_rect(...)` and `_addFrame(...)` call in the function is left exactly as it is.

If `Part` and `Sketcher` are no longer referenced anywhere else in `_makeDoorGeometry` after this, remove those two now-unused in-function imports; if they are still used elsewhere in the function, leave them.

- [ ] **Step 6: Delegate from Windows**

In `tools/windows/gui.py`, add this beside the in-function `import Part` / `import Sketcher` at lines 156-157, inside `_makeWindowGeometry` — **not** at module scope:

```python
    from common import geometry as archplus_geometry
```

Then replace the two nested definitions (lines 191-210) with:

```python
    # --- Helper: add a rectangle to the sketch ---
    def _rect(p1, p2, p3, p4):
        archplus_geometry.add_rect(s, p1, p2, p3, p4)

    def _addFrame(outer_p1, outer_p2, outer_p3, outer_p4,
                  inner_p1, inner_p2, inner_p3, inner_p4):
        """Add outer+inner rectangles forming a frame."""
        archplus_geometry.add_frame(s, outer_p1, outer_p2, outer_p3, outer_p4,
                                    inner_p1, inner_p2, inner_p3, inner_p4)
```

Every existing `_rect(...)` and `_addFrame(...)` call in the function is left exactly as it is. As in Step 5, drop the now-unused `import Part` / `import Sketcher` only if nothing else in the function still references them.

- [ ] **Step 7: Confirm no module-scope leak of the geometry import**

The lazy-import discipline is the constraint most easily broken here, and no test would catch it:

```bash
grep -n "^from common import geometry\|^import Part\|^import Sketcher" tools/doors/gui.py tools/windows/gui.py || echo "clean"
```
Expected: `clean` — all three must be indented inside a function.

- [ ] **Step 8: Run the whole suite**

Run: `pytest -q`
Expected: `179 passed` (174 from Task 8 + 5 new)

- [ ] **Step 9: MANUAL CHECK — geometry still builds in FreeCAD**

**Requires the user.** The geometry builders construct real Sketcher objects; the test fakes record calls but never build a shape.

In FreeCAD's BIM workbench, create a wall, then insert a Door and a Window into it. Confirm both produce correct frames and panels, and that the Report view shows no error.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor: extract shared sketch helpers into common/geometry.py"
```

---

## Final verification

- [ ] Full suite: `pytest -q` → `179 passed`
- [ ] Layout matches the spec:
  ```bash
  find . -maxdepth 2 -type d -not -path "./.git*" -not -name "__pycache__" | sort
  ```
  Expected top level: `common`, `docs`, `tools` — and no `Resources`, `doors`, `windows`, `stairs`, `partslib`, or `tests`.
- [ ] No shims survive: `ls *plus_object.py 2>/dev/null || echo "clean"` → `clean`
- [ ] The `rotdata` / `slidevec` bug at `tools/doors/object.py:402-403` is still open. It is deliberately out of scope for this plan — file it as follow-up work rather than fixing it here.
