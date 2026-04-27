from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase


THEME_VARIANTS = {
    "mist": {
        "bg": "#FAF7F1",
        "panel": "rgba(255,255,255,0.92)",
        "card": "rgba(255,255,255,0.95)",
        "accent": "#7E98A8",
        "wood": "#9B785D",
        "text": "#33424B",
        "muted": "#6E7C84",
        "line": "rgba(126,152,168,0.12)",
        "nav": "rgba(243,239,232,0.75)",
        "shadow": "rgba(0,0,0,0.06)",
    },
    "cream": {
        "bg": "#FAFAF8",
        "panel": "rgba(255,252,247,0.92)",
        "card": "rgba(255,255,255,0.96)",
        "accent": "#D4B896",
        "wood": "#AE8665",
        "text": "#2D2D2D",
        "muted": "#746E67",
        "line": "rgba(212,184,150,0.14)",
        "nav": "rgba(248,242,235,0.76)",
        "shadow": "rgba(0,0,0,0.05)",
    },
    "blue": {
        "bg": "#F0F7FF",
        "panel": "rgba(255,255,255,0.92)",
        "card": "rgba(255,255,255,0.96)",
        "accent": "#7BA7CC",
        "wood": "#8A745F",
        "text": "#2F3437",
        "muted": "#6D7881",
        "line": "rgba(123,167,204,0.14)",
        "nav": "rgba(235,243,250,0.76)",
        "shadow": "rgba(0,0,0,0.05)",
    },
}


def setup_app_fonts(app):
    font_path = Path(__file__).resolve().parents[2] / "resources" / "fonts" / "SourceHanSansSC-Regular.otf"
    family = ""
    if font_path.exists():
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            family = families[0]
    font = QFont()
    font.setFamilies([family or "Microsoft YaHei UI", "Yu Gothic UI", "Segoe UI", "Sans Serif"])
    font.setPointSize(10)
    app.setFont(font)


def load_stylesheet(mode: str, accent_theme: str) -> str:
    base = Path(__file__).resolve().parent
    qss_path = base / ("dark.qss" if mode == "dark" else "light.qss")
    theme = THEME_VARIANTS.get(accent_theme, THEME_VARIANTS["mist"])
    template = qss_path.read_text(encoding="utf-8")
    return template.format(**theme)
