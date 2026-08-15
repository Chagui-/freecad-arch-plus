# SPDX-License-Identifier: LGPL-2.1-or-later
#
# PartsLibrary - a dockable browser for the bundled BIM parts library.
#
# Unlike the other ArchPlus tools this is NOT a Task panel: it is a QDockWidget
# that stays open across insertions, so the pick -> place -> pick loop a
# library exists for does not require reopening the tool between parts.
#
# Browsing never loads geometry. The grid is built from the cached index and
# committed PNG thumbnails; a shape is only built when a part is previewed or
# placed.

import os
import re
import sys

import FreeCAD
import FreeCADGui
from PySide import QtGui, QtCore

_DIR = os.path.dirname(__file__)
if _DIR not in sys.path:
    sys.path.append(_DIR)

import partslib_index
import partslib_thumbs

# partslib_object is imported lazily, inside the functions that need it
# (refresh(), _onPlace()) rather than here at module scope. It imports
# ArchComponent at its own module scope, and this module is imported during
# the BIM workbench's Initialize() (InitGui.py's add_ui()), wrapped in a bare
# except that only prints to the Report view - if ArchComponent were not yet
# importable at that point, the import would raise, appendToolbar() would
# never run, and the whole ArchPlus toolbar would silently fail to appear.
# Matches windowsplus_gui.py's lazy `import windowsplus_object`.

ICON = os.path.join(_DIR, "Resources", "icons", "PartsLibrary.svg")

GROUP_FACETS = ("function", "element", "room")
DEFAULT_GROUP_FACET = "room"
_PREF_PATH = "User parameter:BaseApp/Preferences/Mod/ArchPlus"
_PREF_GROUP_KEY = "PartsLibraryGroupBy"

_THUMB_SIZE = 96

# The Task 1 spike found that pivy's bundled Quarter is unusable on FreeCAD
# 1.1: QOpenGLWidget moved out of QtWidgets into QtOpenGLWidgets in Qt6, and
# pivy/qt/quarter/QuarterWidget.py still imports it from the old location, so
# `from pivy import quarter` raises ImportError on this build. The panel must
# never let that (or any other failure building the live widget) block it
# from opening, so live preview support is now auto-detected rather than
# hardcoded.
#
# PREVIEW_LIVE_ALLOWED is an override, not a statement of fact: True lets the
# panel attempt the live widget (falling back automatically if that attempt
# fails); set it False to force the static fallback even on a machine where
# the live widget would work.
PREVIEW_LIVE_ALLOWED = True

# The detected outcome for this session: None before the first attempt, then
# True or False once a live widget has actually been tried. Read this (not
# PREVIEW_LIVE_ALLOWED) wherever the code needs to know which preview path is
# actually in use.
_PREVIEW_LIVE = None

# Set once the "live preview unavailable" console warning has been printed,
# so the user sees it once per session rather than once per panel/selection.
_PREVIEW_WARNED = False

_PREVIEW_HEIGHT = 180

_panel = None


def _warnPreviewUnavailable(exc):
    """Print the one-per-session console warning that the live pivy.quarter
    preview could not be built, and that the panel is falling back to a
    static image instead."""
    global _PREVIEW_WARNED
    if _PREVIEW_WARNED:
        return
    _PREVIEW_WARNED = True
    FreeCAD.Console.PrintWarning(
        "ArchPlus: live 3D preview is unavailable on this FreeCAD build "
        "(%s); using a static image preview instead.\n" % (exc,))


def _sanitizeVariantLabel(label):
    """Turn a variant label ("800 mm") into a safe filename fragment.

    Labels are free text from the manifest and may contain spaces or, in
    principle, path characters ("/", ".."); this must never be used
    unsanitised as part of a filename."""
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", label or "").strip("_")
    return safe or "variant"


def _prefs():
    return FreeCAD.ParamGet(_PREF_PATH)


