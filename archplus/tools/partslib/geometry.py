# SPDX-License-Identifier: LGPL-2.1-or-later
#
# PartsLib geometry - resolves builders, loads shape assets and caches them.
#
# Every source format becomes a bare Part.Shape, never a DocumentObject. That
# is what keeps insertion to a single object in the tree: File > Insert copies
# every sketch and body into the document root and FreeCAD's delete does not
# cascade, so removing the top object would orphan the rest.

import importlib
import os
import re

from . import manifest as partslib_manifest

BUILDER_PACKAGE = "archplus.tools.partslib.builders"
CACHE_DIRNAME = ".cache"

_DIR = os.path.dirname(os.path.abspath(__file__))
LIBRARY_DIR = os.path.join(_DIR, "library")
LIBRARY_PACKAGE = "archplus.tools.partslib.library"
BUILDER_MODULE = "builder"
BUILDER_FILENAME = BUILDER_MODULE + ".py"

_SYMBOL_RE = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")


def resolve_builder(symbol):
    """Turn a "module.function" symbol into a callable.

    Only names inside the archplus.tools.partslib.builders package resolve. Anything
    path-like, dotted deeper than one level, or absent raises ValueError."""
    if not isinstance(symbol, str) or not _SYMBOL_RE.match(symbol):
        raise ValueError("invalid builder symbol %r" % (symbol,))

    module_name, function_name = symbol.split(".")
    try:
        module = importlib.import_module(
            "%s.%s" % (BUILDER_PACKAGE, module_name))
    except ImportError as exc:
        raise ValueError("unknown builder module %r: %s" % (module_name, exc))

    builder = getattr(module, function_name, None)
    if (function_name.startswith("_")
            or function_name not in vars(module)
            or not callable(builder)):
        raise ValueError("builder %r has no callable %r"
                         % (module_name, function_name))
    return builder


def has_local_builder(part_dir):
    """True when this part folder carries its own builder.py."""
    return os.path.exists(os.path.join(part_dir, BUILDER_FILENAME))


def load_local_builder(part_dir):
    """Import a part folder's own builder.py and return its build().

    The manifest names NOTHING on this route - the module path is derived
    from where the part lives - so a manifest cannot point at code outside
    its own folder. The library tree is the import tree: no __init__.py is
    needed anywhere under it, because a directory without one is a namespace
    package, and `from .. import _shared` still resolves inside those."""
    base = os.path.abspath(LIBRARY_DIR)
    target = os.path.abspath(part_dir)

    # Containment, checked the same way AssetLoader.shape() checks asset
    # paths - including the ValueError, which commonpath raises for two
    # paths on different Windows drives.
    try:
        contained = os.path.commonpath([base, target]) == base
    except ValueError:
        contained = False
    if not contained or target == base:
        raise ValueError("part directory %r is not inside the library"
                         % (part_dir,))

    segments = os.path.relpath(target, base).replace("\\", "/").split("/")
    for segment in segments:
        if "." in segment:
            raise ValueError(
                "part folder %r cannot contain '.': it would split the "
                "import path" % (segment,))

    module_name = "%s.%s.%s" % (
        LIBRARY_PACKAGE, ".".join(segments), BUILDER_MODULE)
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ValueError("cannot import %s: %s" % (module_name, exc))

    builder = getattr(module, "build", None)
    # `build.__module__ == module_name` and not just `"build" in vars(module)`:
    # a star-import or an explicit `from x import y as build` also lands
    # `build` in vars(module), so only checking membership there would let a
    # name imported from elsewhere pass as this part's builder. Checking
    # __module__ confirms `build` was actually DEFINED in this file.
    if (getattr(builder, "__module__", None) != module_name
            or not callable(builder)):
        raise ValueError("%s has no callable build()" % (module_name,))
    return builder


def select_builder(resolved, part_dir):
    """The callable that builds this part.

    Local-first: a part's own builder.py wins. The manifest's `builder`
    symbol is a transitional fallback while builders move into part folders
    (see the plan's Tasks 5-8); once every part has a builder.py it is
    removed and the last resort is the stock asset builder, which is what an
    asset-only part - one shipping no code at all - uses."""
    if has_local_builder(part_dir):
        return load_local_builder(part_dir)
    symbol = (resolved.get("geometry") or {}).get("builder")
    if symbol:
        return resolve_builder(symbol)
    return resolve_builder("asset.single")


