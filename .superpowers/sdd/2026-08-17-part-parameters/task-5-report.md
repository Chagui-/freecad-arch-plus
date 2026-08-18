# Task 5 Report

## Status

DONE

## Changes

- Replaced television's flat `variants` list and `Mounted` integer with the
  `ScreenSize` integer and `Mounting` choice params.
- Added floor/stand and wall/1100mm placement overrides to the television
  choice options.
- Derived television Width and Height from the diagonal ScreenSize using the
  specified 16:9-plus-bezel formula; explicit Width and Height values remain
  supported as pins.
- Replaced curtain's variants with the parameter set and derived `FoldCount`
  from Width when auto.
- Added the four specified content tests, including the previously unreachable
  65-inch stand-mounted television cell.

## Derivation ordering evidence

- television Width: assigned on builder.py line 31; its dependency `bezel` is
  assigned on builder.py line 22 and `diagonal` on line 27.
- television Height: assigned on builder.py line 35; its dependency `bezel` is
  assigned on builder.py line 22 and `diagonal` on line 27.
- curtain FoldCount: assigned on builder.py line 32; its dependency `width` is
  assigned on builder.py line 23.

The television builder assigns `bezel` exactly once, and both derived
Width/Height values are converted to float before first geometry use.
`mounted` remains the integer wall-bracket flag expected by the rest of the
builder, derived from `Mounting == "wall"` on builder.py line 38.

## Arithmetic sanity check

Using BezelWidth 18mm, the specified formula gives approximately:

- 55-inch: 1253.6 x 720.9mm
- 65-inch: 1475.0 x 845.4mm

## Verification

- Focused library content tests: 23 passed.
- Full suite: 229 passed.
- `git diff --check`: passed.
- No FreeCAD runtime geometry build was possible in headless WSL; the source
  ordering and parameter guards were reviewed directly.
