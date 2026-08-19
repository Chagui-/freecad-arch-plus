# Parts Library — manual verification checklist

This checklist is the deferred, human-in-FreeCAD verification for the whole
Parts Library feature (Tasks 7–15, plus the pass-2 restructure into a
full-window MDI tab with a two-screen catalogue browser). None of it can be
run headlessly: it needs a real FreeCAD 1.1 process, a real Qt event loop and
(for the preview and thumbnail checks) a real GL/offscreen context. Automated
coverage stops at `uv run --with pytest --no-project pytest -q` (122
passed at the time this doc was written, including `archplus/tools/partslib/tests/test_partslib_theme.py`'s
headless coverage of the dark/light theme decision); everything below is
what that suite cannot see.

## The library now ships 31 real parts — PARTLY verified in real FreeCAD

`library/` no longer ships empty. The `parts-library-content` branch adds 31
parametric parts across six rooms (Kitchen, Dining Room, Bedroom, Living
Room, Bath Room, Office) — see the table below — plus four
builder modules (`furniture.py`, `sanitary.py`, `kitchen.py`,
`fittings.py`) and a shared geometry-massing helper
(`partslib/shapes.py`: rounded corners, square legs, rolled
edges, panel reveals, toe-kick recesses, oval basin scaling).

The first 14 parts HAVE now been rendered and reviewed in FreeCAD, and
several were reworked as a result — see the git history for chair, sofa,
desk and toilet. The 17 added afterwards (Kitchen, fittings and
the Living/Bedroom additions) have NOT been seen in FreeCAD yet.

### Wall-hosted parts are new and unproven

Six of the new parts declare `host: wall` — wall cabinet, corner wall
cabinet, mirror, towel hook, toilet roll holder, curtain — plus the
television's wall-mounted mounting option. Until now every shipped part was
`host: floor`, so `partslib_placement`'s wall branch (including its
snap-to-host-base logic) has only ever run against synthetic unit-test
data. **Placing a wall-hosted part against a real Arch wall is the single
highest-value manual check on this branch.**

Note also that a selected `Choice` option can merge `placement`, so a
parameter can change its host — the television relies on this to be
floor-hosted on a stand and wall-hosted on a bracket.

There is no FreeCAD in the development environment, so automated
verification stops at: (1) the headless `pytest -q` suite (manifests
and facets are well-formed, every part folder's builder.py (where present)
loads and exposes a callable build(), every declared parameter is valid, every declared placement host
is known, every facet icon exists on disk), and (2) a throwaway script that
runs every part's builder against a bounding-box-only stand-in for
`Part`/`FreeCAD` — confirming the Python executes without exceptions and
that measured `W × D × H` figures match what each manifest advertises, but
**not** that the real OCC boolean/fillet operations succeed. Every step
below that involves placing, previewing or measuring a part (B7 onward, C,
D, E, F, G, I, J, K) needs a human-in-FreeCAD pass. In particular, watch
for:

- Any `PrintWarning`/`PrintError` from a `makeFillet` or boolean op falling
  back silently (every fillet in `shapes.py` is wrapped in a try/except that
  degrades to a sharp edge on failure — a part that looks "blockier" than
  intended in the preview is this fallback firing, not a bug to fix blind).
- The toilet, bathtub, vanity and shower base's oval/recessed geometry
  (`sanitary.py`) actually resolving to valid solids — these are the parts
  most likely to hit an OCC edge case (non-uniform scale of a filleted
  surface, a cut whose cavity clips through more of the shell than intended).
- The bookcase's open-front shell + shelf dividers (`furniture.bookcase`) —
  the one part built as a hollow carcass rather than a solid block.

27 facet icon SVGs live under `archplus/tools/partslib/resources/icons/facets/` — eyeball that they
render at both toolbar and list-row sizes in light and dark theme. A test
now asserts every icon a facet value names actually exists on disk (four
shipped missing once, rendering as blank cards with nothing in the console
to explain why), but nothing automated can tell you one looks wrong.

