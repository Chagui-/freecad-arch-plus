# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


def build(params, assets, ctx):
    """A glass panel for a shower or over a bath: a pane in a slim profile,
    with a floor-to-top support post at the fixed edge.

    Params: Width, Height, GlassThickness, ProfileWidth (mm).

    Placed as a floor-hosted part rather than wall-hosted: a bath screen
    stands on the tub rim and a walk-in panel stands on the tray, and in
    both cases the thing you position is the foot of the post, not a fixing
    height up the wall."""
    width = float(params.get("Width", 900))
    height = float(params.get("Height", 1900))
    glass = float(params.get("GlassThickness", 8))
    profile = float(params.get("ProfileWidth", 30))

    glass = min(glass, profile)
    pane_width = max(width - profile, 10.0)

    # The post is at the wall end (+Y is the wall side for a floor part
    # standing against one), the pane runs out from it.
    post = sh.rounded_box(profile, profile, height, radius=3)
    post = sh.place(post, 0, 0, 0)

    pane = sh.rounded_box(pane_width, glass, height - profile * 0.3, radius=2)
    pane = sh.place(pane, profile, (profile - glass) / 2.0, 0)

    # A short bottom rail stiffens the free edge and gives the pane
    # something to read against at the floor.
    rail = sh.rounded_box(pane_width, profile * 0.8, profile * 0.8, radius=3)
    rail = sh.place(rail, profile, (profile - profile * 0.8) / 2.0, 0)

    return sh.fuse_all([post, pane, rail])
