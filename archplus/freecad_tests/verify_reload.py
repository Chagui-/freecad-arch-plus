# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Reload, save/reopen and missing-id checks: Parts F1-F5, G1/G2 and K1 of
# docs/PARTS-LIBRARY-VERIFICATION.md. Every check restores the library
# files it touches, even on failure.

import json
import os
import shutil
import tempfile

from archplus.freecad_tests import _harness as h

import FreeCAD

from archplus.tools.partslib import object as partslib_object

_LIBRARY = partslib_object.LIBRARY_DIR


def _facets():
    return partslib_object.libraryIndex()["facets"]


def _entry(part_id):
    return partslib_object.resolveEntry(part_id)[0]


def _make(part_id, placement=None):
    return partslib_object.makePart(_entry(part_id), _facets(),
                                    placement=placement)


def _part_json(part_id):
    return os.path.join(_LIBRARY, part_id, "part.json")


def _edit_manifest(part_id, mutate):
    """Apply `mutate` to a part.json dict, returning an undo function."""
    path = _part_json(part_id)
    backup = path + ".bak"
    shutil.copyfile(path, backup)
    data = json.load(open(path, encoding="utf-8"))
    mutate(data)
    json.dump(data, open(path, "w", encoding="utf-8"))

    def undo():
        os.remove(path)
        shutil.move(backup, path)

    return undo


def _with_folder_renamed(part_id, func):
    """Run `func` while a part folder is renamed out of the library."""
    folder = os.path.join(_LIBRARY, part_id)
    renamed = folder + "-hidden"
    os.rename(folder, renamed)
    try:
        return func()
    finally:
        os.rename(renamed, folder)


def run():
    # --- F1: reload on a fresh part runs without error.
    doc = h.fresh_doc()
    cabinet = _make("basic/base-cabinet")
    reloaded = partslib_object.reloadFromLibrary(cabinet)
    h.check("F1 Reload from library succeeds", bool(reloaded),
            detail="returned=%r" % (reloaded,))

    # --- F2: opening a document never silently rebuilds from the manifest.
    doc_path = os.path.join(tempfile.gettempdir(), "archplus_verify_f2.FCStd")
    if os.path.exists(doc_path):
        os.remove(doc_path)
    cabinet.Width = 800
    doc.recompute()
    volume_saved = cabinet.Shape.Volume
    doc.saveAs(doc_path)
    undo = _edit_manifest("basic/base-cabinet",
                          lambda d: d["params"].update(
                              {"Height": {"type": "Length",
                                          "default": 1000}}))
    try:
        FreeCAD.closeDocument(doc.Name)
        reopened = FreeCAD.openDocument(doc_path)
        obj = reopened.Objects[0]
        h.check("F2 reopening keeps the saved geometry (no silent rebuild)",
                obj.Width.Value == 800 and obj.Height.Value == 900,
                detail="Width=%.0f Height=%.0f"
                % (obj.Width.Value, obj.Height.Value))
        partslib_object.reloadFromLibrary(obj)
        h.check("F2 Reload then adopts the edited manifest",
                obj.Height.Value == 1000 and obj.Width.Value == 600,
                detail="Width=%.0f Height=%.0f (reseeded)"
                % (obj.Width.Value, obj.Height.Value))
        FreeCAD.closeDocument(reopened.Name)
    finally:
        undo()
        partslib_object.libraryIndex(force=True)

    # --- F3: reload discards a pinned derived value.
    doc = h.fresh_doc()
    chest = _make("basic/chest-of-drawers")
    chest.Height = 700
    doc.recompute()
    pinned = "Height" not in (chest.AutoParams or [])
    partslib_object.reloadFromLibrary(chest)
    h.check("F3 reload discards the pin and restores the derived Height",
            pinned and "Height" in (chest.AutoParams or []),
            detail="pinned=%r AutoParams=%r" % (pinned, chest.AutoParams))

    # --- F4: editing the driver discards pinned sizes.
    doc = h.fresh_doc()
    hob = _make("basic/gas-hob")
    hob.Width = 900
    hob.Depth = 600
    doc.recompute()
    five = next(v for v in hob.getEnumerationsOfProperty("BurnerCount")
                if "5" in v)
    hob.BurnerCount = five
    doc.recompute()
    h.check("F4 BurnerCount 5 re-derives Width and Depth",
            "Width" in (hob.AutoParams or [])
            and abs(hob.Width.Value - 750.0) < 1.0
            and abs(hob.Depth.Value - 520.0) < 1.0,
            detail="W=%.3f D=%.3f Auto=%r"
            % (hob.Width.Value, hob.Depth.Value, hob.AutoParams))

    # --- F5/K1: a part missing from the library fails safely.
    doc = h.fresh_doc()
    toilet = _make("basic/toilet")
    volume = toilet.Shape.Volume
    result = _with_folder_renamed(
        "basic/toilet",
        lambda: partslib_object.reloadFromLibrary(toilet))
    partslib_object.libraryIndex(force=True)
    h.check("F5 reload with a missing part fails safely",
            result is False and abs(toilet.Shape.Volume - volume) < 1e-6,
            detail="returned=%r volume=%.0f/%.0f"
            % (result, toilet.Shape.Volume, volume))

    # --- G1: save/reopen keeps the saved dimensions, not the manifest's.
    doc_path = os.path.join(tempfile.gettempdir(), "archplus_verify_g1.FCStd")
    if os.path.exists(doc_path):
        os.remove(doc_path)
    doc = h.fresh_doc()
    cabinet = _make("basic/base-cabinet")
    cabinet.Width = 700
    doc.recompute()
    doc.saveAs(doc_path)
    FreeCAD.closeDocument(doc.Name)
    reopened = FreeCAD.openDocument(doc_path)
    obj = reopened.Objects[0]
    h.check("G1 reopening keeps the saved dimensions",
            obj.Width.Value == 700 and obj.Shape.isValid(),
            detail="Width=%.0f valid=%r"
            % (obj.Width.Value, obj.Shape.isValid()))
    FreeCAD.closeDocument(reopened.Name)

    # --- G2: deleting a part leaves the tree clean.
    doc = h.fresh_doc()
    cabinet = _make("basic/base-cabinet")
    doc.removeObject(cabinet.Name)
    h.check("G2 deleting a placed part leaves the tree clean",
            len(doc.Objects) == 0,
            detail="objects=%d" % len(doc.Objects))

    return h.failures()
