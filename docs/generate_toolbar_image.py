# SPDX-License-Identifier: LGPL-2.1-or-later
"""
Regenerate docs/images/toolbar.png - the README's toolbar screenshot.

Run INSIDE a GUI FreeCAD session, e.g. from the FreeCAD Python console:

    exec(open(r"C:\\Users\\apeci\\AppData\\Roaming\\FreeCAD\\v1-1\\Mod\\ArchPlus\\docs\\generate_toolbar_image.py").read())

Two modes:

- Live: if the running BIM workbench has the ArchPlus toolbar with a
  populated dropdown (the Walls flyout), the real, live-themed toolbar
  widget is grabbed.
- Repo replica: otherwise the toolbar is rebuilt offscreen from
  REPO_SPEC below (the commands registered by InitGui.py and their
  GetResources definitions), so a session that predates the latest
  tools still produces an up-to-date image.

In both modes the Walls dropdown menu is rendered offscreen (a plain
grab() of a never-shown popup can return empty pixels; in that case the
replica is popped up with WA_DontShowOnScreen, which forces the real
layout/paint path without the menu appearing on screen), and the strip
+ menu composite is written to docs/images/toolbar.png with a
transparent background.

Menu anchoring is PIXEL-based: Qt's mapTo() geometry is unreliable on a
never-resized toolbar (stale layout), so the Walls icon is located by
scanning the grabbed strip's pixels for content clusters. The saved
file is re-decoded and the placement asserted before the script reports
success.

Re-run whenever the toolbar's set of tools changes (keep REPO_SPEC in
sync with InitGui.py).
"""

import os
import struct
import zlib

import FreeCAD
import FreeCADGui as Gui
from PySide import QtGui, QtCore, QtWidgets

HERE = os.path.join(FreeCAD.getUserAppDataDir(), "Mod", "ArchPlus")
OUT = os.path.join(HERE, "docs", "images", "toolbar.png")
TOOLS = os.path.join(HERE, "archplus", "tools")

# The toolbar as InitGui.py assembles it, with each command's
# GetResources definition. The last entry is a grouped command (the BIM
# flyout pattern): button icon plus the dropdown behind its arrow.
REPO_SPEC = [
    ("Stairs",
     os.path.join(TOOLS, "stairs", "resources", "icons", "StairsPlus.svg")),
    ("Door",
     os.path.join(TOOLS, "doors", "resources", "icons", "DoorsPlus.svg")),
    ("Window",
     os.path.join(TOOLS, "windows", "resources", "icons", "WindowsPlus.svg")),
    ("Parts Library",
     os.path.join(TOOLS, "partslib", "resources", "icons",
                  "PartsLibrary.svg")),
    ("Walk Through",
     os.path.join(TOOLS, "walk", "resources", "icons", "WalkThrough.svg")),
    ("Walls",
     os.path.join(TOOLS, "walls", "resources", "icons", "WallPlus.svg"),
     [("Wall",
       os.path.join(TOOLS, "walls", "resources", "icons", "WallPlus.svg")),
      ("Split / move segment\u2026",
       os.path.join(TOOLS, "walls", "resources", "icons",
                    "WallSplit.svg"))]),
]

MENU_GAP = 2               # logical px between strip and menu
MENU_BLEED = 2             # device px menu panel sits left of the icon
EDGE_PAD = 4               # device px kept around the strip content


def _rgb(pixel_int):
    """QImage.pixel() -> (r, g, b) in the image's format (ARGB32)."""
    return (pixel_int & 255, (pixel_int >> 8) & 255,
            (pixel_int >> 16) & 255)


def _icon(path):
    if not os.path.isfile(path):
        raise RuntimeError("icon missing: %s" % path)
    return QtGui.QIcon(path)


def _rasterized(icon, size):
    """An icon backed by a pre-rendered pixmap.

    Offscreen menus skip painting SVG-engine icons; a pixmap-backed
    QIcon always blits.
    """
    pm = icon.pixmap(size)
    return QtGui.QIcon(pm)


def _archToolbar():
    mw = Gui.getMainWindow()
    bars = [b for b in mw.findChildren(QtGui.QToolBar)
            if b.objectName() == "ArchPlus" or b.windowTitle() == "ArchPlus"]
    if not bars:
        raise RuntimeError(
            "ArchPlus toolbar not found - activate the BIM workbench first")
    return bars[0]


def _replicaMenu(entries, parent):
    """A QMenu with `entries` (text, icon path), force-enabled."""
    menu = QtGui.QMenu(parent)
    for text, path in entries:
        act = QtGui.QAction(_icon(path), text, menu)
        act.setEnabled(True)
        menu.addAction(act)
    menu.ensurePolished()
    # Offscreen menus skip painting SVG-engine icons; rasterize each
    # action's icon into a pixmap-backed QIcon so it always blits, at
    # the toolbar's icon size (menus inherit it in FreeCAD's style).
    size = QtCore.QSize(24, 24)
    menu.adjustSize()
    return menu


