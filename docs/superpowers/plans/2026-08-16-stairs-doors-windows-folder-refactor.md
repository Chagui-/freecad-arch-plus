# Stairs/Doors/Windows Folder Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Correction added during Task 2's review (before Task 3 was dispatched):**
> each tool's `_object.py` has a **reverse** lazy import of its sibling
> `_gui.py` — used by the ViewProvider's `doubleClicked()`/`setEdit()` (to
> reopen the Task panel) and, for Doors/Windows, its "Reposition" context-menu
> command — that the original Task 1/2/3 text below did not account for
> (the plan's original investigation only checked the gui→object direction).
> Task 1 (Stairs) and Task 2 (Doors) needed a fix-round for this after their
> initial implementation; Task 3 (Windows) below has been corrected with an
> explicit Step 5a so it doesn't repeat the mistake. See the ledger's
> "Mid-plan finding" entry for the full story.

**Goal:** Move Stairs, Doors, and Windows — each currently two root-level
files (`*_gui.py` + `*_object.py`) — into their own `stairs/`, `doors/`,
`windows/` packages, completing the "one folder per tool" reorganization
started by the Parts Library pilot (already on this branch). No behavior
change: same three `ArchPlus_*` commands, same toolbar, same tests
(relocated, not rewritten) — **plus** a backward-compatibility requirement
Parts Library didn't have: real `.FCStd` documents exist that place Stairs/
Doors/Windows objects, so each tool keeps a thin compatibility shim at its
old module path so those documents keep restoring correctly.

**Architecture:** Same recipe as the Parts Library pilot — pure mechanical
move + import rewiring, plus one new piece: after moving `_object.py`, the
old flat path becomes a 2-line shim re-exporting the two classes FreeCAD's
document unpickler looks up by module path (`_StairsPlus`/
`_ViewProviderStairsPlus`, or the tool's equivalent). `_gui.py` files need no
shim — Command/Task-panel classes are never pickled into a document.
Stairs/Doors/Windows have no tool-local data folder (unlike Parts Library's
`library/`), so there's no `_DIR`/`_ROOT` split needed — just a single
one-level-up fix per file that uses `_DIR` (or, for
`stairsplus_object.py`, an inline `os.path.dirname(__file__)`).

**Tech Stack:** Python 3, pytest 9.1.1 (via `uv run --with pytest
--no-project`), FreeCAD 1.1 (BIM/Arch workbench) for the manual smoke test.

**Spec:** `docs/superpowers/specs/2026-08-16-per-tool-folders-design.md`
(see especially the "Addendum: backward compatibility" section, added for
this plan)

## Global Constraints

- No behavior change: command names (`ArchPlus_Stairs`, `ArchPlus_Doors`,
  `ArchPlus_Windows`), toolbar entries, and panel behavior are identical
  before and after.
- Every lazy in-function `import <tool>plus_object` keeps its local name
  after rewiring (`from . import object as <tool>plus_object`), so call
  sites below the import are never touched.
- Each tool's old `*_object.py` path becomes a compatibility shim — it must
  keep existing and keep exposing the exact class names FreeCAD's document
  unpickler needs, for as long as pre-refactor documents might be opened.
  Never delete these shim files as part of a later cleanup without a
  separate, explicit decision to drop backward compatibility.
- `*_gui.py` files get **no** compatibility shim — they hold Command and
  Task-panel classes, never pickled into a document.
- Continue on the existing `partslib-folder-refactor` branch (already
  checked out) — do not create a new branch for this plan.
- Doors and Windows both define classes literally named `_Window` and
  `_ViewProviderWindow` (each tool keeps its own copy of `ArchWindow.py` per
  the README) — these stay distinct because they resolve through two
  different module names (`doors.object._Window` vs.
  `windows.object._Window`), exactly as they already are today under their
  current flat names.

---

### Task 1: Move Stairs into `stairs/`, add its compat shim, fix imports and paths

**Files:**
- Create: `stairs/__init__.py`
- Move: `stairsplus_gui.py` → `stairs/gui.py`
- Move: `stairsplus_object.py` → `stairs/object.py`
- Create: `stairsplus_object.py` (new content — compat shim, replaces the
  moved original at this path)
- Modify: `InitGui.py`
- Move: `tests/test_stairs.py` → `tests/stairs/test_stairs.py`

**Interfaces:**
- Produces: `stairs.gui`, `stairs.object` (with `_StairsPlus`,
  `_ViewProviderStairsPlus`, `makeStairsPlus`, `TURN_INFO` and everything
  else `stairsplus_object.py` exported, now under the new package name).
  Root-level `stairsplus_object` continues to exist as a 2-line shim
  exposing `_StairsPlus`/`_ViewProviderStairsPlus` only.
- Consumes: nothing from other tasks — Stairs, Doors, and Windows are fully
  independent of each other and of Parts Library.

- [ ] **Step 1: Baseline — confirm the current suite is green before moving anything**

Run: `uv run --with pytest --no-project pytest tests/ -q`
Expected: PASS (162 passed, 0 failed — same count Parts Library left this
branch at; note it so later steps can compare).

- [ ] **Step 2: Move the files**

```bash
mkdir -p stairs
touch stairs/__init__.py
git mv stairsplus_gui.py stairs/gui.py
git mv stairsplus_object.py stairs/object.py
git add stairs/__init__.py
```

- [ ] **Step 3: Fix `stairs/gui.py`'s `_DIR` and drop the `sys.path` hack**

Change:
```python
import math
import os
import sys

import FreeCAD
import FreeCADGui
from PySide import QtGui, QtCore

# Make sibling modules (stairsplus_object) importable.
_DIR = os.path.dirname(__file__)
if _DIR not in sys.path:
    sys.path.append(_DIR)

ICON = os.path.join(_DIR, "Resources", "icons", "StairsPlus.svg")
```
to:
```python
import math
import os

import FreeCAD
import FreeCADGui
from PySide import QtGui, QtCore

_DIR = os.path.dirname(os.path.dirname(__file__))     # repo root, for Resources/

ICON = os.path.join(_DIR, "Resources", "icons", "StairsPlus.svg")
```
(`import sys` is removed along with the hack — verified `sys` has no other
use anywhere in this file. `_DIR` keeps its name but now means "repo root"
one level up, which is what both `ICON` above and the `_setRefImage()`
line below need — no other line changes.)

Confirm the one other `_DIR` use in this file needs no separate edit — it
already reads `_DIR` and will pick up the corrected value automatically:
```python
    def _setRefImage(self, lbl, name, size):
        """Set (or clear) a reference SVG on an existing label."""
        path = os.path.join(_DIR, "Resources", "icons", name + ".svg")
```

- [ ] **Step 4: Fix the three lazy in-function imports in `stairs/gui.py`**

Each becomes `from . import object as stairsplus_object` — same local
name, nothing else on the line or below it changes. Find each by its
surrounding function (not by line number — Step 2 already ran):

| Function | Before | After |
| --- | --- | --- |
| `makeStairsPlus()` (module-level factory) | `import stairsplus_object` | `from . import object as stairsplus_object` |
| `StairsPlusTaskPanel.__init__()` | `import stairsplus_object` | `from . import object as stairsplus_object` |
| `StairsPlusTaskPanel._startPreview()` | `import stairsplus_object` | `from . import object as stairsplus_object` |

- [ ] **Step 5: Fix `stairs/object.py`'s inline icon path**

In `_ViewProviderStairsPlus.getIcon()`, change:
```python
    def getIcon(self):

        import os

        return os.path.join(os.path.dirname(__file__),
                            "Resources", "icons", "StairsPlus.svg")
```
to:
```python
    def getIcon(self):

        import os

        return os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "Resources", "icons", "StairsPlus.svg")
```
(This file has no module-level `_DIR`. It DOES have one cross-module
`stairsplus_gui` import, fixed in Step 5a below — the original text here
incorrectly claimed there was none.)

- [ ] **Step 5a: Fix the reverse lazy import — `stairs/object.py` importing `stairsplus_gui`**

*(Added as a correction after Task 1 originally shipped without it — see
the plan header's correction note.)* `_ViewProviderStairsPlus.doubleClicked()`
lazily imports the sibling GUI module to reopen the Task panel on
double-click. This is the same pattern as the `_gui.py` → `_object.py`
imports fixed in Step 4, just in the opposite direction. Change:
```python
    def doubleClicked(self, vobj):
        "Reopen the StairsPlus configuration panel to edit this object"

        import FreeCADGui

        # Don't stack panels if one is already open.
        if FreeCADGui.Control.activeDialog():
            return False
        import stairsplus_gui
        FreeCADGui.Control.showDialog(
            stairsplus_gui.StairsPlusTaskPanel(vobj.Object))
        return True
```
to:
```python
    def doubleClicked(self, vobj):
        "Reopen the StairsPlus configuration panel to edit this object"

        import FreeCADGui

        # Don't stack panels if one is already open.
        if FreeCADGui.Control.activeDialog():
            return False
        from . import gui as stairsplus_gui
        FreeCADGui.Control.showDialog(
            stairsplus_gui.StairsPlusTaskPanel(vobj.Object))
        return True
```
(Only the one `import stairsplus_gui` line changes — same local name, so
the two lines below it are untouched.)

- [ ] **Step 6: Create the compatibility shim at the old `stairsplus_object.py` path**

Create `stairsplus_object.py` (repo root) with exactly this content:
```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Backward-compatibility shim — DO NOT DELETE.
#
# Documents saved with ArchPlus before the per-tool-folder reorganization
# pickle their Stairs object's Proxy by this exact module path
# ("stairsplus_object._StairsPlus" / "_ViewProviderStairsPlus"). FreeCAD's
# unpickler resolves the class via plain getattr(import(module), name),
# regardless of that class's own __module__ attribute — so this module
# must keep existing and keep exposing these two names for as long as any
# such document might still be opened. The real implementation lives in
# stairs/object.py now; nothing here does anything but re-export.

from stairs.object import _StairsPlus, _ViewProviderStairsPlus  # noqa: F401
```

- [ ] **Step 7: Update `InitGui.py`'s Stairs import**

Change:
```python
        import stairsplus_gui   # noqa: F401
```
to:
```python
        import stairs.gui       # noqa: F401
```
(Leave the `doorsplus_gui`/`windowsplus_gui` lines exactly as they are —
those move in Tasks 2 and 3.)

- [ ] **Step 8: Move and fix the Stairs test file**

```bash
mkdir -p tests/stairs
git mv tests/test_stairs.py tests/stairs/test_stairs.py
```

Change its import:
```python
import stairsplus_gui as sg
```
to:
```python
from stairs import gui as sg
```

- [ ] **Step 9: Smoke-test the package imports without FreeCAD**

Run:
```bash
PYTHONPATH=. python3 -c "import stairs.gui" 2>&1 | tail -5
```
Expected: fails with a `ModuleNotFoundError` for `FreeCAD` (or similar) —
this is normal, `stairs/gui.py` imports FreeCAD/PySide at module scope and
can't import outside FreeCAD. That failure mode confirms the file at least
parses far enough to hit the FreeCAD import; a `SyntaxError` or an error
naming `stairs` itself would mean something is actually wrong.

Then run the real check — the full test suite, which uses `conftest.py`'s
FreeCAD/PySide fakes to actually exercise `stairs.gui`:
```bash
uv run --with pytest --no-project pytest tests/ -q
```
Expected: PASS, same 162-test count as the baseline (Stairs' own tests now
run from `tests/stairs/test_stairs.py` importing through the new package;
Doors/Windows/Parts-Library tests are unaffected).

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor: move Stairs into stairs/ package, add compat shim for saved documents"
```

---

### Task 2: Move Doors into `doors/`, add its compat shim, fix imports and paths

**Files:**
- Create: `doors/__init__.py`
- Move: `doorsplus_gui.py` → `doors/gui.py`
- Move: `doorsplus_object.py` → `doors/object.py`
- Create: `doorsplus_object.py` (new content — compat shim)
- Modify: `InitGui.py`
- Move: `tests/test_doors.py` → `tests/doors/test_doors.py`

**Interfaces:**
- Produces: `doors.gui` (with the GUI-level `makeDoor()` convenience
  factory and the Task panel) and `doors.object` (with `_Window`,
  `_ViewProviderWindow`, and its own internal `makeWindow()` used by the
  panel's accept path — same function name as Windows' `_object.py`, but a
  separate module, same as the class names). Root-level `doorsplus_object`
  continues to exist as a 2-line shim exposing `_Window`/`_ViewProviderWindow`
  only.
- Consumes: nothing from Task 1 — independent.

- [ ] **Step 1: Baseline check**

Run: `uv run --with pytest --no-project pytest tests/ -q`
Expected: PASS, same count as Task 1 left it at.

- [ ] **Step 2: Move the files**

```bash
mkdir -p doors
touch doors/__init__.py
git mv doorsplus_gui.py doors/gui.py
git mv doorsplus_object.py doors/object.py
git add doors/__init__.py
```

- [ ] **Step 3: Fix `doors/gui.py`'s `_DIR` and drop the `sys.path` hack**

Change:
```python
import json
import math
import os
import sys

import FreeCAD
import FreeCADGui
from PySide import QtGui, QtCore

_DIR = os.path.dirname(__file__)
if _DIR not in sys.path:
    sys.path.append(_DIR)

ICON = os.path.join(_DIR, "Resources", "icons", "DoorsPlus.svg")
```
to:
```python
import json
import math
import os

import FreeCAD
import FreeCADGui
from PySide import QtGui, QtCore

_DIR = os.path.dirname(os.path.dirname(__file__))     # repo root, for Resources/

ICON = os.path.join(_DIR, "Resources", "icons", "DoorsPlus.svg")
```
(`import sys` removed — verified no other use in this file. The
`_refImage()` method's `os.path.join(_DIR, "Resources", "icons", name +
".svg")` line needs no separate edit; it picks up the corrected `_DIR`
automatically.)

- [ ] **Step 4: Fix the three lazy in-function imports in `doors/gui.py`**

Each becomes `from . import object as doorsplus_object` — same local name.
Find each by its surrounding function:

| Function | Before | After |
| --- | --- | --- |
| `makeDoor()` (module-level factory) | `import doorsplus_object` | `from . import object as doorsplus_object` |
| the panel's `_startPreview()` | `import doorsplus_object` | `from . import object as doorsplus_object` |
| the panel's accept/commit path (creates the door via `makeWindow`) | `import doorsplus_object` | `from . import object as doorsplus_object` |

- [ ] **Step 5: `doors/object.py` needs no path fix, but DOES need an import fix (see Step 5a)**

Confirm (don't guess): this file's `_ViewProviderWindow.getIcon()` returns
FreeCAD's built-in `Arch_rc` Qt resource paths (e.g.
`":/icons/Arch_Window_Tree.svg"`), not a filesystem path — there is no
`_DIR`, no `Resources/` reference in this file. There IS a cross-module
import to fix, though — two sites, handled in Step 5a below.

- [ ] **Step 5a: Fix the reverse lazy imports — `doors/object.py` importing `doorsplus_gui`**

*(Added as a correction after this task originally shipped without it —
see the plan header's correction note.)* Two sites in
`_ViewProviderWindow` lazily import the sibling GUI module — one to reopen
the Task panel (double-click / native Edit), one for the "Reposition (pick
point)" context-menu command. Same pattern as the `_gui.py` → `_object.py`
imports fixed in Step 4, just in the opposite direction.

In `_openDoorsPlusPanel()`, change:
```python
        try:
            import doorsplus_gui
            FreeCADGui.Control.showDialog(doorsplus_gui.DoorsPlusTaskPanel(obj))
            return True
```
to:
```python
        try:
            from . import gui as doorsplus_gui
            FreeCADGui.Control.showDialog(doorsplus_gui.DoorsPlusTaskPanel(obj))
            return True
```

In `repositionDoor()`, change:
```python
        try:
            import doorsplus_gui
            doorsplus_gui.repositionDoor(self.Object)
```
to:
```python
        try:
            from . import gui as doorsplus_gui
            doorsplus_gui.repositionDoor(self.Object)
```
(Only the `import doorsplus_gui` line changes at each site — same local
name, so nothing else on either site needs touching.)

- [ ] **Step 6: Create the compatibility shim at the old `doorsplus_object.py` path**

Create `doorsplus_object.py` (repo root) with exactly this content:
```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Backward-compatibility shim — DO NOT DELETE.
#
# Documents saved with ArchPlus before the per-tool-folder reorganization
# pickle their Door object's Proxy by this exact module path
# ("doorsplus_object._Window" / "_ViewProviderWindow"). FreeCAD's unpickler
# resolves the class via plain getattr(import(module), name), regardless of
# that class's own __module__ attribute — so this module must keep
# existing and keep exposing these two names for as long as any such
# document might still be opened. The real implementation lives in
# doors/object.py now; nothing here does anything but re-export.
#
# Windows keeps its own separate copy of these same two class names under
# windowsplus_object.py / windows.object — the two stay distinct because
# they resolve through different module names, exactly as they already do
# today.

from doors.object import _Window, _ViewProviderWindow  # noqa: F401
```

- [ ] **Step 7: Update `InitGui.py`'s Doors import**

Change:
```python
        import doorsplus_gui    # noqa: F401
```
to:
```python
        import doors.gui        # noqa: F401
```

- [ ] **Step 8: Move and fix the Doors test file**

```bash
mkdir -p tests/doors
git mv tests/test_doors.py tests/doors/test_doors.py
```

Change its import:
```python
import doorsplus_gui as dg
```
to:
```python
from doors import gui as dg
```

- [ ] **Step 9: Run the full suite**

Run: `uv run --with pytest --no-project pytest tests/ -q`
Expected: PASS, same 162-test count.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor: move Doors into doors/ package, add compat shim for saved documents"
```

---

### Task 3: Move Windows into `windows/`, add its compat shim, fix imports and paths

**Files:**
- Create: `windows/__init__.py`
- Move: `windowsplus_gui.py` → `windows/gui.py`
- Move: `windowsplus_object.py` → `windows/object.py`
- Create: `windowsplus_object.py` (new content — compat shim)
- Modify: `InitGui.py`
- Move: `tests/test_windows.py` → `tests/windows/test_windows.py`

**Interfaces:**
- Produces: `windows.gui` (with its own GUI-level `makeWindow()` convenience
  factory and the Task panel) and `windows.object` (with `_Window`,
  `_ViewProviderWindow`, and its own internal `makeWindow()` used by the
  panel's accept path — same class and function names as Doors' `_object.py`,
  but a separate module, so no collision). Root-level `windowsplus_object`
  continues to exist as a 2-line shim exposing `_Window`/`_ViewProviderWindow`
  only.
- Consumes: nothing from Tasks 1-2 — independent.

- [ ] **Step 1: Baseline check**

Run: `uv run --with pytest --no-project pytest tests/ -q`
Expected: PASS, same count as Task 2 left it at.

- [ ] **Step 2: Move the files**

```bash
mkdir -p windows
touch windows/__init__.py
git mv windowsplus_gui.py windows/gui.py
git mv windowsplus_object.py windows/object.py
git add windows/__init__.py
```

- [ ] **Step 3: Fix `windows/gui.py`'s `_DIR` and drop the `sys.path` hack**

Change:
```python
import json
import math
import os
import sys

import FreeCAD
import FreeCADGui
from PySide import QtGui, QtCore

_DIR = os.path.dirname(__file__)
if _DIR not in sys.path:
    sys.path.append(_DIR)

ICON = os.path.join(_DIR, "Resources", "icons", "WindowsPlus.svg")
```
to:
```python
import json
import math
import os

import FreeCAD
import FreeCADGui
from PySide import QtGui, QtCore

_DIR = os.path.dirname(os.path.dirname(__file__))     # repo root, for Resources/

ICON = os.path.join(_DIR, "Resources", "icons", "WindowsPlus.svg")
```
(`import sys` removed — verified no other use in this file. The
`_refImage()` method's `os.path.join(_DIR, "Resources", "icons", name +
".svg")` line needs no separate edit.)

- [ ] **Step 4: Fix the three lazy in-function imports in `windows/gui.py`**

Each becomes `from . import object as windowsplus_object` — same local
name. Find each by its surrounding function:

| Function | Before | After |
| --- | --- | --- |
| `makeWindow()` (module-level factory) | `import windowsplus_object` | `from . import object as windowsplus_object` |
| the panel's `_startPreview()` | `import windowsplus_object` | `from . import object as windowsplus_object` |
| the panel's accept/commit path (creates the window via `makeWindow`) | `import windowsplus_object` | `from . import object as windowsplus_object` |

- [ ] **Step 5: `windows/object.py` needs no path fix, but DOES need an import fix (see Step 5a)**

Same as Doors (Task 2 Step 5): this file's `_ViewProviderWindow.getIcon()`
uses `Arch_rc` Qt resource paths, no filesystem `_DIR`. There IS a
cross-module import to fix, though — two sites, handled in Step 5a below
(this mirrors Doors exactly; Doors needed a post-hoc fix round for the
identical pattern — see the plan header's correction note — Windows gets
it correctly the first time).

- [ ] **Step 5a: Fix the reverse lazy imports — `windows/object.py` importing `windowsplus_gui`**

Two sites in `_ViewProviderWindow` lazily import the sibling GUI module —
one to reopen the Task panel (double-click / native Edit), one for the
"Reposition (pick point)" context-menu command. Same pattern as the
`_gui.py` → `_object.py` imports fixed in Step 4, just in the opposite
direction.

In `_openWindowsPlusPanel()`, change:
```python
        try:
            import windowsplus_gui
            FreeCADGui.Control.showDialog(windowsplus_gui.WindowsPlusTaskPanel(obj))
            return True
```
to:
```python
        try:
            from . import gui as windowsplus_gui
            FreeCADGui.Control.showDialog(windowsplus_gui.WindowsPlusTaskPanel(obj))
            return True
```

In `repositionWindow()`, change:
```python
        try:
            import windowsplus_gui
            windowsplus_gui.repositionWindow(self.Object)
```
to:
```python
        try:
            from . import gui as windowsplus_gui
            windowsplus_gui.repositionWindow(self.Object)
```
(Only the `import windowsplus_gui` line changes at each site — same local
name, so nothing else on either site needs touching.)

- [ ] **Step 6: Create the compatibility shim at the old `windowsplus_object.py` path**

Create `windowsplus_object.py` (repo root) with exactly this content:
```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Backward-compatibility shim — DO NOT DELETE.
#
# Documents saved with ArchPlus before the per-tool-folder reorganization
# pickle their Window object's Proxy by this exact module path
# ("windowsplus_object._Window" / "_ViewProviderWindow"). FreeCAD's
# unpickler resolves the class via plain getattr(import(module), name),
# regardless of that class's own __module__ attribute — so this module
# must keep existing and keep exposing these two names for as long as any
# such document might still be opened. The real implementation lives in
# windows/object.py now; nothing here does anything but re-export.
#
# Doors keeps its own separate copy of these same two class names under
# doorsplus_object.py / doors.object — the two stay distinct because they
# resolve through different module names, exactly as they already do
# today.

from windows.object import _Window, _ViewProviderWindow  # noqa: F401
```

- [ ] **Step 7: Update `InitGui.py`'s Windows import**

Change:
```python
        import windowsplus_gui  # noqa: F401
```
to:
```python
        import windows.gui      # noqa: F401
```

At this point, `InitGui.py`'s `add_ui()` import block should read:
```python
        import stairs.gui       # noqa: F401
        import doors.gui        # noqa: F401
        import windows.gui      # noqa: F401
        import partslib.gui     # noqa: F401
```

- [ ] **Step 8: Move and fix the Windows test file**

```bash
mkdir -p tests/windows
git mv tests/test_windows.py tests/windows/test_windows.py
```

Change its import:
```python
import windowsplus_gui as wg
```
to:
```python
from windows import gui as wg
```

- [ ] **Step 9: Run the full suite**

Run: `uv run --with pytest --no-project pytest tests/ -q`
Expected: PASS, same 162-test count.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor: move Windows into windows/ package, add compat shim for saved documents"
```

---

### Task 4: Update tests/README.md, full verification

**Files:**
- Modify: `tests/README.md`

**Interfaces:** none — this task only touches one doc file and runs checks.

- [ ] **Step 1: Fix the one stale module-name reference in `tests/README.md`**

Change:
```
Geometry that needs the real kernel (the actual solid built by
`windowsplus_object` / `doorsplus_object`) is out of scope here — verify that
in FreeCAD.
```
to:
```
Geometry that needs the real kernel (the actual solid built by
`windows.object` / `doors.object`) is out of scope here — verify that
in FreeCAD.
```

- [ ] **Step 2: Commit the doc fix**

```bash
git add tests/README.md
git commit -m "docs: update tests/README.md module references to the new package names"
```

- [ ] **Step 3: Run the full automated suite one more time**

Run: `uv run --with pytest --no-project pytest tests/ -q`
Expected: PASS, same 162-test count throughout this whole plan.

- [ ] **Step 4: Manual smoke test in FreeCAD — new placements**

Open FreeCAD 1.1, switch to the **BIM** workbench, and confirm:
1. The **ArchPlus** toolbar still shows all four tools (Stairs, Doors,
   Windows, Parts Library) with correct icons — no console errors about a
   missing `stairsplus_gui`/`doorsplus_gui`/`windowsplus_gui` module.
2. **Stairs:** click Stairs → configure → OK. Double-click the placed
   stairs object to reopen the panel and confirm it edits correctly.
3. **Doors:** click Doors → click a wall face to place → configure in the
   panel. Double-click (or right-click → Edit) to reopen; right-click →
   Reposition to move it.
4. **Windows:** same as Doors — place, edit, reposition.

- [ ] **Step 5: Manual smoke test in FreeCAD — backward compatibility (the important one)**

This is the check that actually exercises the compatibility shims from
Tasks 1-3, which nothing in the automated suite can touch:
1. Open one of your **existing real project files** (saved before this
   refactor) that contains a Stairs, Doors, or Windows object placed by
   ArchPlus.
2. Confirm the object's geometry still displays (expected regardless — the
   shape itself is cached in the file).
3. Confirm you can **double-click the object to edit it** and the panel
   opens with its current values loaded correctly. This is the step that
   proves the compatibility shim actually works — if it silently failed,
   this is where it would show up (either an error in the Report view
   naming a module, or the edit panel not opening at all).
4. Make a small change and confirm it recomputes correctly.

If step 5 fails for any object type, that means the shim for that tool
needs fixing before this branch is safe to merge — stop and report which
tool and what error appeared in FreeCAD's Report view.