| Room | Parts |
|---|---|
| Kitchen | Base cabinet (300/600/800), Base cabinet with oven, Corner base cabinet, Wall cabinet (600/800), Corner wall cabinet, Gas hob (4/5 burner) |
| Dining Room | Dining table (4/6/8-seat), Basic chair |
| Bedroom | King bed (1800×2000), Single bed (1050×2000), Nightstand, Wardrobe, Chest of drawers, Side table, Mirror, Floor lamp, Curtain, Television |
| Living Room | Sofa (2/3-seat), Armchair, Coffee table, Side table, TV unit, Television, Floor lamp, Curtain |
| Bath Room | Toilet, Bathtub, Shower base, Vanity, Shower screen, Towel hook, Toilet roll holder, Mirror |
| Office | Desk, Bookcase |

Steps that only exercised the empty library in the prior pass (A, B1/B2, the
empty-state message) remain valid as written but are no longer the
interesting case — B2 in particular should now show all six rooms above,
each with its declared elements and counts.

## The panel is now an MDI tab, not a dock

`partslib_gui.py` no longer opens a `QDockWidget`. `PartsLibraryPanel` is a
plain `QWidget` hosted as a full-window tab in FreeCAD's MDI area (the same
area document windows live in), the same way `Mod/Help/Help.py` hosts its
own browser. Any step below that still says "dock" is describing the old
behaviour — read it as "the ArchPlus Library tab" instead. The panel is also
now a two-screen catalogue: a **categories** screen (a card per room) that
drills into a **results** screen (breadcrumb, search, card grid, detail
sidebar) — the old "Group by" dropdown and its persisted preference are gone,
replaced by the room/element drill-down.

Work through it top to bottom in a single FreeCAD session. Each step has a
checkbox — tick it only after you have actually observed the stated result,
not merely run the action.

## Read this before you start: the live preview is RESOLVED — it does not work on FreeCAD 1.1

This was previously an open risk ("is `PREVIEW_LIVE` verified?"). It is now a
confirmed, permanent limitation, with a known cause and a shipped fix.

`pivy`'s bundled Quarter (`pivy/quarter/QuarterWidget.py`) does
`from pivy.qt.QtWidgets import QOpenGLWidget`. Under FreeCAD 1.1's Qt6-based
`pivy.qt` shim, `QOpenGLWidget` moved out of `QtWidgets` into
`QtOpenGLWidgets` — pivy's copy of Quarter is Qt5-era and was never updated
for that move, so `from pivy import quarter` raises `ImportError` on this
build. This is a bug inside FreeCAD's own bundled `pivy` (under
`Program Files`), not in ArchPlus, and it is not something this add-on
patches or works around by injecting names into pivy's namespace.

`partslib_gui.py` now **auto-detects** this at panel construction: it
attempts `from pivy import quarter` and `quarter.QuarterWidget()` inside a
try/except covering both steps, and on any failure (an `ImportError` today,
but the same path also covers a GL-context failure raising something else)
falls back to a static rendered-image preview instead — printing one console
warning per session, not one per part selected. Panel construction itself
can never fail because of this: nothing in `_buildUi` → `_buildDetail` →
preview setup propagates an exception from a missing/broken live widget.

A module-level `PREVIEW_LIVE_ALLOWED = True` remains as an override (set it
`False` to force the static fallback even on a machine where the live widget
would work); the actually-detected outcome is recorded separately and is not
something you need to touch by hand.

**What this means for verification below:** wherever the checklist mentions
"the live preview", read it as "the panel opens and shows a still preview of
the part" — that is the check that matters on this build. Confirming that
`QuarterWidget` itself embeds live is not expected to pass on FreeCAD 1.1 and
is no longer part of this checklist's bar for success. Grouping, search, parameters, measurements, placement and everything else the panel does are
unaffected by the fallback.

---

## Part A — Startup and toolbar

- [ ] **A1.** Restart FreeCAD 1.1, switch to the **BIM** workbench. The
      **ArchPlus** toolbar shows a fourth button with the Parts Library icon
      (`archplus/tools/partslib/resources/icons/PartsLibrary.svg`), rendering correctly and visually
      consistent in weight/style with the Stairs/Doors/Windows icons at both
      toolbar and tree icon sizes.
