"""Three-layer design tokens for the Jetson workstation UI."""

from types import MappingProxyType


PRIMITIVES = MappingProxyType(
    {
        "navy_950": "#07131D",
        "navy_900": "#0B1B27",
        "navy_800": "#12263A",
        "navy_700": "#193853",
        "navy_600": "#244A68",
        "neutral_50": "#F4F7FA",
        "neutral_100": "#EDF2F7",
        "neutral_200": "#D7E0EA",
        "neutral_300": "#C4D0DD",
        "neutral_600": "#5E6D82",
        "neutral_700": "#405069",
        "neutral_900": "#142033",
        "white": "#FFFFFF",
        "blue_50": "#E9F3FC",
        "blue_200": "#AFCFEA",
        "blue_600": "#0B70C9",
        "blue_700": "#085EAA",
        "focus": "#58A6FF",
        "teal": "#16B8A6",
        "teal_light": "#DDF5F1",
        "success": "#0F766E",
        "warning": "#9A5B00",
        "warning_light": "#FFF4D6",
        "danger": "#B42318",
        "danger_light": "#FDEBE9",
        "dark_text": "#ECF4F7",
        "dark_muted": "#A9BBC5",
        "dark_border": "#24404E",
        "dark_warning": "#F3C969",
        "dark_warning_bg": "#2B2418",
        "dark_danger": "#FF9C91",
        "dark_danger_bg": "#301B1D",
    }
)


SEMANTIC_LIGHT = MappingProxyType(
    {
        "background": PRIMITIVES["neutral_50"],
        "surface": PRIMITIVES["white"],
        "surface_subtle": PRIMITIVES["neutral_100"],
        "text": PRIMITIVES["neutral_900"],
        "text_muted": PRIMITIVES["neutral_600"],
        "border": PRIMITIVES["neutral_200"],
        "border_strong": PRIMITIVES["neutral_300"],
        "interactive": PRIMITIVES["blue_600"],
        "interactive_hover": PRIMITIVES["blue_700"],
        "interactive_subtle": PRIMITIVES["blue_50"],
        "interactive_border": PRIMITIVES["blue_200"],
        "focus": PRIMITIVES["focus"],
        "operational": PRIMITIVES["teal"],
        "success": PRIMITIVES["success"],
        "success_background": PRIMITIVES["teal_light"],
        "warning": PRIMITIVES["warning"],
        "warning_background": PRIMITIVES["warning_light"],
        "danger": PRIMITIVES["danger"],
        "danger_background": PRIMITIVES["danger_light"],
    }
)


SEMANTIC_DARK = MappingProxyType(
    {
        "background": PRIMITIVES["navy_950"],
        "surface": PRIMITIVES["navy_900"],
        "surface_raised": PRIMITIVES["navy_800"],
        "surface_selected": PRIMITIVES["navy_600"],
        "text": PRIMITIVES["dark_text"],
        "text_muted": PRIMITIVES["dark_muted"],
        "border": PRIMITIVES["dark_border"],
        "interactive": PRIMITIVES["teal"],
        "interactive_hover": "#35D2C0",
        "focus": PRIMITIVES["focus"],
        "success": "#7AECDD",
        "success_background": "#0C2A28",
        "warning": PRIMITIVES["dark_warning"],
        "warning_background": PRIMITIVES["dark_warning_bg"],
        "danger": PRIMITIVES["dark_danger"],
        "danger_background": PRIMITIVES["dark_danger_bg"],
        "viewer_overlay": PRIMITIVES["navy_900"],
        "viewer_raised": PRIMITIVES["navy_800"],
        "viewer_hover": PRIMITIVES["navy_700"],
        "viewer_border": PRIMITIVES["dark_border"],
    }
)


COMPONENT_TOKENS = MappingProxyType(
    {
        "space_1": "4px",
        "space_2": "8px",
        "space_3": "12px",
        "space_4": "16px",
        "space_5": "20px",
        "space_6": "24px",
        "space_8": "32px",
        "radius_sm": "6px",
        "radius_md": "10px",
        "radius_lg": "14px",
        "font_caption": "13px",
        "font_body": "16px",
        "font_section": "19px",
        "font_subtitle": "23px",
        "font_title": "28px",
        "button_height": "40px",
        "button_primary_height": "44px",
        "nav_item_height": "48px",
        "focus_width": "2px",
    }
)


def style_tokens():
    """Return flattened named tokens for QSS template substitution."""

    tokens = dict(COMPONENT_TOKENS)
    tokens.update(
        {"light_" + key: value for key, value in SEMANTIC_LIGHT.items()}
    )
    tokens.update(
        {"dark_" + key: value for key, value in SEMANTIC_DARK.items()}
    )
    return tokens
