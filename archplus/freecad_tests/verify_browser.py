# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Startup, toolbar and browser checks: Parts A (A1/A2) and B
# (B1/B2/B4/B5/B6/B7/B9) of docs/PARTS-LIBRARY-VERIFICATION.md.

from archplus.freecad_tests import _harness as h

import FreeCADGui
from PySide import QtGui

from archplus.tools.partslib import gui as partslib_gui


def _toolbar_texts():
    """Every action text on every toolbar of the main window."""
    texts = []
    window = FreeCADGui.getMainWindow()
    for toolbar in window.findChildren(QtGui.QToolBar):
        for action in toolbar.actions():
            if action.text():
                texts.append(action.text())
    return texts


def _menu_texts():
    """Action texts inside the ArchPlus menu, if present."""
    texts = []
    window = FreeCADGui.getMainWindow()
    for menu in window.menuBar().findChildren(QtGui.QMenu):
        if "ArchPlus" in (menu.title() or ""):
            for action in menu.actions():
                if action.text():
                    texts.append(action.text())
    return texts


def _chip_texts(panel):
    texts = []
    for i in range(panel.chipLayout.count()):
        widget = panel.chipLayout.itemAt(i).widget()
        if widget is not None:
            texts.append(widget.text())
    return texts


def _card_labels(panel, index):
    card = panel.grid.itemWidget(panel.grid.item(index))
    if card is None:
        return []
    return [label.text() for label in card.findChildren(QtGui.QLabel)]


def _grid_names(panel):
    """Card names: the list item itself carries no text, the card's first
    text label is the part name (the thumbnail label is empty)."""
    names = []
    for i in range(panel.grid.count()):
        texts = [t for t in _card_labels(panel, i) if t]
        names.append(texts[0] if texts else "")
    return names


def _click_chip(panel, text):
    for i in range(panel.chipLayout.count()):
        widget = panel.chipLayout.itemAt(i).widget()
        if widget is not None and widget.text() == text:
            widget.click()
            return True
    return False


def _search(panel, text):
    panel.search.setText(text)
    h.process_events(400)  # the search debounce is 250 ms


def run():
    h.fresh_doc()
    FreeCADGui.activateWorkbench("BIMWorkbench")

    # A1/A2 - the command is registered and reachable.
    h.check("A1 Parts Library on a BIM toolbar",
            "Parts Library" in _toolbar_texts())
    h.check("A2 Parts Library in the ArchPlus menu",
            "Parts Library" in _menu_texts())

    # B1 - the panel opens as a tab hosted in the MDI area.
    panel = partslib_gui.showPanel()
    h.process_events(200)
    h.check("B1 panel opens as an MDI tab",
            panel.objectName() == "ArchPlusPartsLibrary"
            and panel.isVisible()
            and isinstance(panel.parentWidget(), QtGui.QMdiSubWindow),
            detail="objectName=%r visible=%r parent=%r"
            % (panel.objectName(), panel.isVisible(),
               type(panel.parentWidget()).__name__))

    # B2 - the chip row.
    expected = ["All · 31", "Bathroom · 8", "Bedroom · 10",
                "Dining Room · 2", "Kitchen · 6", "Living Room · 8",
                "Office · 2"]
    h.check("B2 chip row labels and counts",
            sorted(_chip_texts(panel)) == sorted(expected),
            detail="got %r" % (_chip_texts(panel),))

    # B4 - filtering.
    clicked = _click_chip(panel, "Bathroom · 8")
    h.process_events(100)
    h.check("B4 Bathroom chip filters to 8 parts",
            clicked and len(_grid_names(panel)) == 8,
            detail="clicked=%r count=%d" % (clicked,
                                            len(_grid_names(panel))))
    clicked = _click_chip(panel, "All · 31")
    h.process_events(100)
    h.check("B4 All chip restores 31 parts",
            clicked and len(_grid_names(panel)) == 31,
            detail="clicked=%r count=%d" % (clicked,
                                            len(_grid_names(panel))))

    # B5 - multi-valued room facet and no-op click on the selected chip.
    _click_chip(panel, "Bathroom · 8")
    h.process_events(100)
    h.check("B5 Mirror listed under Bathroom",
            "Mirror" in _grid_names(panel),
            detail="got %r" % (_grid_names(panel),))
    _click_chip(panel, "Bedroom · 10")
    h.process_events(100)
    h.check("B5 Mirror listed under Bedroom too",
            "Mirror" in _grid_names(panel),
            detail="got %r" % (_grid_names(panel),))
    panel.grid.setCurrentRow(0)
    before = list(_grid_names(panel))
    _click_chip(panel, "Bedroom · 10")
    h.process_events(100)
    h.check("B5 clicking the selected chip does not rebuild the grid",
            panel.grid.count() == len(before)
            and panel.grid.currentRow() == 0,
            detail="count=%d expected=%d currentRow=%d"
            % (panel.grid.count(), len(before), panel.grid.currentRow()))

    # B6 - debounced search (back on All, so the room filter cannot hide
    # a match from another room).
    _click_chip(panel, "All · 31")
    h.process_events(100)
    _search(panel, "toilet")
    names = _grid_names(panel)
    h.check("B6 search narrows to keyword matches",
            len(names) == 2
            and "Toilet" in names and "Toilet roll holder" in names,
            detail="got %r" % (names,))
    _search(panel, "")

    # B7 - card and detail sidebar.
    _search(panel, "base cabinet")
    panel.grid.setCurrentRow(0)
    h.process_events(300)
    card = panel.grid.itemWidget(panel.grid.item(0))
    pixmap_label = None
    if card is not None:
        pixmap_label = next(
            (lbl for lbl in card.findChildren(QtGui.QLabel)
             if lbl.pixmap() is not None and not lbl.pixmap().isNull()),
            None)
    h.check("B7 card shows name plus a thumbnail image",
            _grid_names(panel)[0] == "Base cabinet"
            and pixmap_label is not None)
    h.check("B7 detail shows name, description and parameter form",
            panel.detailName.text() == "Base cabinet"
            and bool(panel.description.text())
            and "Width" in panel.paramForm._widgets,
            detail="name=%r description=%r widgets=%r"
            % (panel.detailName.text(), panel.description.text()[:20],
               sorted(panel.paramForm._widgets)))
    h.check("B7 no family line on the card or in the sidebar",
            panel.detailFamily.text() == "",
            detail="family=%r" % (panel.detailFamily.text(),))

    _search(panel, "")
    return h.failures()
