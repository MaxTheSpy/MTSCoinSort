# MTS CoinSort V0.0.19
# uses prompt_toolkit
# pip install prompt_toolkit or pip install prompt_toolkit colorama

import csv
import json
import os
import re
import sys
import select
import shutil
import builtins
import io
import ctypes
from datetime import datetime
from collections import Counter

try:
    import termios
    import tty
except ImportError:
    termios = None
    tty = None

try:
    from prompt_toolkit.input import create_input
    from prompt_toolkit.keys import Keys
except ImportError:
    create_input = None
    Keys = None

try:
    import msvcrt
except ImportError:
    msvcrt = None

MINTS = ["P", "D", "S", "W", "No Mint"]
DENOMS = []  # Built from Numista CSV exports at startup.
SESSION_TYPES = ["Bulk sorting", "Coin roll hunt", "Collection sorting", "Inventory audit", "Other"]

APP_NAME = "MTS CoinSort"
APP_SLUG = "mts-coinsort"


def default_config_dir():
    """Return the OS-standard folder where settings.json should live.

    Keep settings outside the movable data folder so the app can always find
    the user's chosen data_dir on startup.
    """
    if os.name == "nt":
        root = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return os.path.join(root, APP_NAME)
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", APP_NAME)
    root = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(root, APP_SLUG)


def default_data_dir():
    """Return the OS-standard folder where sessions/exports/Numista CSV live."""
    if os.name == "nt":
        root = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return os.path.join(root, APP_NAME)
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", APP_NAME)
    root = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(root, APP_SLUG)


def clean_user_path(path):
    """Expand ~ and environment variables from settings.json path values."""
    return os.path.abspath(os.path.expandvars(os.path.expanduser(str(path).strip())))


CONFIG_DIR = default_config_dir()
SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.json")
DATA_DIR = default_data_dir()
SESSIONS_DIR = os.path.join(DATA_DIR, "coin_sort_sessions")
NUMISTA_DIR = os.path.join(DATA_DIR, "Numista CSV")
EXPORTS_DIR = os.path.join(DATA_DIR, "coin_sort_exports")

DEFAULT_HOTKEYS = {
    "reject": "/",
    "keep_bulk": "*",
    "mint_next": "+",
    "mint_previous": "-",
    "save_quit": "q",
}

HOTKEY_LABELS = {
    "reject": "Toggle Reject",
    "keep_bulk": "Toggle Keep/Bulk",
    "mint_next": "Next Mint",
    "mint_previous": "Previous Mint",
    "save_quit": "Save + Quit",
}

HOTKEYS = DEFAULT_HOTKEYS.copy()
DENOM_VALUES = {
    "1 cent": "0.01",
    "5 cent": "0.05",
    "10 cent": "0.10",
    "25 cent": "0.25",
    "50 cent": "0.50",
    "1 dollar": "1.00",
}
CSV_HEADERS = [
    "timestamp", "session_name", "session_type", "country", "denomination", "currency", "face_value",
    "year", "mint", "notes", "reject", "reject_reason", "keep_bulk",
    "numista_found", "possible_missing_collection", "new_collection"
]

REJECT_REASONS = [
    "Already Have Enough",
    "Bulk Overflow",
    "Low Quality",
    "Damaged",
    "Corroded",
    "Worn",
    "Other / custom reason",
]

KEY_UP = "UP"
KEY_DOWN = "DOWN"
KEY_RIGHT = "RIGHT"
KEY_LEFT = "LEFT"
KEY_ENTER = "ENTER"
KEY_BACKSPACE = "BACKSPACE"
KEY_DELETE = "DELETE"
KEY_ESC = "ESC"
KEY_TAB = "TAB"
KEY_SHIFT_TAB = "SHIFT_TAB"

FOCUS_ORDER = ["year", "mint", "save", "notes", "recent", "change_denom", "statistics", "invalid_check", "quit"]

# ANSI color/bold works in most Linux terminals.
# On Windows, we attempt to enable Virtual Terminal Processing. If that is not
# available, the app falls back to plain text plus cls-based screen clears.
USE_COLOR = True
BIG_UI = True
ANSI_SUPPORTED = os.name != "nt"


def enable_ansi_on_windows():
    """Enable ANSI escape handling in modern Windows terminals when possible.

    Returns True when ANSI control sequences should be safe to use.
    Linux/macOS terminals normally support ANSI already.
    """
    if os.name != "nt":
        return True

    # This no-op shell call helps some Windows terminal hosts initialize ANSI.
    try:
        os.system("")
    except Exception:
        pass

    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        if handle in (0, -1):
            return False

        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False

        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        new_mode = mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
        if not kernel32.SetConsoleMode(handle, new_mode):
            return False

        return True
    except Exception:
        return False


def configure_terminal_output():
    """Set global terminal capabilities after startup/settings load."""
    global ANSI_SUPPORTED, USE_COLOR
    ANSI_SUPPORTED = enable_ansi_on_windows()

    # If ANSI is not supported, disable colors too, because the color helpers
    # are also ANSI escape sequences.
    if not ANSI_SUPPORTED:
        USE_COLOR = False


def c(text, code):
    if not USE_COLOR or not ANSI_SUPPORTED:
        return text
    return f"\033[{code}m{text}\033[0m"


def bold(text):
    return c(text, "1")


def cyan(text):
    return c(text, "96")


def green(text):
    return c(text, "92")


def yellow(text):
    return c(text, "93")


def red(text):
    return c(text, "91")


def dim(text):
    return c(text, "2")


def reverse(text):
    return c(text, "7")


_SCREEN_BUFFER = None


def _flush_screen_buffer():
    """Write a full screen redraw in one terminal update.

    Linux/macOS use ANSI cursor/screen controls for smooth redraws. Windows
    uses ANSI when available, otherwise it falls back to `cls` so PyInstaller
    console builds do not print raw escape codes like ``←[2J``.
    """
    global _SCREEN_BUFFER
    if _SCREEN_BUFFER is None:
        return

    content = _SCREEN_BUFFER.getvalue()
    _SCREEN_BUFFER = None

    # In --windowed PyInstaller builds sys.stdout can be None. The app should
    # be built with --console, but this guard prevents a crash if it is not.
    if sys.stdout is None:
        return

    if ANSI_SUPPORTED:
        sys.stdout.write("\033[?25l\033[H\033[2J")
        sys.stdout.write(content)
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
    else:
        # Plain Windows console fallback. This may flicker a little more than
        # ANSI redraws, but it stays readable and works in cmd/PowerShell/exe.
        os.system("cls" if os.name == "nt" else "clear")
        sys.stdout.write(content)
        sys.stdout.flush()


def print(*args, sep=" ", end="\n", file=None, flush=False):
    """Module-local print that buffers screen redraws after clear()."""
    global _SCREEN_BUFFER
    if file is not None and file is not sys.stdout:
        return builtins.print(*args, sep=sep, end=end, file=file, flush=flush)
    if _SCREEN_BUFFER is None:
        return builtins.print(*args, sep=sep, end=end, flush=flush)
    _SCREEN_BUFFER.write(sep.join(str(arg) for arg in args) + end)
    if flush:
        _flush_screen_buffer()


def clear():
    """Start a buffered redraw instead of blanking the terminal immediately."""
    global _SCREEN_BUFFER
    _SCREEN_BUFFER = io.StringIO()


def key_display(key):
    names = {
        KEY_ENTER: "ENTER",
        KEY_BACKSPACE: "BACKSPACE",
        KEY_DELETE: "DELETE",
        KEY_ESC: "ESC",
        KEY_TAB: "TAB",
        KEY_SHIFT_TAB: "SHIFT+TAB",
        KEY_UP: "UP",
        KEY_DOWN: "DOWN",
        KEY_LEFT: "LEFT",
        KEY_RIGHT: "RIGHT",
        " ": "SPACE",
    }
    return names.get(key, str(key).upper() if len(str(key)) == 1 else str(key))


def normalize_key_for_compare(key):
    if isinstance(key, str) and len(key) == 1:
        return key.lower()
    return key


def hotkey_matches(key, action):
    return normalize_key_for_compare(key) == normalize_key_for_compare(HOTKEYS.get(action, DEFAULT_HOTKEYS[action]))


def apply_data_dir(path):
    """Update all user-data folders after loading a custom data_dir."""
    global DATA_DIR, SESSIONS_DIR, NUMISTA_DIR, EXPORTS_DIR
    DATA_DIR = clean_user_path(path)
    SESSIONS_DIR = os.path.join(DATA_DIR, "coin_sort_sessions")
    NUMISTA_DIR = os.path.join(DATA_DIR, "Numista CSV")
    EXPORTS_DIR = os.path.join(DATA_DIR, "coin_sort_exports")


def ensure_app_dirs():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    os.makedirs(NUMISTA_DIR, exist_ok=True)
    os.makedirs(EXPORTS_DIR, exist_ok=True)


def load_settings():
    global HOTKEYS, USE_COLOR, BIG_UI
    HOTKEYS = DEFAULT_HOTKEYS.copy()
    if not os.path.exists(SETTINGS_PATH):
        ensure_app_dirs()
        save_settings()
        return
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        custom_data_dir = data.get("data_dir", "")
        if isinstance(custom_data_dir, str) and custom_data_dir.strip():
            apply_data_dir(custom_data_dir)

        saved_hotkeys = data.get("hotkeys", {})
        for action in DEFAULT_HOTKEYS:
            if action in saved_hotkeys and isinstance(saved_hotkeys[action], str) and saved_hotkeys[action]:
                HOTKEYS[action] = saved_hotkeys[action]
        USE_COLOR = bool(data.get("use_color", USE_COLOR))
        BIG_UI = bool(data.get("big_ui", BIG_UI))
        ensure_app_dirs()
    except Exception:
        HOTKEYS = DEFAULT_HOTKEYS.copy()
        ensure_app_dirs()


def save_settings():
    ensure_app_dirs()
    data = {
        "data_dir": DATA_DIR,
        "hotkeys": HOTKEYS,
        "use_color": USE_COLOR,
        "big_ui": BIG_UI,
    }
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def reset_hotkeys_to_default():
    global HOTKEYS
    HOTKEYS = DEFAULT_HOTKEYS.copy()
    save_settings()


def read_assignable_key():
    while True:
        key = read_key()
        if key in (KEY_ESC, KEY_BACKSPACE):
            return None
        # Keep arrows, Tab, Enter, and normal printable keys assignable.
        return key


