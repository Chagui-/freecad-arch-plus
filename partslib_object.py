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
        self.setPartProperties(obj)
        obj.Proxy = self
        self.Type = "LibraryPart"

    def setPartProperties(self, obj):
        if PROP_PART_ID not in obj.PropertiesList:
            obj.addProperty("App::PropertyString", PROP_PART_ID, _PARAM_GROUP,
                            "Library part this object was created from")
            obj.setEditorMode(PROP_PART_ID, 1)  # read-only
        if PROP_VARIANT not in obj.PropertiesList:
            obj.addProperty("App::PropertyEnumeration", PROP_VARIANT,
                            _PARAM_GROUP, "Which variant of the part to build")

    def onDocumentRestored(self, obj):
        ArchComponent.Component.onDocumentRestored(self, obj)
        self.setPartProperties(obj)
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
            shape = partslib_geometry.build_shape(resolved, entry["dir"])
        except Exception as exc:
            FreeCAD.Console.PrintError(
                "ArchPlus: cannot rebuild %s: %s\n" % (obj.Label, exc))
            return  # cache again

        placement = obj.Placement
        obj.Shape = shape
        obj.Placement = placement


class _ViewProviderLibraryPart(ArchComponent.ViewProviderComponent):

    def __init__(self, vobj):
        ArchComponent.ViewProviderComponent.__init__(self, vobj)
        vobj.Proxy = self

    def getIcon(self):
        return os.path.join(_DIR, "Resources", "icons", "PartsLibrary.svg")

    def setEdit(self, vobj, mode):
        return False


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
    _applyMetadata(obj, resolved, facets)

    if placement is not None:
        obj.Placement = placement

    obj.Proxy.execute(obj)
    return obj
