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
from . import palette as partslib_palette

PROP_PART_ID = "PartId"
PROP_AUTO_PARAMS = "AutoParams"
PROP_MOUNT_OFFSET = "MountOffset"
PROP_MOUNT_HEIGHT = "MountHeight"
_PARAM_GROUP = "Part"
_PARAMS_GROUP = "Parameters"

# "Not placed against a host yet", for MountOffset. A real offset is a
# distance in mm and can be 0 (a part standing on the floor against a wall),
# so 0 cannot be the marker; -1e9 mm cannot be a placement.
_MOUNT_UNSET = -1.0e9

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
        # What the object's Z was last built at, so a mounting height edited
        # after placement can move it by the difference - see
        # _applyMountHeight. Both are hidden: they are bookkeeping, not
        # anything to edit.
        if PROP_MOUNT_OFFSET not in obj.PropertiesList:
            obj.addProperty("App::PropertyFloat", PROP_MOUNT_OFFSET,
                            _PARAM_GROUP,
                            "Mounting offset this object was last built at",
                            locked=True)
            # A new float property holds 0.0, which is a REAL offset, so the
            # marker has to be written explicitly or the first build would
            # read it as "last placed at 0" and apply the offset a second
            # time as a delta.
            setattr(obj, PROP_MOUNT_OFFSET, _MOUNT_UNSET)
        obj.setEditorMode(PROP_MOUNT_OFFSET, 2)  # hidden
        if PROP_MOUNT_HEIGHT not in obj.PropertiesList:
            obj.addProperty("App::PropertyFloat", PROP_MOUNT_HEIGHT,
                            _PARAM_GROUP,
                            "Height the mounting offset was measured to",
                            locked=True)
        obj.setEditorMode(PROP_MOUNT_HEIGHT, 2)  # hidden
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

    def applyEdit(self, obj, manifest, overrides, auto):
        """Write the edit form's state onto a placed part.

        The pinned side goes through _applyParamOverrides(); the derived
        side is what it cannot express - that method only ever removes
        names from AutoParams, while the form's Reset returns fields to
        derived, so AutoParams is set to exactly the names the form still
        shows derived. The caller rebuilds once afterwards."""
        self._applyParamOverrides(obj, manifest, overrides)
        specs = partslib_manifest.param_specs(manifest)
        auto = [name for name in (auto or ())
                if name in specs and name in obj.PropertiesList]
        setattr(obj, PROP_AUTO_PARAMS, auto)

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
            shape, roles = partslib_geometry.build_shape_and_roles(
                manifest, entry["dir"], overrides)
        except Exception as exc:
            FreeCAD.Console.PrintError(
                "ArchPlus: cannot rebuild %s: %s\n" % (obj.Label, exc))
            return  # cache again

        placement = obj.Placement
        obj.Shape = shape
        obj.Placement = placement
        # After the shape, and only on a change. After it, because the view
        # provider refuses a role list whose length does not match the face
        # count, so the shape must never be the newer of the two. Only on a
        # change, because a recompute runs on EVERY part in the document, so
        # writing unconditionally marks every part modified inside whatever
        # undo step is open - and undoing an edit to one part then rolls the
        # others' bookkeeping back with it (the chest of drawers losing its
        # derived Height when the king bed's edit was undone, check L5).
        _storeRoles(obj, roles)

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

        self._applyMountHeight(obj, manifest, overrides)

    def _applyMountHeight(self, obj, manifest, overrides):
        """Move the part when its mounting height changes after placement.

        Placement computes Z once, at insert. Without this, editing a wall
        cabinet's Height above floor would rebuild the shape and leave it
        hanging where it was - a field that does nothing. What is remembered
        is the offset the object's Z was built at (and, where the manifest
        measures the offset to the part's TOP, the height it measured to), so
        an edit shifts it by the difference rather than re-deriving Z from
        the host: a part the user has since dragged stays where they put it
        and moves only by what the edit changed.

        Idempotent by construction - the same params compute a zero delta -
        so every execute() path (param edit, Reload from library, reopening
        the edit panel) can call it."""
        from . import placement as partslib_placement

        params = partslib_manifest.merge_params(manifest, overrides)
        resolved = {"placement": partslib_manifest.resolve_placement(
            manifest, params)}
        host = partslib_placement.host_of(resolved)
        sign = partslib_placement.offset_sign(host)
        if not sign:
            return  # no host surface: nothing holds this part at a height
        offset = partslib_placement.offset_of(resolved)
        top = partslib_placement.offset_to_of(resolved) == "top"
        height = 0.0
        if top:
            try:
                height = partslib_geometry.measure(obj.Shape)["Height"]
            except Exception as exc:
                FreeCAD.Console.PrintWarning(
                    "ArchPlus: cannot measure %s for its mounting height: "
                    "%s\n" % (obj.Label, exc))

        last_offset = getattr(obj, PROP_MOUNT_OFFSET, _MOUNT_UNSET)
        last_height = getattr(obj, PROP_MOUNT_HEIGHT, 0.0)
        if last_offset <= _MOUNT_UNSET + 1.0:
            # A freshly placed object: placement already put it at host +
            # offset, so record that and change nothing. A document written
            # before these properties existed lands here too, and so does
            # not jump.
            setattr(obj, PROP_MOUNT_OFFSET, offset)
            setattr(obj, PROP_MOUNT_HEIGHT, height)
            return

        delta = sign * (offset - last_offset)
        if top:
            # The offset measures to the top, so a taller part hangs lower.
            delta -= height - last_height
        setattr(obj, PROP_MOUNT_OFFSET, offset)
        setattr(obj, PROP_MOUNT_HEIGHT, height)
        if abs(delta) < 1e-9:
            return
        placement = obj.Placement
        placement.Base = FreeCAD.Vector(placement.Base.x, placement.Base.y,
                                        placement.Base.z + delta)
        obj.Placement = placement

    def onChanged(self, obj, prop):
        """Changing a Parameter property rebuilds.

        FreeCAD fires onChanged() for every property as it restores a
        document, so this must not react while "Restore" is in obj.State, or
        opening a file would silently rebuild from whatever the library
        currently contains, exactly what this module's cache semantics forbid.
        """
        if prop == "Material":
            # The greys give way to a Material, so a part has to be repainted
            # the moment one is set or cleared: nothing else would, and the
            # previous appearance would stay on screen. Guarded because the
            # proxy is only there in a GUI session.
            proxy = getattr(getattr(obj, "ViewObject", None), "Proxy", None)
            colorize = getattr(proxy, "colorize", None)
            if colorize is not None:
                colorize(obj)
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


