# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Panel lifecycle, thumbnail fallback, collection family line, preview
# pane, no-host placement and property checks: Parts B11/B12, C1/C3,
# D5/D6, H1-H3 and U7 of docs/PARTS-LIBRARY-VERIFICATION.md.

import json
import os
import shutil

from archplus.freecad_tests import _harness as h

import FreeCAD
from PySide import QtGui
from FreeCAD import Vector

from archplus.tools.partslib import gui as partslib_gui
from archplus.tools.partslib import object as partslib_object
from archplus.tools.partslib import placement as partslib_placement

_LIBRARY = partslib_object.LIBRARY_DIR


def _facets():
    return partslib_object.libraryIndex()["facets"]


def _entry(part_id):
    return partslib_object.resolveEntry(part_id)[0]


def _make(part_id, placement=None):
    return partslib_object.makePart(_entry(part_id), _facets(),
                                    placement=placement)


def _search(panel, text):
    panel.search.setText(text)
    h.process_events(400)


def _select(panel, query):
    _search(panel, query)
    panel.grid.setCurrentRow(0)
    h.process_events(400)


def _grid_names(panel):
    names = []
    for i in range(panel.grid.count()):
        card = panel.grid.itemWidget(panel.grid.item(i))
        texts = []
        if card is not None:
            texts = [label.text()
                     for label in card.findChildren(QtGui.QLabel)
                     if label.text()]
        names.append(texts[0] if texts else "")
    return names


def _click_chip(panel, text):
    for i in range(panel.chipLayout.count()):
        widget = panel.chipLayout.itemAt(i).widget()
        if widget is not None and widget.text() == text:
            widget.click()
            return True
    return False


def _mdi_tab_count():
    window = FreeCAD.Gui.getMainWindow() if hasattr(FreeCAD, "Gui") else None
    mdi = window.findChild(QtGui.QMdiArea) if window is not None else None
    if mdi is None:
        return 0
    return sum(1 for sub in mdi.subWindowList()
               if sub.windowTitle() == "ArchPlus Library")


