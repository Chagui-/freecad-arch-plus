# ArchPlus tools

User guide for the enhanced **Stairs**, **Doors**, **Windows** and **Walls**
tools. For the Parts Library see [PARTS-LIBRARY.md](PARTS-LIBRARY.md); for the
road ahead see [ROADMAP.md](ROADMAP.md).

Stairs, doors and windows are each a modifiable copy of a native FreeCAD
module — `ArchStairs` and `ArchWindow` respectively — so every native feature
(IFC export, hosting/opening cuts, presets, …) is preserved while new
behaviour is added on top, without affecting the built-in tools. Walls is a
from-scratch engine built around a shared sketch.

## Stairs

- **Configuration dialog** (Task panel) with **live preview** — the stair
  renders in the 3D view as you change values, and updates as you edit.
- **Double-click to edit** an existing stairs object, reusing the panel.
- **Comfort note** — live riser/tread readout and Blondel ratio (2R + T) check.
- **Configurable landing position** — `LandingStep` places the landing/turn on
  any step that leaves at least one step on each flight (0 = auto, centered)
  instead of always at the middle.
- **Half- and quarter-turn winders** — a turn is built from winder (wedge)
  steps that sweep 180° (half) or 90° (quarter) while climbing, filling a
  square footprint. Set the turn to a single step for a flat landing instead.

### Layouts

<img src="images/stairs_straight.jpg" alt="Straight stairs" width="150">
<img src="images/stairs_landing.jpg" alt="Stairs with a landing" width="150">
<img src="images/stairs_half_turn.jpg" alt="Half-turn stairs with winders" width="150">
<img src="images/stairs_quarter_turn.jpg" alt="Quarter-turn stairs" width="150">

### Configuration dialog

<img src="images/stairs_dialog_1.jpg" alt="Stairs configuration dialog" width="250">
<img src="images/stairs_dialog_2.jpg" alt="Stairs configuration dialog with comfort note" width="250">

### Usage

BIM workbench → **ArchPlus** toolbar → **Stairs** → configure → **OK**.
Double-click a stairs object to edit it.

## Doors

- **Configuration dialog** (Task panel) with **live preview** — the door
  renders as you edit, and the host wall's opening re-cuts immediately.
- **Double-click** (or right-click → **Edit**) to reopen the panel on an
  existing door.
- **Operations** — Single swing, Double swing, Sliding (single), Sliding
  (double), and Opening only (a bare hole, no leaf).
- **Panel styles** — Solid or Glass (full).
- **Swing controls** — hinge side and opening direction for hinged doors.
- **Opening animation** — a 0–100 % slider: swing leaves rotate about the
  hinge, sliding leaves slide aside.
- **Panel position** — place the leaf Centered (default), flush Front, or flush
  Back within the frame depth.
- **Height above wall base** — lift the door off the floor for a threshold or
  mid-wall placement (0 = sitting on the floor).
- **Opening symbols** — plan (swing arc) and elevation symbols, each
  toggleable (elevation off by default).
- **Mouse placement** — click a wall face and the door drops to the wall base
  (floor) automatically and centres on the cursor, so you only aim *along* the
  wall. A sill/threshold offset is available during placement.
- **Reposition with the mouse** — from the panel button or right-click →
  **Reposition (pick point)**: pick a new spot; the door re-orients to the
  wall face you point at, re-snaps to the floor, and re-cuts the host wall.

### Layouts

<img src="images/door_single_swing.jpg" alt="Single-swing door hosted in a wall" width="150">
<img src="images/doors_double_swing.jpg" alt="Double-swing door hosted in a wall" width="150">

### Configuration dialog

<img src="images/doors_dialog_1.jpg" alt="Doors configuration dialog" width="250">
<img src="images/doors_dialog_2.jpg" alt="Doors configuration dialog with opening options" width="250">

### Usage

BIM workbench → **ArchPlus** toolbar → **Doors** → click a wall face to place →
configure in the panel. Double-click (or right-click → **Edit**) a door to
reopen the panel; right-click → **Reposition (pick point)** to move it with
the mouse.

## Windows