def _grabMenu(menu):
    """Grab a prepared QMenu, forcing the paint path if needed.

    A plain grab() of a never-shown popup can return empty pixels; in
    that case the menu is popped up with WA_DontShowOnScreen, which
    forces the real layout/paint path without it appearing on screen.
    """
    menu.ensurePolished()
    img = menu.grab().toImage()
    img.setDevicePixelRatio(1.0)
    if img.width() <= 0 or img.height() <= 0 or not _hasPixels(img):
        menu.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
        menu.popup(QtCore.QPoint(0, 0))
        QtWidgets.QApplication.processEvents()
        img = menu.grab().toImage()
        img.setDevicePixelRatio(1.0)
        menu.close()
    if img.width() <= 0 or img.height() <= 0 or not _hasPixels(img):
        raise RuntimeError("menu render produced an empty image")
    return img


def _buildReplicaToolbar(spec):
    """Build the ArchPlus toolbar offscreen from REPO_SPEC."""
    bar = QtGui.QToolBar("ArchPlus")
    bar.setObjectName("ArchPlus")
    bar.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
    bar.setIconSize(QtCore.QSize(24, 24))
    for entry in spec:
        text, icon_path = entry[0], entry[1]
        act = QtGui.QAction(_icon(icon_path), text, bar)
        btn = QtGui.QToolButton(bar)
        btn.setDefaultAction(act)
        if len(entry) > 2:                      # grouped command flyout
            btn.setMenu(_replicaMenu(entry[2], bar))
            btn.setPopupMode(QtGui.QToolButton.MenuButtonPopup)
        btn.toolButtonStyle = QtCore.Qt.ToolButtonTextUnderIcon
        bar.addWidget(btn)
    mw = Gui.getMainWindow()
    bar.setParent(mw)
    bar.resize(max(560, bar.sizeHint().width()), bar.sizeHint().height())
    bar.show()
    QtWidgets.QApplication.processEvents()
    for b in bar.findChildren(QtGui.QToolButton):
        b.raise_()
    bar.repaint()
    QtWidgets.QApplication.processEvents()
    return bar


def _hasPixels(img):
    """True if the image has any non-transparent pixels (sparse scan)."""
    return any(((img.pixel(xx, yy) >> 24) & 255) > 0
               for yy in range(0, img.height(), 4)
               for xx in range(0, img.width(), 4))


def _contentClusters(img, y0, y1, bg, thresh=60, min_gap=8):
    """Column ranges whose pixels differ from `bg` (icon clusters)."""
    w = img.width()
    hits = []
    for x in range(w):
        hit = False
        for y in range(y0, y1, 2):
            c = img.pixel(x, y)
            if ((c >> 24) & 255) > 200:      # opaque
                r, g, b = _rgb(c)
                if abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2]) > thresh:
                    hit = True
                    break
        hits.append(hit)
    out, start = [], None
    for x, hit in enumerate(hits + [False]):
        if hit and start is None:
            start = x
        elif not hit and start is not None:
            out.append([start, x - 1])
            start = None
    merged = []
    for c in out:
        if merged and c[0] - merged[-1][1] < min_gap:
            merged[-1][1] = c[1]
        else:
            merged.append(c)
    return merged


def _decodePng(path):
    """Minimal PNG decoder -> (w, h, bytearray RGBA)."""
    d = open(path, "rb").read()
    pos, idat, w, h = 8, b"", 0, 0
    while pos < len(d):
        ln, typ = struct.unpack(">I4s", d[pos:pos + 8])
        if typ == b"IHDR":
            w, h = struct.unpack(">II", d[pos + 8:pos + 16])
        elif typ == b"IDAT":
            idat += d[pos + 8:pos + 8 + ln]
        pos += 12 + ln
    raw = zlib.decompress(idat)
    stride = w * 4
    px = bytearray(w * h * 4)
    prev = bytearray(stride)
    i = 0
    for y in range(h):
        f = raw[i]
        i += 1
        line = bytearray(raw[i:i + stride])
        i += stride
        if f == 1:
            for x in range(4, stride):
                line[x] = (line[x] + line[x - 4]) & 255
        elif f == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                a = line[x - 4] if x >= 4 else 0
                line[x] = (line[x] + ((a + prev[x]) >> 1)) & 255
        elif f == 4:
            for x in range(stride):
                a = line[x - 4] if x >= 4 else 0
                b = prev[x]
                c = prev[x - 4] if x >= 4 else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] +
                           (a if (pa <= pb and pa <= pc)
                            else (b if pb <= pc else c))) & 255
        px[y * stride:(y + 1) * stride] = line
        prev = line
    return w, h, px


