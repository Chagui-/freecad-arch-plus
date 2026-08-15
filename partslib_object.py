# SPDX-License-Identifier: LGPL-2.1-or-later
#
# LibraryPart - one document object per inserted library part.
#
# Subclasses ArchComponent.Component so the object inherits Description, Tag,
# Material, IfcType, IfcData and IfcProperties, and so IfcProperties
# round-trips into IFC property sets on export.
#
# CACHE SEMANTICS: the cached shape needs no property of its own, because
# FreeCAD already persists obj.Shape in the FCStd. When the library cannot be
# resolved, execute() returns WITHOUT touching obj.Shape, so the saved geometry
# stays on screen for anyone opening the file without ArchPlus. Nothing
# rebuilds on document open - a corrected library part must never silently
# alter drawings that have already been issued. Rebuilding is the explicit
# "Reload from library" command.

import os
import sys

import FreeCAD
import ArchComponent

_DIR = os.path.dirname(__file__)
if _DIR not in sys.path:
    sys.path.append(_DIR)

import partslib_geometry
import partslib_index
import partslib_manifest

PROP_PART_ID = "PartId"
PROP_VARIANT = "Variant"
_PARAM_GROUP = "Part"
_PARAMS_GROUP = "Parameters"

# Manifest param `type` -> FreeCAD property type. An unlisted manifest type
# is refused, not guessed: a mistyped dimension property would be worse than
# an absent one, since the absent case still falls back to the manifest
# default in build_shape() and builds correctly.
_PARAM_PROPERTY_TYPES = {
    "Length": "App::PropertyLength",
    "Angle": "App::PropertyAngle",
    "Integer": "App::PropertyInteger",
    "Bool": "App::PropertyBool",
    "String": "App::PropertyString",
    "Enum": "App::PropertyEnumeration",
}

LIBRARY_DIR = os.path.join(_DIR, "library")

# Spec §9: browsing must never re-parse the whole library. The scanned index
# is cached outside the add-on folder so a git checkout never clobbers it.
CACHE_PATH = os.path.join(
    FreeCAD.getUserAppDataDir(), "ArchPlus", "index.json")

_INDEX = None


def libraryIndex(force=False):
    """The scanned library index, memoised for the session.

    `force` drops the in-memory copy but still honours the on-disk cache -
    the cache is mtime-validated against every manifest and against
    facets.json, so only a real change to the library costs a full rescan."""
    global _INDEX
    if _INDEX is not None and not force:
        return _INDEX

    cached = partslib_index.load_cache(CACHE_PATH)
    if cached and partslib_index.is_cache_valid(cached, LIBRARY_DIR):
        cached.setdefault("errors", [])
        cached.setdefault("warnings", [])
        _INDEX = cached
        return _INDEX

    _INDEX = partslib_index.scan(LIBRARY_DIR)
    for message in _INDEX["errors"]:
        FreeCAD.Console.PrintError("ArchPlus library: %s\n" % message)
    try:
        partslib_index.save_cache(_INDEX, CACHE_PATH)
    except Exception as exc:
        # A cache we cannot write is a slow library, not a broken one.
        FreeCAD.Console.PrintWarning(
            "ArchPlus: cannot write the library cache: %s\n" % (exc,))
    return _INDEX


def resolveEntry(partId):
    """Find an indexed entry by id. Returns (entry, facets) or None."""
    index = libraryIndex()
    for entry in index["entries"]:
        if entry["id"] == partId:
            return entry, index["facets"]
    return None


