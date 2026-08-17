# Colocated part builders and style families

**Date:** 2026-08-17
**Status:** approved, not yet implemented
**Supersedes:** §6.4 "Builders are central, not per-part" and the builder-symbol
half of §6.3 "Security", both in `2026-08-15-parts-library-design.md`. The
zero-executable-code property §6.3 reserved for user-supplied libraries is kept,
and strengthened from a declaration into a structural fact — see §4.1.

## 1. Why

§6.4 placed every builder in a central `partslib_builders/` package and named the
condition for revisiting the decision:

> Revisit when: builders start appearing one-per-part with no shared logic. The
> manifest already names builders by symbol, so adding colocation later is an
> `importlib` change and no format change.

That condition has been met. 29 builder functions serve 31 parts, and only two
are shared: `furniture.table` (dining-table, coffee-table) and `furniture.bed`
(king-bed, single-bed). The reuse that justified central placement did not
materialise — 27 of 29 builders are already one-per-part, and the real reuse
lives in `_shapes.py`, which is primitive vocabulary rather than part logic.

The cost of the current arrangement is that a part is not a unit. A part folder
holds `part.json` and `thumbnail.jpg`, while its geometry sits in a 872-line
module shared with thirteen unrelated parts. Deleting a part means also finding
and deleting an orphaned function, and nothing catches the omission.

A second problem surfaced while designing this. The library tree carries a
category level — `furniture/`, `kitchen/`, `sanitary/`, `fittings/` — that no
code reads. It is a single-valued taxonomy competing with the multi-valued facet
vocabulary the browser actually uses, so it cannot be made correct: `mirror`
declares `"room": ["Bathroom", "Bedroom"]` and a folder can only pick one. It
has already drifted unnoticed — `docs/PARTS-LIBRARY-VERIFICATION.md:360` names
`library/furniture/base-cabinet/`, but that part lives under `kitchen/`.

## 2. Scope

In scope: where builder code lives, how it is resolved, how the library tree is
organised, and how part ids are derived.

**Out of scope, deliberately.** The option model (`variants`) is unchanged by
this work. Replacing the single `variants` list with named option axes —
`diagonal_size`, `with_stand`, `drawers` — is a separate project with its own
spec. It touches `manifest.py`, `index.py`, `gui.py`, `object.py`, and all 21
manifests that declare variants, and it changes the property model on every
placed part. It is sequenced second because pushing a part's coupled parameters
(a 800mm cabinet has two doors) into that part's own builder is only possible
once per-part builders exist.

## 3. Layout

### 3.1 A family is a style, not a part type

The unit that owns shared code is a **family**: one design language, one
manufacturer's series. Not a part type. `basic-table/` and `basic-cabinet/`
would reproduce the category problem one level down — for a real brand there is
no rule deciding whether a part belongs in `ikea-table/` or `ikea-storage/`.
Naming a family after its style makes the question factual, because a part has
exactly one designer.

Family folders are flat and named `<brand>-<series>`: `ikea-brimnes/`,
`ikea-malm/`. A house style is the degenerate case with no brand half: `basic/`.
Flat rather than `ikea/brimnes/` so that `..` unambiguously means "my family";
a brand/series split would make `..` the brand and reopen the question of which
level owns shared code.

### 3.2 The tree

The category level is removed. All 31 existing parts are one house-style family.

```
archplus/tools/partslib/
  shapes.py                      moved from builders/_shapes.py, contents unchanged
  asset.py                       moved from builders/asset.py — the fallback for
                                 parts that ship no builder.py
  library/
    facets.json
    basic/
      _shared.py                 carcass, doors, pulls, table, bed
      base-cabinet/              part.json  builder.py  thumbnail.jpg
      wall-cabinet/  oven-cabinet/  corner-base-cabinet/
      corner-wall-cabinet/  gas-hob/  dining-table/  coffee-table/
      king-bed/  single-bed/  armchair/  basic-chair/  bathtub/
      bookcase/  chest-of-drawers/  curtain/  desk/  floor-lamp/
      media-unit/  mirror/  nightstand/  shower-base/  shower-screen/
      side-table/  sofa/  television/  toilet/  toilet-roll-holder/
      towel-hook/  vanity/  wardrobe/
```