def run():
    # Start from a known panel state: previous scripts leave search text
    # and a chip selection behind, which would silently filter every later
    # grid check.
    panel = partslib_gui.showPanel()
    h.process_events(300)
    panel.search.setText("")
    _click_chip(panel, "All · 31")
    h.process_events(300)

    # --- H1: close the tab; the toolbar path brings it back. Closing an
    # MDI subwindow HIDES it (it does not destroy the panel), so the tab
    # re-appears with its state preserved - the documented "fresh panel"
    # narrative in gui.py does not match this behaviour.
    _click_chip(panel, "Bathroom · 8")
    h.process_events(100)
    sub = panel.parentWidget()
    sub.close()
    h.process_events(300)
    back = partslib_gui.showPanel()
    h.process_events(300)
    h.check("H1 closing the tab and reopening yields a working tab",
            _mdi_tab_count() == 1 and back is panel
            and len(_grid_names(back)) == 8
            and panel.parentWidget() is not None
            and panel.parentWidget().isVisible(),
            detail="tabs=%d same=%r count=%d visible=%r"
            % (_mdi_tab_count(), back is panel, len(_grid_names(back)),
               panel.parentWidget() is not None
               and panel.parentWidget().isVisible()))

    cycles_ok = True
    for _ in range(3):
        partslib_gui.showPanel().parentWidget().close()
        h.process_events(300)
        partslib_gui.showPanel()
        h.process_events(300)
        cycles_ok = cycles_ok and _mdi_tab_count() == 1
    h.check("H3 each close/reopen cycle yields exactly one tab",
            cycles_ok, detail="tabs=%d" % _mdi_tab_count())
    _click_chip(partslib_gui.showPanel(), "All · 31")
    h.process_events(100)

    # --- H2: the tab survives a document switch, keeping its state.
    panel = partslib_gui.showPanel()
    _click_chip(panel, "Bathroom · 8")
    h.process_events(100)
    _search(panel, "toilet")
    panel.grid.setCurrentRow(0)
    h.process_events(300)
    doc2 = h.fresh_doc("ArchPlusVerifySwitch")
    sub = panel.parentWidget()
    mdi = sub.mdiArea()
    mdi.setActiveSubWindow(sub)
    h.process_events(200)
    h.check("H2 tab survives a document switch with state intact",
            sub.isVisible()
            and len(_grid_names(panel)) == 2
            and panel.search.text() == "toilet"
            and panel.grid.currentRow() == 0,
            detail="active=%r count=%d search=%r row=%d"
            % (sub.isVisible(), len(_grid_names(panel)),
               panel.search.text(), panel.grid.currentRow()))
    _search(panel, "")
    _click_chip(panel, "All · 31")
    h.process_events(100)
    FreeCAD.closeDocument(doc2.Name)
    h.process_events(200)

    # --- B11: on-demand thumbnail fallback.
    thumb = os.path.join(_LIBRARY, "basic", "base-cabinet", "thumbnail.jpg")
    backup = thumb + ".bak"
    try:
        shutil.copyfile(thumb, backup)
        os.remove(thumb)
        partslib_gui.showPanel()
        h.process_events(2000)  # the missing thumbnail is rendered once
        regenerated = os.path.exists(thumb)
        mtime1 = os.path.getmtime(thumb) if regenerated else 0.0
        partslib_gui.showPanel()  # reopen: served from the file, no re-render
        h.process_events(500)
        mtime2 = os.path.getmtime(thumb)
        h.check("B11 thumbnail regenerated on demand and reused on reopen",
                regenerated and mtime1 == mtime2,
                detail="regenerated=%r mtime=%r/%r"
                % (regenerated, mtime1, mtime2))
    finally:
        if os.path.exists(thumb):
            os.remove(thumb)
        shutil.move(backup, thumb)

    # --- B12: collection.json family line.
    collection = os.path.join(_LIBRARY, "basic", "collection.json")
    backup = collection + ".bak"
    try:
        shutil.copyfile(collection, backup)
        data = json.load(open(collection, encoding="utf-8"))
        data["label"] = "Demo Collection"
        json.dump(data, open(collection, "w", encoding="utf-8"))
        panel = partslib_gui.showPanel()  # refresh() rescans the library
        h.process_events(300)
        _select(panel, "base cabinet")
        sidebar_line = panel.detailFamily.text()
        _search(panel, "Demo Collection")
        family_matches = len(_grid_names(panel)) == 31
        card_line = any(
            "Demo Collection" in
            [label.text() for label in card.findChildren(QtGui.QLabel)]
            for i in range(panel.grid.count())
            for card in [panel.grid.itemWidget(panel.grid.item(i))]
            if card is not None)
        h.check("B12 family label appears on card, sidebar and in search",
                sidebar_line == "Demo Collection"
                and family_matches and card_line,
                detail="sidebar=%r matches=%r card=%r"
                % (sidebar_line, family_matches, card_line))
    finally:
        if os.path.exists(collection):
            os.remove(collection)
        shutil.move(backup, collection)
        partslib_gui.showPanel()  # restore the label-less state
        h.process_events(300)

    # --- C1: the detail pane shows a still preview image.
    panel = partslib_gui.showPanel()
    _select(panel, "base cabinet")
    preview = panel.preview
    pixmap_ok = (isinstance(preview, QtGui.QLabel)
                 and preview.pixmap() is not None
                 and not preview.pixmap().isNull())
    h.check("C1 detail shows a still preview image",
            pixmap_ok,
            detail="widget=%r" % type(preview).__name__)

    # --- D5: the tab stays open across placements.
    panel = partslib_gui.showPanel()
    _click_chip(panel, "All · 31")
    _search(panel, "")
    h.fresh_doc()
    _make("basic/base-cabinet")
    partslib_gui.showPanel()
    h.process_events(200)
    h.check("D5 the tab stays open across placements",
            _mdi_tab_count() == 1 and len(_grid_names(panel)) == 31,
            detail="tabs=%d count=%d"
            % (_mdi_tab_count(), len(_grid_names(panel))))

    # --- D6: placement with no face under the cursor still places.
    doc = h.fresh_doc()
    placement = partslib_placement.partPlacement(
        Vector(0, 0, 1000), None, "floor", 0)
    obj = _make("basic/base-cabinet", placement=placement)
    h.check("D6 no-host placement still places",
            obj is not None and len(doc.Objects) == 1,
            detail="objects=%d" % len(doc.Objects))

    # --- U7: the placed part's Width stays an ordinary PropertyLength.
    obj = _make("basic/base-cabinet")
    h.check("U7 placed Width is an App::PropertyLength",
            obj.getTypeIdOfProperty("Width") == "App::PropertyLength",
            detail="type=%r" % obj.getTypeIdOfProperty("Width"))

    return h.failures()
