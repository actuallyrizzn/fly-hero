from __future__ import annotations

import numpy as np

from flyhero.node_viz import LEG_LABELS, layout_points, render_firing


def test_layout_points_count_and_bounds():
    pts = layout_points(100, width=400, height=600)
    assert pts.shape == (100, 2)
    assert pts[:, 0].min() >= 0
    assert pts[:, 1].min() >= 0
    assert pts[:, 0].max() <= 400
    assert pts[:, 1].max() <= 600


def test_render_firing_highlights_legs():
    state = np.zeros(200, dtype=np.float32)
    legs = (10, 20, 30, 40, 50, 60)
    state[list(legs)] = [0.1, 0.5, 0.9, 0.2, 0.0, 1.0]
    drive = [1, 0, 1, 0, 0, 1]
    img = render_firing(state, legs=legs, width=320, height=480, drive=drive)
    assert img.size == (320, 480)
    assert img.mode == "RGB"
    # Driven leg colors should appear somewhere (green / yellow / white-ish).
    arr = np.asarray(img)
    assert (arr[:, :, 1] > 180).any()  # green channel hot
    assert LEG_LABELS[0] == "G"