- **Configuration dialog** (Task panel) with **live preview** — the window
  renders as you edit, and the host wall's opening re-cuts immediately.
- **Double-click** (or right-click → **Edit**) to reopen the panel on an
  existing window.
- **Shapes** — Rectangular or **Round** (a circular oculus). A round window is
  fixed glass; its diameter follows the width.
- **Operations** — Fixed (no opening), Single casement, Single sliding, and
  Double casement (rectangular only).
- **Swing controls** — hinge side and opening direction for casement windows.
- **Opening animation** — a 0–100 % slider: casement sashes rotate about the
  hinge, sliding sashes slide aside.
- **Sash position** (casement only) — set the sash flush to the Front/interior
  (default) or Back/exterior face within the frame depth (only matters when
  the sash is shallower than the frame). For sliding windows the fixed half
  is always at the front and the sliding half at the back.
- **Full 4-sided frame** — unlike doors (which sit on the floor and use a
  3-sided frame), windows get a frame on all four sides including the bottom
  sill jamb, since they sit in a wall opening.
- **Single undivided glass pane** per sash.
- **Opening symbols** — plan (swing arc) and elevation symbols, each
  toggleable (elevation off by default).
- **Mouse placement** — click a wall face and the window drops to a sill height
  (default 900 mm) above the wall base automatically and centres on the cursor,
  so you only aim *along* the wall. The sill height is adjustable during
  placement.
- **Reposition with the mouse** — from the panel button or right-click →
  **Reposition (pick point)**: pick a new spot; the window re-orients to the
  wall face you point at, snaps to the wall base (the sill height is not
  preserved — set it again in the panel), and re-cuts the host wall.
- **Flip without reopening** — right-click a casement window → **Invert Opening
  Direction** to mirror the swing in place.

### Layouts

<img src="images/window_single_sliding.jpg" alt="Single sliding window" width="150">
<img src="images/window_double_casement.jpg" alt="Double casement window" width="150">
<img src="images/window_round_fixed.jpg" alt="Round fixed window" width="150">

### Usage

BIM workbench → **ArchPlus** toolbar → **Windows** → click a wall face to place
(drops to a 900 mm sill height by default) → configure in the panel.
Double-click (or right-click → **Edit**) a window to reopen the panel;
right-click → **Reposition (pick point)** to move it with the mouse.

## Walls

- **Sketch-based segments** — a wall references its base sketch (never owns
  it): each straight run of the sketch is claimed by a `WallSegment` group
  that extrudes it separately, so segments can be edited, split and
  overridden independently. Connected runs build as one mitered chain —
  corners join cleanly and closed loops build as a single ring — exactly
  like an Arch Wall. The `Wall` root holds the default dimensions and
  the hosted openings.
- **Nesting with inherited overrides** — segments can be grouped and
  sub-grouped; a parent's settings flow down to its children unless they
  override. Width and height are overridden with a checkbox (unchecked =
  inherit; the panel pre-fills the field with the inherited value), align
  with an **Inherit** option in its combo.
- **Rest segment** — an optional segment that auto-claims every sketch edge no
  other segment claims (at most one per wall, a direct child of the wall, set
  from the Edit Wall panel). New sketch edges land in the rest segment
  automatically; with no rest segment they stay unbuilt and a warning is
  printed to the Report view.
- **Cross-segment corners** — where one segment's run ends and another's
  begins, both segments extend or trim to the same seam line (each using
  its own width, align and offset), so segment boundaries are mitered just
  like corners within one segment: no gap and no overlap. With differing
  widths the seam slants so the wider segment takes the larger share of the
  corner; segment heights simply step at the seam plane. Open sketch ends,
  curved boundary edges, and vertices where three or more segments meet
  keep a straight butt joint.
- **Hosted doors and windows** — ArchPlus doors and windows host on the wall
  by picking any segment face (the tool walks up to the root). Openings are
  found both among the root's `Subtractions` and, Arch-style, through the
  opening's `Hosts`, and an opening that spans two segments is cut from both.