### 3.3 Rules

- A folder containing `part.json` is a **part**.
- A folder not containing `part.json` is a **family**. It holds `_shared.py`
  (or a `_shared/` package once one module is too small) and its member parts.
- A part normally belongs to a family. A part folder may also sit **standalone**
  at the library root, which is reserved for one-off imports that belong to no
  series — a downloaded model with no style affiliation. All 31 parts shipping
  today are the house style and live under `basic/`; nothing is standalone yet.
- A standalone part has no family, so `..` is the library root and
  `from .. import _shared` is unavailable to it. It imports `shapes` only. That
  is the correct constraint: a one-off has no family design language to inherit.
- A part's **id** is its folder path relative to the library root, using `/`
  separators — `basic/mirror` for a family member, `geberit-icon` for a
  standalone part. Ids therefore have one or two segments.
- Browse taxonomy lives in `facets`, never in the filesystem.

`_shared.py` and `_shared/` are invisible to the index, which walks only for
`part.json`, so there is no "family or part?" ambiguity to resolve.

**No folder renames.** `importlib.import_module` takes a string and never parses
identifiers, so `library/basic/coffee-table/builder.py` imports as
`…library.basic.coffee-table.builder`. Verified: hyphens, leading digits, and
reserved words all import; only a `.` in a segment fails, by splitting the
dotted path. `_ID_RE` (`^[a-z0-9][a-z0-9-]*$`) already forbids dots, so validation
is the existing pattern applied to each folder name — that is, to each segment of
a path id, never to the id as a whole, which contains `/`.

No `__init__.py` files are needed under `library/`. Namespace packages cover it,
and relative imports work inside them — verified with both a two-level and a
three-level tree.

### 3.4 shapes.py vs _shared.py

`partslib/shapes.py` is cross-family primitive vocabulary — `rounded_box`,
`square_leg`, `toe_kick`, `fuse_all`. It is imported by every part builder and
every family, so it is public and loses its underscore.

`library/<family>/_shared.py` is one family's design language. A second brand
imports `shapes` and writes its own `_shared.py`.

## 4. Builder resolution

### 4.1 The file on disk decides

A part's geometry comes from its own `builder.py` when it has one, and from the
stock asset builder when it does not:

```python
builder_py = os.path.join(part_dir, "builder.py")
builder = (load_local_builder(part_dir) if os.path.exists(builder_py)
           else asset.single)
```

The manifest says **nothing** about builders. `geometry` carries only `assets`
and `transform`:

```json
{ "geometry": {} }
```
```json
{ "geometry": { "assets": { "body": "chair.step" } } }
```

This deletes the whole symbol mechanism: `resolve_builder`, `_SYMBOL_RE`, the
`geometry.builder` field, its validation at `manifest.py:147`, its entry in
`KNOWN_FIELDS`, and `symbol` from `build_shape`'s cache key — `part_dir` already
identifies the builder. `builders/asset.py` becomes `partslib/asset.py` and is
imported rather than resolved, so the `builders/` package goes too.

An enum (`"builder": "local"` / `"asset"`) was considered and rejected: it would
restate what is already on disk, giving the manifest one more thing that can
drift from reality.

**This strengthens the zero-code property** that §6.3 of the parts-library
design reserved for possible user-supplied libraries. "This part ships no
executable code" stops being a declaration that has to be kept true and becomes
structural — an asset-only part is one with no `builder.py`, and the absence of
the file *is* the guarantee.

Future central helpers need no registry. A part reaches one by ordinary import:

```python
from archplus.tools.partslib import asset

def build(params, assets, ctx):
    return asset.multi(params, assets, ctx)
```

The README's "the two routes are not exclusive" case is unaffected: a part with
both a `builder.py` and assets runs its builder, which calls
`assets.shape(...)`.

### 4.2 Guards

`load_local_builder(part_dir)` derives the module from the path:

```
part_dir  <LIBRARY_DIR>/basic/television
module    archplus.tools.partslib.library.basic.television.builder
callable  build
```

Mirroring what `AssetLoader.shape()` already does for asset paths:

