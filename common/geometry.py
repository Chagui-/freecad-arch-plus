# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Sketch-building helpers shared by the ArchPlus geometry builders.
#
# Kept separate from common/widgets.py on purpose: this module pulls in
# Part and Sketcher, so it must only ever be imported from inside a function
# (never at gui.py module scope), or BIM workbench init would drag those in.

import Part
import Sketcher


def add_rect(sketch, p1, p2, p3, p4):
    """Add a fully-constrained rectangle to `sketch`."""
    idx = sketch.GeometryCount
    sketch.addGeometry(Part.LineSegment(p1, p2))
    sketch.addGeometry(Part.LineSegment(p2, p3))
    sketch.addGeometry(Part.LineSegment(p3, p4))
    sketch.addGeometry(Part.LineSegment(p4, p1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", idx, 2, idx + 1, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", idx + 1, 2, idx + 2, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", idx + 2, 2, idx + 3, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", idx + 3, 2, idx, 1))
    sketch.addConstraint(Sketcher.Constraint("Horizontal", idx))
    sketch.addConstraint(Sketcher.Constraint("Horizontal", idx + 2))
    sketch.addConstraint(Sketcher.Constraint("Vertical", idx + 1))
    sketch.addConstraint(Sketcher.Constraint("Vertical", idx + 3))


def add_frame(sketch, outer_p1, outer_p2, outer_p3, outer_p4,
              inner_p1, inner_p2, inner_p3, inner_p4):
    """Add outer+inner rectangles forming a frame."""
    add_rect(sketch, outer_p1, outer_p2, outer_p3, outer_p4)
    add_rect(sketch, inner_p1, inner_p2, inner_p3, inner_p4)