def _storeRoles(obj, roles):
    """Hand the role of each face to the view provider that paints it.

    Deliberately not a property - see _ViewProviderLibraryPart.partRoles for
    what declaring one costs."""
    if not FreeCAD.GuiUp:
        return
    view = getattr(obj, "ViewObject", None)
    proxy = getattr(view, "Proxy", None)
    store = getattr(proxy, "setPartRoles", None)
    if store is not None:
        store(list(roles or []))


def _material_appearance(material):
    """One face's appearance from the Material linked to a part.

    ArchComponent's Material is a LINK to a material object whose own
    `Material` is a dict, and in that dict "DiffuseColor" is a string like
    "(0.5, 0.5, 0.6)" and "Transparency" a whole percentage - so both are
    parsed the way ArchComponent.updateData parses them, not the way a colour
    arrives from ArchCommands (an RGBA tuple, which the doors paint with)."""
    values = material if isinstance(material, dict) else (
        getattr(material, "Material", None) or {})
    colour = (0.8, 0.8, 0.8)
    try:
        channels = [float(channel) for channel in
                    str(values["DiffuseColor"]).strip("()[] ").split(",")]
        colour = tuple(channels[:3])
    except Exception:
        pass
    appearance = FreeCAD.Material()
    appearance.DiffuseColor = colour + (1.0,)
    try:
        appearance.Transparency = float(values.get("Transparency", 0)) / 100.0
    except Exception:
        pass
    return appearance


def _paints_the_same(current, wanted):
    """True when an appearance list already paints exactly `wanted`.

    Only DiffuseColor and Transparency are compared, because they are the
    only things colorize() sets: an appearance that differs anywhere else is
    someone else's, and repainting it would be colorize() fighting the user."""
    if len(current) != len(wanted):
        return False
    for have, want in zip(current, wanted):
        if (have.DiffuseColor != want.DiffuseColor
                or have.Transparency != want.Transparency):
            return False
    return True


