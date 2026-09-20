# Parts Library — manual verification checklist

This checklist is the human-in-FreeCAD verification for the Parts Library.
None of it can run headlessly: it needs a real FreeCAD 1.1 process, a real
Qt event loop and (for the preview and thumbnail checks) a real
GL/offscreen context. Automated coverage stops at the headless pytest suite
(manifests and facets are well-formed, every part folder's `builder.py`
loads and exposes a callable `build()`, every declared parameter and
placement host is valid, every facet icon exists on disk) — everything below
is what that suite cannot see.

The library ships 36 parametric parts across six rooms (Kitchen, Dining
Room, Bedroom, Living Room, Bathroom, Office). All 36 ship a committed
`thumbnail.jpg` and a `builder.py`; none uses the model-file (assets) path.

Everything scriptable runs inside FreeCAD via
`archplus/freecad_tests/run_all.py` (65 checks) — from the repository root
run `"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py`,
which prints PASS/FAIL lines and exits non-zero on failure. The items below
are what remains for a human: visual judgments (dark-theme legibility, leaf
counts in the preview, "looks right"), the mouse-driven placement tracker
(D7-D9), the imperial-schema readout (U3), and the mouse-driven edit entry
points (L7-L9).

| Room | Parts |
|---|---|
| Kitchen | Base cabinet (300/600/800, with/without worktop), Base cabinet with oven, Corner base cabinet (with/without worktop), Wall cabinet (600/800), Corner wall cabinet, Gas hob (1/2/4/5 burner), Sink (1/2 bowl), Fridge (single/double doors), Tall pantry cabinet, Tall unit with oven and microwave, Pedal bin |
| Dining Room | Dining table (4/6/8-seat), Basic chair |
| Bedroom | King bed (1800×2000), Single bed (1050×2000), Nightstand, Wardrobe, Chest of drawers, Side table, Mirror, Floor lamp, Curtain, Television |
| Living Room | Sofa (2/3-seat), Armchair, Coffee table, Side table, TV unit, Television, Floor lamp, Curtain |
| Bathroom | Toilet, Bathtub, Shower base, Vanity, Shower screen, Towel hook, Toilet roll holder, Mirror |
| Office | Desk, Bookcase |

The highest-value checks are the ones the headless suite structurally
cannot see: a real OCC boolean or fillet falling back silently (every
fillet in `shapes.py` degrades to a sharp edge on failure — a part that
looks "blockier" than intended is this fallback firing, not a bug to fix
blind), the wall-hosted placement path against a real Arch wall, and the
preview/thumbnail rendering itself.

## The live preview is a static image on FreeCAD 1.1 — expected

`pivy`'s bundled Quarter does `from pivy.qt.QtWidgets import QOpenGLWidget`.
Under FreeCAD 1.1's Qt6-based `pivy.qt` shim, `QOpenGLWidget` moved into
`QtOpenGLWidgets` — pivy's copy of Quarter is Qt5-era and was never updated
for that move, so `from pivy import quarter` raises `ImportError` on this
build. The panel auto-detects this at construction and falls back to a
static rendered-image preview, printing one console warning per session.
Wherever a check below mentions "the preview", read it as "the panel shows
a still render of the part" — that is the bar on this build.

Work through the checklist top to bottom in a single FreeCAD session. Each
step has a checkbox — tick it only after you have actually observed the
stated result, not merely run the action.

## Part A — Startup and toolbar

- [ ] **A3.** Create a new document and draw an Arch Wall (BIM → Wall), so
      there is a wall face available to click later.

## Part B — Opening the panel and browsing

- [ ] **B9a (selected part, then grid empties).** With a part selected in
      the sidebar, type a search (or pick a chip) that empties the grid.
      Confirm the sidebar leaves no empty visible row behind: the family
      label blanks **and** hides, not merely blanks its text.
