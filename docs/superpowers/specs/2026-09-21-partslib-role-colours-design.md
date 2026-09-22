# Parts library role colours — design

Date: 2026-09-21
Status: draft (awaiting user review)
Branch: `partslib-role-colours`

## Purpose

Every part in the library renders in one flat grey today, so a wardrobe is
an undifferentiated slab and a room of furniture reads as grey mush. Give
each part's *pieces* their own colour - a cabinet as carcass + doors +
worktop, a bed as base + mattress + headboard - the same idea as the
door's frame/leaf/knob.

The cap is the user's: **at most 3 colours on any one part, 2 for most**.

## Background: what already exists

- **Parts are one fused solid.** Builders assemble pieces (`[box, top] +
  pulls`, `[body] + doors + handles`, `[top] + legs + rails + shelf`) and
  fuse them. Measured across the 36 shipped parts: **34 come out as a
  single solid**, only `curtain` and `oven-cabinet` as two. There is no
  per-solid role to colour.
- **One choke point.** All 36 builders pass those pieces through
  `shapes.fuse_all(...)`; only `mirror` and `shower-base` return a bare
  shape without fusing anything.
- **Per-face colouring is already how doors are painted**:
  `doors/object.py`'s `colorize` + `DOOR_PART_COLORS` drive FreeCAD's
  per-face `ShapeAppearance`. The library's own view provider sets no
  colour at all today, so it inherits ArchComponent's default.
- **No material or colour vocabulary exists in the manifests** (grep over
  `library/basic`: zero hits outside prose), so this design introduces it.

## The colours

Two families, because furniture is two materials, and the user's second pass
over the palette asked for both: the first pass's three greys were too close
together to read apart, and wood needed its own shades.

**Wood** - the casework - in three lightnesses, and the same three
lightnesses in the grey family, so the two families have the same contrast
between their steps:

| role | colour | what it is | examples |
|---|---|---|---|
| `top` | 0.80 light wood | a wooden surface you use | worktops, table tops, shelves |
| `carcass` | 0.52 mid wood | the wood mass | bodies, case panels, plinths, frames |
| `front` | 0.24 dark wood | an applied wooden front | door slabs, drawer fronts |

**Not wood** - three steps apart, 80% white / mid grey / 80% black:

| role | colour | what it is | examples |
|---|---|---|---|
| `soft` | 0.80 white | upholstery and bedding | cushions, mattresses, pillows, fabric |
| `shell` | 0.80 white | a moulded body | a tub, a sink bowl, a cistern, a tray, a fridge, a bin |
| `glass` | 0.62 blue at 35% opacity | glazing, tinted and see-through | a shower screen, a mirror pane, a hob plate |
| `fitting` | 0.20 black | hardware | handles, pulls, taps, burners, feet, drains, seats |

The glazing is the one role that is not solid: alpha is opacity, so the
screen and the mirror pane are drawn over whatever is behind them, which is
how a glass pane reads as glass rather than as a grey plate.

`shell` exists because the role names are what tell the palette what a piece
is made of: a bathtub, a sink bowl, a cistern, a shower tray, a fridge and a
bin are all one moulded mass, and calling them `carcass` would have painted
them wood. The ten parts whose mass is not wood use it (see the retag in the
plan); everything else keeps the wood roles.

Roles are semantic names, colours are few: seven roles map onto six colours,
and the colours a part can use without contradicting itself never reach
four, which is what makes the cap structural rather than a rule to remember.
Most parts land on 2 (a cabinet: carcass + front; a bed: carcass + soft); a
part that also has a surface or a piece of hardware lands on 3 (a kitchen
unit: carcass + front + top). Three parts land on 1, honestly: a towel hook
and a roll holder are all metal, and a bathtub is one enamel mass.

## How a builder declares roles

`fuse_all` takes the pieces grouped by role instead of a flat list:

```python
# before
return sh.fuse_all([top, panel, pedestal] + modesty + pulls)

# after
return sh.fuse_all({
    "top": [top],
    "carcass": [panel, pedestal] + modesty,
    "fitting": pulls,
})
```

`fuse_all` groups the pieces and fuses them, which also reorders the fuse.
That cannot change the solid - a union is a union - but it can change how the
result's faces are subdivided, and `removeSplitter()` normalises most of that
back. **Volume, bounding box and solid count come out identical**; a face
count that moves is a subdivision, not a shape.

One consequence worth stating plainly, because it is visible: roles follow the
pieces a builder builds. Where a feature is a groove or a recess cut into the
mass rather than a piece - a kitchen unit's door seams, a television's screen
recess, an oven's recess - there is no piece to give a different colour,
so those parts stay at two (the mass plus the hardware or the worktop).
Making those fronts read would mean adding an applied piece, which is a
geometry change and a separate decision.

