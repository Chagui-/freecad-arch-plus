# Parts Library — manual verification checklist

This checklist is the deferred, human-in-FreeCAD verification for the whole
Parts Library feature (Tasks 7–15). None of it can be run headlessly: it
needs a real FreeCAD 1.1 process, a real Qt event loop and (for the preview
and thumbnail checks) a real GL/offscreen context. Automated coverage stops
at `uv run --with pytest --no-project pytest tests/ -q` (88 passed at the
time this doc was written); everything below is what that suite cannot see.

Work through it top to bottom in a single FreeCAD session. Each step has a
checkbox — tick it only after you have actually observed the stated result,
not merely run the action.

## ⚠️ Read this before you start: `PREVIEW_LIVE` is UNVERIFIED

`partslib_gui.py` sets `PREVIEW_LIVE = True` near the top of the file. This
turns on a live 3D preview in the detail pane using
`pivy.quarter.QuarterWidget` embedded inside the dock's Qt layout. **This
spike was never run** — nobody has confirmed that `QuarterWidget` actually
embeds correctly under FreeCAD 1.1's Qt6/PySide shim on this machine.

If Check 7 below (the live preview) fails to appear, crashes, throws a
console traceback on selecting a part, or embeds as a broken/blank widget:

> **The fix is one line.** Open `partslib_gui.py`, find `PREVIEW_LIVE = True`
> near the top of the file, and change it to `PREVIEW_LIVE = False`. This
> disables the embedded live preview only — grouping, search, variants,
> measurements, placement and everything else the panel does are
> independent of this flag and are unaffected by the fallback.

Do not spend time debugging `QuarterWidget` itself before trying the flag
flip — it is the accepted, pre-agreed mitigation for exactly this risk.

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

## Part B — Opening the panel and browsing (brief Step 5, checks 1–8)

- [ ] **B1 (brief check 3).** Click **Parts Library**. A dock appears on the
      right titled "ArchPlus Library".
- [ ] **B2 (brief check 4).** The group list shows `Sanitary`, `Storage`.
      The grid shows the parts in the selected group.
- [ ] **B3 (brief check 5).** Switch **Group by** to `Room`. `Bathroom`,
      `Cloakroom`, `Kitchen`, `Office` appear, and **Wall-hung WC (demo)
      appears under both Bathroom and Cloakroom** — this is the
      multi-valued facet working.
- [ ] **B4 (brief check 6).** Type `toilet` in the search box. Only the WC
      remains, matched on its keyword.
- [ ] **B5 (brief check 7).** Clear the search. Select **Base cabinet**. The
      detail pane shows a preview, `W 600  D 560  H 720 mm`, and the
      description.
- [ ] **B6 (brief check 8).** Change **Variant** to `800 mm`. The
      measurements change to `W 800`.
- [ ] **B7 (deferred, Task 13).** Restart FreeCAD after choosing `Room` as
      Group by. Reopen the panel: the chosen facet persists across restarts
      (stored under `User parameter:BaseApp/Preferences/Mod/ArchPlus` →
      `PartsLibraryGroupBy`). Switch back to whichever grouping you prefer
      for the rest of this session.
- [ ] **B8 (deferred, Task 13 — empty/error safety).** Not applicable now
      that the library is populated, but confirm no traceback ever appeared
      on first opening the panel this session — the dock, tree and grid all
      rendered without a Python console error.

## Part C — Live preview (the unverified spike)

- [ ] **C1 (brief check 7, the preview half — SPIKE).** With Base cabinet
      selected, confirm a live 3D preview actually renders in the detail
      pane (a shaded box), not just the measurements/description. If this
      fails, apply the `PREVIEW_LIVE = False` fix described above, then
      re-open the panel and confirm the pane degrades gracefully (no crash,
      measurements/description/variant/Place button all still work) with
      the preview area simply absent or blank.
- [ ] **C2 (deferred, Task 14).** Switch **Variant** to `1000 mm` while
      still in the panel (not yet placed). The preview updates to the new
      width alongside the measurements.

## Part D — Placement

- [ ] **D1 (brief check 9).** Click **Place**, then click a point on the
      floor. Exactly ONE object named "Base cabinet" appears in the tree —
      expand it and confirm it has **no children**.
- [ ] **D2 (brief check 10).** Select it. In the property editor confirm
      `PartId` = `base-cabinet` (greyed out/read-only), `Variant` = `800 mm`
      (or whichever variant was selected at placement time), `Description`
      is populated, `IfcType` = `Furniture`.
- [ ] **D3 (brief check 11).** Change `Variant` to `1000 mm` in the property
      editor. The object rebuilds in place and keeps its position.
- [ ] **D4 (brief check 12).** Select the WC in the panel, click **Place**,
      then click a wall face. It lands at the wall base + 400 mm and
      orients to the wall.
- [ ] **D5 (brief check 13).** The dock is still open. Place a second
      cabinet without reopening anything.
- [ ] **D6 (deferred, Task 14).** Click **Place** on any part, then click on
      empty space (no face under the cursor) instead of a wall/floor. The
      part still places (using the no-host fallback) without raising an
      exception.

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

## Part H — Panel lifecycle (deferred, Task 13 fix round)

- [ ] **H1.** Close the Parts Library dock (its close button, not the
      workbench), then click **Parts Library** again. The same singleton
      dock re-appears (re-raised, not a second dock) and calls `refresh()`
      — confirm this by checking that any change made to the library on
      disk earlier in this session (if any) is picked up.
- [ ] **H2.** Switch to a different document (or create a new one) while
      the dock is open, then switch back. The dock survives the document
      switch without a `RuntimeError` in the console.

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
      resolution (e.g. the `PREVIEW_LIVE` flip) is recorded here:

  ```
  (record any deviations / fixes applied during this verification pass)
  ```

- [ ] If any `part.json` edits made for Parts F2/F3/K1 were left in place by
      mistake, `git diff library/` is empty before closing out this pass.