def main():
    # --- Acquire the toolbar and its Walls menu. ---
    try:
        bar = _archToolbar()
        buttons = bar.findChildren(QtGui.QToolButton)
        menu_btns = [b for b in buttons
                     if b.menu() is not None and b.menu().actions()]
        walls_btn = menu_btns[0] if menu_btns else None
        if walls_btn is None:
            raise RuntimeError("live toolbar has no populated flyout")
        for b in buttons:
            b.raise_()
        bar.repaint()
        QtWidgets.QApplication.processEvents()
        menu = walls_btn.menu()
        mode = "live"
    except RuntimeError:
        bar = _buildReplicaToolbar(REPO_SPEC)
        walls_btn = next(b for b in bar.findChildren(QtGui.QToolButton)
                         if b.menu() is not None)
        menu = walls_btn.menu()
        mode = "repo"

    bar.repaint()
    full = bar.grab().toImage()
    dpr = full.devicePixelRatio() or 1.0
    W, H = full.width(), full.height()

    # Toolbar row background, sampled from the far-right empty stretch.
    bg = _rgb(full.pixel(W - 8, H // 2))

    # Locate the icons by pixels - mapTo() geometry is stale on a
    # never-resized toolbar. The last cluster is the Walls button's
    # area: a narrow one is just the split dropdown arrow (the icon is
    # the cluster before it), a wide one is the merged icon+arrow.
    clusters = _contentClusters(full, 4, H - 4, bg)
    if len(clusters) < 2:
        raise RuntimeError("toolbar grab shows no icon clusters")
    last = clusters[-1]
    if last[1] - last[0] <= round(14 * dpr):
        if len(clusters) < 3:
            raise RuntimeError("toolbar grab shows no Walls icon cluster")
        walls, arrow = clusters[-2], last
    else:
        walls, arrow = last, last
    walls_btn_left = walls[0]

    # Crop to the content: skip leading drag-handle dot clusters
    # (narrow, in the left margin before the first icon), small bleed.
    first_icon = clusters[0]
    for cl in clusters:
        if cl[1] - cl[0] > round(8 * dpr) or cl is clusters[-1]:
            first_icon = cl
            break
    crop_x = max(0, first_icon[0] - EDGE_PAD)
    crop_w = min(W - crop_x, arrow[1] + EDGE_PAD - crop_x)
    strip = full.copy(crop_x, 0, crop_w, H)
    # The grab carries the window's devicePixelRatio; composite in raw
    # device pixels so drawImage maps it 1:1 onto the canvas instead of
    # downscaling it to logical size.
    strip.setDevicePixelRatio(1.0)

    # The grab's backing store can be taller than the painted toolbar
    # (fractional DPR), so anchor to the strip's last visibly painted
    # row, not its nominal height.
    strip_bottom = 0
    for yy in range(strip.height()):
        if any(((strip.pixel(xx, yy) >> 24) & 255) > 200
               for xx in range(strip.width())):
            strip_bottom = yy
    if strip_bottom == 0:
        raise RuntimeError("strip grab is fully transparent")

    menuImg = _grabMenu(menu)
    if menuImg.width() <= 0 or menuImg.height() <= 0:
        raise RuntimeError("menu render produced an empty image")

    # Menu floats below the painted strip, left edge under the Walls
    # button's left edge.
    x = walls_btn_left - crop_x - MENU_BLEED
    y = strip_bottom + 1 + round(MENU_GAP * dpr)
    width = max(strip.width(), x + menuImg.width() + 2)
    height = y + menuImg.height() + 2

    canvas = QtGui.QImage(width, height, QtGui.QImage.Format_ARGB32)
    canvas.fill(0)                                     # transparent backdrop
    painter = QtGui.QPainter(canvas)
    painter.drawImage(0, 0, strip)
    painter.drawImage(x, y, menuImg)
    painter.end()

    if not canvas.save(OUT, "PNG"):
        raise RuntimeError("failed to write %s" % OUT)

    # --- Post-save pixel verification: decode the file and assert the
    # menu panel really sits under the Walls icon. ---
    vw, vh, px = _decodePng(OUT)

    def alpha(xx, yy):
        return px[(yy * vw + xx) * 4 + 3]

    opaque_rows = [any(alpha(xx, yy) > 200 for xx in range(vw))
                   for yy in range(vh)]
    runs, start = [], None
    for yy, op in enumerate(opaque_rows + [False]):
        if op and start is None:
            start = yy
        elif not op and start is not None:
            runs.append((start, yy - 1))
            start = None
    if len(runs) < 2:
        raise RuntimeError("verify: expected strip and menu bands, got %r"
                           % (runs,))
    band_gap = runs[1][0] - runs[0][1] - 1
    mx = [xx for yy in range(runs[1][0], runs[1][1] + 1)
          for xx in range(vw) if alpha(xx, yy) > 200]
    menu_left = min(mx)
    icon_left = walls_btn_left - crop_x
    if abs(menu_left - icon_left + MENU_BLEED) > 6 \
            or band_gap != round(MENU_GAP * dpr):
        raise RuntimeError(
            "verify: menu at x=%d gap=%d, Walls icon at x=%d - anchoring "
            "failed (bands %r)" % (menu_left, band_gap, icon_left, runs))

    print("toolbar image written: %s (%dx%d, mode=%s; menu x=%d under "
          "Walls icon x=%d, gap %d device px; verified)" %
          (OUT, vw, vh, mode, menu_left, icon_left, band_gap))


main()
