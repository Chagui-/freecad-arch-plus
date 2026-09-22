# SPDX-License-Identifier: LGPL-2.1-or-later
#
# The library's colours, and the roles that map onto them.
#
# A part is one fused solid, so its pieces are not visible in the shape: the
# only thing that says "this face is the door, that one the handle" is the
# role its builder gave the piece the face came from (shapes.fuse_all). This
# module is the other half - the colours those roles are painted with.
#
# TWO FAMILIES, because furniture is two materials. Wood for the casework -
# a cabinet's box, its worktop, its doors - and a grey scale for everything
# that is not wood: hardware, upholstery, glazing, and the moulded bodies of
# sanitaryware and appliances. A part declares which by the roles it uses,
# which is why there is a `shell` role: a bathtub, a sink bowl, a cistern, a
# shower tray, a fridge and a bin are all one moulded mass, and calling them
# `carcass` would have made them wood.
#
# THE STEPS ARE FAR APART ON PURPOSE. Three per family - 80% white, mid grey
# and 80% black, and the same three lightnesses in wood - because the first
# pass's greys were too close to tell apart, and a part has to read as its
# pieces rather than as one mass with faint shading. At most three colours on
# any one part, which the palette makes structural: the roles a part can use
# without contradicting itself never reach four.
#
# Colours are RGBA, and alpha is opacity: the glazing is tinted blue and
# see-through, everything else is solid.
#
# The roles stay semantic (what a piece IS) and the colours are this
# module's business, so moving a role from one colour to another is a
# one-line change here rather than a retag of every part that has one.
#
# This module must stay importable without FreeCAD: it is plain data, and
# the partslib tests read it headlessly.

# 80% white, mid grey, 80% black. Alpha is opacity: 1.0 is solid, and the
# glazing is the only role that is not.
WHITE = (0.80, 0.80, 0.80, 1.0)
GREY = (0.50, 0.50, 0.50, 1.0)
BLACK = (0.20, 0.20, 0.20, 1.0)
GLASS = (0.62, 0.78, 0.92, 0.35)

# The same three steps in wood: light oak, walnut, wenge.
LIGHT_WOOD = (0.80, 0.66, 0.46, 1.0)
MID_WOOD = (0.52, 0.39, 0.26, 1.0)
DARK_WOOD = (0.24, 0.16, 0.10, 1.0)

# role -> RGBA colour. These keys are the vocabulary a builder may use, and
# fuse_all() rejects anything else, so a typo is a build error rather than a
# part that quietly comes out the wrong colour.
ROLE_COLOUR = {
    "top": LIGHT_WOOD,      # the surface you use: worktops, table tops, shelves
    "carcass": MID_WOOD,    # the wood mass: bodies, case panels, plinths, frames
    "front": DARK_WOOD,     # an applied wooden face: doors, drawer fronts, a plinth
    "soft": WHITE,          # upholstery and bedding: cushions, mattresses, pillows
    "shell": WHITE,         # a moulded body: a tub, a bowl, a fridge, a bin
    "glass": GLASS,         # glazing, tinted and see-through: a screen, a mirror
    "fitting": BLACK,       # hardware: handles, pulls, taps, burners, feet
}

ROLES = tuple(sorted(ROLE_COLOUR))

# What a piece is when its builder does not say - a part built as one mass.
DEFAULT_ROLE = "carcass"


def colour_for(role):
    """The colour a role is painted with.

    An unknown role is a builder bug, not a fallback: raising here means a
    misspelled role stops the build with the name in the message, instead of
    painting the part in the default colour and leaving someone to wonder why
    its doors look like its carcass."""
    try:
        return ROLE_COLOUR[role]
    except KeyError:
        raise ValueError("unknown part role %r; expected one of %s"
                         % (role, ", ".join(ROLES)))


def colours_used(roles):
    """The distinct colours a part's faces use.

    What the cap is checked with: a part with three or fewer is the rule, and
    a part with more means a role was added without thinking about how many
    colours it puts on one object."""
    return sorted({colour_for(role) for role in roles if role})