class _ViewProviderLibraryPart(ArchComponent.ViewProviderComponent):

    def __init__(self, vobj):
        ArchComponent.ViewProviderComponent.__init__(self, vobj)
        vobj.Proxy = self

    def partRoles(self):
        """The role of each face, from the build that last ran.

        Held on the proxy rather than in a property, which is a hard-won
        detail: declaring any NEW property on a placed part - on the object
        or on its view - breaks FreeCAD's undo/redo of that object's OTHER
        properties, because the declaration is recorded inside the creation
        transaction and replaying it stops the rest of the restore. It showed
        up as a chest of drawers losing its derived Height when an unrelated
        part's edit was undone (check L5), and it was not the property's type
        or its position that mattered, only its existence.

        Nothing is lost by not persisting the roles: the colours themselves
        live in ShapeAppearance, which saves with the document, and the roles
        are only needed to PAINT - which happens on a rebuild, and a rebuild
        recomputes them."""
        return list(getattr(self, "_roles", ()) or [])

    def setPartRoles(self, roles):
        """Remember one role per face, and repaint with them.

        The repaint is here rather than left to the shape change: the roles
        arrive from the object's rebuild AFTER its shape does, so a part
        painted on the shape event alone would wear the roles of its
        previous build. colorize() compares before it writes, so this does
        not loop."""
        self._roles = list(roles or [])
        self.colorize(self.Object)

    def getIcon(self):
        return os.path.join(_DIR, "resources", "icons", "PartsLibrary.svg")

    def updateData(self, obj, prop):
        # The shape is what the colours are read from, so a rebuild repaints.
        if prop == "Shape":
            self.colorize(obj)
        ArchComponent.ViewProviderComponent.updateData(self, obj, prop)

    def onChanged(self, vobj, prop):
        # Assigning ShapeAppearance in colorize() comes back through here, so
        # colorize() compares before it writes - that comparison is what stops
        # this being a loop, exactly as doors/object.py does it. PartRoles is
        # here because the roles arrive from the object's rebuild AFTER the
        # shape does, so a shape change alone would paint a part with the
        # roles of its previous build.
        if prop == "ShapeAppearance":
            self.colorize(vobj.Object)
        ArchComponent.ViewProviderComponent.onChanged(self, vobj, prop)

    def colorize(self, obj):
        """Paint each face with the colour of the piece it came from.

        The roles are this view object's own PartRoles (see palette.py). A
        face count that does not match means the roles belong to another
        shape - a rebuild is on its way - so the appearance is left alone
        rather than painted from a stale list.

        A Material set on the part wins, and it has to win HERE rather than
        by leaving the appearance alone: a per-face appearance overrides the
        whole-shape colour FreeCAD paints a Material with, so a part left
        painted in greys would ignore the material its owner had set. A role
        this build of the palette does not know falls back to the default
        rather than raising, because a hand-edited file must still draw."""
        shape = getattr(obj, "Shape", None)
        if shape is None or not shape.Faces:
            return

        material = getattr(obj, "Material", None)
        if material:
            wanted = [_material_appearance(material)] * len(shape.Faces)
        else:
            roles = self.partRoles()
            if not roles or len(roles) != len(shape.Faces):
                return
            fallback = partslib_palette.ROLE_COLOUR[partslib_palette.DEFAULT_ROLE]
            wanted = []
            for role in roles:
                red, green, blue, alpha = partslib_palette.ROLE_COLOUR.get(
                    role, fallback)
                appearance = FreeCAD.Material()
                appearance.DiffuseColor = (red, green, blue, 1.0)
                # Alpha is opacity, and FreeCAD stores its inverse - the same
                # reading doors/object.py gives a glass panel.
                appearance.Transparency = 1.0 - alpha
                wanted.append(appearance)

        if _paints_the_same(obj.ViewObject.ShapeAppearance, wanted):
            return
        obj.ViewObject.ShapeAppearance = wanted

    def setEdit(self, vobj, mode):
        # Mode 0 (Default) opens the library panel's edit page - FreeCAD
        # itself must NOT enter edit mode, so the opener runs and False is
        # returned, exactly as doors/gui.py documents. Other modes must
        # NOT be refused: FreeCAD 1.1 runs its transform tool as edit mode
        # ViewProvider::Transform, and a blanket False here is what made
        # the gizmo never appear. None says "not implemented", which hands
        # the mode back to the C++ ViewProviderDragger.
        if mode == 0:
            editLibraryPart(vobj.Object)
            return False
        return None

    def doubleClicked(self, vobj):
        # The same opener as setEdit: every entry point - double-click,
        # Edit menu, context menu - lands on the one edit page.
        editLibraryPart(vobj.Object)
        return True

    def setupContextMenu(self, vobj, menu):
        from PySide import QtGui

        editAction = QtGui.QAction("Edit in Parts Library", menu)
        editAction.triggered.connect(
            lambda: editLibraryPart(vobj.Object))
        menu.addAction(editAction)

        action = QtGui.QAction("Reload from library", menu)
        action.setToolTip("Rebuild this part and reset its parameters to the "
                          "library's defaults")
        action.triggered.connect(lambda: reloadFromLibrary(vobj.Object))
        menu.addAction(action)

        # The document-wide counterpart: one right-click catches every placed
        # part up after the library's geometry changes, and keeps the
        # dimensions this file's parts carry.
        rebuildAll = QtGui.QAction("Rebuild all parts from library", menu)
        rebuildAll.setToolTip(
            "Rebuild every placed part in this document from the library's "
            "current geometry, keeping each part's own parameter values")
        rebuildAll.triggered.connect(lambda: rebuildAllFromLibrary())
        menu.addAction(rebuildAll)


