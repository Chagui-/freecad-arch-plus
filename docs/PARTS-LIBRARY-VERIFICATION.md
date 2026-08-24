# Parts Library — manual verification checklist

This checklist is the human-in-FreeCAD verification for the Parts Library.
None of it can run headlessly: it needs a real FreeCAD 1.1 process, a real
Qt event loop and (for the preview and thumbnail checks) a real
GL/offscreen context. Automated coverage stops at the headless pytest suite
(manifests and facets are well-formed, every part folder's `builder.py`
loads and exposes a callable `build()`, every declared parameter and
placement host is valid, every facet icon exists on disk) — everything below
is what that suite cannot see.

The library ships 31 parametric parts across six rooms (Kitchen, Dining
Room, Bedroom, Living Room, Bathroom, Office). All 31 ship a committed
`thumbnail.jpg` and a `builder.py`; none uses the model-file (assets) path.

Everything scriptable runs inside FreeCAD via
`archplus/freecad_tests/run_all.py` (57 checks) — from the repository root
run `"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py`,
which prints PASS/FAIL lines and exits non-zero on failure. The items below
are what remains for a human: visual judgments (dark-theme legibility, leaf
counts in the preview, "looks right"), the mouse-driven placement tracker
(D7-D9), and the imperial-schema readout (U3).

| Room | Parts |
|---|---|
| Kitchen | Base cabinet (300/600/800), Base cabinet with oven, Corner base cabinet, Wall cabinet (600/800), Corner wall cabinet, Gas hob (1/2/4/5 burner) |
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