class PartsLibraryPanel(QtGui.QDockWidget):
    """The library browser dock."""

    def __init__(self, parent=None):
        super(PartsLibraryPanel, self).__init__("ArchPlus Library", parent)
        self.setObjectName("ArchPlusPartsLibrary")
        self._entries = []
        self._buildUi()
        self.refresh()

    # -- construction ----------------------------------------------------
    def _buildUi(self):
        body = QtGui.QWidget()
        layout = QtGui.QVBoxLayout(body)

        self.search = QtGui.QLineEdit()
        self.search.setPlaceholderText("Search…")
        self.search.textChanged.connect(self._repopulate)
        layout.addWidget(self.search)

        groupRow = QtGui.QHBoxLayout()
        groupRow.addWidget(QtGui.QLabel("Group by:"))
        self.groupBy = QtGui.QComboBox()
        self.groupBy.addItems([f.capitalize() for f in GROUP_FACETS])
        stored = _prefs().GetString(_PREF_GROUP_KEY, DEFAULT_GROUP_FACET)
        if stored in GROUP_FACETS:
            self.groupBy.setCurrentIndex(GROUP_FACETS.index(stored))
        self.groupBy.currentIndexChanged.connect(self._onGroupChanged)
        groupRow.addWidget(self.groupBy, 1)
        layout.addLayout(groupRow)

        splitter = QtGui.QSplitter(QtCore.Qt.Horizontal)
        self.tree = QtGui.QListWidget()
        self.tree.setMaximumWidth(140)
        self.tree.currentItemChanged.connect(self._repopulateGrid)
        splitter.addWidget(self.tree)

        self.grid = QtGui.QListWidget()
        self.grid.setViewMode(QtGui.QListView.IconMode)
        self.grid.setIconSize(QtCore.QSize(_THUMB_SIZE, _THUMB_SIZE))
        self.grid.setResizeMode(QtGui.QListView.Adjust)
        self.grid.setMovement(QtGui.QListView.Static)
        self.grid.setSpacing(6)
        splitter.addWidget(self.grid)
        layout.addWidget(splitter, 1)

        self._buildDetail(layout)
        # Connected only after _buildDetail has created the widgets _onSelect
        # touches (placeButton, variant, metrics, description) - it is wired
        # here rather than alongside the rest of self.grid's setup above.
        self.grid.currentItemChanged.connect(self._onSelect)

        self.setWidget(body)

    def _buildDetail(self, layout):
        """Preview, measurements, description, variant picker and Place."""
        self.preview = self._makePreviewWidget()
        self.preview.setMinimumHeight(_PREVIEW_HEIGHT)
        layout.addWidget(self.preview)

        variantRow = QtGui.QHBoxLayout()
        variantRow.addWidget(QtGui.QLabel("Variant:"))
        self.variant = QtGui.QComboBox()
        self.variant.currentIndexChanged.connect(self._onVariantChanged)
        variantRow.addWidget(self.variant, 1)
        layout.addLayout(variantRow)

        self.metrics = QtGui.QLabel("")
        layout.addWidget(self.metrics)

        self.description = QtGui.QLabel("")
        self.description.setWordWrap(True)
        layout.addWidget(self.description)

        self.placeButton = QtGui.QPushButton("Place")
        self.placeButton.setEnabled(False)
        self.placeButton.clicked.connect(self._onPlace)
        layout.addWidget(self.placeButton)

    def _makePreviewWidget(self):
        """Build the live 3D preview widget if possible, else a static image
        label - FIX 1 of the bug-fix round.

        A preview is a nice-to-have and must never sit on panel
        construction's critical path: both `from pivy import quarter` and
        `quarter.QuarterWidget()` are wrapped so that ANY failure (today an
        ImportError - pivy's bundled QuarterWidget.py imports QOpenGLWidget
        from QtWidgets, which moved to QtOpenGLWidgets in Qt6 - but possibly
        a GL-context failure raising something else entirely) falls back to
        the static QLabel path instead of propagating out of __init__."""
        global _PREVIEW_LIVE
        if PREVIEW_LIVE_ALLOWED and _PREVIEW_LIVE is not False:
            try:
                from pivy import quarter
                widget = quarter.QuarterWidget()
            except Exception as exc:
                if _PREVIEW_LIVE is None:
                    _warnPreviewUnavailable(exc)
                _PREVIEW_LIVE = False
            else:
                _PREVIEW_LIVE = True
                return widget
        label = QtGui.QLabel()
        label.setAlignment(QtCore.Qt.AlignCenter)
        return label

    # -- data ------------------------------------------------------------
    def refresh(self):
        """Rescan the library and rebuild the whole view."""
        import partslib_object

        index = partslib_object.libraryIndex(force=True)
        self._entries = index["entries"]
        self._facets = index["facets"]
        self._repopulate()

    def _groupFacet(self):
        return GROUP_FACETS[self.groupBy.currentIndex()]

    def _onGroupChanged(self, *args):
        _prefs().SetString(_PREF_GROUP_KEY, self._groupFacet())
        self._repopulate()

    def _repopulate(self, *args):
        """Rebuild the group list, preserving the selected group if possible."""
        previous = self.tree.currentItem().text() if self.tree.currentItem() \
            else None
        matches = partslib_index.search(self._entries, self.search.text())
        self._groups = partslib_index.group_by(matches, self._groupFacet())

        self.tree.blockSignals(True)
        self.tree.clear()
        for name in sorted(self._groups):
            self.tree.addItem(name)
        self.tree.blockSignals(False)

        if self.tree.count():
            row = 0
            if previous:
                found = self.tree.findItems(previous, QtCore.Qt.MatchExactly)
                if found:
                    row = self.tree.row(found[0])
            self.tree.setCurrentRow(row)
        self._repopulateGrid()

    def _repopulateGrid(self, *args):
        self.grid.clear()
        item = self.tree.currentItem()
        if item is None:
            return
        for entry in sorted(self._groups.get(item.text(), []),
                            key=lambda e: e["name"]):
            cell = QtGui.QListWidgetItem(entry["name"])
            cell.setData(QtCore.Qt.UserRole, entry["id"])
            thumb = partslib_thumbs.thumbnail_path(entry["dir"])
            if not os.path.exists(thumb):
                # Spec Sec 9: no thumbnail was committed for this part, so
                # render one now and cache it to disk - this is the ONE place
                # browsing is allowed to build a shape, and only the first
                # time; ensure_thumbnail() writes the PNG next to the part,
                # so every later open is back to a plain file read. Never
                # raises: any failure (no committed manifest, no GL context)
                # returns None and the card below is just shown without an
                # icon rather than being hidden.
                thumb = self._ensureGridThumbnail(entry) or thumb
            if os.path.exists(thumb):
                cell.setIcon(QtGui.QIcon(thumb))
            cell.setToolTip(entry.get("description") or entry["name"])
            self.grid.addItem(cell)

    def _ensureGridThumbnail(self, entry):
        """Render a fallback thumbnail for `entry`'s default variant.

        Resolved the same way `_resolvedSelection` does, but for the first
        variant rather than whatever is currently selected in the detail
        pane - the grid is not variant-specific. Must never raise: a bad
        manifest or a failed render must still leave the entry's card
        visible by name, just with no icon."""
        import partslib_manifest

        try:
            manifest = partslib_manifest.load_manifest(entry["path"])
            resolved = partslib_manifest.resolve_variant(
                manifest, entry["variants"][0])
            return partslib_thumbs.ensure_thumbnail(entry, resolved)
        except Exception as exc:
            FreeCAD.Console.PrintWarning(
                "ArchPlus: cannot render a thumbnail for %s: %s\n"
                % (entry["id"], exc))
            return None

    def currentEntry(self):
        """The selected entry dict, or None."""
        item = self.grid.currentItem()
        if item is None:
            return None
        partId = item.data(QtCore.Qt.UserRole)
        for entry in self._entries:
            if entry["id"] == partId:
                return entry
        return None

    def _onSelect(self, *args):
        entry = self.currentEntry()
        self.placeButton.setEnabled(entry is not None)
        if entry is None:
            self.variant.clear()
            self.metrics.setText("")
            self.description.setText("")
            return

        self.description.setText(entry.get("description") or "")
        self.variant.blockSignals(True)
        self.variant.clear()
        self.variant.addItems(entry["variants"])
        self.variant.blockSignals(False)
        self._refreshPreview()

    def _onVariantChanged(self, *args):
        self._refreshPreview()

    def _resolvedSelection(self):
        """(entry, resolved manifest) for the current selection, or None."""
        import partslib_manifest

        entry = self.currentEntry()
        if entry is None:
            return None
        manifest = partslib_manifest.load_manifest(entry["path"])
        label = self.variant.currentText() or entry["variants"][0]
        return entry, partslib_manifest.resolve_variant(manifest, label)

    def _refreshPreview(self):
        """Build the selected variant and show it with its measurements."""
        import partslib_geometry

        selection = self._resolvedSelection()
        if selection is None:
            return
        entry, resolved = selection
        try:
            shape = partslib_geometry.build_shape(resolved, entry["dir"])
        except Exception as exc:
            self.metrics.setText("Cannot build this part: %s" % exc)
            return

        metrics = partslib_geometry.measure(shape)
        self.metrics.setText("W %.0f   D %.0f   H %.0f mm"
                             % (metrics["Width"], metrics["Depth"],
                                metrics["Height"]))

        if _PREVIEW_LIVE:
            try:
                self.preview.setSceneGraph(
                    partslib_thumbs.scene_from_shape(shape))
                self.preview.viewAll()
            except Exception as exc:
                FreeCAD.Console.PrintWarning(
                    "ArchPlus: live preview failed: %s\n" % (exc,))
        else:
            label = self.variant.currentText() or entry["variants"][0]
            self._showStaticPreview(entry, shape, label)

    def _showStaticPreview(self, entry, shape, label):
        """Static-image fallback for the detail pane - FIX 2 of the bug-fix
        round. Degrades through three layers, most-specific first, each
        wrapped so a failure falls through to the next rather than raising:

          1. a freshly rendered/cached per-variant PNG at detail (256px)
             resolution;
          2. the part's committed thumbnail.png (not variant-specific, but
             still a real preview of the part);
          3. a plain text placeholder - this layer must always succeed, even
             with no pivy/GL available at all, since it is what stands
             between the user and a blank pane."""
        pixmap = self._renderVariantPreview(entry, shape, label)
        if pixmap is None:
            try:
                thumb = partslib_thumbs.thumbnail_path(entry["dir"])
                if os.path.exists(thumb):
                    candidate = QtGui.QPixmap(thumb)
                    if not candidate.isNull():
                        pixmap = candidate
            except Exception as exc:
                FreeCAD.Console.PrintWarning(
                    "ArchPlus: cannot load committed thumbnail for %s: %s\n"
                    % (entry["id"], exc))

        if pixmap is not None:
            self.preview.setPixmap(pixmap.scaledToHeight(
                _PREVIEW_HEIGHT, QtCore.Qt.SmoothTransformation))
        else:
            self.preview.setPixmap(QtGui.QPixmap())
            self.preview.setText("No preview available")

    def _renderVariantPreview(self, entry, shape, label):
        """Render `shape` at detail resolution, cached under the part's
        `.cache/` directory keyed by the sanitised variant label. Returns a
        QPixmap, or None on any failure (a bad cache path, or a renderer
        with no GL context - render_shape already returns False rather than
        raising in that case) so the caller can fall through to the next
        layer."""
        try:
            cache_dir = os.path.join(entry["dir"], ".cache")
            out_path = os.path.join(
                cache_dir, "%s.png" % _sanitizeVariantLabel(label))
            if not os.path.exists(out_path):
                if not partslib_thumbs.render_shape(
                        shape, out_path, size=partslib_thumbs.THUMBNAIL_SIZE):
                    return None
            pixmap = QtGui.QPixmap(out_path)
            return None if pixmap.isNull() else pixmap
        except Exception as exc:
            FreeCAD.Console.PrintWarning(
                "ArchPlus: cannot render a detail preview for %s (%s): %s\n"
                % (entry["id"], label, exc))
            return None

    def _onPlace(self):
        """Pick a point in the 3D view, then create the part there.

        Browsing the catalogue never needs a document (see IsActive below),
        but placing does - a Snapper pick has nowhere to land with no
        document/3D view open. Check first and bail out cleanly, before any
        tracker or Snapper session is started."""
        if FreeCAD.ActiveDocument is None:
            FreeCAD.Console.PrintError(
                "ArchPlus: no active document - create or open a document "
                "before placing a library part.\n")
            return

        import partslib_geometry
        import partslib_object
        import partslib_placement
        import draftguitools.gui_trackers as DraftTrackers

        selection = self._resolvedSelection()
        if selection is None:
            return
        entry, resolved = selection
        host = partslib_placement.host_of(resolved)
        offset = partslib_placement.offset_of(resolved)
        variant = self.variant.currentText() or entry["variants"][0]

        # Ghost tracker (spec Sec 7/8's "_placeTracker pattern",
        # doorsplus_gui.py:887): a rough box preview of the part's footprint
        # that follows the cursor while picking, sized from the built
        # shape's measured bounding box. It is centred on the same
        # placement partPlacement() computes for the click - an
        # approximation, since a part's anchor (manifest "anchor") need not
        # sit at its box's centre, but enough to judge size and orientation
        # before committing. Degrade to no tracker, not blocked placement,
        # if the shape cannot be built.
        tracker = None
        try:
            shape = partslib_geometry.build_shape(resolved, entry["dir"])
            metrics = partslib_geometry.measure(shape)
            tracker = DraftTrackers.boxTracker()
            tracker.length(metrics["Width"])
            tracker.width(metrics["Depth"])
            tracker.height(metrics["Height"])
            tracker.on()
        except Exception as exc:
            FreeCAD.Console.PrintWarning(
                "ArchPlus: no placement preview for %s: %s\n"
                % (entry["id"], exc))
            tracker = None

        # The Snapper's callback does NOT hand back the picked face - only the
        # movecallback's `info` dict carries it. Capture it there and read it
        # back on click, exactly as repositionDoor does
        # (doorsplus_gui.py:922-934).
        doc = FreeCAD.ActiveDocument
        state = {"face": None}

        def moved(point, info):
            if info and "Face" in info.get("Component", ""):
                target = doc.getObject(info["Object"])
                try:
                    index = int(info["Component"][4:]) - 1
                except (ValueError, IndexError):
                    state["face"] = None
                else:
                    state["face"] = [target, index]
            else:
                state["face"] = None
            if tracker is not None:
                preview = partslib_placement.partPlacement(
                    point, state["face"], host, offset)
                tracker.setRotation(preview.Rotation)
                tracker.pos(preview.Base)

        def placed(point=None, obj=None):
            FreeCADGui.Snapper.off()
            try:
                if point is None:
                    return
                placement = partslib_placement.partPlacement(
                    point, state["face"], host, offset)
                doc.openTransaction("Place library part")
                try:
                    partslib_object.makePart(
                        entry, self._facets, variant=variant,
                        placement=placement)
                    doc.commitTransaction()
                except Exception as exc:
                    doc.abortTransaction()
                    FreeCAD.Console.PrintError(
                        "ArchPlus: cannot place %s: %s\n"
                        % (entry["id"], exc))
                doc.recompute()
            finally:
                # Every exit path - commit, abort, or cancel (point is None)
                # - must clear the tracker, or a cancelled placement leaves a
                # ghost box stuck in the 3D view. Matches doorsplus_gui.py's
                # repositionDoor, which uses try/finally for the same reason.
                if tracker is not None:
                    tracker.finalize()

        FreeCADGui.Snapper.getPoint(callback=placed, movecallback=moved)


