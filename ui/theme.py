"""
The look of the dashboard: a dark space-flight-deck. Change a colour here and the whole window follows.
Colours are written as #RRGGBB.
"""

from pathlib import Path

# deep space
BG = "#03060F"            # window background
SIDEBAR = "#070C1A"       # left menu
PANEL = "#0B1226"         # cards
PANEL_HOVER = "#122044"
BORDER = "#17315C"        # thin card outlines
BORDER_GLOW = "#2A5C9A"

# text
TEXT = "#E6F4FF"
MUTED = "#7C93B8"

# accents (cyan like a HUD, with a warm orange for contrast)
ACCENT = "#3DD9FF"
ACCENT_HOVER = "#7BE6FF"
ACCENT_DIM = "#1B6F8C"
ORANGE = "#FF9A3D"
VIOLET = "#9B7BFF"
GOOD = "#3DFFB0"
WARN = "#FFB84D"
BAD = "#FF5C7A"

# the frame round her picture changes with her mood
MOOD_COLOURS = {"Infatuated": "#FF4FB3", "Upset": "#C8203F", "Close": "#FF7AC8", "Friendly": "#3DFFB0", "Neutral": "#3DD9FF",
                "Sarcastic": "#FFB84D", "Frustrated": "#FF5C7A"}

FONT = "Segoe UI"         # body text: a clean font every Windows PC has
HEAD_FONT = "Bahnschrift"  # headings: a squarer "instrument panel" font on Windows 10 and 11 (Windows picks another if missing)
TITLE_SIZE = 22
HEADING_SIZE = 15
BODY_SIZE = 13
SMALL_SIZE = 11

WINDOW_SIZE = "1280x820"
MIN_SIZE = (1000, 640)
BANNER_HEIGHT = 92
SIDEBAR_WIDTH = 214
STAR_COUNT = 110

# small symbols on the menu buttons (all in Windows' standard symbol font)
ICONS = {"home": "\u25C8", "voice": "\u25C9", "listening": "\u25CE", "controls": "\u25A3", "chat": "\u2726",
         "combat": "\u271B", "exploration": "\u25CD", "exobiology": "\u2740", "mining": "\u2692", "trading": "\u21C4",
         "antixeno": "\u2620", "navigation": "\u25B2", "updates": "\u21E9", "bookmarks": "\u25C6", "personality": "\u25CF",
         "game": "\u25A7"}

# one line along the bottom of the window, changed each time the dashboard opens
QUOTES = ["The best view comes after the hardest jump.", "Same sky. Different horizon.", "Fly safe, Commander.",
          "Every system has a story.", "The black is never empty.", "Fuel up. Look up. Jump.", "Somewhere out there is the next rock worth mining."]
TAGLINE = "FLY FURTHER   \u2022   KNOW MORE   \u2022   NEVER ALONE"

# the small symbol in front of each kind of event in the Recent events list
KIND_ICONS = {"Journal": "\u25A4", "Navigation": "\u25B2", "System": "\u25CE", "Voice": "\u25C9", "Ship": "\u25ED",
              "Exploration": "\u25CD", "Combat": "\u271B", "Exobiology": "\u2740", "Mining": "\u2692", "Trading": "\u21C4",
              "Anti-Xeno": "\u2620"}

# her picture (the old single picture is still used if there are no mood pictures)
AVATAR_FILE = Path(__file__).resolve().parent / "assets" / "avatar.png"
PORTRAIT_BOX = (300, 380)
