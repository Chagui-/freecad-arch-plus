# Wall "Rest segment" → "Fallback segment" — design

## Goal

"Rest segment" reads confusingly in the wall panel (rest of what?). Rename the
concept to **Fallback segment** everywhere it surfaces: panel labels,
Report-view warnings, the persisted `Rest` property, internal identifiers,
tests and docs. Behavior is unchanged — this is a vocabulary rename plus the
property migration it requires.

## Decisions

- **"Fallback segment"**, not "Default": the same dialog already uses
  "defaults" for inherited dimensions ("These are the defaults — children
  follow them unless they override."), which would give "default" two
  meanings in one panel. "Fallback" says exactly what the segment does:
  it catches every sketch edge no other segment claims.
- **Property `Rest` → `Fallback` with a restore-time migration**, so saved
  wall documents keep their flag (see below).
- Branch cut from `feat/wall-length-overlay` per user decision.

## User-visible strings

| Where | Before | After |
|---|---|---|
| `gui.py` root panel, Sketch & claims row | `Rest segment` | `Fallback segment` |
| `gui.py` segment panel note | "Rest and Sketch are set in the wall panel." | "Fallback and Sketch are set in the wall panel." |
| `model.py` warning | "Rest only applies to direct children of the wall; …" | "Fallback only applies to direct children of the wall; …" |
| `model.py` warning | "Rest segment '%s' ignores its explicit edges" | "Fallback segment '%s' ignores its explicit edges" |
| `model.py` warning | "Only one rest segment is allowed; …" | "Only one fallback segment is allowed; …" |
| `object.py` Report-view warning | "…unclaimed and no rest segment to build them" | "…unclaimed and no fallback segment to build them" |
| `object.py` `Edges` tooltip | "empty with Rest=true claims everything unclaimed" | "empty with Fallback=true claims everything unclaimed" |
| Property `Rest` (`App::PropertyBool`, group Wall) | shows as "Rest" in the property editor | renamed to `Fallback`; tooltip text unchanged |

The picker description ("This segment auto-claims any new sketch edge.
\"None\" = new edges build nothing.") already avoids the word and stays.

## Property rename + migration

`_Wall` gains `onDocumentRestored` — the doors, stairs, windows and partslib
proxies all re-run their property setup there; walls is currently the
outsider:

```python
def onDocumentRestored(self, obj):
    self.setProperties(obj, self.Type == TYPE_WALL)
    if self.Type == TYPE_SEGMENT and "Rest" in obj.PropertiesList:
        obj.Fallback = obj.Rest
        obj.removeProperty("Rest")
```

- `setProperties` adds every property guardedly (`"X" not in pl`), so a
  document saved before the rename gets `Fallback` created, the old flag's
  value is copied across, and `Rest` is removed. `removeProperty` in the
  restore path has the partslib precedent (`partslib/object.py:248`).
- Documents saved after the rename carry no `Rest`, so the block is a no-op.
- Re-running `setProperties` on restore is idempotent by construction.

## Internal renames (no behavior change)

- `model.py`: `ClaimNode(node, claimed, rest=False)` → `fallback=False`;
  attribute `.rest` → `.fallback`; locals `rest_nodes` / `rest_edges` /
  `rest_node` → `fallback_*`.
- `object.py`: `getattr(obj, "Rest", False)` → `"Fallback"`;
  `onChanged` touch tuple `("Edges", "Rest")` → `("Edges", "Fallback")`;
  `has_rest` → `has_fallback`; `makeWall` (`seg.Rest = True` →
  `seg.Fallback = True`) and its "one rest child" docstring; the
  edge-splitting comment "the rest rebuilds without those edges" reworded to
  say "the fallback" (that "rest" no longer means "remainder" there).
- `gui.py`: `self.rest` → `self.fallback`, `restForm`, `_collect(rest=…)`
  kwarg → `fallback=`, `vals["rest"]`, the `_loadFromObject` local.
- `tests/test_model.py`: names (`test_rest_*` → `test_fallback_*`), locals,
  and the assertion `"one rest" in w` → `"one fallback" in w`;
  `tests/test_panel.py` `p.rest` → `p.fallback`.
- `freecad_tests/verify_walls.py`: `seg.Rest`, the `.Rest = False` calls,
  `rest3`/`rest5` locals, check name "W1 rest child defaults".

## Docs

- `docs/TOOLS.md`: the **Rest segment** bullet and the panel description
  sentence.
- `docs/ROADMAP.md`: "rest segment" in the shipped-walls line.
- Out of scope: dated specs and plans under `docs/superpowers/` stay as
  historical records.

## Testing

- Headless suite (`uv run --no-project --with pytest python -m pytest -q`)
  stays green; renamed tests assert identical claim math.
- `verify_walls.py` gains a migration check: on a created segment, add a
  `Rest` bool by hand and remove `Fallback`, which reproduces a pre-rename
  document exactly; save, close, reopen, and assert `Fallback` carried the
  value and `Rest` is gone. This exercises both halves of the new
  `onDocumentRestored` for real.
- Panel smoke test in FreeCAD: the Edit Wall panel shows the "Fallback
  segment" row and claims stats still count auto-claimed edges.

## Risks

- `onDocumentRestored` now runs `setProperties` for every restored wall
  object — safe because every add is guarded; the other tools already do
  this.
- Assigning `obj.Fallback` during restore fires `onChanged`, which only
  touches segments — cheap and harmless before the first recompute.