class _LibraryPart(ArchComponent.Component):
    """A single library part instance."""

    def __init__(self, obj):
        ArchComponent.Component.__init__(self, obj)
        # Guards _declareParamProperties()'s own property assignments - see
        # that method for what reentrancy it is protecting against.
        self._reseeding = False
        self._paramNames = set()
        self.setPartProperties(obj)
        obj.Proxy = self
        self.Type = "LibraryPart"

    def setPartProperties(self, obj, resolved=None, reseed=False):
        """Ensure PartId/Variant exist, and one property per declared param.

        Safe to call repeatedly, including from onDocumentRestored: with
        `reseed` False (the default) an already-existing param property's
        value is never touched, only newly-declared params are added - a
        hand-edited dimension must survive a save/reload. `reseed=True` is
        the one path that deliberately overwrites every declared param back
        to its manifest default; see onChanged()'s Variant branch."""
        if PROP_PART_ID not in obj.PropertiesList:
            obj.addProperty("App::PropertyString", PROP_PART_ID, _PARAM_GROUP,
                            "Library part this object was created from",
                            locked=True)
        # Reapplied on every call (including from onDocumentRestored) in case
        # FreeCAD does not round-trip the ReadOnly editor bit through the
        # FCStd - belt and braces alongside locked=True above.
        obj.setEditorMode(PROP_PART_ID, 1)  # read-only
        if PROP_VARIANT not in obj.PropertiesList:
            obj.addProperty("App::PropertyEnumeration", PROP_VARIANT,
                            _PARAM_GROUP, "Which variant of the part to build")
        self._declareParamProperties(obj, resolved, reseed)

    def _declareParamProperties(self, obj, resolved, reseed):
        """Add/seed the "Parameters" group properties for `resolved`.

        This is a genuinely reachable reentrancy hazard, unlike the
        `_rebuilding` flag removed from this file in an earlier review (that
        one guarded a path nothing could reach): assigning each property
        below fires onChanged(obj, name) for that property, and onChanged()
        reacts to a Parameter property change by rebuilding - so seeding N
        properties would otherwise trigger N rebuilds from inside this one
        call, on top of whatever rebuild the caller does afterwards. Setting
        self._reseeding for the duration collapses all of that down to the
        single rebuild the caller (onChanged's Variant branch, or makePart)
        performs explicitly once this returns.
        """
        specs = partslib_manifest.param_specs(resolved) if resolved else {}
        names = set()
        self._reseeding = True
        try:
            for name, spec in specs.items():
                prop_type = _PARAM_PROPERTY_TYPES.get(spec.get("type"))
                if prop_type is None:
                    FreeCAD.Console.PrintWarning(
                        "ArchPlus: part %r declares param %r with unknown "
                        "type %r; skipping\n"
                        % (getattr(obj, PROP_PART_ID, ""), name,
                           spec.get("type")))
                    continue
                is_new = name not in obj.PropertiesList
                if is_new:
                    obj.addProperty(prop_type, name, _PARAMS_GROUP,
                                    "Part parameter %r" % (name,))
                if (is_new or reseed) and prop_type == "App::PropertyEnumeration":
                    # An Enumeration property needs its allowed values set
                    # before a current value is accepted. The manifest
                    # schema has no declared "options" list for Enum params
                    # yet, so fall back to a single-choice enum of just the
                    # default rather than guess at a wider vocabulary.
                    options = spec.get("options") or (
                        [spec.get("default")]
                        if spec.get("default") is not None else [])
                    setattr(obj, name, options)
                if is_new or reseed:
                    setattr(obj, name, spec.get("default"))
                names.add(name)
        finally:
            self._reseeding = False
        self._paramNames = names

    def _resolveCurrent(self, obj):
        """(resolved manifest) for obj's current PartId/Variant, or None.

        Only used to know which Parameter properties to declare or reseed -
        never touches obj.Shape, so it is safe to call from
        onDocumentRestored, where nothing must rebuild."""
        partId = getattr(obj, PROP_PART_ID, "")
        if not partId:
            return None
        found = resolveEntry(partId)
        if found is None:
            return None
        entry, _facets = found
        try:
            manifest = partslib_manifest.load_manifest(entry["path"])
            return partslib_manifest.resolve_variant(
                manifest, getattr(obj, PROP_VARIANT, None)
                or partslib_manifest.DEFAULT_VARIANT_LABEL)
        except Exception:
            return None

    def onDocumentRestored(self, obj):
        ArchComponent.Component.onDocumentRestored(self, obj)
        self._reseeding = False
        self.setPartProperties(obj, self._resolveCurrent(obj))
        self.Type = "LibraryPart"

    def execute(self, obj):
        """Rebuild from the library, or leave the cached shape alone."""
        partId = getattr(obj, PROP_PART_ID, "")
        if not partId:
            return

        found = resolveEntry(partId)
        if found is None:
            FreeCAD.Console.PrintWarning(
                "ArchPlus: part %r is not in the library; keeping the cached "
                "shape for %s\n" % (partId, obj.Label))
            return  # DO NOT touch obj.Shape - this is the cache

        entry, _facets = found
        try:
            manifest = partslib_manifest.load_manifest(entry["path"])
            resolved = partslib_manifest.resolve_variant(
                manifest, getattr(obj, PROP_VARIANT, None)
                or partslib_manifest.DEFAULT_VARIANT_LABEL)
            overrides = {name: getattr(obj, name)
                        for name in getattr(self, "_paramNames", ())
                        if name in obj.PropertiesList}
            shape = partslib_geometry.build_shape(
                resolved, entry["dir"], overrides)
        except Exception as exc:
            FreeCAD.Console.PrintError(
                "ArchPlus: cannot rebuild %s: %s\n" % (obj.Label, exc))
            return  # cache again

        placement = obj.Placement
        obj.Shape = shape
        obj.Placement = placement

    def onChanged(self, obj, prop):
        """Switching Variant re-seeds Parameters and rebuilds in place;
        changing a Parameter property rebuilds too.

        FreeCAD fires onChanged() for every property as it restores a
        document, including Variant - so this must not react while
        "Restore" is in obj.State, or opening a file would silently rebuild
        from whatever the library currently contains, exactly what this
        module's cache semantics forbid. Same guard as doorsplus_object.py
        and windowsplus_object.py.

        Variants are different products (design spec Sec 5.3): switching
        Variant deliberately discards any hand-edited Parameter values by
        re-seeding them from the new variant's declared defaults, rather
        than risk an object whose dimensions match no catalogue entry."""
        if prop == PROP_VARIANT:
            if "Restore" not in obj.State:
                self.setPartProperties(
                    obj, self._resolveCurrent(obj), reseed=True)
                self.execute(obj)
        elif prop in getattr(self, "_paramNames", ()):
            if ("Restore" not in obj.State
                    and not getattr(self, "_reseeding", False)):
                self.execute(obj)
        else:
            ArchComponent.Component.onChanged(self, obj, prop)