class AssetLoader:
    """Lazily loads a part's shape assets, caching parsed results as BREP.

    STEP translation is slow; BREP is the format FreeCAD itself stores shapes
    in (ArchReference reads .brp blobs straight out of FCStd archives), so the
    first load of a STEP writes a .brep beside it under .cache/."""

    def __init__(self, part_dir, assets_map):
        self._dir = part_dir
        self._assets = assets_map or {}
        self._shapes = {}

    def shape(self, name):
        """Return the named asset as a Part.Shape."""
        if name in self._shapes:
            return self._shapes[name]

        filename = self._assets.get(name)
        if not filename:
            raise ValueError("part declares no asset %r" % (name,))

        # Separator choice must never decide the outcome: a manifest authored
        # on one OS can name a traversal using the other OS's separator, and
        # this loader still has to reject it, so check both explicitly before
        # trusting os.path (whose own separator handling is native-OS-only).
        segments = filename.replace("\\", "/").split("/")

        base = os.path.abspath(self._dir)
        source = os.path.abspath(os.path.join(base, filename))
        try:
            contained = os.path.commonpath([base, source]) == base
        except ValueError:
            contained = False  # different drive on Windows: cannot be inside
        if os.path.isabs(filename) or ".." in segments or not contained:
            raise ValueError("asset %r must be a name inside the part folder"
                             % (filename,))

        if not os.path.exists(source):
            raise ValueError("missing asset file %s" % source)

        shape = self._read(source)
        self._shapes[name] = shape
        return shape

    def _read(self, source):
        import Part

        if source.lower().endswith(".brep"):
            return Part.Shape(Part.read(source))

        cache_dir = os.path.join(self._dir, CACHE_DIRNAME)
        cached = os.path.join(
            cache_dir, os.path.splitext(os.path.basename(source))[0] + ".brep")
        if (os.path.exists(cached)
                and os.path.getmtime(cached) >= os.path.getmtime(source)):
            return Part.Shape(Part.read(cached))

        shape = Part.read(source)
        try:
            if not os.path.isdir(cache_dir):
                os.makedirs(cache_dir)
            shape.exportBrep(cached)
        except Exception:
            pass  # a cache miss is never fatal
        return shape


def measure(shape):
    """Derived measurements, in mm, from the built shape's bounding box.

    Measurements are never authored in a manifest - deriving them is what
    stops a part's stated size disagreeing with its geometry. The metric
    names come from partslib_manifest.derived_metric_names() so there is one
    definition of what "derived" means, mapped in order onto the bounding
    box's X/Y/Z extents."""
    box = shape.BoundBox
    lengths = (box.XLength, box.YLength, box.ZLength)
    return dict(zip(partslib_manifest.derived_metric_names(), lengths))


# Session cache of built shapes, keyed by everything that determines the
# geometry. See build_shape() for why this exists and clear_shape_cache()
# for when it is dropped.
_SHAPE_CACHE = {}
_SHAPE_CACHE_ORDER = []
_SHAPE_CACHE_LIMIT = 96


def clear_shape_cache():
    """Forget every remembered shape.

    Called whenever the library is rescanned. A part's params are part of
    the cache key, so editing a manifest already misses the cache - but
    editing a BUILDER, or an asset file on disk, would not, and a rescan is
    the user saying "re-read the library" in as many words."""
    _SHAPE_CACHE.clear()
    del _SHAPE_CACHE_ORDER[:]


def _remember_shape(key, shape):
    if key in _SHAPE_CACHE:
        return
    _SHAPE_CACHE[key] = shape
    _SHAPE_CACHE_ORDER.append(key)
    while len(_SHAPE_CACHE_ORDER) > _SHAPE_CACHE_LIMIT:
        _SHAPE_CACHE.pop(_SHAPE_CACHE_ORDER.pop(0), None)


