# SPDX-License-Identifier: LGPL-2.1-or-later
#
# PartsLibrary - a full-window MDI tab browsing the bundled BIM parts library.
#
# The panel is ONE screen, top to bottom: a wrapping row of room filter
# chips ("All" plus one per room a part declares, with counts), a search
# field, and a splitter holding the card grid beside a detail sidebar
# (preview, name, parameter form, description, Place in 3D view).
#
# There used to be a catalogue screen in front of this one - a card per room
# listing that room's elements as clickable rows - but 25 of the library's 36
# element rows led to exactly one part, so it cost two clicks to reach a
# single card. The rooms became the chips; the element facet stays in
# part.json, feeding search and the IFC type mapping, and is not navigable.
#
# PartsLibraryPanel itself is a plain QWidget that knows nothing about docks
# or MDI sub-windows - showPanel() below is the one place that hosts it, and
# it stays open across insertions so the pick -> place -> pick loop a library
# exists for does not require reopening the tool between parts.
#
# Browsing never loads geometry. The grid is built from the cached index and
# committed JPEG thumbnails; a shape is only built when a part is previewed
# or placed.

import os
import shutil
import tempfile


import FreeCAD
import FreeCADGui
from PySide import QtGui, QtCore

_DIR = os.path.dirname(__file__)     # archplus/tools/partslib/ itself

from archplus.common import widgets as archplus_widgets

from . import index as partslib_index
from . import theme as partslib_theme
from . import thumbs as partslib_thumbs

# partslib_object is imported lazily, inside the functions that need it
# (refresh(), _onPlace(), _fillResultsEmptyState()) rather than here at
# module scope. It imports ArchComponent at its own module scope, and this
# module is imported during the BIM workbench's Initialize() (InitGui.py's
# add_ui()), wrapped in a bare
# except that only prints to the Report view - if ArchComponent were not yet
# importable at that point, the import would raise, appendToolbar() would
# never run, and the whole ArchPlus toolbar would silently fail to appear.
# Matches archplus/tools/windows/gui.py's lazy `from . import object as
# windowsplus_object`.

ICON = os.path.join(_DIR, "resources", "icons", "PartsLibrary.svg")
_FACET_ICON_DIR = os.path.join(_DIR, "resources", "icons", "facets")

# Qt class name of FreeCAD's 3D view, used both to ask Gui.activateView for
# one and to find its MDI sub-window.
_VIEW3D_CLASS = "Gui::View3DInventor"

# Slow-operation reporting for the panel's own phases, sharing the timer
# and threshold used for thumbnails so the whole feature has one notion of
# "slow enough to be worth telling the user about". See
# partslib_thumbs.Timer.
_Timer = partslib_thumbs.Timer

# Detail-pane previews, remembered in memory rather than written to disk.
#
# These used to land in each part's .cache/ directory, one JPEG per distinct
# set of parameter values. Under variants that was a closed set - a handful
# of named sizes per part, so the directory converged. Under free-form
# params it is not: Width alone is a continuous Length, so every value
# anybody types leaves a file behind that nothing ever removes. One evening
# of trying television sizes left nine JPEGs in the library folder.
#
# A detail preview is a browsing artifact - it is worth having while the
# panel is open and worthless afterwards - so it belongs in a bounded
# in-memory cache that dies with the session, not in the source tree.
# .cache/ is now the BREP cache's alone (see geometry.CACHE_DIRNAME).
#
# Keyed by (part id, parameter hash): the same part at the same parameters
# renders once, and switching two values back and forth is free.
_PREVIEW_CACHE = {}
_PREVIEW_CACHE_ORDER = []
_PREVIEW_CACHE_LIMIT = 48


def _rememberPreview(key, pixmap):
    """Cache one rendered preview, evicting the oldest past the limit."""
    if key in _PREVIEW_CACHE:
        return
    _PREVIEW_CACHE[key] = pixmap
    _PREVIEW_CACHE_ORDER.append(key)
    while len(_PREVIEW_CACHE_ORDER) > _PREVIEW_CACHE_LIMIT:
        _PREVIEW_CACHE.pop(_PREVIEW_CACHE_ORDER.pop(0), None)


def clear_preview_cache():
    """Forget every remembered preview.

    Called on a rescan for the same reason the shape cache is dropped
    there: params are part of the key, but an edited BUILDER or asset file
    is not, so a preview can outlive the geometry it depicts."""
    _PREVIEW_CACHE.clear()
    del _PREVIEW_CACHE_ORDER[:]


_THUMB_SIZE = 96

# Explicit colour token sets for the panel's stylesheet, keyed by
# name so _applyTheme() (partslib_theme.read_is_dark_theme()) can pick the
# right one. These replace the old QPalette-derived colours: FreeCAD
# applies its theme as a global Qt STYLESHEET, not a palette, so
# palette().color(Base) stayed the Qt default WHITE regardless of how dark
# the active theme was, and the panel painted white cards with light text
# on top of them - white on white.
#
# Accent blue matches this add-on's own icon colour (#1a5fb4) on light;
# a lighter blue (#63a0e8) is used on dark so it does not disappear against
# a dark card.
_DARK_TOKENS = {
    "card_bg": "#3c3c3c",
    "page_bg": "#2b2b2b",
    "text": "#f2f2f2",
    "text_dim": "#b3b3b3",
    "border": "#5c5c5c",
    "accent": "#63a0e8",
    "accent_text": "#12233a",
    "ring": "#63a0e8",
}
_LIGHT_TOKENS = {
    "card_bg": "#ffffff",
    "page_bg": "#f2f2f2",
    "text": "#1c1c1c",
    "text_dim": "#5a5a5a",
    "border": "#c9c9c9",
    "accent": "#1a5fb4",
    "accent_text": "#ffffff",
    "ring": "#1a5fb4",
}

