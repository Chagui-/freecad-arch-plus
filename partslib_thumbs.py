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
#
# SESSION-LEVEL FAILURE CACHE: on a machine where SoOffscreenRenderer cannot
# get a GL context, render_shape() returns False on every single call - not
# an exception, so there is nothing here for a caller to catch and remember
# on its own. Without _RENDER_FAILED below, every part lacking a committed
# thumbnail would rebuild its real geometry (booleans, fillets) and retry a
# doomed render on every grid repaint: every keystroke in the search box,
# every breadcrumb click, every panel reopen - unbounded, and with no
# warning printed anywhere to explain why. _RENDER_FAILED remembers a path
# that has already failed once, so both callers (the grid's committed-vs-
# on-demand thumbnail, and the detail pane's per-variant preview) skip
# straight to "no thumbnail" without touching the geometry kernel again,
# for the rest of this FreeCAD session.

import os

THUMBNAIL_FILENAME = "thumbnail.png"
THUMBNAIL_SIZE = 256
_BACKGROUND = (1.0, 1.0, 1.0)

_RENDER_FAILED = set()


def render_failed_before(out_path):
    """True if rendering to `out_path` has already failed this session."""
    return out_path in _RENDER_FAILED


def mark_render_failed(out_path, message=None):
    """Remember that `out_path` cannot be rendered, and say so once."""
    _RENDER_FAILED.add(out_path)
    _warn(message or (
        "ArchPlus: cannot render %s; will not retry this session\n"
        % (out_path,)))


def reset_render_failures():
    """Forget every remembered failure - a test/debug hook only. Nothing in
    this module calls it: the whole point of the cache is that a failure
    stays remembered for the rest of the session."""
    _RENDER_FAILED.clear()


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
    """Path to the part's thumbnail, rendering one if it is missing.

    Checks the session failure cache BEFORE building anything: the build
    step (real Part booleans/fillets) is exactly the expensive half of this,
    so a part already known to fail must skip it entirely, not just skip
    the render call."""
    import partslib_geometry

    path = thumbnail_path(entry["dir"])
    if os.path.exists(path):
        return path
    if render_failed_before(path):
        return None
    try:
        shape = partslib_geometry.build_shape(resolved, entry["dir"])
    except Exception as exc:
        mark_render_failed(path, (
            "ArchPlus: cannot build %r for a thumbnail; will not retry "
            "this session: %s\n" % (entry["id"], exc)))
        return None
    if render_shape(shape, path):
        return path
    mark_render_failed(path, (
        "ArchPlus: cannot render a thumbnail for %r (no GL context?); "
        "will not retry this session\n" % (entry["id"],)))
    return None