- **Split / move segment** — the **Split / move segment…** entry lives only
  in the 3D-view right-click menu (there is no tree context-menu entry and no
  toolbar button), greyed out until a wall face is selected. Clicking a wall
  face selects the wall itself — FreeCAD attributes picks of claimed children
  to the top claim parent — and the split resolves each clicked face to the
  segment owning it. Select the faces to move, right-click and choose it: a
  picker dialog offers **<new segment>**, which splits the picked faces' runs
  into a new sibling segment, or one of the wall's other top-level segments,
  which the runs are moved into (rejoining that segment's chain). Hovering a
  row previews that segment in the 3D view; double-click chooses it.
  Splitting requires picked faces — running the command with no face picked
  prints a Report-view warning and changes nothing. Each clicked face moves
  the run nearest to the click.
- **Native selection mapping** — clicking a segment in the tree selects all
  of its faces, and clicking wall geometry in the 3D view selects the
  segment that owns the picked face (not the wall root), so the tree always
  highlights the right item. Both behave like any other FreeCAD selection:
  clicking something else clears or replaces it.

### Edit Wall panel

- **Dimensions** — width, height, align (center/left/right) and offset, each
  with a reference diagram. These are the wall defaults; segments follow them
  unless they override.
- **Sketch & claims** — the base sketch, which segment (if any) is the rest
  segment, and a live count of claimed vs. unclaimed sketch edges.
- **Metadata** — tag / mark.

### Edit Segment panel

- **Overrides** — width and height with per-field checkboxes (unchecked =
  inherit, the field shows the inherited value); align with an **Inherit**
  option in its combo.
- **Claims** — a read-only summary of the sketch edges the segment claims.

### Usage

BIM workbench → select a sketch → **ArchPlus** toolbar → **Wall** → set the
default dimensions → **OK**. Double-click the wall or a segment to edit it.
With the wall built, click one or more wall faces in the 3D view (the menu
entry stays greyed out otherwise), right-click, choose **Split / move
segment…**, then pick **<new segment>** or an existing segment to move the
faces' runs into.

### Known limitations

- Collinear runs that belong to *different* groups butt with coplanar faces
  and can flicker in the 3D view (z-fighting — the same cosmetic artifact as
  any two touching solids in FreeCAD).
- **Split / move segment** maps each clicked face to the claimed run nearest
  to the click point (within one wall width); a clicked face that matches no
  run is reported in the Report view and nothing is split for it.

## Regenerating the images

The layout images above are generated, not hand-captured: `docs/gen_images.py`
builds each layout, hosts it in a real Arch Wall, and renders it offscreen with
the Parts Library's thumbnail renderer. Run it from the repository root:

```
"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" docs/gen_images.py
```

It needs a GUI session (the offscreen renderer wants a GL context),
overwrites the generated layout images in `docs/images/` (the dialog
screenshots are hand-captured and untouched), and the layouts to render live
in the `DOORS`, `WINDOWS` and `STAIRS` lists at the top of the script.

## Walk Through

First-person mode for inspecting a model at eye height — mouse-driven.
Click **Walk Through**, then aim the small figure in the 3D view and
left-click: the camera starts there at the person height (1.65 m by
default) along the picked face's normal (a floor puts you on it, a wall
puts you in front of it). Placement runs on the Draft Snapper's real
mouse pipeline, so the stand point is the actual surface under the
cursor — a click on a 2nd-floor slab starts you there, and clicking bare
ground stands you on the z=0 plane. While walking:

- **Mouse wheel** — step forward/back along the view heading (one notch
  ≈ 30 cm; a fast scroll piles up notches, capped per step)
- **Hold Right-mouse + move** — look around
- **Esc**, **click the tool again**, or the panel's **Exit** — stop and
  restore the camera

The camera follows the ground: floors and stairs raise/lower your eyes
within a 0.6 m rise / 2 m drop tolerance; over gaps or big drops the
height is held. Clicking a storey whose slab doesn't exist under the
click keeps that level until you walk onto real geometry near it (e.g.
stairs). The task panel adjusts person height (meters, or ft/in when
your unit scheme is imperial), look-axis inversion, and the walk camera's
field of view (90°/67° horizontal) while you walk. Movement is
view-only — nothing in the document changes, and the camera/projection
you had before is restored on exit.