# STRUCTURAL RULE: every selector below that sets a background-color also
# sets a color, and vice versa, both drawn from the SAME token set
# (_DARK_TOKENS or _LIGHT_TOKENS - never mixed). That pairing is what makes
# white-on-white (or its dark-theme mirror, invisible-on-invisible)
# impossible to reintroduce by accident rather than merely unlikely - do
# not add a rule below that sets only one half of the pair.
_STYLESHEET_TEMPLATE = """
    QWidget#ArchPlusPartsLibrary {
        background-color: %(page_bg)s;
        color: %(text)s;
    }
    QFrame#PartCard {
        background-color: %(card_bg)s;
        color: %(text)s;
        border: 1px solid %(border)s;
        border-radius: 8px;
    }
    QFrame#PartCard[selected="true"] {
        background-color: %(card_bg)s;
        color: %(text)s;
        border: 2px solid %(ring)s;
    }
    QToolButton#RoomChip {
        background-color: %(page_bg)s;
        color: %(text)s;
        border: 1px solid %(border)s;
        border-radius: 11px;
        padding: 3px 10px;
    }
    QToolButton#RoomChip:hover {
        background-color: %(page_bg)s;
        color: %(accent)s;
        border-color: %(accent)s;
    }
    QToolButton#RoomChip:checked {
        background-color: %(accent)s;
        color: %(accent_text)s;
        border-color: %(accent)s;
    }
    QListWidget::item:selected, QListWidget::item:hover {
        background: transparent;
        border: none;
    }
"""

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

# How long the panel waits after the last keystroke before doing expensive
# work. Shared by the search field and the parameter form so the panel has
# ONE notion of "the user has stopped typing".
_DEBOUNCE_MS = 250

_panel = None


def _warnPreviewUnavailable(exc):
    """Note, once per session, that the live pivy.quarter preview could not be
    built and the panel is using a static image instead.

    This goes to the developer log rather than the console on purpose. On
    FreeCAD 1.1 it fires every single session and always will: Qt6 moved
    QOpenGLWidget out of QtWidgets, and pivy's bundled QuarterWidget still
    imports it from the old location. There is nothing the user can do about
    it, the static preview is a complete substitute, and a warning nobody can
    act on is just noise that trains people to ignore the report view. The
    detection stays in place so a future pivy fix silently restores the live
    preview, and the message stays available under View > Panels > Report
    view with logging enabled for anyone diagnosing it."""
    global _PREVIEW_WARNED
    if _PREVIEW_WARNED:
        return
    _PREVIEW_WARNED = True
    FreeCAD.Console.PrintLog(
        "ArchPlus: live 3D preview unavailable on this build "
        "(%s); using a static image preview instead.\n" % (exc,))



def _clearLayout(layout):
    """Remove and delete every item/widget a layout holds, so it can be
    rebuilt from scratch (the empty-state message)."""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        sublayout = item.layout()
        if sublayout is not None:
            _clearLayout(sublayout)