class _ViewProviderLibraryPart(ArchComponent.ViewProviderComponent):

    def __init__(self, vobj):
        ArchComponent.ViewProviderComponent.__init__(self, vobj)
        vobj.Proxy = self

    def getIcon(self):
        return os.path.join(_DIR, "Resources", "icons", "PartsLibrary.svg")

    def setEdit(self, vobj, mode):
        return False

    def setupContextMenu(self, vobj, menu):
        from PySide import QtGui

        action = QtGui.QAction("Reload from library", menu)
        action.triggered.connect(lambda: reloadFromLibrary(vobj.Object))
        menu.addAction(action)


def _applyMetadata(obj, resolved, facets):
    """Write description, IfcType and IfcProperties onto the object."""
    obj.Description = resolved.get("description", "")
    ifcType = partslib_manifest.resolve_ifc_type(resolved, facets)
    try:
        obj.IfcType = ifcType
    except Exception:
        FreeCAD.Console.PrintWarning(
            "ArchPlus: IfcType %r not accepted; leaving the default\n"
            % (ifcType,))
    properties = resolved.get("ifcProperties") or {}
    if properties:
        obj.IfcProperties = dict(properties)


def makePart(entry, facets, variant=None, placement=None):
    """Create one library part object in the active document."""
    doc = FreeCAD.ActiveDocument
    if doc is None:
        raise RuntimeError("no active document")

    manifest = partslib_manifest.load_manifest(entry["path"])
    labels = partslib_manifest.variant_labels(manifest)
    variant = variant or labels[0]
    resolved = partslib_manifest.resolve_variant(manifest, variant)

    obj = doc.addObject("Part::FeaturePython", "LibraryPart")
    _LibraryPart(obj)
    if FreeCAD.GuiUp:
        _ViewProviderLibraryPart(obj.ViewObject)

    obj.Label = manifest.get("name", entry["id"])
    setattr(obj, PROP_PART_ID, entry["id"])
    setattr(obj, PROP_VARIANT, labels)
    setattr(obj, PROP_VARIANT, variant)
    # Explicit, not left to the onChanged(Variant) cascade above: whether
    # that cascade actually fires here depends on FreeCAD's PropertyEnumeration
    # "did the value really change" semantics when `variant` is the list's
    # first entry, which this file has no reliable way to assert headlessly.
    # setPartProperties()/_declareParamProperties() are idempotent under
    # reseed=True, so calling this explicitly is redundant-but-safe if the
    # cascade already ran, and load-bearing if it did not.
    obj.Proxy.setPartProperties(obj, resolved, reseed=True)
    _applyMetadata(obj, resolved, facets)

    if placement is not None:
        obj.Placement = placement

    obj.Proxy.execute(obj)
    return obj


def reloadFromLibrary(obj):
    """Force one object to rebuild from the current library contents.

    This is deliberately explicit. Automatic rebuilding on document open would
    let a corrected library part silently change drawings already issued."""
    libraryIndex(force=True)
    partId = getattr(obj, PROP_PART_ID, "")
    found = resolveEntry(partId)
    if found is None:
        FreeCAD.Console.PrintError(
            "ArchPlus: part %r is not in the library\n" % (partId,))
        return False

    entry, facets = found
    try:
        manifest = partslib_manifest.load_manifest(entry["path"])
        labels = partslib_manifest.variant_labels(manifest)

        # Decide the label explicitly rather than relying on how a
        # PropertyEnumeration reads back after being reassigned with the old
        # selection missing from the new list - that readback is
        # FreeCAD-version-dependent and can otherwise feed an unknown label
        # into resolve_variant(), raising KeyError out of this Qt slot.
        current = getattr(obj, PROP_VARIANT, None)
        if current in labels:
            variant = current
        else:
            variant = labels[0]
            if current:
                FreeCAD.Console.PrintWarning(
                    "ArchPlus: variant %r of %s no longer exists; using %r "
                    "instead\n" % (current, obj.Label, variant))

        # Reassigning PROP_VARIANT fires onChanged(Variant) even when
        # `variant` is unchanged from before, which re-seeds Parameter
        # properties to their (possibly library-corrected) defaults - the
        # same discard-on-reload behaviour this command already applies to
        # metadata and geometry, just extended to dimensions now that they
        # are properties too.
        setattr(obj, PROP_VARIANT, labels)
        setattr(obj, PROP_VARIANT, variant)

        resolved = partslib_manifest.resolve_variant(manifest, variant)
        _applyMetadata(obj, resolved, facets)
    except Exception as exc:
        FreeCAD.Console.PrintError(
            "ArchPlus: cannot reload %s: %s\n" % (obj.Label, exc))
        return False

    obj.Proxy.execute(obj)
    obj.Document.recompute()
    return True
