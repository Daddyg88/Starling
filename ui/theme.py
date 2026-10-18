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
MOOD_COLOURS = {"Close": "#FF7AC8", "Friendly": "#3DFFB0", "Neutral": "#3DD9FF",
                "Sarcastic": "#FFB84D", "Frustrated": "#FF5C7A"}

FONT = "Segoe UI"         # body text: a clean font every Windows PC has
HEAD_FONT = "Bahnschrift"  # headings: a squarer "instrument panel" font on Windows 10 and 11 (Windows picks another if missing)
TITLE_SIZE = 22
HEADING_SIZE = 15
BODY_SIZE = 13
SMALL_SIZE = 11

WINDOW_SIZE = "1120x720"
MIN_SIZE = (900, 600)
SIDEBAR_WIDTH = 214
STAR_COUNT = 110

# small symbols on the menu buttons (all in Windows' standard symbol font)
ICONS = {"home": "◈", "voice": "◉", "listening": "◎", "controls": "▣", "chat": "✦",
         "navigation": "▲", "bookmarks": "◆", "personality": "●", "game": "■"}

# her picture (the old single picture is still used if there are no mood pictures)
AVATAR_FILE = Path(__file__).resolve().parent / "assets" / "avatar.png"
PORTRAIT_BOX = (300, 380)
