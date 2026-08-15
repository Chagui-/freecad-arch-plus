# Parts Library — manual verification checklist

This checklist is the deferred, human-in-FreeCAD verification for the whole
Parts Library feature (Tasks 7–15, plus the pass-2 restructure into a
full-window MDI tab with a two-screen catalogue browser). None of it can be
run headlessly: it needs a real FreeCAD 1.1 process, a real Qt event loop and
(for the preview and thumbnail checks) a real GL/offscreen context. Automated
coverage stops at `uv run --with pytest --no-project pytest tests/ -q` (122
passed at the time this doc was written, including `tests/test_partslib_theme.py`'s
headless coverage of the dark/light theme decision); everything below is
what that suite cannot see.

## The library ships EMPTY

`library/` now contains only `facets.json` (the faceted vocabulary) — no
parts. The two placeholder parts this checklist was originally written
against (`base-cabinet`, `wc-demo`) proved the pipeline during development
and have since been removed now that real content is authored on a separate
branch. **Every step below that involves placing, previewing, selecting
variants, or reading parameters off a part (all of Parts B7 onward, C, D, E,
F, G, I9/B10's thumbnail checks, J, K) cannot run until you have added at
least one real part under `library/`.** Steps that only exercise the empty
library itself — A (startup/toolbar), B1/B2 (the categories screen's new
empty-state message and its library-path hint), B6-as-a-search-with-nothing
(the results screen's empty-state message) — remain valid as written today.
The rest of the checklist is not wrong, only dormant: it becomes runnable
again, unchanged, the moment a part exists.

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
is no longer part of this checklist's bar for success. Grouping, search,
variants, measurements, placement and everything else the panel does are
unaffected by the fallback.

---

## Part A — Startup and toolbar

- [ ] **A1.** Restart FreeCAD 1.1, switch to the **BIM** workbench. The
      **ArchPlus** toolbar shows a fourth button with the Parts Library icon
      (`Resources/icons/PartsLibrary.svg`), rendering correctly and visually
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
      shown — with the seed library this is `Bathroom`, `Cloakroom`,
      `Kitchen`, `Office` (not every room in `library/facets.json`'s
      vocabulary — a room with zero parts, e.g. `Bedroom`, must not be
      drawn at all). Each visible room card shows its icon (where
      `library/facets.json` declares one under
      `Resources/icons/facets/`), its label, a hairline rule, then that
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
      `Bathroom` and `Cloakroom` room cards** — this is the multi-valued
      `room` facet working, matching `category_tree`'s "one part counted
      once per room it belongs to" behaviour.
- [ ] **B6 (search).** From a results screen, type `toilet` in the search
      box. Only the WC remains, matched on its keyword.
- [ ] **B7.** Clear the search. Select **Base cabinet** in the grid. The
      detail sidebar on the right shows a preview, the part name, variant
      chips, `W 600   D 560   H 720 mm`, and the description.
- [ ] **B8.** Click the `800 mm` variant chip. It becomes the selected chip
      (visually distinct from the others) and the measurements change to
      `W 800`.
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
      ships a committed `thumbnail.png`, so this exercises the fallback by
      default. Before opening the panel this session, confirm (in a file
      browser, or `os.path.exists` in the Python console against each
      part's own directory) that neither `base-cabinet`'s nor
      `wc-demo`'s folder under `library/` yet contains a `thumbnail.png`.
      Open the panel and drill in to view both cards: they still show their
      names even with no icon yet. Close the tab, and confirm each part's
      folder now contains a freshly-rendered `thumbnail.png`. Reopen the
      panel: both cards now show an icon, read straight from that file (no
      re-render — check the file's mtime is unchanged across the reopen).

## Part C — Preview pane and detail sidebar (confirmed static fallback)

- [ ] **C1 (the preview half of B7).** With Base cabinet selected, confirm
      the detail sidebar shows a rendered still image of the part (not a
      live/rotatable 3D view — that is expected on FreeCAD 1.1, see the
      caveat above), alongside the name, variant chips, measurements and
      description. Confirm the Report view shows at most ONE
      "live 3D preview is unavailable on this FreeCAD build" warning for the
      whole session, not one per part selected. The bar for this check is
      "the sidebar shows a still preview", not "the live preview embeds".
- [ ] **C2 (deferred, Task 14).** Click the `1000 mm` variant chip while
      still in the panel (not yet placed). The preview image updates to the
      new width alongside the measurements (rendered fresh for that variant
      and cached under the part's `.cache/` folder — check the folder now
      contains a PNG named after the variant).

## Part D — Placement

- [ ] **D1 (brief check 9).** With a document and its 3D view already open
      in another MDI tab, select Base cabinet in the library tab and click
      **Place in 3D view**. The MDI area switches to the document's 3D view
      tab automatically (Place activates it — the Snapper needs an active
      3D view to pick a point in). Click a point on the floor. Exactly ONE
      object named "Base cabinet" appears in the tree — expand it and
      confirm it has **no children**.
- [ ] **D2 (brief check 10).** Select it. In the property editor confirm
      `PartId` = `base-cabinet` (greyed out/read-only), `Variant` = `800 mm`
      (or whichever variant was selected at placement time), `Description`
      is populated, `IfcType` = `Furniture`.
- [ ] **D3 (brief check 11).** Change `Variant` to `1000 mm` in the property
      editor. The object rebuilds in place and keeps its position.
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
- [ ] **D8 (parts-library branch — editable dimensions).** Select the placed
      Base cabinet (any variant). In the property editor, confirm a new
      **Parameters** group appears alongside **Part**, containing `Width`,
      `Depth`, `Height` as editable (not read-only) Length properties. Change
      `Width` to `750` — a size the manifest's shipped variants (600/800/
      1000 mm) do not offer. The object rebuilds in place at 750 mm (check
      both the property editor and the 3D view) and its placement is
      unchanged. This proves the dimension is genuinely editable, not just
      re-picking a shipped variant.
- [ ] **D9 (parts-library branch — variant reseed).** With the object still
      at `Width = 750` from D8, change `Variant` to `1000 mm`. Confirm
      `Width` snaps to `1000` (the new variant's declared default) rather
      than staying at `750` — switching `Variant` deliberately discards
      hand-edited Parameter values, since a variant is a different catalogue
      product and a surviving stale edit would match no entry in it. Edit
      `Width` to a custom value again, then switch `Variant` to yet another
      label: confirm it reseeds again, with no console error and no
      duplicate/lingering rebuild artefacts — this exercises the guard
      around one Variant change re-seeding several Parameter properties at
      once.
- [ ] **D10 (fix round — reload discards hand-edits too).** Place a fresh
      Base cabinet and edit `Width` to a custom value (e.g. `750`, not one
      of the shipped variants). Right-click the object → **Reload from
      library**, leaving `Variant` untouched (the same variant is still
      selected — this is the common case, and the one the fix targets).
      Confirm `Width` snaps back to the current variant's manifest default
      rather than staying at `750` — "Reload from library" means "take the
      library's current truth", so it must discard hand-edits exactly like
      switching `Variant` does, not only when the cascade from reassigning
      `Variant` happens to fire.
- [ ] **D11 (fix round — no dead editable field survives a variant
      switch).** Pick (or temporarily edit a `part.json` to create) a part
      whose variants declare a different set of params — e.g. one variant
      with `Width`/`Depth`/`Height` and another that drops one of them.
      Place it on the first variant and confirm all its params show as
      editable fields in the **Parameters** group. Switch to the variant
      that declares fewer params. Confirm the now-undeclared property is no
      longer visible in the property editor (hidden, not deleted) rather
      than lingering as a field that silently does nothing. Switch back to
      the first variant: confirm the property reappears as editable. If you
      edited a `part.json` for this check, revert it afterwards.

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

## Part F — Reload from library and stale-variant handling (deferred, Tasks 11)

- [ ] **F1 (brief check 14).** Right-click the placed Base cabinet in the
      tree → **Reload from library** runs without error.
- [ ] **F2 (Check 1 from the Task 10/11 fix round — no silent rebuild on
      document open).**
      1. Note the current shape/dimensions of the placed Base cabinet.
      2. Save the document and close it.
      3. On disk, edit `library/furniture/base-cabinet/part.json` and change
         one dimension under `params` (e.g. bump `Height`'s `default`).
      4. Reopen the document. **Expected: the object's geometry is
         unchanged** — it still shows the old dimension. Opening/recomputing
         a document must never silently rebuild a placed part from a
         since-edited manifest.
      5. Right-click the object → **Reload from library**. **Expected: now**
         the geometry updates to the new dimension from the edited
         `part.json`. Revert your edit to `part.json` afterwards so the
         shipped content matches what is committed.
- [ ] **F3 (Check 2 from the Task 10/11 fix round — stale variant remaps
      safely).**
      1. Place a Base cabinet and set `Variant` to a non-first value (e.g.
         `1000 mm`).
      2. Save and close the document.
      3. On disk, temporarily remove the `1000 mm` entry from
         `variants` in `library/furniture/base-cabinet/part.json` (leaving
         `600 mm` and `800 mm`).
      4. Reopen the document — the cached shape and `Variant` label may
         still show the now-stale `1000 mm` string.
      5. Right-click → **Reload from library**. **Expected:** it succeeds,
         `Variant` remaps to the first remaining label (`600 mm`), a
         `PrintWarning` appears in the Report view naming the missing
         variant and its replacement, and — the key assertion — **no
         exception/traceback appears** anywhere. Restore the removed
         variant in `part.json` afterwards.
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
import Part, partslib_thumbs as pt
thumb_path = os.path.join(tempfile.gettempdir(), "archplus_thumb_test.png")
print(pt.render_shape(Part.makeBox(360, 540, 400), thumb_path))
print(thumb_path)
```

- [ ] **I1.** Prints `True`, and the printed `thumb_path` file shows a
      shaded box on white.
- [ ] **I2.** If it instead prints `False`: `SoOffscreenRenderer` failed on
      this machine's GL/driver setup. This is not a bug to chase down here —
      note it, because it means committed `thumbnail.png` files become
      mandatory for every future part (fresh offscreen rendering can never
      be relied on on this machine), and that finding should be recorded
      back into the spec.

## Part J — `demo.box` shape building sanity check (deferred, Task 8)

Run in the FreeCAD Python console. As in Part I, the add-on directory is
derived at run time rather than hard-coded:

```python
import os, sys
addon_dir = os.path.join(FreeCAD.getUserAppDataDir(), "Mod", "ArchPlus")
sys.path.append(addon_dir)
import partslib_geometry as pg

resolved = {"geometry": {"builder": "demo.box"},
            "params": {"Width": {"default": 500},
                       "Depth": {"default": 400},
                       "Height": {"default": 300}}}
shape = pg.build_shape(resolved, ".")
print(pg.measure(shape))
```

- [ ] **J1.** Prints `{'Width': 500.0, 'Depth': 400.0, 'Height': 300.0}`.
- [ ] **J2.** `len(FreeCAD.ActiveDocument.Objects)` is unchanged before and
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
