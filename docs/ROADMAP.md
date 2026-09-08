# Roadmap

## Walls

- [x] Shipped — sketch-based segmented walls with inherited overrides,
  fallback segment, hosted doors and windows, and interactive splitting
  (see [TOOLS.md](TOOLS.md#walls)).
- [x] Shipped — on-select length dimensions in the 3D view: a dimension
  line with oblique end ticks and a length label drawn above the selected
  face's wall run (one per run when the whole segment is selected; Coin
  overlay, no document objects; tracks reflows; see
  [TOOLS.md](TOOLS.md#walls)).
- [ ] Backlog — interactive in-view controls: endpoint handles that edit
  the shared sketch (whole connected runs only; plane-projected drags,
  min-length clamps, opening-embedding validation since hosted openings
  do not follow the wall, one undo transaction per drag).

## Stairs

- [ ] Add balusters and extend railing support to turns (railing links and
  the wire path are inherited from ArchStairs, but only follow the first
  flight).
- [ ] For half-turns, support spacing between the two stairways.

## Windows

- [ ] Muntins/grille (divided lite grids, e.g. 2×2, 3×3)
- [ ] Awning/hopper (top/bottom-hung) and tilt-and-turn operations
- [ ] Triple-pane and double-casement-plus-fixed configurations
- [ ] Real projecting sill geometry (currently the bottom jamb is flush)
- [ ] Make the "Invert Hinge Position" context-menu entry reachable — the
  hinge-edge guard counts the same edge duplicated across a sash's frame and
  glass parts, so the menu item never appears (only "Invert Opening
  Direction" does).
- [ ] Reposition preserves the sill height instead of snapping to the wall
  base (the panel button's tooltip claims it already does).