def settings_menu():
    global USE_COLOR, BIG_UI
    actions = list(DEFAULT_HOTKEYS.keys())
    menu_items = [HOTKEY_LABELS[action] for action in actions] + ["Toggle colors", "Toggle big title", "Reset hotkeys to defaults", "Back"]
    index = 0

    while True:
        clear()
        print(c("=" * 100, "94"))
        print(bold(cyan("SETTINGS".center(100))))
        print(c("=" * 100, "94"))
        print()
        print(bold("Select a hotkey option, press ENTER, then press the key you want to assign."))
        print(dim(f"Settings file: {SETTINGS_PATH}"))
        print(dim(f"Data folder  : {DATA_DIR}"))
        print(dim("To move sessions/exports/Numista CSV, edit data_dir in settings.json, then restart."))
        print()

        for i, item in enumerate(menu_items):
            if i < len(actions):
                action = actions[i]
                value = key_display(HOTKEYS[action])
                line = f"{item:<28} {cyan(value)}"
            elif item == "Toggle colors":
                line = f"{item:<28} {'ON' if USE_COLOR else 'OFF'}"
            elif item == "Toggle big title":
                line = f"{item:<28} {'ON' if BIG_UI else 'OFF'}"
            else:
                line = item
            print((reverse(line) if i == index else line))

        print()
        print(dim("TAB/DOWN/+ next | UP/- previous | ENTER select | BACKSPACE/ESC back"))

        key = read_key()
        if key in (KEY_ESC, KEY_BACKSPACE):
            save_settings()
            return
        if key in (KEY_TAB, KEY_DOWN, "+", "="):
            index = (index + 1) % len(menu_items)
            continue
        if key in (KEY_SHIFT_TAB, KEY_UP, "-", "_"):
            index = (index - 1) % len(menu_items)
            continue
        if key != KEY_ENTER:
            continue

        selected = menu_items[index]
        if index < len(actions):
            action = actions[index]
            while True:
                clear()
                print(c("=" * 90, "94"))
                print(bold(cyan(f"ASSIGN HOTKEY: {HOTKEY_LABELS[action]}".center(90))))
                print(c("=" * 90, "94"))
                print()
                print(f"Current key: {bold(yellow(key_display(HOTKEYS[action])))}")
                print()
                print(bold("Press the new key now."))
                print(dim("BACKSPACE/ESC cancels. You can press numpad /, *, +, -, ENTER, etc."))
                new_key = read_assignable_key()
                if new_key is None:
                    break

                conflict = None
                for other_action, other_key in HOTKEYS.items():
                    if other_action != action and normalize_key_for_compare(other_key) == normalize_key_for_compare(new_key):
                        conflict = other_action
                        break

                HOTKEYS[action] = new_key
                if conflict:
                    HOTKEYS[conflict] = DEFAULT_HOTKEYS[conflict]
                    clear()
                    print(yellow(f"{key_display(new_key)} was already used by {HOTKEY_LABELS[conflict]}."))
                    print(yellow(f"{HOTKEY_LABELS[conflict]} was reset to {key_display(HOTKEYS[conflict])}."))
                    print()
                    print("Press any key to continue.")
                    read_key()
                save_settings()
                break
        elif selected == "Toggle colors":
            USE_COLOR = not USE_COLOR
            save_settings()
        elif selected == "Toggle big title":
            BIG_UI = not BIG_UI
            save_settings()
        elif selected == "Reset hotkeys to defaults":
            reset_hotkeys_to_default()
        elif selected == "Back":
            save_settings()
            return


def read_key():
    _flush_screen_buffer()
    """Cross-platform key reader.

    IMPORTANT: The first Prompt Toolkit test created/closed a prompt_toolkit
    input object on every keypress. On some terminals that can cause rapid
    repainting/flashing because the terminal mode is constantly reset while
    the rest of this app is also clearing/redrawing the screen.

    This version keeps the existing no-dependency Unix reader on Linux/macOS
    and uses Windows' built-in msvcrt reader on Windows. Prompt Toolkit can
    still be used later for a fuller UI rewrite, but this avoids the flashing
    while preserving Windows compatibility for the current app structure.
    """
    if os.name == "nt" and msvcrt is not None:
        return read_key_windows()
    return read_key_unix()


def read_key_windows():
    """Read one key on Windows using msvcrt, mapping it to the app constants."""
    ch = msvcrt.getwch()

    # Extended keys such as arrows come through as a prefix, then a second code.
    if ch in ("\x00", "\xe0"):
        ch2 = msvcrt.getwch()
        mapping = {
            "H": KEY_UP,
            "P": KEY_DOWN,
            "M": KEY_RIGHT,
            "K": KEY_LEFT,
            "S": KEY_DELETE,
        }
        return mapping.get(ch2, f"SPECIAL_WIN_{repr(ch2)}")

    if ch in ("\r", "\n"):
        return KEY_ENTER
    if ch == "\t":
        return KEY_TAB
    if ch in ("\x08", "\x7f"):
        return KEY_BACKSPACE
    if ch == "\x1b":
        return KEY_ESC
    return ch


def read_key_prompt_toolkit():
    """Optional single-key Prompt Toolkit reader kept for future experiments.

    It is intentionally not used by read_key() right now because repeatedly
    entering/leaving prompt_toolkit raw mode caused screen flashing in this app.
    """
    if create_input is None:
        return read_key_windows() if os.name == "nt" and msvcrt is not None else read_key_unix()
    inp = create_input()
    try:
        with inp.raw_mode():
            key_presses = inp.read_keys()
    finally:
        try:
            inp.close()
        except Exception:
            pass

    if not key_presses:
        return ""

    kp = key_presses[0]
    key = kp.key
    data = kp.data

    mapping = {
        getattr(Keys, "Enter", None): KEY_ENTER,
        getattr(Keys, "ControlM", None): KEY_ENTER,
        getattr(Keys, "Tab", None): KEY_TAB,
        getattr(Keys, "ControlI", None): KEY_TAB,
        getattr(Keys, "BackTab", None): KEY_SHIFT_TAB,
        getattr(Keys, "Backspace", None): KEY_BACKSPACE,
        getattr(Keys, "Delete", None): KEY_DELETE,
        getattr(Keys, "Escape", None): KEY_ESC,
        getattr(Keys, "Up", None): KEY_UP,
        getattr(Keys, "Down", None): KEY_DOWN,
        getattr(Keys, "Right", None): KEY_RIGHT,
        getattr(Keys, "Left", None): KEY_LEFT,
    }
    if key in mapping and mapping[key] is not None:
        return mapping[key]

    if data in ("\r", "\n"):
        return KEY_ENTER
    if data == "\t":
        return KEY_TAB
    if data in ("\x7f", "\b"):
        return KEY_BACKSPACE
    if data == "\x1b":
        return KEY_ESC

    if isinstance(data, str) and len(data) == 1:
        return data
    if isinstance(key, str) and len(key) == 1:
        return key
    return str(key)


def read_key_unix():
    """Linux/macOS raw key reader with Tab, arrows, numpad chars, Enter, Backspace."""
    if termios is None or tty is None:
        raise RuntimeError("This version needs a terminal with termios/tty support.")

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)

        if ch in ("\r", "\n"):
            return KEY_ENTER
        if ch == "\t":
            return KEY_TAB
        if ch in ("\x7f", "\b"):
            return KEY_BACKSPACE

        if ch == "\x1b":
            # ESC alone or start of ANSI escape sequence. 0.20s is more reliable on Linux terminals.
            if not select.select([sys.stdin], [], [], 0.20)[0]:
                return KEY_ESC

            ch2 = sys.stdin.read(1)

            # Shift+Tab is usually ESC [ Z
            if ch2 == "[":
                if not select.select([sys.stdin], [], [], 0.20)[0]:
                    return KEY_ESC
                ch3 = sys.stdin.read(1)

                if ch3 == "A":
                    return KEY_UP
                if ch3 == "B":
                    return KEY_DOWN
                if ch3 == "C":
                    return KEY_RIGHT
                if ch3 == "D":
                    return KEY_LEFT
                if ch3 == "Z":
                    return KEY_SHIFT_TAB

                # Delete is often ESC [ 3 ~
                if ch3 == "3" and select.select([sys.stdin], [], [], 0.20)[0]:
                    ch4 = sys.stdin.read(1)
                    if ch4 == "~":
                        return KEY_DELETE

                return f"SPECIAL_ESC_[{repr(ch3)}]"

            # Some terminals/keypads send application cursor mode: ESC O A/B/C/D
            if ch2 == "O":
                if not select.select([sys.stdin], [], [], 0.20)[0]:
                    return KEY_ESC
                ch3 = sys.stdin.read(1)
                if ch3 == "A":
                    return KEY_UP
                if ch3 == "B":
                    return KEY_DOWN
                if ch3 == "C":
                    return KEY_RIGHT
                if ch3 == "D":
                    return KEY_LEFT
                return f"SPECIAL_ESC_O{repr(ch3)}"

            return KEY_ESC

        return ch

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def safe_filename(name):
    name = name.strip()
    name = re.sub(r"[^\w\s.-]", "", name)
    name = re.sub(r"\s+", "_", name)
    return name or "coin_sort_session"


def ensure_sessions_dir():
    ensure_app_dirs()


def ensure_numista_dir():
    ensure_app_dirs()


def ensure_exports_dir():
    ensure_app_dirs()


def normalize_decimal(value):
    """Normalize values like 0.1, 0.10, 1, 1.00 for matching."""
    try:
        return f"{float(str(value).strip()):.2f}"
    except ValueError:
        return str(value).strip()


def normalize_mint(value):
    value = str(value).strip()
    if value.lower() in ("", "no mint", "none", "nan"):
        return ""

    # Numista exports can contain extra punctuation/spacing. Keep only the
    # common US mint letters so "D ", "D." etc. still match.
    value = value.upper().replace(" ", "")
    if value in ("P", "D", "S", "W"):
        return value
    if value.startswith("P"):
        return "P"
    if value.startswith("D"):
        return "D"
    if value.startswith("S"):
        return "S"
    if value.startswith("W"):
        return "W"
    return value


def coin_mint_candidates(mint_value):
    mint = normalize_mint(mint_value)
    if mint in ("", "P", "NO MINT"):
        # Numista often leaves Philadelphia/no-mint blank, but some rows may use P.
        return {"", "P", "NO MINT"}
    return {mint}


def make_denom_label(face_value, currency):
    face = normalize_decimal(face_value)
    currency = str(currency).strip()
    return f"{face} {currency}" if currency else face


def split_denom_label(label):
    parts = str(label).strip().split(" ", 1)
    face = normalize_decimal(parts[0]) if parts else ""
    currency = parts[1].strip() if len(parts) > 1 else ""
    return face, currency


