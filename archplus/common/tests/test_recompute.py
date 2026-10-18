# SPDX-License-Identifier: LGPL-2.1-or-later
#
# The panels' live path asks the document to recompute a list of objects
# rather than the whole document, which is what keeps a wall or opening edit
# from re-running the drawings. A build whose Document.recompute takes no
# list must fall back to the document-wide form instead of leaving the edit
# unbuilt.

import FreeCAD

from archplus.common.recompute import recompute_only


class _Doc:
    """A document that records what it was asked to recompute."""

    def __init__(self, targeted=True):
        self.calls = []
        self.targeted = targeted

    def recompute(self, objects=None):
        if objects is not None and not self.targeted:
            raise TypeError("recompute() takes no arguments")
        self.calls.append(objects)


def test_the_object_list_reaches_the_document(monkeypatch):
    doc = _Doc()
    monkeypatch.setattr(FreeCAD, "ActiveDocument", doc)
    a, b = object(), object()

    recompute_only([a, b])

    assert doc.calls == [[a, b]]


def test_a_build_without_a_targeted_recompute_falls_back(monkeypatch):
    """FreeCAD before 1.1 only takes the document-wide form: the edit must
    still be built, so the fallback runs rather than the call failing."""
    doc = _Doc(targeted=False)
    monkeypatch.setattr(FreeCAD, "ActiveDocument", doc)

    recompute_only([object()])

    assert doc.calls == [None]


def test_no_document_is_a_no_op(monkeypatch):
    """A live handler can fire while the last document is closing."""
    monkeypatch.setattr(FreeCAD, "ActiveDocument", None)

    recompute_only([object()])