- [ ] **B10 (dark theme legibility).** Switch FreeCAD to a dark theme.
      Reopen the Parts Library tab. Confirm the chips are legible in both
      their checked and unchecked states — readable label text against a
      card background clearly distinct from the page behind it — and that
      the grid still lays out as a **grid** (multiple cards per row when the
      tab is wide enough), not one full-width row per card. Resize the tab
      narrower and wider: the column count changes at natural card-width
      breakpoints. Switch back to a light theme and confirm the chips and
      grid still read correctly.

## Part C — Preview pane and detail sidebar (static fallback expected)

### Parameter checks

- [ ] **P2.** Typing `80` into **Width** rebuilds the preview once, not once
      per keystroke.
- [ ] **P5.** Setting cabinet **Width** to `800` rebuilds the cabinet with two
      door leaves; count the leaves in the preview geometry.

### Display-unit checks

Length fields are pinned to centimetres (inches under an imperial schema),
not to the FreeCAD unit schema itself — `part.json` and every property on a
placed part stay in millimetres.

- [ ] **U3.** Set **Edit → Preferences → General → Units** to
      *Building US (ft-in)* and reselect the part. Every length field now
      reads in inches (**Width** ≈ `23.62 in`). Switch back to
      *Standard (mm)* and reselect: the fields return to centimetres — NOT
      to millimetres, which is the point of pinning them. If a metric
      schema ever shows inches, `units.is_imperial()` misread the schema;
      report the schema name.

## Part D — Placement

- [ ] **D3.** Change the object's **Width** to `800` in the property editor.
      Confirm the cabinet geometry has two door leaves (count them in the 3D
      view).
- [ ] **D7 (placement tracker).** Select Base cabinet, click **Place in 3D
      view**. Before clicking to commit, move the mouse around the 3D view:
      a translucent box sized to the cabinet's measured dimensions follows
      the cursor and re-orients over a wall face vs. the floor. Click to
      commit — the tracker disappears at the same moment the real object
      appears (no lingering ghost box).
- [ ] **D8 (repeat placement).** Immediately after D7's click commits the
      first cabinet, confirm the ghost tracker box is STILL visible and
      following the cursor (the Snapper has re-armed itself) without
      reopening the library tab or clicking **Place in 3D view** again.
      Click a second point: a second "Base cabinet" object appears, and the
      tracker keeps following the cursor for a third pick. Repeat this two
      or three times in a row to confirm the loop keeps re-arming.
- [ ] **D9 (Esc ends the loop cleanly).** While the tracker from D8 is still
      following the cursor, press **Escape** (or right-click) instead of
      clicking. Confirm: (1) the ghost tracker box disappears — no leftover
      geometry in the 3D view; (2) no further object is placed; (3) the MDI
      area switches back to the ArchPlus Library tab automatically.
- [ ] **D12 (a wall-hosted part hangs on the wall).** Select **Wall
      cabinet**, click **Place**, then click a wall face in the 3D view. It
      arrives **upright** — its back against the wall, its body standing out
      into the room, its underside at 1500 mm above the wall's base — and
      the ghost box follows the cursor in the same orientation. Then change
      **Height above floor** to `1200` in the property editor: the cabinet
      moves down to 1200 without being re-placed. Click it, drag it
      sideways, and change the height again: it keeps the new position and
      moves only by the difference.

## Part K — the kitchen additions (K1-K5)

Five parts added to the Kitchen room after the first pass: `basic/sink`,
`basic/fridge`, `basic/tall-pantry`, `basic/tall-oven-unit` and
`basic/waste-bin`. Their heights and offsets are the part of a new part that
only a real placement click can show.

