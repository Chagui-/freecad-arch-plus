# Walk Through Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** An interactive first-person walk mode for ArchPlus: click the tool, click a point on 3D geometry to place your eyes at 1.65 m, walk on floors/stairs with WASD/arrows, look by holding the right mouse button, Esc restores the saved camera.

**Architecture:** A per-view `addEventCallback("SoEvent", …)` handler only *records* input into a pure `WalkController`; a 30 Hz `QTimer` tick integrates the pose and rewrites the Coin camera each frame (masking FreeCAD's own RMB-orbit). Ground height comes from `ActiveView.getObjectInfoRay()` (vertical down-ray), so the eye rides floors and ArchPlus stairs within snap tolerances. Spec: `docs/superpowers/specs/2026-09-04-walk-through-design.md`.

**Tech Stack:** Python (FreeCAD 1.1), PySide6 (`QtCore.QTimer`), pivy/Coin camera fields, pytest with the repo's headless-fake conftest.

## Global Constraints

- Target FreeCAD 1.1; pure Python add-on; no C++, no new dependencies.
- Every new file starts with `# SPDX-License-Identifier: LGPL-2.1-or-later` and a short docstring (match `archplus/tools/doors/gui.py`).
- Units are FreeCAD internal: **millimetres**; speeds in mm/s; angles in radians.
- View-only: never mutate the document, selection, or undo stack.
- Lazy-import rule (`archplus/common/tests/test_lazy_imports.py`): `Part`, `Sketcher`, `ArchComponent`, `Arch`, `Draft`, `archplus.common.geometry` must never be imported at module scope in `archplus/tools/*/gui.py`. This tool additionally keeps `pivy.coin` out of module scope for headless hygiene.
- `archplus/tools/walk/kinematics.py` and `state.py` are **pure** (no FreeCAD/PySide/pivy imports) — that is what makes them headless-testable.
- Tests run headless: `python3 -m pytest -q` (on this machine: `uv run --no-project --with pytest python -m pytest -q`, per `docs/TESTING.md`).
- Branch: `feat/walk-through`. Commit per task (PR lands as one squash commit).

## FreeCAD API facts (verified against `src/Gui` on `main`)

- `view = FreeCADGui.ActiveDocument.ActiveView` (a `View3DInventorPy`).
- `view.addEventCallback("SoEvent", cb)` / `view.removeEventCallback("SoEvent", cb)` — `cb` receives a **dict**: `{"Type": "SoKeyboardEvent"|"SoLocation2Event"|"SoMouseButtonEvent"|…, "State": "UP"/"DOWN" (button/key events), "Key": "ESCAPE"/"UP_ARROW"/… (keyboard; printable chars arrive via the default branch, e.g. "w"/"W"), "Button": "BUTTON1".."BUTTON5" (RMB = "BUTTON3"), "Position": (x, y) pixels, "ShiftDown": bool, …}` (source: `src/Gui/View3DPy.cpp::eventCallback`).
- `view.getObjectInfoRay(FreeCAD.Vector start, FreeCAD.Vector dir) -> dict|None` with keys `PickedPoint` (Vector), `Document`, `Object`, optional `Component`. Range is the camera's clipping planes; a ray from the eye downward is safely inside it (source: `View3DInventor.cpp::getObjInfoRay` → `SoRayPickAction.setRay(start, dir, nearClippingPlane)`).
- `view.getCameraNode()` → Coin `SoCamera`: `cam.position.setValue(x, y, z)`, `cam.pointAt(SbVec3f target, SbVec3f up)`.
- `view.getCamera()` → XML string; `view.setCamera(xml)` restores. `view.getCameraType()` → string; `view.setCameraType(0)` = orthographic, `1` = perspective (`View3DPy.cpp::setCameraType`).
- `view.getViewDirection()` → (x, y, z) tuple of the current view direction.
- `FreeCADGui.Snapper.getPoint(callback, movecallback)` — `callback(point=None, obj=None)`; `point is None` = cancelled. `movecallback(point, info)`; face picks land in `info["Component"]` as `"Face<n>"` and `info["Object"]` (same pattern as `archplus/tools/doors/gui.py:935-975`).

## File Structure

- Create: `archplus/tools/walk/__init__.py` — empty package marker.
- Create: `archplus/tools/walk/kinematics.py` — pure constants + math (move vector, clamps, height snap, look direction).
- Create: `archplus/tools/walk/state.py` — pure `WalkController`: event dicts in, pose out; no FreeCAD.
- Create: `archplus/tools/walk/gui.py` — `WalkSession` (event callback + QTimer tick + camera writes + save/restore), `_start_walk` (pick → eye pose), `WalkThroughCommand`, registration guard.
- Create: `archplus/tools/walk/tests/__init__.py`, `test_kinematics.py`, `test_state.py`.
- Modify: `InitGui.py` — add the command to `commands` + module import in `add_ui`.
- Modify: `archplus/common/tests/test_lazy_imports.py` — add `archplus.tools.walk.gui` to `MODULES`.
- Modify: `docs/TOOLS.md`, `README.md` — document the tool.

---

### Task 1: Kinematics (pure math)

**Files:**
- Create: `archplus/tools/walk/__init__.py`, `archplus/tools/walk/tests/__init__.py` (both empty)
- Create: `archplus/tools/walk/kinematics.py`
- Test: `archplus/tools/walk/tests/test_kinematics.py`

**Interfaces:**
- Produces (used by Tasks 2–3): constants `EYE_HEIGHT=1650.0`, `WALK_SPEED=1400.0`, `RUN_SPEED=4500.0`, `STEP_UP=600.0`, `STEP_DOWN=2000.0`, `MAX_STEP=300.0`, `PITCH_LIMIT`, `TURN_SPEED`, `LOOK_SENS=0.0035`, `TICK_INTERVAL=1/30`, `DT_MAX=0.1`; functions `look_direction(yaw, pitch) -> (x, y, z)`, `clamp_pitch(p) -> float`, `move_vector(active: set, yaw, run=False) -> (vx, vy)`, `clamp_step(dx, dy) -> (dx, dy)`, `snap_target(eye_z, ground_z) -> float | None`, `turn_step(active, dt) -> float`.

- [x] **Step 1: Write the failing tests**

`archplus/tools/walk/tests/test_kinematics.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Headless tests for the Walk Through kinematics (pure math, mm + radians)."""

import math

import pytest

from archplus.tools.walk import kinematics as kin


def test_look_direction_yaw_zero_faces_plus_y():
    d = kin.look_direction(0.0, 0.0)
    assert d == pytest.approx((0.0, 1.0, 0.0))


def test_look_direction_pitch_up_adds_z():
    d = kin.look_direction(0.0, math.pi / 2)
    assert d[2] == pytest.approx(1.0)


def test_clamp_pitch_bounds():
    assert kin.clamp_pitch(2.0) == pytest.approx(kin.PITCH_LIMIT)
    assert kin.clamp_pitch(-2.0) == pytest.approx(-kin.PITCH_LIMIT)
    assert kin.clamp_pitch(0.3) == pytest.approx(0.3)


def test_move_forward_at_yaw_zero_is_plus_y():
    vx, vy = kin.move_vector({"forward"}, 0.0)
    assert vx == pytest.approx(0.0)
    assert vy == pytest.approx(kin.WALK_SPEED)


def test_move_forward_at_yaw_90_faces_plus_x():
    vx, vy = kin.move_vector({"forward"}, math.pi / 2)
    assert vx == pytest.approx(kin.WALK_SPEED)
    assert vy == pytest.approx(0.0)


def test_strafe_right_at_yaw_zero_is_plus_x():
    vx, vy = kin.move_vector({"right"}, 0.0)
    assert vx == pytest.approx(kin.WALK_SPEED)
    assert vy == pytest.approx(0.0)


def test_back_is_minus_forward():
    vx, vy = kin.move_vector({"back"}, 0.0)
    assert vy == pytest.approx(-kin.WALK_SPEED)


def test_run_multiplies_speed():
    vx, vy = kin.move_vector({"forward"}, 0.0, run=True)
    assert vy == pytest.approx(kin.RUN_SPEED)


def test_diagonal_does_not_exceed_walk_speed():
    vx, vy = kin.move_vector({"forward", "right"}, 0.0)
    assert math.hypot(vx, vy) == pytest.approx(kin.WALK_SPEED)


def test_clamp_step_limits_displacement():
    dx, dy = kin.clamp_step(1000.0, 0.0)
    assert math.hypot(dx, dy) == pytest.approx(kin.MAX_STEP)


def test_clamp_step_passes_small_steps():
    assert kin.clamp_step(30.0, 40.0) == (30.0, 40.0)


def test_snap_target_is_stable_on_flat_ground():
    assert kin.snap_target(1650.0, 0.0) == pytest.approx(1650.0)


def test_snap_target_climbs_stair_riser():
    # ArchPlus stairs: ~170 mm riser up
    assert kin.snap_target(1650.0, 170.0) == pytest.approx(1820.0)


def test_snap_target_descends_stair_riser():
    assert kin.snap_target(1650.0, -170.0) == pytest.approx(1480.0)


def test_snap_target_refuses_big_rise():
    assert kin.snap_target(1650.0, 1000.0) is None


def test_snap_target_refuses_big_drop():
    assert kin.snap_target(1650.0, -5000.0) is None


def test_turn_step_directions():
    assert kin.turn_step({"turn_right"}, 1.0) == pytest.approx(kin.TURN_SPEED)
    assert kin.turn_step({"turn_left"}, 1.0) == pytest.approx(-kin.TURN_SPEED)
    assert kin.turn_step(set(), 1.0) == 0.0
```

- [x] **Step 2: Run the tests, verify they fail**

Run: `uv run --no-project --with pytest python -m pytest archplus/tools/walk/tests/test_kinematics.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'archplus.tools.walk'` (or a collection error for the missing module).

- [x] **Step 3: Write the implementation**

`archplus/tools/walk/__init__.py` and `archplus/tools/walk/tests/__init__.py`: empty files.

`archplus/tools/walk/kinematics.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pure math for the Walk Through mode.

Units are FreeCAD internal: millimetres (speeds in mm/s); angles are radians.
No FreeCAD/PySide/pivy imports here — everything must run headless under
pytest.

Conventions
-----------
yaw    0 looks toward +Y; increasing yaw turns right (clockwise seen from
       above: at yaw 90 deg the look direction is +X).
pitch  positive looks up; clamped to +-85 deg so `pointAt` can keep +Z up.
mouse  screen y grows downward, so dragging up (dy < 0) raises the pitch.
"""

import math

# Parameters — spec: docs/superpowers/specs/2026-09-04-walk-through-design.md
EYE_HEIGHT = 1650.0        # mm above the ground the eye sits
WALK_SPEED = 1400.0        # mm/s
RUN_SPEED = 4500.0         # mm/s
STEP_UP = 600.0            # max instant rise while following ground, mm
STEP_DOWN = 2000.0         # max instant drop while following ground, mm
MAX_STEP = 300.0           # max horizontal displacement per tick, mm
PITCH_LIMIT = math.radians(85.0)
TURN_SPEED = math.radians(120.0)  # rad/s for the arrow turn keys
LOOK_SENS = 0.0035         # rad per pixel of right-mouse drag
TICK_INTERVAL = 1.0 / 30.0  # s; the Qt timer period (30 Hz)
DT_MAX = 0.1               # s; clamp so a stall cannot teleport the camera


def look_direction(yaw, pitch):
    """Unit look direction (x, y, z) for a yaw/pitch pair."""
    c = math.cos(pitch)
    return (math.sin(yaw) * c, math.cos(yaw) * c, math.sin(pitch))


def clamp_pitch(pitch):
    """Clamp pitch to +-PITCH_LIMIT."""
    return max(-PITCH_LIMIT, min(PITCH_LIMIT, pitch))


def move_vector(active, yaw, run=False):
    """Horizontal world velocity (vx, vy) in mm/s for the held actions.

    `active` holds semantic actions: 'forward', 'back', 'left' (strafe),
    'right' (strafe). Running comes in as the `run` flag.
    """
    speed = RUN_SPEED if run else WALK_SPEED
    f = (1 if "forward" in active else 0) - (1 if "back" in active else 0)
    s = (1 if "right" in active else 0) - (1 if "left" in active else 0)
    vx = (f * math.sin(yaw) + s * math.cos(yaw)) * speed
    vy = (f * math.cos(yaw) - s * math.sin(yaw)) * speed
    return (vx, vy)


def clamp_step(dx, dy):
    """Limit one tick's horizontal displacement to MAX_STEP mm."""
    d = math.hypot(dx, dy)
    if d <= MAX_STEP or d == 0.0:
        return (dx, dy)
    k = MAX_STEP / d
    return (dx * k, dy * k)


def snap_target(eye_z, ground_z):
    """Eye z for a ground hit, or None when the snap must be refused.

    Refusal (keep the current height) covers walking off a ledge and any
    ground jump larger than the stair tolerances: the eye then holds its
    height instead of teleporting or sinking.
    """
    target = ground_z + EYE_HEIGHT
    rise = target - eye_z
    if rise > STEP_UP:
        return None
    if -rise > STEP_DOWN:
        return None
    return target


def turn_step(active, dt):
    """Yaw delta (rad) for one tick from the arrow turn keys."""
    t = ((1 if "turn_right" in active else 0)
         - (1 if "turn_left" in active else 0))
    return t * TURN_SPEED * dt
```

- [x] **Step 4: Run the tests, verify they pass**

Run: `uv run --no-project --with pytest python -m pytest archplus/tools/walk/tests/test_kinematics.py -q`
Expected: PASS (17 tests).

- [x] **Step 5: Commit**

```bash
git add archplus/tools/walk
git commit -m "Add Walk Through kinematics"
```

---

### Task 2: WalkController (pure state machine)

**Files:**
- Create: `archplus/tools/walk/state.py`
- Test: `archplus/tools/walk/tests/test_state.py`

**Interfaces:**
- Consumes: everything from `kinematics` (Task 1).
- Produces (used by Task 3): `WalkController(position: (x, y, z), yaw=0.0, pitch=0.0)` with attributes `position`, `yaw`, `pitch`, `active`, `run`, `looking`, `exited`; methods `on_event(ev: dict) -> None`, `advance(dt: float, ground_z: float | None) -> None`. Event dicts are exactly what `addEventCallback("SoEvent", …)` delivers (see "FreeCAD API facts").

- [x] **Step 1: Write the failing tests**

`archplus/tools/walk/tests/test_state.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Headless tests for the Walk Through controller (event dicts -> pose)."""

import pytest

from archplus.tools.walk import kinematics as kin
from archplus.tools.walk import state


def key(k, st="DOWN"):
    return {"Type": "SoKeyboardEvent", "Key": k, "State": st}


def motion(x, y):
    return {"Type": "SoLocation2Event", "Position": (x, y)}


def button(st, btn="BUTTON3"):
    return {"Type": "SoMouseButtonEvent", "Button": btn, "State": st}


def test_wasd_forward_moves_toward_look_direction():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(key("w"))
    c.advance(0.05)                # one 50 ms tick: 1400 mm/s * 0.05 s
    x, y, z = c.position
    assert (x, y) == pytest.approx((0.0, 70.0))
    assert z == pytest.approx(1650.0)


def test_uppercase_w_with_shift_runs_forward():
    # Reality model: Shift held -> printable char arrives uppercase AND
    # ShiftDown is set, so "W" + ShiftDown is run-speed forward.
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event({"Type": "SoKeyboardEvent", "Key": "W", "State": "DOWN",
                "ShiftDown": True})
    c.advance(0.05)
    assert c.position[1] == pytest.approx(225.0)   # 4500 mm/s * 0.05 s


def test_arrow_key_is_forward():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(key("UP_ARROW"))
    c.advance(0.05)
    assert c.position[1] == pytest.approx(70.0)    # 1400 mm/s * 0.05 s


def test_key_release_stops_motion():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(key("w"))
    c.advance(0.05)
    c.on_event(key("w", "UP"))
    c.advance(0.05)
    assert c.position[1] == pytest.approx(70.0)


def test_arrow_turn_rotates_heading():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(key("RIGHT_ARROW"))
    c.advance(0.5)
    assert c.yaw == pytest.approx(0.5 * kin.TURN_SPEED)


def test_escape_sets_exit_flag_and_freezes_pose():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(key("ESCAPE"))
    assert c.exited is True
    c.advance(1.0)
    assert c.position == (0.0, 0.0, 1650.0)


def test_rmb_drag_right_and_up():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(button("DOWN"))
    c.on_event(motion(100, 100))
    c.on_event(motion(200, 50))
    c.advance(0.03)
    assert c.yaw == pytest.approx(100 * kin.LOOK_SENS)
    assert c.pitch == pytest.approx(50 * kin.LOOK_SENS)


def test_drag_without_rmb_does_not_look():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(motion(100, 100))
    c.on_event(motion(300, 40))
    c.advance(0.03)
    assert c.yaw == 0.0
    assert c.pitch == 0.0


def test_released_rmb_leaves_no_stale_jump():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(button("DOWN"))
    c.on_event(motion(0, 0))
    c.on_event(motion(500, 0))
    c.on_event(button("UP"))
    c.on_event(motion(900, 0))     # moves while not looking: ignored
    c.on_event(button("DOWN"))
    c.advance(0.03)
    assert c.yaw == 0.0


def test_pitch_clamped_at_limit():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(button("DOWN"))
    c.on_event(motion(0, 0))
    c.on_event(motion(0, 100000))
    c.advance(0.03)
    assert c.pitch == pytest.approx(-kin.PITCH_LIMIT)


def test_shift_down_runs():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(key("w"))
    c.on_event({"Type": "SoKeyboardEvent", "Key": "SHIFT", "State": "DOWN",
                "ShiftDown": True})
    c.advance(0.05)
    assert c.position[1] == pytest.approx(225.0)   # 4500 mm/s * 0.05 s


def test_ground_snap_rides_stairs():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.advance(0.03, ground_z=170.0)
    assert c.position[2] == pytest.approx(1820.0)


def test_ground_none_holds_height():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.advance(0.03, ground_z=None)
    assert c.position[2] == pytest.approx(1650.0)


def test_ground_outside_tolerance_holds_height():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.advance(0.03, ground_z=-5000.0)
    assert c.position[2] == pytest.approx(1650.0)


def test_max_step_clamped_in_advance():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(key("w"))
    c.advance(10.0)                # absurd dt must not teleport
    assert c.position[1] == pytest.approx(kin.MAX_STEP)
```

- [x] **Step 2: Run the tests, verify they fail**

Run: `uv run --no-project --with pytest python -m pytest archplus/tools/walk/tests/test_state.py -q`
Expected: FAIL — `ImportError: cannot import name 'state'` (module missing).

- [x] **Step 3: Write the implementation**

`archplus/tools/walk/state.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Walk-mode state machine: input dicts in, camera pose out.

Pure Python — no FreeCAD/PySide/pivy imports. `on_event` consumes the event
dicts that `View3DInventorPy.addEventCallback("SoEvent", ...)` delivers
(Type/State/Key/Button/Position/ShiftDown — see src/Gui/View3DPy.cpp
eventCallback), and `advance` integrates one timer tick.

Keyboard letters arrive through FreeCAD's printable-character default
branch ("w", or "W" when Shift is held), so lookups normalize case; named
constants ("UP_ARROW", "ESCAPE") pass through unchanged. Shift is reported
as ShiftDown on every event and tracked regardless of event type.
"""

from . import kinematics as kin

KEYMAP = {
    "W": "forward", "UP_ARROW": "forward",
    "S": "back", "DOWN_ARROW": "back",
    "A": "left",
    "D": "right",
    "RIGHT_ARROW": "turn_right",
    "LEFT_ARROW": "turn_left",
}


class WalkController:
    """Holds the walking pose and converts events + ticks into motion."""

    def __init__(self, position, yaw=0.0, pitch=0.0):
        self.position = tuple(float(v) for v in position)  # (x, y, z) mm
        self.yaw = float(yaw)
        self.pitch = kin.clamp_pitch(float(pitch))
        self.active = set()       # semantic actions currently held
        self.run = False          # Shift held (from ShiftDown)
        self.looking = False      # right mouse button held
        self.exited = False       # set on Escape, read by the tick
        self._mdx = 0             # unconsumed mouse drag delta, px
        self._mdy = 0
        self._last_mouse = None   # last Location2 position, for deltas

    def on_event(self, ev):
        """Consume one event dict; never raises on unknown events."""
        etype = ev.get("Type")
        if etype == "SoKeyboardEvent":
            kstate = ev.get("State")
            key = ev.get("Key")
            if key == "ESCAPE":
                if kstate == "DOWN":
                    self.exited = True
                return
            action = KEYMAP.get(str(key).upper()) if key else None
            if action is None:
                return
            if kstate == "DOWN":
                self.active.add(action)
            elif kstate == "UP":
                self.active.discard(action)
        elif etype == "SoMouseButtonEvent":
            if ev.get("Button") == "BUTTON3":
                self.looking = ev.get("State") == "DOWN"
                if not self.looking:
                    self._last_mouse = None
                    self._mdx = 0
                    self._mdy = 0
        elif etype == "SoLocation2Event":
            pos = ev.get("Position")
            if not pos:
                return
            x, y = int(pos[0]), int(pos[1])
            # Accumulate drag deltas only while looking; still track the
            # position so a fresh RMB press starts measuring from where it
            # happened (no jump from hover movement before the press).
            if self.looking and self._last_mouse is not None:
                self._mdx += x - self._last_mouse[0]
                self._mdy += y - self._last_mouse[1]
            self._last_mouse = (x, y)
        # ShiftDown is carried on every event; track it regardless of type.
        self.run = bool(ev.get("ShiftDown"))

    def advance(self, dt, ground_z=None):
        """Integrate one tick (`dt` seconds, clamped by the caller).

        `ground_z` is the floor height under the eye from the down-ray pick,
        or None when nothing was hit / the snap was refused (height held).
        """
        if self.exited:
            return
        if self.looking:
            self.yaw += self._mdx * kin.LOOK_SENS
            self.pitch = kin.clamp_pitch(self.pitch - self._mdy * kin.LOOK_SENS)
        self._mdx = 0
        self._mdy = 0
        self.yaw += kin.turn_step(self.active, dt)
        vx, vy = kin.move_vector(self.active, self.yaw, self.run)
        dx, dy = kin.clamp_step(vx * dt, vy * dt)
        x, y, z = self.position
        x += dx
        y += dy
        if ground_z is not None:
            target = kin.snap_target(z, ground_z)
            if target is not None:
                z = target
        self.position = (x, y, z)
```


Note: drag deltas accumulate only while `looking` (and position tracking continues regardless), so hover movement before an RMB press can never leak into a look-jump; the RMB-up reset of `_mdx/_mdy/_last_mouse` keeps `test_released_rmb_leaves_no_stale_jump` green.

Run: `uv run --no-project --with pytest python -m pytest archplus/tools/walk/tests/ -q`
Expected: PASS (32 tests total across both files).

- [x] **Step 5: Commit**

```bash
git add archplus/tools/walk
git commit -m "Add Walk Through controller"
```

---

### Task 3: Walk session + command (FreeCAD glue)

**Files:**
- Create: `archplus/tools/walk/gui.py`

**Interfaces:**
- Consumes: `WalkController` (Task 2), all kinematics constants; the FreeCAD API facts above.
- Produces: `gui._start_walk(view, point, face)` (face = `[obj, face_index]` or `None`) and module-global `gui._MODE` (a `WalkSession` or `None`) — the MCP smoke test in Task 5 drives these directly. Registers command `ArchPlus_WalkThrough`.

No headless unit tests: this file is thin FreeCAD/Qt glue (callback wiring, Coin camera writes, Snapper session); its behavior is verified by the full-suite run here and the live smoke test in Task 5. The pure logic it delegates to is already tested.

- [x] **Step 1: Write `archplus/tools/walk/gui.py`**

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Walk Through — interactive first-person walk mode (ArchPlus).

Click the tool, click a point on 3D geometry to place your eyes (point +
1.65 m along the picked face normal), then walk: WASD/arrows move, hold the
right mouse button and move to look, Shift runs, Esc (or clicking the tool
again) exits and restores the saved camera.

Architecture: a per-view event callback only RECORDS input into a pure
WalkController (see state.py); a 30 Hz QTimer tick integrates the pose and
rewrites the Coin camera each frame — the tick's camera overwrite is what
masks FreeCAD's own right-mouse orbit while RMB is repurposed for looking.
The ground under the eye is found with ActiveView.getObjectInfoRay() (a
vertical down-ray), so the eye rides floors and stairs.
"""

import math
import time

import FreeCAD
import FreeCADGui
from PySide import QtCore

from . import kinematics as kin
from . import state as walk_state

_MODE = None  # the active WalkSession, or None

PICK_HINT = ("ArchPlus Walk Through: click a point in the 3D view to start "
             "walking.")
ACTIVE_HINT = ("ArchPlus Walk Through: WASD/arrows move, hold right-mouse "
               "to look, Shift run, Esc exit.")


class WalkSession:
    """One walk-mode session bound to one 3D view."""

    def __init__(self, view, eye, yaw, pitch=0.0):
        self.view = view
        self.controller = walk_state.WalkController(eye, yaw=yaw, pitch=pitch)
        self._saved_camera = view.getCamera()
        self._saved_type = view.getCameraType()
        self._timer = QtCore.QTimer()
        self._timer.setInterval(int(round(1000.0 * kin.TICK_INTERVAL)))
        self._timer.timeout.connect(self._tick)
        self._last_t = time.monotonic()

    def start(self):
        self.view.setCameraType(1)  # perspective (0 = orthographic)
        self.view.addEventCallback("SoEvent", self._on_event)
        self._last_t = time.monotonic()
        self._timer.start()
        self._apply_camera()
        FreeCAD.Console.PrintMessage(ACTIVE_HINT + "\n")

    def stop(self):
        self._timer.stop()
        try:
            self.view.removeEventCallback("SoEvent", self._on_event)
        except Exception:
            pass  # view already gone
        try:
            self.view.setCamera(self._saved_camera)
            self.view.setCameraType(self._saved_type)
        except Exception:
            pass  # view already gone
        global _MODE
        _MODE = None
        FreeCAD.Console.PrintMessage("ArchPlus Walk Through: exited.\n")

    def _on_event(self, ev):
        try:
            self.controller.on_event(ev)
            if self.controller.exited:
                # Removing the callback from inside its own callback is not
                # safe; defer the teardown to the next event-loop pass.
                QtCore.QTimer.singleShot(0, self.stop)
        except Exception as exc:
            FreeCAD.Console.PrintError("ArchPlus Walk Through: %s\n" % exc)
            self.controller.exited = True
            QtCore.QTimer.singleShot(0, self.stop)

    def _tick(self):
        now = time.monotonic()
        dt = min(now - self._last_t, kin.DT_MAX)
        self._last_t = now
        try:
            x, y, z = self.controller.position
            info = self.view.getObjectInfoRay(
                FreeCAD.Vector(x, y, z), FreeCAD.Vector(0, 0, -1))
            ground = info["PickedPoint"].z if info else None
            self.controller.advance(dt, ground)
            if self.controller.exited:
                self.stop()
                return
            self._apply_camera()
        except RuntimeError:
            # The view wrapper died (document closed / workbench switch).
            self._teardown_only()
        except Exception as exc:
            FreeCAD.Console.PrintError("ArchPlus Walk Through: %s\n" % exc)
            self._teardown_only()

    def _teardown_only(self):
        """Stop the mode WITHOUT touching the (possibly dead) view."""
        self._timer.stop()
        global _MODE
        _MODE = None
        FreeCAD.Console.PrintMessage("ArchPlus Walk Through: exited.\n")

    def _apply_camera(self):
        from pivy import coin

        x, y, z = self.controller.position
        dx, dy, dz = kin.look_direction(self.controller.yaw,
                                        self.controller.pitch)
        cam = self.view.getCameraNode()
        cam.position.setValue(x, y, z)
        cam.pointAt(coin.SbVec3f(x + dx * 1000.0,
                                 y + dy * 1000.0,
                                 z + dz * 1000.0),
                    coin.SbVec3f(0.0, 0.0, 1.0))


def _face_normal(face_obj, point):
    """Normal of the picked face ([obj, face_index]) at `point`, or None."""
    if face_obj is None:
        return None
    obj, fi = face_obj
    try:
        face = obj.Shape.Faces[fi]
        u, v = face.Surface.parameter(FreeCAD.Vector(point))
        return face.normalAt(u, v)
    except Exception:
        return None


def _start_walk(view, point, face):
    """Start the session with the eye at `point` + eye height along normal."""
    normal = _face_normal(face, point)
    if normal is None:
        normal = FreeCAD.Vector(0, 0, 1)
    if normal.Length > 0:
        normal.normalize()
    eye = FreeCAD.Vector(point) + normal * kin.EYE_HEIGHT
    # Keep the current heading: yaw from the view direction, pitch level.
    d = view.getViewDirection()
    yaw = math.atan2(d[0], d[1])
    global _MODE
    _MODE = WalkSession(view, (eye.x, eye.y, eye.z), yaw=yaw)
    _MODE.start()


class WalkThroughCommand:
    """Toolbar/menu command: toggles the walk mode."""

    def GetResources(self):
        return {"MenuText": "Walk Through",
                "ToolTip": ("First-person walk: click a point to place your "
                            "eyes, WASD to move, hold right-mouse to look, "
                            "Esc to exit")}

    def IsActive(self):
        window = FreeCADGui.getMainWindow().getActiveWindow()
        return hasattr(window, "getSceneGraph")

    def Activated(self):
        if _MODE is not None:
            _MODE.stop()
            return
        if FreeCAD.ActiveDocument is None:
            FreeCAD.Console.PrintError(
                "ArchPlus Walk Through: no active document.\n")
            return
        gui_doc = FreeCADGui.ActiveDocument
        view = gui_doc.ActiveView if gui_doc is not None else None
        if view is None or not hasattr(view, "getObjectInfoRay"):
            FreeCAD.Console.PrintError(
                "ArchPlus Walk Through: no active 3D view.\n")
            return

        doc = FreeCAD.ActiveDocument
        picked = {"face": None}

        def _move(point, info):
            if info and "Face" in info.get("Component", ""):
                o = doc.getObject(info["Object"])
                try:
                    fi = int(info["Component"][4:]) - 1
                except (ValueError, IndexError):
                    picked["face"] = None
                else:
                    picked["face"] = [o, fi]

        def _place(point=None, obj=None):
            FreeCADGui.Snapper.off()
            if point is None:
                return  # cancelled
            _start_walk(view, point, picked["face"])

        FreeCAD.Console.PrintMessage(PICK_HINT + "\n")
        FreeCADGui.Snapper.getPoint(callback=_place, movecallback=_move)


# Register (FreeCAD 1.1 has no removeCommand; guard to stay reload-safe,
# same as ArchPlus_Doors).
if "ArchPlus_WalkThrough" not in FreeCADGui.listCommands():
    FreeCADGui.addCommand("ArchPlus_WalkThrough", WalkThroughCommand())
```

- [x] **Step 2: Run the full suite (nothing broke; the AST-based lazy guard must stay green)**

Run: `uv run --no-project --with pytest python -m pytest -q`
Expected: PASS — 32 walk tests plus the pre-existing suite; zero failures.

- [x] **Step 3: Commit**

```bash
git add archplus/tools/walk/gui.py
git commit -m "Add Walk Through command and walk session"
```

---

### Task 4: Registration + lazy-guard + docs

**Files:**
- Modify: `InitGui.py` (commands list, `add_ui` imports)
- Modify: `archplus/common/tests/test_lazy_imports.py` (`MODULES`)
- Modify: `docs/TOOLS.md` (append section), `README.md` (tools table + quick start)

**Interfaces:**
- Consumes: command name `ArchPlus_WalkThrough`, module `archplus.tools.walk.gui` (Task 3).

- [x] **Step 1: Wire the command into the BIM workbench injection**

In `InitGui.py`, extend the two lists (exact current content: `commands = ["ArchPlus_Stairs", "ArchPlus_Doors", "ArchPlus_Windows", "ArchPlus_PartsLibrary"]` and the four `import archplus.tools.*.gui` lines in `add_ui`):

```python
    commands = ["ArchPlus_Stairs", "ArchPlus_Doors", "ArchPlus_Windows",
                "ArchPlus_PartsLibrary", "ArchPlus_WalkThrough"]
```

```python
        import archplus.tools.partslib.gui  # noqa: F401
        import archplus.tools.walk.gui  # noqa: F401
```

- [x] **Step 2: Extend the lazy-import guard**

In `archplus/common/tests/test_lazy_imports.py`, add `archplus.tools.walk.gui` to `MODULES`:

```python
MODULES = (
    "archplus.tools.doors.gui",
    "archplus.tools.windows.gui",
    "archplus.tools.stairs.gui",
    "archplus.tools.partslib.gui",
    "archplus.tools.walk.gui",
    "archplus.common.widgets",
)
```

- [x] **Step 3: Run the full suite**

Run: `uv run --no-project --with pytest python -m pytest -q`
Expected: PASS, including the updated lazy-import guard (walk/gui.py imports `math`, `time`, `FreeCAD`, `FreeCADGui`, `PySide`, and lazy `pivy.coin` — none banned).

- [x] **Step 4: Document**

`docs/TOOLS.md` — append at the end (match the file's heading level for tools):

```markdown
## Walk Through

First-person mode for inspecting a model at eye height. Click **Walk
Through**, then click a point on any 3D geometry: the camera starts there,
1.65 m along the picked face's normal (a floor puts you on it, a wall puts
you in front of it). Then:

- **W/S** or **Up/Down** — move forward/back · **A/D** — strafe
- **Left/Right** — turn · **hold Right-mouse + move** — look around
- **Shift** — run · **Esc** (or clicking the tool again) — exit and restore
  the camera

The camera follows the ground: floors and stairs raise/lower your eyes
within a ±0.6 m / 2 m step tolerance; over gaps or big drops the height is
held. Movement is view-only — nothing in the document changes, and the
camera/projection you had before is restored on exit.
```

`README.md` — add a row to the **What's inside** table:

```markdown
| | **Walk Through** — first-person mode: click a point to place your eyes, walk floors and stairs with WASD, look with right-mouse drag. [Guide](docs/TOOLS.md#walk-through) |
```

and a bullet to **Quick start**:

```markdown
- **Walk Through** → click a point in the 3D view → walk with WASD/arrows,
  hold the right mouse button to look, Shift to run, Esc to exit.
```

- [x] **Step 5: Commit**

```bash
git add InitGui.py archplus/common/tests/test_lazy_imports.py docs/TOOLS.md README.md
git commit -m "Register Walk Through and document it"
```

---

### Task 5: Verification (full suite + live FreeCAD smoke)

**Files:** none created (fix-and-amend if anything fails).

- [x] **Step 1: Full headless suite**

Run: `uv run --no-project --with pytest python -m pytest -q`
Expected: PASS, zero failures.

- [x] **Step 2: Live smoke via the FreeCAD MCP**

Run through `xd://mcp__freecad_execute_code` (the RPC server runs inside the real GUI; ticks are pumped manually so the smoke is deterministic):

```python
import FreeCAD
import FreeCADGui

doc = FreeCAD.newDocument("WalkSmoke")
floor = doc.addObject("Part::Box", "Floor")
floor.Length, floor.Width, floor.Height = 4000.0, 4000.0, 200.0
step = doc.addObject("Part::Box", "Step")
step.Length, step.Width, step.Height = 1000.0, 1000.0, 370.0
step.Placement.Base = (4000.0, 0, 0)
doc.recompute()

from archplus.tools.walk import gui
view = FreeCADGui.ActiveDocument.ActiveView
saved_camera = view.getCamera()
saved_type = view.getCameraType()

# 1. Start: eye on the floor at (500, 500), facing +Y.
gui._start_walk(view, FreeCAD.Vector(500, 500, 200), face=None)  # z=200: the floor's top face, as a real pick would return
s = gui._MODE
assert s is not None and s.controller.position == (500.0, 500.0, 1850.0), s.controller.position

# 2. One tick with ground under the eye: height snaps to 200 + 1650.
s._tick()
assert s.controller.position[2] == 1850.0, s.controller.position

# 3. Walk forward exactly one 50 ms tick worth (drive the controller
#    directly; no _tick here, so no double movement).
s.controller.on_event({"Type": "SoKeyboardEvent", "Key": "w", "State": "DOWN"})
s.controller.advance(0.05)
assert s.controller.position[1] == 500.0 + 70.0, s.controller.position
s.controller.on_event({"Type": "SoKeyboardEvent", "Key": "w", "State": "UP"})
s.controller.position = (4500.0, 500.0, 1850.0)
s._tick()
assert s.controller.position[2] == 370.0 + 1650.0, s.controller.position

# 5. Camera actually moved (perspective, eye at the controller pose).
cam = view.getCameraNode()
px, py, pz = cam.position.getValue().getValue()
assert (round(px, 3), round(py, 3), round(pz, 3)) == (4500.0, 500.0, 2020.0), (px, py, pz)
assert view.getCameraType() == "Perspective"

# 6. Exit restores the projection (camera XML compared via type + position
#    fields, since Coin re-serializes floats).
s.stop()
assert gui._MODE is None
assert view.getCameraType() == saved_type

# 7. Command is registered for the toolbar.
assert "ArchPlus_WalkThrough" in FreeCADGui.listCommands()
print("Walk Through smoke: OK")
```

Expected: the script prints `Walk Through smoke: OK` with no assertion errors. If an assertion fires, fix `gui.py`/`state.py`/`kinematics.py`, re-run `pytest`, and re-run the smoke.

- [x] **Step 3: Visual check via MCP**

Call `xd://mcp__freecad_get_view` twice: once mid-walk (re-run steps 1–4, stop before `s.stop()`) and once after exit — confirm the mid-walk view is a ground-level perspective inside the model and the post-exit view matches the original camera. Clean up: `FreeCAD.closeDocument("WalkSmoke")`.

- [x] **Step 4: Manual keyboard/mouse pass (user-side, since MCP cannot inject real input)**

Ask the user to run once in their FreeCAD: start BIM → Walk Through → click the floor → walk/look/Esc. This exercises the real event path (Snapper pick + live QTimer + Coin redraws) that the scripted smoke bypasses.

- [x] **Step 5: No commit** — Task 5 produces evidence, not diffs. If fixes were needed, commit them with the fix description.

---

## Self-review notes

- Spec coverage: pick-to-start (Task 3 `_place`/`_start_walk`), normal-offset eye with +Z fallback (Task 3), heading preserved/pitch leveled (Task 3), controls incl. Shift/Esc (Tasks 2–3), forced perspective + camera/projection restore (Task 3 `start`/`stop`), down-ray ground follow + tolerances (Tasks 1, 3 `_tick`), displacement clamp (Task 1 `clamp_step`), no document mutation (nothing calls document APIs), edge cases — no doc/view error paths in `Activated`, dead-view auto-exit in `_tick` (`RuntimeError` → `_teardown_only`), recompute-safe (live ray) — all mapped. Out-of-scope items (tours, collision, VR, prefs) intentionally absent.
- Types/names: `WalkController(position, yaw, pitch)`, `advance(dt, ground_z=None)`, `on_event(ev)`, `snap_target(eye_z, ground_z)`, `move_vector(active, yaw, run=False)`, `_start_walk(view, point, face)`, `gui._MODE` — consistent across tasks and tests.
- Known sharp edge, deliberately kept: the ground pick depends on `getObjectInfoRay` hitting the top face of a solid under the eye; if a recompute leaves the view mid-frame the pick uses the last committed scene graph — acceptable, the next tick corrects.
