"""
The "What she knows about you" window: everything she has kept, grouped, with a Forget button on every line you can forget one by one.
The list itself comes from memory/knowledge.py (tested); this file only draws it with customtkinter, in the dashboard's colours.
Opening it again just brings the open one to the front. Nothing here ever adds or changes what she knows: it only forgets what you press.
"""
from core.logger import get_logger
from ui import theme as T

log = get_logger("knowledge_window")

HINTS = {"You told me": "Things you said about yourself. Say 'forget that I like pizza' and she does the same.",
         "People": "People you told her about (say 'who do you know?').",
         "Moments": "Records, deaths, big missions and firsts she may bring up when you log in.",
         "Habits": "What she has noticed you keep doing.",
         "Sessions": "A one-line record of each recent play session. The newest is her 'last time we...' at login.",
         "Totals": "Counts kept since she started."}


class KnowledgeWindow:
    def __init__(self, dashboard):
        self.dash = dashboard
        self.ctk = dashboard.ctk
        self.window = None
        self.body = None

    def open(self):
        try:
            if self.window is not None and self.window.winfo_exists():
                self.window.deiconify()
                self.window.lift()
                self.refresh()
                return
        except Exception:
            self.window = None
        ctk = self.ctk
        window = ctk.CTkToplevel(self.dash.root)
        window.title("What she knows about you")
        window.geometry("640x640")
        window.minsize(420, 320)
        window.configure(fg_color=T.BG)
        self.window = window
        top = ctk.CTkLabel(window, text="What she knows about you", font=self.dash._font(T.HEADING_SIZE, True, head=True), text_color=T.ACCENT, anchor="w")
        top.pack(fill="x", padx=18, pady=(16, 2))
        ctk.CTkLabel(window, text="All of this is kept on your computer. Press Forget on a line and she drops it for good.", font=self.dash._font(T.SMALL_SIZE),
                     text_color=T.MUTED, anchor="w", justify="left", wraplength=580).pack(fill="x", padx=18, pady=(0, 8))
        self.body = ctk.CTkScrollableFrame(window, fg_color=T.BG, corner_radius=0)
        self.body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.refresh()
        try:
            window.after(200, window.lift)
        except Exception:
            pass

    def refresh(self):
        ctk = self.ctk
        for child in list(self.body.winfo_children()):
            child.destroy()
        try:
            groups = self.dash.app.knowledge().grouped()
        except Exception:
            log.exception("Could not read what she knows")
            groups = []
        if not groups:
            ctk.CTkLabel(self.body, text="She hasn't learned anything about you yet. Tell her, e.g. 'I love pizza', or just fly with her for a while.",
                         font=self.dash._font(), text_color=T.MUTED, anchor="w", justify="left", wraplength=560).pack(fill="x", padx=10, pady=14)
            return
        for group, entries in groups:
            ctk.CTkLabel(self.body, text=" ".join(group.upper()), font=self.dash._font(T.SMALL_SIZE, True, head=True), text_color=T.ACCENT_DIM,
                         anchor="w").pack(fill="x", padx=10, pady=(14, 0))
            ctk.CTkLabel(self.body, text=HINTS.get(group, ""), font=self.dash._font(T.SMALL_SIZE), text_color=T.MUTED, anchor="w", justify="left",
                         wraplength=560).pack(fill="x", padx=10, pady=(0, 4))
            for entry in entries:
                row = ctk.CTkFrame(self.body, fg_color=T.PANEL, corner_radius=8, border_width=1, border_color=T.BORDER)
                row.pack(fill="x", padx=8, pady=3)
                row.grid_columnconfigure(0, weight=1)
                ctk.CTkLabel(row, text=entry.text, font=self.dash._font(), text_color=T.TEXT, anchor="w", justify="left",
                             wraplength=470).grid(row=0, column=0, sticky="w", padx=12, pady=8)
                if entry.can_forget:
                    ctk.CTkButton(row, text="Forget", width=74, height=28, font=self.dash._font(T.SMALL_SIZE), fg_color=T.PANEL, border_width=1,
                                  border_color=T.BAD, hover_color=T.PANEL_HOVER, text_color=T.BAD, corner_radius=6,
                                  command=lambda e=entry: self.forget(e)).grid(row=0, column=1, padx=10)

    def forget(self, entry):
        try:
            self.dash.app.knowledge().forget(entry)
        except Exception:
            log.exception("Could not forget that")
        self.refresh()
