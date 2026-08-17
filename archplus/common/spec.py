# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Persistence of the ArchPlus creation spec on a FreeCAD object.
#
# The native Window object only stores Width/Height/Frame. The remaining panel
# settings are serialized to JSON in a single hidden string property so the
# panel can be reopened with every field intact. Doors and Windows shared
# byte-identical copies of this before it was extracted here.

import json

SPEC_PROP = "ArchPlusSpec"


def storeSpec(obj, spec):
    """Persist the ArchPlus creation spec on the object as JSON."""
    if obj is None:
        return
    if not hasattr(obj, SPEC_PROP):
        obj.addProperty("App::PropertyString", SPEC_PROP, "ArchPlus",
                        "Serialized ArchPlus settings (internal)")
        try:
            obj.setEditorMode(SPEC_PROP, 2)   # hidden from the property editor
        except Exception:
            pass
    setattr(obj, SPEC_PROP, json.dumps(spec))


def readSpec(obj):
    """Return the stored ArchPlus spec dict, or None if absent/unreadable."""
    raw = getattr(obj, SPEC_PROP, "") or ""
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except Exception:
        return None
    return d if isinstance(d, dict) else None
