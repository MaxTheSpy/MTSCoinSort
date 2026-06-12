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
        ttk.Button(left, text="Settings", command=self.show_settings).pack(fill="x", pady=(18, 5))
        ttk.Button(left, text="Open Data Folder", command=lambda: utils.open_folder(state.DATA_DIR)).pack(fill="x", pady=5)
        ttk.Button(left, text="Terminal Mode", command=self.run_terminal_note).pack(fill="x", pady=5)

        ttk.Label(right, text="Loaded data", style="Big.TLabel").pack(anchor="w")
        ttk.Label(right, text=f"Numista CSV files: {len(self.numista_files)}", style="Card.TLabel").pack(anchor="w", pady=(12, 2))
        ttk.Label(right, text=f"Owned coin keys: {len(self.numista_index)}", style="Card.TLabel").pack(anchor="w", pady=2)
        ttk.Label(right, text=f"Countries available: {len(self.numista_countries)}", style="Card.TLabel").pack(anchor="w", pady=2)
        ttk.Label(right, text=f"Data folder:\n{state.DATA_DIR}", style="Muted.TLabel", wraplength=470).pack(anchor="w", pady=(16, 0))
        ttk.Label(right, text="Tip: keep using the terminal mode for advanced API prompts until those dialogs are ported into GUI.", style="Muted.TLabel", wraplength=470).pack(anchor="w", pady=(18, 0))

    def run_terminal_note(self):
        messagebox.showinfo("Terminal mode", "Close this GUI and run:\n\npython MTS_Coin_Sort.py --terminal")

    def show_new_session(self):
        self.clear_main()
        wrap, frame = self.card(self.main_area, 20)
        wrap.pack(fill="both", expand=True)
        ttk.Label(frame, text="New sorting session", style="Big.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 14))

        name_var = tk.StringVar(value=datetime.now().strftime("Sort %Y-%m-%d"))
        type_var = tk.StringVar(value=state.SESSION_TYPES[0])
        country_var = tk.StringVar(value=self.numista_countries[0] if self.numista_countries else "")
        denom_var = tk.StringVar()
        roll_mode_var = tk.StringVar(value="none")
        roll_qty_var = tk.StringVar(value="")

        def labels_for_country(country):
            return list(self.denoms_by_country.get(country, []))

        def refresh_denoms(*_):
            labels = labels_for_country(country_var.get())
            denom_combo["values"] = labels
            denom_var.set(labels[0] if labels else "")

        ttk.Label(frame, text="Session name", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        name_entry = ttk.Entry(frame, textvariable=name_var)
        name_entry.grid(row=1, column=1, columnspan=3, sticky="ew", pady=5)

        ttk.Label(frame, text="Session type", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=5)
        type_combo = ttk.Combobox(frame, textvariable=type_var, values=state.SESSION_TYPES, state="readonly")
        type_combo.grid(row=2, column=1, sticky="ew", pady=5)

        ttk.Label(frame, text="Country", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=5)
        country_combo = ttk.Combobox(frame, textvariable=country_var, values=self.numista_countries, state="readonly")
        country_combo.grid(row=3, column=1, sticky="ew", pady=5)

        ttk.Label(frame, text="Denomination", style="Card.TLabel").grid(row=4, column=0, sticky="w", pady=5)
        denom_combo = ttk.Combobox(frame, textvariable=denom_var, state="readonly")
        denom_combo.grid(row=4, column=1, sticky="ew", pady=5)
        country_combo.bind("<<ComboboxSelected>>", refresh_denoms)
        refresh_denoms()

        ttk.Label(frame, text="CRH roll mode", style="Card.TLabel").grid(row=5, column=0, sticky="w", pady=5)
        roll_mode_combo = ttk.Combobox(frame, textvariable=roll_mode_var, values=["none", "automatic", "manual"], state="readonly")
        roll_mode_combo.grid(row=5, column=1, sticky="ew", pady=5)
        ttk.Label(frame, text="Roll quantity", style="Card.TLabel").grid(row=5, column=2, sticky="e", padx=(16, 8), pady=5)
        ttk.Entry(frame, textvariable=roll_qty_var, width=10).grid(row=5, column=3, sticky="ew", pady=5)

        button_row = ttk.Frame(frame, style="Card.TFrame")
        button_row.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(22, 0))
        ttk.Button(button_row, text="Back", command=self.show_start).pack(side="left")
        ttk.Button(button_row, text="Start Session", style="Accent.TButton", command=lambda: self.start_new_session(name_var, type_var, country_var, denom_var, roll_mode_var, roll_qty_var)).pack(side="right")

        for i in range(4):
            frame.columnconfigure(i, weight=1 if i in (1, 3) else 0)
        self.focus_widgets = [name_entry, type_combo, country_combo, denom_combo, roll_mode_combo]
        name_entry.focus_set()

    def start_new_session(self, name_var, type_var, country_var, denom_var, roll_mode_var, roll_qty_var):
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
            "session_notes": "",
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
        self.keep_bulk.set(False)
        self.reject.set(False)
        self.year_var.set("")
        self.notes_var.set("")

        top = ttk.Frame(self.main_area, style="TFrame")
        top.pack(fill="x", pady=(0, 10))
        ttk.Button(top, text="← Sessions", command=self.show_start).pack(side="left")
        ttk.Button(top, text="Change Denomination", style="Blue.TButton", command=self.change_denom_dialog).pack(side="left", padx=8)
        ttk.Button(top, text="Session Notes", command=self.edit_session_notes).pack(side="left")
        ttk.Button(top, text="Add Numista Type", style="Blue.TButton", command=self.add_numista_type_dialog).pack(side="left", padx=8)
        ttk.Button(top, text="Settings", command=self.show_settings).pack(side="left")
        ttk.Button(top, text="Open CSV Folder", command=lambda: utils.open_folder(state.SESSIONS_DIR)).pack(side="right")

        body = ttk.Frame(self.main_area, style="TFrame")
        body.pack(fill="both", expand=True)
        left_wrap, left = self.card(body, 16)
        left_wrap.pack(side="left", fill="both", expand=True, padx=(0, 10))
        right_wrap, right = self.card(body, 14)
        right_wrap.pack(side="right", fill="both", expand=True, padx=(10, 0))

        self.session_title = ttk.Label(left, text="", style="Big.TLabel")
        self.session_title.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 14))

        ttk.Label(left, text="Year", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        year_vcmd = (self.root.register(self.validate_year_input), "%P")
        self.year_entry = ttk.Entry(
            left,
            textvariable=self.year_var,
            font=("Segoe UI Semibold", 18),
            width=8,
            validate="key",
            validatecommand=year_vcmd,
        )
        self.year_entry.grid(row=1, column=1, sticky="ew", pady=5)
        self.year_entry.bind("<KeyPress>", self._year_keypress)
        self.year_entry.bind("<KeyRelease>", lambda _e: self.refresh_type_options())

        ttk.Label(left, text="Mint", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=5)
        self.mint_combo = ttk.Combobox(left, values=state.MINTS, state="readonly")
        self.mint_combo.grid(row=2, column=1, sticky="ew", pady=5)
        self.mint_combo.set(state.MINTS[self.mint_index])
        self.mint_combo.bind("<<ComboboxSelected>>", self.on_mint_selected)

        ttk.Label(left, text="Coin Type", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=5)
        self.type_combo = ttk.Combobox(left, state="readonly")
        self.type_combo.grid(row=3, column=1, columnspan=3, sticky="ew", pady=5)
        self.type_combo.bind("<<ComboboxSelected>>", self.on_type_selected)

        ttk.Label(left, text="Notes", style="Card.TLabel").grid(row=4, column=0, sticky="nw", pady=5)
        self.notes_entry = ttk.Entry(left, textvariable=self.notes_var)
        self.notes_entry.grid(row=4, column=1, columnspan=3, sticky="ew", pady=5)

        check_row = ttk.Frame(left, style="Card.TFrame")
        check_row.grid(row=5, column=1, columnspan=3, sticky="ew", pady=(8, 0))
        self.keep_check = ttk.Checkbutton(check_row, text="Keep / Bulk  (*)", variable=self.keep_bulk, command=self.on_keep_toggle)
        self.keep_check.pack(side="left", padx=(0, 16))
        self.reject_check = ttk.Checkbutton(check_row, text="Reject  (/)", variable=self.reject, command=self.on_reject_toggle)
        self.reject_check.pack(side="left", padx=(0, 10))
        self.reject_combo = ttk.Combobox(check_row, textvariable=self.reject_reason, values=state.REJECT_REASONS, state="readonly", width=24)
        self.reject_combo.pack(side="left")

        btn_row = ttk.Frame(left, style="Card.TFrame")
        btn_row.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(18, 4))
        ttk.Button(btn_row, text="Save Coin  (Enter)", style="Accent.TButton", command=self.save_coin).pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="Next Mint  (+)", command=self.next_mint).pack(side="left", padx=4)
        ttk.Button(btn_row, text="Prev Mint  (-)", command=self.prev_mint).pack(side="left", padx=4)
        ttk.Button(btn_row, text="Next Type  (.)", command=self.next_type).pack(side="left", padx=4)
        if self.session.get("session_type") == "Coin roll hunt" and self.session.get("roll_mode") in ("automatic", "manual"):
            ttk.Button(btn_row, text="Next Roll", command=self.next_roll).pack(side="right")

        self.warning_label = ttk.Label(left, text="", style="Muted.TLabel", wraplength=650)
        self.warning_label.grid(row=7, column=0, columnspan=4, sticky="w", pady=(8, 0))

        for i in range(4):
            left.columnconfigure(i, weight=1 if i in (1, 2, 3) else 0)

        ttk.Label(right, text="Session stats", style="Big.TLabel").pack(anchor="w")
        self.stats_text = tk.Text(right, height=8, bg=COLORS["panel"], fg=COLORS["dark"], relief="flat", font=("Consolas", 10), wrap="word")
        self.stats_text.pack(fill="x", pady=(8, 12))
        ttk.Label(right, text="Recent coins", style="Big.TLabel").pack(anchor="w")
        columns = ("year", "mint", "type", "status")
        self.recent_tree = ttk.Treeview(right, columns=columns, show="headings", height=12)
        for col, text, width in [("year", "Year", 65), ("mint", "Mint", 70), ("type", "Type", 220), ("status", "Status", 100)]:
            self.recent_tree.heading(col, text=text)
            self.recent_tree.column(col, width=width, anchor="w")
        self.recent_tree.pack(fill="both", expand=True, pady=(8, 0))
        ttk.Button(right, text="Delete Highlighted Coin", style="Danger.TButton", command=self.delete_selected_recent).pack(fill="x", pady=(12, 0))

        self.focus_widgets = [self.year_entry, self.mint_combo, self.type_combo, self.notes_entry, self.keep_check, self.reject_check, self.reject_combo, self.recent_tree]
        self.refresh_all()
        self.year_entry.focus_set()

    def refresh_all(self):
        if not self.session:
            return
        self.session_title.configure(text=f"{self.session['session_name']}  •  {self.session.get('country','')}  •  {self.session.get('denomination','')}")
        self.refresh_type_options()
        self.refresh_stats()
        self.refresh_recent()
        self.update_warning()

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

        if keysym in ("KP_Add", "plus"):
            self.next_mint()
            return "break"
        if keysym in ("KP_Subtract", "minus"):
            self.prev_mint()
            return "break"
        if keysym in ("KP_Decimal", "period"):
            self.next_type()
            return "break"
        if keysym in ("KP_Divide", "slash"):
            self.toggle_reject()
            return "break"
        if keysym in ("KP_Multiply", "asterisk"):
            self.toggle_keep()
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
        if not hasattr(self, "stats_text"):
            return
        total, today = sorting.session_counts(self.session.get("log", []))
        kept = sum(1 for c in self.session["log"] if sorting.boolish(c.get("keep_bulk", False)))
        rejected = sum(1 for c in self.session["log"] if sorting.boolish(c.get("reject", False)))
        new_collection = sum(1 for c in self.session["log"] if sorting.boolish(c.get("new_collection", False)))
        roll_line = ""
        if self.session.get("session_type") == "Coin roll hunt" and self.session.get("roll_mode"):
            roll_line = f"\nRoll: {self.session.get('current_roll', 1)}   Count: {self.session.get('current_roll_count', 0)}/{self.session.get('roll_quantity') or '?'}"
        text = f"Total coins: {total}\nToday:       {today}\nKeep/Bulk:   {kept}\nRejected:    {rejected}\nNew Coll.:   {new_collection}{roll_line}"
        self.stats_text.configure(state="normal")
        self.stats_text.delete("1.0", "end")
        self.stats_text.insert("1.0", text)
        self.stats_text.configure(state="disabled")

    def refresh_recent(self):
        if not hasattr(self, "recent_tree"):
            return
        self.recent_tree.delete(*self.recent_tree.get_children())
        for idx, coin in list(enumerate(self.session.get("log", [])))[-40:][::-1]:
            status = "New Collection" if sorting.boolish(coin.get("new_collection", False)) else "Reject" if sorting.boolish(coin.get("reject", False)) else "Keep/Bulk" if sorting.boolish(coin.get("keep_bulk", False)) else "Logged"
            self.recent_tree.insert("", "end", iid=str(idx), values=(coin.get("year", ""), coin.get("mint", ""), coin.get("coin_type", ""), status))

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
        """When OTHER is selected, offer the Numista N# workflow immediately."""
        option = self.selected_type_option()
        if not option or option.get("coin_type") != "OTHER":
            return

        response = messagebox.askyesnocancel(
            "OTHER coin type selected",
            "OTHER is for a coin type that is not yet known locally.\n\n"
            "Open Numista search and add this type by N# now?\n\n"
            "Yes = open/search Numista and enter N#\n"
            "No = keep OTHER selected for now\n"
            "Cancel = go back to the first listed type",
            parent=self.root,
        )
        if response is None:
            if self.current_type_options:
                self.type_index = 0
                try:
                    self.type_combo.current(0)
                except Exception:
                    pass
            return
        if response is False:
            return

        row = self.add_numista_type_dialog()
        if row:
            self.select_numista_row_option(row)

    def on_keep_toggle(self):
        if self.keep_bulk.get():
            self.reject.set(False)

    def on_reject_toggle(self):
        if self.reject.get():
            self.keep_bulk.set(False)

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
        new_collection = False
        reject = bool(self.reject.get())
        keep_bulk = bool(self.keep_bulk.get())
        reject_reason = self.reject_reason.get() if reject else ""
        if not found:
            if not messagebox.askyesno("Possible New Collection", "This coin was not found in your Numista CSV.\n\nMark it as New Collection and save it?"):
                return
            new_collection = True
            reject = False
            keep_bulk = False
            reject_reason = ""

        roll_mode = self.session.get("roll_mode", "")
        roll_number = ""
        roll_coin_number = ""
        roll_quantity = self.session.get("roll_quantity", "") or ""
        if self.session.get("session_type") == "Coin roll hunt" and roll_mode in ("automatic", "manual"):
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
        self.status_var.set(f"Saved {year}-{mint_name} • {option.get('coin_type', 'Unknown')}")
        self.year_var.set("")
        self.notes_var.set("")
        self.keep_bulk.set(False)
        self.reject.set(False)
        self.type_index = 0
        self.refresh_all()
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
        win.geometry("520x240")
        frame = ttk.Frame(win, padding=18, style="TFrame")
        frame.pack(fill="both", expand=True)
        country_var = tk.StringVar(value=self.session.get("country", ""))
        denom_var = tk.StringVar(value=self.session.get("denomination", ""))
        ttk.Label(frame, text="Country").pack(anchor="w")
        country_combo = ttk.Combobox(frame, textvariable=country_var, values=self.numista_countries, state="readonly")
        country_combo.pack(fill="x", pady=(4, 10))
        ttk.Label(frame, text="Denomination").pack(anchor="w")
        denom_combo = ttk.Combobox(frame, textvariable=denom_var, state="readonly")
        denom_combo.pack(fill="x", pady=(4, 14))

        def refresh(*_):
            labels = self.denoms_by_country.get(country_var.get(), [])
            denom_combo["values"] = labels
            if labels and denom_var.get() not in labels:
                denom_var.set(labels[0])
        country_combo.bind("<<ComboboxSelected>>", refresh)
        refresh()

        def apply():
            denom = denom_var.get()
            if not country_var.get() or not denom:
                return
            face, currency = utils.split_denom_label(denom)
            self.session["country"] = country_var.get()
            self.session["denomination"] = denom
            self.session["face_value"] = face
            self.session["currency"] = currency
            storage.save_session_meta(self.session)
            win.destroy()
            self.refresh_all()
        ttk.Button(frame, text="Cancel", command=win.destroy).pack(side="left")
        ttk.Button(frame, text="Apply", style="Accent.TButton", command=apply).pack(side="right")
        country_combo.focus_set()

    def edit_session_notes(self):
        if not self.session:
            return
        value = simpledialog.askstring("Session Notes", "Notes for this session:", initialvalue=self.session.get("session_notes", ""), parent=self.root)
        if value is not None:
            self.session["session_notes"] = value
            storage.save_session_meta(self.session)
            self.status_var.set("Session notes saved.")


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
        notebook.add(general, text="General")
        notebook.add(api_tab, text="Numista API")
        notebook.add(sound_tab, text="Sound")
        notebook.add(roll_tab, text="Roll quantities")

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
        ttk.Button(general, text="Reload Numista CSV + Coin Types", style="Blue.TButton", command=self.reload_numista_data).grid(row=4, column=0, columnspan=3, sticky="ew", pady=(4, 10))
        ttk.Label(general, text=f"Settings file:\n{state.SETTINGS_PATH}", style="Muted.TLabel", wraplength=680).grid(row=5, column=0, columnspan=3, sticky="w", pady=(10, 0))
        ttk.Label(general, text=f"Loaded now: {len(self.numista_files)} Numista CSV file(s), {len(self.numista_index)} owned coin key(s).", style="Muted.TLabel").grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 0))
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

    def add_numista_type_dialog(self):
        """Fetch, verify, and save a Numista type from the GUI.

        Returns the saved/cached Coin_Types.csv row when a type is available,
        otherwise returns None.
        """
        settings.load_settings()
        if self.session:
            should_search = messagebox.askyesnocancel(
                "Numista search",
                "Open Numista search in your browser first?\n\nYes = open search page\nNo = I already know the N#\nCancel = stop",
                parent=self.root,
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
        n_value = simpledialog.askstring("Add Numista type", "Enter Numista N# for the coin type, example 457 or N#457:", parent=self.root)
        if not n_value:
            return None
        clean_number = numista.clean_numista_number(n_value)
        cached = numista.best_cached_numista_row(clean_number)
        if cached:
            if messagebox.askyesno("Use local cached type?", f"This N# already exists in Coin_Types.csv.\n\nN# {cached.get('numista_number', '')} - {cached.get('numista_title', '')}\n{cached.get('country', '')} | {cached.get('denomination', '')}\n\nUse this cached type instead of spending an API call?", parent=self.root):
                settings.log_numista_cache_hit(clean_number)
                choice = numista.cached_row_choice(cached)
                if self.session and choice:
                    self.apply_numista_choice_to_session(choice)
                self.reload_numista_data()
                self.status_var.set(f"Using cached Numista type N# {clean_number}.")
                return cached

        details, error = self.fetch_numista_type_details_gui(clean_number, parent=self.root)
        if error:
            messagebox.showerror("Numista lookup failed", error, parent=self.root)
            return None
        summary = self.numista_detail_summary(details)
        if not messagebox.askyesno("Verify Numista result", summary + "\n\nSave this type to Coin_Types.csv?", parent=self.root):
            return None

        choice = numista.numista_choice_from_details(details)
        if not choice:
            if not self.session:
                messagebox.showerror("Cannot save type", "The API result did not include enough country/value data, and no active session is available as a fallback.", parent=self.root)
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
                if messagebox.askyesno("Change active denomination?", f"The API result is:\n{choice.get('country')} | {choice.get('denomination')}\n\nChange the active session to this country/denomination?", parent=self.root):
                    self.apply_numista_choice_to_session(choice)
            self.session["numista_type_index"] = self.numista_type_index
            storage.save_session_meta(self.session)

        self.reload_numista_data()
        self.status_var.set(f"Saved Numista type N# {row.get('numista_number', '')} - {row.get('numista_title', '')}")
        messagebox.showinfo("Saved", f"Saved to Coin_Types.csv:\n\nN# {row.get('numista_number', '')} - {row.get('numista_title', '')}", parent=self.root)
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
        self.root.bind_all("<KP_Add>", lambda e: self._consume(e, self.next_mint))
        self.root.bind_all("<plus>", lambda e: self._consume(e, self.next_mint))
        self.root.bind_all("<KP_Subtract>", lambda e: self._consume(e, self.prev_mint))
        self.root.bind_all("<minus>", lambda e: self._consume(e, self.prev_mint))
        self.root.bind_all("<KP_Decimal>", lambda e: self._consume(e, self.next_type))
        self.root.bind_all("<period>", lambda e: self._consume(e, self.next_type))
        self.root.bind_all("<KP_Multiply>", lambda e: self._consume(e, self.toggle_keep))
        self.root.bind_all("<asterisk>", lambda e: self._consume(e, self.toggle_keep))
        self.root.bind_all("<KP_Divide>", lambda e: self._consume(e, self.toggle_reject))
        self.root.bind_all("<slash>", lambda e: self._consume(e, self.toggle_reject))
        self.root.bind_all("<KP_Enter>", lambda e: self._consume(e, self.save_coin))
        self.root.bind_all("<Return>", self._return_key)
        self.root.bind_all("<Control-o>", lambda e: self._consume(e, lambda: utils.open_folder(state.DATA_DIR)))

    def _return_key(self, event):
        widget = self.root.focus_get()
        # Let listboxes/combobox dropdowns handle Return where appropriate outside sorting.
        if self.session and hasattr(self, "year_entry"):
            return self._consume(event, self.save_coin)
        return None

    def _consume(self, event, func):
        try:
            func()
        finally:
            return "break"

    def toggle_keep(self):
        if not self.session:
            return
        self.keep_bulk.set(not self.keep_bulk.get())
        self.on_keep_toggle()

    def toggle_reject(self):
        if not self.session:
            return
        self.reject.set(not self.reject.get())
        self.on_reject_toggle()


def main():
    root = tk.Tk()
    app = CoinSortGUI(root)
    root.mainloop()
    return app


if __name__ == "__main__":
    main()