- [ ] **A2.** The command also appears under the **ArchPlus** menu group
      inside the BIM workbench (not just the toolbar).
- [ ] **A3.** Create a new document and draw an Arch Wall (BIM → Wall), so
      there is a wall face available to click later.
- [ ] **A4 (parts-library branch — startup fix).** This is the check for the
      reported "the tool doesn't even open" failure. Fully restart FreeCAD
      (not just switch workbenches) and switch to **BIM** again. Confirm A1
      still passes — the ArchPlus toolbar appears with all four buttons,
      Parts Library included — and check the Report view for any traceback
      from `InitGui.py`'s `add_ui()` (it swallows import errors into a
      printed message rather than raising). The fix under test: an
      `import partslib_object` at module scope in `partslib_gui.py`
      transitively imports `ArchComponent`, which may not yet be importable
      during the BIM workbench's `Initialize()`; that import has been moved
      into the two functions that actually need it (`refresh()`,
      `_onPlace()`), matching `windowsplus_gui.py`'s lazy
      `import windowsplus_object`. If the toolbar still fails to appear here,
      the hypothesis was wrong and the real cause is still open.

## Part B — Opening the panel and browsing

- [ ] **B1.** Click **Parts Library**. A new tab titled "ArchPlus Library"
      opens full-window in the MDI area (alongside any open document tabs),
      showing the **categories** screen: a card per room.
- [ ] **B2 (category screen).** Only rooms that actually contain a part are
      shown — with the seed library this is `Bathroom`,
      `Kitchen`, `Office` (not every room in `library/facets.json`'s
      vocabulary — a room with zero parts, e.g. `Bedroom`, must not be
      drawn at all). Each visible room card shows its icon (where
      `library/facets.json` declares one under
      `archplus/tools/partslib/resources/icons/facets/`), its label, a hairline rule, then that
      room's elements as rows with counts (e.g. `Toilets (1)` under
      `Bathroom`).
- [ ] **B3 (drilling in).** Click the `Toilets` row under `Bathroom`. The
      view switches to the **results** screen: the breadcrumb reads
      `All › Bathroom › Toilets`, and the card grid shows the WC (demo)
      part.
- [ ] **B4 (breadcrumb navigation).** Click `Bathroom` in the breadcrumb.
      The results screen stays open but now shows every part in the
      Bathroom room (both the WC and, since it is multi-room, the Base
      cabinet if it also declares Bathroom — otherwise just the WC), and
      the breadcrumb shrinks to `All › Bathroom`. Click `All`. This returns
      to the categories screen.
- [ ] **B5 (multi-valued room facet).** From the categories screen, confirm
      **the WC (demo) part's element row/count appears under both the
      `Bathroom` and `Bedroom` room cards** — this is the multi-valued
      `room` facet working, matching `category_tree`'s "one part counted
      once per room it belongs to" behaviour.
- [ ] **B6 (search).** From a results screen, type `toilet` in the search
      box. Only the WC remains, matched on its keyword.
- [ ] **B7.** Clear the search. Select **Base cabinet** in the grid. The
      detail sidebar shows a preview, the part name, primary parameter labels
      and the description. Its grid card reads `Width | Depth | Height`.
- [ ] **B8.** In the parameter form, type `80` into **Width** (the fields are
      in centimetres). The value is accepted and the preview rebuilds to an
      800 mm cabinet after one debounced rebuild, not once per keystroke.
- [ ] **B9 (empty/error safety).** Confirm no traceback ever appeared while
      opening the panel and browsing this session — the categories screen,
      breadcrumb, grid and sidebar all rendered without a Python console
      error.
