# SPDX-License-Identifier: LGPL-2.1-or-later
#
# PartsLibrary - a full-window MDI tab browsing the bundled BIM parts library.
#
# The panel is a two-screen catalogue browser:
#   - "categories": a card per ROOM (icon, label, hairline rule, then that
#     room's elements as clickable rows with counts). Clicking an element (or
#     a room header) drills into screen two.
#   - "results": a clickable breadcrumb ("All > Bathroom > Toilets"), a
#     search field, a card grid of parts, and a detail sidebar (preview,
#     name, parameter form, description, Place in 3D view).
#
# PartsLibraryPanel itself is a plain QWidget that knows nothing about docks
# or MDI sub-windows - showPanel() below is the one place that hosts it, and
# it stays open across insertions so the pick -> place -> pick loop a library
# exists for does not require reopening the tool between parts.
#
# Browsing never loads geometry. The grid is built from the cached index and
# committed PNG thumbnails; a shape is only built when a part is previewed or
# placed.

import os
import shutil
import tempfile


import FreeCAD
import FreeCADGui
from PySide import QtGui, QtCore

_DIR = os.path.dirname(__file__)     # archplus/tools/partslib/ itself

from . import index as partslib_index
from . import theme as partslib_theme
from . import thumbs as partslib_thumbs

# partslib_object is imported lazily, inside the functions that need it
# (refresh(), _onPlace()) rather than here at module scope. It imports
# ArchComponent at its own module scope, and this module is imported during
# the BIM workbench's Initialize() (InitGui.py's add_ui()), wrapped in a bare
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

# Target width (px) for a card in the categories/results grids - used to
# compute how many columns fit the available viewport width. See
# _columnCountFor() / Fix 3 of the bug-fix round.
_CARD_TARGET_WIDTH = 260

