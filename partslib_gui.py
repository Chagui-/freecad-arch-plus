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
#     name, variant chips, W/D/H, description, Place in 3D view).
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
import re
import sys

import FreeCAD
import FreeCADGui
from PySide import QtGui, QtCore

_DIR = os.path.dirname(__file__)
if _DIR not in sys.path:
    sys.path.append(_DIR)

import partslib_index
import partslib_theme
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
_FACET_ICON_DIR = os.path.join(_DIR, "Resources", "icons", "facets")

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
    QPushButton#VariantChip {
        background-color: transparent;
        color: %(text)s;
        border: 1px solid %(border)s;
        border-radius: 10px;
        padding: 2px 10px;
    }
    QPushButton#VariantChip:checked {
        background-color: transparent;
        color: %(accent)s;
        border: 1px solid %(accent)s;
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
        self._buildUi()
        self.refresh()

    # -- construction ----------------------------------------------------
    def _buildUi(self):
        outer = QtGui.QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        self.stack = QtGui.QStackedWidget()
        outer.addWidget(self.stack)

        self._buildCategoriesScreen()
        self._buildResultsScreen()
        self.stack.addWidget(self.categoriesScreen)
        self.stack.addWidget(self.resultsScreen)
        self.stack.setCurrentIndex(0)

        self._applyTheme()

    def _buildCategoriesScreen(self):
        """Screen one: a scrollable stack of room cards."""
        self.categoriesScreen = QtGui.QScrollArea()
        self.categoriesScreen.setWidgetResizable(True)
        self.categoriesScreen.setFrameShape(QtGui.QFrame.NoFrame)

        container = QtGui.QWidget()
        container.setObjectName("CategoriesContainer")
        self.categoriesLayout = QtGui.QGridLayout(container)
        self.categoriesLayout.setSpacing(16)
        self.categoriesLayout.setContentsMargins(4, 4, 4, 4)
        self.categoriesScreen.setWidget(container)
        self.categoriesScreen.viewport().installEventFilter(self)

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
        splitter.addWidget(self.grid)

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
        """Preview, name, variant chips, measurements, description, Place."""
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

        self.variantRow = QtGui.QHBoxLayout()
        self.variantRow.setSpacing(4)
        layout.addLayout(self.variantRow)
        self.variantGroup = QtGui.QButtonGroup(self)
        self.variantGroup.setExclusive(True)
        self.variantGroup.buttonToggled.connect(self._onVariantChanged)

        self.metrics = QtGui.QLabel("")
        metricsFont = QtGui.QFont("Monospace")
        metricsFont.setStyleHint(QtGui.QFont.TypeWriter)
        self.metrics.setFont(metricsFont)
        layout.addWidget(self.metrics)

        self.description = QtGui.QLabel("")
        self.description.setWordWrap(True)
        layout.addWidget(self.description)

        layout.addStretch(1)

        self.placeButton = QtGui.QPushButton("Place in 3D view")
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
        import partslib_object

        index = partslib_object.libraryIndex(force=True)
        self._entries = index["entries"]
        self._facets = index["facets"]
        self._populateCategories()
        self._updateBreadcrumb()
        self._repopulateGrid()

    def _facetIconPath(self, iconName):
        """Resolve a bare facet icon filename under Resources/icons/facets/.

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
        self._categoryCards = [self._makeRoomCard(room)
                                for room in self._categories]
        self._categoryColumns = 0  # force _reflowCategories to (re)place them
        self._reflowCategories()

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
        thrashing the layout on every pixel."""
        columns = self._columnCountFor(self.categoriesScreen.viewport().width())
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
        if (watched is self.categoriesScreen.viewport()
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
        icon is conditional."""
        self.grid.clear()
        for entry in sorted(self._filteredEntries(), key=lambda e: e["name"]):
            item = QtGui.QListWidgetItem()
            item.setData(QtCore.Qt.UserRole, entry["id"])
            card = self._makePartCard(entry)
            item.setSizeHint(card.sizeHint())
            self.grid.addItem(item)
            self.grid.setItemWidget(item, card)
        if self.grid.count():
            self.grid.setCurrentRow(0)
        else:
            self._onSelect()

    def _makePartCard(self, entry):
        """Square thumbnail on top, name beneath, a small monospaced line of
        variant labels - the card look used everywhere in the panel."""
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

        variants = QtGui.QLabel("  ".join(entry["variants"]))
        variantsFont = QtGui.QFont("Monospace")
        variantsFont.setStyleHint(QtGui.QFont.TypeWriter)
        variantsFont.setPointSize(max(7, variantsFont.pointSize() - 1))
        variants.setFont(variantsFont)
        variants.setAlignment(QtCore.Qt.AlignHCenter)
        variants.setWordWrap(True)
        # Dim the variant line relative to the name, using this screen's own
        # text_dim token (never QPalette - see _applyTheme's docstring for
        # why palette colours cannot be trusted here).
        variants.setStyleSheet("color: %s;" % self._tokens["text_dim"])
        v.addWidget(variants)

        return card

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
            self._setVariantChips([])
            self.metrics.setText("")
            self.description.setText("")
            return

        self.detailName.setText(entry["name"])
        self.description.setText(entry.get("description") or "")
        self._setVariantChips(entry["variants"])
        self._refreshPreview()

    def _setVariantChips(self, labels):
        """Rebuild the variant chip row for the current selection."""
        for button in list(self.variantGroup.buttons()):
            self.variantGroup.removeButton(button)
            button.setParent(None)
            button.deleteLater()
        _clearLayout(self.variantRow)

        for label in labels:
            chip = QtGui.QPushButton(label)
            chip.setObjectName("VariantChip")
            chip.setCheckable(True)
            chip.setCursor(QtCore.Qt.PointingHandCursor)
            self.variantGroup.addButton(chip)
            self.variantRow.addWidget(chip)
        self.variantRow.addStretch(1)

        buttons = self.variantGroup.buttons()
        if buttons:
            buttons[0].blockSignals(True)
            buttons[0].setChecked(True)
            buttons[0].blockSignals(False)

    def _currentVariantLabel(self):
        for button in self.variantGroup.buttons():
            if button.isChecked():
                return button.text()
        return None

    def _onVariantChanged(self, *args):
        # buttonToggled(button, checked) fires twice on an exclusive switch
        # (the old chip going False, the new one going True) - only react
        # to the "became checked" half.
        checked = args[1] if len(args) > 1 else True
        if not checked:
            return
        self._refreshPreview()

    def _resolvedSelection(self):
        """(entry, resolved manifest) for the current selection, or None."""
        import partslib_manifest

        entry = self.currentEntry()
        if entry is None:
            return None
        manifest = partslib_manifest.load_manifest(entry["path"])
        label = self._currentVariantLabel() or entry["variants"][0]
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
            label = self._currentVariantLabel() or entry["variants"][0]
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

    def _findSceneGraphSubWindow(self, mdi):
        """The MDI sub-window whose widget is a real 3D view - the same
        `getSceneGraph` attribute check doorsplus_gui.py:992 already uses to
        detect one, just applied across every open sub-window instead of
        only the active one."""
        for sub in mdi.subWindowList():
            if hasattr(sub.widget(), "getSceneGraph"):
                return sub
        return None

    def _onPlace(self, *args):
        """Activate a 3D view, pick a point, place the part, and repeat.

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
        sceneSubWindow = self._findSceneGraphSubWindow(mdi) if mdi else None
        if sceneSubWindow is None:
            FreeCAD.Console.PrintError(
                "ArchPlus: no 3D view is open - open a document with a 3D "
                "view before placing a library part.\n")
            return

        librarySubWindow = self.parentWidget()
        mdi.setActiveSubWindow(sceneSubWindow)

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
        variant = self._currentVariantLabel() or entry["variants"][0]

        # Ghost tracker (spec Sec 7/8's "_placeTracker pattern",
        # doorsplus_gui.py:887): a rough box preview of the part's footprint
        # that follows the cursor while picking, sized from the built
        # shape's measured bounding box. It stays ON across every repeat of
        # the placement loop below and is finalized EXACTLY ONCE, when the
        # loop ends (Esc, an exception, or - see the early returns above -
        # never even started when there is no document/3D view). Degrade to
        # no tracker, not blocked placement, if the shape cannot be built.
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
            again = False
            try:
                if point is None:
                    return  # Esc/cancel - end the repeat-placement loop
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
                again = True
            finally:
                if again:
                    # REPEAT PLACEMENT: re-arm for another pick so the user
                    # can keep clicking to drop more of the same part,
                    # without switching back to this tab between parts. The
                    # tracker stays on across repeats.
                    FreeCADGui.Snapper.getPoint(
                        callback=placed, movecallback=moved)
                else:
                    # Loop end - Esc, or an exception above: finalize the
                    # tracker exactly once and return the user to the
                    # library tab they started from.
                    if tracker is not None:
                        tracker.finalize()
                    if librarySubWindow is not None:
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
        # and _onPlace handles that case itself (stairsplus_gui.py:488
        # follows the same permissive pattern).
        return True

    def Activated(self):
        showPanel()


# Register the command (FreeCAD 1.1 has no removeCommand; addCommand is a
# no-op if it's already registered, so guard to stay reload-safe).
if "ArchPlus_PartsLibrary" not in FreeCADGui.listCommands():
    FreeCADGui.addCommand("ArchPlus_PartsLibrary", PartsLibraryCommand())