1. `part_dir` must resolve inside `LIBRARY_DIR` — `os.path.commonpath`, with the
   `ValueError` catch for a different drive on Windows.
2. No path segment may contain `.` — the only character that breaks a dotted
   import.
3. `build` must be callable and present in `vars(module)`, so an imported or
   inherited name cannot be used as a builder. Same check as today.

`geometry` itself stays required — it carries `assets` and `transform`.

### 4.3 Missing-builder detection

Because the fallback is implicit, forgetting to write `builder.py` for a
parametric part would silently fall through to `asset.single` and fail with
"part declares no asset 'body'" — a confusing error for a missing-file problem.
The scan-time check in §6 closes it: a part must have either a `builder.py` or a
non-empty `geometry.assets`, else it is a scan error.

### 4.4 Family code

A part builder reaches its family as `from .. import _shared`, which means "my
family" at any depth. Moving a part and its `_shared.py` into a deeper folder
therefore requires no edit to any `builder.py` — verified.

## 5. Ids

```python
part_id = data.get("id") or os.path.relpath(
    os.path.dirname(path), library_dir).replace(os.sep, "/")
```

An explicit `id` still wins when present, which is how identity is pinned across
a folder move. All 31 manifests drop the field.

Path ids are unique by construction, because the filesystem enforces it. This
matters as soon as a second family exists: every brand sells a mirror, and IKEA
sells a chest of drawers in several series, so leaf-name ids would collide.
Today `index.py:58-63` treats a duplicate as a scan error and **excludes** the
second part, which would fail
`test_scan_reports_zero_errors_for_the_shipped_library`. Path ids make the
collision unrepresentable.

A `/` in an id is safe: no code turns an id into a filesystem path. Ids are only
compared, stored in a `PropertyString`, and printed — verified across `gui.py`,
`thumbs.py`, `object.py`, and `index.py`.

The duplicate-id check stays as a cheap invariant assertion, now unreachable in
practice. That is the same standing as the existing facet safety-net test, which
documents its own redundancy.

### 5.1 Accepted one-time break

Every id changes: `mirror` becomes `basic/mirror`. A document saved before this
change holds `PartId = "mirror"`, which no longer resolves. No compatibility
shim is added; the existing degradation path is adequate and already reports
itself:

- `execute()` prints `part 'mirror' is not in the library; keeping the cached
  shape for <label>` and deliberately does not touch `obj.Shape`, so the
  geometry survives.
- `setPartProperties()` hides the Parameters group, so parametric editing stops.
- "Reload from library" prints `part 'mirror' is not in the library`.

The library shipped 2026-08-15, two days before this spec, so the exposure is
limited to the author's own files. Documented in the README as a known break
rather than carried as permanent compatibility code.

## 6. Two additions

**Scan-time builder check.** `index.py` verifies that every part has either a
`builder.py` on disk or a non-empty `geometry.assets`. Pure `os.path`, so
`index.py` stays free of FreeCAD imports, and it turns a missing builder from a
misleading insert-time "declares no asset 'body'" into a scan error already
guarded by `test_scan_reports_zero_errors_for_the_shipped_library`.

**Builder reload on rescan.** `clear_shape_cache()` exists because editing a
builder does not invalidate the shape cache. Once builders are colocated,
authoring a part means editing that part's `builder.py`, and its `sys.modules`
entry becomes a second stale cache. `clear_shape_cache()` also drops
`…partslib.library.*` from `sys.modules`, so "Rescan library" genuinely re-reads
an edited builder. This is a new capability that only makes sense once builders
are per-part, not a regression fix.

## 7. Testing

The legacy-id work is gone, so no logic moves out of `object.py` for
testability.

