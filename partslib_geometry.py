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
import sys

_DIR = os.path.dirname(__file__)
if _DIR not in sys.path:
    sys.path.append(_DIR)

BUILDER_PACKAGE = "partslib_builders"
CACHE_DIRNAME = ".cache"

_SYMBOL_RE = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")


def resolve_builder(symbol):
    """Turn a "module.function" symbol into a callable.

    Only names inside the partslib_builders package resolve. Anything
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
    if not callable(builder):
        raise ValueError("builder %r has no callable %r"
                         % (module_name, function_name))
    return builder


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
        if os.path.isabs(filename) or ".." in filename.split(os.sep):
            raise ValueError("asset %r must be a name inside the part folder"
                             % (filename,))

        source = os.path.join(self._dir, filename)
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
    stops a part's stated size disagreeing with its geometry."""
    box = shape.BoundBox
    return {"Width": box.XLength, "Depth": box.YLength, "Height": box.ZLength}


def build_shape(resolved, part_dir):
    """Build one resolved variant's shape."""
    geometry = resolved.get("geometry") or {}
    builder = resolve_builder(geometry.get("builder"))
    assets = AssetLoader(part_dir, geometry.get("assets"))
    params = {name: spec.get("default")
              for name, spec in (resolved.get("params") or {}).items()}
    return builder(params, assets, _Context(geometry))


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
