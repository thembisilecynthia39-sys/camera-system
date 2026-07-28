"""Behaviour checks for the workstation UI design system."""

import re

from camera_system_app.ui.design_tokens import SEMANTIC_DARK, SEMANTIC_LIGHT
from camera_system_app.ui.theme import application_stylesheet


def _relative_luminance(hex_color):
    channels = [
        int(hex_color[index : index + 2], 16) / 255.0
        for index in (1, 3, 5)
    ]
    linear = [
        value / 12.92
        if value <= 0.04045
        else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first, second):
    light, dark = sorted(
        (_relative_luminance(first), _relative_luminance(second)),
        reverse=True,
    )
    return (light + 0.05) / (dark + 0.05)


def test_semantic_text_pairs_meet_wcag_contrast():
    pairs = (
        (SEMANTIC_LIGHT["text"], SEMANTIC_LIGHT["background"]),
        (SEMANTIC_LIGHT["text_muted"], SEMANTIC_LIGHT["surface"]),
        (SEMANTIC_DARK["text"], SEMANTIC_DARK["background"]),
        (SEMANTIC_DARK["text_muted"], SEMANTIC_DARK["background"]),
    )

    for foreground, background in pairs:
        assert _contrast(foreground, background) >= 4.5


def test_stylesheet_resolves_tokens_and_styles_model_views():
    stylesheet = application_stylesheet()

    assert re.search(r"\{[a-z][a-z0-9_]*\}", stylesheet) is None
    assert "QTableView" in stylesheet
    assert SEMANTIC_LIGHT["interactive"] in stylesheet
    assert SEMANTIC_DARK["background"] in stylesheet