| File | Changes |
|---|---|
| `test_partslib_geometry.py` | The 8 `resolve_builder` tests are **deleted** with the symbol mechanism, including `test_demo_builder_resolves`. New `load_local_builder` tests: resolves from a part dir; rejects a dir outside `LIBRARY_DIR`; rejects a dot in a segment; rejects a missing `build`; rejects a `build` that is imported rather than defined. New: a part folder with no `builder.py` falls back to `asset.single`. Cache tests at 129-183 monkeypatch `resolve_builder` — retarget to the new branch point, and `_manifest()`'s `builder="demo.box"` default goes away with the field. |
| `test_partslib_thumbs.py` | Three fixtures at 99, 121, 140 pass `{"builder": "demo.box"}`, which is never resolved in any of them — drop the field. |
| `test_partslib_index.py` | id derived from path; explicit `id` overrides; the builder-or-assets scan check |
| `test_partslib_manifest.py` | `geometry.builder` is no longer a known field; `geometry` still required |
| `test_library_content.py` | `test_every_entry_geometry_builder_resolves` becomes "every part resolves to a builder, local or fallback"; all 31 ids unique and path-shaped |

**Known limit.** `conftest.py` fakes `Part` with only `LineSegment` and
`Circle`, so headless tests can import a builder and check it is callable but
cannot execute it. No automated test proves the geometry is unchanged by this
refactor. That verification is the manual FreeCAD pass in
`docs/PARTS-LIBRARY-VERIFICATION.md`, whose stale
`library/furniture/base-cabinet/` path is corrected as part of this work.

Because geometry cannot be verified headlessly, the 31 `builder.py` files are
generated by a throwaway extraction script that copies each function body
verbatim, reviewed as a diff, and the script then deleted. This makes the move
provably mechanical rather than 1835 hand-transcribed lines.

## 8. Migration order

Each step lands with the suite green.

1. `builders/_shapes.py` → `partslib/shapes.py`; update the 4 importers.
2. `git mv` all 31 part folders into `library/basic/`. No code change — ids are
   still explicit.
3. Derive ids from the path, with explicit `id` overriding. Behaviour unchanged,
   because every manifest still carries its id.
4. Add `load_local_builder` and make resolution **local-first**: a part's own
   `builder.py` wins, the `geometry.builder` symbol is the fallback, and
   `asset.single` is the last resort. No part has a `builder.py` yet, so every
   part still resolves exactly as before.
5. Per part, 31 times: create `builder.py` and delete the function from its
   family module. Local-first resolution means each part switches over the
   moment its file lands, and a part not yet migrated keeps using the symbol
   route — so the library is never broken mid-migration.
6. Move the five shared functions into `library/basic/_shared.py`; delete
   `furniture.py`, `kitchen.py`, `sanitary.py`, `fittings.py`.
7. Now that all 31 parts have a `builder.py`, delete the symbol fallback:
   `resolve_builder`, `_SYMBOL_RE`, `geometry.builder` in all 31 manifests, and
   their tests. `builders/asset.py` → `partslib/asset.py`, imported rather than
   resolved; delete `demo.py` and the `builders/` package.
8. Drop the now-redundant explicit `id` from all 31 manifests.
9. Builder-or-assets scan check; `sys.modules` invalidation in
   `clear_shape_cache()`.
10. Docs: README §2b rewritten, the add-a-part walkthrough, the
    `PARTS-LIBRARY-VERIFICATION.md` paths, and the known id break.

Steps 4-6 keep the symbol route alive as a fallback while 1835 lines move, so a
broken extraction shows up as one failing part rather than a dead library. Step 7
removes the fallback once every part has its own `builder.py`.

## 9. Accepted costs

- All 31 ids change; pre-existing documents keep their geometry but lose
  parametric editing (§5.1).
- Four builders — `dining-table`, `coffee-table`, `king-bed`, `single-bed` —
  start as two-line delegations to `_shared`, because those pairs genuinely are
  one function driven by different manifest params today. That file is where the
  first real divergence goes.
- A single flat family holds 31 parts. Real brand series absorb parts into their
  own families as they land, and moving a part between families is a `git mv`
  plus an id change.
- No automated proof that geometry is unchanged (§7).

`demo.py` is deleted rather than kept. Its header justifies it as "the worked
example of the builder contract" because "the library ships empty" — both stale:
the library has 31 parts, and after this change every one of them is a worked
example sitting beside its manifest. The five test sites naming `demo.box` never
resolve it; each monkeypatches `FreeCAD`, `build_shape`, or `resolve_builder`
first, so the string is an arbitrary placeholder. The only test that resolves it
exists to assert that it exists.
