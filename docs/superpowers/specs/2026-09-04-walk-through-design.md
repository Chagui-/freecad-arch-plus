# Walk Through — design

Date: 2026-09-04
Status: approved (user)
Branch: `feat/walk-through`

## Purpose

An interactive first-person walk mode for inspecting buildings modeled with
ArchPlus (stairs, doors, windows): the camera stands at eye height, follows
floors and stairs, and is steered like a game. Click the tool, click a point
in the 3D view to position your eyes, walk with the keyboard, look with the
mouse, Esc to exit.

## Background: what already exists

FreeCAD (1.1 and `main`) has no first-person navigation:

- All built-in navigation styles (`src/Gui/Navigation/`) are orbit-style:
  Blender, CAD, Gesture, Inventor, MayaGesture, OpenCascade, OpenSCAD,
  Revit, SiemensNX, SolidWorks, TinkerCAD, Touchpad, Turntable.
- No bundled workbench ships anything walk-like (grep over the 1.1 `Mod`
  tree: zero hits).
- Community: JMG's 2014 "Tour Camera" script (camera follows selected
  edges; Python 2, dead) and microelly2's Animation workbench (path camera
  animation, last pushed 2019) are guided tours, not interactive; both
  unmaintained. GitHub: no repos for `freecad "first person"` at all.
  Users currently export to Blender/Bonsai for a walkthrough.

A true navigation style requires C++; this tool is therefore a pure-Python
*toggle mode* owned by ArchPlus, not a navigation style.

## UX

Two-phase start (same pick pattern as Doors/Windows/Parts Library):

1. Click **Walk Through** (`ArchPlus_WalkThrough`) in the ArchPlus
   toolbar/menu → console/status hint: "ArchPlus: click a point in the 3D
   view to start walking." A `FreeCADGui.Snapper.getPoint` session runs.
   Esc or right-click cancels cleanly (the `point is None` convention).
2. Click on geometry:
   - Face picked (face in the movecallback `info`): eye = picked point +
     1.65 m along the face normal. Floor ⇒ standing on it; wall ⇒ standing
     in front of it; stair rake ⇒ close enough, the ground-following tick
     corrects on frame one.
   - No face: fallback offset straight up.
   - Initial heading = current view yaw, pitch leveled to 0.
3. Walk mode is active: perspective projection is forced (previous camera +
   projection remembered). Status-bar hint: "WASD/arrows move · hold
   right-mouse + move to look · Shift run · Esc exit".
4. Esc or clicking the tool again exits: event callback + timer removed,
   saved camera + projection restored.

### Controls — revised 2026-09-04: mouse-only (user decision)

After live testing the user removed the keyboard entirely (WASD, arrows,
Shift, Esc). Draft's Snapper was also dropped from placement: it projects
the cursor ray onto the working plane unconditionally
(`getApparentPoint`), pinning picks to the plane's height — 2nd-floor
clicks came back at floor-1 height after door placements moved the plane.
Placement now reads the true scene hit under the cursor through an
application-level mouse filter.

| Input | Action |
|---|---|
| Left click (placement phase) | place the eyes at the aimed point |
| Wheel | step forward/back along the view heading (one notch = 300 mm) |
| Hold RMB + move mouse | free look (yaw + pitch) |
| Click tool again / panel Exit | exit walk mode |

Pitch clamped to ±85°.

## Architecture

**Chosen: event callback + Qt timer (option A).**
`Gui.addEventCallback("SoEvent", handler)` only *records* input state:
held keys, RMB drag deltas, Esc. A 30 Hz `QTimer` integrates movement from
(dt, key state, yaw/pitch) and rewrites the Coin camera each tick via
`ActiveView.getCameraNode()` (position + `pointAt`). FreeCAD's own RMB-orbit
still fires, but the per-tick camera rewrite from internal state masks it.

Alternatives considered and rejected:
- Qt event filter on the 3D widget for true input suppression: fragile
  across Qt/FreeCAD internals.
- C++ `NavigationStyle` subclass: the "proper" FPS fix, but breaks the
  pure-Python add-on model.

Module layout follows the existing per-tool pattern:
`archplus/tools/walk/` with `gui.py` (command, mode lifecycle, input, tick)
and `kinematics.py` (pure functions: move vector from key state + yaw,
pitch clamp, height-snap decision, speed clamp). Command registered as
`ArchPlus_WalkThrough` and added to the `commands` list in `InitGui.py`.

## Ground following (floor-following mode)

Each tick a vertical ray (`SoRayPickAction` via pivy) is cast downward onto
the viewer scene graph from above the eye at the eye's x,y (honors
visibility). On a hit: target eye = ground z + eye height.

- Snap tolerance per step: +0.6 m up / −2.0 m down ⇒ ArchPlus stairs climb
  naturally; outside tolerance or no hit ⇒ hold current height (hover over
  gaps).
- Speeds: 1.4 m/s walk, 4.5 m/s run; per-tick displacement clamped to
  0.3 m to avoid tunneling at hitches.

No document changes ever: view-only, selection untouched.

## Edge cases

- No active 3D view or document ⇒ console error, pick session not started.
- View/document closed mid-walk (dead object on tick) ⇒ auto-exit, callback
  + timer removed.
- Recompute mid-walk: fine, the ray picks the live scene.
- Workbench switch mid-walk: the timer's dead-view guard exits the mode.

## Parameters (v1 constants, in kinematics.py)

| Parameter | Value |
|---|---|
| Eye height | 1.65 m |
| Walk speed | 1.4 m/s |
| Run speed | 4.5 m/s |
| Step up tolerance | +0.6 m |
| Step down tolerance | −2.0 m |
| Tick rate | 30 Hz |
| Max per-tick displacement | 0.3 m |
| Pitch clamp | ±85° |

## Testing

- Headless pytest (existing per-tool pattern): `kinematics.py` is pure and
  fully covered — move vectors from key state + yaw (including strafe and
  run multipliers), pitch clamp bounds, height-snap decision (hit / no-hit /
  up-tolerance / down-tolerance), speed and displacement clamps.
- GUI smoke via the FreeCAD MCP (`execute_code` + `get_view` screenshots):
  start the pick, simulate a picked point, start the mode, drive key state
  directly, verify camera pose and ground snap visually.

## Out of scope (v1)

- Guided tours along paths (possible later; port of Tour Camera).
- Wall collision, gravity free-fall, crouch/jump, VR/stereo.
- Preferences page; parameters stay constants.
