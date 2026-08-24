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

import FreeCAD
import ArchComponent

_DIR = os.path.dirname(__file__)     # archplus/tools/partslib/ itself

from . import geometry as partslib_geometry
from . import index as partslib_index
from . import manifest as partslib_manifest

PROP_PART_ID = "PartId"
PROP_AUTO_PARAMS = "AutoParams"
_PARAM_GROUP = "Part"
_PARAMS_GROUP = "Parameters"

# Manifest param `type` -> FreeCAD property type. An unlisted manifest type
# is refused, not guessed: a mistyped dimension property would be worse than
# an absent one, since the absent case still falls back to the manifest
# default in build_shape() and builds correctly.
#
# "Choice" maps to an enumeration whose allowed values come from the param's
# own `options` map. That is why it is expressible now and was not before:
# the schema previously had no way to declare them.
_PARAM_PROPERTY_TYPES = {
    "Length": "App::PropertyLength",
    "Angle": "App::PropertyAngle",
    "Integer": "App::PropertyInteger",
    "Bool": "App::PropertyBool",
    "String": "App::PropertyString",
    "Choice": "App::PropertyEnumeration",
}

# What a reseed resets an "auto" param property to when it discards a
# pinned value: the type's own empty value, not the stale number the user
# typed. execute()'s write-back immediately replaces it with the real
# derived value for measured params; for the rest an honest 0 beats a
# confident 3 that contradicts the geometry. Choice has no empty value,
# which is one more reason manifest validation refuses "auto" there.
_EMPTY_PARAM_VALUES = {
    "Length": 0,
    "Angle": 0,
    "Integer": 0,
    "Bool": False,
    "String": "",
}


def _paramValue(obj, name, spec):
    """One param property's value, as a builder expects it.

    A Choice property holds the option LABEL, because that is what the user
    reads in the property editor. Map it back to the stable value the
    manifest and the builder use - by label first, then by position. The
    positional fallback is for a library edited on disk mid-session."""
    value = getattr(obj, name)
    options = partslib_manifest.choice_options(spec)
    if not options:
        return value
    for option_value, option in options.items():
        if ((option or {}).get("label") or option_value) == value:
            return option_value
    try:
        labels = list(obj.getEnumerationsOfProperty(name))
        return list(options)[labels.index(value)]
    except Exception:
        FreeCAD.Console.PrintWarning(
            "ArchPlus: param %r has unknown choice value %r; using %r\n"
            % (name, value, list(options)[0]))
        return list(options)[0]

