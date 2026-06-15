# StairsPlus

A FreeCAD add-on that extends the built-in BIM/Arch **Stairs** tool with a
configuration dialog and an enhanced parametric stairs object.

It adds a **StairsPlus** toolbar and menu inside the **BIM** workbench. The
geometry engine is a modifiable copy of FreeCAD's `ArchStairs`, so every native
feature (flights, landings, stringers, IFC export) is preserved while new
behaviour is added on top.

## Features

- **Configuration dialog** (Task panel) with **live preview** — the stair
  renders in the 3D view as you change values, and updates as you edit.
- **Double-click to edit** an existing StairsPlus object, reusing the panel.
- **Comfort note** — live riser/tread readout and Blondel ratio (2R + T) check.
- **Configurable landing position** — `LandingStep` places the landing/turn on
  any step (0 = auto, centered) instead of always at the middle.
- **Half-turn winders** — a half-turn with no landing is built from winder
  (wedge) steps that sweep 180° while climbing, filling a square footprint with
  an optional square well/hole, instead of a flat landing.

## Installation

Clone (or copy) this repository into your FreeCAD user `Mod` folder:

- **Linux:** `~/.local/share/FreeCAD/Mod/StairsPlus` (or, for FreeCAD 1.1,
  `~/.config/FreeCAD/...`)
- **Windows (FreeCAD 1.1):**
  `%APPDATA%\FreeCAD\v1-1\Mod\StairsPlus`

The exact path is `FreeCAD.getUserAppDataDir()` + `Mod` (run it in FreeCAD's
Python console). Restart FreeCAD, switch to the **BIM** workbench, and use the
**StairsPlus** toolbar button.

## Usage

BIM workbench → **StairsPlus** toolbar → configure → **OK**. Double-click a
StairsPlus object in the tree to edit it.

## Requirements

- FreeCAD 1.1 (the BIM/Arch modules must be available).

## License

LGPL-2.1-or-later. This add-on includes a modified copy of FreeCAD's
`ArchStairs.py` (© 2013 Yorik van Havre), so as a derivative work it is licensed
under the same terms. See [LICENSE](LICENSE).
