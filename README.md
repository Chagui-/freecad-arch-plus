# ArchPlus

A FreeCAD add-on that extends the built-in **BIM** workbench with enhanced
Arch tools. It adds an **ArchPlus** toolbar and menu inside the BIM workbench.

Currently it provides an enhanced parametric **Stairs** tool; more Arch tools
(e.g. doors, windows) are planned. The stairs geometry engine is a modifiable
copy of FreeCAD's `ArchStairs`, so every native feature (flights, landings,
stringers, IFC export) is preserved while new behaviour is added on top.

## Features (Stairs)

- **Configuration dialog** (Task panel) with **live preview** — the stair
  renders in the 3D view as you change values, and updates as you edit.
- **Double-click to edit** an existing stairs object, reusing the panel.
- **Comfort note** — live riser/tread readout and Blondel ratio (2R + T) check.
- **Configurable landing position** — `LandingStep` places the landing/turn on
  any step (0 = auto, centered) instead of always at the middle.
- **Half-turn winders** — a half-turn with no landing is built from winder
  (wedge) steps that sweep 180° while climbing, filling a square footprint with
  an optional square well/hole, instead of a flat landing.

## Installation

Clone (or copy) this repository into your FreeCAD user `Mod` folder:

- **Linux:** `~/.local/share/FreeCAD/Mod/ArchPlus` (or, for FreeCAD 1.1,
  `~/.config/FreeCAD/...`)
- **Windows (FreeCAD 1.1):**
  `%APPDATA%\FreeCAD\v1-1\Mod\ArchPlus`

The exact path is `FreeCAD.getUserAppDataDir()` + `Mod` (run it in FreeCAD's
Python console). Restart FreeCAD, switch to the **BIM** workbench, and use the
**ArchPlus** toolbar.

## Usage

BIM workbench → **ArchPlus** toolbar → **Stairs** → configure → **OK**.
Double-click a stairs object in the tree to edit it.

## TODO

- [ ] Implement quarter-turn stairs.
- [x] Rename the add-on to **ArchPlus** (doors and windows will be added later).
- [ ] Resolve the winder well issue.
- [ ] Support railings, balusters, etc.
- [ ] For half-turns, support spacing between the two stairways.
- [ ] UI: landing and winder steps are too similar — probably merge them into a
      single setting. *(done — unified into one break/turn setting.)*
- [ ] Publish to the FreeCAD Addon Manager. Needs a `package.xml`, but note:
      on FreeCAD 1.1 a manifest only loads the add-on if it declares a
      `<content><workbench>` (with `<subdirectory>.</subdirectory>`); a
      manifest with no workbench, or pointing `<classname>` at `BIMWorkbench`,
      misbehaves (nothing loads / BIM's icon gets replaced). Since this add-on
      injects into BIM rather than shipping its own workbench, publishing will
      likely require either a real `ArchPlusWorkbench` or targeting newer
      FreeCAD (which always runs the root `InitGui.py`). For now we ship no
      `package.xml` and rely on classic root-`InitGui.py` loading.

## Requirements

- FreeCAD 1.1 (the BIM/Arch modules must be available).

## License

LGPL-2.1-or-later. This add-on includes a modified copy of FreeCAD's
`ArchStairs.py` (© 2013 Yorik van Havre), so as a derivative work it is licensed
under the same terms. See [LICENSE](LICENSE).