- [ ] **K1 (the sink drops into the hole).** Place a **Base cabinet** and
      set its **Worktop** to *Without worktop*: the unit's top drops 40 mm
      below its Height (the top surface reads 86.0 cm while **Height** still
      says 90.0 — that 40 mm is where the work surface goes), and it is an
      open-topped box rather than a block — look into it and you see its
      walls and floor, 18 mm in from the edges. Select **Sink**, set its
      **Depth** to `600` so its rim reaches the unit's edges (its 500 mm
      default leaves the back 100 mm of that opening showing, which is the
      hole at its clearest), then click **Place** and click the floor in
      front of that unit. The rim's underside lands on the box's edges and
      its top face becomes the work surface at 900 mm — the unit's Height —
      with the bowl hanging in the interior and the tap behind it. Switch
      **Bowls** to *Double bowl*: the sink widens to 1000 mm and the tap
      stays centred behind the two bowls.
- [ ] **K2 (the fridge's doors are its size).** Place a **Fridge**: it
      measures 600 × 650 × 1850, Width and Depth shown derived (italic).
      Switch **Doors** to *Double doors*: it rebuilds 750 wide with the
      fridge compartment's single door replaced by a pair meeting at the
      middle, their handles facing each other across that seam, and the
      freezer door below unchanged. Type 700 into **Width**, then switch
      **Doors** back to *Single doors*: the typed width is discarded and
      Width returns to derived at 600 — the arrangement is the driver, so
      its pins go with it.
- [ ] **K3 (the tall units are tall).** Place **Tall pantry cabinet** and
      **Tall unit with oven and microwave**. Both stand on the floor (they
      are floor-hosted, not lifted like the wall cabinet) and measure
      2100 mm high: the pantry shows four door leaves in two tiers, the oven
      unit a cupboard below two appliance fronts and another above them.
- [ ] **K4 (the appliance recesses read).** On the tall oven unit, confirm
      the oven and microwave fronts are recessed into the door line rather
      than outlined on it — each should carry a shadow on all four sides,
      the way the base cabinet with oven's front does.
- [ ] **K5 (the bin is round).** Place **Pedal bin**: it stands on the floor
      and measures 300 × 300 × 700. A round plan is one dimension, so
      **Depth** reads derived (italic) and follows **Width** — change
      **Width** to `400` and the bin rebuilds round at 400 across, keeping
      the taper and the lid's overhang. At the defaults the body is 270
      across at the shoulder narrowing to 237 at the floor, the domed cap
      overhangs it by 15 mm on every side, and the foot pedal shows at the
      front of the floor without reaching past the advertised depth.

## Part L — Editing placed parts

L1-L6 are scripted (`verify_edit.py`): opening the edit task panel loads
the part's current values with the object's derived fields shown derived,
field edits rebuild the placed part live, Reset returns to the manifest's
answer, Apply commits the whole session as one undo step, Discard rolls it
back, and a second edit refuses while one is open. The edit lives in a task
panel (FreeCAD's task area), never in the library tab. What remains for a
human is the mouse routing into that same panel:

- [ ] **L7 (double-click).** Place a king bed, then double-click it in the
      3D view. A task panel titled "Edit King bed" opens in the task area
      with Width ≈ 180.0 cm, Length ≈ 200.0 cm. The ArchPlus Library tab
      does not change. Cancel.
- [ ] **L8 (context menu).** Right-click the bed in the tree. The menu
      shows **Edit in Parts Library** above **Reload from library**; both
      behave (Edit opens the same task panel; Reload still rebuilds from
      the library). Cancel any open edit.
- [ ] **L9 (Cancel/Esc discards).** Open the edit panel for a part, change
      a field so the 3D view rebuilds, then press Esc (or the native Cancel
      button). The part returns to its pre-edit values (the discarded
      transaction), the task panel closes, and nothing in the console
      reports a transaction error.

---

## Wrap-up

- [ ] Every checkbox above is ticked, or the specific failure and its
      resolution is recorded here:

  ```
  (record any deviations / fixes applied during this verification pass)
  ```

- [ ] If any edits made during this pass (manifests, thumbnails, collection
      files) were left in place by mistake, `git diff library/` is empty
      before closing out.
