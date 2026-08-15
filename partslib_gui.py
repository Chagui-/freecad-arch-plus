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
import sys

import FreeCAD
import FreeCADGui
from PySide import QtGui, QtCore

_DIR = os.path.dirname(__file__)
if _DIR not in sys.path:
    sys.path.append(_DIR)

import partslib_index
import partslib_object
import partslib_thumbs

ICON = os.path.join(_DIR, "Resources", "icons", "PartsLibrary.svg")

GROUP_FACETS = ("function", "element", "room")
DEFAULT_GROUP_FACET = "function"
_PREF_PATH = "User parameter:BaseApp/Preferences/Mod/ArchPlus"
_PREF_GROUP_KEY = "PartsLibraryGroupBy"

_THUMB_SIZE = 96

_panel = None


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
        self.grid.currentItemChanged.connect(self._onSelect)
        splitter.addWidget(self.grid)
        layout.addWidget(splitter, 1)

        self.setWidget(body)

    # -- data ------------------------------------------------------------
    def refresh(self):
        """Rescan the library and rebuild the whole view."""
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
            thumb = os.path.join(entry["dir"],
                                 partslib_thumbs.THUMBNAIL_FILENAME)
            if os.path.exists(thumb):
                cell.setIcon(QtGui.QIcon(thumb))
            cell.setToolTip(entry.get("description") or entry["name"])
            self.grid.addItem(cell)

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
        """Extended in Task 14 to drive the detail pane."""
        pass


def showPanel():
    """Create the dock, or raise it if it already exists."""
    global _panel
    main = FreeCADGui.getMainWindow()
    if _panel is None:
        _panel = PartsLibraryPanel(main)
        main.addDockWidget(QtCore.Qt.RightDockWidgetArea, _panel)
    else:
        _panel.refresh()
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
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        showPanel()


# Register the command (FreeCAD 1.1 has no removeCommand; addCommand is a
# no-op when the name already exists).
if FreeCAD.GuiUp:
    FreeCADGui.addCommand("ArchPlus_PartsLibrary", PartsLibraryCommand())
