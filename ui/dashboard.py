"""
The STARLING dashboard window (CustomTkinter).

This file only DRAWS things. What the settings are lives in ui/settings_model.py,
what colours are used lives in ui/theme.py, and what the Home page says lives in ui/status.py.
To change the look, edit theme.py. To add a setting, edit settings_model.py.
"""

import math
import random
import time

from core.identity import assistant_name
from core.logger import get_logger
from ui import portraits, ship_pictures
from ui import theme as T
from ui.settings_model import SettingsModel
from ui.status import EventFeed, collect_status, header_data, home_data

log = get_logger("dashboard")

TEST_LINES = [
    "Systems check complete. I can hear myself, and I sound fantastic.",
    "This is how I sound right now, Commander. Adjust me until you are happy.",
]
STATUS_COLOURS = {"good": T.GOOD, "warn": T.WARN, "bad": T.BAD, "muted": T.MUTED}
REFRESH_MS = 1000


def customtkinter_missing_message():
    return ("The dashboard needs the 'customtkinter' package.\n"
            "Double-click setup.bat again to install it, then run_dashboard.bat.")


class Dashboard:
    def __init__(self, app):
        import customtkinter as ctk
        self.ctk = ctk
        self.app = app
        self.model = SettingsModel(app.settings)
        self.feed = EventFeed(app.bus)
        self.page_frames = {}
        self.nav_buttons = {}
        self.current = None
        self._status_labels = []
        self._home_signature = None
        self._ship_shown = None
        self._ship_label = None
        self._ship_outline = None
        self._ship_images = {}
        self._galaxy_image = None
        self._status_pool = []
        self._feed_pool = []
        self._portrait_images = {}
        self._portrait_mood = None
        self._portrait_label = None
        self._portrait_frame = None
        self._mood_chip = None
        self._mood_score = None
        self._quote = random.choice(T.QUOTES)
        self._header_shown = {}
        self._home_widgets = {}
        self._event_rows = []
        self._busy_until = 0.0          # the window was just moved or resized: skip the 1-second refresh until it settles
        self._stars_job = None
        self._stars_size = (0, 0)

        ctk.set_appearance_mode("dark")
        self.root = ctk.CTk(fg_color=T.BG)
        self.root.title(assistant_name(app.settings).upper())
        self.root.geometry(T.WINDOW_SIZE)
        self.root.minsize(*T.MIN_SIZE)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self._build_layout()
        self.root.bind("<Configure>", self._window_moved, add="+")
        self.show("home")
        self.root.after(REFRESH_MS, self._tick)

    # ------------------------------------------------------------------ layout
    def _font(self, size=None, bold=False, head=False):
        return self.ctk.CTkFont(family=T.HEAD_FONT if head else T.FONT, size=size or T.BODY_SIZE,
                                weight="bold" if bold else "normal")

    def _heading(self, parent, text):
        """A small spaced-out section title, like the labels on an instrument panel."""
        return self.ctk.CTkLabel(parent, text=" ".join(text.upper()),
                                 font=self._font(T.SMALL_SIZE, True, head=True), text_color=T.ACCENT, anchor="w")

    def _build_layout(self):
        ctk = self.ctk
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        # left menu
        side = ctk.CTkFrame(self.root, width=T.SIDEBAR_WIDTH, corner_radius=0, fg_color=T.SIDEBAR,
                            border_width=0)
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)
        name = assistant_name(self.app.settings).upper()
        head = ctk.CTkFrame(side, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(20, 12))
        logo = ctk.CTkCanvas(head, width=48, height=48, bg=T.SIDEBAR, highlightthickness=0)
        logo.grid(row=0, column=0, rowspan=2, padx=(0, 10))
        self._draw_logo(logo)
        ctk.CTkLabel(head, text=" ".join(name), font=self._font(T.TITLE_SIZE - 2, True, head=True), text_color=T.TEXT).grid(
            row=0, column=1, sticky="w")
        ctk.CTkLabel(head, text="SHIP  COMPANION", font=self._font(T.SMALL_SIZE - 1, head=True), text_color=T.ACCENT).grid(
            row=1, column=1, sticky="w")
        ctk.CTkFrame(side, height=1, fg_color=T.BORDER, corner_radius=0).pack(fill="x", padx=16, pady=(0, 10))
        for page_id, title in [("home", "Home")] + [(p.id, p.title) for p in self.model.sidebar_pages]:
            icon = T.ICONS.get(page_id, "\u25C7")
            button = ctk.CTkButton(side, text="%s   %s" % (icon, title), anchor="w", height=38, corner_radius=8,
                                   font=self._font(), fg_color="transparent", text_color=T.MUTED,
                                   hover_color=T.PANEL_HOVER, border_width=1, border_color=T.BORDER_GLOW,
                                   command=lambda i=page_id: self.show(i))
            button.pack(fill="x", padx=12, pady=2)
            self.nav_buttons[page_id] = button
        try:
            from core.app import APP_VERSION
            version = APP_VERSION.split(" ")[0]
        except Exception:
            version = ""
        if version:
            ctk.CTkLabel(side, text="v" + version, font=self._font(T.SMALL_SIZE - 1), text_color=T.BORDER_GLOW).pack(
                side="bottom", padx=20, pady=(0, 12), anchor="w")
        ctk.CTkLabel(side, text="A  SAFER  GALAXY\nT O G E T H E R", font=self._font(T.SMALL_SIZE - 2, head=True), text_color=T.MUTED,
                     justify="center").pack(side="bottom", pady=(0, 8))

        # right side: starfield banner, page area, save bar
        right = ctk.CTkFrame(self.root, fg_color=T.BG, corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        self.banner = self.ctk.CTkCanvas(right, height=T.BANNER_HEIGHT, bg=T.BG, highlightthickness=0)
        self.banner.grid(row=0, column=0, sticky="ew")
        self.banner.bind("<Configure>", self._stars_soon)
        self._stars = [(random.random(), random.random(), random.choice((1, 1, 2)), random.choice((T.TEXT, T.MUTED, T.VIOLET, T.ACCENT)))
                       for _ in range(T.STAR_COUNT)]

        self.area = ctk.CTkFrame(right, fg_color=T.BG, corner_radius=0)
        self.area.grid(row=1, column=0, sticky="nsew", padx=24, pady=(4, 8))
        self.area.grid_columnconfigure(0, weight=1)
        self.area.grid_rowconfigure(0, weight=1)

        bar = ctk.CTkFrame(right, fg_color=T.SIDEBAR, corner_radius=0, height=56)
        bar.grid(row=2, column=0, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)
        self.save_note = ctk.CTkLabel(bar, text="", font=self._font(T.SMALL_SIZE), text_color=T.MUTED, anchor="w")
        self.save_note.grid(row=0, column=0, padx=20, pady=14, sticky="w")
        ctk.CTkLabel(bar, text="\u201C%s\u201D" % self._quote, font=self._font(T.SMALL_SIZE), text_color=T.MUTED).grid(
            row=0, column=1, padx=16, pady=14)
        ctk.CTkButton(bar, text="\u2699   SAVE SETTINGS", width=170, font=self._font(T.SMALL_SIZE + 1, True, head=True),
                      fg_color="transparent", border_width=1, border_color=T.ACCENT, hover_color=T.PANEL_HOVER, text_color=T.ACCENT,
                      corner_radius=6, command=self.save).grid(row=0, column=2, padx=(0, 20), pady=8)

        self._build_home()
        for page in self.model.sidebar_pages:
            self._build_page(page)

    def _stars_soon(self, event=None):
        """Redraw the starfield once the window has stopped changing size (drawing it 100 times a second made dragging sluggish)."""
        self._busy_until = time.monotonic() + 0.4
        size = (getattr(event, "width", 0), getattr(event, "height", 0))
        if event is not None and size == self._stars_size:
            return                                     # only moved, not resized: nothing to redraw
        if self._stars_job is not None:
            self.root.after_cancel(self._stars_job)
        self._stars_job = self.root.after(120, self._draw_stars)

    def _draw_stars(self, event=None):
        self._stars_job = None
        canvas = self.banner
        width, height = max(canvas.winfo_width(), 10), max(canvas.winfo_height(), 10)
        self._stars_size = (width, height)
        canvas.delete("all")
        for fx, fy, size, colour in self._stars:
            x, y = fx * width, fy * height
            canvas.create_oval(x, y, x + size, y + size, fill=colour, outline="")
            if size == 2 and colour == T.TEXT:                       # a few brighter stars get a little glint
                canvas.create_line(x - 4, y + 1, x + 6, y + 1, fill=T.BORDER_GLOW)
                canvas.create_line(x + 1, y - 4, x + 1, y + 6, fill=T.BORDER_GLOW)
        self._banner_title(canvas, width, height)

    def _banner_title(self, canvas, width=0, height=None):
        height = height or T.BANNER_HEIGHT
        page = self.current or "home"
        if page == "home":
            text = "WELCOME, COMMANDER"
            sub = "\u201C%s\u201D   \u2013   %s" % (self._quote, assistant_name(self.app.settings).title())
        else:
            text = next((p.title for p in self.model.sidebar_pages if p.id == page), "").upper()
            sub = ""
        right = max(width - 24, 400)
        canvas.create_text(24, 12, text=T.TAGLINE, anchor="w", fill=T.ORANGE, font=(T.HEAD_FONT, T.SMALL_SIZE - 2))
        canvas.create_text(24, 38, text=text, anchor="w", fill=T.TEXT, font=(T.HEAD_FONT, T.TITLE_SIZE + 2, "bold"))
        if sub:
            canvas.create_text(24, 66, text=sub, anchor="w", fill=T.MUTED, font=(T.FONT, T.BODY_SIZE))
        # a thin instrument-panel line under the title, with end ticks
        y = max(height - 10, 50)
        canvas.create_line(24, y, right, y, fill=T.BORDER)
        canvas.create_line(24, y, 150, y, fill=T.ACCENT, width=2)
        canvas.create_line(24, y - 4, 24, y + 4, fill=T.ACCENT)
        canvas.create_line(right, y - 4, right, y + 4, fill=T.BORDER_GLOW)
        # top right: who and where, and the clocks
        canvas.create_text(right - 128, 26, text="", tags="hdr_cmdr", anchor="e", fill=T.TEXT, font=(T.HEAD_FONT, T.BODY_SIZE - 1, "bold"))
        canvas.create_text(right - 128, 50, text="", tags="hdr_sys", anchor="e", fill=T.ACCENT, font=(T.HEAD_FONT, T.SMALL_SIZE))
        canvas.create_line(right - 108, 14, right - 108, 62, fill=T.ORANGE)
        # the microphone box: lit green while she is listening to you
        canvas.create_rectangle(right - 470, 22, right - 330, 56, outline=T.BORDER, width=2, tags="hdr_micbox")
        canvas.create_text(right - 400, 39, text="", tags="hdr_mic", anchor="center", fill=T.MUTED, font=(T.HEAD_FONT, T.SMALL_SIZE, "bold"))
        canvas.create_text(right, 26, text="", tags="hdr_time", anchor="e", fill=T.TEXT, font=(T.HEAD_FONT, T.BODY_SIZE - 1))
        canvas.create_text(right, 50, text="", tags="hdr_date", anchor="e", fill=T.MUTED, font=(T.HEAD_FONT, T.SMALL_SIZE))
        self._header_shown = {}
        self._update_header()

    def _update_header(self):
        """Commander, system, time and game date at the top right. Only changed words are sent to the window."""
        try:
            data = header_data(self.app)
        except Exception:
            return
        for tag, key in (("hdr_cmdr", "commander"), ("hdr_sys", "system"), ("hdr_time", "time"), ("hdr_date", "date")):
            if self._header_shown.get(tag) != data[key]:
                self._header_shown[tag] = data[key]
                self.banner.itemconfigure(tag, text=data[key])
        words, tone = data.get("mic", ("", "muted"))
        if self._header_shown.get("hdr_mic") != (words, tone):
            self._header_shown["hdr_mic"] = (words, tone)
            colour = STATUS_COLOURS.get(tone, T.MUTED)
            self.banner.itemconfigure("hdr_mic", text=("\u25CF  " if tone == "good" else "\u25CB  ") + words, fill=colour)
            self.banner.itemconfigure("hdr_micbox", outline=colour)

    @staticmethod
    def _draw_logo(canvas):
        """A small ring logo: a glowing blue circle with a bright gap."""
        canvas.create_oval(4, 4, 44, 44, outline=T.ACCENT_DIM, width=6)
        canvas.create_arc(4, 4, 44, 44, start=30, extent=280, style="arc", outline=T.ACCENT, width=4)
        canvas.create_oval(18, 18, 30, 30, outline=T.BORDER_GLOW, width=1)

    # ------------------------------------------------------------------ pages
    def _card(self, parent):
        return self.ctk.CTkFrame(parent, fg_color=T.PANEL, corner_radius=12, border_width=1, border_color=T.BORDER)

    def _build_home(self):
        """The Home page: her picture, three status tiles, the current system, ship status, recent events and quick actions."""
        ctk = self.ctk
        frame = ctk.CTkScrollableFrame(self.area, fg_color=T.BG, corner_radius=0)
        frame.grid_columnconfigure(0, weight=0)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(2, weight=0)
        self.page_frames["home"] = frame
        w = self._home_widgets

        self._build_avatar(frame)                                           # left, tall

        middle = ctk.CTkFrame(frame, fg_color=T.BG, corner_radius=0)         # middle top: tiles + current system
        middle.grid(row=0, column=1, sticky="nsew", padx=(14, 0))
        middle.grid_columnconfigure(0, weight=1)
        self._build_tiles(middle)
        self._build_system_card(middle)

        self._build_ship_card(frame)                                        # right top
        self._build_events_card(frame)                                      # middle bottom
        self._build_quick_actions(frame)                                    # right bottom
        w["ready"] = True
        self._refresh_home()

    def _panel_title(self, parent, icon, text, colour=None, row=0, column=0, columnspan=1):
        label = self.ctk.CTkLabel(parent, text="%s   %s" % (icon, " ".join(text.upper()) if len(text) < 16 else text.upper()),
                                  font=self._font(T.SMALL_SIZE + 1, True, head=True), text_color=colour or T.ACCENT, anchor="w")
        label.grid(row=row, column=column, columnspan=columnspan, sticky="w", padx=18, pady=(14, 6))
        return label

    def _autowrap(self, card, *labels, margin=34, minimum=90):
        """Makes the words in a card wrap to the card's real width, so nothing is cut off when the window is small."""
        state = {"width": 0}

        def resize(event=None):
            width = max(minimum, (getattr(event, "width", 0) or card.winfo_width()) - margin)
            if abs(width - state["width"]) < 6:
                return
            state["width"] = width
            for label in labels:
                try:
                    label.configure(wraplength=width)
                except Exception:
                    pass
        try:
            card.bind("<Configure>", resize, add="+")
        except Exception:
            pass

    def _build_tiles(self, parent):
        ctk = self.ctk
        holder = ctk.CTkFrame(parent, fg_color=T.BG, corner_radius=0)
        holder.grid(row=0, column=0, sticky="ew")
        holder.grid_columnconfigure((0, 1, 2), weight=1, uniform="tile")
        self._home_widgets["tiles"] = []
        for index, (title, icon) in enumerate((("VOICE", "\u25C9"), ("HOTAS", "\u2316"), ("JOURNAL", "\u25A4"))):
            card = self._card(holder)
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 8, 0))
            card.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(card, text=icon, font=self._font(T.TITLE_SIZE, True), text_color=T.ACCENT, width=34).grid(
                row=0, column=0, padx=(14, 4), pady=(12, 0))
            ctk.CTkLabel(card, text=title, font=self._font(T.BODY_SIZE, True, head=True), text_color=T.TEXT, anchor="w").grid(
                row=0, column=1, sticky="w", pady=(12, 0))
            status = ctk.CTkLabel(card, text="", font=self._font(T.SMALL_SIZE + 1, True, head=True), text_color=T.MUTED, anchor="w")
            status.grid(row=1, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 0))
            sub = ctk.CTkLabel(card, text="", font=self._font(T.SMALL_SIZE), text_color=T.MUTED, anchor="w", justify="left",
                               wraplength=110)
            sub.grid(row=2, column=0, columnspan=2, sticky="w", padx=16, pady=(2, 12))
            status.configure(wraplength=110, justify="left")
            self._autowrap(card, sub, status)
            self._home_widgets["tiles"].append((status, sub))

    def _build_system_card(self, parent):
        ctk = self.ctk
        card = self._card(parent)
        card.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        card.grid_columnconfigure(0, weight=1)
        self._panel_title(card, "\u25CE", "Current system", T.ORANGE)
        self._home_widgets["system_name"] = ctk.CTkLabel(card, text="-", font=self._font(T.TITLE_SIZE - 2, True), text_color=T.TEXT, anchor="w")
        self._home_widgets["system_name"].grid(row=1, column=0, sticky="w", padx=18, pady=(2, 6))
        self._home_widgets["system_name"].configure(wraplength=240, justify="left")
        self._autowrap(card, self._home_widgets["system_name"], margin=210, minimum=140)
        facts = ctk.CTkFrame(card, fg_color="transparent")
        facts.grid(row=2, column=0, sticky="w", padx=18, pady=(0, 14))
        for index, (label, key) in enumerate((("SECURITY", "security"), ("ALLEGIANCE", "allegiance"), ("POPULATION", "population"))):
            ctk.CTkLabel(facts, text=label, font=self._font(T.SMALL_SIZE), text_color=T.MUTED, anchor="w", width=110).grid(
                row=index, column=0, sticky="w", pady=2)
            value = ctk.CTkLabel(facts, text="-", font=self._font(T.BODY_SIZE), text_color=T.ORANGE if key == "security" else T.TEXT, anchor="w")
            value.grid(row=index, column=1, sticky="w", padx=(8, 0), pady=2)
            self._home_widgets["system_" + key] = value
        self._galaxy_picture(card)
        ctk.CTkButton(card, text="GALAXY MAP  \u2197", width=130, height=24, font=self._font(T.SMALL_SIZE - 1, True, head=True),
                      fg_color="transparent", text_color=T.ACCENT, hover_color=T.PANEL_HOVER, corner_radius=4,
                      command=self.open_system_map).grid(row=3, column=1, sticky="e", padx=(0, 14), pady=(0, 10))

    def _galaxy_picture(self, card):
        """The galaxy map picture (ui/assets/galaxy.jpg). If it cannot be loaded, a little drawn spiral is used instead."""
        ctk = self.ctk
        try:
            from PIL import Image
            picture = Image.open(portraits.ASSETS / "galaxy.jpg")
            picture.load()
            image = ctk.CTkImage(light_image=picture, dark_image=picture, size=(150, 150))
            self._galaxy_image = image                                  # keep a reference, or the picture disappears
            ctk.CTkLabel(card, text="", image=image, fg_color="transparent").grid(
                row=0, column=1, rowspan=3, padx=(0, 14), pady=(10, 4))
        except Exception:
            log.warning("Could not load the galaxy picture", exc_info=True)
            canvas = ctk.CTkCanvas(card, width=210, height=130, bg=T.PANEL, highlightthickness=0)
            canvas.grid(row=0, column=1, rowspan=3, padx=(0, 10), pady=6)
            self._draw_galaxy(canvas)

    @staticmethod
    def _draw_galaxy(canvas):
        """A little spiral galaxy made of dots (drawn once)."""
        rng = random.Random(7)
        cx, cy = 105, 65
        canvas.create_oval(cx - 14, cy - 8, cx + 14, cy + 8, fill=T.ACCENT_DIM, outline="")
        canvas.create_oval(cx - 6, cy - 4, cx + 6, cy + 4, fill=T.ORANGE, outline="")
        for arm in (0.0, math.pi):
            for i in range(90):
                t = i / 90.0
                angle = arm + t * 5.2
                radius = 8 + t * 82
                x = cx + radius * math.cos(angle) * 1.1 + rng.uniform(-4, 4)
                y = cy + radius * math.sin(angle) * 0.55 + rng.uniform(-3, 3)
                colour = rng.choice((T.ACCENT, T.ACCENT_DIM, T.VIOLET, T.TEXT))
                size = 2 if rng.random() < 0.25 else 1
                canvas.create_oval(x, y, x + size, y + size, fill=colour, outline="")

    def _build_ship_card(self, frame):
        ctk = self.ctk
        card = self._card(frame)
        card.grid(row=0, column=2, sticky="nsew", padx=(14, 0))
        card.grid_columnconfigure(0, weight=1)
        card.grid_columnconfigure(1, weight=0)
        self._panel_title(card, "\u2630", "Ship status", T.ACCENT, row=0, column=0)
        self._home_widgets["ship_name"] = ctk.CTkLabel(card, text="-", font=self._font(T.BODY_SIZE), text_color=T.TEXT, anchor="e")
        self._home_widgets["ship_name"].grid(row=0, column=1, sticky="e", padx=18, pady=(14, 6))
        self._home_widgets["ship_name"].configure(wraplength=150, justify="right")
        holder = ctk.CTkFrame(card, fg_color="transparent", width=290, height=100)
        holder.grid(row=1, column=0, columnspan=2, pady=(0, 6))
        holder.grid_propagate(False)
        holder.grid_columnconfigure(0, weight=1)
        holder.grid_rowconfigure(0, weight=1)
        self._ship_outline = ctk.CTkCanvas(holder, width=290, height=84, bg=T.PANEL, highlightthickness=0)
        self._ship_outline.grid(row=0, column=0)
        self._draw_ship(self._ship_outline)
        self._ship_label = ctk.CTkLabel(holder, text="", fg_color="transparent")     # shown instead of the outline when a picture exists
        self._ship_label.grid(row=0, column=0)
        self._ship_label.grid_remove()
        bars = ctk.CTkFrame(card, fg_color="transparent")
        bars.grid(row=2, column=0, columnspan=2, sticky="ew", padx=18)
        bars.grid_columnconfigure(1, weight=1)
        self._home_widgets["bars"] = {}
        for index, (label, key, colour) in enumerate((("FUEL", "fuel", T.ACCENT), ("HULL", "hull", T.ORANGE),
                                                      ("SHIELDS", "shields", T.ACCENT), ("CARGO", "cargo", T.ORANGE))):
            ctk.CTkLabel(bars, text=label, font=self._font(T.SMALL_SIZE + 1, False, head=True), text_color=T.TEXT, anchor="w", width=70).grid(
                row=index, column=0, sticky="w", pady=5)
            bar = ctk.CTkProgressBar(bars, height=9, corner_radius=4, fg_color=T.BG, progress_color=colour)
            bar.set(0)
            bar.grid(row=index, column=1, sticky="ew", padx=8, pady=5)
            value = ctk.CTkLabel(bars, text="-", font=self._font(T.SMALL_SIZE + 1), text_color=T.TEXT, anchor="e", width=70)
            value.grid(row=index, column=2, sticky="e", pady=5)
            self._home_widgets["bars"][key] = (bar, value)
        self._home_widgets["where"] = ctk.CTkLabel(card, text="", font=self._font(T.SMALL_SIZE), text_color=T.MUTED, anchor="w")
        self._home_widgets["where"].grid(row=3, column=0, columnspan=2, sticky="w", padx=18, pady=(8, 14))

    @staticmethod
    def _draw_ship(canvas):
        """A simple orange outline of a ship (drawn once)."""
        outline = [(20, 56), (90, 40), (150, 18), (240, 12), (272, 26), (210, 34), (190, 44), (250, 52), (214, 64),
                   (130, 66), (70, 70)]
        canvas.create_polygon(outline, outline=T.ORANGE, fill="", width=2)
        canvas.create_line(90, 40, 130, 66, fill=T.ORANGE)
        canvas.create_line(150, 18, 190, 44, fill=T.ORANGE)
        canvas.create_line(240, 12, 214, 64, fill=T.ORANGE)
        canvas.create_oval(160, 22, 186, 34, outline=T.ACCENT, width=1)

    def _build_events_card(self, frame):
        ctk = self.ctk
        card = self._card(frame)
        card.grid(row=1, column=1, columnspan=1, sticky="nsew", padx=(14, 0), pady=(14, 0))
        card.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(0, weight=1)
        self._panel_title(top, "\u2630", "Recent events", T.ORANGE)
        ctk.CTkButton(top, text="CLEAR", width=64, height=24, font=self._font(T.SMALL_SIZE - 1, True, head=True), fg_color="transparent",
                      text_color=T.ACCENT, hover_color=T.PANEL_HOVER, corner_radius=4, command=self.clear_events).grid(
            row=0, column=1, padx=14, pady=(10, 0))
        self.feed_card = ctk.CTkFrame(card, fg_color="transparent")
        self.feed_card.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 12))
        self.feed_card.grid_columnconfigure(2, weight=1)

    def _build_quick_actions(self, frame):
        ctk = self.ctk
        card = self._card(frame)
        card.grid(row=1, column=2, sticky="nsew", padx=(14, 0), pady=(14, 0))
        card.grid_columnconfigure(0, weight=1)
        self._panel_title(card, "\u26A1", "Quick actions", T.ACCENT)
        for index, (icon, text, command) in enumerate((
                ("\u2692", "Plot Route", self.quick_plot), ("\u25A3", "Open Galaxy Map", self.quick_map),
                ("\u25C9", "Toggle Voice", self.quick_voice), ("\u25CE", "Check Systems", self.quick_check),
                ("\u25A4", "Read Journal", self.quick_journal))):
            ctk.CTkButton(card, text="%s     %s" % (icon, text), anchor="w", height=34, font=self._font(), fg_color=T.PANEL,
                          border_width=1, border_color=T.ACCENT_DIM, hover_color=T.PANEL_HOVER, text_color=T.TEXT, corner_radius=6,
                          command=command).grid(row=1 + index, column=0, sticky="ew", padx=14, pady=(0, 6))

    def _build_avatar(self, frame):
        """Her picture, framed in the colour of her mood. The pictures are in ui/assets/portraits/ (see the README there)."""
        ctk = self.ctk
        holder = ctk.CTkFrame(frame, fg_color=T.PANEL, corner_radius=12, border_width=2, border_color=T.MOOD_COLOURS["Neutral"])
        holder.grid(row=0, column=0, rowspan=2, sticky="n")
        self._portrait_frame = holder
        ctk.CTkLabel(holder, text=" ".join(assistant_name(self.app.settings).upper()), font=self._font(T.BODY_SIZE + 1, True, head=True),
                     text_color=T.ACCENT, anchor="w").pack(fill="x", padx=16, pady=(12, 6))
        self._portrait_label = ctk.CTkLabel(holder, text="", fg_color="transparent")
        self._portrait_label.pack(padx=12, pady=(0, 6))
        ctk.CTkLabel(holder, text="\u25CF  ONLINE", font=self._font(T.SMALL_SIZE, True, head=True), text_color=T.GOOD).pack()
        ctk.CTkLabel(holder, text="Your AI co-pilot", font=self._font(T.SMALL_SIZE), text_color=T.MUTED).pack()
        ctk.CTkLabel(holder, text="\u201CReady when you are,\nCommander.\u201D", font=self._font(T.SMALL_SIZE), text_color=T.MUTED,
                     justify="center").pack(pady=(8, 4))
        self._mood_chip = ctk.CTkLabel(holder, text="", font=self._font(T.SMALL_SIZE, True, head=True), text_color=T.MUTED)
        self._mood_chip.pack(pady=(4, 0))
        self._mood_score = ctk.CTkLabel(holder, text="", font=self._font(T.SMALL_SIZE), text_color=T.MUTED)
        self._mood_score.pack(pady=(0, 12))
        self._update_portrait()

    def _current_mood(self):
        mood = getattr(self.app, "mood", None)
        if self.app.settings.get("personality.mood_mode", "auto") == "fixed" or mood is None:
            word = str(self.app.settings.get("personality.mood", "Friendly"))
        else:
            word = str(mood.mood)
        return word if word in portraits.MOODS else "Neutral"

    def _portrait_image(self, path):
        """The picture as a window image, made once per file."""
        key = str(path)
        if key not in self._portrait_images:
            from PIL import Image
            picture = Image.open(path)
            picture.load()
            size = portraits.fit(picture.width, picture.height, *T.PORTRAIT_BOX)
            self._portrait_images[key] = self.ctk.CTkImage(light_image=picture, dark_image=picture, size=size)
        return self._portrait_images[key]

    def _update_portrait(self):
        """Show the picture for her current mood. Only touches the window when the mood changes."""
        if self._portrait_label is None:
            return
        mood = self._current_mood()
        if mood == self._portrait_mood:
            return
        self._portrait_mood = mood
        colour = T.MOOD_COLOURS.get(mood, T.ACCENT)
        try:
            path = portraits.portrait_for(mood)
            if path is not None:
                self._portrait_label.configure(image=self._portrait_image(path))
        except Exception:
            log.warning("Could not load her picture for %s", mood, exc_info=True)
        self._portrait_frame.configure(border_color=colour)
        self._mood_chip.configure(text="\u25CF  %s" % mood.upper(), text_color=colour)

    def _refresh_home(self):
        """Update the Home page in place. Widgets are re-used and only changed when their words change,
        so nothing is destroyed and rebuilt (that was what made the page flicker)."""
        w = self._home_widgets
        if not w.get("ready"):
            return
        data = home_data(self.app)
        items = self.feed.recent_with_kind()[:6]
        signature = (repr(data["tiles"]), repr(data["system"]), repr(data["ship"]), data["mood"], tuple(items))
        self._update_portrait()
        if signature == self._home_signature:
            return
        self._home_signature = signature
        for (status, sub), (_title, _icon, word, tone, text) in zip(w["tiles"], data["tiles"]):
            status.configure(text="\u25CF  " + word, text_color=STATUS_COLOURS.get(tone, T.TEXT))
            sub.configure(text=text)
        system = data["system"]
        w["system_name"].configure(text=system["name"])
        for key in ("security", "allegiance", "population"):
            w["system_" + key].configure(text=system[key])
        ship = data["ship"]
        shown = ship["name"] if not ship.get("model") or ship["model"].lower() == ship["name"].lower() else "%s  (%s)" % (ship["name"], ship["model"])
        w["ship_name"].configure(text=shown)
        self._update_ship_picture(ship)
        w["where"].configure(text=ship["where"])
        for key in ("fuel", "hull", "shields", "cargo"):
            bar, value = w["bars"][key]
            bar.set(ship[key])
            value.configure(text=ship["cargo_text"] if key == "cargo" else "%d%%" % round(ship[key] * 100))
        if self._mood_score is not None:
            self._mood_score.configure(text=data["mood"])
        self._sync_events(items)

    def _update_ship_picture(self, ship):
        """Her picture of the ship you are flying (see ui/assets/ships/README.txt). Only changes when the ship changes."""
        key = (ship.get("code"), ship.get("model"))
        if key == self._ship_shown or self._ship_label is None:
            return
        self._ship_shown = key
        path = None
        try:
            path = ship_pictures.picture_for(ship.get("code") or "", ship.get("model") or "")
            if path is not None:
                if path not in self._ship_images:
                    from PIL import Image
                    picture = Image.open(path)
                    picture.load()
                    size = portraits.fit(picture.width, picture.height, 290, 100)
                    self._ship_images[path] = self.ctk.CTkImage(light_image=picture, dark_image=picture, size=size)
                self._ship_label.configure(image=self._ship_images[path])
        except Exception:
            log.warning("Could not load the ship picture", exc_info=True)
            path = None
        if path is not None:
            self._ship_outline.grid_remove()
            self._ship_label.grid()
        else:
            self._ship_label.grid_remove()
            self._ship_outline.grid()

    def _sync_events(self, items):
        """The Recent events list: time, kind and words. Rows are re-used."""
        ctk = self.ctk
        while len(self._event_rows) < 6:
            row = len(self._event_rows)
            when = ctk.CTkLabel(self.feed_card, text="", font=self._font(T.SMALL_SIZE + 1), text_color=T.MUTED, anchor="w", width=60)
            when.grid(row=row, column=0, padx=(12, 6), pady=4, sticky="w")
            kind = ctk.CTkLabel(self.feed_card, text="", font=self._font(T.SMALL_SIZE + 1), text_color=T.TEXT, anchor="w", width=130)
            kind.grid(row=row, column=1, padx=6, pady=4, sticky="w")
            text = ctk.CTkLabel(self.feed_card, text="", font=self._font(T.SMALL_SIZE + 1), text_color=T.TEXT, anchor="w",
                                justify="left", wraplength=260)
            text.grid(row=row, column=2, padx=6, pady=4, sticky="w")
            self._autowrap(self.feed_card, text, margin=240, minimum=140)
            self._event_rows.append({"when": when, "kind": kind, "text": text, "shown": None})
        if not items:
            items = [("", "", "Nothing yet. Fly somewhere!", "low")]
        for index, entry in enumerate(self._event_rows):
            if index < len(items):
                when, kind, text, priority = items[index]
                shown = (when, kind, text, priority)
                if entry["shown"] is None:
                    for part in ("when", "kind", "text"):
                        entry[part].grid()
                if entry["shown"] != shown:
                    entry["when"].configure(text=when)
                    entry["kind"].configure(text=("%s   %s" % (T.KIND_ICONS.get(kind, "\u25A4"), kind)) if kind else "")
                    colour = T.BAD if priority == "critical" else (T.MUTED if not kind else T.TEXT)
                    entry["text"].configure(text=text[:160], text_color=colour)
                    entry["shown"] = shown
            elif entry["shown"] is not None:
                for part in ("when", "kind", "text"):
                    entry[part].grid_remove()
                entry["shown"] = None

    # ---- Home page buttons ----
    def clear_events(self):
        self.feed.clear()
        self._home_signature = None
        self._refresh_home()

    def open_system_map(self):
        state = getattr(self.app, "state", None)
        system = getattr(state, "system", None) if state is not None else None
        if not system:
            self.save_note.configure(text="I don't know which system you are in yet.", text_color=T.WARN)
            return
        import urllib.parse
        import webbrowser
        webbrowser.open("https://www.edsm.net/en/system?systemName=" + urllib.parse.quote(system))
        self.save_note.configure(text="Opening %s on EDSM in your browser." % system, text_color=T.MUTED)

    def quick_plot(self):
        self._controls_result(self.app.plot_route_now(""), T.GOOD)

    def quick_map(self):
        self._controls_result(self.app.run_command_now("open the galaxy map", doing="open the galaxy map"), T.WARN)

    def quick_voice(self):
        """Switch her voice on or off (the same setting as the Voice page; press Save settings to keep it)."""
        field = self.model.field("speech.enabled")
        now_on = not bool(self.model.current_value(field))
        self._changed(self.model.set_value(field, now_on))
        switch = getattr(self, "_w_speech_enabled", None)
        if switch is not None:
            (switch.select if now_on else switch.deselect)()
        self.save_note.configure(text="Her voice is now %s. Save settings to keep that." % ("ON" if now_on else "OFF"), text_color=T.WARN)

    def quick_check(self):
        problems = [(label, text) for label, text, tone in collect_status(self.app) if tone in ("bad", "warn")]
        if problems:
            self.save_note.configure(text="Check: " + "; ".join("%s - %s" % p for p in problems)[:140], text_color=T.WARN)
        else:
            self.save_note.configure(text="All systems ready, Commander.", text_color=T.GOOD)

    def quick_journal(self):
        folder = getattr(self.app, "journal_folder", None)
        if not folder:
            self.save_note.configure(text="I can't see the Elite journal folder yet.", text_color=T.WARN)
            return
        try:
            import os
            os.startfile(str(folder))                           # Windows: opens the folder in Explorer
            self.save_note.configure(text="Opening the journal folder.", text_color=T.MUTED)
        except (AttributeError, OSError):
            self.save_note.configure(text="Journal folder: %s" % folder, text_color=T.MUTED)

    def _sync_rows(self, card, pool, data, left_width, left_bold, pad):
        """Make the rows in `card` show `data` [(left, right, right_colour)], touching only what changed."""
        ctk = self.ctk
        while len(pool) < len(data):
            row = len(pool)
            left = ctk.CTkLabel(card, text="", font=self._font(T.SMALL_SIZE if not left_width else None, left_bold),
                                text_color=T.MUTED, anchor="w", width=left_width)
            left.grid(row=row, column=0, padx=(18, 8), pady=pad, sticky="w")
            right = ctk.CTkLabel(card, text="", font=self._font(bold=bool(left_width)), anchor="w", text_color=T.TEXT)
            right.grid(row=row, column=1, padx=8, pady=pad, sticky="w")
            pool.append({"left": left, "right": right, "shown": None})
        for index, (left_text, right_text, colour) in enumerate(data):
            entry = pool[index]
            if entry["shown"] is None:
                entry["left"].grid()
                entry["right"].grid()
            if entry["shown"] != (left_text, right_text, colour):
                entry["left"].configure(text=left_text)
                entry["right"].configure(text=right_text, text_color=colour)
                entry["shown"] = (left_text, right_text, colour)
        for entry in pool[len(data):]:
            if entry["shown"] is not None:
                entry["left"].grid_remove()
                entry["right"].grid_remove()
                entry["shown"] = None

    def _build_page(self, page):
        """One sidebar page: its own content, then any pages merged into it as titled sections."""
        ctk = self.ctk
        frame = ctk.CTkScrollableFrame(self.area, fg_color=T.BG, corner_radius=0)
        frame.grid_columnconfigure(0, weight=1)
        self.page_frames[page.id] = frame
        row = self._build_section(frame, page, 0, heading=False)
        for child in self.model.pages:
            if child.parent == page.id:
                row = self._build_section(frame, child, row, heading=True)

    def _build_section(self, frame, page, row, heading):
        """Draws one model page into the frame starting at grid row `row`; returns the next free row."""
        ctk = self.ctk
        if heading:
            ctk.CTkFrame(frame, height=1, fg_color=T.BORDER, corner_radius=0).grid(row=row, column=0, sticky="ew", pady=(28, 10))
            ctk.CTkLabel(frame, text=page.title.upper(), font=self._font(T.BODY_SIZE, True, head=True), text_color=T.ACCENT,
                         anchor="w").grid(row=row + 1, column=0, sticky="w", pady=(0, 4))
            row += 2
        ctk.CTkLabel(frame, text=page.blurb, font=self._font(), text_color=T.MUTED, anchor="w", justify="left",
                     wraplength=720).grid(row=row, column=0, sticky="w", pady=(0, 12))
        row += 1
        if page.id == "bookmarks":
            return self._build_bookmarks(frame, page, row)
        if page.fields:
            card = self._card(frame)
            card.grid(row=row, column=0, sticky="ew")
            card.grid_columnconfigure(0, weight=1)
            row += 1
            for index, field in enumerate(page.fields):
                self._build_field(card, index, field)

        extra = []
        if page.id == "voice":
            extra.append(("Prepare her voice now (makes her faster)", self.prepare_voice))
        if page.id == "personality":
            extra.append(("Reset her mood", self.reset_mood))
        if page.id == "listening":
            extra.append(("Refresh microphone list", lambda p=page: self.refresh_mics(p)))
        if page.id == "memory":
            extra += [("Show what she remembers", self.show_memories),
                      ("Forget everything", self.forget_memories)]
        if page.id == "updates":
            extra += [("Check for updates now", self.check_updates)]
        if page.id == "navigation":
            extra += [("Plot neutron route to my destination", lambda: self.nav_plot(use_entry=False)),
                      ("Plot the next waypoint in the galaxy map", self.nav_next),
                      ("Clear the route", self.nav_clear)]
        if page.id == "controls":
            extra += [("Learn push-to-talk button", self.learn_button)]
        if page.id == "developer":
            extra += [("Test her voice", self.test_voice),
                      ("Test the honk now", self.test_honk),
                      ("Check my Elite keys", self.check_keys),
                      ("Look for my joystick / HOTAS", self.scan_joysticks),
                      ("Record my buttons", self.record_buttons),
                      ("Copy my log to the clipboard (to send to Claude)", self.copy_log)]
        if page.id == "voice":
            self._build_voice_progress(frame, row)
            row += 1
        for text, command in extra:
            ctk.CTkButton(frame, text=text, width=230, font=self._font(), fg_color=T.PANEL, border_width=1, corner_radius=8,
                          border_color=T.ACCENT_DIM, hover_color=T.PANEL_HOVER, text_color=T.TEXT, command=command).grid(
                row=row, column=0, sticky="w", pady=(12, 0))
            row += 1
        if page.id == "developer":
            self._build_try_box(frame, row)
            row += 1
        if page.id == "navigation":
            line = ctk.CTkFrame(frame, fg_color=T.BG, corner_radius=0)
            line.grid(row=row, column=0, sticky="ew", pady=(16, 0))
            line.grid_columnconfigure(0, weight=1)
            self.nav_entry = ctk.CTkEntry(line, font=self._font(), fg_color=T.PANEL, border_color=T.BORDER, text_color=T.TEXT,
                                          placeholder_text="Or type any system here, e.g. Colonia", corner_radius=8)
            self.nav_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
            ctk.CTkButton(line, text="Plot to this system", width=170, font=self._font(), fg_color=T.PANEL, border_width=1,
                          corner_radius=8, border_color=T.ACCENT_DIM, hover_color=T.PANEL_HOVER, text_color=T.TEXT,
                          command=lambda: self.nav_plot(use_entry=True)).grid(row=0, column=1)
            ctk.CTkLabel(frame, text="Plotting a route needs you to be in the game (so she knows where you are). "
                                     "'Plot the next waypoint' waits 4 seconds so you can click back into Elite first.",
                         font=self._font(T.SMALL_SIZE), text_color=T.MUTED, anchor="w", justify="left",
                         wraplength=720).grid(row=row + 1, column=0, sticky="w", pady=(8, 0))
            row += 2
        return row

    def _build_bookmarks(self, frame, page, row=1):
        """Eleven boxes in two columns: Home and Bookmark 1-10. Each holds a system name."""
        ctk = self.ctk
        grid = ctk.CTkFrame(frame, fg_color=T.BG, corner_radius=0)
        grid.grid(row=row, column=0, sticky="ew")
        grid.grid_columnconfigure((0, 1), weight=1, uniform="bm")
        self._bookmark_entries = {}
        self._bookmark_seen = {}
        for index, field in enumerate(page.fields):
            card = self._card(grid)
            card.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0 if index % 2 == 0 else 8, 8 if index % 2 == 0 else 0), pady=6)
            card.grid_columnconfigure(0, weight=1)
            is_home = field.key == "bookmarks.home"
            title = ctk.CTkLabel(card, text=("\u25C8  " if is_home else "\u25C6  ") + field.label.upper(),
                                 font=self._font(T.BODY_SIZE, True, head=True),
                                 text_color=T.ORANGE if is_home else T.ACCENT, anchor="w")
            title.grid(row=0, column=0, columnspan=2, padx=16, pady=(12, 4), sticky="w")
            entry = ctk.CTkEntry(card, font=self._font(), fg_color=T.BG, border_color=T.BORDER, text_color=T.TEXT,
                                 placeholder_text=field.placeholder, corner_radius=8)
            current = self.model.current_value(field)
            if current:
                entry.insert(0, str(current))
            commit = lambda _e=None, f=field, w=entry: self._changed(self.model.set_value(f, w.get()))
            entry.bind("<Return>", commit)
            entry.bind("<FocusOut>", commit)
            entry.grid(row=1, column=0, padx=(16, 6), pady=(0, 12), sticky="ew")
            ctk.CTkButton(card, text="Here", width=58, font=self._font(T.SMALL_SIZE), fg_color=T.PANEL, border_width=1,
                          border_color=T.ACCENT_DIM, hover_color=T.PANEL_HOVER, text_color=T.TEXT, corner_radius=8,
                          command=lambda f=field, w=entry: self.use_current_system(f, w)).grid(row=1, column=1, padx=(0, 16), pady=(0, 12))
            self._bookmark_entries[field.key] = (field, entry)
            self._bookmark_seen[field.key] = str(current or "")
        ctk.CTkLabel(frame, text="'Here' fills the box with the system you are in now. You can also say: \"Starling, save this system as bookmark 3\".",
                     font=self._font(T.SMALL_SIZE), text_color=T.MUTED, anchor="w", justify="left", wraplength=720).grid(
            row=row + 1, column=0, sticky="w", pady=(10, 0))
        return row + 2

    def use_current_system(self, field, entry):
        state = getattr(self.app, "state", None)
        system = getattr(state, "system", None) if state is not None else None
        if not system:
            self.save_note.configure(text="I don't know which system you are in yet. Make a jump first.", text_color=T.WARN)
            return
        entry.delete(0, "end")
        entry.insert(0, system)
        self._changed(self.model.set_value(field, system))
        self.save_note.configure(text="%s set to %s. Save settings to keep it." % (field.label, system), text_color=T.GOOD)

    def _sync_bookmarks(self):
        """A bookmark saved by voice shows up here. A box is only rewritten when the SETTING changed behind your back,
        never because of what you are typing (the old version compared with the box itself and wiped your typing)."""
        entries = getattr(self, "_bookmark_entries", None) or {}
        seen = self._bookmark_seen
        for key, (field, entry) in entries.items():
            wanted = str(self.model.current_value(field) or "")
            if seen.get(key) == wanted:
                continue
            seen[key] = wanted
            if entry.get() != wanted:
                entry.delete(0, "end")
                entry.insert(0, wanted)

    def _build_field(self, card, row, field):
        ctk = self.ctk
        left = ctk.CTkFrame(card, fg_color="transparent")
        left.grid(row=row, column=0, sticky="w", padx=18, pady=9)
        ctk.CTkLabel(left, text=field.label, font=self._font(bold=True), text_color=T.TEXT, anchor="w").pack(anchor="w")
        note = field.help + ("  (applies after restart)" if field.restart else "")
        if note.strip():
            ctk.CTkLabel(left, text=note.strip(), font=self._font(T.SMALL_SIZE), text_color=T.MUTED, anchor="w").pack(anchor="w")

        if field.kind == "choice":
            menu = ctk.CTkOptionMenu(card, values=self.model.labels(field), width=260, font=self._font(),
                                     fg_color=T.BG, button_color=T.BORDER, button_hover_color=T.ACCENT,
                                     dropdown_fg_color=T.PANEL, dropdown_hover_color=T.PANEL_HOVER,
                                     dropdown_text_color=T.TEXT, text_color=T.TEXT,
                                     command=lambda label, f=field: self._changed(self.model.set_choice(f, label)))
            menu.set(self.model.current_label(field))
            menu.grid(row=row, column=1, padx=18, pady=9, sticky="e")
            field_widget = menu
        elif field.kind == "toggle":
            switch = ctk.CTkSwitch(card, text="", progress_color=T.ACCENT, button_color=T.TEXT, fg_color=T.BORDER,
                                   command=lambda: None)
            switch.configure(command=lambda f=field, s=switch: self._changed(self.model.set_value(f, bool(s.get()))))
            if self.model.current_value(field):
                switch.select()
            switch.grid(row=row, column=1, padx=18, pady=9, sticky="e")
            field_widget = switch
        else:
            entry = ctk.CTkEntry(card, width=260, font=self._font(), fg_color=T.BG, border_color=T.BORDER,
                                 text_color=T.TEXT, placeholder_text=field.placeholder)
            current = self.model.current_value(field)
            if current:
                entry.insert(0, str(current))
            commit = lambda _e=None, f=field, w=entry: self._changed(self.model.set_value(f, w.get()))
            entry.bind("<Return>", commit)
            entry.bind("<FocusOut>", commit)
            entry.grid(row=row, column=1, padx=18, pady=9, sticky="e")
            field_widget = entry
        setattr(self, "_w_" + field.key.replace(".", "_"), field_widget)

        if row:
            pass

    def _build_try_box(self, frame, row):
        ctk = self.ctk
        box = self._card(frame)
        box.grid(row=row, column=0, sticky="ew", pady=(16, 0))
        box.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(box, text="Try a command (nothing is pressed)", font=self._font(bold=True), text_color=T.ACCENT,
                     anchor="w").grid(row=0, column=0, padx=18, pady=(12, 0), sticky="w")
        self.try_entry = ctk.CTkEntry(box, font=self._font(), fg_color=T.BG, border_color=T.BORDER, text_color=T.TEXT,
                                      placeholder_text="e.g. could you please put the wheels down")
        self.try_entry.grid(row=1, column=0, padx=18, pady=8, sticky="ew")
        self.try_entry.bind("<Return>", lambda _e: self.try_command())
        ctk.CTkButton(box, text="Try", width=80, font=self._font(), fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
                      text_color=T.BG, command=self.try_command).grid(row=1, column=1, padx=(0, 18), pady=8)
        self.try_result = ctk.CTkLabel(box, text="", font=self._font(T.SMALL_SIZE), text_color=T.MUTED, anchor="w",
                                       justify="left", wraplength=560)
        self.try_result.grid(row=2, column=0, columnspan=2, padx=18, pady=(0, 12), sticky="w")

    # ------------------------------------------------------------------ actions
    def _controls_result(self, text, colour=None):
        label = getattr(self, "try_result", None)
        if label is not None:
            label.configure(text=text, text_color=colour or T.MUTED)
        self.save_note.configure(text=text.splitlines()[0][:110] if text else "", text_color=colour or T.MUTED)

    def try_command(self):
        runner = self.app.ensure_commands()
        if runner is None:
            self._controls_result("Voice commands could not start. Check the log.", T.BAD)
            return
        lines = runner.explain(self.try_entry.get())
        self._controls_result("\n".join(lines), T.TEXT)

    def check_keys(self):
        runner = self.app.ensure_commands()
        if runner is None:
            self._controls_result("Voice commands could not start. Check the log.", T.BAD)
            return
        working, problems = runner.binding_report()
        path = runner.book.path
        head = "%d commands have a keyboard key%s." % (working, " (from %s)" % path.name if path else "")
        foot = getattr(runner.book, "foot_path", None)
        if foot is not None:
            head += "\nOn-foot keys are read from %s (you use a different preset on foot)." % foot.name
        else:
            head += "\nOn-foot keys are read from the same file. If your on-foot controls use another preset, type its name on the On foot page."
        try:
            from control import binds as _binds
            head += "\n" + "\n".join(_binds.describe_folder(runner.book.folder))
        except Exception:
            pass
        try:
            import time as _time
            if path:
                head += "\nThat file was last saved by Elite at %s. If you changed keys just now, press APPLY in Elite's controls screen, then check again." % \
                    _time.strftime("%H:%M on %d %b", _time.localtime(path.stat().st_mtime))
        except OSError:
            pass
        if problems:
            head += "\n\nCommands she cannot press (each needs a KEYBOARD key, a chord like [T]+[B] is fine):\n- " + "\n- ".join(
                "%s" % why for _label, why in problems)
        clashes = runner.binding_conflicts()
        if clashes:
            head += "\n\nKeys that clash (Elite may do the wrong thing):\n- " + "\n- ".join(clashes)
        else:
            head += "\nNo key clashes found."
        try:
            from core.logger import get_logger
            get_logger("controls").info("Key check:\n%s", head)         # the whole report, in case the box is too small to show it
        except Exception:
            pass
        self._controls_result(head, T.GOOD if not (problems or clashes) else T.WARN)

    def scan_joysticks(self):
        reader = self.app.ensure_buttons()
        if reader is None:
            self._controls_result("Joystick reading only works on Windows.", T.WARN)
            return
        devices = reader.devices(force=True)
        if not devices:
            self._controls_result("No joystick found. Plug it in, then press this again.", T.WARN)
            return
        names = ", ".join(("%s [HOTAS]" if d.is_hotas() else "%s") % d.name for d in devices)
        self._controls_result("Found: " + names, T.GOOD)

    def show_memories(self):
        self._controls_result(self.app.memory_text(), T.GOOD)

    def forget_memories(self):
        from tkinter import messagebox
        if not messagebox.askyesno("Forget everything", "Delete ALL of her memories and the hours-together count? This cannot be undone."):
            return
        self._controls_result(self.app.forget_memories(), T.WARN)

    def copy_log(self):
        """Puts the end of logs/starling.log on the clipboard, so you can paste it into a chat when something is not working."""
        from core import paths
        try:
            lines = (paths.LOGS_DIR / "starling.log").read_text(encoding="utf-8", errors="replace").splitlines()[-300:]
            text = "\n".join(lines)
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.save_note.configure(text="Copied the last %d log lines. Paste them into the chat." % len(lines), text_color=T.GOOD)
        except OSError:
            self.save_note.configure(text="I could not find the log file yet.", text_color=T.WARN)

    def check_updates(self):
        """Updates page: look on GitHub (in the background) and say what was found."""
        import threading
        service = self.app.ensure_updates()
        self._controls_result("Checking GitHub...", T.WARN)

        def work():
            text = service.check()
            self.root.after(0, lambda: self._controls_result(text, T.GOOD))
        threading.Thread(target=work, name="update-now", daemon=True).start()

    def nav_plot(self, use_entry=True):
        """Navigation page: plot a neutron route without speaking."""
        typed = ""
        if use_entry and getattr(self, "nav_entry", None) is not None:
            typed = self.nav_entry.get().strip()
            if not typed:
                self._controls_result("Type a system name in the box first.", T.WARN)
                return
        self._controls_result(self.app.plot_route_now(typed), T.GOOD)

    def test_honk(self):
        """Exploration page: honk once, 4 seconds from now, so you can click back into Elite. She says what happened."""
        self._controls_result(self.app.honk_now(), T.WARN)

    def nav_next(self):
        self._controls_result(self.app.plot_next_now(), T.WARN)

    def nav_clear(self):
        self._controls_result(self.app.clear_route_now(), T.MUTED)

    def record_buttons(self):
        """Watches the buttons you press for a few seconds and saves a report into the recordings folder."""
        reader = self.app.ensure_buttons()
        if reader is None:
            self._controls_result("Button reading only works on Windows.", T.WARN)
            return
        if getattr(self, "_recording", False):
            return
        self._recording = True
        import threading
        seconds = int(self.model.settings.get("recorder.seconds", 20) or 20)
        count = int(self.model.settings.get("recorder.countdown", 5) or 5)
        say = lambda text, colour=None: self.root.after(0, lambda: self._controls_result(text, colour))
        self._controls_result("Recording starts in %d seconds. Go to Elite and do your button presses." % count, T.WARN)

        def work():
            try:
                from control.record_buttons import record_and_save
                txt, recording = record_and_save(
                    self.app, reader, "dashboard", seconds, count=count, out=lambda t: say(t.strip(), T.WARN),
                    flush=lambda: None)
                presses = sum(1 for e in recording.events if e["type"] == "down")
                say("Recorded %d button presses. Saved: %s  (send me that file)" % (presses, txt), T.GOOD)
            except Exception as error:
                self.app.log.exception("Recording failed")
                say("The recording failed: %s" % error, T.BAD)
            finally:
                self._recording = False
        threading.Thread(target=work, name="record-buttons", daemon=True).start()

    def learn_button(self):
        reader = self.app.ensure_buttons()
        if reader is None:
            self._controls_result("Button reading only works on Windows.", T.WARN)
            return
        self._controls_result("Press the key or button you want to use for push-to-talk now (6 seconds)...", T.WARN)
        self.root.update_idletasks()
        import threading

        def work():
            spec = reader.learn(seconds=6.0)
            self.root.after(0, lambda: self._learned(spec, reader))
        threading.Thread(target=work, name="learn", daemon=True).start()

    def _learned(self, spec, reader):
        if not spec:
            self._controls_result("Nothing was pressed. Try again.", T.WARN)
            return
        field = self.model.field("ptt.button")
        self._changed(self.model.set_value(field, spec))
        entry = getattr(self, "_w_ptt_button", None)
        if entry is not None:
            entry.delete(0, "end")
            entry.insert(0, spec)
        from control.inputs import describe
        note = "Push-to-talk button: " + describe(spec, reader.devices())
        if self.model.settings.get("ptt.mode", "off") == "off":
            note += ".  Now set 'Push-to-talk' above to Hold or Toggle."
        self._controls_result(note + "  (Save settings to keep it.)", T.GOOD)

    def show(self, page_id):
        if self.current:
            self.page_frames[self.current].grid_forget()
            self.nav_buttons[self.current].configure(fg_color="transparent", text_color=T.MUTED, border_color=T.BORDER_GLOW)
        self.current = page_id
        self.page_frames[page_id].grid(row=0, column=0, sticky="nsew")
        self.nav_buttons[page_id].configure(fg_color=T.PANEL, text_color=T.ACCENT, border_color=T.ACCENT)
        if page_id == "home":
            self._refresh_home()
        self._draw_stars()
        if page_id == "voice":
            self._start_voice_poll()

    def _changed(self, did_change):
        if did_change:
            self._update_note()

    def _update_note(self):
        if self.model.restart_needed():
            self.save_note.configure(text="Restart the app for some changes to take effect.", text_color=T.WARN)
        elif self.model.dirty():
            self.save_note.configure(text="Unsaved changes", text_color=T.WARN)
        else:
            self.save_note.configure(text="", text_color=T.MUTED)

    def save(self):
        ok, why = self.model.save()
        if ok:
            suffix = " Restart the app for some changes to take effect." if self.model.restart_needed() else ""
            self.save_note.configure(text="Saved." + suffix, text_color=T.GOOD)
        else:
            self.save_note.configure(text=why, text_color=T.BAD)

    def prepare_voice(self):
        self._controls_result(self.app.prepare_voice_now(), T.GOOD)
        self._start_voice_poll()

    # ---- the "Prepare her voice" progress bar ----
    def _build_voice_progress(self, frame, row):
        ctk = self.ctk
        box = ctk.CTkFrame(frame, fg_color=T.BG, corner_radius=0)
        box.grid(row=row, column=0, sticky="ew", pady=(16, 0))
        box.grid_columnconfigure(0, weight=1)
        self.voice_bar = ctk.CTkProgressBar(box, height=14, corner_radius=7, fg_color=T.PANEL, progress_color=T.ACCENT,
                                            border_width=1, border_color=T.BORDER)
        self.voice_bar.set(0)
        self.voice_bar.grid(row=0, column=0, sticky="ew")
        self.voice_label = ctk.CTkLabel(box, text="", font=self._font(T.SMALL_SIZE), text_color=T.MUTED, anchor="w", justify="left")
        self.voice_label.grid(row=1, column=0, sticky="w", pady=(6, 0))
        self._voice_poll = None

    @staticmethod
    def _minutes_text(seconds):
        if seconds is None:
            return ""
        if seconds < 90:
            return " - under a minute left"
        return " - about %d minutes left" % round(seconds / 60.0)

    def _start_voice_poll(self):
        if getattr(self, "_voice_poll", "none") is None and self.current == "voice":
            self._voice_poll = self.root.after(0, self._poll_voice)

    def _poll_voice(self):
        self._voice_poll = None
        warmer = getattr(self.app, "warmer", None)
        bar = getattr(self, "voice_bar", None)
        if bar is None or self.current != "voice":
            return
        if warmer is None:
            self.voice_label.configure(text="Her voice is not running, so there is nothing to prepare.")
            return
        done, total, left = warmer.progress()
        if total:
            bar.set(done / float(total))
        finished = warmer.finished or (total and done >= total)
        if finished:
            bar.set(1.0 if total else 0)
            self.voice_label.configure(text=warmer.status(), text_color=T.GOOD)
            return                                                   # nothing more to watch
        if total:
            self.voice_label.configure(text="Preparing her voice: %d of %d lines ready (%d%%)%s" % (
                done, total, round(100.0 * done / total), self._minutes_text(left)), text_color=T.ACCENT)
        else:
            self.voice_label.configure(text=warmer.status(), text_color=T.MUTED)
        self._voice_poll = self.root.after(600, self._poll_voice)

    def test_voice(self):
        speech = self.app.speech
        if speech is None:
            self.save_note.configure(text="Her voice is switched off (turn on 'She speaks aloud' first and restart).",
                                     text_color=T.WARN)
            return
        speech.say(random.choice(TEST_LINES), priority="normal", event_name="dashboard.test")
        self.save_note.configure(text="Playing a test line...", text_color=T.MUTED)

    def reset_mood(self):
        mood = getattr(self.app, "mood", None)
        if mood is None:
            self.save_note.configure(text="Mood only works while her voice is on.", text_color=T.WARN)
            return
        mood.reset()
        self.save_note.configure(text="Her mood is back to neutral.", text_color=T.GOOD)

    def refresh_mics(self, page):
        for field in page.fields:
            if field.key == "stt.microphone":
                menu = getattr(self, "_w_stt_microphone", None)
                self.model.choices(field, refresh=True)
                if menu is not None:
                    menu.configure(values=self.model.labels(field))
                    menu.set(self.model.current_label(field))
                self.save_note.configure(text="Microphone list updated.", text_color=T.GOOD)

    def _window_moved(self, event=None):
        if event is None or event.widget is self.root:
            self._busy_until = time.monotonic() + 0.4

    def _tick(self):
        if time.monotonic() < self._busy_until:                      # being dragged: do nothing this second
            self.root.after(300, self._tick)
            return
        try:
            self._update_header()
            if self.current == "home":
                self._refresh_home()
            elif self.current == "navigation":
                self._sync_bookmarks()
        except Exception:
            log.exception("Dashboard refresh failed")
        self.root.after(REFRESH_MS, self._tick)

    def close(self):
        if self.model.dirty():
            self.model.save()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def run_dashboard(app):
    """Open the window. Returns an exit code."""
    try:
        import customtkinter  # noqa: F401
    except ImportError:
        print(customtkinter_missing_message())
        return 1
    Dashboard(app).run()
    return 0