def load_numista_index():
    """Load owned coins from every CSV in ./Numista CSV.

    Uses Numista export columns by position:
    A Country, D Currency, E Face value, T Gregorian year, U Mintmark, Y Quantity.

    Returns:
      index: set of (country, face_value, gregorian_year, mintmark) for owned coins
      csv_files: list of loaded CSV paths
      countries: sorted country names found in the export
      denoms_by_country: {country: ["0.01 Dollar (1785-date)", ...]}
    """
    ensure_numista_dir()
    index = set()
    countries = set()
    denom_map = {}

    csv_files = [
        os.path.join(NUMISTA_DIR, name)
        for name in os.listdir(NUMISTA_DIR)
        if name.lower().endswith(".csv")
    ]

    for path in csv_files:
        try:
            with open(path, "r", newline="", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                next(reader, None)  # header
                for row in reader:
                    if len(row) < 21:
                        continue

                    country = row[0].strip()
                    currency = row[3].strip() if len(row) > 3 else ""
                    face_value = normalize_decimal(row[4]) if len(row) > 4 else ""
                    gregorian_year = row[19].strip() if len(row) > 19 else ""
                    mintmark = normalize_mint(row[20]) if len(row) > 20 else ""

                    if not country or not face_value:
                        continue

                    countries.add(country)
                    denom_label = make_denom_label(face_value, currency)
                    denom_map.setdefault(country, set()).add(denom_label)

                    if not gregorian_year:
                        continue

                    # Only count rows that are actually in your collection.
                    # Column Y / index 24 is Quantity in Numista exports.
                    quantity = "1"
                    if len(row) > 24:
                        quantity = row[24].strip() or "0"
                    try:
                        if float(quantity) <= 0:
                            continue
                    except ValueError:
                        # If Quantity is weird but the row is in the export, keep it.
                        pass

                    index.add((country, face_value, gregorian_year, mintmark))
        except Exception:
            # Bad CSVs should not crash sorting. They just won't be used for matching.
            continue

    countries = sorted(countries)
    denoms_by_country = {
        country: sorted(labels, key=lambda label: (split_denom_label(label)[1].lower(), float(split_denom_label(label)[0]) if split_denom_label(label)[0].replace('.', '', 1).isdigit() else 999999, split_denom_label(label)[0]))
        for country, labels in denom_map.items()
    }

    return index, csv_files, countries, denoms_by_country

def coin_exists_in_numista(numista_index, session, year, mint_name):
    country = session.get("country", "").strip()
    face_value = normalize_decimal(session.get("face_value", ""))
    if not country or not face_value or not year:
        return True
    candidates = coin_mint_candidates(mint_name)
    return any((country, face_value, str(year).strip(), mint) in numista_index for mint in candidates)


def choose_country_and_denom(numista_countries, denoms_by_country, current_country=None):
    if not numista_countries:
        clear()
        print(yellow(f"No Numista CSV rows were found in {NUMISTA_DIR}."))
        print("Add one or more Numista export CSV files, then restart.")
        print("Press any key to continue.")
        read_key()
        return None

    country_options = list(numista_countries)
    if current_country in country_options:
        # Put the current country at the top without losing the full list.
        country_options.remove(current_country)
        country_options.insert(0, current_country)

    country = choose_from_list("Select country from Numista CSV:", country_options)
    if not country:
        return None

    denom_options = denoms_by_country.get(country, [])
    if not denom_options:
        clear()
        print(yellow(f"No denominations found for {country}."))
        print("Press any key to return.")
        read_key()
        return None

    denom_label = choose_from_list(f"Select denomination for {country}:", denom_options)
    if not denom_label:
        return None

    face_value, currency = split_denom_label(denom_label)
    return {
        "country": country,
        "denomination": denom_label,
        "currency": currency,
        "face_value": face_value,
    }

def prompt_missing_numista_coin(session, year, mint_name):
    """Force + / - selection, no default. Returns True to keep/save, False to cancel."""
    selection = None  # None, True, False

    def selected(text, is_selected):
        return reverse(text) if is_selected else dim(text)

    while True:
        clear()
        coin_label = f"{year}-{mint_name}  |  {session.get('country', '')} | {session['denomination']}"

        print(c("═" * 100, "93"))
        print(bold(red("⚠  POSSIBLE NEW COLLECTION COIN  ⚠".center(100))))
        print(c("═" * 100, "93"))
        print()
        print(bold(yellow("This coin was NOT found in your Numista CSV.")))
        print()
        print(c("┌" + "─" * 70 + "┐", "96"))
        print(c("│", "96") + bold("  COIN TO VERIFY".ljust(70)) + c("│", "96"))
        print(c("├" + "─" * 70 + "┤", "96"))
        print(c("│", "96") + f"  Year / Mint : {bold(cyan(str(year) + '-' + mint_name))}".ljust(79)[:70] + c("│", "96"))
        print(c("│", "96") + f"  Country     : {bold(cyan(session.get('country', 'Unknown')))}".ljust(79)[:70] + c("│", "96"))
        print(c("│", "96") + f"  Denomination: {bold(cyan(session['denomination']))}".ljust(79)[:70] + c("│", "96"))
        print(c("│", "96") + f"  Session     : {session['session_name']}".ljust(70) + c("│", "96"))
        print(c("└" + "─" * 70 + "┘", "96"))
        print()
        print(red(bold("IMPORTANT:")), yellow("It may be missing from your collection."))
        print(yellow("Put this coin in a SPECIAL VERIFY BIN — separate from Reject and Keep/Bulk."))
        print(dim("You will still get this warning again if you find another matching coin, so you can pick the best one."))
        print()
        print(bold("Save this coin as NEW COLLECTION in the session CSV?"))
        print()

        yes_text = "  YES — save as NEW COLLECTION  "
        no_text = "  NO — cancel and return to entry  "
        print("   +  " + selected(green(yes_text), selection is True))
        print("   -  " + selected(red(no_text), selection is False))
        print()

        if selection is None:
            print(bold(yellow("No option selected yet.")))
        elif selection is True:
            print(green("Selected: YES — this will be marked New Collection."))
        else:
            print(red("Selected: NO — this will not be saved."))

        print()
        print(dim("Use + or - to choose. Then press ENTER. BACKSPACE/ESC cancels."))

        key = read_key()
        if key in ("+", "=", KEY_DOWN, KEY_RIGHT):
            selection = True
        elif key in ("-", "_", KEY_UP, KEY_LEFT):
            selection = False
        elif key == KEY_ENTER and selection is not None:
            return selection
        elif key in (KEY_BACKSPACE, KEY_ESC):
            return False


def session_path(session_name):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return os.path.join(SESSIONS_DIR, f"{timestamp}_{safe_filename(session_name)}.csv")


def write_session_csv(path, log):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
        writer.writeheader()
        for row in log:
            writer.writerow(row)


def load_session_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def text_input(prompt, default=""):
    value = default
    while True:
        clear()
        print(prompt)
        print()
        print(value)
        print()
        print("Type text | ENTER/TAB confirm | BACKSPACE delete | ESC cancel")

        key = read_key()
        if key == KEY_ESC:
            return None
        if key in (KEY_ENTER, KEY_TAB):
            return value.strip()
        if key == KEY_BACKSPACE:
            value = value[:-1]
        elif isinstance(key, str) and len(key) == 1 and key.isprintable():
            value += key


def choose_from_list(title, options):
    index = 0
    while True:
        clear()
        print(title)
        print()
        for i, item in enumerate(options):
            print(("> " if i == index else "  ") + item)
        print()
        print("TAB/DOWN next | UP previous | ENTER confirm | ESC cancel")

        key = read_key()
        if key == KEY_ESC:
            return None
        if key in (KEY_TAB, KEY_DOWN, "+", "="):
            index = (index + 1) % len(options)
        elif key in (KEY_SHIFT_TAB, KEY_UP, "-", "_"):
            index = (index - 1) % len(options)
        elif key == KEY_ENTER:
            return options[index]


def list_sessions():
    ensure_sessions_dir()
    files = [f for f in os.listdir(SESSIONS_DIR) if f.lower().endswith(".csv")]
    files.sort(key=lambda f: os.path.getmtime(os.path.join(SESSIONS_DIR, f)), reverse=True)
    return files


def new_session(numista_countries, denoms_by_country):
    session_name = text_input("Enter new session name:")
    if not session_name:
        return None

    session_type = choose_from_list("Select session type:", SESSION_TYPES)
    if not session_type:
        return None

    coin_choice = choose_country_and_denom(numista_countries, denoms_by_country)
    if not coin_choice:
        return None

    path = session_path(session_name)
    if os.path.exists(path):
        choice = choose_from_list(
            "A session with this name already exists. What do you want to do?",
            ["Resume existing session", "Overwrite and start fresh", "Cancel"]
        )
        if choice == "Resume existing session":
            log = load_session_csv(path)
        elif choice == "Overwrite and start fresh":
            log = []
            write_session_csv(path, log)
        else:
            return None
    else:
        log = []
        write_session_csv(path, log)

    return {"session_name": session_name, "session_type": session_type, "country": coin_choice["country"], "denomination": coin_choice["denomination"], "currency": coin_choice["currency"], "face_value": coin_choice["face_value"], "path": path, "log": log}


def confirm_delete_session(filename, path):
    selection = None
    while True:
        clear()
        print(c("=" * 90, "91"))
        print(bold(red("DELETE SESSION CSV?".center(90))))
        print(c("=" * 90, "91"))
        print()
        print(bold("Selected file:"), cyan(filename))
        print(dim(path))
        print()
        print(red(bold("This moves the session CSV to a backup-style delete filename?")))
        print(yellow("Actually deleting is permanent from this folder, so only confirm if you are sure."))
        print()
        print("   +  " + (reverse(green("  YES — delete this session  ")) if selection is True else dim("  YES — delete this session  ")))
        print("   -  " + (reverse(red("  NO — keep it  ")) if selection is False else dim("  NO — keep it  ")))
        print()
        print(dim("Use + or - to choose. ENTER confirms. BACKSPACE/ESC cancels."))

        key = read_key()
        if key in ("+", "=", KEY_RIGHT, KEY_DOWN):
            selection = True
        elif key in ("-", "_", KEY_LEFT, KEY_UP):
            selection = False
        elif key == KEY_ENTER and selection is not None:
            return selection
        elif key in (KEY_BACKSPACE, KEY_ESC):
            return False


def choose_session_file_for_resume():
    """Session picker that can delete the highlighted session with BACKSPACE."""
    index = 0
    while True:
        files = list_sessions()
        if not files:
            clear()
            print(bold(yellow("No saved sessions found.")))
            print()
            print("Press any key to continue.")
            read_key()
            return None

        index = max(0, min(index, len(files) - 1))
        clear()
        print(c("=" * 100, "94"))
        print(bold(cyan("RESUME SAVED SESSION".center(100))))
        print(c("=" * 100, "94"))
        print()
        print(bold("Controls:"), "TAB/DOWN/+ next   UP/- previous   ENTER resume   BACKSPACE delete selected   ESC cancel")
        print(dim("Newest sessions appear first."))
        print()

        for i, filename in enumerate(files):
            path = os.path.join(SESSIONS_DIR, filename)
            try:
                modified = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
                rows = max(0, len(load_session_csv(path)))
                detail = f"{rows} coins | modified {modified}"
            except Exception:
                detail = "unable to read details"
            line = f"{i + 1:>3}. {filename:<45} {detail}"
            print(reverse(line) if i == index else line)

        key = read_key()
        if key == KEY_ESC:
            return None
        if key in (KEY_TAB, KEY_DOWN, "+", "="):
            index = (index + 1) % len(files)
        elif key in (KEY_SHIFT_TAB, KEY_UP, "-", "_"):
            index = (index - 1) % len(files)
        elif key == KEY_ENTER:
            return files[index]
        elif key == KEY_BACKSPACE:
            filename = files[index]
            path = os.path.join(SESSIONS_DIR, filename)
            if confirm_delete_session(filename, path):
                try:
                    os.remove(path)
                    clear()
                    print(green(f"Deleted {filename}"))
                    print()
                    print("Press any key to continue.")
                    read_key()
                    index = max(0, index - 1)
                except Exception as exc:
                    clear()
                    print(red(f"Could not delete {filename}: {exc}"))
                    print()
                    print("Press any key to continue.")
                    read_key()




def choose_multiple_from_list(title, options, allow_all=True):
    """Numpad-first multi-select menu. Returns selected option strings, or None."""
    if not options:
        clear()
        print(bold(yellow("Nothing available to select.")))
        print()
        print("Press any key to return.")
        read_key()
        return None

    index = 0
    selected = set(range(len(options))) if allow_all else set()
    focus_area = "items"
    action_index = 0
    actions = ["Confirm", "Select all", "Select none", "Cancel"]

    while True:
        clear()
        print(c("=" * 110, "94"))
        print(bold(cyan(title.center(110))))
        print(c("=" * 110, "94"))
        print()
        print(bold("Controls:"), "TAB moves selection   + / - changes highlighted option   ENTER selects/toggles   BACKSPACE cancels")
        print(dim("Use ENTER on an item to check/uncheck it. TAB down to Confirm when ready."))
        print()

        for i, item in enumerate(options):
            check = "[x]" if i in selected else "[ ]"
            line = f"{check} {item}"
            is_active = focus_area == "items" and i == index
            print(reverse(line) if is_active else line)

        print()
        print(c("-" * 110, "94"))
        print(dim(f"Selected: {len(selected)} of {len(options)}"))
        print()
        rendered_actions = []
        for i, action in enumerate(actions):
            text = f" {action} "
            rendered_actions.append(reverse(text) if focus_area == "actions" and i == action_index else bold(text))
        print("   ".join(rendered_actions))
        print(dim("TAB switches between the item list and action row. + / - moves within the active area."))

        key = read_key()
        if key in (KEY_BACKSPACE, KEY_ESC):
            return None

        if key in (KEY_TAB, KEY_DOWN):
            if focus_area == "items":
                focus_area = "actions"
                action_index = 0
            else:
                focus_area = "items"
            continue
        if key in (KEY_SHIFT_TAB, KEY_UP):
            if focus_area == "actions":
                focus_area = "items"
            else:
                focus_area = "actions"
                action_index = len(actions) - 1
            continue

        if key in ("+", "="):
            if focus_area == "items":
                index = (index + 1) % len(options)
            else:
                action_index = (action_index + 1) % len(actions)
            continue
        if key in ("-", "_"):
            if focus_area == "items":
                index = (index - 1) % len(options)
            else:
                action_index = (action_index - 1) % len(actions)
            continue

        if key == KEY_ENTER:
            if focus_area == "items":
                if index in selected:
                    selected.remove(index)
                else:
                    selected.add(index)
                continue

            action = actions[action_index]
            if action == "Confirm":
                if not selected:
                    clear()
                    print(red("Select at least one item first."))
                    print("Press any key to continue.")
                    read_key()
                    focus_area = "items"
                    continue
                return [options[i] for i in range(len(options)) if i in selected]
            if action == "Select all":
                selected = set(range(len(options)))
            elif action == "Select none":
                selected = set()
            elif action == "Cancel":
                return None

def read_session_rows(filename):
    path = os.path.join(SESSIONS_DIR, filename)
    try:
        rows = load_session_csv(path)
        for row in rows:
            row.setdefault("source_file", filename)
        return rows
    except Exception:
        return []


def export_menu():
    ensure_sessions_dir()
    ensure_exports_dir()
    files = list_sessions()
    if not files:
        clear()
        print(bold(yellow("No saved session CSVs found to export.")))
        print()
        print("Press any key to return.")
        read_key()
        return

    session_options = []
    option_to_file = {}
    for filename in files:
        path = os.path.join(SESSIONS_DIR, filename)
        try:
            rows = len(load_session_csv(path))
            modified = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
            label = f"{filename}  ({rows} coins, modified {modified})"
        except Exception:
            label = f"{filename}  (unable to read details)"
        session_options.append(label)
        option_to_file[label] = filename

    picked_sessions = choose_multiple_from_list("EXPORT DATA - SELECT SESSIONS", session_options, allow_all=True)
    if not picked_sessions:
        return
    picked_files = [option_to_file[label] for label in picked_sessions]

    export_columns = CSV_HEADERS + ["source_file"]
    picked_columns = choose_multiple_from_list("EXPORT DATA - SELECT COLUMNS", export_columns, allow_all=True)
    if not picked_columns:
        return

    rows = []
    for filename in picked_files:
        rows.extend(read_session_rows(filename))

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_path = os.path.join(EXPORTS_DIR, f"{timestamp}_coin_sort_export.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=picked_columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in picked_columns})

    clear()
    print(c("=" * 100, "92"))
    print(bold(green("EXPORT COMPLETE".center(100))))
    print(c("=" * 100, "92"))
    print()
    print(f"Exported rows : {green(str(len(rows)))}")
    print(f"Sessions      : {green(str(len(picked_files)))}")
    print(f"Columns       : {green(str(len(picked_columns)))}")
    print()
    print(bold("Saved to:"))
    print(cyan(out_path))
    print()
    print("Press any key to return.")
    read_key()



def face_value_float(value):
    try:
        return float(normalize_decimal(value))
    except Exception:
        return 0.0


def money(value):
    return f"${value:,.2f}"


def denom_bucket_for_row(row):
    face = normalize_decimal(row.get("face_value", ""))
    denom = str(row.get("denomination", "")).lower()

    # Prefer the normalized numeric face value first so "25 cent" is not
    # accidentally counted as "5 cent" by substring matching.
    if face == "0.01":
        return "Pennies"
    if face == "0.05":
        return "Nickels"
    if face == "0.10":
        return "Dimes"
    if face == "0.25":
        return "Quarters"
    if face == "0.50":
        return "Half Dollars"
    if face == "1.00":
        return "Dollar Coins"

    if "penny" in denom or "pennies" in denom or re.search(r"\b1\s+cent\b", denom):
        return "Pennies"
    if "nickel" in denom or re.search(r"\b5\s+cent\b", denom):
        return "Nickels"
    if "dime" in denom or re.search(r"\b10\s+cent\b", denom):
        return "Dimes"
    if "quarter" in denom or re.search(r"\b25\s+cent\b", denom):
        return "Quarters"
    if "half dollar" in denom or re.search(r"\b50\s+cent\b", denom):
        return "Half Dollars"
    if re.search(r"\b1\s+dollar\b", denom):
        return "Dollar Coins"
    return "Other / Unknown"


def suspicious_year_rows_from_rows(rows):
    suspicious = []
    high = current_year()
    for i, coin in enumerate(rows):
        year = str(coin.get("year", "")).strip()
        reason = ""
        if not year_is_complete(year):
            reason = "not exactly 4 digits"
        else:
            y = int(year)
            if y < 1600 or y > high:
                reason = f"outside broad range 1600-{high}"
        if reason:
            suspicious.append((i, coin, reason))
    return suspicious




def parse_coin_timestamp(value):
    """Parse timestamps saved by the sorter. Returns None for blank/bad values."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def format_duration(seconds):
    seconds = int(max(0, round(seconds)))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def session_group_key(row):
    return str(row.get("source_file") or row.get("session_name") or "Current Session")


def calculate_time_analysis(rows, break_threshold_seconds=300):
    """Estimate active sorting time from saved coin timestamps.

    Time is calculated inside each session/file separately, then summed. This means
    a multi-day gap inside one session, or the gap between Mom/Dad sessions, is not
    counted as active sorting time when it exceeds the break threshold.
    """
    groups = {}
    for row in rows:
        ts = parse_coin_timestamp(row.get("timestamp", ""))
        if ts is None:
            continue
        groups.setdefault(session_group_key(row), []).append(ts)

    all_timestamps = []
    active_seconds = 0.0
    raw_session_span_seconds = 0.0
    ignored_break_seconds = 0.0
    longest_break_seconds = 0.0
    counted_gap_count = 0
    ignored_gap_count = 0

    for timestamps in groups.values():
        timestamps = sorted(timestamps)
        all_timestamps.extend(timestamps)
        if len(timestamps) >= 2:
            raw_session_span_seconds += (timestamps[-1] - timestamps[0]).total_seconds()
        for previous, current in zip(timestamps, timestamps[1:]):
            gap = max(0.0, (current - previous).total_seconds())
            if gap <= break_threshold_seconds:
                active_seconds += gap
                counted_gap_count += 1
            else:
                ignored_break_seconds += gap
                longest_break_seconds = max(longest_break_seconds, gap)
                ignored_gap_count += 1

    if all_timestamps:
        all_timestamps.sort()
        calendar_span_seconds = (all_timestamps[-1] - all_timestamps[0]).total_seconds() if len(all_timestamps) >= 2 else 0.0
    else:
        calendar_span_seconds = 0.0

    total_coins = len(rows)
    coins_per_hour = (total_coins / (active_seconds / 3600.0)) if active_seconds > 0 else 0.0
    seconds_per_coin = (active_seconds / total_coins) if total_coins > 0 and active_seconds > 0 else 0.0

    return {
        "sessions_with_timestamps": len(groups),
        "coins_with_timestamps": len(all_timestamps),
        "break_threshold_seconds": break_threshold_seconds,
        "calendar_span_seconds": calendar_span_seconds,
        "raw_session_span_seconds": raw_session_span_seconds,
        "active_seconds": active_seconds,
        "ignored_break_seconds": ignored_break_seconds,
        "longest_break_seconds": longest_break_seconds,
        "counted_gap_count": counted_gap_count,
        "ignored_gap_count": ignored_gap_count,
        "coins_per_hour": coins_per_hour,
        "seconds_per_coin": seconds_per_coin,
    }


def build_statistics_lines(title, rows, selected_files=None):
    """Build a cleaner, less repetitive statistics report."""
    selected_files = selected_files or []
    total = len(rows)
    today = datetime.now().date().isoformat()
    today_total = sum(1 for coin in rows if str(coin.get("timestamp", ""))[:10] == today)

    valid_years = [coin_year_int(coin) for coin in rows]
    valid_years = [year for year in valid_years if year is not None]

    reject_count = sum(1 for coin in rows if boolish(coin.get("reject", False)))
    keep_bulk_count = sum(1 for coin in rows if boolish(coin.get("keep_bulk", False)))

    new_collection_rows = [coin for coin in rows if boolish(coin.get("new_collection", False))]
    new_collection_count = len(new_collection_rows)
    collection_type_counts = Counter(coin_type_label(coin) for coin in new_collection_rows)
    unique_collection_type_count = len(collection_type_counts)

    reject_reason_counts = Counter(
        str(coin.get("reject_reason", "") or "No reason saved").strip()
        for coin in rows
        if boolish(coin.get("reject", False))
    )

    year_counts = Counter(valid_years)
    decade_counts = Counter(decade_label(year) for year in valid_years)
    mint_counts = Counter(str(coin.get("mint", "") or "Unknown") for coin in rows)
    session_type_counts = Counter(str(coin.get("session_type", "") or "Unknown") for coin in rows)
    country_counts = Counter(str(coin.get("country", "") or "Unknown") for coin in rows)
    denom_counts = Counter(str(coin.get("denomination", "") or "Unknown") for coin in rows)

    bucket_order = ["Pennies", "Nickels", "Dimes", "Quarters", "Half Dollars", "Dollar Coins", "Other / Unknown"]
    bucket_counts = Counter()
    bucket_values = Counter()
    total_value = 0.0
    for row in rows:
        bucket = denom_bucket_for_row(row)
        value = face_value_float(row.get("face_value", ""))
        bucket_counts[bucket] += 1
        bucket_values[bucket] += value
        total_value += value

    # Active sorting time ignores long gaps between coins/sessions, so reports
    # do not get distorted if you only sort on certain days of the week.
    time_stats = calculate_time_analysis(rows)

    def pct(part, whole):
        return (part / whole * 100.0) if whole else 0.0

    def every_label(event_count, unit_name):
        if not event_count:
            return f"No {unit_name.lower()} yet"
        coins_per = total / event_count if total else 0
        return f"1 every {coins_per:,.1f} coins"

    collection_find_rate = pct(new_collection_count, total)
    unique_type_rate = pct(unique_collection_type_count, total)

    lines = []
    lines.append("=" * 110)
    lines.append(title.center(110))
    lines.append("=" * 110)
    lines.append("")
    if selected_files:
        lines.append(f"Sessions included          : {len(selected_files)}")
        for filename in selected_files:
            lines.append(f"  - {filename}")
        lines.append("")

    lines.append("Session Summary")
    lines.append("---------------")
    lines.append(f"Total Coins Sorted         : {total:,}")
    lines.append(f"Sorted Today               : {today_total:,}")
    lines.append(f"Total Face Value           : {money(total_value)}")
    lines.append(f"Rejects                    : {reject_count:,}")
    lines.append(f"Kept for Bulk              : {keep_bulk_count:,}")
    lines.append(f"Collection Set-Asides      : {new_collection_count:,}")
    lines.append(f"Unique Collection Types    : {unique_collection_type_count:,}")
    lines.append("")

    lines.append("Collection Results")
    lines.append(f"  Collection set-asides    : {new_collection_count:,}  ({collection_find_rate:.2f}% of sorted coins)")
    lines.append(f"  Set-aside pace           : {every_label(new_collection_count, 'Collection Find')}")
    lines.append(f"  Unique collection types  : {unique_collection_type_count:,}  ({unique_type_rate:.2f}% of sorted coins)")
    lines.append(f"  Unique type pace         : {every_label(unique_collection_type_count, 'Unique Type')}")
    lines.append("")

    lines.append("Sorting Time")
    if time_stats["active_seconds"] > 0:
        lines.append(f"  Active sorting time      : {format_duration(time_stats['active_seconds'])}")
        lines.append(f"  Average time per coin    : {time_stats['seconds_per_coin']:.1f} seconds")
        lines.append(f"  Sorting pace             : {time_stats['coins_per_hour']:,.1f} coins/hour")
        lines.append(f"  Timestamped coins        : {time_stats['coins_with_timestamps']:,}")
        lines.append(f"  Timed sessions           : {time_stats['sessions_with_timestamps']:,}")
        lines.append(f"  Ignored long breaks      : {time_stats['ignored_gap_count']:,}")
    else:
        lines.append("  Active sorting time      : not enough timestamp gaps yet")
        lines.append("  Average time per coin    : not enough timestamp gaps yet")
        lines.append("  Sorting pace             : not enough timestamp gaps yet")
    lines.append("  Note                     : long gaps between sort days are ignored")
    lines.append("")

    lines.append("Denomination Totals")
    for bucket in bucket_order:
        lines.append(f"  {bucket:<18}: {bucket_counts[bucket]:>6} coins  {money(bucket_values[bucket])}")
    lines.append("  " + "-" * 48)
    lines.append(f"  {'TOTAL':<18}: {total:>6} coins  {money(total_value)}")
    lines.append("")

    if reject_reason_counts:
        lines.append("Reject Reasons")
        for reason, count in reject_reason_counts.most_common():
            reject_pct = (count / reject_count * 100) if reject_count else 0
            lines.append(f"  {reason:<28} {count:>5}  {reject_pct:>5.1f}%")
        lines.append("")

    if collection_type_counts:
        lines.append(f"Collection Set-Aside Types ({len(collection_type_counts)} Unique Types)")
        for label, count in collection_type_counts.most_common():
            lines.append(f"  {count:>4}x  {label}")
        lines.append("")

    if valid_years:
        oldest = min(valid_years)
        newest = max(valid_years)
        avg_year = round(sum(valid_years) / len(valid_years), 1)
        lines.append("Date Story")
        lines.append(f"  Oldest coin              : {oldest}")
        lines.append(f"  Newest coin              : {newest}")
        lines.append(f"  Average year             : {avg_year}")
        lines.append("")

        lines.append("Most Common Years")
        max_year_count = max(year_counts.values()) if year_counts else 0
        for year, count in year_counts.most_common(10):
            lines.append(f"  {year}: {count:>4}  {make_bar(count, max_year_count)}")
        lines.append("")

        lines.append("Most Common Decades")
        max_decade_count = max(decade_counts.values()) if decade_counts else 0
        for dec, count in decade_counts.most_common(10):
            lines.append(f"  {dec}: {count:>4}  {make_bar(count, max_decade_count)}")
        lines.append("")

    lines.append("Mint Mark Breakdown")
    max_mint_count = max(mint_counts.values()) if mint_counts else 0
    for mint, count in mint_counts.most_common():
        mint_pct = (count / total * 100) if total else 0
        lines.append(f"  {mint:>8}: {count:>4}  {mint_pct:>5.1f}%  {make_bar(count, max_mint_count)}")
    lines.append("")

    if len(country_counts) > 1 or (country_counts and next(iter(country_counts)) not in ("Unknown", "")):
        lines.append("Country Breakdown")
        for country, count in country_counts.most_common(10):
            country_pct = (count / total * 100) if total else 0
            lines.append(f"  {country:<28} {count:>5}  {country_pct:>5.1f}%")
        lines.append("")

    lines.append("Denomination Breakdown")
    for denom, count in denom_counts.most_common(12):
        denom_pct = (count / total * 100) if total else 0
        lines.append(f"  {denom:<36} {count:>5}  {denom_pct:>5.1f}%")
    lines.append("")

    if len(session_type_counts) > 1 or (session_type_counts and next(iter(session_type_counts)) not in ("Unknown", "")):
        lines.append("Session Type Breakdown")
        for session_type, count in session_type_counts.most_common():
            type_pct = (count / total * 100) if total else 0
            lines.append(f"  {session_type:<28} {count:>5}  {type_pct:>5.1f}%")
        lines.append("")

    return lines

def export_statistics_lines(lines, prefix="coin_sort_statistics"):
    ensure_exports_dir()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_path = os.path.join(EXPORTS_DIR, f"{timestamp}_{safe_filename(prefix)}.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).replace("\033[", ""))
        f.write("\n")
    return out_path


def show_statistics_page(title, rows, selected_files=None, return_hint="ENTER selects the highlighted action."):
    action_index = 0
    actions = ["Back", "Export report"]
    while True:
        lines = build_statistics_lines(title, rows, selected_files)
        clear()
        for line in lines:
            if (
                line in (
                    "Session Summary", "Collection Results", "Sorting Time", "Denomination Totals", "Reject Reasons", "Date Story",
                    "Most Common Years", "Most Common Decades", "Mint Mark Breakdown", "Country Breakdown",
                    "Denomination Breakdown", "Session Type Breakdown"
                )
                or line.startswith("Collection Set-Aside Types")
                or line.startswith("Unique Collection Types Found")
            ):
                print(bold(yellow(line)))
            elif line.startswith("="):
                print(c(line, "94"))
            elif "TOTAL" in line and "coins" in line:
                print(bold(green(line)))
            else:
                print(line)
        print(c("-" * 110, "94"))
        rendered_actions = []
        for i, action in enumerate(actions):
            text = f" {action} "
            rendered_actions.append(reverse(text) if i == action_index else bold(text))
        print("   ".join(rendered_actions))
        print(dim(f"TAB/+/- changes the highlighted action. ENTER selects. BACKSPACE/ESC returns. {return_hint}"))

        key = read_key()
        if key in (KEY_BACKSPACE, KEY_ESC):
            return
        if key in (KEY_TAB, KEY_DOWN, "+", "="):
            action_index = (action_index + 1) % len(actions)
            continue
        if key in (KEY_SHIFT_TAB, KEY_UP, "-", "_"):
            action_index = (action_index - 1) % len(actions)
            continue
        if key == KEY_ENTER:
            action = actions[action_index]
            if action == "Back":
                return
            if action == "Export report":
                out_path = export_statistics_lines(lines, title.lower().replace(" ", "_"))
                clear()
                print(c("=" * 100, "92"))
                print(bold(green("STATISTICS EXPORT COMPLETE".center(100))))
                print(c("=" * 100, "92"))
                print()
                print(bold("Saved to:"))
                print(cyan(out_path))
                print()
                print("Press any key to return to statistics.")
                read_key()
                continue

def choose_session_files_for_statistics():
    ensure_sessions_dir()
    files = list_sessions()
    if not files:
        clear()
        print(bold(yellow("No saved session CSVs found for statistics.")))
        print()
        print("Press any key to return.")
        read_key()
        return None

    session_options = []
    option_to_file = {}
    for filename in files:
        path = os.path.join(SESSIONS_DIR, filename)
        try:
            rows = len(load_session_csv(path))
            modified = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
            label = f"{filename}  ({rows} coins, modified {modified})"
        except Exception:
            label = f"{filename}  (unable to read details)"
        session_options.append(label)
        option_to_file[label] = filename

    picked_sessions = choose_multiple_from_list("STATISTICS - SELECT SESSIONS", session_options, allow_all=True)
    if not picked_sessions:
        return None
    return [option_to_file[label] for label in picked_sessions]


def home_statistics_menu():
    picked_files = choose_session_files_for_statistics()
    if not picked_files:
        return

    rows = []
    for filename in picked_files:
        rows.extend(read_session_rows(filename))

    title = "COMBINED SESSION STATISTICS" if len(picked_files) > 1 else "SESSION STATISTICS"
    show_statistics_page(title, rows, picked_files, "ENTER/BACKSPACE/ESC returns to home menu.")


def resume_session(numista_countries, denoms_by_country):
    selected_file = choose_session_file_for_resume()
    if not selected_file:
        return None

    path = os.path.join(SESSIONS_DIR, selected_file)
    log = load_session_csv(path)

    if log:
        first = log[0]
        session_name = first.get("session_name", selected_file.replace(".csv", ""))
        session_type = first.get("session_type", "Unknown")
        country = first.get("country", "")
        denomination = first.get("denomination", "Unknown")
        currency = first.get("currency", "")
        face_value = first.get("face_value", "")
        if not country or not face_value:
            coin_choice = choose_country_and_denom(numista_countries, denoms_by_country, country or None)
            if not coin_choice:
                return None
            country = coin_choice["country"]
            denomination = coin_choice["denomination"]
            currency = coin_choice["currency"]
            face_value = coin_choice["face_value"]
    else:
        session_name = selected_file.replace(".csv", "")
        session_type = "Unknown"
        coin_choice = choose_country_and_denom(numista_countries, denoms_by_country)
        if not coin_choice:
            return None
        country = coin_choice["country"]
        denomination = coin_choice["denomination"]
        currency = coin_choice["currency"]
        face_value = coin_choice["face_value"]

    return {"session_name": session_name, "session_type": session_type, "country": country, "denomination": denomination, "currency": currency, "face_value": face_value, "path": path, "log": log}

def session_menu():
    ensure_sessions_dir()
    ensure_numista_dir()
    numista_index, numista_files, numista_countries, denoms_by_country = load_numista_index()
    while True:
        choice = choose_from_list("Coin Sorter Sessions", ["Start new session", "Resume session", "Statistics", "Export Data", "Settings", "Quit"])
        if choice == "Start new session":
            session = new_session(numista_countries, denoms_by_country)
            if session:
                session["numista_index"] = numista_index
                session["numista_csv_count"] = len(numista_files)
                session["numista_coin_count"] = len(numista_index)
                session["numista_countries"] = numista_countries
                session["denoms_by_country"] = denoms_by_country
                return session
        elif choice == "Resume session":
            session = resume_session(numista_countries, denoms_by_country)
            if session:
                session["numista_index"] = numista_index
                session["numista_csv_count"] = len(numista_files)
                session["numista_coin_count"] = len(numista_index)
                session["numista_countries"] = numista_countries
                session["denoms_by_country"] = denoms_by_country
                return session
        elif choice == "Statistics":
            home_statistics_menu()
        elif choice == "Export Data":
            export_menu()
        elif choice == "Settings":
            settings_menu()
        elif choice == "Quit" or choice is None:
            return None


def prompt_reject_reason(current_reason=""):
    """Ask why a coin was rejected. Returns a reason string, or None if cancelled."""
    options = list(REJECT_REASONS)
    if current_reason and current_reason not in options:
        options.insert(0, f"Keep current reason: {current_reason}")

    choice = choose_from_list("Why was this coin rejected?", options)
    if not choice:
        return None
    if choice.startswith("Keep current reason:"):
        return current_reason
    if choice == "Other / custom reason":
        custom = text_input("Type the custom reject reason:", current_reason if current_reason not in REJECT_REASONS else "")
        return custom.strip() if custom else None
    return choice


def coin_type_key(row):
    """Unique type key for collection set-asides: country + value + year + mint."""
    return (
        str(row.get("country", "")).strip(),
        normalize_decimal(row.get("face_value", "")),
        str(row.get("denomination", "")).strip(),
        str(row.get("year", "")).strip(),
        normalize_mint(row.get("mint", "")),
    )


def coin_type_label(row):
    year = str(row.get("year", "")).strip() or "????"
    mint = str(row.get("mint", "")).strip() or "?"
    denom = str(row.get("denomination", "")).strip() or "Unknown denomination"
    country = str(row.get("country", "")).strip() or "Unknown country"
    return f"{year}-{mint} | {denom} | {country}"


def make_coin(session_name, session_type, country, denom, currency, face_value, year, mint_index, notes, reject, reject_reason, keep_bulk, numista_found="", possible_missing_collection="", new_collection=False):
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "session_name": session_name,
        "session_type": session_type,
        "country": country,
        "denomination": denom,
        "currency": currency,
        "face_value": face_value,
        "year": year,
        "mint": MINTS[mint_index],
        "notes": notes,
        "reject": str(bool(reject)),
        "reject_reason": reject_reason if reject else "",
        "keep_bulk": str(bool(keep_bulk)),
        "numista_found": str(numista_found),
        "possible_missing_collection": str(possible_missing_collection),
        "new_collection": str(boolish(new_collection) if isinstance(new_collection, str) else bool(new_collection)),
    }


def reset_coin():
    return "", 0, "", False, "", False, "year"


def boolish(value):
    return str(value).lower() in ["true", "1", "yes"]


def current_year():
    return datetime.now().year


def get_year_range_for_session(session):
    """Return a practical valid range for the active coin type.

    This is intentionally a sanity check, not a rare-coin authority. It catches
    obvious slips like 1510, 2220, or 2260 while still allowing older world coins.
    """
    country = str(session.get("country", "")).lower()
    denom = str(session.get("denomination", "")).lower()

    if "united states" in country and ("1 cent" in denom or "0.01" in denom):
        return 1793, current_year()
    if "united states" in country:
        return 1792, current_year()
    return 1600, current_year()


def year_is_complete(year):
    return len(str(year).strip()) == 4 and str(year).strip().isdigit()


def year_warning(session, year):
    if not year:
        return "Enter a 4-digit year before saving."
    if not str(year).isdigit():
        return "Year must contain numbers only."
    if len(str(year)) < 4:
        return f"Need {4 - len(str(year))} more digit(s) before this coin can save."
    if len(str(year)) > 4:
        return "Year must be exactly 4 digits."
    low, high = get_year_range_for_session(session)
    y = int(year)
    if y < low or y > high:
        suggestions = suggest_year_corrections(year, session.get("log", []), session)
        if suggestions:
            return f"Suspicious year. Did you mean {', '.join(str(x) for x in suggestions[:3])}?"
        return f"Suspicious year. Expected roughly {low}-{high}."
    return ""


def plausible_year_for_session(year, session):
    if not isinstance(year, int):
        return False
    low, high = get_year_range_for_session(session)
    return low <= year <= high


def suggest_year_corrections(year_text, log, session):
    """Suggest likely corrections for typo years like 2220 -> 2020.

    Ranking favors years already seen in the session, then dates close to the
    session's average year, then newer/simple substitutions.
    """
    text = str(year_text).strip()
    if len(text) != 4 or not text.isdigit():
        return []

    existing_years = [coin_year_int(coin) for coin in log]
    existing_years = [y for y in existing_years if y is not None and plausible_year_for_session(y, session)]
    counts = Counter(existing_years)
    center = round(sum(existing_years) / len(existing_years)) if existing_years else 1980

    candidates = set()

    # One-digit substitutions catch common fat-finger mistakes: 2220 -> 2020, 1510 -> 1910.
    for i in range(4):
        for d in "0123456789":
            if d == text[i]:
                continue
            candidate = int(text[:i] + d + text[i + 1:])
            if plausible_year_for_session(candidate, session):
                candidates.add(candidate)

    # Two-digit substitutions catch messier slips like 2260 -> 2020.
    # This is still safe because ranking favors years already seen in your session.
    for i in range(4):
        for j in range(i + 1, 4):
            for d1 in "0123456789":
                for d2 in "0123456789":
                    chars = list(text)
                    if chars[i] == d1 and chars[j] == d2:
                        continue
                    chars[i] = d1
                    chars[j] = d2
                    if chars[0] == "0":
                        continue
                    candidate = int("".join(chars))
                    if plausible_year_for_session(candidate, session):
                        candidates.add(candidate)

    # If someone typed a doubled first two digits for a 20xx coin, this catches it directly.
    if text.startswith("22"):
        candidate = int("20" + text[2:])
        if plausible_year_for_session(candidate, session):
            candidates.add(candidate)

    # Common old-cent slips where the second digit is wrong: 1510 -> 1910.
    if text[0] == "1":
        for second in "789":
            candidate = int(text[0] + second + text[2:])
            if plausible_year_for_session(candidate, session):
                candidates.add(candidate)

    def digit_distance(y):
        return sum(a != b for a, b in zip(text, str(y).zfill(4)))

    def score(y):
        # Lower score is better. Prefer smaller typo corrections, then dates already seen,
        # then dates near the session's average year.
        return (digit_distance(y), 0 if counts[y] else 1, -counts[y], abs(y - center), abs(y - int(text)))

    return sorted(candidates, key=score)[:5]


def find_suspicious_year_rows(session):
    rows = []
    for i, coin in enumerate(session.get("log", [])):
        year = str(coin.get("year", "")).strip()
        reason = ""
        if not year_is_complete(year):
            reason = "not exactly 4 digits"
        else:
            y = int(year)
            low, high = get_year_range_for_session(session)
            if y < low or y > high:
                reason = f"outside expected range {low}-{high}"
        if reason:
            rows.append((i, coin, reason, suggest_year_corrections(year, session.get("log", []), session)))
    return rows


def next_focus(focus, direction=1):
    i = FOCUS_ORDER.index(focus)
    return FOCUS_ORDER[(i + direction) % len(FOCUS_ORDER)]


def save_current_coin(session, year, mint_index, notes, reject, reject_reason, keep_bulk, editing_index, numista_index=None):
    if not (len(year) == 4 and year.isdigit()):
        return False, editing_index

    mint_name = MINTS[mint_index]
    numista_found = ""
    possible_missing = ""
    new_collection = False

    if numista_index is not None:
        found = coin_exists_in_numista(numista_index, session, year, mint_name)
        numista_found = str(found)
        possible_missing = str(not found)
        if not found:
            keep_entry = prompt_missing_numista_coin(session, year, mint_name)
            if not keep_entry:
                return False, editing_index
            # Missing from Numista and accepted: treat as a separate New Collection bin,
            # not reject and not normal keep/bulk. The warning intentionally appears
            # every time this year/mint/value is not found so duplicates can be compared.
            reject = False
            reject_reason = ""
            keep_bulk = False
            new_collection = True

    if reject and not str(reject_reason).strip():
        reject_reason = prompt_reject_reason()
        if not reject_reason:
            return False, editing_index

    coin = make_coin(
        session["session_name"], session["session_type"], session.get("country", ""), session["denomination"], session.get("currency", ""), session.get("face_value", ""),
        year, mint_index, notes, reject, reject_reason, keep_bulk, numista_found, possible_missing, new_collection
    )

    if editing_index is not None:
        session["log"][editing_index] = coin
        editing_index = None
    else:
        session["log"].append(coin)

    write_session_csv(session["path"], session["log"])
    return True, editing_index



def session_counts(log):
    """Return (total_count, today_count) for the active session CSV log."""
    today = datetime.now().date().isoformat()
    total = len(log)
    today_count = 0
    for coin in log:
        timestamp = str(coin.get("timestamp", ""))
        if timestamp[:10] == today:
            today_count += 1
    return total, today_count

def draw(session, year, mint_index, notes, reject, reject_reason, keep_bulk, selected_index, focus, editing_index):
    clear()
    log = session["log"]

    if BIG_UI:
        print(c("=" * 110, "94"))
        print(bold(c(" ██████╗ ██████╗ ██╗███╗   ██╗     ███████╗ ██████╗ ██████╗ ████████╗ ".center(110), "96")))
        print(bold(c("██╔════╝██╔═══██╗██║████╗  ██║     ██╔════╝██╔═══██╗██╔══██╗╚══██╔══╝ ".center(110), "96")))
        print(bold(c("██║     ██║   ██║██║██╔██╗ ██║     ███████╗██║   ██║██████╔╝   ██║    ".center(110), "96")))
        print(bold(c("╚██████╗╚██████╔╝██║██║ ╚████║     ███████║╚██████╔╝██║  ██║   ██║    ".center(110), "96")))
        print(c("=" * 110, "94"))
    else:
        print(bold(cyan("COIN SORTER")))

    print(f"{bold('Session:')} {session['session_name']}    {bold('Type:')} {session['session_type']}")
    print(f"{bold('Country:')} {session.get('country', 'Unknown')}    {bold('Denomination:')} {session['denomination']}")
    print(f"{bold('File:')} {session['path']}")
    if session.get("numista_csv_count", 0):
        print(f"{bold('Numista CSVs:')} {session.get('numista_csv_count')} loaded from {NUMISTA_DIR} | {session.get('numista_coin_count', 0)} owned US coin entries indexed")
    else:
        print(yellow(f"Numista CSVs: none loaded from {NUMISTA_DIR}"))

    total_sorted, today_sorted = session_counts(log)
    print(f"{bold('Sorted in this CSV:')} {green(str(total_sorted))} total    {bold('Today:')} {green(str(today_sorted))}")
    print()
    print(cyan("Flow:"), "Year → Mint → ENTER saves/adds coin  |  TAB moves selection  |  + / - changes selected option")
    print(cyan("Controls:"), f"TAB = move   ENTER = select/save   + / - = change mint/options   {key_display(HOTKEYS['reject'])} = REJECT   {key_display(HOTKEYS['keep_bulk'])} = KEEP/BULK")
    print(dim("Invalid Check catches weird years like 1510, 2220, or 2260 and suggests likely fixes."))
    print(dim("TAB only changes which field/action is selected. It does not change mint or toggle anything."))
    print(c("-" * 110, "94"))

    status = f"EDITING COIN #{editing_index + 1}" if editing_index is not None else "NEW COIN"
    print(bold(yellow(status)))
    print()

    def box_line(label_text, value_text, name, hint=""):
        left = reverse(f" {label_text} ") if focus == name else bold(f" {label_text} ")
        print(f"{left:<38} {value_text} {dim(hint)}")
        if BIG_UI:
            print()

    warning = year_warning(session, year)
    year_value = bold(cyan(year or "____"))
    if warning and year:
        year_value += "  " + red("⚠")
    mint_value = bold(cyan(MINTS[mint_index]))
    notes_value = bold(cyan(notes)) if notes else dim("(blank)")
    reject_value = red("YES") if reject else dim("no")
    if reject and reject_reason:
        reject_value += dim(f" ({reject_reason})")
    keep_value = green("YES") if keep_bulk else dim("no")

    print(bold(cyan("  ┌──────────────────────────────────────────────────────────────┐")))
    print(bold(cyan("  │                    CURRENT COIN ENTRY                         │")))
    print(bold(cyan("  └──────────────────────────────────────────────────────────────┘")))
    print()
    box_line("Year", year_value, "year", "must be 4 digits to save")
    if warning:
        print("  " + yellow(warning))
        print()
    box_line("Mint", mint_value, "mint", "+ / - changes mint; ENTER saves")
    box_line("Save Coin", green("manual save if you tab here"), "save", "")
    box_line("Notes", notes_value, "notes", "optional; TAB here only if needed")

    print(f"{bold('  Reject')}        {reject_value}      {dim('hotkey only; asks reason when turned on')}")
    print(f"{bold('  Keep/Bulk')}  {keep_value}      {dim('hotkey only: *')}")
    print()
    print(f"{(reverse(' Recent/Edit ') if focus == 'recent' else bold(' Recent/Edit '))} {dim('ENTER opens full previous-coin edit list')}")
    print(f"{(reverse(' Change Country/Denom ') if focus == 'change_denom' else bold(' Change Country/Denom '))} {dim('ENTER changes active sorting selection')}")
    print(f"{(reverse(' Statistics ') if focus == 'statistics' else bold(' Statistics '))} {dim('ENTER opens session statistics page')}")
    print(f"{(reverse(' Invalid Check ') if focus == 'invalid_check' else bold(' Invalid Check '))} {dim('ENTER reviews suspicious saved years')}")
    print(f"{(reverse(' Save + Quit ') if focus == 'quit' else bold(' Save + Quit '))} {dim('ENTER opens confirmation')}")

    print()
    print(c("-" * 110, "94"))
    print(bold("Last sorted coins:"))
    recent = log[-5:]
    start_index = len(log) - len(recent)
    if not recent:
        print(dim("  No coins saved yet."))
    for i, coin in enumerate(recent):
        global_index = start_index + i
        marker = reverse("> ") if global_index == selected_index else "  "
        flags = []
        if boolish(coin.get("reject", False)):
            reason = coin.get("reject_reason", "")
            flags.append(red("REJECT" + (f": {reason}" if reason else "")))
        if boolish(coin.get("keep_bulk", False)):
            flags.append(green("KEEP/BULK"))
        if boolish(coin.get("new_collection", False)):
            flags.append(yellow("NEW COLLECTION"))
        flag_text = f" [{' | '.join(flags)}]" if flags else ""
        print(f"{marker}{global_index + 1}. {coin.get('year', '')}-{coin.get('mint', '')} | {coin.get('denomination', '')} | {coin.get('notes', '')}{flag_text}")

    print()
    print(c("-" * 110, "94"))
    print(bold("Current selection help:"))
    if focus == "year":
        print("Type the year. You can TAB to menus anytime, but the coin will not save unless the year is exactly 4 digits.")
    elif focus == "mint":
        print("Use + or - to choose the mint. ENTER saves/adds the coin. TAB moves down if you need Notes first.")
    elif focus == "save":
        print("Press ENTER to save this coin and start the next coin. This is the manual save step if you tabbed past Mint.")
    elif focus == "notes":
        print("Type notes if needed. ENTER saves this coin and starts the next coin.")
    elif focus == "recent":
        print("Press ENTER to open the full previous-coin edit list. TAB only moves selection.")
    elif focus == "change_denom":
        print("Press ENTER to choose a different country and denomination from your Numista CSV.")
    elif focus == "statistics":
        print("Press ENTER to open a separate statistics page for this session CSV.")
    elif focus == "invalid_check":
        print("Press ENTER to review saved coins with suspicious years and suggested corrections.")
    elif focus == "quit":
        print("ENTER opens Save + Quit confirmation.")



def change_current_country_denom(session):
    choice = choose_country_and_denom(
        session.get("numista_countries", []),
        session.get("denoms_by_country", {}),
        session.get("country"),
    )
    if not choice:
        return False
    session["country"] = choice["country"]
    session["denomination"] = choice["denomination"]
    session["currency"] = choice["currency"]
    session["face_value"] = choice["face_value"]
    return True


def previous_coins_menu(session, start_index=None):
    """Full saved-coin picker. Returns the selected log index, or None.

    This menu keeps the highlighted coin inside a fixed on-screen viewport.
    When you move up or down through a long session, the list scrolls with
    the cursor instead of letting the selected row disappear above/below the
    terminal window.
    """
    log = session["log"]
    if not log:
        clear()
        print(bold(yellow("No saved coins yet.")))
        print()
        print("Press BACKSPACE or ENTER to return.")
        while True:
            key = read_key()
            if key in (KEY_BACKSPACE, KEY_ENTER, KEY_ESC):
                return None

    if start_index is None:
        index = len(log) - 1
    else:
        index = max(0, min(int(start_index), len(log) - 1))
    top_index = index

    def format_previous_coin_line(i, coin):
        flags = []
        if boolish(coin.get("reject", False)):
            reason = coin.get("reject_reason", "")
            flags.append(red("REJECT" + (f": {reason}" if reason else "")))
        if boolish(coin.get("keep_bulk", False)):
            flags.append(green("KEEP/BULK"))
        if boolish(coin.get("new_collection", False)):
            flags.append(yellow("NEW COLLECTION"))
        flag_text = f" [{' | '.join(flags)}]" if flags else ""
        return (
            f"{i + 1:>4}. {coin.get('year', '')}-{coin.get('mint', '')} | "
            f"{coin.get('denomination', '')} | {coin.get('notes', '')}{flag_text}"
        )

    while True:
        terminal_rows = shutil.get_terminal_size((110, 30)).lines
        # Header/footer take roughly 11 rows. Keep at least 5 coins visible.
        visible_count = max(5, terminal_rows - 11)
        visible_count = min(visible_count, len(log))

        # Keep the cursor inside the visible window, scrolling the window as needed.
        if index < top_index:
            top_index = index
        elif index >= top_index + visible_count:
            top_index = index - visible_count + 1
        top_index = max(0, min(top_index, max(0, len(log) - visible_count)))
        bottom_index = min(len(log), top_index + visible_count)

        clear()
        print(c("=" * 110, "94"))
        print(bold(cyan("EDIT PREVIOUS COINS".center(110))))
        print(c("=" * 110, "94"))
        print()
        print(bold("Controls:"), "TAB/+ = newer/down   SHIFT+TAB/- = older/up   ENTER = edit selected   BACKSPACE = back")
        print(dim("The highlighted row stays on screen; the list scrolls as you move through older/newer coins."))
        print(dim(f"Showing {top_index + 1}-{bottom_index} of {len(log)} saved coins."))
        print()

        if top_index > 0:
            print(dim(f"  ... {top_index} older coin(s) above ..."))

        for i in range(top_index, bottom_index):
            line = format_previous_coin_line(i, log[i])
            print(reverse(line) if i == index else line)

        if bottom_index < len(log):
            print(dim(f"  ... {len(log) - bottom_index} newer coin(s) below ..."))

        key = read_key()
        if key == KEY_BACKSPACE or key == KEY_ESC:
            return None
        if key in ("+", "=", KEY_TAB, KEY_DOWN):
            index = min(len(log) - 1, index + 1)
        elif key in ("-", "_", KEY_SHIFT_TAB, KEY_UP):
            index = max(0, index - 1)
        elif key == KEY_ENTER:
            return index


def make_bar(count, max_count, width=30):
    if max_count <= 0:
        return ""
    filled = max(1, int((count / max_count) * width))
    return "█" * filled


def coin_year_int(coin):
    year = str(coin.get("year", "")).strip()
    if year.isdigit() and len(year) == 4:
        return int(year)
    return None


def decade_label(year):
    return f"{(year // 10) * 10}s"


def statistics_menu(session):
    """Statistics page for the active session CSV, using the same fields as home statistics."""
    selected_file = os.path.basename(session.get("path", "current_session.csv"))
    rows = list(session.get("log", []))
    for row in rows:
        row.setdefault("source_file", selected_file)
    show_statistics_page("SESSION STATISTICS", rows, [selected_file], "ENTER/BACKSPACE/ESC returns to coin entry.")



def apply_year_correction(session, row_index, new_year):
    session["log"][row_index]["year"] = str(new_year)
    session["log"][row_index]["timestamp"] = datetime.now().isoformat(timespec="seconds")
    write_session_csv(session["path"], session["log"])


def invalid_year_check_menu(session):
    """Separate safe review page for weird saved years.

    Returns the selected log index to edit, or None to go back.
    It never auto-changes a year from this page. You must choose an item,
    press ENTER to load it into the normal editor, then save it there.
    After the saved year is valid, it naturally disappears from this list.
    """
    index = 0
    while True:
        suspicious = find_suspicious_year_rows(session)
        clear()
        print(c("=" * 110, "91" if suspicious else "92"))
        print(bold((red if suspicious else green)("INVALID YEAR CHECK".center(110))))
        print(c("=" * 110, "91" if suspicious else "92"))
        print()
        print(f"{bold('Session:')} {session['session_name']}    {bold('CSV:')} {session['path']}")
        print()

        if not suspicious:
            print(green(bold("No suspicious saved years found.")))
            print(dim("This checks for non-4-digit years and dates outside the expected range for the active coin type."))
            print()
            print(dim("ENTER/BACKSPACE/ESC returns to coin entry."))
            key = read_key()
            if key in (KEY_ENTER, KEY_BACKSPACE, KEY_ESC):
                return None
            continue

        index = max(0, min(index, len(suspicious) - 1))
        print(bold("Controls:"), "TAB/+ next   SHIFT+TAB/- previous   ENTER edit selected   BACKSPACE return")
        print(dim("This page is review-only. It will not auto-apply a suggested year."))
        print(dim("Edit the selected coin on the normal entry screen, then save it. Once valid, it leaves this list."))
        print()

        for pos, (row_index, coin, reason, suggestions) in enumerate(suspicious):
            year = str(coin.get("year", ""))
            mint = str(coin.get("mint", ""))
            suggestion_text = ", ".join(str(x) for x in suggestions[:3]) if suggestions else "no obvious suggestion"
            line = f"{row_index + 1:>4}. {year}-{mint:<7} | {reason:<28} | suggested: {suggestion_text}"
            print(reverse(line) if pos == index else line)

        row_index, coin, reason, suggestions = suspicious[index]
        print()
        print(c("-" * 110, "91"))
        print(bold("Selected coin:"), f"#{row_index + 1}  {coin.get('year', '')}-{coin.get('mint', '')}  {coin.get('denomination', '')}")
        print(bold("Reason:"), red(reason))
        if suggestions:
            print(bold("Possible fixes:"), green(", ".join(str(x) for x in suggestions[:5])))
            print(dim("These are suggestions only. Press ENTER to edit the coin yourself."))
        else:
            print(yellow("No automatic correction looked safe. Press ENTER to edit it manually."))
        print()
        print(dim("BACKSPACE/ESC returns to coin entry."))

        key = read_key()
        if key in (KEY_BACKSPACE, KEY_ESC):
            return None
        if key in ("+", "=", KEY_TAB, KEY_DOWN):
            index = (index + 1) % len(suspicious)
        elif key in ("-", "_", KEY_SHIFT_TAB, KEY_UP):
            index = (index - 1) % len(suspicious)
        elif key == KEY_ENTER:
            return row_index


def confirm_save_quit(session):
    while True:
        clear()
        print(c("=" * 90, "94"))
        print(bold(yellow("SAVE + QUIT?".center(90))))
        print(c("=" * 90, "94"))
        print()
        print(bold("Your CSV will be saved here:"))
        print(cyan(session["path"]))
        print()
        print(bold("Press ENTER to save and quit."))
        print(bold("Press BACKSPACE to cancel and return."))
        print()
        print(dim("ESC also cancels."))
        key = read_key()
        if key == KEY_ENTER:
            write_session_csv(session["path"], session["log"])
            return True
        if key in (KEY_BACKSPACE, KEY_ESC):
            return False

def sorting_loop(session):
    numista_index = session.get("numista_index")
    if numista_index is None:
        numista_index, numista_files, numista_countries, denoms_by_country = load_numista_index()
        session["numista_index"] = numista_index
        session["numista_csv_count"] = len(numista_files)
        session["numista_coin_count"] = len(numista_index)
        session["numista_countries"] = numista_countries
        session["denoms_by_country"] = denoms_by_country
    year, mint_index, notes, reject, reject_reason, keep_bulk, focus = reset_coin()
    selected_index = -1
    editing_index = None
    return_to_recent_after_edit = False

    def load_index_for_edit(index, return_to_recent=False):
        nonlocal year, mint_index, notes, reject, reject_reason, keep_bulk, editing_index, focus, selected_index, return_to_recent_after_edit
        if index is None or not (0 <= index < len(session["log"])):
            return
        selected_index = index
        coin = session["log"][index]
        year = coin.get("year", "")
        notes = coin.get("notes", "")
        mint_value = coin.get("mint", "P")
        mint_index = MINTS.index(mint_value) if mint_value in MINTS else 0
        reject = boolish(coin.get("reject", False))
        reject_reason = coin.get("reject_reason", "")
        keep_bulk = boolish(coin.get("keep_bulk", False))
        editing_index = index
        return_to_recent_after_edit = bool(return_to_recent)
        focus = "year"

    def load_selected_for_edit():
        if selected_index == -1:
            return
        load_index_for_edit(selected_index, return_to_recent=True)

    def finish_save():
        nonlocal year, mint_index, notes, reject, reject_reason, keep_bulk, focus, editing_index, selected_index, return_to_recent_after_edit
        was_editing_index = editing_index
        should_return_to_recent = return_to_recent_after_edit and was_editing_index is not None
        saved, editing_index = save_current_coin(session, year, mint_index, notes, reject, reject_reason, keep_bulk, editing_index, numista_index)
        if saved:
            year, mint_index, notes, reject, reject_reason, keep_bulk, focus = reset_coin()
            if should_return_to_recent:
                selected_index = max(0, min(was_editing_index, len(session["log"]) - 1)) if session["log"] else -1
                return_to_recent_after_edit = False
                chosen = previous_coins_menu(session, selected_index if selected_index != -1 else None)
                if chosen is not None:
                    load_index_for_edit(chosen, return_to_recent=True)
                else:
                    focus = "year"
            else:
                selected_index = -1
                return_to_recent_after_edit = False

    def move_focus(direction):
        nonlocal focus
        focus = next_focus(focus, direction)

    while True:
        draw(session, year, mint_index, notes, reject, reject_reason, keep_bulk, selected_index, focus, editing_index)
        key = read_key()

        if hotkey_matches(key, "save_quit"):
            if confirm_save_quit(session):
                break
            continue


        # Hotkey-only bin flags. These are never TAB/ENTER selectable.
        if hotkey_matches(key, "reject"):
            if reject:
                reject = False
                reject_reason = ""
            else:
                reason = prompt_reject_reason(reject_reason)
                if reason:
                    reject = True
                    reject_reason = reason
                    keep_bulk = False
            continue
        if hotkey_matches(key, "keep_bulk"):
            keep_bulk = not keep_bulk
            if keep_bulk:
                reject = False
                reject_reason = ""
            continue

        # Mint changes only with assigned hotkeys. TAB/ENTER never changes the mint value.
        if hotkey_matches(key, "mint_next"):
            mint_index = (mint_index + 1) % len(MINTS)
            focus = "mint"
            continue
        if hotkey_matches(key, "mint_previous"):
            mint_index = (mint_index - 1) % len(MINTS)
            focus = "mint"
            continue

        # TAB changes the selected area only. It never opens a menu, saves, toggles, or changes an option.
        if key == KEY_TAB:
            move_focus(1)
            continue
        if key == KEY_SHIFT_TAB:
            move_focus(-1)
            continue

        # Optional arrow controls.
        if key == KEY_UP:
            if focus == "recent" and session["log"]:
                selected_index = len(session["log"]) - 1 if selected_index == -1 else max(0, selected_index - 1)
            else:
                move_focus(-1)
            continue
        if key == KEY_DOWN:
            if focus == "recent" and session["log"]:
                selected_index = len(session["log"]) - 1 if selected_index == -1 else min(len(session["log"]) - 1, selected_index + 1)
            else:
                move_focus(1)
            continue
        if key == KEY_LEFT:
            move_focus(-1)
            continue
        if key == KEY_RIGHT:
            if focus == "recent":
                chosen = previous_coins_menu(session)
                if chosen is not None:
                    load_index_for_edit(chosen, return_to_recent=True)
                else:
                    focus = "year"
            else:
                move_focus(1)
            continue

        if key == KEY_ENTER:
            if focus == "year":
                focus = "mint"
            elif focus == "mint":
                finish_save()
            elif focus == "save":
                finish_save()
            elif focus == "notes":
                finish_save()
            elif focus == "recent":
                chosen = previous_coins_menu(session)
                if chosen is not None:
                    load_index_for_edit(chosen, return_to_recent=True)
                else:
                    focus = "year"
            elif focus == "change_denom":
                change_current_country_denom(session)
                focus = "year"
            elif focus == "statistics":
                statistics_menu(session)
                focus = "year"
            elif focus == "invalid_check":
                chosen_invalid_index = invalid_year_check_menu(session)
                if chosen_invalid_index is not None:
                    load_index_for_edit(chosen_invalid_index)
                else:
                    focus = "year"
            elif focus == "quit":
                if confirm_save_quit(session):
                    break
            continue

        if key == KEY_BACKSPACE:
            if focus == "year":
                year = year[:-1]
            elif focus == "notes":
                notes = notes[:-1]
            continue

        if isinstance(key, str) and len(key) == 1 and key.isprintable():
            if focus == "year" and key.isdigit():
                if len(year) >= 4:
                    year = key
                else:
                    year += key
            elif focus == "notes":
                notes += key


def main():
    load_settings()
    configure_terminal_output()
    while True:
        session = session_menu()
        if not session:
            clear()
            print("Goodbye.")
            return
        sorting_loop(session)


if __name__ == "__main__":
    main()