# Explicit colour token sets for the two screens' stylesheet, keyed by
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
    QWidget#ArchPlusPartsLibrary, QWidget#CategoriesContainer,
    QWidget#ResultsScreen {
        background-color: %(page_bg)s;
        color: %(text)s;
    }
    QFrame#RoomCard, QFrame#PartCard {
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
    QFrame#HairlineRule {
        background-color: %(border)s;
        color: %(border)s;
        border: none;
    }
    QPushButton#RoomHeader {
        background-color: transparent;
        color: %(text)s;
        font-weight: bold;
        text-align: left;
        border: none;
        padding: 4px 2px;
    }
    QPushButton#ElementRow {
        background-color: transparent;
        color: %(text_dim)s;
        text-align: left;
        border: none;
        padding: 3px 2px 3px 14px;
    }
    QPushButton#RoomHeader:hover, QPushButton#ElementRow:hover {
        background-color: transparent;
        color: %(accent)s;
    }

    QPushButton#BreadcrumbSegment {
        background-color: transparent;
        color: %(text)s;
        border: none;
        text-align: left;
        padding: 0px 2px;
    }
    QPushButton#BreadcrumbSegment:hover {
        background-color: transparent;
        color: %(accent)s;
        text-decoration: underline;
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
    rebuilt from scratch (breadcrumb, category cards)."""
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
    """The library browser widget: a two-screen catalogue.

    This is a plain QWidget - it knows nothing about docks or the MDI area.
    showPanel() below is the only thing that hosts it."""

    def __init__(self, parent=None):
        super(PartsLibraryPanel, self).__init__(parent)
        self.setObjectName("ArchPlusPartsLibrary")
        self._entries = []
        self._facets = {}
        self._categories = []
        self._categoryCards = []
        self._categoryColumns = 0
        self._filterRoom = None
        self._filterElement = None
        # Cleared when the user cancels the thumbnail build, so the cards
        # do not quietly go on rendering the rest inline. Reset by refresh.
        self._renderThumbnails = True
        self._buildUi()
        self.refresh()

    # -- construction ----------------------------------------------------
    def _buildUi(self):
        outer = QtGui.QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        self.stack = QtGui.QStackedWidget()
        outer.addWidget(self.stack)

        # Theme FIRST: _applyTheme() is what assigns self._tokens, and the
        # detail pane hands those tokens to ParamForm as it is constructed.
        # Building the screens first left that read hitting an attribute
        # that did not exist yet. Nothing here touches a child widget - it
        # reads the theme, sets the tokens and styles this panel - so it is
        # safe before the screens exist.
        self._applyTheme()

        self._buildCategoriesScreen()
        self._buildResultsScreen()
        self.stack.addWidget(self.categoriesScreen)
        self.stack.addWidget(self.resultsScreen)
        self.stack.setCurrentIndex(0)

    def _buildCategoriesScreen(self):
        """Screen one: a scrollable stack of room cards, or - JOB2, empty
        library - a centred empty-state message in its place.

        self.categoriesScreen (the page added to the top-level self.stack)
        holds its own nested QStackedLayout switching between
        self.categoriesScroll (the card grid) and self.categoriesEmptyState,
        so a resize event never needs to know which mode is active (see the
        early-return guard at the top of _reflowCategories)."""
        self.categoriesScreen = QtGui.QWidget()
        self._categoriesStack = QtGui.QStackedLayout(self.categoriesScreen)

        self.categoriesScroll = QtGui.QScrollArea()
        self.categoriesScroll.setWidgetResizable(True)
        self.categoriesScroll.setFrameShape(QtGui.QFrame.NoFrame)

        container = QtGui.QWidget()
        container.setObjectName("CategoriesContainer")
        self.categoriesLayout = QtGui.QGridLayout(container)
        self.categoriesLayout.setSpacing(16)
        self.categoriesLayout.setContentsMargins(4, 4, 4, 4)
        self.categoriesScroll.setWidget(container)
        self.categoriesScroll.viewport().installEventFilter(self)

        self.categoriesEmptyState = QtGui.QWidget()

        self._categoriesStack.addWidget(self.categoriesScroll)     # index 0
        self._categoriesStack.addWidget(self.categoriesEmptyState)  # index 1

    def _buildResultsScreen(self):
        """Screen two: breadcrumb, search, card grid and detail sidebar."""
        self.resultsScreen = QtGui.QWidget()
        self.resultsScreen.setObjectName("ResultsScreen")
        v = QtGui.QVBoxLayout(self.resultsScreen)
        v.setContentsMargins(0, 0, 0, 0)

        self.breadcrumb = QtGui.QHBoxLayout()
        v.addLayout(self.breadcrumb)

        self.search = QtGui.QLineEdit()
        self.search.setPlaceholderText("Search…")
        self.search.textChanged.connect(self._repopulateGrid)
        v.addWidget(self.search)

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

        # JOB2: the grid and its empty-state message ("no parts match this
        # search") occupy the same splitter slot, switched by _repopulateGrid
        # - the card grid area must never render as a blank void when a
        # search matches nothing.
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
        v.addWidget(splitter, 1)

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

        from . import paramform as partslib_paramform

        self.paramForm = partslib_paramform.ParamForm(self, self._tokens)
        self.paramForm.changed.connect(self._onParamsChanged)
        layout.addWidget(self.paramForm)

        self._paramTimer = QtCore.QTimer(self)
        self._paramTimer.setSingleShot(True)
        self._paramTimer.setInterval(250)
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
        """Rescan the library and rebuild both screens."""
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

        self._populateCategories()
        self._updateBreadcrumb()
        timer.mark("categories")

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

    # -- screen one: categories -------------------------------------------
    def _populateCategories(self):
        """Rebuild the room-card grid from scratch (new entries/facets).

        The cards themselves are (re)built here; _reflowCategories() below
        only ever repositions them in the grid, so a mere resize never
        rebuilds a card."""
        _clearLayout(self.categoriesLayout)
        self._categories = partslib_index.category_tree(
            self._entries, self._facets, primary="room", secondary="element")
        if not self._categories:
            # JOB2: zero rooms (an empty library) - show the empty-state
            # message in place of the card grid instead of a blank void.
            self._categoryCards = []
            self._categoryColumns = 0
            self._fillCategoriesEmptyState()
            self._categoriesStack.setCurrentWidget(self.categoriesEmptyState)
            return
        self._categoriesStack.setCurrentWidget(self.categoriesScroll)
        self._categoryCards = [self._makeRoomCard(room)
                                for room in self._categories]
        self._categoryColumns = 0  # force _reflowCategories to (re)place them
        self._reflowCategories()

    def _fillCategoriesEmptyState(self):
        """(Re)build the categories screen's empty-state message - JOB2: a
        quiet centred line plus, smaller beneath it, the absolute path of
        the library folder so the user knows where to add content.

        partslib_object is imported lazily, here, for its LIBRARY_DIR
        constant only - never at module scope. See the note above refresh()/
        _onPlace(): importing it at module scope pulls in ArchComponent
        during the BIM workbench's Initialize() and previously took out the
        whole toolbar."""
        from . import object as partslib_object

        layout = self.categoriesEmptyState.layout()
        if layout is None:
            layout = QtGui.QVBoxLayout(self.categoriesEmptyState)
            layout.setAlignment(QtCore.Qt.AlignCenter)
        else:
            _clearLayout(layout)

        message = QtGui.QLabel("No parts in the library yet")
        message.setAlignment(QtCore.Qt.AlignCenter)
        message.setWordWrap(True)
        message.setStyleSheet("color: %s;" % self._tokens["text"])
        layout.addWidget(message)

        path = QtGui.QLabel(os.path.abspath(partslib_object.LIBRARY_DIR))
        path.setAlignment(QtCore.Qt.AlignCenter)
        path.setWordWrap(True)
        pathFont = path.font()
        pathFont.setPointSize(max(7, pathFont.pointSize() - 1))
        path.setFont(pathFont)
        path.setStyleSheet("color: %s;" % self._tokens["text_dim"])
        layout.addWidget(path)

    def _columnCountFor(self, width):
        """How many ~_CARD_TARGET_WIDTH-wide columns fit in `width`, never
        fewer than one."""
        if width <= 0:
            return 1
        return max(1, width // _CARD_TARGET_WIDTH)

    def _reflowCategories(self):
        """Lay self._categoryCards out in a grid, sized from the scroll
        area's current viewport width.

        Only actually re-flows - taking the existing card widgets out of
        the grid and re-adding them at their new row/col, never rebuilding
        or leaking them - when the computed column count has actually
        CHANGED (or on the initial call, where _categoryColumns is reset to
        0 by _populateCategories). This is what keeps a resize drag from
        thrashing the layout on every pixel.

        Guarded at the top for the empty-library case (JOB2): with zero
        categories, _populateCategories has already switched
        self._categoriesStack to the empty-state page and returned without
        calling this method, but a resize event can still reach it through
        eventFilter - the detach/re-add loop below must not run against an
        empty self._categoryCards, or it would strip the (unrelated)
        empty-state widget out of the grid layout it does not belong to."""
        if not self._categories:
            return
        columns = self._columnCountFor(self.categoriesScroll.viewport().width())
        if columns == self._categoryColumns:
            return
        self._categoryColumns = columns

        while self.categoriesLayout.count():
            # Detach only - takeAt() does not delete the widget, so every
            # card is reused, never rebuilt or destroyed, across a reflow.
            self.categoriesLayout.takeAt(0)

        for index, card in enumerate(self._categoryCards):
            row, col = divmod(index, columns)
            self.categoriesLayout.addWidget(card, row, col)

        rowCount = 0
        if self._categoryCards:
            rowCount = (len(self._categoryCards) - 1) // columns + 1
        # Equal stretch on every occupied (and a few spare) column keeps
        # cards in a row equal-width and stops a lone card in a short row
        # from being stretched across the whole grid; one stretched row
        # below the last real row keeps cards pinned to the top instead of
        # stretching vertically to fill the scroll area. Reset a generous
        # fixed range every time rather than tracking the previous extent,
        # so a shrinking grid never leaves stale stretch behind.
        for c in range(64):
            self.categoriesLayout.setColumnStretch(c, 1 if c < columns else 0)
        for r in range(64):
            self.categoriesLayout.setRowStretch(r, 1 if r == rowCount else 0)

    def eventFilter(self, watched, event):
        if (watched is self.categoriesScroll.viewport()
                and event.type() == QtCore.QEvent.Resize):
            self._reflowCategories()
        return super(PartsLibraryPanel, self).eventFilter(watched, event)

    def _makeRoomCard(self, room):
        """One room card: icon + label header, a hairline rule, then that
        room's elements as clickable rows with counts."""
        card = QtGui.QFrame()
        card.setObjectName("RoomCard")
        v = QtGui.QVBoxLayout(card)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(6)

        header = QtGui.QPushButton("%s (%d)" % (room["label"], room["count"]))
        header.setObjectName("RoomHeader")
        header.setFlat(True)
        header.setCursor(QtCore.Qt.PointingHandCursor)
        iconPath = self._facetIconPath(room.get("icon"))
        if iconPath:
            header.setIcon(QtGui.QIcon(iconPath))
            header.setIconSize(QtCore.QSize(20, 20))
        header.clicked.connect(
            lambda *args, r=room["value"]: self._showResults(r, None))
        v.addWidget(header)

        rule = QtGui.QFrame()
        rule.setObjectName("HairlineRule")
        rule.setFixedHeight(1)
        v.addWidget(rule)

        for child in room["children"]:
            row = QtGui.QPushButton(
                "%s (%d)" % (child["label"], child["count"]))
            row.setObjectName("ElementRow")
            row.setFlat(True)
            row.setCursor(QtCore.Qt.PointingHandCursor)
            row.clicked.connect(
                lambda *args, r=room["value"], e=child["value"]:
                    self._showResults(r, e))
            v.addWidget(row)

        return card

    def _showCategories(self, *args):
        self.stack.setCurrentIndex(0)

    # -- screen two: results -----------------------------------------------
    def _showResults(self, room=None, element=None):
        self._filterRoom = room
        self._filterElement = element
        self._updateBreadcrumb()
        self._repopulateGrid()
        self.stack.setCurrentIndex(1)

    def _roomLabel(self, value):
        for room in self._categories:
            if room["value"] == value:
                return room["label"]
        return value

    def _elementLabel(self, roomValue, elementValue):
        for room in self._categories:
            if room["value"] == roomValue:
                for child in room["children"]:
                    if child["value"] == elementValue:
                        return child["label"]
        return elementValue

    def _updateBreadcrumb(self):
        """Rebuild "All > Bathroom > Toilets" - every segment clickable."""
        _clearLayout(self.breadcrumb)
        self._addBreadcrumbSegment("All", self._showCategories)
        if self._filterRoom is not None:
            self._addBreadcrumbSeparator()
            label = self._roomLabel(self._filterRoom)
            self._addBreadcrumbSegment(
                label,
                lambda *args, r=self._filterRoom: self._showResults(r, None))
        if self._filterElement is not None:
            self._addBreadcrumbSeparator()
            label = self._elementLabel(self._filterRoom, self._filterElement)
            self._addBreadcrumbSegment(
                label,
                lambda *args, r=self._filterRoom, e=self._filterElement:
                    self._showResults(r, e))
        self.breadcrumb.addStretch(1)

    def _addBreadcrumbSegment(self, text, callback):
        button = QtGui.QPushButton(text)
        button.setObjectName("BreadcrumbSegment")
        button.setFlat(True)
        button.setCursor(QtCore.Qt.PointingHandCursor)
        button.clicked.connect(callback)
        self.breadcrumb.addWidget(button)

    def _addBreadcrumbSeparator(self):
        sep = QtGui.QLabel("›")  # ›
        self.breadcrumb.addWidget(sep)

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
        if self._filterElement is not None:
            matches = [e for e in matches
                       if self._facetMatches(e, "element", self._filterElement)]
        return matches

    def _repopulateGrid(self, *args):
        """Rebuild the card grid from the current search text + breadcrumb
        filter. Each card is always created and added - FIX 3 of the
        bug-fix round: a thumbnail failure must never hide a card, only its
        icon is conditional.

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
        """(Re)build the results screen's empty-state message - JOB2: a
        quiet centred line where the card grid would otherwise render a
        blank void."""
        layout = self.resultsEmptyState.layout()
        if layout is None:
            layout = QtGui.QVBoxLayout(self.resultsEmptyState)
            layout.setAlignment(QtCore.Qt.AlignCenter)
        else:
            _clearLayout(layout)

        message = QtGui.QLabel("No parts match this search")
        message.setAlignment(QtCore.Qt.AlignCenter)
        message.setWordWrap(True)
        message.setStyleSheet("color: %s;" % self._tokens["text"])
        layout.addWidget(message)

    def _makePartCard(self, entry):
        """Square thumbnail on top, name beneath, a small monospaced line of
        primary parameter labels - the card look used everywhere in the panel."""
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
            # ensure_thumbnail() writes the PNG next to the part, so every
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

        from . import manifest as partslib_manifest

        shaped = {"params": entry.get("params") or {}}
        specs = partslib_manifest.param_specs(shaped)
        adjustable = QtGui.QLabel(" | ".join(
            (specs.get(name) or {}).get("label") or name
            for name in partslib_manifest.primary_params(shaped)))
        adjustableFont = QtGui.QFont("Monospace")
        adjustableFont.setStyleHint(QtGui.QFont.TypeWriter)
        adjustableFont.setPointSize(max(7, adjustableFont.pointSize() - 1))
        adjustable.setFont(adjustableFont)
        adjustable.setAlignment(QtCore.Qt.AlignHCenter)
        adjustable.setWordWrap(True)
        # Dim the parameter line relative to the name, using this screen's own
        # text_dim token (never QPalette - see _applyTheme's docstring for
        # why palette colours cannot be trusted here).
        adjustable.setStyleSheet("color: %s;" % self._tokens["text_dim"])
        v.addWidget(adjustable)

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
            self.paramForm.setSpecs({}, [])
            self.buildError.setText("")
            self.description.setText("")
            return

        self.detailName.setText(entry["name"])
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
