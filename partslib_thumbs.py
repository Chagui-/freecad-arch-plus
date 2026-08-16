# SPDX-License-Identifier: LGPL-2.1-or-later
#
# PartsLib thumbnails - offscreen PNG rendering from a bare Part.Shape.
#
# Thumbnails are committed to the repo so a fresh clone opens to a populated
# grid. Runtime rendering is a fallback for a part whose thumbnail is missing,
# and it is never fatal: SoOffscreenRenderer needs a GL context and fails on
# some drivers, so every failure path returns False instead of raising.
#
# The technique follows FreeCAD's own OfflineRenderingUtils.render().

import os

THUMBNAIL_FILENAME = "thumbnail.png"
THUMBNAIL_SIZE = 256
_BACKGROUND = (1.0, 1.0, 1.0)

# Tessellation for writeInventor: (deviation, angular deviation). Coarse
# enough to render fast, fine enough for a 256px thumbnail.
_TESSELLATION = (2, 0.01)


def thumbnail_path(part_dir):
    """Where a part's committed thumbnail lives."""
    return os.path.join(part_dir, THUMBNAIL_FILENAME)


def _warn(message):
    """Best-effort console warning. A missing FreeCAD must not turn a
    warning into a crash - the failure paths that call this must stay as
    silent-but-harmless as the rendering failure they are reporting."""
    try:
        import FreeCAD
        FreeCAD.Console.PrintWarning(message)
    except Exception:
        pass


def scene_from_shape(shape):
    """Build a Coin scene graph from a bare Part.Shape - no document needed."""
    from pivy import coin

    buf = shape.writeInventor(*_TESSELLATION)
    reader = coin.SoInput()
    reader.setBuffer(buf)
    return coin.SoDB.readAll(reader)


def render_shape(shape, out_path, size=THUMBNAIL_SIZE):
    """Render `shape` to a PNG. Returns True on success, False otherwise."""
    try:
        from pivy import coin

        node = scene_from_shape(shape)
        root = coin.SoSeparator()
        root.addChild(coin.SoDirectionalLight())
        camera = coin.SoPerspectiveCamera()
        root.addChild(camera)
        root.addChild(node)

        region = coin.SbViewportRegion(size, size)
        camera.viewAll(root, region)

        renderer = coin.SoOffscreenRenderer(region)
        renderer.setBackgroundColor(coin.SbColor(*_BACKGROUND))

        root.ref()
        try:
            ok = renderer.render(root)
        finally:
            root.unref()

        if not ok:
            return False

        folder = os.path.dirname(out_path)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        renderer.writeToFile(out_path, "PNG")
        return os.path.exists(out_path)
    except Exception as exc:
        _warn("ArchPlus: thumbnail render failed: %s\n" % (exc,))
        return False


def ensure_thumbnail(entry, resolved):
    """Path to the part's thumbnail, rendering one if it is missing."""
    import partslib_geometry

    path = thumbnail_path(entry["dir"])
    if os.path.exists(path):
        return path
    try:
        shape = partslib_geometry.build_shape(resolved, entry["dir"])
    except Exception as exc:
        _warn("ArchPlus: cannot build %s for a thumbnail: %s\n"
              % (entry["id"], exc))
        return None
    return path if render_shape(shape, path) else None