class PartsLibraryPanel(QtGui.QWidget):
    """The library browser widget: chips, search, grid and detail, on one
    screen.

    This is a plain QWidget - it knows nothing about docks or the MDI area.
    showPanel() below is the only thing that hosts it."""

    def __init__(self, parent=None):
        super(PartsLibraryPanel, self).__init__(parent)
        self.setObjectName("ArchPlusPartsLibrary")
        self._entries = []
        self._facets = {}
        # None is the "All" chip: no room filter, every part in the grid.
        self._filterRoom = None
        # Cleared when the user cancels the thumbnail build, so the cards
        # do not quietly go on rendering the rest inline. Reset by refresh.
        self._renderThumbnails = True
        self._buildUi()
        self.refresh()

    # -- construction ----------------------------------------------------
    def _buildUi(self):
        """The whole panel: chips, search, then grid beside detail."""
        outer = QtGui.QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        # Theme FIRST: _applyTheme() is what assigns self._tokens, and the
        # detail pane hands those tokens to ParamForm as it is constructed.
        # Building the widgets first left that read hitting an attribute
        # that did not exist yet. Nothing here touches a child widget - it
        # reads the theme, sets the tokens and styles this panel - so it is
        # safe before any of them exist.
        self._applyTheme()

        # There is no QStackedWidget here any more. The panel used to open
        # on a catalogue page of room cards listing element rows - but 25 of
        # the library's 36 element rows lead to exactly one part, so the page
        # was two clicks to reach a single card. The rooms survive as filter
        # chips above the grid; the element facet stays in part.json, feeding
        # search and the IFC type mapping, and is simply not navigable.
        self.chipRow = QtGui.QWidget()
        self.chipLayout = archplus_widgets.FlowLayout(self.chipRow)
        outer.addWidget(self.chipRow)

        # Created once, here, rather than per _populateChips() refresh: a
        # QButtonGroup rebound on every rescan would leave its predecessor
        # parented to the panel and never deleted - empty and harmless (its
        # buttons are already deleteLater()'d out from under it, and a button
        # removes itself from its group on destruction), but a leak all the
        # same. Reusing one group means _populateChips() only ever adds this
        # refresh's buttons to it.
        self._chipGroup = QtGui.QButtonGroup(self)
        self._chipGroup.setExclusive(True)

        self.search = QtGui.QLineEdit()
        self.search.setPlaceholderText("Search…")
        # DEBOUNCED, not wired straight to _repopulateGrid. Repopulating
        # selects row 0, which fires _onSelect -> _refreshPreview, so an
        # undebounced field ran a whole preview for every keystroke: typing
        # "cabinet" cost seven of them, and before the thumbnail fast path
        # that was three to four seconds of frozen UI. The parameter form
        # has had this treatment since it was written; the search field
        # never got it.
        self._searchTimer = QtCore.QTimer(self)
        self._searchTimer.setSingleShot(True)
        self._searchTimer.setInterval(_DEBOUNCE_MS)
        self._searchTimer.timeout.connect(self._repopulateGrid)
        self.search.textChanged.connect(self._searchTimer.start)
        outer.addWidget(self.search)

        splitter = QtGui.QSplitter(QtCore.Qt.Horizontal)

        self.grid = QtGui.QListWidget()
        self.grid.setViewMode(QtGui.QListView.IconMode)
        self.grid.setFlow(QtGui.QListView.LeftToRight)
        self.grid.setWrapping(True)
        self.grid.setResizeMode(QtGui.QListView.Adjust)
        self.grid.setMovement(QtGui.QListView.Static)
        self.grid.setSpacing(10)
        self.grid.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        self.grid.currentItemChanged.connect(self._onSelect)

        # JOB2: the grid and its empty-state message occupy the same
        # splitter slot, switched by _repopulateGrid - the card grid area
        # must never render as a blank void, whether the library is empty
        # or a search simply matches nothing.
        self.gridStack = QtGui.QStackedWidget()
        self.gridStack.addWidget(self.grid)          # index 0
        self.resultsEmptyState = QtGui.QWidget()
        self.gridStack.addWidget(self.resultsEmptyState)  # index 1
        splitter.addWidget(self.gridStack)

        sidebar = QtGui.QWidget()
        sidebar.setMinimumWidth(240)
        sidebar.setMaximumWidth(340)
        sidebarLayout = QtGui.QVBoxLayout(sidebar)
        self._buildDetail(sidebarLayout)
        splitter.addWidget(sidebar)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        outer.addWidget(splitter, 1)

    def _buildDetail(self, layout):
        """Preview, name, parameter form, description, Place."""
        self.preview = self._makePreviewWidget()
        self.preview.setMinimumHeight(_PREVIEW_HEIGHT)
        layout.addWidget(self.preview)

        self.detailName = QtGui.QLabel("")
        nameFont = self.detailName.font()
        nameFont.setBold(True)
        nameFont.setPointSize(nameFont.pointSize() + 1)
        self.detailName.setFont(nameFont)
        self.detailName.setWordWrap(True)
        layout.addWidget(self.detailName)

        self.detailFamily = QtGui.QLabel("")
        self.detailFamily.setWordWrap(True)
        familyFont = self.detailFamily.font()
        familyFont.setPointSize(max(7, familyFont.pointSize() - 1))
        self.detailFamily.setFont(familyFont)
        self.detailFamily.setStyleSheet(
            "color: %s;" % self._tokens["text_dim"])
        layout.addWidget(self.detailFamily)

        from . import paramform as partslib_paramform

        self.paramForm = partslib_paramform.ParamForm(self, self._tokens)
        self.paramForm.changed.connect(self._onParamsChanged)
        layout.addWidget(self.paramForm)

        self._paramTimer = QtCore.QTimer(self)
        self._paramTimer.setSingleShot(True)
        self._paramTimer.setInterval(_DEBOUNCE_MS)
        self._paramTimer.timeout.connect(self._refreshPreview)

        # There used to be a W/D/H readout here, measured from the built
        # shape. It went because it earned its keep only when it disagreed
        # with the fields above it - and disagreeing is exactly what a
        # measurement of the real geometry does: the vanity's 85 cm Height is
        # a 105 cm part once its backsplash and tap are counted. A user reads
        # a second set of W/D/H as the same numbers restated, so a 1 mm
        # difference reads as a bug rather than as information. The fields are
        # the part's dimensions now; this label only reports a failed build.
        self.buildError = QtGui.QLabel("")
        self.buildError.setWordWrap(True)
        layout.addWidget(self.buildError)

        self.description = QtGui.QLabel("")
        self.description.setWordWrap(True)
        layout.addWidget(self.description)

        layout.addStretch(1)

        self.placeButton = QtGui.QPushButton("Place in 3D view")
        self.placeButton.setEnabled(False)
        self.placeButton.clicked.connect(self._onPlace)
        layout.addWidget(self.placeButton)

        # Repeat placement is OPT-IN. "Place in 3D view" reads as placing
        # one part, so staying armed and dropping another on the next click
        # is a surprise for anyone who did not ask for it - and an easy one
        # to trigger by accident.
        self.repeatCheck = QtGui.QCheckBox("Keep placing until Esc")
        self.repeatCheck.setChecked(False)
        self.repeatCheck.setToolTip(
            "Stay armed after placing, so each click drops another copy. "
            "Press Esc to stop.")
        layout.addWidget(self.repeatCheck)

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

    def _applyTheme(self):
        """Build the stylesheet from an explicit dark/light colour token
        set (see _DARK_TOKENS/_LIGHT_TOKENS above), chosen by
        partslib_theme.read_is_dark_theme() - not from this widget's
        QPalette. FreeCAD applies its theme as a global Qt STYLESHEET, not
        a palette, so palette().color(Base) stayed the Qt default WHITE
        regardless of how dark the active theme was, and the previous
        version of this method painted white cards with light text on top
        of them: white on white.

        Rounded corners and comfortable padding come from the stylesheet
        template; the selected part card gets a two-pixel accent RING (not
        a filled highlight, which would drown the thumbnail)."""
        dark = partslib_theme.read_is_dark_theme()
        self._tokens = _DARK_TOKENS if dark else _LIGHT_TOKENS
        self.setStyleSheet(_STYLESHEET_TEMPLATE % self._tokens)

    # -- data ------------------------------------------------------------
    def refresh(self):
        """Rescan the library and rebuild the chips and the grid."""
        from . import object as partslib_object

        from . import geometry as partslib_geometry

        timer = _Timer("refreshing the parts library")
        # Reopening (or explicitly refreshing) is the user asking again, so
        # a cancelled thumbnail build gets another go.
        self._renderThumbnails = True
        # A rescan is the user saying "re-read the library", so remembered
        # shapes and previews go too - params are in both cache keys, but an
        # edited builder or asset file is not.
        partslib_geometry.clear_shape_cache()
        clear_preview_cache()
        index = partslib_object.libraryIndex(force=True)
        timer.mark("scan")

        self._entries = index["entries"]
        self._facets = index["facets"]

        self._populateChips()
        timer.mark("chips")

        self._repopulateGrid()
        timer.mark("grid")
        timer.report("%d parts" % (len(self._entries),))

    def _facetIconPath(self, iconName):
        """Resolve a bare facet icon filename under resources/icons/facets/.

        A missing file must degrade to no icon, never an error."""
        if not iconName:
            return None
        try:
            path = os.path.join(_FACET_ICON_DIR, iconName)
            return path if os.path.exists(path) else None
        except Exception:
            return None

    # -- room chips --------------------------------------------------------
    def _populateChips(self):
        """(Re)build the room filter chips from the current index.

        `All` comes first and is selected on open, then one chip per room
        that at least one part declares, with its facet icon and part count.
        They are exclusive - this is a filter, not a multi-select - which is
        what an auto-exclusive QButtonGroup gives for free."""
        while self.chipLayout.count():
            item = self.chipLayout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        groups = partslib_index.facet_groups(
            self._entries, self._facets, "room")
        # A rescan can retire the room the user was filtering by - deleting
        # the last part in it, or renaming its facet value. Fall back to All
        # rather than leave a filter no chip can show as active, which would
        # read as an empty library.
        if self._filterRoom is not None and not any(
                group["value"] == self._filterRoom for group in groups):
            self._filterRoom = None

        self._addChip("All", len(self._entries), None, None)
        for group in groups:
            self._addChip(group["label"], group["count"],
                          group["icon"], group["value"])

    def _addChip(self, label, count, iconName, room):
        """One filter chip. `room` is None for the All chip."""
        chip = QtGui.QToolButton()
        chip.setObjectName("RoomChip")
        chip.setCheckable(True)
        chip.setAutoRaise(True)
        chip.setCursor(QtCore.Qt.PointingHandCursor)
        chip.setText("%s · %d" % (label, count))
        chip.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        iconPath = self._facetIconPath(iconName)
        if iconPath:
            chip.setIcon(QtGui.QIcon(iconPath))
            chip.setIconSize(QtCore.QSize(16, 16))
        chip.setChecked(room == self._filterRoom)
        chip.clicked.connect(
            lambda *args, r=room: self._onChipSelected(r))
        self._chipGroup.addButton(chip)
        self.chipLayout.addWidget(chip)

    def _onChipSelected(self, room):
        # Clicking the already-selected chip still fires `clicked` (an
        # exclusive QButtonGroup refuses to uncheck it, but the click itself
        # still happened) - without this guard that re-ran _repopulateGrid()
        # for no filter change, which clears the grid and resets the
        # selection to row 0, losing whatever card and detail pane the user
        # had open.
        if room == self._filterRoom:
            return
        self._filterRoom = room
        self._repopulateGrid()

    def _facetMatches(self, entry, facet, value):
        declared = (entry.get("facets") or {}).get(facet)
        if declared is None or declared == []:
            return value == partslib_index.UNCLASSIFIED
        values = declared if isinstance(declared, list) else [declared]
        return value in values

    def _filteredEntries(self):
        matches = partslib_index.search(self._entries, self.search.text())
        if self._filterRoom is not None:
            matches = [e for e in matches
                       if self._facetMatches(e, "room", self._filterRoom)]
        return matches

    def _repopulateGrid(self, *args):
        """Rebuild the card grid from the current search text + room chip.
        Each card is always created and added - FIX 3 of the bug-fix round:
        a thumbnail failure must never hide a card, only its icon is
        conditional.

        JOB2: when nothing matches (an empty library, or a search that
        matches nothing) self.gridStack switches to the empty-state message
        in place of the card grid, and switches back the moment a match
        reappears - covering both "clear the search" and "the library
        gained its first part"."""
        self.grid.clear()
        entries = sorted(self._filteredEntries(), key=lambda e: e["name"])
        # Render anything missing FIRST, with a progress dialog, so the
        # count is known up front instead of discovered as the grid fills.
        # After this pass every card is a plain file read; on any open
        # after the first, nothing is pending and this returns instantly.
        if self._renderThumbnails:
            self._prerenderThumbnails(entries)
        # No per-card timing here: a card is only ever slow because of the
        # thumbnail behind it, and ensure_thumbnail already reports that -
        # naming the part and where its time went - for the parts that
        # actually were slow.
        for entry in entries:
            item = QtGui.QListWidgetItem()
            item.setData(QtCore.Qt.UserRole, entry["id"])
            card = self._makePartCard(entry)
            item.setSizeHint(card.sizeHint())
            self.grid.addItem(item)
            self.grid.setItemWidget(item, card)
        if self.grid.count():
            self.gridStack.setCurrentWidget(self.grid)
            self.grid.setCurrentRow(0)
        else:
            self._fillResultsEmptyState()
            self.gridStack.setCurrentWidget(self.resultsEmptyState)
            self._onSelect()

    def _fillResultsEmptyState(self):
        """(Re)build the empty-state message shown in place of the grid.

        One message now serves both cases the two screens used to split: an
        empty library and a search that matches nothing. The library path
        appears only for the former - it is the answer to "where do I put
        parts?", and noise next to a mistyped search.

        partslib_object is imported lazily, here, for its LIBRARY_DIR
        constant only - never at module scope. See the note above refresh()/
        _onPlace(): importing it at module scope pulls in ArchComponent
        during the BIM workbench's Initialize() and previously took out the
        whole toolbar."""
        from . import object as partslib_object

        layout = self.resultsEmptyState.layout()
        if layout is None:
            layout = QtGui.QVBoxLayout(self.resultsEmptyState)
            layout.setAlignment(QtCore.Qt.AlignCenter)
        else:
            _clearLayout(layout)

        empty = not self._entries
        message = QtGui.QLabel("No parts in the library yet" if empty
                               else "No parts match this search")
        message.setAlignment(QtCore.Qt.AlignCenter)
        message.setWordWrap(True)
        message.setStyleSheet("color: %s;" % self._tokens["text"])
        layout.addWidget(message)

        if empty:
            path = QtGui.QLabel(
                os.path.abspath(partslib_object.LIBRARY_DIR))
            path.setAlignment(QtCore.Qt.AlignCenter)
            path.setWordWrap(True)
            pathFont = path.font()
            pathFont.setPointSize(max(7, pathFont.pointSize() - 1))
            path.setFont(pathFont)
            path.setStyleSheet("color: %s;" % self._tokens["text_dim"])
            layout.addWidget(path)

    def _makePartCard(self, entry):
        """Square thumbnail, name, and - when its collection declares one -
        the family it belongs to.

        There used to be a monospaced line of the part's primary parameter
        LABELS here ("Width | Depth | Height"), with no values: it restated
        the column headings of a form the user had not opened. A card's job
        is recognition, which the thumbnail does; the detail pane states
        dimensions properly, as editable fields."""
        card = QtGui.QFrame()
        card.setObjectName("PartCard")
        card.setProperty("selected", False)
        card.setToolTip(entry.get("description") or entry["name"])
        v = QtGui.QVBoxLayout(card)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(4)

        thumb = QtGui.QLabel()
        thumb.setFixedSize(_THUMB_SIZE, _THUMB_SIZE)
        thumb.setAlignment(QtCore.Qt.AlignCenter)
        thumbPath = partslib_thumbs.thumbnail_path(entry["dir"])
        if not os.path.exists(thumbPath):
            # Spec Sec 9: no thumbnail was committed for this part, so
            # render one now and cache it to disk - this is the ONE place
            # browsing is allowed to build a shape, and only the first time;
            # ensure_thumbnail() writes the JPEG next to the part, so every
            # later open is back to a plain file read. Never raises: any
            # failure (no committed manifest, no GL context) returns None
            # and the card is still shown, just without an icon.
            if self._renderThumbnails:
                thumbPath = self._ensureGridThumbnail(entry) or thumbPath
        if os.path.exists(thumbPath):
            pixmap = QtGui.QPixmap(thumbPath)
            if not pixmap.isNull():
                thumb.setPixmap(pixmap.scaled(
                    _THUMB_SIZE, _THUMB_SIZE, QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation))
        v.addWidget(thumb, 0, QtCore.Qt.AlignHCenter)

        name = QtGui.QLabel(entry["name"])
        name.setAlignment(QtCore.Qt.AlignHCenter)
        name.setWordWrap(True)
        v.addWidget(name)

        # Only where the collection declares a label. An unlabelled
        # collection - which is what library/basic/ is - leaves the card at
        # thumbnail-plus-name and correspondingly shorter, because an
        # identical "Basic" under all 31 generic parts would be exactly the
        # noise the parameter line was removed for.
        family = entry.get("family")
        if family:
            familyLabel = QtGui.QLabel(family)
            familyLabel.setAlignment(QtCore.Qt.AlignHCenter)
            familyLabel.setWordWrap(True)
            familyFont = familyLabel.font()
            familyFont.setPointSize(max(7, familyFont.pointSize() - 1))
            familyLabel.setFont(familyFont)
            familyLabel.setStyleSheet(
                "color: %s;" % self._tokens["text_dim"])
            familyLabel.setToolTip(entry.get("familyDescription") or "")
            v.addWidget(familyLabel)

        return card

    # Below this many missing thumbnails, a dialog is more disruptive than
    # the wait it reports on.
    PROGRESS_THRESHOLD = 3

    def _prerenderThumbnails(self, entries):
        """Render every missing thumbnail up front, showing progress.

        Without this the first open of a fresh clone freezes FreeCAD
        outright: each card renders its own thumbnail inline, on the main
        thread, with nothing on screen to say why. Rendering cannot move
        off the main thread - the offscreen renderer needs the GL context
        that lives there - so the honest fix is to say what is happening
        and let the user stop it.

        Doing it as a separate pass BEFORE any card is built is what makes
        the count meaningful: the total is known before the first render
        rather than discovered as the grid fills.

        Cancelling sets `_renderThumbnails` False, which stops the cards
        rendering the rest inline behind the dialog's back - otherwise
        "Cancel" would only dismiss the dialog and leave the freeze."""
        pending = []
        for entry in entries:
            path = partslib_thumbs.thumbnail_path(entry["dir"])
            if (not os.path.exists(path)
                    and not partslib_thumbs.render_failed_before(path)):
                pending.append(entry)
        if len(pending) < self.PROGRESS_THRESHOLD:
            return

        dialog = QtGui.QProgressDialog(
            "Building thumbnails…", "Cancel", 0, len(pending),
            FreeCADGui.getMainWindow())
        dialog.setWindowTitle("ArchPlus Parts Library")
        dialog.setWindowModality(QtCore.Qt.ApplicationModal)
        # Show immediately: the whole point is that the UI is about to be
        # busy for a while, so Qt's default "wait and see" defeats it.
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(True)
        dialog.setValue(0)

        for index, entry in enumerate(pending):
            if dialog.wasCanceled():
                self._renderThumbnails = False
                FreeCAD.Console.PrintMessage(
                    "ArchPlus: stopped building thumbnails at %d of %d; the "
                    "rest will render next time the library is opened.\n"
                    % (index, len(pending)))
                break
            dialog.setLabelText("Building thumbnails: %d of %d\n%s"
                                % (index + 1, len(pending), entry["name"]))
            dialog.setValue(index)
            QtGui.QApplication.processEvents()
            self._ensureGridThumbnail(entry)
        dialog.setValue(len(pending))
        dialog.close()

    def _ensureGridThumbnail(self, entry):
        """Render a fallback thumbnail for `entry`'s manifest defaults.

        Resolve the manifest defaults for the grid rather than whatever is
        currently selected in the detail pane - the grid is not parameter-
        specific. Must never raise: a bad
        manifest or a failed render must still leave the entry's card
        visible by name, just with no icon."""
        from . import manifest as partslib_manifest

        try:
            manifest = partslib_manifest.load_manifest(entry["path"])
            return partslib_thumbs.ensure_thumbnail(entry, manifest)
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
        # Re-style every card's selection ring rather than tracking the
        # previous item separately - grids here are small, and this keeps
        # the "selected" property and the grid's actual current item from
        # ever drifting apart.
        current = self.grid.currentItem()
        for i in range(self.grid.count()):
            item = self.grid.item(i)
            widget = self.grid.itemWidget(item)
            if widget is not None:
                widget.setProperty("selected", item is current)
                widget.style().unpolish(widget)
                widget.style().polish(widget)

        entry = self.currentEntry()
        self.placeButton.setEnabled(entry is not None)
        if entry is None:
            self.detailName.setText("")
            self.detailFamily.setText("")
            self.detailFamily.setVisible(False)
            self.paramForm.setSpecs({}, [])
            self.buildError.setText("")
            self.description.setText("")
            return

        self.detailName.setText(entry["name"])
        self.detailFamily.setText(entry.get("family") or "")
        self.detailFamily.setToolTip(entry.get("familyDescription") or "")
        # An empty label still occupies a layout row; hide it so an
        # unlabelled collection leaves no gap under the part name.
        self.detailFamily.setVisible(bool(entry.get("family")))
        self.description.setText(entry.get("description") or "")
        from . import manifest as partslib_manifest

        shaped = {"params": entry.get("params") or {}}
        self.paramForm.setSpecs(
            partslib_manifest.param_specs(shaped),
            partslib_manifest.primary_params(shaped))
        self._refreshPreview()

    def _onParamsChanged(self):
        self._paramTimer.start()

    def _selection(self):
        """(entry, manifest, overrides) for the current selection, or None."""
        from . import manifest as partslib_manifest

        entry = self.currentEntry()
        if entry is None:
            return None
        manifest = partslib_manifest.load_manifest(entry["path"])
        return entry, manifest, self.paramForm.values()

    def _refreshPreview(self):
        """Show the selected part at the selected parameters.

        Not simply "build and render" any more - see
        partslib_thumbs.preview_plan for which of the four steps each state
        actually needs, and why."""
        from . import geometry as partslib_geometry

        selection = self._selection()
        if selection is None:
            return
        entry, manifest, overrides = selection

        thumbPath = partslib_thumbs.thumbnail_path(entry["dir"])
        # A live pivy preview must never be replaced by a flat picture, so
        # the committed thumbnail is only "usable" on the static path. On
        # FreeCAD 1.1 that is every session (Qt6 moved QOpenGLWidget out from
        # under pivy's QuarterWidget), but the guard keeps a future pivy fix
        # from silently downgrading the pane.
        thumbnailUsable = bool(
            not _PREVIEW_LIVE and os.path.exists(thumbPath))
        plan = partslib_thumbs.preview_plan(
            self.paramForm.isPristine(),
            self.paramForm.hasDerivedFields(),
            thumbnailUsable)

        timer = _Timer("previewing %r" % (entry["id"],))
        shape = None
        if plan["build"]:
            try:
                shape = partslib_geometry.build_shape(
                    manifest, entry["dir"], overrides)
            except Exception as exc:
                self.buildError.setText("Cannot build this part: %s" % exc)
                return
            timer.mark("build")
        self.buildError.setText("")

        if plan["measure"] and shape is not None:
            # An "auto" param can only be one of the shape's own dimensions
            # (manifest.AUTO_PARAM_NAMES), so measuring the built shape
            # reports every one of them - there is nothing else for a builder
            # to tell us.
            self.paramForm.setDerived(partslib_geometry.measure(shape))
            timer.mark("measure")

        if plan["use_thumbnail"]:
            self._showCommittedThumbnail(thumbPath)
        elif _PREVIEW_LIVE:
            try:
                self.preview.setSceneGraph(
                    partslib_thumbs.scene_from_shape(shape))
                self.preview.viewAll()
            except Exception as exc:
                FreeCAD.Console.PrintWarning(
                    "ArchPlus: live preview failed: %s\n" % (exc,))
        else:
            self._showStaticPreview(entry, shape, manifest, overrides)
        timer.mark("preview")
        timer.report()

    def _showCommittedThumbnail(self, thumbPath):
        """Put the part's committed thumbnail in the detail pane.

        Degrades to the placeholder rather than raising: an unreadable file
        must leave the pane usable, exactly as _showStaticPreview's last
        layer does."""
        pixmap = QtGui.QPixmap(thumbPath)
        if pixmap.isNull():
            self.preview.setPixmap(QtGui.QPixmap())
            self.preview.setText("No preview available")
            return
        self.preview.setPixmap(pixmap.scaledToHeight(
            _PREVIEW_HEIGHT, QtCore.Qt.SmoothTransformation))

    def _showStaticPreview(self, entry, shape, manifest, overrides):
        """Static-image fallback for the detail pane - FIX 2 of the bug-fix
        round. Degrades through three layers, most-specific first, each
        wrapped so a failure falls through to the next rather than raising:

          1. a per-parameter render at detail (256px) resolution, held in
             memory for the session (see _PREVIEW_CACHE);
          2. the part's committed thumbnail.jpg (not parameter-specific, but
             still a real preview of the part);
          3. a plain text placeholder - this layer must always succeed, even
             with no pivy/GL available at all, since it is what stands
             between the user and a blank pane."""
        pixmap = self._renderParamPreview(entry, shape, manifest, overrides)
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

    def _paramCacheKey(self, manifest, overrides):
        """A stable short digest of one set of param values."""
        import hashlib

        from . import manifest as partslib_manifest

        params = partslib_manifest.merge_params(manifest, overrides)
        blob = repr(sorted((str(k), str(v)) for k, v in params.items()))
        return hashlib.sha1(blob.encode("utf8")).hexdigest()[:12]

    def _renderParamPreview(self, entry, shape, manifest, overrides):
        """Render `shape` at detail resolution, memoized in _PREVIEW_CACHE by
        part and parameter values. Returns a QPixmap, or None on any failure
        (a renderer with no GL context - render_shape already returns False
        rather than raising in that case) so the caller can fall through to
        the next layer.

        The render still needs a file to write, since SoOffscreenRenderer
        saves to a path rather than handing back a buffer - but that file is
        a temporary one, read straight into a pixmap and deleted. A
        temporary DIRECTORY rather than a temporary file, because
        render_shape reports success by testing that out_path exists, and
        mkstemp would have created it already.

        Checks the shared session failure cache first, under a key naming
        the part rather than the (now per-call) output path: on a machine
        where the renderer can never succeed, re-selecting the same part or
        switching parameters back and forth would otherwise retry the same
        doomed render every single time - see partslib_thumbs.py's
        _RENDER_FAILED for the full rationale."""
        key = (entry["id"], self._paramCacheKey(manifest, overrides))
        cached = _PREVIEW_CACHE.get(key)
        if cached is not None:
            return cached
        failureKey = "detail-preview:%s" % (entry["id"],)
        if partslib_thumbs.render_failed_before(failureKey):
            return None

        folder = tempfile.mkdtemp(prefix="archplus-preview-")
        out_path = os.path.join(folder, "preview.jpg")
        try:
            if not partslib_thumbs.render_shape(
                    shape, out_path, size=partslib_thumbs.THUMBNAIL_SIZE):
                partslib_thumbs.mark_render_failed(failureKey, (
                    "ArchPlus: cannot render a detail preview for %r; "
                    "will not retry this session\n" % (entry["id"],)))
                return None
            pixmap = QtGui.QPixmap(out_path)
            if pixmap.isNull():
                return None
            _rememberPreview(key, pixmap)
            return pixmap
        except Exception as exc:
            FreeCAD.Console.PrintWarning(
                "ArchPlus: cannot render a detail preview for %s: %s\n"
                % (entry["id"], exc))
            return None
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def _find3DSubWindow(self, mdi):
        """The MDI sub-window holding a 3D view, or None.

        Matched on the widget's Qt class name: PySide hands back a plain
        QWidget for a sub-window's widget and knows nothing of FreeCAD's
        view API, but the widget's metaObject still reports the real C++
        class underneath."""
        for sub in mdi.subWindowList():
            try:
                if sub.widget().metaObject().className() == _VIEW3D_CLASS:
                    return sub
            except Exception:
                continue
        return None

    def _activate3DView(self, mdi):
        """Make a 3D view the active window. True if one is now active.

        The Snapper needs an ACTIVE 3D view, and the library panel is itself
        an MDI sub-window - so simply opening the library deactivates
        whatever 3D view the user was looking at.

        This used to scan mdi.subWindowList() for a sub-window whose widget
        had a `getSceneGraph` attribute, borrowing the duck-type check
        doors/gui.py applies to the active window. It could never match:
        getSceneGraph lives on FreeCAD's View3DInventorPy - the object Gui
        hands back as ActiveView - and NOT on the QWidget that PySide
        returns from QMdiSubWindow.widget(), where PySide only knows the Qt
        base class. The check was being asked of an object that had no way
        to answer it, so placing a part always reported "no 3D view is
        open" even with one open right beside the panel.

        Gui.activateView is FreeCAD's own API for this (its PartDesign test
        suite uses the identical call), and letting it create a view when
        the document has none is friendlier than refusing to place."""
        try:
            FreeCADGui.activateView(_VIEW3D_CLASS, True)
        except Exception as exc:
            FreeCAD.Console.PrintWarning(
                "ArchPlus: cannot activate a 3D view: %s\n" % (exc,))

        # activateView makes the view current as far as FreeCAD is
        # concerned, but the library panel is itself an MDI sub-window and
        # keeps the on-screen tab - so raise the 3D view's tab too, or the
        # user has to click it by hand before they can pick a point.
        subWindow = self._find3DSubWindow(mdi) if mdi is not None else None
        if subWindow is not None:
            mdi.setActiveSubWindow(subWindow)

        try:
            # Ask the view object itself, which is where getSceneGraph
            # actually lives.
            return hasattr(FreeCADGui.ActiveDocument.ActiveView,
                           "getSceneGraph")
        except Exception:
            return False

    def _onPlace(self, *args):
        """Activate a 3D view, pick a point, and place the part.

        One click places one part. Ticking "Keep placing until Esc" instead
        stays armed after each placement, so every click drops another copy
        of the same part until the user cancels.

        The Snapper needs an ACTIVE 3D view, so this first finds and
        activates one (browsing the catalogue never needs a document - see
        IsActive below - but placing does). If there is no document or no
        3D view open, bail out with a clear console message before any
        Snapper session or tracker is started."""
        if FreeCAD.ActiveDocument is None:
            FreeCAD.Console.PrintError(
                "ArchPlus: no active document - open a document with a 3D "
                "view before placing a library part.\n")
            return

        mainWindow = FreeCADGui.getMainWindow()
        mdi = mainWindow.findChild(QtGui.QMdiArea)
        librarySubWindow = self.parentWidget()
        if not self._activate3DView(mdi):
            FreeCAD.Console.PrintError(
                "ArchPlus: no 3D view is open - open a document with a 3D "
                "view before placing a library part.\n")
            return

        from . import geometry as partslib_geometry
        from . import manifest as partslib_manifest
        from . import object as partslib_object
        from . import placement as partslib_placement
        import draftguitools.gui_trackers as DraftTrackers

        selection = self._selection()
        if selection is None:
            return
        entry, manifest, overrides = selection
        params = partslib_manifest.merge_params(manifest, overrides)
        effective = {"placement": partslib_manifest.resolve_placement(
            manifest, params)}
        host = partslib_placement.host_of(effective)
        offset = partslib_placement.offset_of(effective)
        # Read once, up front: the checkbox lives on the library tab, which
        # is not even the active window while picking, so a mid-session
        # change of mind is not something the user can express anyway - and
        # this way the loop cannot be re-armed by a widget that has since
        # been destroyed.
        repeat = self.repeatCheck.isChecked()

        # Ghost tracker (spec Sec 7/8's "_placeTracker pattern",
        # doors/gui.py:887): a rough box preview of the part's footprint
        # that follows the cursor while picking, sized from the built
        # shape's measured bounding box. It stays ON across every repeat of
        # the placement loop below and is finalized EXACTLY ONCE, when the
        # loop ends (a single placement with repeat off, Esc, an exception,
        # or - see the early returns above - never even started when there
        # is no document/3D view). Degrade to
        # no tracker, not blocked placement, if the shape cannot be built.
        tracker = None
        trackerCentre = None
        try:
            shape = partslib_geometry.build_shape(
                manifest, entry["dir"], overrides)
            metrics = partslib_geometry.measure(shape)
            tracker = DraftTrackers.boxTracker()
            tracker.length(metrics["Width"])
            tracker.width(metrics["Depth"])
            tracker.height(metrics["Height"])
            # boxTracker.pos() sets the CENTRE of the ghost box (it moves an
            # SoCube, which straddles its own origin), but a part's origin
            # is its bounding box's minimum corner. Without this offset the
            # ghost previews a spot half a sofa away from where the part
            # actually lands.
            trackerCentre = FreeCAD.Vector(metrics["Width"] / 2.0,
                                           metrics["Depth"] / 2.0,
                                           metrics["Height"] / 2.0)
            tracker.on()
        except Exception as exc:
            FreeCAD.Console.PrintWarning(
                "ArchPlus: no placement preview for %s: %s\n"
                % (entry["id"], exc))
            tracker = None

        # The Snapper's callback does NOT hand back the picked face - only the
        # movecallback's `info` dict carries it. Capture it there and read it
        # back on click, exactly as repositionDoor does
        # (doors/gui.py:922-934).
        doc = FreeCAD.ActiveDocument
        state = {"face": None, "placed": False}

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
                tracker.pos(preview.multVec(trackerCentre))

        def placed(point=None, obj=None):
            FreeCADGui.Snapper.off()
            again = False
            state["placed"] = False
            try:
                if point is None:
                    return  # Esc/cancel - end the placement loop
                placement = partslib_placement.partPlacement(
                    point, state["face"], host, offset)
                doc.openTransaction("Place library part")
                try:
                    partslib_object.makePart(
                        entry, self._facets, placement=placement,
                        overrides=overrides)
                    doc.commitTransaction()
                    state["placed"] = True
                except Exception as exc:
                    doc.abortTransaction()
                    FreeCAD.Console.PrintError(
                        "ArchPlus: cannot place %s: %s\n"
                        % (entry["id"], exc))
                doc.recompute()
                again = repeat
            finally:
                if again:
                    # REPEAT PLACEMENT: re-arm for another pick so the user
                    # can keep clicking to drop more of the same part,
                    # without switching back to this tab between parts. The
                    # tracker stays on across repeats.
                    FreeCADGui.Snapper.getPoint(
                        callback=placed, movecallback=moved)
                else:
                    # End of the session - Esc, an exception above, or a
                    # single placement with repeat off. Finalize the tracker
                    # exactly once.
                    if tracker is not None:
                        tracker.finalize()
                    # Go back to the library only when nothing was placed.
                    # Having just dropped a part, the user wants to SEE it,
                    # and yanking them to the library tab hides the thing
                    # they asked for - but a cancel means "I'm done here",
                    # so return them where they started.
                    if not state["placed"] \
                            and mdi is not None \
                            and librarySubWindow is not None:
                        mdi.setActiveSubWindow(librarySubWindow)

        FreeCADGui.Snapper.getPoint(callback=placed, movecallback=moved)


