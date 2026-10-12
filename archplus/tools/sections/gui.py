# SPDX-License-Identifier: LGPL-2.1-or-later
#
# The section view command: convert a Draft Shape2DView into an ArchPlus one.
#
# One view at a time, on purpose - a converted view renumbers its drawing, so
# the dimensions measuring it need re-picking once. Converting one, comparing
# it against an unconverted one, and only then converting the rest is the
# migration the design doc describes.
#
# A view whose settings the ArchPlus view does not reproduce is refused, by
# name, rather than converted: silently dropping HiddenLines or a non-Solid
# projection mode would draw something the user did not ask for.

import FreeCAD

# Draft's Shape2DView settings this view does not reproduce, with the value
# that means "not used" (None = the property is absent on that object).
UNSUPPORTED = (
    ("ProjectionMode", "Solid"),
    ("HiddenLines", False),
    ("Tessellation", False),
    # Draft defaults InPlace to True, and it only means anything in the
    # Cutlines/Cutfaces modes, which the ProjectionMode entry above refuses -
    # so True is this table's "not used". False here would refuse every
    # default Draft view.
    ("InPlace", True),
    ("Clip", False),
    ("Depth", 0.0),
)


def unsupported_settings(view):
    """The settings that stop this view being converted, as readable names."""
    found = []
    for name, neutral in UNSUPPORTED:
        if not hasattr(view, name):
            continue
        value = getattr(view, name)
        if name == "Depth":
            value = value.Value
        if value != neutral:
            found.append("%s = %s" % (name, value))
    points = list(getattr(view, "ExclusionPoints", None) or [])
    if points:
        found.append("ExclusionPoints")
    return found


def convertSectionView(view):
    """Replace a Draft Shape2DView with an ArchPlus section view.

    Copies the base, the placement and the settings the new view reproduces,
    re-points every TechDraw view reading the old one, and only then removes
    it - so a failure part-way leaves the document usable.
    """
    from archplus.tools.sections import object as sections_object

    if not _is_draft_view(view):
        FreeCAD.Console.PrintWarning(
            "ArchPlus: '%s' is not a Draft section view\n" % view.Label)
        return False
    if not _is_section_plane(view.Base):
        FreeCAD.Console.PrintWarning(
            "ArchPlus: '%s' is not on a section plane; not converted\n"
            % view.Label)
        return False
    found = unsupported_settings(view)
    if found:
        FreeCAD.Console.PrintWarning(
            "ArchPlus: '%s' uses %s, which an ArchPlus section view does not "
            "reproduce; not converted\n" % (view.Label, ", ".join(found)))
        return False

    doc = view.Document
    doc.openTransaction("Convert to ArchPlus section view")
    try:
        new = sections_object.makeSectionView(doc, base=view.Base)
        label = view.Label  # captured: `view` is dead after removeObject
        # Captured too, and applied after the build below: a view frozen
        # before it ever drew would otherwise come out blank *and* frozen,
        # where the Draft view it replaces keeps the drawing it was frozen
        # with.
        auto_update = getattr(view, "AutoUpdate", True)
        new.Placement = view.Placement
        _copy_settings(view, new)
        if not _repoint_sources(doc, view, new):
            raise RuntimeError("a TechDraw view could not be re-pointed")
        doc.removeObject(view.Name)
        # Only now: while the old view still held the label, FreeCAD would
        # have uniquified this one to "ToConvert001", and the suffix survives
        # the removal - so the converted view would stop reading as the view
        # it replaced.
        new.Label = label
    except Exception as exc:
        doc.abortTransaction()
        FreeCAD.Console.PrintError(
            "ArchPlus: could not convert '%s': %s\n" % (view.Label, exc))
        return False
    doc.commitTransaction()
    doc.recompute()
    if not auto_update:
        # After the recompute on purpose: the new view has to draw once, or
        # freezing it would leave it blank.
        new.AutoUpdate = auto_update
    return True


def _is_draft_view(view):
    proxy = getattr(view, "Proxy", None)
    return type(proxy).__name__ == "Shape2DView"


def _is_section_plane(base):
    """True when `base` is the kind of plane this view knows how to gather.

    Draft's Shape2DView also accepts a building part or an IFC annotation as
    its base, and gathers those differently (the level's Group, a synthetic
    cut plane). This view reproduces the section plane case only, so any
    other base is refused rather than converted into a blank drawing.
    """
    import Draft

    return base is not None and Draft.getType(base) == "SectionPlane"


def _copy_settings(view, new):
    # AutoUpdate is deliberately absent: the caller applies it after the
    # recompute, because a view frozen before it drew would come out blank.
    for name in ("FuseArch", "OnlySolids", "VisibleOnly"):
        if hasattr(view, name):
            setattr(new, name, getattr(view, name))
    if hasattr(view, "ExclusionNames"):
        new.ExclusionNames = list(view.ExclusionNames or [])


def _repoint_sources(doc, old, new):
    """Point every TechDraw view that read `old` at `new` instead."""
    for obj in doc.Objects:
        source = getattr(obj, "Source", None)
        if not source:
            continue
        if not any(item is old for item in source):
            continue
        try:
            obj.Source = [new if item is old else item for item in source]
        except Exception:
            return False
    return True


class ConvertSectionViewCommand:
    def GetResources(self):
        import os

        return {"Pixmap": os.path.join(os.path.dirname(__file__),
                                       "resources", "icons", "SectionView.svg"),
                "MenuText": "Convert section view",
                "ToolTip": "Draw library parts as their plan outline in the "
                           "selected Draft section view"}

    def IsActive(self):
        return bool(_selected_views())

    def Activated(self):
        for view in _selected_views():
            convertSectionView(view)


def _selected_views():
    import FreeCADGui

    return [sel.Object for sel in FreeCADGui.Selection.getSelectionEx()
            if _is_draft_view(sel.Object)]


if FreeCAD.GuiUp:
    import FreeCADGui

    FreeCADGui.addCommand("ArchPlus_SectionView", ConvertSectionViewCommand())