# Defined in geometry.py, which needs it for the builder containment guard
# and must stay importable without FreeCAD. Re-exported here because
# gui.py reads partslib_object.LIBRARY_DIR.
LIBRARY_DIR = partslib_geometry.LIBRARY_DIR

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
        self._resetMap = {}
        self.setPartProperties(obj)
        obj.Proxy = self
        self.Type = "LibraryPart"

    def setPartProperties(self, obj, resolved=None, reseed=False):
        """Ensure PartId and one property per declared param.

        Safe to call repeatedly, including from onDocumentRestored: with
        `reseed` False (the default) an already-existing param property's
        value is never touched, only newly-declared params are added - a
        hand-edited dimension must survive a save/reload. `reseed=True` is the
        one path that deliberately overwrites every declared param back
        to its manifest default."""
        if PROP_PART_ID not in obj.PropertiesList:
            obj.addProperty("App::PropertyString", PROP_PART_ID, _PARAM_GROUP,
                            "Library part this object was created from",
                            locked=True)
        # Reapplied on every call (including from onDocumentRestored) in case
        # FreeCAD does not round-trip the ReadOnly editor bit through the
        # FCStd - belt and braces alongside locked=True above.
        obj.setEditorMode(PROP_PART_ID, 1)  # read-only
        if PROP_AUTO_PARAMS not in obj.PropertiesList:
            obj.addProperty("App::PropertyStringList", PROP_AUTO_PARAMS,
                            _PARAM_GROUP,
                            "Params still derived by the builder",
                            locked=True)
        obj.setEditorMode(PROP_AUTO_PARAMS, 2)  # hidden
        # A document written before params replaced variants still carries a
        # Variant enumeration. Removing a document property is destructive,
        # so it stays - but it must stop looking like a live control.
        if "Variant" in obj.PropertiesList:
            obj.setEditorMode("Variant", 2)  # hidden
        self._declareParamProperties(obj, resolved, reseed)

    def _declareParamProperties(self, obj, resolved, reseed):
        """Add/seed the "Parameters" group properties for `resolved`, and
        show/hide that group's properties to match what `resolved` declares.

        This is a genuinely reachable reentrancy hazard, unlike the
        `_rebuilding` flag removed from this file in an earlier review (that
        one guarded a path nothing could reach): assigning each property
        below fires onChanged(obj, name) for that property, and onChanged()
        reacts to a Parameter property change by rebuilding - so seeding N
        properties would otherwise trigger N rebuilds from inside this one
        call, on top of whatever rebuild the caller does afterwards. Setting
        self._reseeding for the duration collapses all of that down to the
        single rebuild the caller (onChanged's parameter path, or makePart)
        performs explicitly once this returns.
        """
        specs = partslib_manifest.param_specs(resolved) if resolved else {}
        # Computed up front, from `specs` alone, rather than accumulated
        # during the loop below: onChanged()'s reentrancy guard consults
        # self._paramNames, and if it were only assigned after the loop
        # finished, the guard would consult the OLD set while a property is
        # being declared for the very first time and miss it. Assigning it
        # before the loop also means _paramNames stays consistent with what
        # this call intends to declare even if the loop below raised partway
        # through, instead of being left stale from some earlier call.
        names = {name for name, spec in specs.items()
                  if _PARAM_PROPERTY_TYPES.get(spec.get("type")) is not None}
        self._paramNames = names
        # Driver param -> the "auto" params its edit returns to derived.
        # Consulted by onChanged(), whose driver branch re-adds the targets
        # to AutoParams before rebuilding, so editing a placed hob's burner
        # count re-sizes it even at a hand-typed width.
        self._resetMap = {}
        for name, spec in specs.items():
            if name not in names:
                continue
            targets = [target for target
                       in partslib_manifest.reset_targets(spec)
                       if target in names]
            if targets:
                self._resetMap[name] = targets
        self._reseeding = True
        try:
            existing_auto = list(getattr(obj, PROP_AUTO_PARAMS, ()) or [])
            new_auto = []
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
                carried = None
                if not is_new and obj.getTypeIdOfProperty(name) != prop_type:
                    # A param whose declared type changed (the gas hob's
                    # BurnerCount moved from Integer to Choice) leaves a
                    # property the new spec cannot drive. Removing a
                    # document property is destructive, so this only ever
                    # happens when the type actually changed; the old value
                    # is carried across when it maps into the new spec and
                    # reseeded to the manifest default when it does not.
                    carried = partslib_manifest.migrated_value(
                        getattr(obj, name), spec)
                    obj.removeProperty(name)
                    is_new = True
                if is_new:
                    obj.addProperty(prop_type, name, _PARAMS_GROUP,
                                    "Part parameter %r" % (name,))
                options = partslib_manifest.choice_options(spec)
                if options:
                    # An enumeration needs its allowed values before its
                    # value, or the assignment below has nothing to match.
                    setattr(obj, name,
                            [(opt or {}).get("label") or value
                             for value, opt in options.items()])
                if is_new or reseed:
                    default = spec.get("default")
                    if carried is not None and not reseed:
                        default = ((options.get(carried) or {}).get("label")
                                   or carried)
                    elif options:
                        default = ((options.get(default) or {}).get("label")
                                   or default)
                    if default == partslib_manifest.AUTO:
                        # Nothing meaningful to seed: execute() writes the
                        # builder's answer in once the shape exists.
                        default = None
                        if is_new:
                            new_auto.append(name)
                        if reseed:
                            # Reload discards the pin, but without this the
                            # property goes on DISPLAYING the pinned number
                            # while AutoParams already says the value is
                            # derived again - a cabinet showing Doors: 3
                            # over two door leaves (verification F3).
                            empty = _EMPTY_PARAM_VALUES.get(spec.get("type"))
                            if empty is not None:
                                setattr(obj, name, empty)
                    if default is not None:
                        setattr(obj, name, default)
            if reseed:
                setattr(obj, PROP_AUTO_PARAMS,
                        [name for name, spec in specs.items()
                         if name in names
                         and spec.get("default") == partslib_manifest.AUTO])
            elif new_auto:
                # A param the library gained since the document was saved
                # must start out DERIVED, or the builder receives 0.
                setattr(obj, PROP_AUTO_PARAMS,
                        existing_auto + [name for name in new_auto
                                         if name not in existing_auto])
        finally:
            self._reseeding = False
        # Non-destructive fix for a part switch that declares fewer
        # params than before: the now-undeclared property is never removed
        # (removing a document property is destructive and can break older
        # files), but it must stop being an editable field that silently
        # does nothing. Hide anything in the "Parameters" group `resolved`
        # does not declare, and un-hide what it does - idempotent, and using
        # getGroupOfProperty() so this only ever touches properties in that
        # group, never PartId or anything inherited from
        # ArchComponent.
        for existing in obj.PropertiesList:
            if obj.getGroupOfProperty(existing) == _PARAMS_GROUP:
                obj.setEditorMode(existing, 0 if existing in names else 2)

    def _applyParamOverrides(self, obj, manifest, overrides):
        """Write the browser panel's param values onto a seeded object.

        makePart() seeds every property to its manifest default first;
        this then applies the values the panel collected, so the placed
        object is the part the preview showed rather than a silent reset
        to the defaults.

        A Choice override arrives as the option's STABLE VALUE - that is
        what ParamForm.values() reads back via itemData - while the
        property stores the LABEL, so it is mapped through the same
        choice_options() lookup _declareParamProperties performs when
        seeding a default. Every name applied is removed from AutoParams:
        a value the user typed is pinned by definition, the rule everywhere
        else in this module. Names the manifest does not declare, names
        with no property, and None values are skipped.

        Assigning a param property fires onChanged, which rebuilds - the
        same reentrancy _declareParamProperties guards against, guarded
        the same way (the caller performs the one real rebuild)."""
        overrides = overrides or {}
        if not overrides:
            return
        specs = partslib_manifest.param_specs(manifest)
        auto = list(getattr(obj, PROP_AUTO_PARAMS, ()) or [])
        self._reseeding = True
        try:
            for name, value in overrides.items():
                spec = specs.get(name)
                if spec is None or value is None \
                        or name not in obj.PropertiesList:
                    continue
                options = partslib_manifest.choice_options(spec)
                if options and value in options:
                    value = ((options.get(value) or {}).get("label")
                             or value)
                setattr(obj, name, value)
                if name in auto:
                    auto.remove(name)
            setattr(obj, PROP_AUTO_PARAMS, auto)
        finally:
            self._reseeding = False

    def _resolveCurrent(self, obj):
        """The manifest for obj's current PartId, or None.

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
            return manifest
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
            specs = partslib_manifest.param_specs(manifest)
            auto = set(getattr(obj, PROP_AUTO_PARAMS, ()) or ())
            overrides = {}
            for name in getattr(self, "_paramNames", ()):
                if name in obj.PropertiesList and name not in auto:
                    overrides[name] = _paramValue(obj, name, specs.get(name))
            shape = partslib_geometry.build_shape(
                manifest, entry["dir"], overrides)
        except Exception as exc:
            FreeCAD.Console.PrintError(
                "ArchPlus: cannot rebuild %s: %s\n" % (obj.Label, exc))
            return  # cache again

        placement = obj.Placement
        obj.Shape = shape
        obj.Placement = placement

        # An "auto" param has no seeded value, so the editor would otherwise
        # show a meaningless zero. The built shape is the only thing that
        # knows what the builder actually derived, so its measurements are
        # what get written back - which covers Width/Depth/Height, the
        # dimensions users read. Assigning these fires onChanged() for each,
        # the same reentrancy _declareParamProperties() guards against, and
        # guarded the same way.
        if auto:
            try:
                measured = partslib_geometry.measure(shape)
                self._reseeding = True
                try:
                    for name in auto:
                        if name in measured and name in obj.PropertiesList:
                            setattr(obj, name, measured[name])
                finally:
                    self._reseeding = False
            except Exception as exc:
                FreeCAD.Console.PrintWarning(
                    "ArchPlus: cannot write derived params for %s: %s\n"
                    % (obj.Label, exc))

    def onChanged(self, obj, prop):
        """Changing a Parameter property rebuilds.

        FreeCAD fires onChanged() for every property as it restores a
        document, so this must not react while "Restore" is in obj.State, or
        opening a file would silently rebuild from whatever the library
        currently contains, exactly what this module's cache semantics forbid.
        """
        if prop in getattr(self, "_paramNames", ()):
            if ("Restore" not in obj.State
                    and not getattr(self, "_reseeding", False)):
                auto = list(getattr(obj, PROP_AUTO_PARAMS, ()) or ())
                changed = False
                if prop in auto:
                    # Editing a derived field is what pins it.
                    auto.remove(prop)
                    changed = True
                # Editing a driver param discards the pins its manifest
                # names: a hob re-sized to 5 burners must not keep the
                # width the user typed for 4. "Reload from library" stays
                # the manual way back to derived for everything else.
                for target in getattr(self, "_resetMap", {}).get(prop, ()):
                    if target not in auto:
                        auto.append(target)
                        changed = True
                if changed:
                    setattr(obj, PROP_AUTO_PARAMS, auto)
                self.execute(obj)
        else:
            ArchComponent.Component.onChanged(self, obj, prop)


class _ViewProviderLibraryPart(ArchComponent.ViewProviderComponent):

    def __init__(self, vobj):
        ArchComponent.ViewProviderComponent.__init__(self, vobj)
        vobj.Proxy = self

    def getIcon(self):
        return os.path.join(_DIR, "resources", "icons", "PartsLibrary.svg")

    def setEdit(self, vobj, mode):
        # No edit-mode task for a library part (mode 0 = Default). Other
        # modes must NOT be refused: FreeCAD 1.1 runs its transform tool as
        # edit mode ViewProvider::Transform, and a blanket False here is
        # what made the gizmo never appear. None says "not implemented",
        # which hands the mode back to the C++ ViewProviderDragger.
        if mode == 0:
            return False
        return None

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


def makePart(entry, facets, placement=None, overrides=None):
    """Create one library part object in the active document.

    `overrides` is {name: value} for the parameters the browser panel's
    user actually set (ParamForm.values(), which omits fields still
    marked derived). Applied on top of the manifest-default seeding, so
    what lands in the 3D view is what the preview rebuilt - and so a
    Choice that carries a placement (e.g. a television's Mounting) cannot
    disagree with the placement computed from the same value."""
    doc = FreeCAD.ActiveDocument
    if doc is None:
        raise RuntimeError("no active document")

    manifest = partslib_manifest.load_manifest(entry["path"])

    obj = doc.addObject("Part::FeaturePython", "LibraryPart")
    _LibraryPart(obj)
    if FreeCAD.GuiUp:
        _ViewProviderLibraryPart(obj.ViewObject)

    obj.Label = manifest.get("name", entry["id"])
    setattr(obj, PROP_PART_ID, entry["id"])
    obj.Proxy.setPartProperties(obj, manifest, reseed=True)
    obj.Proxy._applyParamOverrides(obj, manifest, overrides)
    _applyMetadata(obj, manifest, facets)

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
        # Reload means "take the library's current truth", so it discards
        # hand-edited Parameter values and returns every derived param to
        # derived. reseed=True is what does both.
        obj.Proxy.setPartProperties(obj, manifest, reseed=True)
        _applyMetadata(obj, manifest, facets)
    except Exception as exc:
        FreeCAD.Console.PrintError(
            "ArchPlus: cannot reload %s: %s\n" % (obj.Label, exc))
        return False

    obj.Proxy.execute(obj)
    obj.Document.recompute()
    return True