def _hostInMdi(widget):
    """Host `widget` as a full-window tab in FreeCAD's MDI area.

    Follows FreeCAD's own shipped idiom exactly (Mod/Help/Help.py:505-510's
    mdi-hosting branch): find the QMdiArea, addSubWindow, set title/icon,
    show, and make it active.

    WA_DeleteOnClose is set on `widget` so that closing the tab actually
    destroys the underlying Qt objects - showPanel()'s RuntimeError-based
    self-healing below then has something real to catch rather than reusing
    or silently resurrecting a closed tab."""
    mainWindow = FreeCADGui.getMainWindow()
    mdi = mainWindow.findChild(QtGui.QMdiArea)
    if mdi is None:
        return None
    widget.setAttribute(QtCore.Qt.WA_DeleteOnClose)
    subWindow = mdi.addSubWindow(widget)
    subWindow.setWindowTitle("ArchPlus Library")
    subWindow.setWindowIcon(QtGui.QIcon(ICON))
    subWindow.show()
    mdi.setActiveSubWindow(subWindow)
    return subWindow


def showPanel():
    """Create the library tab, or bring it to the front if it already exists.

    `_panel` can outlive its C++ QWidget/QMdiSubWindow if the user closes the
    tab (WA_DeleteOnClose above then destroys both) or if FreeCAD ever tears
    down MDI sub-windows across a document switch or add-on reload. Touching
    a deleted widget raises RuntimeError; treat that as "no panel" and fall
    through to the single construction path below rather than leaving the
    tool permanently dead - so closing the tab and clicking the toolbar
    button again always yields a working tab."""
    global _panel
    # Not timed here: opening the panel is only ever slow because of the
    # refresh() inside it, which reports itself.
    mainWindow = FreeCADGui.getMainWindow()
    if _panel is not None:
        try:
            _panel.refresh()
            mdi = mainWindow.findChild(QtGui.QMdiArea)
            subWindow = _panel.parentWidget()
            if mdi is not None and subWindow is not None:
                mdi.setActiveSubWindow(subWindow)
            return _panel
        except RuntimeError:
            _panel = None
    _panel = PartsLibraryPanel(mainWindow)
    _hostInMdi(_panel)
    return _panel


class PartsLibraryCommand:
    """ArchPlus_PartsLibrary - open the parts library browser."""

    def GetResources(self):
        return {"Pixmap": ICON,
                "MenuText": "Parts Library",
                "ToolTip": "Browse and place reusable BIM parts"}

    def IsActive(self):
        # Browsing the catalogue never needs a document - only placing does,
        # and _onPlace handles that case itself (stairs/gui.py:488
        # follows the same permissive pattern).
        return True

    def Activated(self):
        showPanel()


# Register the command (FreeCAD 1.1 has no removeCommand; addCommand is a
# no-op if it's already registered, so guard to stay reload-safe).
if "ArchPlus_PartsLibrary" not in FreeCADGui.listCommands():
    FreeCADGui.addCommand("ArchPlus_PartsLibrary", PartsLibraryCommand())