def build_shape(resolved, part_dir, overrides=None):
    """Build one resolved variant's shape, reusing an identical earlier build.

    `overrides` is an optional {paramName: value} map - typically an
    inserted object's current Parameter property values - merged over the
    manifest's declared defaults by partslib_manifest.merge_params(), which
    also drops anything the manifest does not declare.

    THE CACHE. Building is not cheap: a drawer chest is roughly 27 sequential
    OCC booleans and measured over a second. It is also called far more often
    than "once per part" suggests - selecting a part in the browser rebuilds
    it, because the W x D x H readout is measured from the shape rather than
    authored, so the rendered-image caches on disk cannot spare the rebuild.
    Clicking between two parts therefore paid full price every time.

    The key is everything that decides the geometry: which part directory,
    which builder (module AND function - two builders sharing a module,
    e.g. two kitchen.* functions, must not collide), which variant, and the
    fully merged params. Anything a user can change from the UI changes the
    key, so a stale hit is not reachable by editing a Parameter or switching
    a variant.

    Callers get a COPY. A shape handed to a document object becomes that
    object's, and a caller free to mutate what it was given would otherwise
    corrupt the entry for everyone after it. Copying a finished solid is
    still far cheaper than rebuilding one."""
    geometry = resolved.get("geometry") or {}
    builder = select_builder(resolved, part_dir)
    params = partslib_manifest.merge_params(resolved, overrides)

    key = (os.path.abspath(part_dir),
           getattr(builder, "__module__", "") + "."
           + getattr(builder, "__qualname__", ""),
           resolved.get("variantLabel"),
           repr(sorted(params.items(), key=lambda item: item[0])),
           repr(sorted((geometry.get("assets") or {}).items())))

    cached = _SHAPE_CACHE.get(key)
    if cached is not None:
        try:
            return cached.copy()
        except Exception:
            # A cached shape that can no longer be copied is worse than no
            # cache at all - drop it and rebuild.
            _SHAPE_CACHE.pop(key, None)

    assets = AssetLoader(part_dir, geometry.get("assets"))
    shape = builder(params, assets, _Context(geometry))
    _remember_shape(key, shape)
    try:
        return shape.copy()
    except Exception:
        return shape


class _Context:
    """Normalisation helpers handed to every builder as `ctx`."""

    def __init__(self, geometry):
        self.transform = geometry.get("transform") or {}

    def normalize(self, shape, params=None):
        """Apply the manifest's transform: unit scale, rotation, anchor.

        A part's origin is normalised ONCE here, at build time, which is why
        placement never has to know about a vendor asset's arbitrary origin."""
        import FreeCAD

        shape = shape.copy()
        scale = float(self.transform.get("unitScale", 1.0))
        if scale != 1.0:
            matrix = FreeCAD.Matrix()
            matrix.scale(scale, scale, scale)
            shape = shape.transformGeometry(matrix)

        rotate = self.transform.get("rotate")
        if rotate:
            placement = FreeCAD.Placement()
            placement.Rotation = FreeCAD.Rotation(
                float(rotate[0]), float(rotate[1]), float(rotate[2]))
            shape.Placement = placement.multiply(shape.Placement)

        anchor = self.transform.get("anchor")
        if anchor:
            shape.translate(_anchor_offset(shape, anchor))
        return shape


# Anchor names map to a fraction of the bounding box along each axis:
# 0.0 = minimum face, 0.5 = centre, 1.0 = maximum face.
_ANCHOR_FRACTIONS = {
    "center": (0.5, 0.5, 0.5),
    "bottom-center": (0.5, 0.5, 0.0),
    "top-center": (0.5, 0.5, 1.0),
    "back-bottom-center": (0.5, 1.0, 0.0),
    "front-bottom-center": (0.5, 0.0, 0.0),
    "back-center": (0.5, 1.0, 0.5),
    "front-center": (0.5, 0.0, 0.5),
    "origin": None,
}


def _anchor_offset(shape, anchor):
    """Translation that moves `anchor` on the shape to the global origin."""
    import FreeCAD

    if anchor not in _ANCHOR_FRACTIONS:
        raise ValueError("unknown anchor %r" % (anchor,))
    fractions = _ANCHOR_FRACTIONS[anchor]
    if fractions is None:
        return FreeCAD.Vector(0, 0, 0)

    box = shape.BoundBox
    fx, fy, fz = fractions
    return FreeCAD.Vector(
        -(box.XMin + box.XLength * fx),
        -(box.YMin + box.YLength * fy),
        -(box.ZMin + box.ZLength * fz))