The two builders that return a bare shape split it into role pieces whose
union is the shape they build today - `mirror` becomes frame (`fitting`)
plus a thin glass slab on the recess floor (`glass`), cut so the recess
stays open - which is checked by the same volume/bbox comparison as
everything else.

`_shared.split_front(carcass, width, height)` is the same idea for the
cabinets whose doors are *cut* into the front rather than applied: it
returns the front `PANEL` (18mm) of the carcass as a piece of its own, plus
the rest, disjoint, so the door line can take the `front` colour while the
part's shape stays exactly as it was. The three parts that use it are the
wardrobe and the two tall units - the ones where the door line is the whole
of what you see.

## How a face gets its role

`fuse_all` computes the map at build time, because the pieces are only
there: for each face of the fused shape, a point 0.05mm *inside* the face
(along its reversed normal) is tested against the pieces in
increasing-volume order and the first piece containing it owns the face.
Fallbacks - a smaller epsilon, then the nearest piece's surface, then the
largest role - guarantee every face is assigned. Measured over the shipped
library: **0 to 4 faces per part need a fallback and none are left
unassigned**, at 5-355ms per part, once per unique build.

## How the colour reaches the screen

- `geometry.build_shape_and_roles()` returns `(shape, roles)`; the shape
  cache stores the map beside the shape, and `build_shape()` keeps its
  current signature and return type for every other caller (tests,
  thumbnails, placement).
- The object hands the per-face roles to its view provider as it rebuilds,
  which holds them on its proxy and paints `ShapeAppearance` face by face
  from the palette, exactly as the doors' `colorize` does, leaving a
  Material the user set on the part alone. They are deliberately NOT a
  property: declaring a new property on a placed part - on the object or on
  its view - breaks FreeCAD's undo and redo of that object's *other*
  properties, because the declaration is recorded inside the creation
  transaction and replaying it stops the rest of the restore. Nothing is
  lost: the colours themselves live in `ShapeAppearance`, which saves with
  the document, and the roles are only needed to paint, which a rebuild
  recomputes.

## Rejected approaches, with the measurements

**Colour per solid, by handing the document a compound of the pieces**
(the doors' own pattern). Bounding boxes come out identical for all 36
parts, but the volume inflates wherever pieces interpenetrate - the
builders overlap pieces deliberately ("so the fuse has material to join")
and cushions are pressed into their frames: **armchair +31%, sofa +20%,
chair +5.2%, gas hob +4.6%, coffee and side tables +3.1%**, and every
part becomes 2-13 solids instead of 1. A part's volume would stop
describing its material.

**Classify the fused faces by their support surface** (`Surface.isSame`,
or a canonicalised plane/axis/radius key). The fuse's `removeSplitter`
pass refits merged coplanar faces, so their surface matches no piece:
**17 of 32 parts had 1-15 unmatched faces, all of them 100mm² or larger,
i.e. visible**, and a fallback would paint visible patches the wrong colour.

## Out of scope (deferred, deliberately)

- **Browser thumbnails.** The offscreen renderer builds a Coin scene from
  a bare shape with a single material, so per-face colours there need the
  scene builder extended and the 36 committed thumbnails regenerated.
  Separate job; the 3D model is what this changes.
- **Glass transparency.** Mirror, shower screen and TV screen get the
  the palette's mid grey, not the doors' translucent glass material.
- **One palette for the whole add-on.** The doors' three greys live in
  `doors/object.py`, and PR #31 is open on them; this branch starts from
  `main` and must not touch that file. The light step is the door frame's
  0.82 exactly; the mid and dark steps are this library's own.

## Verification

- **Geometry unchanged**, per part: volume, bounding box and solid count
  compared against the values recorded from the library before the change,
  for all 36 parts; face count and `isValid()` reported alongside (a face
  count that moves is a subdivision, not a shape).
- **Roles**: every face of every shipped part has a role; every role is in
  the palette; no part uses more than 3 distinct colours, with the 2-vs-3
  distribution printed so the cap is visible rather than assumed. This is
  `archplus/freecad_tests/verify_part_colours.py`, run by `run_all.py`, and
  it also drives a placed part end to end - one material per face, painted
  with exactly its roles' colours, and a `Material` on the part left alone.
- **Rendered contact sheet** of all 36 parts from the new colours, checked
  by eye - the only real test of whether the greys read as the parts.
- Existing suites: the headless pytest suite, the partslib FreeCAD tests,
  and the `archplus/freecad_tests` modules that touch placed parts.