- [ ] **B2a (fix round — dark theme legibility).** Switch FreeCAD to a dark
      theme (Edit → Preferences → General → Appearance, or whichever build
      of 1.1 you have exposes `Theme`/`StyleSheet` — the exact reported
      config was `Theme = "FreeCAD Dark"`, `StyleSheet = "FreeCAD.qss"`).
      Reopen the Parts Library tab (or click **Parts Library** again — the
      panel is rebuilt fresh each time `showPanel()` constructs it). On the
      categories screen: the room cards are a **dark** card colour clearly
      distinct from the page behind them (cards read as raised, not the
      same flat black-on-black), every room name and every element row
      (e.g. `Toilets (1)`) is legible near-white text — never the same
      colour as its own card background — and the cards are laid out as a
      **grid** (multiple cards per row when the tab is wide enough), not
      one full-width row per card. Resize the tab narrower and wider: the
      column count changes at natural card-width breakpoints and no card
      is left stretched edge-to-edge while others exist beside it. Switch
      back to a light theme and confirm the same screen still reads
      correctly (light cards, dark text) — this is the same code path,
      not a separate dark-only fix.
- [ ] **B10 (fix round — on-demand thumbnail fallback).** Neither seed part
      ships a committed `thumbnail.jpg`, so this exercises the fallback by
      default. Before opening the panel this session, confirm (in a file
      browser, or `os.path.exists` in the Python console against each
      part's own directory) that neither `base-cabinet`'s nor
      `wc-demo`'s folder under `library/` yet contains a `thumbnail.jpg`.
      Open the panel and drill in to view both cards: they still show their
      names even with no icon yet. Close the tab, and confirm each part's
      folder now contains a freshly-rendered `thumbnail.jpg`. Reopen the
      panel: both cards now show an icon, read straight from that file (no
      re-render — check the file's mtime is unchanged across the reopen).

## Part C — Preview pane and detail sidebar (confirmed static fallback)

- [ ] **C1 (the preview half of B7).** With Base cabinet selected, confirm
      the detail sidebar shows a rendered still image of the part (not a
      live/rotatable 3D view — that is expected on FreeCAD 1.1, see the
      caveat above), alongside the name, parameter form and description. Confirm the Report view shows at most ONE
      "live 3D preview is unavailable on this FreeCAD build" warning for the
      whole session, not one per part selected. The bar for this check is
      "the sidebar shows a still preview", not "the live preview embeds".
- [ ] **C2.** Expand **More parameters**. Confirm the additional fields appear
      below the primary fields, including the dimmed italic derived field
      **Doors**. Edit **Doors** and confirm it becomes active rather than
      dimmed; click **Reset** and confirm it returns to the derived state.
- [ ] **C3.** Edit a primary parameter while the part is still in the panel
      (for example, set cabinet **Width** to `800`). Confirm a fresh cached
      preview image appears for the new parameter set under the part's
      `.cache/` folder, rather than reusing the old preview.

### Parameter checks

These are the focused checks for the parameter form and object state:

- [ ] **P1.** Selecting a base cabinet shows **Width**, **Depth** and
      **Height** as editable fields, with **More parameters** collapsed beneath
      them.
- [ ] **P2.** Typing `80` into **Width** rebuilds the preview once, not once
      per keystroke.
- [ ] **P3.** Expanding the form shows **WorktopThickness**, **KickHeight**
      and a dimmed italic derived **Doors** field; editing **Doors** un-dims it.
- [ ] **P4.** **Reset** restores every field and re-dims **Doors**.
- [ ] **P8.** Setting cabinet **Width** to `800` rebuilds the cabinet with two
      door leaves; count the leaves in the preview geometry.
- [ ] **P9.** Pin **Doors** to `3` and confirm the pinned value survives
      recompute.
- [ ] **P10.** **Reload from library** restores the cabinet geometry to two
      door leaves and discards the pinned value.
- [ ] **P11.** Open an old document: its shape remains unchanged and its
      legacy selector is hidden.
- [ ] **P12.** A selected television's **Mounting** option changes its host
      placement without changing the part's other parameters.

### Display-unit checks

Length fields are pinned to centimetres (inches under an imperial schema),
not to the FreeCAD unit schema itself — `part.json` and every property on a
placed part stay in millimetres. Only U1 and U2 can be checked headlessly;
the rest need the real widget, and U3 is the one piece of this whose
FreeCAD-side answer no test can prove (`units.is_imperial()` reads the live
schema through an API this project cannot exercise outside the app).

- [ ] **U1.** Selecting a base cabinet shows **Width** as `60.0 cm`, not
      `600 mm`, one field per row, with the value AND its unit fully visible.
      Drag the splitter to make the sidebar as narrow as it goes and confirm
      nothing is clipped.
- [ ] **U2.** Type `800 mm` into **Width**. The field settles on `80.0 cm`
      and the preview rebuilds to an 800 mm cabinet. Repeat with `2 ft`
      (→ `60.96 cm`) and, in a `"` field, `5' 6"`.
- [ ] **U3.** Set **Edit → Preferences → General → Units** to
      *Building US (ft-in)* and reselect the part. Every length field now
      reads in inches (**Width** ≈ `23.62 in`). Switch back to *Standard (mm)* and reselect: the fields return to
      centimetres — NOT to millimetres, which is the point of pinning them.
      If a metric schema ever shows inches, `units.is_imperial()` misread the
      schema; report the schema name.
- [ ] **U4.** Type nonsense (`abc`) into a length field and press Tab. The
      field keeps the value it had; it does not fall to `0` and does not
      rebuild the part.
- [ ] **U6.** Type `2 ft` into a centimetre **Width** field. It settles on
      `61.0 cm` and the part is built 610 mm wide - the number shown is the
      number built, not 60.96 cm rounded for display.
- [ ] **U7.** Select the **King bed**. Its **Width** field reads `180.0 cm`
      and the placed part measures 1800 mm, not 1800.61 mm. (This is the
      overshoot that used to make the deleted W/D/H readout say `180.1 cm`;
      `geometry.measure()` now uses the tight bounding box.)
- [ ] **U5.** Place the part, select it, and confirm the property editor's
      **Width** still shows the FreeCAD unit schema's own unit (millimetres
      under *Standard*). The panel is the only surface that pins a unit; a
      placed part remains an ordinary `App::PropertyLength`.

## Part D — Placement

- [ ] **D1 (brief check 9).** With a document and its 3D view already open
      in another MDI tab, select Base cabinet in the library tab and click
      **Place in 3D view**. The MDI area switches to the document's 3D view
      tab automatically (Place activates it — the Snapper needs an active
      3D view to pick a point in). Click a point on the floor. Exactly ONE
      object named "Base cabinet" appears in the tree — expand it and
      confirm it has **no children**.
- [ ] **D2 (brief check 10).** Select it. In the property editor confirm
      `PartId` = `base-cabinet` (greyed out/read-only), `Description` is
      populated, and `IfcType` = `Furniture`. A **Parameters** group is
      present and no legacy selector is shown.
- [ ] **D3.** Change the object's **Width** to `800` in the property editor.
      It rebuilds in place and keeps its position; the cabinet geometry has two
      door leaves.
- [ ] **D8.** Select a television in the browser. It shows **Size (in)** and a
      **Mounting** dropdown; choosing **Wall-mounted** makes **Place in 3D
      view** host it on a wall.
- [ ] **D9.** Confirm grid cards read `Width | Depth | Height` under the part
      name.
- [ ] **D10.** Select a placed object. Its **Parameters** group is present and
      no legacy selector is shown.
- [ ] **D4 (brief check 12).** Select the WC in the panel, click
      **Place in 3D view**, then click a wall face. It lands at the wall
      base + 400 mm and orients to the wall.
- [ ] **D5 (brief check 13).** The library tab is still open (in the MDI
      area's tab list). Place a second cabinet without reopening anything.
- [ ] **D6 (deferred, Task 14).** Click **Place in 3D view** on any part,
      then click on empty space (no face under the cursor) instead of a
      wall/floor. The part still places (using the no-host fallback)
      without raising an exception.
- [ ] **D7 (fix round — ghost tracker).** Select Base cabinet, click
      **Place in 3D view**. Before clicking to commit, move the mouse
      around the 3D view: a translucent box sized to the cabinet's measured
      dimensions follows the cursor and re-orients over a wall face vs. the
      floor. Click to commit — the tracker disappears at the same moment
      the real object appears (no lingering ghost box).
- [ ] **D7a (repeat placement).** Immediately after D7's click commits the
      first cabinet, confirm the ghost tracker box is STILL visible and
      following the cursor (the Snapper has re-armed itself) without
      reopening the library tab or clicking **Place in 3D view** again.
      Click a second point: a second "Base cabinet" object appears, and the
      tracker keeps following the cursor for a third pick. Repeat this two
      or three times in a row to confirm the loop keeps re-arming.
- [ ] **D7b (Esc ends the loop cleanly).** While the tracker from D7a is
      still following the cursor, press **Escape** (or right-click) instead
      of clicking. Confirm: (1) the ghost tracker box disappears — no
      leftover geometry in the 3D view; (2) no further object is placed;
      (3) the MDI area switches back to the ArchPlus Library tab
      automatically, landing you back where you started rather than
      leaving you on the 3D view tab.

## Part E — IFC properties and export round-trip (deferred, Task 10)

- [ ] **E1.** With the placed Base cabinet selected, confirm in the
      property editor that `IfcProperties` reflects
      `Reference = ArchPlus demo` (from the manifest's
      `Pset_ManufacturerTypeInformation;;IfcLabel;;ArchPlus demo` string).
- [ ] **E2.** Export the document to IFC (File → Export → IFC) and re-import
      it, or open the exported file in a viewer/text editor. Confirm the
      `Pset_ManufacturerTypeInformation.Reference` property round-trips as
      an `IfcLabel` with value `ArchPlus demo`, and that both placed
      objects export with `IfcType` = `Furniture` (cabinet) and
      `Sanitary Terminal` (WC) respectively.

## Part F — Reload from library and derived-parameter handling (deferred, Tasks 11)

- [ ] **F1 (brief check 14).** Right-click the placed Base cabinet in the
      tree → **Reload from library** runs without error.
- [ ] **F2 (no silent rebuild on document open).**
      1. Note the current shape/dimensions of the placed Base cabinet.
      2. Save the document and close it.
      3. On disk, edit `library/basic/base-cabinet/part.json` and change
         one dimension under `params` (e.g. bump `Height`'s `default`).
      4. Reopen the document. **Expected: the object's geometry is
         unchanged** — it still shows the old dimension. Opening/recomputing
         a document must never silently rebuild a placed part from a
         since-edited manifest.
      5. Right-click the object → **Reload from library**. **Expected: now**
         the geometry updates to the new dimension from the edited
         `part.json`. Revert your edit to `part.json` afterwards so the
         shipped content matches what is committed.
- [ ] **F3 (derived values restore safely).** Place a Base cabinet and set
      its **Width** to `800` in the property editor. Pin **Doors** to `3` and
      confirm the custom value survives recompute. Right-click →
      **Reload from library**. **Expected:** Reload succeeds, the cabinet
      geometry returns to two door leaves (the derived value for width `800`),
      the pin is discarded, and no exception/traceback appears.
- [ ] **F4 (deferred, Task 11).** Right-click a placed part, choose
      **Reload from library** after having renamed/deleted its `id` from
      the library entirely (simulate by temporarily renaming the part's
      folder). Confirm `reloadFromLibrary()` returns `False`-equivalent
      behaviour: a console error appears and the object's shape is left
      untouched (no crash). Restore the folder name afterwards.

## Part G — Save/reopen and cleanup (brief checks 15–16)

- [ ] **G1 (brief check 15).** Save the document, close it, reopen it. The
      parts still render, and nothing rebuilt on open (dimensions match
      what was last saved, not the current `part.json` — consistent with
      Part F2 above).
- [ ] **G2 (brief check 16).** Delete a placed part. Confirm the tree is
      left completely clean — no orphaned objects (no leftover Part
      Shape/Feature children, no stray geometry).

## Part H — Panel lifecycle (MDI tab, self-healing)

- [ ] **H1 (tab close + self-heal).** Close the ArchPlus Library tab (its
      own close button/X, not the workbench or a document). Click
      **Parts Library** again. A working tab re-appears (a fresh one, since
      closing an MDI sub-window destroys it) showing the categories screen,
      and it calls `refresh()` — confirm this by checking that any change
      made to the library on disk earlier in this session (if any) is
      picked up. No `RuntimeError` appears in the console during this
      close/reopen cycle.
- [ ] **H2.** With the library tab open, switch to a different document tab
      (or create a new document) in the MDI area, then switch back to the
      library tab. It survives the document switch without a `RuntimeError`
      in the console and without losing its current screen/selection.
- [ ] **H3 (single construction path).** Repeat H1 two or three times in a
      row (close the tab, reopen via the toolbar button, close again).
      Each cycle yields exactly ONE library tab — never zero, never two —
      and the Report view never shows a traceback from `showPanel()`.

## Part I — Offscreen thumbnail rendering (deferred, Task 9)

Run in the FreeCAD Python console. The add-on directory and the output path
are both derived at run time — this is the same `getUserAppDataDir() +
"Mod"` location README.md's Installation section already points to, so
nothing here is specific to any one machine or username:

```python
import os, sys, tempfile
addon_dir = os.path.join(FreeCAD.getUserAppDataDir(), "Mod", "ArchPlus")
sys.path.append(addon_dir)
import Part
import archplus.tools.partslib.thumbs as pt
thumb_path = os.path.join(tempfile.gettempdir(), "archplus_thumb_test.png")
print(pt.render_shape(Part.makeBox(360, 540, 400), thumb_path))
print(thumb_path)
```

- [ ] **I1.** Prints `True`, and the printed `thumb_path` file shows a
      shaded box on white.
- [ ] **I2.** If it instead prints `False`: `SoOffscreenRenderer` failed on
      this machine's GL/driver setup. This is not a bug to chase down here —
      note it, because it means committed `thumbnail.jpg` files become
      mandatory for every future part (fresh offscreen rendering can never
      be relied on on this machine), and that finding should be recorded
      back into the spec.

## Part J — builder resolution and shape building sanity check (deferred, Task 8)

`demo.py` and its synthetic `box`-shaped builder are gone — a builder now has
to live in a real part's own folder, so this check resolves and builds a
real part (`library/basic/nightstand`) instead of a synthetic one. Run in
the FreeCAD Python console. As in Part I, the add-on directory is derived at
run time rather than hard-coded:

```python
import os, sys
addon_dir = os.path.join(FreeCAD.getUserAppDataDir(), "Mod", "ArchPlus")
sys.path.append(addon_dir)
import archplus.tools.partslib.geometry as pg

part_dir = os.path.join(addon_dir, "archplus", "tools", "partslib",
                         "library", "basic", "nightstand")
resolved = {"geometry": {},
            "params": {"Width": {"default": 400},
                       "Depth": {"default": 350},
                       "Height": {"default": 500}}}
builder = pg.select_builder(resolved, part_dir)
print(builder)
shape = pg.build_shape(resolved, part_dir)
print(pg.measure(shape))
```

- [ ] **J1.** `select_builder` prints the nightstand's own `build` function,
      e.g. `<function build at ...>` whose `__module__` is
      `archplus.tools.partslib.library.basic.nightstand.builder` — resolved
      because that folder holds a `builder.py`, not because the manifest
      named anything.
- [ ] **J2.** `pg.measure(shape)` prints
      `{'Width': 400.0, 'Depth': 350.0, 'Height': 500.0}` — the nightstand
      builder is written so the built shape's bounding box matches the
      advertised `Width`/`Depth`/`Height` exactly.
- [ ] **J3.** `len(FreeCAD.ActiveDocument.Objects)` is unchanged before and
      after calling `build_shape` — building a shape must add nothing to
      the document tree.

## Part K — Restoring a document with a missing part id (deferred, Task 10)

- [ ] **K1.** Take a saved document containing a placed library part.
      Temporarily rename that part's folder under `library/` (or its
      `part.json`) so the id can no longer be found, then reopen the
      document. Confirm the object keeps its last-saved shape on screen and
      prints a console warning, without altering `obj.Shape`. Restore the
      folder/file name afterwards.

---

## Wrap-up

- [ ] Every checkbox above is ticked, or the specific failure and its
      resolution (e.g. an unexpected `PREVIEW_LIVE_ALLOWED` override) is
      recorded here:

  ```
  (record any deviations / fixes applied during this verification pass)
  ```

- [ ] If any `part.json` edits made for Parts F2/F3/K1 were left in place by
      mistake, `git diff library/` is empty before closing out this pass.
