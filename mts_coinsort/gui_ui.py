"""Tkinter GUI for MTS CoinSort.

This is intentionally a practical phase-1 GUI: it uses the existing storage,
Numista indexes, session CSV format, and sorting helpers from the refactor while
adding a clickable/numpad-friendly desktop interface.
"""
from .wiring import load_and_wire

modules = load_and_wire()
state = modules["settings"].state
settings = modules["settings"]
storage = modules["storage"]
numista = modules["numista"]
sorting = modules["sorting"]
sound = modules["sound"]
utils = modules["utils"]
stats_mod = modules["statistics"]

import os
import json
import shutil
import webbrowser
import urllib.parse
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from datetime import datetime

# Banknote-inspired palette with a Numista-blue accent.
COLORS = {
    "bg": "#efe4cf",          # warm tan paper
    "panel": "#f8f1e4",       # lighter card
    "panel2": "#eadabb",      # darker tan card
    "green": "#2f5d3a",       # banknote green
    "green2": "#4f7f52",      # softer green
    "dark": "#203326",        # dark ink
    "muted": "#6b665c",
    "blue": "#1d72aa",        # Numista-ish blue
    "blue2": "#0f5f97",
    "gold": "#b58a3a",
    "danger": "#9f2d20",
    "danger_light": "#f4d7d2",
    "green_light": "#dcebd8",
    "blue_light": "#d9ebf7",
    "gold_light": "#f3e5c2",
    "white": "#ffffff",
}

FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI Semibold", 19)
FONT_BIG = ("Segoe UI Semibold", 13)


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


class CoinSortGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("MTS CoinSort")
        self.root.geometry("1160x760")
        self.root.minsize(1030, 660)
        self.root.configure(bg=COLORS["bg"])

        settings.load_settings()
        settings.ensure_app_dirs()
        self.numista_index, self.numista_files, self.numista_countries, self.denoms_by_country, self.numista_type_index = storage.load_numista_index()

        self.session = None
        self.current_type_options = []
        self.type_index = 0
        self.mint_index = 0
        self.keep_bulk = tk.BooleanVar(value=False)
        self.reject = tk.BooleanVar(value=False)
        self.reject_reason = tk.StringVar(value=state.REJECT_REASONS[0])
        self.year_var = tk.StringVar()
        self.notes_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready.")
        self.session_notes_var = tk.StringVar()
        self.focus_widgets = []
        self.editing_index = None

        self._configure_style()
        self._build_root()
        self.show_start()
        self._bind_keys()

    def _configure_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("Card.TFrame", background=COLORS["panel"], relief="flat")
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["dark"], font=FONT)
        style.configure("Card.TLabel", background=COLORS["panel"], foreground=COLORS["dark"], font=FONT)
        style.configure("Title.TLabel", background=COLORS["bg"], foreground=COLORS["green"], font=FONT_TITLE)
        style.configure("Big.TLabel", background=COLORS["panel"], foreground=COLORS["green"], font=FONT_BIG)
        style.configure("Muted.TLabel", background=COLORS["panel"], foreground=COLORS["muted"], font=FONT)
        # Give every button the same modern shape/padding instead of the OS-gray default.
        style.configure("TButton", font=FONT_BOLD, foreground=COLORS["dark"], background=COLORS["panel2"], borderwidth=1, padding=(12, 8))
        style.map("TButton", background=[("active", "#f3e6cc"), ("pressed", "#d8c49e")])
        style.configure("Accent.TButton", font=FONT_BOLD, foreground=COLORS["white"], background=COLORS["green"], borderwidth=0, padding=(12, 8))
        style.map("Accent.TButton", background=[("active", COLORS["green2"]), ("pressed", COLORS["dark"])])
        style.configure("Blue.TButton", font=FONT_BOLD, foreground=COLORS["white"], background=COLORS["blue"], borderwidth=0, padding=(12, 8))
        style.map("Blue.TButton", background=[("active", COLORS["blue2"]), ("pressed", COLORS["dark"])])
        style.configure("Danger.TButton", font=FONT_BOLD, foreground=COLORS["white"], background=COLORS["danger"], borderwidth=0, padding=(12, 8))
        style.map("Danger.TButton", background=[("active", "#b13b2d"), ("pressed", COLORS["dark"])])
        style.configure("TEntry", fieldbackground=COLORS["white"], foreground=COLORS["dark"], padding=7)
        style.configure("TCombobox", fieldbackground=COLORS["white"], foreground=COLORS["dark"], padding=7)
        style.configure("Treeview", font=("Segoe UI", 9), rowheight=27, background=COLORS["white"], fieldbackground=COLORS["white"], foreground=COLORS["dark"])
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background=COLORS["green"], foreground=COLORS["white"])

    def _build_root(self):
        self.shell = ttk.Frame(self.root, style="TFrame", padding=18)
        self.shell.pack(fill="both", expand=True)
        self.header = ttk.Frame(self.shell, style="TFrame")
        self.header.pack(fill="x", pady=(0, 12))
        ttk.Label(self.header, text="MTS CoinSort", style="Title.TLabel").pack(side="left")
        ttk.Label(self.header, text="  banknote tan + green • Numista blue", style="TLabel", foreground=COLORS["blue"]).pack(side="left", padx=(8, 0), pady=(8, 0))
        self.main_area = ttk.Frame(self.shell, style="TFrame")
        self.main_area.pack(fill="both", expand=True)
        self.footer = ttk.Frame(self.shell, style="TFrame")
        self.footer.pack(fill="x", pady=(12, 0))
        ttk.Label(self.footer, textvariable=self.status_var, style="TLabel", foreground=COLORS["muted"]).pack(side="left")
        ttk.Label(self.footer, text="Numpad: digits year • +/− mint • . type • / reject • * keep • Enter save", style="TLabel", foreground=COLORS["blue"]).pack(side="right")

    def clear_main(self):
        for child in self.main_area.winfo_children():
            child.destroy()
        self.focus_widgets = []

    def card(self, parent, padding=14):
        frame = tk.Frame(parent, bg=COLORS["panel"], highlightbackground="#cfbd9a", highlightthickness=1, bd=0)
        inner = ttk.Frame(frame, style="Card.TFrame", padding=padding)
        inner.pack(fill="both", expand=True)
        return frame, inner


    def merged_country_options(self):
        """Countries from Numista CSV, learned Coin_Types.csv rows, and custom settings."""
        countries = set(self.numista_countries or [])
        try:
            countries.update(storage.cache_denoms_by_country().keys())
        except Exception:
            pass
        try:
            countries.update(settings.custom_denoms_by_country().keys())
        except Exception:
            pass
        return sorted([c for c in countries if str(c).strip()], key=lambda v: str(v).lower())

    def denom_options_for_country(self, country):
        """Denominations from CSV + cached API rows + custom settings for one country."""
        denom_set = set(self.denoms_by_country.get(country, []))
        try:
            denom_set.update(storage.cache_denoms_by_country().get(country, set()))
        except Exception:
            pass
        try:
            denom_set.update(settings.custom_denoms_by_country().get(country, set()))
        except Exception:
            pass
        return sorted(
            [d for d in denom_set if str(d).strip()],
            key=lambda label: (
                utils.split_denom_label(label)[1].lower(),
                utils.face_value_float_for_sort(utils.split_denom_label(label)[0]),
                utils.split_denom_label(label)[0],
            ),
        )

    def choice_from_country_denom(self, country, denom_label):
        custom = settings.find_custom_denom(country, denom_label)
        if custom:
            return custom
        face_value, currency = utils.split_denom_label(denom_label)
        return {"country": country, "denomination": denom_label, "currency": currency, "face_value": face_value}

    def add_custom_denom_dialog(self, parent=None, default_country=""):
        parent = parent or self.root
        country = simpledialog.askstring("Custom denomination", "Country:", initialvalue=default_country, parent=parent)
        if not country:
            return None
        face = simpledialog.askstring("Custom denomination", "Face value, example 0.01, 0.05, 0.25, 1.00:", parent=parent)
        if not face:
            return None
        currency = simpledialog.askstring("Custom denomination", "Currency label, example Dollar, Canadian Dollar, Peso, Euro:", parent=parent)
        if currency is None:
            return None
        default_label = utils.make_denom_label(face, currency)
        label = simpledialog.askstring("Custom denomination", "Display label:", initialvalue=default_label, parent=parent)
        if label is None:
            return None
        choice = settings.save_custom_denomination(country, face, currency, label or default_label)
        if choice:
            self.reload_numista_data()
            self.status_var.set(f"Added custom denomination: {choice['country']} | {choice['denomination']}")
        return choice

    def add_country_denom_from_numista_dialog(self, parent=None, default_country=""):
        """GUI equivalent of terminal Add country/denomination from Numista N#."""
        parent = parent or self.root
        if not str(state.NUMISTA_API_KEY or "").strip():
            messagebox.showwarning("Numista API key needed", "Add your Numista API key in Settings > Numista API first.", parent=parent)
            return None
        should_search = messagebox.askyesnocancel(
            "Numista search",
            "Open Numista search in your browser first?\n\nYes = open search page\nNo = I already know the N#\nCancel = stop",
            parent=parent,
        )
        if should_search is None:
            return None
        if should_search:
            try:
                webbrowser.open(numista.numista_country_denom_search_url(default_country))
            except Exception:
                pass
        row = self.add_numista_type_dialog(parent=parent, ask_search=False)
        if not row:
            return None
        choice = numista.cached_row_choice(row)
        if choice:
            self.reload_numista_data()
            return choice
        return None

    def set_session_choice(self, choice):
        if not self.session or not choice:
            return
        self.session["country"] = choice.get("country", self.session.get("country", ""))
        self.session["currency"] = choice.get("currency", self.session.get("currency", ""))
        self.session["face_value"] = utils.normalize_decimal(choice.get("face_value", self.session.get("face_value", "")))
        self.session["denomination"] = choice.get("denomination", "") or utils.make_denom_label(self.session["face_value"], self.session["currency"])
        self.session["numista_type_index"] = self.numista_type_index
        storage.save_session_meta(self.session)
        self.refresh_all()

    def show_start(self):
        self.clear_main()
        left_wrap, left = self.card(self.main_area, 20)
        left_wrap.pack(side="left", fill="both", expand=True, padx=(0, 10))
        right_wrap, right = self.card(self.main_area, 20)
        right_wrap.pack(side="right", fill="both", expand=True, padx=(10, 0))

        ttk.Label(left, text="Start sorting", style="Big.TLabel").pack(anchor="w")
        ttk.Label(left, text="Create a new session, pick a country/denomination, and start entering coins.", style="Muted.TLabel").pack(anchor="w", pady=(4, 18))
        ttk.Button(left, text="New Session", style="Accent.TButton", command=self.show_new_session).pack(fill="x", pady=5)
        ttk.Button(left, text="Resume Session", style="Blue.TButton", command=self.show_resume_session).pack(fill="x", pady=5)
        ttk.Button(left, text="Statistics", command=self.show_home_statistics).pack(fill="x", pady=(18, 5))
        ttk.Button(left, text="Export Data", command=self.show_export_dialog).pack(fill="x", pady=5)
        ttk.Button(left, text="Settings", command=self.show_settings).pack(fill="x", pady=5)
        ttk.Button(left, text="Open Data Folder", command=lambda: utils.open_folder(state.DATA_DIR)).pack(fill="x", pady=5)
        ttk.Button(left, text="Terminal Mode", command=self.run_terminal_note).pack(fill="x", pady=5)

        ttk.Label(right, text="Loaded data", style="Big.TLabel").pack(anchor="w")
        ttk.Label(right, text=f"Numista CSV files: {len(self.numista_files)}", style="Card.TLabel").pack(anchor="w", pady=(12, 2))
        ttk.Label(right, text=f"Owned coin keys: {len(self.numista_index)}", style="Card.TLabel").pack(anchor="w", pady=2)
        ttk.Label(right, text=f"Countries available: {len(self.numista_countries)}", style="Card.TLabel").pack(anchor="w", pady=2)
        ttk.Label(right, text=f"Data folder:\n{state.DATA_DIR}", style="Muted.TLabel", wraplength=470).pack(anchor="w", pady=(16, 0))
        ttk.Label(right, text="Tip: the GUI now includes API, statistics, export, hotkeys, roll quantities, CSV import, and previous-coin editing. Terminal mode is still available.", style="Muted.TLabel", wraplength=470).pack(anchor="w", pady=(18, 0))

    def run_terminal_note(self):
        messagebox.showinfo("Terminal mode", "Close this GUI and run:\n\npython MTS_Coin_Sort.py --terminal")

    def show_new_session(self):
        self.clear_main()
        wrap, frame = self.card(self.main_area, 20)
        wrap.pack(fill="both", expand=True)
        ttk.Label(frame, text="New sorting session", style="Big.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 14))

        name_var = tk.StringVar(value=datetime.now().strftime("Sort %Y-%m-%d"))
        type_var = tk.StringVar(value=state.SESSION_TYPES[0])
        countries = self.merged_country_options()
        country_var = tk.StringVar(value=countries[0] if countries else "")
        denom_var = tk.StringVar()
        notes_var = tk.StringVar()
        roll_mode_var = tk.StringVar(value="none")
        roll_qty_var = tk.StringVar(value="")

        def refresh_denoms(*_):
            labels = self.denom_options_for_country(country_var.get())
            denom_combo["values"] = labels
            denom_var.set(labels[0] if labels else "")
            refresh_roll_qty()

        def refresh_roll_qty(*_):
            if type_var.get() != "Coin roll hunt":
                roll_mode_var.set("none")
                return
            choice = self.choice_from_country_denom(country_var.get(), denom_var.get()) if country_var.get() and denom_var.get() else None
            if choice:
                qty = sorting.get_roll_quantity_for_choice(choice)
                if qty and not roll_qty_var.get().strip():
                    roll_qty_var.set(str(qty))

        def add_from_numista():
            choice = self.add_country_denom_from_numista_dialog(default_country=country_var.get())
            if choice:
                countries = self.merged_country_options()
                country_combo["values"] = countries
                country_var.set(choice["country"])
                refresh_denoms()
                denom_var.set(choice["denomination"])
                refresh_roll_qty()

        def add_custom():
            choice = self.add_custom_denom_dialog(default_country=country_var.get())
            if choice:
                countries = self.merged_country_options()
                country_combo["values"] = countries
                country_var.set(choice["country"])
                refresh_denoms()
                denom_var.set(choice["denomination"])
                refresh_roll_qty()

        ttk.Label(frame, text="Session name", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        name_entry = ttk.Entry(frame, textvariable=name_var)
        name_entry.grid(row=1, column=1, columnspan=3, sticky="ew", pady=5)

        ttk.Label(frame, text="Session type", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=5)
        type_combo = ttk.Combobox(frame, textvariable=type_var, values=state.SESSION_TYPES, state="readonly")
        type_combo.grid(row=2, column=1, sticky="ew", pady=5)

        ttk.Label(frame, text="Country", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=5)
        country_combo = ttk.Combobox(frame, textvariable=country_var, values=countries, state="readonly")
        country_combo.grid(row=3, column=1, sticky="ew", pady=5)
        ttk.Button(frame, text="Add from N#", style="Blue.TButton", command=add_from_numista).grid(row=3, column=2, sticky="ew", padx=(10, 0), pady=5)
        ttk.Button(frame, text="Add custom", command=add_custom).grid(row=3, column=3, sticky="ew", padx=(8, 0), pady=5)

        ttk.Label(frame, text="Denomination", style="Card.TLabel").grid(row=4, column=0, sticky="w", pady=5)
        denom_combo = ttk.Combobox(frame, textvariable=denom_var, state="readonly")
        denom_combo.grid(row=4, column=1, columnspan=3, sticky="ew", pady=5)
        country_combo.bind("<<ComboboxSelected>>", refresh_denoms)
        denom_combo.bind("<<ComboboxSelected>>", refresh_roll_qty)
        refresh_denoms()

        ttk.Label(frame, text="Session notes", style="Card.TLabel").grid(row=5, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=notes_var).grid(row=5, column=1, columnspan=3, sticky="ew", pady=5)

        ttk.Label(frame, text="CRH roll mode", style="Card.TLabel").grid(row=6, column=0, sticky="w", pady=5)
        roll_mode_combo = ttk.Combobox(frame, textvariable=roll_mode_var, values=["none", "automatic", "manual"], state="readonly")
        roll_mode_combo.grid(row=6, column=1, sticky="ew", pady=5)
        ttk.Label(frame, text="Roll quantity", style="Card.TLabel").grid(row=6, column=2, sticky="e", padx=(16, 8), pady=5)
        ttk.Entry(frame, textvariable=roll_qty_var, width=10).grid(row=6, column=3, sticky="ew", pady=5)
        type_combo.bind("<<ComboboxSelected>>", refresh_roll_qty)

        button_row = ttk.Frame(frame, style="Card.TFrame")
        button_row.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(22, 0))
        ttk.Button(button_row, text="Back", command=self.show_start).pack(side="left")
        ttk.Button(button_row, text="Start Session", style="Accent.TButton", command=lambda: self.start_new_session(name_var, type_var, country_var, denom_var, roll_mode_var, roll_qty_var, notes_var)).pack(side="right")

        for i in range(4):
            frame.columnconfigure(i, weight=1 if i in (1, 3) else 0)
        self.focus_widgets = [name_entry, type_combo, country_combo, denom_combo, roll_mode_combo]
        name_entry.focus_set()

    def start_new_session(self, name_var, type_var, country_var, denom_var, roll_mode_var, roll_qty_var, notes_var=None):
        name = name_var.get().strip() or "Untitled Session"
        country = country_var.get().strip()
        denom = denom_var.get().strip()
        if not country or not denom:
            messagebox.showwarning("Missing selection", "Select a country and denomination first.")
            return
        face_value, currency = utils.split_denom_label(denom)
        path = storage.session_path(name)
        roll_mode = roll_mode_var.get() if type_var.get() == "Coin roll hunt" else ""
        if roll_mode == "none":
            roll_mode = ""
        roll_qty = roll_qty_var.get().strip()
        if type_var.get() == "Coin roll hunt" and roll_mode and not roll_qty:
            saved_qty = sorting.get_roll_quantity_for_choice({"country": country, "face_value": face_value, "currency": currency})
            roll_qty = str(saved_qty or "")
        self.session = {
            "session_name": name,
            "session_type": type_var.get(),
            "country": country,
            "denomination": denom,
            "currency": currency,
            "face_value": face_value,
            "path": path,
            "log": [],
            "session_notes": notes_var.get().strip() if notes_var is not None else "",
            "numista_index": self.numista_index,
            "numista_csv_count": len(self.numista_files),
            "numista_coin_count": len(self.numista_index),
            "numista_countries": self.numista_countries,
            "denoms_by_country": self.denoms_by_country,
            "numista_type_index": self.numista_type_index,
            "roll_mode": roll_mode,
            "roll_quantity": roll_qty,
            "current_roll": 1,
            "current_roll_count": 0,
        }
        storage.write_session_csv(path, [])
        storage.save_session_meta(self.session)
        self.show_sorting()

    def show_resume_session(self):
        self.clear_main()
        wrap, frame = self.card(self.main_area, 16)
        wrap.pack(fill="both", expand=True)
        ttk.Label(frame, text="Resume session", style="Big.TLabel").pack(anchor="w", pady=(0, 12))
        listbox = tk.Listbox(frame, bg=COLORS["white"], fg=COLORS["dark"], selectbackground=COLORS["blue"], selectforeground=COLORS["white"], font=("Segoe UI", 10), activestyle="none", height=18)
        listbox.pack(fill="both", expand=True)
        files = storage.list_sessions()
        for f in files:
            listbox.insert("end", f)
        row = ttk.Frame(frame, style="Card.TFrame")
        row.pack(fill="x", pady=(12, 0))
        ttk.Button(row, text="Back", command=self.show_start).pack(side="left")
        ttk.Button(row, text="Resume", style="Accent.TButton", command=lambda: self.resume_selected(files, listbox)).pack(side="right")
        listbox.bind("<Double-Button-1>", lambda _e: self.resume_selected(files, listbox))
        listbox.bind("<Return>", lambda _e: self.resume_selected(files, listbox))
        if files:
            listbox.selection_set(0)
            listbox.focus_set()

    def resume_selected(self, files, listbox):
        sel = listbox.curselection()
        if not sel:
            return
        filename = files[sel[0]]
        path = os.path.join(state.SESSIONS_DIR, filename)
        log = storage.load_session_csv(path)
        meta = storage.load_session_meta(path)
        first = log[0] if log else {}
        session_name = meta.get("session_name") or first.get("session_name") or filename.replace(".csv", "")
        session_type = first.get("session_type", "Bulk sorting")
        country = first.get("country", self.numista_countries[0] if self.numista_countries else "")
        denomination = first.get("denomination", "")
        face_value = first.get("face_value", "")
        currency = first.get("currency", "")
        if not denomination and country and self.denoms_by_country.get(country):
            denomination = self.denoms_by_country[country][0]
            face_value, currency = utils.split_denom_label(denomination)
        roll_quantity = first.get("roll_quantity", "") if first else ""
        current_roll, current_count = sorting.infer_roll_state(log, roll_quantity)
        self.session = {
            "session_name": session_name,
            "session_type": session_type,
            "country": country,
            "denomination": denomination,
            "currency": currency,
            "face_value": face_value,
            "path": path,
            "log": log,
            "session_notes": meta.get("session_notes", ""),
            "numista_index": self.numista_index,
            "numista_csv_count": len(self.numista_files),
            "numista_coin_count": len(self.numista_index),
            "numista_countries": self.numista_countries,
            "denoms_by_country": self.denoms_by_country,
            "numista_type_index": self.numista_type_index,
            "roll_mode": first.get("roll_mode", "") if first else "",
            "roll_quantity": roll_quantity,
            "current_roll": current_roll,
            "current_roll_count": current_count,
        }
        self.show_sorting()

    def show_sorting(self):
        self.clear_main()
        self.type_index = 0
        self.mint_index = 0
        self.editing_index = None
        self.keep_bulk.set(False)
        self.reject.set(False)
        self.year_var.set("")
        self.notes_var.set("")

        topbar = ttk.Frame(self.main_area, style="TFrame")
        topbar.pack(fill="x", pady=(0, 10))
        ttk.Button(topbar, text="← Sessions", command=self.show_start).pack(side="left")
        ttk.Button(topbar, text="Change Denomination", style="Blue.TButton", command=self.change_denom_dialog).pack(side="left", padx=8)
        ttk.Button(topbar, text="Session Notes", style="Blue.TButton", command=self.edit_session_notes).pack(side="left")
        ttk.Button(topbar, text="Add Numista Type", style="Blue.TButton", command=self.add_numista_type_dialog).pack(side="left", padx=8)
        ttk.Button(topbar, text="Statistics", style="Blue.TButton", command=self.show_current_statistics).pack(side="left")
        ttk.Button(topbar, text="Export", style="Blue.TButton", command=self.show_export_dialog).pack(side="left", padx=8)
        ttk.Button(topbar, text="Settings", style="Blue.TButton", command=self.show_settings).pack(side="left")
        ttk.Button(topbar, text="Open CSV Folder", command=lambda: utils.open_folder(state.SESSIONS_DIR)).pack(side="right")

        # Vertical workflow: active coin entry on top, session dashboard + recent coins below.
        top_wrap, entry = self.card(self.main_area, 16)
        top_wrap.pack(fill="x", expand=False, pady=(0, 10))
        bottom_wrap, dashboard = self.card(self.main_area, 14)
        bottom_wrap.pack(fill="both", expand=True)

        self.session_title = ttk.Label(entry, text="", style="Big.TLabel")
        self.session_title.grid(row=0, column=0, columnspan=8, sticky="w", pady=(0, 3))
        self.session_badges_label = ttk.Label(entry, text="", style="Muted.TLabel", wraplength=1040)
        self.session_badges_label.grid(row=1, column=0, columnspan=8, sticky="w", pady=(0, 2))
        self.session_notes_label = ttk.Label(entry, text="", style="Muted.TLabel", wraplength=1040)
        self.session_notes_label.grid(row=2, column=0, columnspan=8, sticky="w", pady=(0, 12))

        ttk.Label(entry, text="Current Coin", style="Big.TLabel").grid(row=3, column=0, columnspan=8, sticky="w", pady=(0, 8))

        year_vcmd = (self.root.register(self.validate_year_input), "%P")
        ttk.Label(entry, text="Year", style="Card.TLabel").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=5)
        self.year_entry = ttk.Entry(
            entry,
            textvariable=self.year_var,
            font=("Segoe UI Semibold", 22),
            width=8,
            justify="center",
            validate="key",
            validatecommand=year_vcmd,
        )
        self.year_entry.grid(row=4, column=1, sticky="ew", pady=5, padx=(0, 16))
        self.year_entry.bind("<KeyPress>", self._year_keypress)
        self.year_entry.bind("<KeyRelease>", lambda _e: self.refresh_type_options())

        ttk.Label(entry, text="Mint", style="Card.TLabel").grid(row=4, column=2, sticky="w", padx=(0, 8), pady=5)
        self.mint_combo = ttk.Combobox(entry, values=state.MINTS, state="readonly", width=14)
        self.mint_combo.grid(row=4, column=3, sticky="ew", pady=5, padx=(0, 8))
        self.mint_combo.set(state.MINTS[self.mint_index])
        self.mint_combo.bind("<<ComboboxSelected>>", self.on_mint_selected)
        ttk.Label(entry, text="+/− changes", style="Muted.TLabel").grid(row=4, column=4, sticky="w", padx=(0, 18), pady=5)

        ttk.Label(entry, text="Coin Type", style="Card.TLabel").grid(row=4, column=5, sticky="w", padx=(0, 8), pady=5)
        self.type_combo = ttk.Combobox(entry, state="readonly")
        self.type_combo.grid(row=4, column=6, sticky="ew", pady=5, padx=(0, 8))
        self.type_combo.bind("<<ComboboxSelected>>", self.on_type_selected)
        ttk.Label(entry, text=". changes", style="Muted.TLabel").grid(row=4, column=7, sticky="w", pady=5)

        ttk.Label(entry, text="Notes", style="Card.TLabel").grid(row=5, column=0, sticky="w", padx=(0, 8), pady=5)
        self.notes_entry = ttk.Entry(entry, textvariable=self.notes_var)
        self.notes_entry.grid(row=5, column=1, columnspan=7, sticky="ew", pady=5)

        self.coin_status_banner = tk.Frame(entry, bg=COLORS["panel2"], highlightbackground="#cfbd9a", highlightthickness=1)
        self.coin_status_banner.grid(row=6, column=0, columnspan=8, sticky="ew", pady=(12, 10))
        self.coin_status_title = tk.Label(
            self.coin_status_banner,
            text="NORMAL LOGGED COIN",
            bg=COLORS["panel2"],
            fg=COLORS["dark"],
            font=("Segoe UI Semibold", 12),
            anchor="w",
            padx=12,
            pady=8,
        )
        self.coin_status_title.pack(fill="x")
        self.coin_status_detail = tk.Label(
            self.coin_status_banner,
            text="No keep/reject status selected.",
            bg=COLORS["panel2"],
            fg=COLORS["muted"],
            font=FONT,
            anchor="w",
            padx=12,
            pady=4,
        )
        self.coin_status_detail.pack(fill="x")

        action_row = ttk.Frame(entry, style="Card.TFrame")
        action_row.grid(row=7, column=0, columnspan=8, sticky="ew", pady=(0, 8))
        self.keep_check = ttk.Button(action_row, text="Keep / Bulk  (*)", style="Blue.TButton", command=self.toggle_keep)
        self.keep_check.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.reject_check = ttk.Button(action_row, text="Reject  (/)", style="Danger.TButton", command=self.open_reject_reason_dialog)
        self.reject_check.pack(side="left", fill="x", expand=True, padx=(8, 8))
        self.reject_combo = ttk.Combobox(action_row, textvariable=self.reject_reason, values=state.REJECT_REASONS, state="readonly", width=24)
        self.reject_combo.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self.reject_combo.bind("<<ComboboxSelected>>", lambda _e: self.on_reject_toggle() if self.reject.get() else self.update_selection_buttons())

        ttk.Button(entry, text="Save Coin  (Enter)", style="Accent.TButton", command=self.save_coin).grid(row=8, column=0, columnspan=8, sticky="ew", pady=(8, 4))
        if self.session.get("session_type") == "Coin roll hunt" and self.session.get("roll_mode") in ("automatic", "manual"):
            ttk.Button(entry, text="Next Roll", style="Blue.TButton", command=self.next_roll).grid(row=9, column=0, columnspan=8, sticky="ew", pady=(6, 0))

        self.warning_label = ttk.Label(entry, text="", style="Muted.TLabel", wraplength=1040)
        self.warning_label.grid(row=10, column=0, columnspan=8, sticky="w", pady=(8, 0))

        for col in range(8):
            entry.columnconfigure(col, weight=1 if col in (1, 3, 6) else 0)

        dashboard_header = ttk.Frame(dashboard, style="Card.TFrame")
        dashboard_header.pack(fill="x")
        ttk.Label(dashboard_header, text="Session dashboard", style="Big.TLabel").pack(side="left")
        ttk.Label(dashboard_header, text="Recent saved coins on bottom", style="Muted.TLabel").pack(side="right")

        self.stat_tiles_frame = tk.Frame(dashboard, bg=COLORS["panel"])
        self.stat_tiles_frame.pack(fill="x", pady=(8, 8))
        self.stat_tiles = {}
        stat_defs = [("total", "Total"), ("today", "Today"), ("keep", "Keep"), ("reject", "Reject"), ("new", "New")]
        for i, (key, label) in enumerate(stat_defs):
            tile = tk.Frame(self.stat_tiles_frame, bg=COLORS["white"], highlightbackground="#cfbd9a", highlightthickness=1)
            tile.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0))
            tk.Label(tile, text=label, bg=COLORS["white"], fg=COLORS["muted"], font=("Segoe UI", 9), padx=8, pady=(5, 0)).pack(fill="x")
            value = tk.Label(tile, text="0", bg=COLORS["white"], fg=COLORS["green"], font=("Segoe UI Semibold", 18), padx=8, pady=(0, 5))
            value.pack(fill="x")
            self.stat_tiles[key] = value
            self.stat_tiles_frame.columnconfigure(i, weight=1)

        self.roll_status_label = ttk.Label(dashboard, text="", style="Muted.TLabel", wraplength=1040)
        self.roll_status_label.pack(anchor="w", fill="x", pady=(0, 8))

        recent_header = ttk.Frame(dashboard, style="Card.TFrame")
        recent_header.pack(fill="x", pady=(0, 4))
        ttk.Label(recent_header, text="Recently saved coins", style="Big.TLabel").pack(side="left")
        self.recent_count_label = ttk.Label(recent_header, text="0 sorted • showing last 40", style="Muted.TLabel")
        self.recent_count_label.pack(side="right")

        columns = ("year", "mint", "type", "status")
        self.recent_tree = ttk.Treeview(dashboard, columns=columns, show="headings", height=9)
        for col, text, width in [("year", "Year", 90), ("mint", "Mint", 95), ("type", "Type", 560), ("status", "Status", 180)]:
            self.recent_tree.heading(col, text=text)
            self.recent_tree.column(col, width=width, anchor="w")
        self.recent_tree.tag_configure("keep", background=COLORS["green_light"])
        self.recent_tree.tag_configure("reject", background=COLORS["danger_light"])
        self.recent_tree.tag_configure("new", background=COLORS["gold_light"])
        self.recent_tree.tag_configure("logged", background=COLORS["white"])
        self.recent_tree.pack(fill="both", expand=True, pady=(0, 8))
        self.recent_tree.bind("<Double-Button-1>", lambda _e: self.load_selected_recent_for_edit())

        recent_buttons = ttk.Frame(dashboard, style="Card.TFrame")
        recent_buttons.pack(fill="x")
        ttk.Button(recent_buttons, text="Undo Last Coin", style="Blue.TButton", command=self.undo_last_coin).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(recent_buttons, text="Edit Highlighted Coin", style="Blue.TButton", command=self.load_selected_recent_for_edit).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(recent_buttons, text="Delete Highlighted Coin", style="Danger.TButton", command=self.delete_selected_recent).pack(side="left", fill="x", expand=True, padx=(6, 0))

        self.focus_widgets = [self.year_entry, self.mint_combo, self.type_combo, self.notes_entry, self.keep_check, self.reject_check, self.recent_tree]
        self.update_selection_buttons()
        self.refresh_all()
        self.update_selection_buttons()
        self.year_entry.focus_set()

    def refresh_all(self):
        if not self.session:
            return
        self.session_title.configure(text=f"{self.session['session_name']}  •  {self.session.get('country','')}  •  {self.session.get('denomination','')}")
        if hasattr(self, "session_badges_label"):
            mode = self.session.get("session_type", "") or "Sorting"
            csv_count = self.session.get("numista_csv_count", len(self.numista_files))
            type_count = len(self.session.get("numista_type_index", {}) or {})
            auto_save = "Auto-save on"
            roll = ""
            if self.session.get("session_type") == "Coin roll hunt" and self.session.get("roll_mode"):
                roll = f"  •  Roll {self.session.get('current_roll', 1)}"
            self.session_badges_label.configure(text=f"{mode}  •  Numista CSVs: {csv_count}  •  learned types: {type_count}  •  {auto_save}{roll}")
        if hasattr(self, "session_notes_label"):
            note = self.session.get("session_notes", "")
            self.session_notes_label.configure(text=("Notes: " + note) if note else "No session notes saved.")
        self.refresh_type_options()
        self.refresh_stats()
        self.refresh_recent()
        self.update_warning()
        self.update_selection_buttons()

    def validate_year_input(self, proposed_value):
        """Allow only blank or 0-4 digits in the year field.

        This also blocks pasted text such as 2025++ or accidental hotkey
        characters from being accepted by the Entry widget.
        """
        return proposed_value == "" or (proposed_value.isdigit() and len(proposed_value) <= 4)

    def _year_keypress(self, event):
        """Prevent sorting hotkeys from typing into the year field.

        Tkinter Entry widgets receive normal characters before the global
        bind_all handlers can fully protect the field. Handling these keys on
        the Entry itself stops +, -, ., /, and * from becoming part of the year
        while still performing their numpad actions.
        """
        keysym = event.keysym
        char = event.char or ""

        key = self._event_key_value(event) if hasattr(self, "_event_key_value") else char
        if keysym in ("KP_Add", "plus") or settings.hotkey_matches(key, "mint_next"):
            self.next_mint()
            return "break"
        if keysym in ("KP_Subtract", "minus") or settings.hotkey_matches(key, "mint_previous"):
            self.prev_mint()
            return "break"
        if keysym in ("KP_Decimal", "period") or settings.hotkey_matches(key, "type_next"):
            self.next_type()
            return "break"
        if keysym in ("KP_Divide", "slash") or settings.hotkey_matches(key, "reject"):
            self.toggle_reject()
            return "break"
        if keysym in ("KP_Multiply", "asterisk") or settings.hotkey_matches(key, "keep_bulk"):
            self.toggle_keep()
            return "break"
        if settings.hotkey_matches(key, "save_quit"):
            self.confirm_leave_session()
            return "break"

        # Let command/navigation/editing keys through.
        allowed_keysyms = {
            "BackSpace", "Delete", "Left", "Right", "Home", "End",
            "Tab", "ISO_Left_Tab", "Shift_L", "Shift_R",
            "Control_L", "Control_R", "Alt_L", "Alt_R",
            "Caps_Lock", "Escape",
        }
        if keysym in allowed_keysyms:
            return None

        # Enter should save the coin, not insert anything.
        if keysym in ("Return", "KP_Enter"):
            self.save_coin()
            return "break"

        # Allow Ctrl-key shortcuts like Ctrl+A/C/V/X. Validation still blocks
        # pasted non-numeric text from landing in the field.
        if event.state & 0x4:
            return None

        # Numpad digits have keysyms like KP_0 through KP_9.
        if keysym.startswith("KP_") and keysym[3:].isdigit():
            return None

        # Normal digits are allowed; validation enforces the 4-character limit.
        if char.isdigit():
            return None

        # Block every other printable character from the year field.
        if char:
            return "break"

        return None

    def refresh_type_options(self):
        if not self.session or not hasattr(self, "type_combo"):
            return
        year = self.year_var.get().strip()
        mint = state.MINTS[self.mint_index]
        self.current_type_options = sorting.get_detected_type_options(self.session, year, mint)
        labels = []
        for opt in self.current_type_options:
            num = sorting.clean_numista_number(opt.get("numista_number", ""))
            label = opt.get("coin_type", "Unknown")
            if num:
                label += f"  •  N# {num}"
            note = opt.get("match_note", "")
            if note and note not in ("manual", "exact mint"):
                label += f"  •  {note}"
            labels.append(label)
        self.type_combo["values"] = labels
        if self.type_index >= len(labels):
            self.type_index = 0
        if labels:
            self.type_combo.current(self.type_index)
        self.update_warning()

    def update_warning(self):
        if not self.session or not hasattr(self, "warning_label"):
            return
        year = self.year_var.get().strip()
        warning = sorting.year_warning(self.session, year)
        if not warning and len(year) == 4 and year.isdigit():
            found = sorting.coin_exists_in_numista(self.numista_index, self.session, year, state.MINTS[self.mint_index])
            if not found:
                warning = "Possible new collection coin: not found in your Numista CSV. Save will ask to mark it as New Collection."
        self.warning_label.configure(text=warning)

    def refresh_stats(self):
        if not hasattr(self, "stat_tiles"):
            return
        total, today = sorting.session_counts(self.session.get("log", []))
        kept = sum(1 for c in self.session["log"] if sorting.boolish(c.get("keep_bulk", False)))
        rejected = sum(1 for c in self.session["log"] if sorting.boolish(c.get("reject", False)))
        new_collection = sum(1 for c in self.session["log"] if sorting.boolish(c.get("new_collection", False)))
        values = {
            "total": total,
            "today": today,
            "keep": kept,
            "reject": rejected,
            "new": new_collection,
        }
        for key, value in values.items():
            label = self.stat_tiles.get(key)
            if label is not None:
                label.configure(text=str(value))
        if hasattr(self, "roll_status_label"):
            if self.session.get("session_type") == "Coin roll hunt" and self.session.get("roll_mode"):
                self.roll_status_label.configure(
                    text=f"Roll {self.session.get('current_roll', 1)}  •  {self.session.get('current_roll_count', 0)}/{self.session.get('roll_quantity') or '?'} coins"
                )
            else:
                self.roll_status_label.configure(text="Bulk sorting session")

    def refresh_recent(self):
        if not hasattr(self, "recent_tree"):
            return
        rows = self.session.get("log", []) if self.session else []
        if hasattr(self, "recent_count_label"):
            self.recent_count_label.configure(text=f"{len(rows)} sorted • showing last {min(40, len(rows))}")
        self.recent_tree.delete(*self.recent_tree.get_children())
        for idx, coin in list(enumerate(rows))[-40:][::-1]:
            if sorting.boolish(coin.get("new_collection", False)):
                status = "New Collection"
                tag = "new"
            elif sorting.boolish(coin.get("reject", False)):
                reason = coin.get("reject_reason", "")
                status = f"Reject: {reason}" if reason else "Reject"
                tag = "reject"
            elif sorting.boolish(coin.get("keep_bulk", False)):
                status = "Keep/Bulk"
                tag = "keep"
            else:
                status = "Logged"
                tag = "logged"
            self.recent_tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(coin.get("year", ""), coin.get("mint", ""), coin.get("coin_type", ""), status),
                tags=(tag,),
            )

    def on_mint_selected(self, _event=None):
        value = self.mint_combo.get()
        self.mint_index = state.MINTS.index(value) if value in state.MINTS else 0
        self.type_index = 0
        self.refresh_type_options()

    def selected_type_option(self):
        """Return the currently selected coin type option, if one exists."""
        if not self.current_type_options:
            self.refresh_type_options()
        if not self.current_type_options:
            return None
        index = max(0, min(self.type_index, len(self.current_type_options) - 1))
        return self.current_type_options[index]

    def select_numista_row_option(self, row):
        """Select the GUI type option matching a saved Coin_Types.csv row."""
        if not row:
            return None
        target_num = sorting.clean_numista_number(row.get("numista_number", ""))
        if not target_num:
            return None
        self.refresh_type_options()
        for i, opt in enumerate(self.current_type_options):
            if sorting.clean_numista_number(opt.get("numista_number", "")) == target_num:
                self.type_index = i
                try:
                    self.type_combo.current(i)
                except Exception:
                    pass
                return opt
        return None

    def on_type_selected(self, _event=None):
        self.type_index = max(0, self.type_combo.current())
        self.handle_other_type_selected()

    def handle_other_type_selected(self):
        """OTHER no longer pops up while cycling types; save_coin handles it."""
        option = self.selected_type_option()
        if option and option.get("coin_type") == "OTHER":
            self.status_var.set("OTHER selected. Save Coin will offer Numista N# lookup, or you can save as OTHER.")

    def update_selection_buttons(self):
        """Make Keep/Bulk and Reject state impossible to miss."""
        keep_on = bool(self.keep_bulk.get())
        reject_on = bool(self.reject.get())
        if hasattr(self, "keep_check"):
            if keep_on:
                self.keep_check.configure(text="✓ KEEP / BULK SELECTED  (*)", style="Accent.TButton")
            else:
                self.keep_check.configure(text="Keep / Bulk  (*)", style="Blue.TButton")
        if hasattr(self, "reject_check"):
            if reject_on:
                reason = self.reject_reason.get() or state.REJECT_REASONS[0]
                self.reject_check.configure(text=f"✗ REJECT SELECTED: {reason}  (/)", style="Danger.TButton")
            else:
                self.reject_check.configure(text="Reject  (/)", style="Danger.TButton")
        if hasattr(self, "coin_status_banner"):
            if reject_on:
                bg = COLORS["danger_light"]
                title = "REJECT SELECTED"
                detail = f"Reason: {self.reject_reason.get() or state.REJECT_REASONS[0]}. Saving will mark this coin as rejected."
                fg = COLORS["danger"]
            elif keep_on:
                bg = COLORS["green_light"]
                title = "KEEP / BULK SELECTED"
                detail = "Saving will mark this coin as keep/bulk and clear reject."
                fg = COLORS["green"]
            else:
                bg = COLORS["panel2"]
                title = "NORMAL LOGGED COIN"
                detail = "No keep/reject status selected."
                fg = COLORS["dark"]
            for widget in (self.coin_status_banner, self.coin_status_title, self.coin_status_detail):
                try:
                    widget.configure(bg=bg)
                except Exception:
                    pass
            self.coin_status_title.configure(text=title, fg=fg)
            self.coin_status_detail.configure(text=detail, fg=COLORS["muted"])

    def update_keep_button_style(self):
        self.update_selection_buttons()

    def on_keep_toggle(self):
        if self.keep_bulk.get():
            self.reject.set(False)
        self.update_selection_buttons()

    def on_reject_toggle(self):
        if self.reject.get():
            self.keep_bulk.set(False)
        self.update_selection_buttons()

    def next_mint(self):
        self.mint_index = (self.mint_index + 1) % len(state.MINTS)
        self.mint_combo.set(state.MINTS[self.mint_index])
        self.type_index = 0
        self.refresh_type_options()

    def prev_mint(self):
        self.mint_index = (self.mint_index - 1) % len(state.MINTS)
        self.mint_combo.set(state.MINTS[self.mint_index])
        self.type_index = 0
        self.refresh_type_options()

    def next_type(self):
        if not self.current_type_options:
            self.refresh_type_options()
        if self.current_type_options:
            self.type_index = (self.type_index + 1) % len(self.current_type_options)
            self.type_combo.current(self.type_index)
            self.handle_other_type_selected()

    def _center_popup(self, win, width=520, height=380):
        """Center a Toplevel over the main window using plain Tk geometry."""
        try:
            self.root.update_idletasks()
            win.update_idletasks()
            root_x = self.root.winfo_rootx()
            root_y = self.root.winfo_rooty()
            root_w = max(1, self.root.winfo_width())
            root_h = max(1, self.root.winfo_height())
            x = root_x + max(0, (root_w - width) // 2)
            y = root_y + max(0, (root_h - height) // 2)
            win.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            win.geometry(f"{width}x{height}")

    def open_reject_reason_dialog(self):
        """Open a numpad-friendly reject reason picker.

        This intentionally uses a normal non-blocking Toplevel, like the
        Statistics window, instead of messagebox/simpledialog/grab_wait logic.
        That makes it behave consistently on Windows and Linux window managers.
        """
        if not self.session:
            return

        existing = getattr(self, "_reject_reason_window", None)
        try:
            if existing is not None and existing.winfo_exists():
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                return
        except Exception:
            pass

        reasons = list(state.REJECT_REASONS) + ["Clear Reject"]
        current_reason = self.reject_reason.get() if self.reject.get() else ""
        start_index = reasons.index(current_reason) if current_reason in reasons else 0

        win = tk.Toplevel(self.root)
        self._reject_reason_window = win
        win.title("Reject Reason")
        win.configure(bg=COLORS["bg"])
        win.transient(self.root)
        win.resizable(False, False)
        self._center_popup(win, 540, 390)

        outer = ttk.Frame(win, padding=16, style="TFrame")
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Reject reason", style="Title.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(
            outer,
            text="Use numpad + / - to choose a reason, then press Enter. Esc or Backspace cancels.",
            style="TLabel",
            wraplength=490,
        ).pack(anchor="w", pady=(0, 12))

        listbox = tk.Listbox(
            outer,
            bg=COLORS["white"],
            fg=COLORS["dark"],
            selectbackground=COLORS["danger"],
            selectforeground=COLORS["white"],
            font=("Segoe UI", 12),
            activestyle="none",
            height=min(10, len(reasons)),
            exportselection=False,
        )
        listbox.pack(fill="both", expand=True, pady=(0, 12))
        for reason in reasons:
            listbox.insert("end", reason)
        listbox.selection_set(start_index)
        listbox.activate(start_index)
        listbox.see(start_index)

        hint_var = tk.StringVar(value="Selected: " + reasons[start_index])
        ttk.Label(outer, textvariable=hint_var, style="Muted.TLabel").pack(anchor="w", pady=(0, 10))

        def current_index():
            sel = listbox.curselection()
            return int(sel[0]) if sel else 0

        def select_index(index):
            index = max(0, min(index, len(reasons) - 1))
            listbox.selection_clear(0, "end")
            listbox.selection_set(index)
            listbox.activate(index)
            listbox.see(index)
            hint_var.set("Selected: " + reasons[index])

        def move(delta):
            select_index((current_index() + delta) % len(reasons))
            return "break"

        def close():
            try:
                win.destroy()
            except Exception:
                pass
            if getattr(self, "_reject_reason_window", None) is win:
                self._reject_reason_window = None

        def confirm():
            reason = reasons[current_index()]
            if reason == "Clear Reject":
                self.reject.set(False)
                self.reject_reason.set(state.REJECT_REASONS[0])
                self.status_var.set("Reject cleared.")
                self.update_selection_buttons()
            else:
                self.reject.set(True)
                self.reject_reason.set(reason)
                self.keep_bulk.set(False)
                self.status_var.set(f"Reject reason selected: {reason}")
                self.update_selection_buttons()
            close()
            try:
                self.year_entry.focus_set()
            except Exception:
                pass
            return "break"

        def cancel():
            close()
            try:
                self.year_entry.focus_set()
            except Exception:
                pass
            return "break"

        button_row = ttk.Frame(outer, style="TFrame")
        button_row.pack(fill="x")
        ttk.Button(button_row, text="Cancel", command=cancel).pack(side="left")
        ttk.Button(button_row, text="Save Reason", style="Danger.TButton", command=confirm).pack(side="right")

        for widget in (win, listbox):
            widget.bind("<KP_Add>", lambda _e: move(1))
            widget.bind("<plus>", lambda _e: move(1))
            widget.bind("<Down>", lambda _e: move(1))
            widget.bind("<KP_Subtract>", lambda _e: move(-1))
            widget.bind("<minus>", lambda _e: move(-1))
            widget.bind("<Up>", lambda _e: move(-1))
            widget.bind("<Return>", lambda _e: confirm())
            widget.bind("<KP_Enter>", lambda _e: confirm())
            widget.bind("<Escape>", lambda _e: cancel())
            widget.bind("<BackSpace>", lambda _e: cancel())
            widget.bind("<Double-Button-1>", lambda _e: confirm())

        win.protocol("WM_DELETE_WINDOW", cancel)
        win.after(10, lambda: (win.deiconify(), win.lift(), listbox.focus_force()))

    def ask_missing_collection_action(self, year, mint_name):
        """Return 'new', 'normal', or None for a coin missing from Numista CSV."""
        win = tk.Toplevel(self.root)
        win.title("Possible New Collection Coin")
        win.configure(bg=COLORS["bg"])
        win.geometry("560x310")
        win.transient(self.root)
        win.grab_set()
        result = {"value": None}
        frame = ttk.Frame(win, padding=18, style="TFrame")
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Possible New Collection Coin", style="Title.TLabel").pack(anchor="w", pady=(0, 12))
        text = (
            f"{year}-{mint_name} was not found in your Numista CSV for:\n"
            f"{self.session.get('country', '')} | {self.session.get('denomination', '')}\n\n"
            "Mark it New Collection if you want it in the verify/set-aside bin. "
            "Use Save normally/bypass when the coin is damaged or you intentionally do not want to keep it."
        )
        ttk.Label(frame, text=text, style="TLabel", wraplength=510).pack(anchor="w", pady=(0, 16))
        row = ttk.Frame(frame, style="TFrame")
        row.pack(fill="x", pady=(8, 0))

        def choose(value):
            result["value"] = value
            win.destroy()

        ttk.Button(row, text="Mark New Collection", style="Accent.TButton", command=lambda: choose("new")).pack(fill="x", pady=4)
        ttk.Button(row, text="Save normally / bypass", style="Blue.TButton", command=lambda: choose("normal")).pack(fill="x", pady=4)
        ttk.Button(row, text="Cancel save", command=lambda: choose(None)).pack(fill="x", pady=4)
        win.bind("<Escape>", lambda _e: choose(None))
        self.root.wait_window(win)
        return result["value"]

    def save_coin(self):
        if not self.session:
            return
        year = self.year_var.get().strip()
        if len(year) != 4 or not year.isdigit():
            messagebox.showwarning("Year needed", "Enter a valid 4-digit year before saving.")
            return
        warn = sorting.year_warning(self.session, year)
        if warn and warn.startswith("Suspicious"):
            if not messagebox.askyesno("Suspicious year", warn + "\n\nSave anyway?"):
                return
        mint_name = state.MINTS[self.mint_index]
        options = self.current_type_options or sorting.get_detected_type_options(self.session, year, mint_name)
        option = options[max(0, min(self.type_index, len(options) - 1))]
        if option.get("coin_type") == "OTHER":
            response = messagebox.askyesnocancel(
                "OTHER coin type",
                "This coin type is not known locally yet.\n\n"
                "Do you want to open Numista search and add the type by N# before saving?\n\n"
                "Yes = search/add with Numista API\n"
                "No = save this coin as OTHER anyway\n"
                "Cancel = do not save",
                parent=self.root,
            )
            if response is None:
                return
            if response is True:
                row = self.add_numista_type_dialog()
                if not row:
                    return
                selected = self.select_numista_row_option(row)
                if selected:
                    option = selected
                else:
                    options = self.current_type_options or sorting.get_detected_type_options(self.session, year, mint_name)
                    option = options[max(0, min(self.type_index, len(options) - 1))]
                    if option.get("coin_type") == "OTHER":
                        if not messagebox.askyesno(
                            "Still listed as OTHER",
                            "The Numista type was saved, but it did not match the current year/mint/denomination.\n\nSave this coin as OTHER anyway?",
                            parent=self.root,
                        ):
                            return
        found = sorting.coin_exists_in_numista(self.numista_index, self.session, year, mint_name)
        editing = self.editing_index is not None
        old_coin = self.session["log"][self.editing_index] if editing and 0 <= self.editing_index < len(self.session["log"]) else None
        new_collection = False
        reject = bool(self.reject.get())
        keep_bulk = bool(self.keep_bulk.get())
        reject_reason = self.reject_reason.get() if reject else ""
        if reject and not reject_reason:
            reject_reason = state.REJECT_REASONS[0]
        if not found:
            action = self.ask_missing_collection_action(year, mint_name)
            if action is None:
                return
            if action == "new":
                new_collection = True
                reject = False
                keep_bulk = False
                reject_reason = ""

        roll_mode = self.session.get("roll_mode", "")
        roll_number = ""
        roll_coin_number = ""
        roll_quantity = self.session.get("roll_quantity", "") or ""
        if editing and old_coin:
            roll_number = old_coin.get("roll_number", "")
            roll_coin_number = old_coin.get("roll_coin_number", "")
            roll_quantity = old_coin.get("roll_quantity", roll_quantity)
            roll_mode = old_coin.get("roll_mode", roll_mode)
        elif self.session.get("session_type") == "Coin roll hunt" and roll_mode in ("automatic", "manual"):
            roll_number = int(self.session.get("current_roll", 1) or 1)
            roll_coin_number = int(self.session.get("current_roll_count", 0) or 0) + 1
            qty = _safe_int(roll_quantity, 0)
            if roll_mode == "manual" and qty and roll_coin_number > qty:
                response = messagebox.askyesnocancel("Roll limit reached", f"Roll {roll_number} already has {self.session.get('current_roll_count', 0)} coins.\n\nYes = start next roll and save this coin there.\nNo = save as extra coin in current roll.\nCancel = do not save.")
                if response is None:
                    return
                if response is True:
                    roll_number += 1
                    roll_coin_number = 1

        coin = sorting.make_coin(
            self.session["session_name"], self.session["session_type"], self.session.get("country", ""),
            self.session["denomination"], self.session.get("currency", ""), self.session.get("face_value", ""),
            year, self.mint_index, option, self.notes_var.get(), reject, reject_reason, keep_bulk,
            str(found), str(not found), new_collection, roll_mode, roll_number, roll_coin_number, roll_quantity,
        )
        if editing and old_coin is not None:
            # Preserve the original timestamp while updating the rest of the row.
            coin["timestamp"] = old_coin.get("timestamp", coin.get("timestamp", ""))
            self.session["log"][self.editing_index] = coin
            self.editing_index = None
            if self.session.get("session_type") == "Coin roll hunt":
                roll, count = sorting.infer_roll_state(self.session["log"], self.session.get("roll_quantity", ""))
                self.session["current_roll"] = roll
                self.session["current_roll_count"] = count
        else:
            self.session["log"].append(coin)
            if self.session.get("session_type") == "Coin roll hunt" and roll_mode in ("automatic", "manual"):
                self.session["current_roll"] = int(roll_number or self.session.get("current_roll", 1) or 1)
                self.session["current_roll_count"] = int(roll_coin_number or 0)
                if roll_mode == "automatic":
                    qty = _safe_int(roll_quantity, 0)
                    if qty and self.session["current_roll_count"] >= qty:
                        self.session["current_roll"] += 1
                        self.session["current_roll_count"] = 0
        storage.write_session_csv(self.session["path"], self.session["log"])
        storage.save_session_meta(self.session)
        sound.play_coin_saved_sound()
        self.status_var.set(f"{'Updated' if old_coin is not None else 'Saved'} {year}-{mint_name} • {option.get('coin_type', 'Unknown')}")
        self.year_var.set("")
        self.notes_var.set("")
        self.keep_bulk.set(False)
        self.reject.set(False)
        self.update_selection_buttons()
        self.type_index = 0
        self.refresh_all()
        self.year_entry.focus_set()

    def load_selected_recent_for_edit(self):
        if not self.session or not hasattr(self, "recent_tree"):
            return
        sel = self.recent_tree.selection()
        if not sel:
            messagebox.showinfo("Edit coin", "Highlight a recent coin first.", parent=self.root)
            return
        idx = int(sel[0])
        if idx < 0 or idx >= len(self.session.get("log", [])):
            return
        coin = self.session["log"][idx]
        self.editing_index = idx
        self.year_var.set(str(coin.get("year", ""))[:4])
        mint = coin.get("mint", "") or "No Mint"
        if mint not in state.MINTS:
            mint = "No Mint"
        self.mint_index = state.MINTS.index(mint)
        self.mint_combo.set(mint)
        self.notes_var.set(coin.get("notes", ""))
        self.keep_bulk.set(sorting.boolish(coin.get("keep_bulk", False)))
        self.reject.set(sorting.boolish(coin.get("reject", False)))
        if coin.get("reject_reason"):
            self.reject_reason.set(coin.get("reject_reason"))
        self.update_selection_buttons()
        self.refresh_type_options()
        target_num = sorting.clean_numista_number(coin.get("numista_number", ""))
        target_type = coin.get("coin_type", "")
        for i, opt in enumerate(self.current_type_options):
            if target_num and sorting.clean_numista_number(opt.get("numista_number", "")) == target_num:
                self.type_index = i
                self.type_combo.current(i)
                break
            if not target_num and opt.get("coin_type") == target_type:
                self.type_index = i
                self.type_combo.current(i)
                break
        self.status_var.set(f"Editing coin #{idx + 1}. Press Enter/Save Coin to update it, or delete it from Recent coins.")
        self.year_entry.focus_set()

    def delete_selected_recent(self):
        sel = self.recent_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        coin = self.session["log"][idx]
        if not messagebox.askyesno("Delete coin", f"Delete {coin.get('year', '')}-{coin.get('mint', '')} {coin.get('coin_type', '')} from this session?"):
            return
        del self.session["log"][idx]
        storage.write_session_csv(self.session["path"], self.session["log"])
        storage.save_session_meta(self.session)
        if self.session.get("session_type") == "Coin roll hunt":
            roll, count = sorting.infer_roll_state(self.session["log"], self.session.get("roll_quantity", ""))
            self.session["current_roll"] = roll
            self.session["current_roll_count"] = count
        self.refresh_all()


    def undo_last_coin(self):
        if not self.session or not self.session.get("log"):
            messagebox.showinfo("Undo Last Coin", "There is no coin to undo.", parent=self.root)
            return
        coin = self.session["log"][-1]
        label = f"{coin.get('year', '')}-{coin.get('mint', '')} {coin.get('coin_type', '')}".strip()
        if not messagebox.askyesno("Undo Last Coin", f"Remove the last saved coin?\n\n{label}", parent=self.root):
            return
        removed = self.session["log"].pop()
        storage.write_session_csv(self.session["path"], self.session["log"])
        storage.save_session_meta(self.session)
        if self.session.get("session_type") == "Coin roll hunt":
            roll, count = sorting.infer_roll_state(self.session["log"], self.session.get("roll_quantity", ""))
            self.session["current_roll"] = roll
            self.session["current_roll_count"] = count
        self.status_var.set(f"Undid last coin: {removed.get('year', '')}-{removed.get('mint', '')} {removed.get('coin_type', '')}")
        self.refresh_all()
        try:
            self.year_entry.focus_set()
        except Exception:
            pass

    def next_roll(self):
        if not self.session or self.session.get("session_type") != "Coin roll hunt" or self.session.get("roll_mode") not in ("automatic", "manual"):
            messagebox.showinfo("Next Roll", "Next Roll is only active for Coin Roll Hunt sessions with roll tracking.")
            return
        self.session["current_roll"] = int(self.session.get("current_roll", 1) or 1) + 1
        self.session["current_roll_count"] = 0
        self.status_var.set(f"Started roll {self.session['current_roll']}.")
        self.refresh_stats()

    def change_denom_dialog(self):
        if not self.session:
            return
        win = tk.Toplevel(self.root)
        win.title("Change country / denomination")
        win.configure(bg=COLORS["bg"])
        win.geometry("620x330")
        win.transient(self.root)
        frame = ttk.Frame(win, padding=18, style="TFrame")
        frame.pack(fill="both", expand=True)
        country_var = tk.StringVar(value=self.session.get("country", ""))
        denom_var = tk.StringVar(value=self.session.get("denomination", ""))
        countries = self.merged_country_options()

        ttk.Label(frame, text="Change active sorting selection", style="Big.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))
        ttk.Label(frame, text="Country", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        country_combo = ttk.Combobox(frame, textvariable=country_var, values=countries, state="readonly")
        country_combo.grid(row=1, column=1, columnspan=3, sticky="ew", pady=5)
        ttk.Label(frame, text="Denomination", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=5)
        denom_combo = ttk.Combobox(frame, textvariable=denom_var, state="readonly")
        denom_combo.grid(row=2, column=1, columnspan=3, sticky="ew", pady=5)

        def refresh(*_):
            labels = self.denom_options_for_country(country_var.get())
            denom_combo["values"] = labels
            if labels and denom_var.get() not in labels:
                denom_var.set(labels[0])

        def add_from_numista():
            choice = self.add_country_denom_from_numista_dialog(parent=win, default_country=country_var.get())
            if choice:
                country_combo["values"] = self.merged_country_options()
                country_var.set(choice["country"])
                refresh()
                denom_var.set(choice["denomination"])

        def add_custom():
            choice = self.add_custom_denom_dialog(parent=win, default_country=country_var.get())
            if choice:
                country_combo["values"] = self.merged_country_options()
                country_var.set(choice["country"])
                refresh()
                denom_var.set(choice["denomination"])

        country_combo.bind("<<ComboboxSelected>>", refresh)
        refresh()
        helper = (
            "Numista CSV countries, learned API countries, and custom denominations are merged here. "
            "Use Add from N# for unexpected foreign coins so the API fills country/value/type data."
        )
        ttk.Label(frame, text=helper, style="Muted.TLabel", wraplength=560).grid(row=3, column=0, columnspan=4, sticky="w", pady=(8, 14))
        ttk.Button(frame, text="Add from Numista N#", style="Blue.TButton", command=add_from_numista).grid(row=4, column=0, columnspan=2, sticky="ew", pady=4, padx=(0, 5))
        ttk.Button(frame, text="Add custom manually", command=add_custom).grid(row=4, column=2, columnspan=2, sticky="ew", pady=4, padx=(5, 0))

        def apply():
            denom = denom_var.get()
            if not country_var.get() or not denom:
                messagebox.showwarning("Missing selection", "Choose a country and denomination first.", parent=win)
                return
            choice = self.choice_from_country_denom(country_var.get(), denom)
            self.set_session_choice(choice)
            self.type_index = 0
            win.destroy()
        ttk.Button(frame, text="Cancel", command=win.destroy).grid(row=5, column=0, sticky="w", pady=(18, 0))
        ttk.Button(frame, text="Apply", style="Accent.TButton", command=apply).grid(row=5, column=3, sticky="e", pady=(18, 0))
        for col in range(4):
            frame.columnconfigure(col, weight=1 if col else 0)
        country_combo.focus_set()

    def edit_session_notes(self):
        if not self.session:
            return
        value = simpledialog.askstring("Session Notes", "Notes for this session:", initialvalue=self.session.get("session_notes", ""), parent=self.root)
        if value is not None:
            self.session["session_notes"] = value
            storage.save_session_meta(self.session)
            self.status_var.set("Session notes saved.")


    def show_statistics_window(self, title, rows, selected_files=None):
        win = tk.Toplevel(self.root)
        win.title(title.title())
        win.geometry("900x650")
        win.minsize(720, 460)
        win.configure(bg=COLORS["bg"])
        win.transient(self.root)
        outer = ttk.Frame(win, padding=12, style="TFrame")
        outer.pack(fill="both", expand=True)
        lines = stats_mod.build_statistics_lines(title, rows, selected_files or [])
        text = tk.Text(outer, bg=COLORS["white"], fg=COLORS["dark"], font=("Consolas", 10), wrap="none")
        yscroll = ttk.Scrollbar(outer, orient="vertical", command=text.yview)
        xscroll = ttk.Scrollbar(outer, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")
        row = ttk.Frame(outer, style="TFrame")
        row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        def export_report():
            out = stats_mod.export_statistics_lines(lines, title.lower().replace(" ", "_"))
            messagebox.showinfo("Statistics exported", f"Saved to:\n\n{out}", parent=win)
            self.status_var.set(f"Statistics exported: {out}")
        ttk.Button(row, text="Export Report", style="Accent.TButton", command=export_report).pack(side="left")
        ttk.Button(row, text="Close", command=win.destroy).pack(side="right")
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

    def show_current_statistics(self):
        if not self.session:
            self.show_home_statistics()
            return
        rows = list(self.session.get("log", []))
        for row in rows:
            row.setdefault("source_file", os.path.basename(self.session.get("path", "current_session.csv")))
        self.show_statistics_window("SESSION STATISTICS", rows, [os.path.basename(self.session.get("path", "current_session.csv"))])

    def show_home_statistics(self):
        files = storage.list_sessions()
        if not files:
            messagebox.showinfo("Statistics", "No saved session CSVs found yet.", parent=self.root)
            return
        win = tk.Toplevel(self.root)
        win.title("Statistics - Select Sessions")
        win.geometry("680x520")
        win.configure(bg=COLORS["bg"])
        win.transient(self.root)
        frame = ttk.Frame(win, padding=14, style="TFrame")
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Select sessions for statistics", style="Big.TLabel").pack(anchor="w", pady=(0, 10))
        listbox = tk.Listbox(frame, selectmode="extended", bg=COLORS["white"], fg=COLORS["dark"], selectbackground=COLORS["blue"], selectforeground=COLORS["white"], height=18)
        listbox.pack(fill="both", expand=True)
        for filename in files:
            path = os.path.join(state.SESSIONS_DIR, filename)
            try:
                rows = len(storage.load_session_csv(path))
                modified = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
                label = f"{filename}  ({rows} coins, modified {modified})"
            except Exception:
                label = filename
            listbox.insert("end", label)
        if files:
            listbox.selection_set(0)
        row = ttk.Frame(frame, style="TFrame")
        row.pack(fill="x", pady=(10, 0))
        def select_all():
            listbox.selection_set(0, "end")
        def open_stats():
            selected = list(listbox.curselection())
            if not selected:
                messagebox.showwarning("No sessions selected", "Select one or more sessions first.", parent=win)
                return
            picked = [files[i] for i in selected]
            rows = []
            for filename in picked:
                rows.extend(storage.read_session_rows(filename))
            title = "COMBINED SESSION STATISTICS" if len(picked) > 1 else "SESSION STATISTICS"
            win.destroy()
            self.show_statistics_window(title, rows, picked)
        ttk.Button(row, text="Select All", command=select_all).pack(side="left")
        ttk.Button(row, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(row, text="Open Statistics", style="Accent.TButton", command=open_stats).pack(side="right", padx=(0, 8))

    def show_export_dialog(self):
        files = storage.list_sessions()
        if not files:
            messagebox.showinfo("Export Data", "No saved session CSVs found yet.", parent=self.root)
            return
        win = tk.Toplevel(self.root)
        win.title("Export Session Data")
        win.geometry("780x620")
        win.configure(bg=COLORS["bg"])
        win.transient(self.root)
        outer = ttk.Frame(win, padding=14, style="TFrame")
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Export Data", style="Title.TLabel").pack(anchor="w", pady=(0, 10))
        panes = ttk.Frame(outer, style="TFrame")
        panes.pack(fill="both", expand=True)
        left = ttk.Frame(panes, style="TFrame")
        right = ttk.Frame(panes, style="TFrame")
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right.pack(side="right", fill="both", expand=True, padx=(8, 0))
        ttk.Label(left, text="Sessions", style="Big.TLabel").pack(anchor="w")
        session_list = tk.Listbox(left, selectmode="extended", bg=COLORS["white"], fg=COLORS["dark"], selectbackground=COLORS["blue"], selectforeground=COLORS["white"], height=18)
        session_list.pack(fill="both", expand=True, pady=(6, 0))
        for filename in files:
            session_list.insert("end", filename)
        session_list.selection_set(0)
        ttk.Label(right, text="Columns", style="Big.TLabel").pack(anchor="w")
        column_list = tk.Listbox(right, selectmode="extended", bg=COLORS["white"], fg=COLORS["dark"], selectbackground=COLORS["blue"], selectforeground=COLORS["white"], height=18)
        column_list.pack(fill="both", expand=True, pady=(6, 0))
        export_columns = list(state.CSV_HEADERS) + ["source_file"]
        for column in export_columns:
            column_list.insert("end", column)
        column_list.selection_set(0, "end")
        row = ttk.Frame(outer, style="TFrame")
        row.pack(fill="x", pady=(12, 0))
        def export_now():
            picked_files = [files[i] for i in session_list.curselection()]
            picked_columns = [export_columns[i] for i in column_list.curselection()]
            if not picked_files or not picked_columns:
                messagebox.showwarning("Missing selection", "Select at least one session and one column.", parent=win)
                return
            rows = []
            for filename in picked_files:
                rows.extend(storage.read_session_rows(filename))
            settings.ensure_app_dirs()
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            out_path = os.path.join(state.EXPORTS_DIR, f"{timestamp}_coin_sort_export.csv")
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                import csv
                writer = csv.DictWriter(f, fieldnames=picked_columns, extrasaction="ignore")
                writer.writeheader()
                for row_data in rows:
                    writer.writerow({col: row_data.get(col, "") for col in picked_columns})
            messagebox.showinfo("Export complete", f"Exported {len(rows)} row(s).\n\nSaved to:\n{out_path}", parent=win)
            self.status_var.set(f"Exported data: {out_path}")
        ttk.Button(row, text="Export CSV", style="Accent.TButton", command=export_now).pack(side="left")
        ttk.Button(row, text="Close", command=win.destroy).pack(side="right")

    def reload_numista_data(self):
        """Reload Numista CSV + Coin_Types.csv data and push it into the active session."""
        try:
            self.numista_index, self.numista_files, self.numista_countries, self.denoms_by_country, self.numista_type_index = storage.load_numista_index()
            if self.session:
                self.session["numista_index"] = self.numista_index
                self.session["numista_csv_count"] = len(self.numista_files)
                self.session["numista_coin_count"] = len(self.numista_index)
                self.session["numista_countries"] = self.numista_countries
                self.session["denoms_by_country"] = self.denoms_by_country
                self.session["numista_type_index"] = self.numista_type_index
                storage.save_session_meta(self.session)
                self.refresh_all()
            self.status_var.set(f"Reloaded Numista data: {len(self.numista_files)} CSV file(s), {len(self.numista_index)} owned keys.")
            return True
        except Exception as exc:
            messagebox.showerror("Reload failed", f"Could not reload Numista data.\n\n{exc}")
            return False

    def show_settings(self):
        """Open the GUI settings window.

        This covers the settings most likely to be needed while sorting: app
        folders, Numista API credentials/usage, sound, and coin roll quantities.
        """
        settings.load_settings()
        win = tk.Toplevel(self.root)
        win.title("MTS CoinSort Settings")
        win.configure(bg=COLORS["bg"])
        win.geometry("780x610")
        win.minsize(700, 520)
        win.transient(self.root)

        outer = ttk.Frame(win, padding=14, style="TFrame")
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Settings", style="Title.TLabel").pack(anchor="w", pady=(0, 10))
        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)

        general = ttk.Frame(notebook, padding=14, style="Card.TFrame")
        api_tab = ttk.Frame(notebook, padding=14, style="Card.TFrame")
        sound_tab = ttk.Frame(notebook, padding=14, style="Card.TFrame")
        roll_tab = ttk.Frame(notebook, padding=14, style="Card.TFrame")
        hotkeys_tab = ttk.Frame(notebook, padding=14, style="Card.TFrame")
        notebook.add(general, text="General")
        notebook.add(api_tab, text="Numista API")
        notebook.add(sound_tab, text="Sound")
        notebook.add(roll_tab, text="Roll quantities")
        notebook.add(hotkeys_tab, text="Hotkeys")

        # General / folders.
        ttk.Label(general, text="App folders", style="Big.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        data_dir_var = tk.StringVar(value=state.DATA_DIR)
        ttk.Label(general, text="Data folder", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(general, textvariable=data_dir_var).grid(row=1, column=1, sticky="ew", pady=5)

        def browse_data_dir():
            selected = filedialog.askdirectory(parent=win, initialdir=state.DATA_DIR or os.path.expanduser("~"))
            if selected:
                data_dir_var.set(selected)

        def save_data_dir():
            value = data_dir_var.get().strip()
            if not value:
                messagebox.showwarning("Missing folder", "Choose a data folder first.", parent=win)
                return
            settings.apply_data_dir(value)
            settings.ensure_app_dirs()
            settings.save_settings()
            self.reload_numista_data()
            messagebox.showinfo("Saved", "Data folder saved. The app folders were created if needed.", parent=win)

        ttk.Button(general, text="Browse", command=browse_data_dir).grid(row=1, column=2, sticky="ew", padx=(8, 0))
        ttk.Button(general, text="Save data folder", style="Accent.TButton", command=save_data_dir).grid(row=2, column=1, sticky="e", pady=(6, 18))

        folder_buttons = ttk.Frame(general, style="Card.TFrame")
        folder_buttons.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(4, 14))
        ttk.Button(folder_buttons, text="Open Data", command=lambda: utils.open_folder(state.DATA_DIR)).pack(side="left", padx=(0, 6))
        ttk.Button(folder_buttons, text="Open Numista CSV", command=lambda: utils.open_folder(state.NUMISTA_DIR)).pack(side="left", padx=6)
        ttk.Button(folder_buttons, text="Open Sessions", command=lambda: utils.open_folder(state.SESSIONS_DIR)).pack(side="left", padx=6)
        ttk.Button(folder_buttons, text="Open Exports", command=lambda: utils.open_folder(state.EXPORTS_DIR)).pack(side="left", padx=6)
        def import_numista_csv():
            selected = filedialog.askopenfilenames(parent=win, title="Choose Numista CSV export(s)", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
            if not selected:
                return
            settings.ensure_app_dirs()
            copied = 0
            for src in selected:
                try:
                    dest = os.path.join(state.NUMISTA_DIR, os.path.basename(src))
                    if os.path.abspath(src) != os.path.abspath(dest):
                        shutil.copy2(src, dest)
                    copied += 1
                except Exception as exc:
                    messagebox.showerror("Import failed", f"Could not copy:\n{src}\n\n{exc}", parent=win)
            self.reload_numista_data()
            messagebox.showinfo("Import complete", f"Imported/copied {copied} CSV file(s) into:\n{state.NUMISTA_DIR}", parent=win)

        ttk.Button(general, text="Import Numista CSV Export(s)", style="Accent.TButton", command=import_numista_csv).grid(row=4, column=0, columnspan=3, sticky="ew", pady=(4, 6))
        ttk.Button(general, text="Reload Numista CSV + Coin Types", style="Blue.TButton", command=self.reload_numista_data).grid(row=5, column=0, columnspan=3, sticky="ew", pady=(4, 10))
        ttk.Label(general, text=f"Settings file:\n{state.SETTINGS_PATH}", style="Muted.TLabel", wraplength=680).grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 0))
        ttk.Label(general, text=f"Loaded now: {len(self.numista_files)} Numista CSV file(s), {len(self.numista_index)} owned coin key(s).", style="Muted.TLabel").grid(row=7, column=0, columnspan=3, sticky="w", pady=(8, 0))
        general.columnconfigure(1, weight=1)

        # Numista API tab.
        ttk.Label(api_tab, text="Numista API", style="Big.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        client_var = tk.StringVar(value=state.NUMISTA_CLIENT_ID)
        key_var = tk.StringVar(value=state.NUMISTA_API_KEY)
        max_var = tk.StringVar(value=str(state.NUMISTA_API_USAGE.get("max_monthly_calls", 2000)))
        warn_var = tk.StringVar(value=str(state.NUMISTA_API_USAGE.get("warn_percent", 85)))
        usage_var = tk.StringVar()

        ttk.Label(api_tab, text="Client ID", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(api_tab, textvariable=client_var).grid(row=1, column=1, columnspan=2, sticky="ew", pady=5)
        ttk.Label(api_tab, text="API key", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(api_tab, textvariable=key_var, show="*").grid(row=2, column=1, columnspan=2, sticky="ew", pady=5)
        ttk.Label(api_tab, text="Monthly local max", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Entry(api_tab, textvariable=max_var, width=10).grid(row=3, column=1, sticky="w", pady=5)
        ttk.Label(api_tab, text="Warn percent", style="Card.TLabel").grid(row=4, column=0, sticky="w", pady=5)
        ttk.Entry(api_tab, textvariable=warn_var, width=10).grid(row=4, column=1, sticky="w", pady=5)
        ttk.Label(api_tab, textvariable=usage_var, style="Muted.TLabel", wraplength=680).grid(row=5, column=0, columnspan=3, sticky="w", pady=(12, 10))

        def refresh_usage_text():
            usage = settings.refresh_numista_api_usage_month(state.NUMISTA_API_USAGE)
            limit = usage.get("max_monthly_calls", 0)
            used = usage.get("api_calls_this_month", 0)
            usage_var.set(
                f"Month: {usage.get('month')}\n"
                f"API calls used: {used} / {limit}  |  Remaining: {max(0, limit - used)}\n"
                f"Successful / failed this month: {usage.get('successful_calls_this_month', 0)} / {usage.get('failed_calls_this_month', 0)}\n"
                f"Cache hits this month / lifetime: {usage.get('cache_hits_this_month', 0)} / {usage.get('cache_hits_lifetime', 0)}\n"
                f"Lifetime API calls: {usage.get('api_calls_lifetime', 0)}\n"
                f"Last API call: {usage.get('last_api_call') or 'Never'}"
            )

        def save_api_settings():
            try:
                max_calls = int(float(max_var.get().strip() or "0"))
                warn_percent = int(float(warn_var.get().strip() or "85"))
            except ValueError:
                messagebox.showwarning("Invalid number", "Monthly max and warn percent must be numbers.", parent=win)
                return
            state.NUMISTA_CLIENT_ID = client_var.get().strip()
            state.NUMISTA_API_KEY = key_var.get().strip()
            usage = settings.refresh_numista_api_usage_month(state.NUMISTA_API_USAGE)
            usage["max_monthly_calls"] = max(0, max_calls)
            usage["warn_percent"] = min(100, max(1, warn_percent))
            state.NUMISTA_API_USAGE = usage
            settings.save_settings()
            refresh_usage_text()
            messagebox.showinfo("Saved", "Numista API settings saved.", parent=win)

        def reset_usage():
            if not messagebox.askyesno("Reset usage", "Reset this month's local Numista API counters?\n\nThis does not reset Numista's real quota.", parent=win):
                return
            usage = settings.refresh_numista_api_usage_month(state.NUMISTA_API_USAGE)
            usage["api_calls_this_month"] = 0
            usage["successful_calls_this_month"] = 0
            usage["failed_calls_this_month"] = 0
            usage["cache_hits_this_month"] = 0
            usage["last_api_call"] = ""
            usage["last_cache_hit"] = ""
            state.NUMISTA_API_USAGE = usage
            settings.save_settings()
            refresh_usage_text()

        api_buttons = ttk.Frame(api_tab, style="Card.TFrame")
        api_buttons.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Button(api_buttons, text="Save API Settings", style="Accent.TButton", command=save_api_settings).pack(side="left", padx=(0, 6))
        ttk.Button(api_buttons, text="Test API Key", style="Blue.TButton", command=lambda: self.test_numista_api(parent=win, after=refresh_usage_text)).pack(side="left", padx=6)
        ttk.Button(api_buttons, text="Reset Local Usage", command=reset_usage).pack(side="left", padx=6)
        ttk.Button(api_buttons, text="Add Type by N#", command=self.add_numista_type_dialog).pack(side="left", padx=6)
        api_tab.columnconfigure(1, weight=1)
        refresh_usage_text()

        # Sound tab.
        ttk.Label(sound_tab, text="Coin saved sound", style="Big.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        sound_mode_var = tk.StringVar(value=state.COIN_SAVE_SOUND_MODE if state.COIN_SAVE_SOUND_MODE in ("default", "custom", "off") else "default")
        sound_file_var = tk.StringVar(value=state.COIN_SAVE_SOUND_FILE)
        ttk.Label(sound_tab, text="Mode", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Combobox(sound_tab, textvariable=sound_mode_var, values=["default", "custom", "off"], state="readonly").grid(row=1, column=1, sticky="ew", pady=5)
        ttk.Label(sound_tab, text="Custom file", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(sound_tab, textvariable=sound_file_var).grid(row=2, column=1, sticky="ew", pady=5)

        def browse_sound():
            selected = filedialog.askopenfilename(parent=win, title="Choose sound file", filetypes=[("Sound files", "*.wav *.mp3 *.ogg *.flac"), ("All files", "*.*")])
            if selected:
                sound_file_var.set(selected)

        def save_sound():
            mode = sound_mode_var.get().strip().lower()
            state.COIN_SAVE_SOUND_MODE = mode
            state.COIN_SAVE_SOUND = mode != "off"
            state.COIN_SAVE_SOUND_FILE = utils.clean_user_path(sound_file_var.get()) if sound_file_var.get().strip() else ""
            settings.save_settings()
            messagebox.showinfo("Saved", "Sound settings saved.", parent=win)

        ttk.Button(sound_tab, text="Browse", command=browse_sound).grid(row=2, column=2, sticky="ew", padx=(8, 0))
        sound_buttons = ttk.Frame(sound_tab, style="Card.TFrame")
        sound_buttons.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        ttk.Button(sound_buttons, text="Save Sound Settings", style="Accent.TButton", command=save_sound).pack(side="left", padx=(0, 6))
        ttk.Button(sound_buttons, text="Test Sound", style="Blue.TButton", command=lambda: (save_sound(), sound.play_coin_saved_sound(force=True))).pack(side="left", padx=6)
        sound_tab.columnconfigure(1, weight=1)

        # Roll quantities tab.
        ttk.Label(roll_tab, text="Coin roll quantities", style="Big.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        roll_list = tk.Listbox(roll_tab, height=14, bg=COLORS["white"], fg=COLORS["dark"], selectbackground=COLORS["blue"], selectforeground=COLORS["white"])
        roll_list.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(0, 10))

        def refresh_roll_list():
            roll_list.delete(0, "end")
            for key, qty in sorted(state.ROLL_QUANTITIES.items(), key=lambda item: item[0].lower()):
                roll_list.insert("end", settings.roll_quantity_label(key, qty))

        def selected_roll_key():
            sel = roll_list.curselection()
            if not sel:
                return None
            entries = sorted(state.ROLL_QUANTITIES.items(), key=lambda item: item[0].lower())
            return entries[sel[0]][0] if sel[0] < len(entries) else None

        def add_or_edit_roll():
            country = simpledialog.askstring("Roll quantity", "Country:", parent=win, initialvalue=self.session.get("country", "") if self.session else "")
            if not country:
                return
            face = simpledialog.askstring("Roll quantity", "Face value, example 0.01, 0.25, 1.00:", parent=win, initialvalue=self.session.get("face_value", "") if self.session else "")
            if not face:
                return
            currency = simpledialog.askstring("Roll quantity", "Currency label, example Dollar (1785-date), Euro, Peso:", parent=win, initialvalue=self.session.get("currency", "") if self.session else "")
            if currency is None:
                return
            key = settings.roll_quantity_key(country, face, currency)
            qty = simpledialog.askinteger("Roll quantity", "Coins per roll:", parent=win, initialvalue=state.ROLL_QUANTITIES.get(key, 50), minvalue=1)
            if qty:
                state.ROLL_QUANTITIES[key] = int(qty)
                settings.save_settings()
                refresh_roll_list()

        def edit_selected_roll():
            key = selected_roll_key()
            if not key:
                return
            qty = simpledialog.askinteger("Edit roll quantity", "Coins per roll:", parent=win, initialvalue=state.ROLL_QUANTITIES.get(key, 50), minvalue=1)
            if qty:
                state.ROLL_QUANTITIES[key] = int(qty)
                settings.save_settings()
                refresh_roll_list()

        def delete_selected_roll():
            key = selected_roll_key()
            if not key:
                return
            if messagebox.askyesno("Delete", f"Delete this roll quantity?\n\n{settings.roll_quantity_label(key, state.ROLL_QUANTITIES[key])}", parent=win):
                state.ROLL_QUANTITIES.pop(key, None)
                settings.save_settings()
                refresh_roll_list()

        roll_buttons = ttk.Frame(roll_tab, style="Card.TFrame")
        roll_buttons.grid(row=2, column=0, columnspan=3, sticky="ew")
        ttk.Button(roll_buttons, text="Add / Edit Custom", style="Accent.TButton", command=add_or_edit_roll).pack(side="left", padx=(0, 6))
        ttk.Button(roll_buttons, text="Edit Selected", command=edit_selected_roll).pack(side="left", padx=6)
        ttk.Button(roll_buttons, text="Delete Selected", style="Danger.TButton", command=delete_selected_roll).pack(side="left", padx=6)
        roll_tab.rowconfigure(1, weight=1)
        roll_tab.columnconfigure(0, weight=1)
        refresh_roll_list()

        # Hotkeys tab.
        ttk.Label(hotkeys_tab, text="Sorting hotkeys", style="Big.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        ttk.Label(hotkeys_tab, text="Click a row, press Change, then press the new key. The GUI listens to these while sorting; the terminal uses the same settings.json values.", style="Muted.TLabel", wraplength=680).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 10))
        hotkey_list = tk.Listbox(hotkeys_tab, height=10, bg=COLORS["white"], fg=COLORS["dark"], selectbackground=COLORS["blue"], selectforeground=COLORS["white"])
        hotkey_list.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=(0, 10))
        actions = list(state.DEFAULT_HOTKEYS.keys())

        def refresh_hotkey_list():
            hotkey_list.delete(0, "end")
            for action in actions:
                hotkey_list.insert("end", f"{state.HOTKEY_LABELS[action]:<24} {settings.key_display(state.HOTKEYS.get(action, state.DEFAULT_HOTKEYS[action]))}")

        def change_hotkey():
            sel = hotkey_list.curselection()
            if not sel:
                return
            action = actions[sel[0]]
            capture = tk.Toplevel(win)
            capture.title("Press new hotkey")
            capture.configure(bg=COLORS["bg"])
            capture.geometry("420x150")
            capture.transient(win)
            capture.grab_set()
            ttk.Label(capture, text=f"Press new key for {state.HOTKEY_LABELS[action]}", style="Big.TLabel").pack(anchor="w", padx=14, pady=(14, 6))
            ttk.Label(capture, text="Esc cancels. Avoid using normal digits for sorting hotkeys.", style="TLabel", wraplength=380).pack(anchor="w", padx=14)

            def keypress(event):
                if event.keysym == "Escape":
                    capture.destroy()
                    return "break"
                key = event.char if event.char else event.keysym
                if event.keysym in ("Return", "KP_Enter"):
                    key = state.KEY_ENTER
                if event.keysym == "Tab":
                    key = state.KEY_TAB
                conflict = None
                for other, other_key in state.HOTKEYS.items():
                    if other != action and settings.normalize_key_for_compare(other_key) == settings.normalize_key_for_compare(key):
                        conflict = other
                        break
                state.HOTKEYS[action] = key
                if conflict:
                    state.HOTKEYS[conflict] = state.DEFAULT_HOTKEYS[conflict]
                settings.save_settings()
                refresh_hotkey_list()
                self._bind_keys()
                capture.destroy()
                return "break"
            capture.bind("<KeyPress>", keypress)
            capture.focus_set()

        def reset_hotkeys_gui():
            if messagebox.askyesno("Reset hotkeys", "Reset sorting hotkeys to defaults?", parent=win):
                settings.reset_hotkeys_to_default()
                refresh_hotkey_list()
                self._bind_keys()

        hotkey_buttons = ttk.Frame(hotkeys_tab, style="Card.TFrame")
        hotkey_buttons.grid(row=3, column=0, columnspan=3, sticky="ew")
        ttk.Button(hotkey_buttons, text="Change Selected", style="Accent.TButton", command=change_hotkey).pack(side="left", padx=(0, 6))
        ttk.Button(hotkey_buttons, text="Reset Defaults", command=reset_hotkeys_gui).pack(side="left", padx=6)
        hotkeys_tab.rowconfigure(2, weight=1)
        hotkeys_tab.columnconfigure(0, weight=1)
        refresh_hotkey_list()

        bottom = ttk.Frame(outer, style="TFrame")
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Button(bottom, text="Close", command=win.destroy).pack(side="right")

    def test_numista_api(self, parent=None, after=None):
        details, error = self.fetch_numista_type_details_gui("1", parent=parent)
        if error:
            messagebox.showerror("Numista API test failed", error, parent=parent or self.root)
        else:
            messagebox.showinfo("Numista API test worked", f"Example returned:\n\nN# {details.get('id', '1')} - {details.get('title', 'Unknown')}", parent=parent or self.root)
        if after:
            after()

    def api_usage_allows_call_gui(self, numista_number="", parent=None):
        usage = settings.refresh_numista_api_usage_month(state.NUMISTA_API_USAGE)
        limit = int(usage.get("max_monthly_calls", 0) or 0)
        used = int(usage.get("api_calls_this_month", 0) or 0)
        next_call = used + 1
        if limit <= 0:
            messagebox.showwarning("Numista API blocked", "Your monthly max call setting is 0. Increase it in Settings > Numista API.", parent=parent or self.root)
            return False
        if used >= limit:
            messagebox.showwarning("Numista API monthly max reached", f"Local counter: {used} / {limit} calls used for {usage.get('month')}.\n\nThis lookup was blocked to protect your chosen monthly limit.", parent=parent or self.root)
            return False
        warn_at = int(limit * int(usage.get("warn_percent", 85) or 85) / 100)
        if next_call >= warn_at:
            return messagebox.askyesno("Numista API usage warning", f"This lookup will use call {next_call} of your {limit} monthly max for {usage.get('month')}.\n\nContinue with this API call?", parent=parent or self.root)
        return True

    def fetch_numista_type_details_gui(self, numista_number, parent=None):
        """GUI-safe Numista fetch that does not call terminal prompts."""
        clean_number = numista.clean_numista_number(numista_number)
        if not clean_number:
            return None, "No Numista number was entered."
        if not str(state.NUMISTA_API_KEY or "").strip():
            return None, "No Numista API key is saved. Add it in Settings > Numista API first."
        if not self.api_usage_allows_call_gui(clean_number, parent=parent):
            return None, "Numista API lookup was blocked by your monthly usage guard."

        url = f"https://api.numista.com/v3/types/{urllib.parse.quote(clean_number)}?lang=en"
        headers = {
            "Accept": "application/json",
            "Numista-API-Key": state.NUMISTA_API_KEY.strip(),
        }
        if str(state.NUMISTA_CLIENT_ID or "").strip():
            headers["Numista-Client-Id"] = state.NUMISTA_CLIENT_ID.strip()
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8", errors="replace")
            settings.log_numista_api_call(clean_number, success=True)
            return json.loads(raw), None
        except urllib.error.HTTPError as exc:
            try:
                details = exc.read().decode("utf-8", errors="replace")
            except Exception:
                details = ""
            settings.log_numista_api_call(clean_number, success=False)
            return None, f"HTTP {exc.code} from Numista API. {details}".strip()
        except urllib.error.URLError as exc:
            settings.log_numista_api_call(clean_number, success=False)
            return None, f"Network error while contacting Numista API: {exc.reason}"
        except Exception as exc:
            settings.log_numista_api_call(clean_number, success=False)
            return None, f"Could not read Numista API response: {exc}"

    def numista_detail_summary(self, details):
        composition = ""
        comp_obj = details.get("composition", {})
        if isinstance(comp_obj, dict):
            composition = str(comp_obj.get("text", "") or "").strip()
        lines = [
            f"N#          : {details.get('id', '')}",
            f"Title       : {details.get('title', 'Unknown')}",
            f"Country     : {numista.numista_detail_country(details) or 'Unknown'}",
            f"Years       : {numista.numista_detail_years(details)}",
            f"Value       : {numista.numista_detail_value_text(details) or 'Unknown'}",
            f"Currency    : {numista.numista_detail_currency_text(details) or 'Unknown'}",
            f"Category    : {numista.numista_detail_category(details) or 'Unknown'}",
        ]
        if composition:
            lines.append(f"Composition : {composition}")
        if details.get("weight"):
            lines.append(f"Weight      : {details.get('weight')} g")
        if details.get("size"):
            lines.append(f"Diameter    : {details.get('size')} mm")
        return "\n".join(lines)

    def add_numista_type_dialog(self, parent=None, ask_search=True):
        """Fetch, verify, and save a Numista type from the GUI.

        Returns the saved/cached Coin_Types.csv row when a type is available,
        otherwise returns None.
        """
        settings.load_settings()
        parent = parent or self.root
        if ask_search and self.session:
            should_search = messagebox.askyesnocancel(
                "Numista search",
                "Open Numista search in your browser first?\n\nYes = open search page\nNo = I already know the N#\nCancel = stop",
                parent=parent,
            )
            if should_search is None:
                return None
            if should_search:
                try:
                    year = self.year_var.get().strip() if hasattr(self, "year_var") else ""
                    mint = state.MINTS[self.mint_index] if hasattr(self, "mint_index") else ""
                    webbrowser.open(numista.numista_search_url(self.session, year, mint))
                except Exception:
                    pass
        n_value = simpledialog.askstring("Add Numista type", "Enter Numista N# for the coin type, example 457 or N#457:", parent=parent)
        if not n_value:
            return None
        clean_number = numista.clean_numista_number(n_value)
        cached = numista.best_cached_numista_row(clean_number)
        if cached:
            if messagebox.askyesno("Use local cached type?", f"This N# already exists in Coin_Types.csv.\n\nN# {cached.get('numista_number', '')} - {cached.get('numista_title', '')}\n{cached.get('country', '')} | {cached.get('denomination', '')}\n\nUse this cached type instead of spending an API call?", parent=parent):
                settings.log_numista_cache_hit(clean_number)
                choice = numista.cached_row_choice(cached)
                if self.session and choice:
                    self.apply_numista_choice_to_session(choice)
                self.reload_numista_data()
                self.status_var.set(f"Using cached Numista type N# {clean_number}.")
                return cached

        details, error = self.fetch_numista_type_details_gui(clean_number, parent=parent)
        if error:
            messagebox.showerror("Numista lookup failed", error, parent=parent)
            return None
        summary = self.numista_detail_summary(details)
        if not messagebox.askyesno("Verify Numista result", summary + "\n\nSave this type to Coin_Types.csv?", parent=parent):
            return None

        choice = numista.numista_choice_from_details(details)
        if not choice:
            if not self.session:
                messagebox.showerror("Cannot save type", "The API result did not include enough country/value data, and no active session is available as a fallback.", parent=parent)
                return None
            choice = {
                "country": self.session.get("country", ""),
                "currency": self.session.get("currency", ""),
                "face_value": self.session.get("face_value", ""),
                "denomination": self.session.get("denomination", ""),
            }

        year = self.year_var.get().strip() if self.session and hasattr(self, "year_var") and self.year_var.get().strip().isdigit() else ""
        mint_name = state.MINTS[self.mint_index] if self.session else ""
        row = numista.make_coin_type_cache_row_from_numista_choice(choice, details, year=year, mint_name=mint_name)
        all_rows = storage.upsert_coin_type_cache_rows([row])
        settings.remove_custom_denominations_for_country_face(choice.get("country", ""), choice.get("face_value", ""))
        self.numista_type_index = numista.build_type_index_from_cache(all_rows)

        if self.session:
            current_key = (self.session.get("country", "").strip().lower(), utils.normalize_decimal(self.session.get("face_value", "")))
            new_key = (choice.get("country", "").strip().lower(), utils.normalize_decimal(choice.get("face_value", "")))
            if new_key != current_key:
                if messagebox.askyesno("Change active denomination?", f"The API result is:\n{choice.get('country')} | {choice.get('denomination')}\n\nChange the active session to this country/denomination?", parent=parent):
                    self.apply_numista_choice_to_session(choice)
            self.session["numista_type_index"] = self.numista_type_index
            storage.save_session_meta(self.session)

        self.reload_numista_data()
        self.status_var.set(f"Saved Numista type N# {row.get('numista_number', '')} - {row.get('numista_title', '')}")
        messagebox.showinfo("Saved", f"Saved to Coin_Types.csv:\n\nN# {row.get('numista_number', '')} - {row.get('numista_title', '')}", parent=parent)
        return row

    def apply_numista_choice_to_session(self, choice):
        if not self.session or not choice:
            return
        self.session["country"] = choice.get("country", self.session.get("country", ""))
        self.session["currency"] = choice.get("currency", self.session.get("currency", ""))
        self.session["face_value"] = utils.normalize_decimal(choice.get("face_value", self.session.get("face_value", "")))
        self.session["denomination"] = choice.get("denomination", "") or utils.make_denom_label(self.session["face_value"], self.session["currency"])
        storage.save_session_meta(self.session)
        self.refresh_all()

    def _bind_keys(self):
        """Bind one global key handler so GUI hotkey remaps take effect immediately."""
        try:
            self.root.unbind_all("<KeyPress>")
        except Exception:
            pass
        self.root.bind_all("<KeyPress>", self._global_keypress)
        self.root.bind_all("<Control-o>", lambda e: self._consume(e, lambda: utils.open_folder(state.DATA_DIR)))

    def _event_key_value(self, event):
        if event.keysym in ("Return", "KP_Enter"):
            return state.KEY_ENTER
        if event.keysym == "Tab":
            return state.KEY_TAB
        if event.keysym in ("BackSpace",):
            return state.KEY_BACKSPACE
        if event.keysym == "Escape":
            return state.KEY_ESC
        return event.char if event.char else event.keysym

    def _global_keypress(self, event):
        if not self.session or not hasattr(self, "year_entry"):
            return None
        # Do not let the main sorter steal keys from settings/dialog windows.
        if event.widget.winfo_toplevel() is not self.root:
            return None
        widget = self.root.focus_get()
        key = self._event_key_value(event)
        # Year entry has its own stricter handler so bad chars never appear.
        if widget is self.year_entry:
            return None
        if key == state.KEY_ENTER:
            return self._consume(event, self.save_coin)
        # Let notes accept normal typed characters, except non-printing actions.
        if widget is self.notes_entry and isinstance(key, str) and len(key) == 1 and key.isprintable():
            return None
        if settings.hotkey_matches(key, "mint_next"):
            return self._consume(event, self.next_mint)
        if settings.hotkey_matches(key, "mint_previous"):
            return self._consume(event, self.prev_mint)
        if settings.hotkey_matches(key, "type_next"):
            return self._consume(event, self.next_type)
        if settings.hotkey_matches(key, "keep_bulk"):
            return self._consume(event, self.toggle_keep)
        if settings.hotkey_matches(key, "reject"):
            return self._consume(event, self.toggle_reject)
        if settings.hotkey_matches(key, "save_quit"):
            return self._consume(event, self.confirm_leave_session)
        return None

    def _return_key(self, event):
        return self._global_keypress(event)

    def _consume(self, event, func):
        try:
            func()
        finally:
            return "break"

    def confirm_leave_session(self):
        if not self.session:
            return
        if messagebox.askyesno("Leave session", "Save current session state and return to the start screen?", parent=self.root):
            storage.save_session_meta(self.session)
            self.session = None
            self.editing_index = None
            self.show_start()

    def toggle_keep(self):
        if not self.session:
            return
        self.keep_bulk.set(not self.keep_bulk.get())
        self.on_keep_toggle()

    def toggle_reject(self):
        if not self.session:
            return
        self.open_reject_reason_dialog()


def main():
    root = tk.Tk()
    app = CoinSortGUI(root)
    root.mainloop()
    return app


if __name__ == "__main__":
    main()