def showPanel():
    """Create the dock, or raise it if it already exists.

    `_panel` can outlive its C++ QDockWidget if FreeCAD ever destroys or
    recreates docked widgets across a document switch or add-on reload -
    nothing in this codebase has exercised that path before, since the other
    ArchPlus tools all use Control.showDialog task panels instead of a
    QDockWidget. Touching a deleted dock raises RuntimeError; treat that as
    "no panel" and fall through to the single construction path below rather
    than leaving the tool permanently dead.
    """
    global _panel
    main = FreeCADGui.getMainWindow()
    if _panel is not None:
        try:
            _panel.refresh()
        except RuntimeError:
            _panel = None
    if _panel is None:
        _panel = PartsLibraryPanel(main)
        main.addDockWidget(QtCore.Qt.RightDockWidgetArea, _panel)
    _panel.show()
    _panel.raise_()
    return _panel


class PartsLibraryCommand:
    """ArchPlus_PartsLibrary - open the parts library browser."""

    def GetResources(self):
        return {"Pixmap": ICON,
                "MenuText": "Parts Library",
                "ToolTip": "Browse and place reusable BIM parts"}

    def IsActive(self):
        # Browsing the catalogue never needs a document - only placing does,
        # and _onPlace handles that case itself (stairsplus_gui.py:488
        # follows the same permissive pattern).
        return True

    def Activated(self):
        showPanel()


# Register the command (FreeCAD 1.1 has no removeCommand; addCommand is a
# no-op if it's already registered, so guard to stay reload-safe).
if "ArchPlus_PartsLibrary" not in FreeCADGui.listCommands():
    FreeCADGui.addCommand("ArchPlus_PartsLibrary", PartsLibraryCommand())