def isLibraryPart(obj):
    """True when `obj` is a placed library part."""
    try:
        return isinstance(getattr(obj, "Proxy", None), _LibraryPart)
    except Exception:
        return False


def panelValues(obj, specs):
    """(values, auto) for the edit form: every declared param's current
    value - Choice mapped to its stable value - plus which are still
    derived.

    `auto` is what obj.AutoParams declares: the placed object's truth,
    which a save/reload or a hand edit may have moved on from the manifest
    defaults the browser's own form derives from."""
    auto = set(getattr(obj, PROP_AUTO_PARAMS, ()) or ())
    values = {}
    for name in specs:
        if name not in obj.PropertiesList:
            continue
        try:
            values[name] = _paramValue(obj, name, specs.get(name))
        except Exception:
            continue
    return values, auto


def libraryPartsIn(objects):
    """The placed library parts among `objects`, order preserved."""
    return [o for o in (objects or []) if o is not None and isLibraryPart(o)]


def rebuildFromLibrary(objects):
    """Rebuild placed library parts from the library's current contents.

    The bulk counterpart of reloadFromLibrary, and deliberately not the same
    thing: reloadFromLibrary reseeds every Parameter from the manifest - "take
    the library's truth" - while this keeps each object's own values and only
    re-runs the build. That is the path you want when the library's *geometry*
    changed (a helper now eases edges differently, say) and the parts already
    in a file should catch up without losing hand-edited dimensions.

    It calls each part's execute() directly, which is what reloadFromLibrary
    does too: a parameter *edit* reaches the build through onChanged, but
    touching an object and recomputing does not re-run execute here (measured:
    Touched -> Up-to-date with no execute call), so nothing here waits on the
    dependency graph to notice. Returns how many were rebuilt; the caller owns
    the recompute that carries the new shapes on to whatever depends on
    them."""
    rebuilt = 0
    for obj in libraryPartsIn(objects):
        execute = getattr(getattr(obj, "Proxy", None), "execute", None)
        if execute is None:
            continue
        try:
            execute(obj)
        except Exception:
            continue
        rebuilt += 1
    return rebuilt


def editLibraryPart(obj):
    """Open the library panel to edit a placed part.

    The one entry every route - double-click, Edit menu, the context-menu
    entry - funnels into, so editing always means the same dialog."""
    from . import gui as partslib_gui

    partslib_gui.editPart(obj)


def rebuildAllFromLibrary():
    """Rebuild every placed library part in the active document, or the
    selected ones when library parts are selected.

    The document-wide recovery action: after a library update, one call
    catches every placed part up instead of right-clicking each of them."""
    from . import gui as partslib_gui

    return partslib_gui.rebuildPlacedParts()


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
