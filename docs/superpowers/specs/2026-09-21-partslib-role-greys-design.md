# Parts library role greys — design

Date: 2026-09-21
Status: draft (awaiting user review)
Branch: `partslib-role-greys`

## Purpose

Every part in the library renders in one flat grey today, so a wardrobe is
an undifferentiated slab and a room of furniture reads as grey mush. Give
each part's *pieces* their own grey - a cabinet as carcass + doors +
worktop, a bed as base + mattress + headboard - the same idea as the
door's frame/leaf/knob.

The cap is the user's: **at most 3 greys on any one part, 2 for most**.

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

## The three greys

One scale, anchored on the door frame's own grey so the add-on reads as one
family (the doors' leaf 0.45 and knob 0.10 are a door's own three-step
scale; the steps below keep that separation at library scale):

| role | grey | what it is | examples |
|---|---|---|---|
| `top` | 0.82 light | the surface you use | worktops, table tops, shelves, counter tops |
| `soft` | 0.82 light | upholstery and bedding | cushions, mattresses, pillows, curtain fabric |
| `glass` | 0.82 light | glazing | mirror glass, shower screen, TV screen |
| `carcass` | 0.58 mid | the mass | bodies, boxes, case panels, plinths, posts, frames, tubs, bowls |
| `front` | 0.35 dark | applied fronts | doors, drawer fronts, fridge door slabs |
| `fitting` | 0.35 dark | hardware | handles, pulls, taps, knobs, burners, rails, legs, feet, finials |

Roles are semantic names, greys are few: six roles map onto three greys,
which is what makes the cap structural rather than a rule to remember.
Most parts land on 2 (a cabinet: carcass + front; a bed: carcass + soft);
a part that has a surface or a piece of hardware as well lands on 3 (a
kitchen unit: carcass + front + top).

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

`fuse_all` flattens the dict in order and fuses exactly as it does today,
so **the shape is unchanged**; the dict adds the roles and nothing else.
A piece whose role is obvious from its name keeps that name.

The two builders that return a bare shape split it into role pieces whose
union is the shape they build today - `mirror` becomes frame (`fitting`)
plus a thin glass slab on the recess floor (`glass`), cut so the recess
stays open - which is checked by the same volume/bbox comparison as
everything else.

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
- The object stores the per-face role names in a new `PartRoles`
  StringList property, so a saved document keeps its colours without
  rebuilding, and so the roles are legible in the file.
- The view provider colours `ShapeAppearance` face by face from the
  palette, exactly as the doors' `colorize` does, and leaves a Material
  the user set on the part alone.

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
i.e. visible**, and a fallback would paint visible patches the wrong grey.

## Out of scope (deferred, deliberately)

- **Browser thumbnails.** The offscreen renderer builds a Coin scene from
  a bare shape with a single material, so per-face greys there need the
  scene builder extended and the 36 committed thumbnails regenerated.
  Separate job; the 3D model is what this changes.
- **Glass transparency.** Mirror, shower screen and TV screen get the
  light grey, not the doors' translucent glass material.
- **One palette for the whole add-on.** The doors' three greys live in
  `doors/object.py`, and PR #31 is open on them; this branch starts from
  `main` and must not touch that file. The light step is the door frame's
  0.82 exactly; the mid and dark steps are this library's own.

## Verification

- **Geometry unchanged**, per part: volume, bounding box, solid count,
  face count and `isValid()` compared before and after the change, for all
  36 parts (the same harness on both sides of the branch).
- **Roles**: every face of every shipped part has a role; every role is in
  the palette; no part uses more than 3 distinct greys (with a printed
  2-vs-3 distribution, so the cap is visible rather than assumed).
- **Rendered contact sheet** of all 36 parts from the new colours, checked
  by eye - the only real test of whether the greys read as the parts.
- Existing suites: the headless pytest suite, the partslib FreeCAD tests,
  and the `archplus/freecad_tests` modules that touch placed parts.
