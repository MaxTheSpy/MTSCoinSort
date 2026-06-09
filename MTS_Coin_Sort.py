# MTS CoinSort V0.1.3
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
import webbrowser
import urllib.parse
import urllib.request
import urllib.error
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
SESSION_TYPES = ["Bulk sorting", "Coin roll hunt", "Other"]

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
COIN_TYPES_PATH = os.path.join(DATA_DIR, "Coin_Types.csv")

DEFAULT_HOTKEYS = {
    "reject": "/",
    "keep_bulk": "*",
    "mint_next": "+",
    "mint_previous": "-",
    "type_next": ".",
    "save_quit": "q",
}

HOTKEY_LABELS = {
    "reject": "Toggle Reject",
    "keep_bulk": "Toggle Keep/Bulk",
    "mint_next": "Next Mint",
    "mint_previous": "Previous Mint",
    "type_next": "Next Coin Type",
    "save_quit": "Save + Quit",
}

HOTKEYS = DEFAULT_HOTKEYS.copy()
CSV_HEADERS = [
    "timestamp", "session_name", "session_type", "country", "denomination", "currency", "face_value",
    "year", "mint", "coin_type", "numista_number", "numista_title", "numista_category", "notes",
    "reject", "reject_reason", "keep_bulk",
    "numista_found", "possible_missing_collection", "new_collection",
    "roll_mode", "roll_number", "roll_coin_number", "roll_quantity"
]

COIN_TYPES_HEADERS = [
    "source", "country", "currency", "face_value", "denomination",
    "year", "min_year", "max_year", "mint",
    "coin_type", "numista_number", "numista_title", "numista_category",
    "year_range", "composition", "weight", "diameter", "thickness", "orientation",
    "comments", "source_csv", "last_seen"
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

FOCUS_ORDER = ["year", "mint", "coin_type", "save", "notes", "recent", "change_denom", "session_notes", "next_roll", "statistics", "quit"]

# ANSI color/bold works in most Linux terminals.
# On Windows, we attempt to enable Virtual Terminal Processing. If that is not
# available, the app falls back to plain text plus cls-based screen clears.
USE_COLOR = True
BIG_UI = True
ROLL_QUANTITIES = {}
CUSTOM_DENOMINATIONS = []
NUMISTA_CLIENT_ID = ""
NUMISTA_API_KEY = ""
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
    global DATA_DIR, SESSIONS_DIR, NUMISTA_DIR, EXPORTS_DIR, COIN_TYPES_PATH
    DATA_DIR = clean_user_path(path)
    SESSIONS_DIR = os.path.join(DATA_DIR, "coin_sort_sessions")
    NUMISTA_DIR = os.path.join(DATA_DIR, "Numista CSV")
    EXPORTS_DIR = os.path.join(DATA_DIR, "coin_sort_exports")
    COIN_TYPES_PATH = os.path.join(DATA_DIR, "Coin_Types.csv")

def ensure_app_dirs():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    os.makedirs(NUMISTA_DIR, exist_ok=True)
    os.makedirs(EXPORTS_DIR, exist_ok=True)

def load_settings():
    global HOTKEYS, USE_COLOR, BIG_UI, ROLL_QUANTITIES, CUSTOM_DENOMINATIONS, NUMISTA_CLIENT_ID, NUMISTA_API_KEY
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
        ROLL_QUANTITIES = normalize_roll_quantities(data.get("roll_quantities", {}))
        CUSTOM_DENOMINATIONS = normalize_custom_denominations(data.get("custom_denominations", []))
        numista_api = data.get("numista_api", {}) if isinstance(data.get("numista_api", {}), dict) else {}
        NUMISTA_CLIENT_ID = str(numista_api.get("client_id", "") or "")
        NUMISTA_API_KEY = str(numista_api.get("api_key", "") or "")
        ensure_app_dirs()
    except Exception:
        HOTKEYS = DEFAULT_HOTKEYS.copy()
        ROLL_QUANTITIES = {}
        CUSTOM_DENOMINATIONS = []
        NUMISTA_CLIENT_ID = ""
        NUMISTA_API_KEY = ""
        ensure_app_dirs()

def save_settings():
    ensure_app_dirs()
    data = {
        "data_dir": DATA_DIR,
        "hotkeys": HOTKEYS,
        "use_color": USE_COLOR,
        "big_ui": BIG_UI,
        "roll_quantities": ROLL_QUANTITIES,
        "custom_denominations": CUSTOM_DENOMINATIONS,
        "numista_api": {
            "client_id": NUMISTA_CLIENT_ID,
            "api_key": NUMISTA_API_KEY,
        },
    }
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def normalize_custom_denominations(value):
    """Return a clean list of custom country/denomination choices.

    These are for coins found in a session that are not already represented in
    the user's Numista CSV export yet, such as a Canadian cent found while
    searching US penny rolls. They are saved in settings.json and merged into
    the normal country/denomination picker.
    """
    cleaned = []
    seen = set()
    if not isinstance(value, list):
        return cleaned

    for item in value:
        if not isinstance(item, dict):
            continue
        country = str(item.get("country", "")).strip()
        face_value = normalize_decimal(item.get("face_value", ""))
        currency = str(item.get("currency", "")).strip()
        denomination = str(item.get("denomination", "")).strip() or make_denom_label(face_value, currency)
        if not country or not face_value:
            continue
        key = (country.lower(), face_value, currency.lower(), denomination.lower())
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({
            "country": country,
            "currency": currency,
            "face_value": face_value,
            "denomination": denomination,
        })
    cleaned.sort(key=lambda item: (item["country"].lower(), item["currency"].lower(), face_value_float_for_sort(item["face_value"]), item["denomination"].lower()))
    return cleaned


def face_value_float_for_sort(value):
    try:
        return float(normalize_decimal(value))
    except Exception:
        return 999999.0


def custom_denoms_by_country():
    mapping = {}
    for item in CUSTOM_DENOMINATIONS:
        country = str(item.get("country", "")).strip()
        label = str(item.get("denomination", "")).strip() or make_denom_label(item.get("face_value", ""), item.get("currency", ""))
        if country and label:
            mapping.setdefault(country, set()).add(label)
    return mapping


def find_custom_denom(country, denom_label):
    for item in CUSTOM_DENOMINATIONS:
        if str(item.get("country", "")).strip() == str(country).strip() and str(item.get("denomination", "")).strip() == str(denom_label).strip():
            return {
                "country": item.get("country", ""),
                "denomination": item.get("denomination", ""),
                "currency": item.get("currency", ""),
                "face_value": normalize_decimal(item.get("face_value", "")),
            }
    return None


def save_custom_denomination(country, face_value, currency, denomination=""):
    """Save a custom country/denomination and return a session choice dict."""
    global CUSTOM_DENOMINATIONS
    country = str(country or "").strip()
    face_value = normalize_decimal(face_value)
    currency = str(currency or "").strip()
    denomination = str(denomination or "").strip() or make_denom_label(face_value, currency)

    if not country or not face_value:
        return None

    new_item = {
        "country": country,
        "currency": currency,
        "face_value": face_value,
        "denomination": denomination,
    }

    normalized = normalize_custom_denominations(CUSTOM_DENOMINATIONS + [new_item])
    if normalized != CUSTOM_DENOMINATIONS:
        CUSTOM_DENOMINATIONS = normalized
        save_settings()

    return dict(new_item)


def remove_custom_denominations_for_country_face(country, face_value):
    """Remove temporary custom denominations after a Numista API type confirms them.

    A custom denomination is only a placeholder so the user can keep sorting a
    foreign or unexpected coin in the same session. Once the user enters an N#
    and the API saves a real Coin_Types.csv row for that country/face value, the
    placeholder should disappear from future pickers.
    """
    global CUSTOM_DENOMINATIONS
    country_key = str(country or "").strip().lower()
    face_key = normalize_decimal(face_value)
    if not country_key or not face_key:
        return False

    kept = []
    removed = False
    for item in CUSTOM_DENOMINATIONS:
        item_country = str(item.get("country", "")).strip().lower()
        item_face = normalize_decimal(item.get("face_value", ""))
        if item_country == country_key and item_face == face_key:
            removed = True
            continue
        kept.append(item)

    if removed:
        CUSTOM_DENOMINATIONS = normalize_custom_denominations(kept)
        save_settings()
    return removed


def cache_denoms_by_country():
    """Return denominations already learned in Coin_Types.csv.

    This lets API-added types backfill the country/denomination picker. For
    example, after adding a Canadian cent by N#, Canada 0.01 will come from
    Coin_Types.csv instead of staying as a temporary custom denomination.
    """
    mapping = {}
    try:
        for row in read_coin_type_cache_rows():
            country = str(row.get("country", "")).strip()
            face_value = normalize_decimal(row.get("face_value", ""))
            currency = normalize_currency_label(str(row.get("currency", "")).strip(), country)
            denom = str(row.get("denomination", "")).strip()
            if not denom or denom == face_value:
                denom = make_denom_label(face_value, currency) if currency else denom
            if country and face_value and denom:
                mapping.setdefault(country, set()).add(denom)
    except Exception:
        pass
    return mapping


def prompt_custom_country_denom(default_country=""):
    """Prompt for a new country/denomination when it is missing from Numista CSV."""
    country = str(default_country or "").strip()
    if not country:
        country = text_input("Enter country name for this coin, for example Canada, Mexico, United Kingdom:")
        if not country:
            return None

    face_value = text_input(
        f"Enter face value for {country}. Examples: 0.01, 0.05, 0.25, 1.00:"
    )
    if not face_value:
        return None

    currency = text_input(
        f"Enter currency/denomination family for {country}. Examples: Dollar, Canadian Dollar, Peso, Euro:"
    )
    if currency is None:
        return None

    default_label = make_denom_label(face_value, currency)
    denomination = text_input(
        "Enter display label for the picker, or press ENTER to use this default:",
        default_label,
    )
    if denomination is None:
        return None
    denomination = denomination or default_label

    choice = save_custom_denomination(country, face_value, currency, denomination)
    if choice:
        clear()
        print(green("Custom country/denomination saved."))
        print()
        print(f"Now available: {choice['country']} | {choice['denomination']}")
        print()
        print(dim("If no type is listed for the coin, choose OTHER, enter the Numista N#, and the API will populate Coin_Types.csv."))
        print("Press any key to continue.")
        read_key()
    return choice


def normalize_roll_quantities(value):
    """Return a clean {country|face_value|currency: int} roll quantity map."""
    cleaned = {}
    if not isinstance(value, dict):
        return cleaned
    for raw_key, raw_qty in value.items():
        try:
            qty = int(raw_qty)
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        parts = str(raw_key).split("|")
        if len(parts) >= 3:
            key = roll_quantity_key(parts[0], parts[1], "|".join(parts[2:]))
        else:
            key = str(raw_key).strip()
        if key:
            cleaned[key] = qty
    return cleaned

def roll_quantity_key(country, face_value, currency):
    return f"{str(country).strip()}|{normalize_decimal(face_value)}|{str(currency).strip()}"

def roll_quantity_label(key, qty):
    parts = str(key).split("|", 2)
    if len(parts) == 3:
        country, face_value, currency = parts
        denom = make_denom_label(face_value, currency)
        return f"{country} | {denom} = {qty} coins/roll"
    return f"{key} = {qty} coins/roll"

def get_roll_quantity_for_choice(choice):
    key = roll_quantity_key(choice.get("country", ""), choice.get("face_value", ""), choice.get("currency", ""))
    return ROLL_QUANTITIES.get(key)

def get_roll_quantity(session):
    return get_roll_quantity_for_choice(session)

def prompt_positive_int(title, default=""):
    while True:
        value = text_input(title, str(default) if default else "")
        if value is None:
            return None
        try:
            number = int(value)
        except ValueError:
            number = 0
        if number > 0:
            return number
        clear()
        print(red("Please enter a whole number greater than 0."))
        print("Press any key to try again.")
        read_key()


def mask_secret(value):
    value = str(value or "")
    if not value:
        return "(not set)"
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + ("*" * (len(value) - 8)) + value[-4:]


def numista_api_configured():
    return bool(str(NUMISTA_API_KEY or "").strip())


def numista_api_settings_menu():
    """Settings sub-page for storing Numista API credentials."""
    global NUMISTA_CLIENT_ID, NUMISTA_API_KEY
    index = 0
    menu_items = ["Set / edit client ID", "Set / edit API key", "Test API key", "Clear saved API settings", "Back"]

    while True:
        clear()
        print(c("=" * 100, "94"))
        print(bold(cyan("NUMISTA API SETTINGS".center(100))))
        print(c("=" * 100, "94"))
        print()
        print(dim("Saved in settings.json. Treat the API key like a password and do not share the file."))
        print()
        print(f"Client ID : {cyan(NUMISTA_CLIENT_ID or '(not set)')}")
        print(f"API key   : {cyan(mask_secret(NUMISTA_API_KEY))}")
        print()

        for i, item in enumerate(menu_items):
            print(reverse(item) if i == index else item)

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
        if selected == "Set / edit client ID":
            value = text_input("Enter Numista client/user ID:", NUMISTA_CLIENT_ID)
            if value is not None:
                NUMISTA_CLIENT_ID = value.strip()
                save_settings()
        elif selected == "Set / edit API key":
            value = text_input("Enter Numista API key:", NUMISTA_API_KEY)
            if value is not None:
                NUMISTA_API_KEY = value.strip()
                save_settings()
        elif selected == "Test API key":
            result, error = numista_fetch_type_details("1")
            clear()
            if error:
                print(red("Numista API test failed."))
                print()
                print(error)
            else:
                print(green("Numista API test worked."))
                print()
                print(f"Example returned: N# {result.get('id', '1')} - {result.get('title', 'Unknown')}")
            print()
            print("Press any key to continue.")
            read_key()
        elif selected == "Clear saved API settings":
            if prompt_yes_no("Clear saved Numista API settings?", "This removes the client ID and API key from settings.json."):
                NUMISTA_CLIENT_ID = ""
                NUMISTA_API_KEY = ""
                save_settings()
        elif selected == "Back":
            save_settings()
            return


def numista_fetch_type_details(numista_number):
    """Fetch one Numista catalogue type by N# using the saved API key.

    Returns (data, error). data is a dict when successful, error is a readable
    string when credentials/network/API response failed.
    """
    clean_number = clean_numista_number(numista_number)
    if not clean_number:
        return None, "No Numista number was entered."
    if not numista_api_configured():
        return None, "No Numista API key is saved. Add it in Settings > Numista API settings first."

    url = f"https://api.numista.com/v3/types/{urllib.parse.quote(clean_number)}?lang=en"
    headers = {
        "Accept": "application/json",
        "Numista-API-Key": NUMISTA_API_KEY.strip(),
    }
    if NUMISTA_CLIENT_ID.strip():
        # Numista's public examples primarily use Numista-API-Key. This is stored
        # for your reference and included harmlessly for future compatibility.
        headers["Numista-Client-Id"] = NUMISTA_CLIENT_ID.strip()

    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8", errors="replace")
        return json.loads(raw), None
    except urllib.error.HTTPError as exc:
        try:
            details = exc.read().decode("utf-8", errors="replace")
        except Exception:
            details = ""
        return None, f"HTTP {exc.code} from Numista API. {details}".strip()
    except urllib.error.URLError as exc:
        return None, f"Network error while contacting Numista API: {exc.reason}"
    except Exception as exc:
        return None, f"Could not read Numista API response: {exc}"


def numista_detail_value_text(details):
    value = details.get("value", {}) if isinstance(details.get("value", {}), dict) else {}
    return str(value.get("text", "") or "").strip()


def numista_detail_currency_text(details):
    currency = details.get("currency", {}) if isinstance(details.get("currency", {}), dict) else {}
    text = str(
        currency.get("full_name", "")
        or currency.get("name", "")
        or currency.get("display_name", "")
        or currency.get("title", "")
        or ""
    ).strip()
    return text


def currency_from_country_fallback(country):
    """Return a useful currency label when Numista omits currency text.

    Some API type responses provide a value like ``1 Cent`` but not a
    convenient currency string for building the local denomination picker.
    This fallback keeps the picker from creating bare labels such as ``0.01``.
    """
    key = re.sub(r"\s+", " ", str(country or "").strip().lower())
    defaults = {
        "canada": "Canadian Dollar",
        "united states": "Dollar (1785-date)",
        "mexico": "Peso",
        "united kingdom": "Pound sterling",
        "great britain": "Pound sterling",
        "australia": "Australian Dollar",
        "new zealand": "New Zealand Dollar",
    }
    return defaults.get(key, "")


def normalize_currency_label(currency, country=""):
    """Clean/repair currency text for picker labels."""
    currency = str(currency or "").strip()
    country = str(country or "").strip()
    if not currency:
        return currency_from_country_fallback(country)
    if "(" in currency and ")" in currency:
        return currency
    low_currency = currency.lower()
    low_country = country.lower()
    if low_currency == "dollar":
        if "canada" in low_country:
            return "Canadian Dollar"
        if "australia" in low_country:
            return "Australian Dollar"
        if "new zealand" in low_country:
            return "New Zealand Dollar"
        if "united states" in low_country:
            return "Dollar (1785-date)"
    return currency


def denomination_label_from_api(details, face_value, currency):
    """Build the picker label from API data without bare numeric placeholders."""
    country = numista_detail_country(details)
    currency = normalize_currency_label(currency, country)
    face_value = normalize_decimal(face_value) if face_value else ""
    value_text = numista_detail_value_text(details)
    if face_value and currency:
        return make_denom_label(face_value, currency)
    if value_text and currency:
        return f"{value_text} {currency}".strip()
    if value_text:
        return value_text
    if face_value:
        fallback_currency = normalize_currency_label("", country)
        return make_denom_label(face_value, fallback_currency) if fallback_currency else face_value
    return currency


def numista_value_to_face_value(details):
    """Best-effort face-value parser from a Numista API type response.

    The API often returns a display value like ``1 Cent`` or ``25 Cents``.
    This turns common decimal-currency cent values into the normalized numeric
    face value used by the sorter, such as 0.01 or 0.25.
    """
    value = details.get("value", {}) if isinstance(details.get("value", {}), dict) else {}

    for key in ("numeric_value", "decimal_value", "face_value", "value", "number"):
        raw = value.get(key)
        if raw not in (None, ""):
            try:
                return normalize_decimal(raw)
            except Exception:
                pass

    text = str(value.get("text", "") or details.get("value", "") or "").strip()
    lowered = text.lower()

    frac_map = {"½": 0.5, "1/2": 0.5, "¼": 0.25, "1/4": 0.25}
    amount = None
    for token, number in frac_map.items():
        if token in lowered:
            amount = number
            break
    if amount is None:
        match = re.search(r"(\d+(?:\.\d+)?)", lowered)
        if match:
            try:
                amount = float(match.group(1))
            except Exception:
                amount = None

    if amount is None:
        return ""

    # Decimal currencies: cents/pence/sen/etc. are hundredths of the main unit.
    if any(word in lowered for word in ("cent", "cents", "centime", "centimes", "penny", "pence", "sen")):
        return normalize_decimal(amount / 100.0)

    return normalize_decimal(amount)


def numista_choice_from_details(details):
    """Create a country/denomination session choice from API details."""
    country = numista_detail_country(details)
    currency = normalize_currency_label(numista_detail_currency_text(details), country)
    face_value = numista_value_to_face_value(details)
    denomination = denomination_label_from_api(details, face_value, currency)
    if not country or not face_value:
        return None
    return {
        "country": country,
        "currency": currency,
        "face_value": normalize_decimal(face_value),
        "denomination": denomination,
    }


def make_coin_type_cache_row_from_numista_choice(choice, details, year="", mint_name=""):
    """Save a Numista API type as a denomination/type seed before coin entry.

    This is used when the user finds a foreign/unexpected coin and chooses
    ``Add from Numista N#`` before typing the year and mint. It avoids temporary
    placeholder countries or currencies by pulling the real country, value,
    currency, title, and year range directly from Numista.
    """
    session_stub = dict(choice or {})
    min_year = str(details.get("min_year", "") or "").strip()
    seed_year = str(year or min_year or "").strip()
    return make_coin_type_cache_row_from_numista_api(session_stub, seed_year, mint_name, details)


def prompt_numista_country_denom_from_api(default_country=""):
    """Prompt for an N#, call the API, confirm, save type, and return choice.

    This replaces the older temporary custom-denomination workflow for coins
    such as Canadian cents found in a US roll. The user enters the N# first,
    the API supplies the country/denomination, then the user continues entering
    year/mint normally in the same session.
    """
    if not numista_api_configured():
        clear()
        print(red("Numista API key is not set."))
        print()
        print("Go to Settings > Numista API settings and save your API key first.")
        print("Press any key to return.")
        read_key()
        return None

    while True:
        prompt = (
            "Enter the Numista N# for the coin type you want to add. Example: 457 or N#457:\n\n"
            "IMPORTANT: Pressing ENTER here will call the Numista API using your saved API key.\n"
            "The API result will provide the country, denomination/value, title, and year range.\n"
            "You will verify the result before anything is saved. ESC cancels."
        )
        if default_country:
            prompt += f"\n\nExpected country, if known: {default_country}"
        entered = text_input(prompt)
        if entered is None:
            return None
        clean_number = clean_numista_number(entered)
        if not clean_number:
            clear()
            print(red("A Numista number is required."))
            print("Example: enter 457 or N#457")
            print("Press any key to continue.")
            read_key()
            continue

        details, error = numista_fetch_type_details(clean_number)
        if error:
            clear()
            print(red("Could not fetch that Numista type."))
            print()
            print(error)
            print()
            retry = prompt_yes_no("Try another N#?", "Choose No to return without changing country/denomination.")
            if retry:
                continue
            return None

        choice = numista_choice_from_details(details)
        if not choice:
            clear()
            print(red("The API result did not include enough value/country data to create a denomination."))
            print()
            print("You can try another N#, or add the coin later using an existing country/denomination.")
            print()
            retry = prompt_yes_no("Try another N#?", "Choose No to return without changing country/denomination.")
            if retry:
                continue
            return None

        confirmed = confirm_numista_type_details(details)
        if confirmed is None:
            return None
        if not confirmed:
            retry = prompt_yes_no("Try another N#?", "Choose No to return without changing country/denomination.")
            if retry:
                continue
            return None

        row = make_coin_type_cache_row_from_numista_choice(choice, details)
        all_rows = upsert_coin_type_cache_rows([row])
        remove_custom_denominations_for_country_face(choice.get("country", ""), choice.get("face_value", ""))

        clear()
        print(green("Numista type saved and country/denomination selected."))
        print()
        print(f"Now sorting: {cyan(choice['country'])} | {cyan(choice['denomination'])}")
        print(f"Saved type: N# {row.get('numista_number', '')} - {row.get('numista_title', '')}")
        print()
        print(dim("Next, type the coin year and mint. The type should now appear automatically when the year falls in the Numista range."))
        print("Press any key to continue.")
        read_key()

        # Store a fresh index for callers that want to update the active session.
        choice["_numista_type_index"] = build_type_index_from_cache(all_rows)
        return choice


def numista_detail_country(details):
    issuer = details.get("issuer", {}) if isinstance(details.get("issuer", {}), dict) else {}
    return str(issuer.get("name", "") or "").strip()


def numista_detail_category(details):
    return str(details.get("category", "") or details.get("type", "") or "").strip()


def numista_detail_years(details):
    min_year = details.get("min_year")
    max_year = details.get("max_year")
    if min_year and max_year:
        return f"{min_year}-{max_year}" if str(min_year) != str(max_year) else str(min_year)
    if min_year:
        return str(min_year)
    if max_year:
        return str(max_year)
    return "Unknown"


def preview_numista_type_details(details):
    """Render a compact preview of a Numista type fetched from the API."""
    clear()
    print(c("=" * 100, "94"))
    print(bold(cyan("NUMISTA TYPE PREVIEW".center(100))))
    print(c("=" * 100, "94"))
    print()
    print(f"N#          : {cyan(str(details.get('id', '')))}")
    print(f"Title       : {bold(details.get('title', 'Unknown'))}")
    print(f"Country     : {numista_detail_country(details) or 'Unknown'}")
    print(f"Years       : {numista_detail_years(details)}")
    print(f"Value       : {numista_detail_value_text(details) or 'Unknown'}")
    print(f"Currency    : {numista_detail_currency_text(details) or 'Unknown'}")
    print(f"Category    : {numista_detail_category(details) or 'Unknown'}")
    composition = details.get("composition", {})
    if isinstance(composition, dict) and composition.get("text"):
        print(f"Composition : {composition.get('text')}")
    print()
    print(dim("This will be saved to Coin_Types.csv. If the API provides a year range, all years in that range will match."))


def confirm_numista_type_details(details):
    """Show the fetched Numista type and require the user to confirm saving it."""
    selection = None

    def mark(text, active):
        return reverse(text) if active else dim(text)

    while True:
        clear()
        print(c("=" * 100, "94"))
        print(bold(cyan("VERIFY NUMISTA API RESULT".center(100))))
        print(c("=" * 100, "94"))
        print()
        print(yellow("The N# you typed was looked up with the Numista API."))
        print(bold("Verify this is the correct coin type before saving."))
        print()
        print(f"N#          : {cyan(str(details.get('id', '')))}")
        print(f"Title       : {bold(details.get('title', 'Unknown'))}")
        print(f"Country     : {numista_detail_country(details) or 'Unknown'}")
        print(f"Years       : {numista_detail_years(details)}")
        print(f"Value       : {numista_detail_value_text(details) or 'Unknown'}")
        print(f"Currency    : {numista_detail_currency_text(details) or 'Unknown'}")
        print(f"Category    : {numista_detail_category(details) or 'Unknown'}")
        composition = details.get("composition", {})
        if isinstance(composition, dict) and composition.get("text"):
            print(f"Composition : {composition.get('text')}")
        if details.get("weight"):
            print(f"Weight      : {details.get('weight')} g")
        if details.get("size"):
            print(f"Diameter    : {details.get('size')} mm")
        print()
        print(dim("If saved, this type is added to Coin_Types.csv. If Numista gives a year range, every year in that range will match automatically."))
        print()
        print("   +  " + mark(green("  YES — save this type  "), selection is True))
        print("   -  " + mark(red("  NO — do not save this type  "), selection is False))
        print()
        if selection is None:
            print(bold(yellow("No option selected yet.")))
        elif selection is True:
            print(green("Selected: YES — save this Numista type."))
        else:
            print(red("Selected: NO — do not save this type."))
        print()
        print(dim("Use + or - to choose. ENTER confirms. BACKSPACE/ESC cancels."))

        key = read_key()
        if key in ("+", "=", KEY_DOWN, KEY_RIGHT):
            selection = True
        elif key in ("-", "_", KEY_UP, KEY_LEFT):
            selection = False
        elif key == KEY_ENTER and selection is not None:
            return selection
        elif key in (KEY_BACKSPACE, KEY_ESC):
            return None


def make_coin_type_cache_row_from_numista_api(session, year, mint_name, details):
    """Convert one Numista /types/{id} response into a range-aware cache row."""
    numista_number = clean_numista_number(details.get("id", ""))
    title = str(details.get("title", "") or "Unknown type").strip()
    short_type = coin_type_from_numista_title(title)
    category = numista_detail_category(details)
    value_text = numista_detail_value_text(details)
    api_country = numista_detail_country(details)
    currency_text = normalize_currency_label(numista_detail_currency_text(details), api_country or session.get("country", ""))
    min_year = str(details.get("min_year", "") or "").strip()
    max_year = str(details.get("max_year", "") or "").strip()
    if not min_year:
        min_year = str(year or "").strip()
    if not max_year:
        max_year = min_year
    years = year_range_label(min_year, max_year, numista_detail_years(details))

    composition = ""
    comp_obj = details.get("composition", {})
    if isinstance(comp_obj, dict):
        composition = str(comp_obj.get("text", "") or "").strip()

    comments = []
    if api_country:
        comments.append(f"API country: {api_country}")
    if value_text:
        comments.append(f"API value: {value_text}")
    if currency_text:
        comments.append(f"API currency: {currency_text}")
    if years:
        comments.append(f"API years: {years}")

    row_country = api_country or session.get("country", "")
    row_currency = normalize_currency_label(currency_text or session.get("currency", ""), row_country)
    row_face_value = session.get("face_value", "")
    row_denomination = denomination_label_from_api(details, row_face_value, row_currency) if row_face_value else (value_text or session.get("denomination", ""))

    return make_coin_type_cache_row(
        "numista_api",
        row_country,
        row_currency,
        row_face_value,
        row_denomination,
        str(year).strip(),
        mint_name,
        short_type,
        numista_number,
        title,
        category,
        "; ".join(comments),
        "numista_api",
        min_year=min_year,
        max_year=max_year,
        year_range=years,
        composition=composition,
        weight=details.get("weight", "") or "",
        diameter=details.get("size", "") or "",
        thickness=details.get("thickness", "") or "",
        orientation=details.get("orientation", "") or "",
    )


def coin_roll_quantities_menu(numista_countries=None, denoms_by_country=None):
    """Settings sub-page for user-defined roll quantities by country/denomination."""
    global ROLL_QUANTITIES
    numista_countries = numista_countries or []
    denoms_by_country = denoms_by_country or {}
    index = 0

    while True:
        entries = sorted(ROLL_QUANTITIES.items(), key=lambda item: item[0].lower())
        menu_items = [roll_quantity_label(key, qty) for key, qty in entries]
        menu_items += ["Add / edit from Numista denominations", "Add / edit custom entry", "Delete selected roll quantity", "Back"]
        index = max(0, min(index, len(menu_items) - 1))

        clear()
        print(c("=" * 100, "94"))
        print(bold(cyan("COIN ROLL QUANTITIES".center(100))))
        print(c("=" * 100, "94"))
        print()
        print(dim("These are saved in settings.json and are not hard-coded."))
        print(dim("Format: Country | denomination = coins per roll"))
        print()
        if not entries:
            print(yellow("No roll quantities saved yet."))
            print()

        for i, item in enumerate(menu_items):
            print(reverse(item) if i == index else item)

        print()
        print(dim("TAB/DOWN/+ next | UP/- previous | ENTER select | BACKSPACE/ESC back"))
        key = read_key()
        if key in (KEY_BACKSPACE, KEY_ESC):
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
        if index < len(entries):
            key_name, current_qty = entries[index]
            qty = prompt_positive_int(f"Edit coins per roll for:\n{roll_quantity_label(key_name, current_qty)}", current_qty)
            if qty is not None:
                ROLL_QUANTITIES[key_name] = qty
                save_settings()
            continue

        if selected == "Add / edit from Numista denominations":
            if not numista_countries:
                clear()
                print(yellow("No Numista countries/denominations are loaded yet."))
                print("Use custom entry, or add Numista CSV files and restart.")
                print("Press any key to continue.")
                read_key()
                continue
            choice = choose_country_and_denom(numista_countries, denoms_by_country)
            if not choice:
                continue
            key_name = roll_quantity_key(choice["country"], choice["face_value"], choice["currency"])
            qty = prompt_positive_int(f"Coins per roll for {choice['country']} | {choice['denomination']}:", ROLL_QUANTITIES.get(key_name, ""))
            if qty is not None:
                ROLL_QUANTITIES[key_name] = qty
                save_settings()
            continue

        if selected == "Add / edit custom entry":
            country = text_input("Country name for this roll quantity:")
            if not country:
                continue
            face_value = text_input("Face value, for example 0.01, 0.25, 1.00:")
            if not face_value:
                continue
            currency = text_input("Currency/denomination label, for example Dollar (1785-date), Euro, Peso:")
            if currency is None:
                continue
            key_name = roll_quantity_key(country, face_value, currency)
            qty = prompt_positive_int(f"Coins per roll for {country} | {make_denom_label(face_value, currency)}:", ROLL_QUANTITIES.get(key_name, ""))
            if qty is not None:
                ROLL_QUANTITIES[key_name] = qty
                save_settings()
            continue

        if selected == "Delete selected roll quantity":
            if not entries:
                continue
            labels = [roll_quantity_label(key, qty) for key, qty in entries]
            picked = choose_from_list("Delete which roll quantity?", labels + ["Cancel"])
            if picked and picked != "Cancel":
                delete_index = labels.index(picked)
                key_name = entries[delete_index][0]
                if prompt_yes_no("Delete this roll quantity?", roll_quantity_label(key_name, ROLL_QUANTITIES[key_name])):
                    ROLL_QUANTITIES.pop(key_name, None)
                    save_settings()
            continue

        if selected == "Back":
            save_settings()
            return

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

def settings_menu(numista_countries=None, denoms_by_country=None):
    global USE_COLOR, BIG_UI
    actions = list(DEFAULT_HOTKEYS.keys())
    menu_items = [HOTKEY_LABELS[action] for action in actions] + ["Coin roll quantities", "Numista API settings", "Toggle colors", "Toggle big title", "Reset hotkeys to defaults", "Back"]
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
        elif selected == "Coin roll quantities":
            coin_roll_quantities_menu(numista_countries, denoms_by_country)
        elif selected == "Numista API settings":
            numista_api_settings_menu()
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

def clean_numista_number(value):
    """Return only the numeric part from values like 'N# 12345'."""
    match = re.search(r"(\d+)", str(value or ""))
    return match.group(1) if match else ""

def numista_url(value):
    number = clean_numista_number(value)
    return f"https://en.numista.com/catalogue/pieces{number}.html" if number else ""

def terminal_link(text, url):
    """Clickable OSC-8 terminal hyperlink, closed immediately after text.

    Some terminals, including VS Code's integrated terminal, can leave the
    hyperlink "open" when OSC-8 is terminated with ST (ESC \\) inside an
    already-colored line. BEL termination is better supported there. The final
    ANSI reset is intentional: it prevents the clickable span from leaking into
    the rest of the line.
    """
    if not url:
        return text
    if not ANSI_SUPPORTED:
        return f"{text} <{url}>"
    return f"\033]8;;{url}\a{text}\033]8;;\a\033[0m"


def ensure_coin_types_csv():
    """Create Coin_Types.csv if it does not exist yet."""
    ensure_app_dirs()
    if not os.path.exists(COIN_TYPES_PATH):
        with open(COIN_TYPES_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COIN_TYPES_HEADERS, extrasaction="ignore")
            writer.writeheader()


def safe_int(value, default=None):
    """Return int(value) when possible, otherwise default."""
    try:
        text = str(value).strip()
        if not text:
            return default
        return int(float(text))
    except Exception:
        return default


def normalized_year_bounds(row):
    """Return (min_year, max_year) for exact-year and range cache rows."""
    year = str(row.get("year", "")).strip()
    min_year = str(row.get("min_year", "")).strip()
    max_year = str(row.get("max_year", "")).strip()

    if not min_year and year:
        min_year = year
    if not max_year and min_year:
        max_year = min_year
    if not min_year and max_year:
        min_year = max_year
    return min_year, max_year


def year_range_label(min_year, max_year, fallback=""):
    min_year = str(min_year or "").strip()
    max_year = str(max_year or "").strip()
    if min_year and max_year:
        return min_year if min_year == max_year else f"{min_year}-{max_year}"
    return str(fallback or "").strip()


def coin_type_cache_key(row):
    min_year, max_year = normalized_year_bounds(row)
    # API/manual range rows should de-dupe by range + Numista number, not by
    # whichever year the user happened to be sorting when they added the type.
    source = str(row.get("source", "")).strip()
    year_key = str(row.get("year", "")).strip()
    if source in ("numista_api", "manual_api") and min_year and max_year:
        year_key = ""

    return (
        str(row.get("country", "")).strip(),
        normalize_decimal(row.get("face_value", "")),
        year_key,
        str(min_year),
        str(max_year),
        normalize_mint(row.get("mint", "")),
        clean_numista_number(row.get("numista_number", "")),
        str(row.get("coin_type", "")).strip(),
    )


def coin_type_from_numista_title(title):
    """Return a short grouping name from a Numista title.

    Examples:
      1 Cent "Lincoln Cent" (Gold Omega Cent) -> Lincoln Cent
      1 Cent "Liberty Head" -> Liberty Head
      1 Dollar (American Innovation - Illinois) -> American Innovation - Illinois
    """
    title = str(title or "").strip()
    quoted = re.search(r'"([^"]+)"', title)
    if quoted:
        return quoted.group(1).strip()
    paren = re.search(r"\(([^()]+)\)", title)
    if paren:
        return paren.group(1).strip()
    if " - " in title:
        return title.split(" - ", 1)[1].strip()
    return title or "Unknown type"


def make_coin_type_cache_row(
    source, country, currency, face_value, denomination, year, mint,
    coin_type, numista_number, numista_title="", numista_category="",
    comments="", source_csv="", min_year="", max_year="", year_range="",
    composition="", weight="", diameter="", thickness="", orientation=""
):
    year_text = str(year).strip()
    min_year = str(min_year).strip() if min_year is not None else ""
    max_year = str(max_year).strip() if max_year is not None else ""
    if not min_year and year_text:
        min_year = year_text
    if not max_year and min_year:
        max_year = min_year
    if not year_range:
        year_range = year_range_label(min_year, max_year, year_text)

    return {
        "source": source,
        "country": str(country).strip(),
        "currency": str(currency).strip(),
        "face_value": normalize_decimal(face_value),
        "denomination": str(denomination).strip(),
        "year": year_text,
        "min_year": str(min_year).strip(),
        "max_year": str(max_year).strip(),
        "mint": normalize_mint(mint),
        "coin_type": str(coin_type or "Unknown type").strip(),
        "numista_number": clean_numista_number(numista_number),
        "numista_title": str(numista_title or coin_type or "Unknown type").strip(),
        "numista_category": str(numista_category).strip(),
        "year_range": str(year_range or "").strip(),
        "composition": str(composition or "").strip(),
        "weight": str(weight or "").strip(),
        "diameter": str(diameter or "").strip(),
        "thickness": str(thickness or "").strip(),
        "orientation": str(orientation or "").strip(),
        "comments": str(comments).strip(),
        "source_csv": os.path.basename(str(source_csv)) if source_csv else "",
        "last_seen": datetime.now().isoformat(timespec="seconds"),
    }

def read_coin_type_cache_rows():
    ensure_coin_types_csv()
    rows = []
    try:
        with open(COIN_TYPES_PATH, "r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                normalized = {key: row.get(key, "") for key in COIN_TYPES_HEADERS}
                # Migrate older Coin_Types.csv rows in memory. The next write will
                # persist the expanded headers safely.
                min_year, max_year = normalized_year_bounds(normalized)
                normalized["min_year"] = min_year
                normalized["max_year"] = max_year
                if not normalized.get("year_range"):
                    normalized["year_range"] = year_range_label(min_year, max_year, normalized.get("year", ""))
                rows.append(normalized)
    except Exception:
        rows = []
    return rows


def write_coin_type_cache_rows(rows):
    ensure_app_dirs()
    with open(COIN_TYPES_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COIN_TYPES_HEADERS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            min_year, max_year = normalized_year_bounds(row)
            clean_row = {key: row.get(key, "") for key in COIN_TYPES_HEADERS}
            clean_row["min_year"] = min_year
            clean_row["max_year"] = max_year
            if not clean_row.get("year_range"):
                clean_row["year_range"] = year_range_label(min_year, max_year, clean_row.get("year", ""))
            repaired_currency = normalize_currency_label(clean_row.get("currency", ""), clean_row.get("country", ""))
            repaired_face = normalize_decimal(clean_row.get("face_value", ""))
            if repaired_currency and (not clean_row.get("currency") or str(clean_row.get("denomination", "")).strip() == repaired_face):
                clean_row["currency"] = repaired_currency
                clean_row["denomination"] = make_denom_label(repaired_face, repaired_currency)
            writer.writerow(clean_row)


def upsert_coin_type_cache_rows(new_rows):
    """Insert or enrich type rows without duplicating existing cache entries."""
    existing_rows = read_coin_type_cache_rows()
    existing_by_key = {coin_type_cache_key(row): row for row in existing_rows}
    changed = False

    for row in new_rows:
        key = coin_type_cache_key(row)
        existing = existing_by_key.get(key)
        if existing is None:
            existing_rows.append(row)
            existing_by_key[key] = row
            changed = True
            continue

        # If a previous row was created before metadata support existed, fill in
        # any blanks from the new Numista CSV/API data.
        for field in COIN_TYPES_HEADERS:
            if not str(existing.get(field, "")).strip() and str(row.get(field, "")).strip():
                existing[field] = row.get(field, "")
                changed = True

        # Repair older API-created rows that had a bare denomination like
        # ``0.01`` because the previous parser did not derive Canadian Dollar,
        # Australian Dollar, etc. from the API/country.
        existing_face = normalize_decimal(existing.get("face_value", ""))
        new_currency = normalize_currency_label(row.get("currency", ""), row.get("country", "") or existing.get("country", ""))
        existing_denom = str(existing.get("denomination", "")).strip()
        if new_currency and existing_face and (not existing.get("currency") or existing_denom == existing_face):
            existing["currency"] = new_currency
            existing["denomination"] = make_denom_label(existing_face, new_currency)
            changed = True

    if changed or not os.path.exists(COIN_TYPES_PATH):
        write_coin_type_cache_rows(existing_rows)
    return existing_rows


def option_from_cache_row(row, face_value, year, mint):
    min_year, max_year = normalized_year_bounds(row)
    return {
        "coin_type": row.get("coin_type", "") or row.get("numista_title", "") or "Unknown type",
        "numista_number": clean_numista_number(row.get("numista_number", "")),
        "numista_title": row.get("numista_title", "") or row.get("coin_type", "") or "Unknown type",
        "numista_category": row.get("numista_category", ""),
        "denomination": row.get("denomination", "") or make_denom_label(face_value, row.get("currency", "")),
        "country": str(row.get("country", "")).strip(),
        "face_value": face_value,
        "year": str(year or row.get("year", "")).strip(),
        "min_year": min_year,
        "max_year": max_year,
        "year_range": row.get("year_range", "") or year_range_label(min_year, max_year, row.get("year", "")),
        "mint": mint,
        "source": row.get("source", ""),
        "composition": row.get("composition", ""),
        "weight": row.get("weight", ""),
        "diameter": row.get("diameter", ""),
        "thickness": row.get("thickness", ""),
        "orientation": row.get("orientation", ""),
        "comments": row.get("comments", ""),
    }


def build_type_index_from_cache(rows):
    """Build exact-year and range lookup indexes from Coin_Types.csv rows.

    The returned dict is backwards-compatible for exact lookups using
    (country, face_value, year, mint). It also includes a special "__ranges__"
    list used by get_detected_type_options() for API-added types that span many
    years, such as N#14203 covering 1816-1835.
    """
    type_index = {"__ranges__": []}
    range_seen = set()

    for row in rows:
        country = str(row.get("country", "")).strip()
        face_value = normalize_decimal(row.get("face_value", ""))
        year = str(row.get("year", "")).strip()
        mint = normalize_mint(row.get("mint", ""))
        min_year, max_year = normalized_year_bounds(row)
        source = str(row.get("source", "")).strip()

        if not country or not face_value:
            continue

        # Exact-year index for Numista export rows and one-year API rows.
        if year:
            option = option_from_cache_row(row, face_value, year, mint)
            key = (country, face_value, year, mint)
            bucket = type_index.setdefault(key, [])
            if not any(existing.get("coin_type") == option["coin_type"] and existing.get("numista_number") == option["numista_number"] for existing in bucket):
                bucket.append(option)

        # Range index for API/manual API rows. CSV rows are already exact by
        # Gregorian year, so keeping their range off avoids noisy duplicates.
        min_int = safe_int(min_year)
        max_int = safe_int(max_year)
        if source in ("numista_api", "manual_api") and min_int is not None and max_int is not None:
            range_key = (
                country, face_value, min_int, max_int, mint,
                clean_numista_number(row.get("numista_number", "")),
                row.get("coin_type", ""),
            )
            if range_key not in range_seen:
                type_index["__ranges__"].append(option_from_cache_row(row, face_value, year, mint))
                range_seen.add(range_key)

    for key in list(type_index.keys()):
        if key == "__ranges__":
            continue
        type_index[key].sort(key=lambda option: (option.get("coin_type", "").lower(), clean_numista_number(option.get("numista_number", "")) or "999999999"))
    type_index["__ranges__"].sort(key=lambda option: (option.get("coin_type", "").lower(), safe_int(option.get("min_year", ""), 999999), clean_numista_number(option.get("numista_number", "")) or "999999999"))
    return type_index


def numista_search_denom_terms(session):
    """Return cleaner denomination search terms for Numista's catalog search.

    The active denomination label can be something like
    ``0.01 Dollar (1785-date)``. Numista's search often does better with
    human terms like ``1 cent`` and without the parenthesized currency era.
    Keep this conservative: use common US names when obvious, then fall back
    to a cleaned denomination label and numeric face/currency.
    """
    country = str(session.get("country", "")).strip().lower()
    face = normalize_decimal(session.get("face_value", ""))
    currency = str(session.get("currency", "")).strip()
    denom = re.sub(r"\s*\([^)]*\)", "", str(session.get("denomination", "")).strip()).strip()

    if "united states" in country:
        us_terms = {
            "0.01": "1 cent",
            "0.05": "5 cents",
            "0.10": "10 cents",
            "0.25": "25 cents",
            "0.50": "50 cents",
            "1.00": "1 dollar",
        }
        if face in us_terms:
            return us_terms[face]

    if denom:
        return denom
    if face and currency:
        return f"{face} {currency}"
    return face


def numista_search_url(session, year, mint_name):
    """Build a broad Numista search URL for finding a missing type.

    Mint marks are intentionally omitted. Searching ``2025 W`` or ``2005 D``
    can return no results even when the type exists, because Numista catalog
    search is type-oriented more than mint-row-oriented. The user can still
    refine the search manually after the browser opens.
    """
    parts = [
        session.get("country", ""),
        numista_search_denom_terms(session),
        str(year),
    ]
    query = "+".join(re.sub(r"\s+", "+", str(p).strip()) for p in parts if p and str(p).strip())
    return f"https://en.numista.com/catalogue/index.php?r={query}&ct=coin"


def prompt_yes_no(title, detail=""):
    """Return True for Yes, False for No, or None when cancelled."""
    choice = choose_from_list(title + (("\n\n" + detail) if detail else ""), ["Yes", "No"])
    if choice is None:
        return None
    return choice == "Yes"


def prompt_manual_coin_type(session, year, mint_name, existing_notes=""):
    """Handle OTHER type by browser search + N# + Numista API lookup.

    Flow:
      1. Ask whether to open Numista search in the browser.
      2. User enters the N# they found.
      3. Fetch /types/{id} with the saved API key.
      4. Preview the result and confirm.
      5. Save the fetched type to Coin_Types.csv for the current coin.
    """
    if not numista_api_configured():
        clear()
        print(red("Numista API key is not set."))
        print()
        print("Go to Settings > Numista API settings and save your API key first.")
        print("Press any key to return to editing this coin.")
        read_key()
        return None, None

    should_search = prompt_yes_no(
        "Coin type is OTHER. Open Numista search in your browser?",
        "Find the correct catalogue page, then come back and enter the N# number. BACKSPACE/ESC returns to editing."
    )
    if should_search is None:
        return None, None

    if should_search:
        try:
            webbrowser.open(numista_search_url(session, year, mint_name))
        except Exception:
            pass

    while True:
        numista_number = text_input(
            "Enter the Numista N# for this type. Example: 1109 or N#1109:\n\n"
            "IMPORTANT: Pressing ENTER here will call the Numista API using your saved API key.\n"
            "After the API returns a result, you will verify it before anything is saved."
        )
        if numista_number is None:
            return None, None
        clean_number = clean_numista_number(numista_number)
        if not clean_number:
            clear()
            print(red("A Numista number is required."))
            print("Example: enter 1109 or N#1109")
            print("Press any key to continue.")
            read_key()
            continue

        details, error = numista_fetch_type_details(clean_number)
        if error:
            clear()
            print(red("Could not fetch that Numista type."))
            print()
            print(error)
            print()
            retry = prompt_yes_no("Try another N#?", "Choose No to return to editing the coin.")
            if retry:
                continue
            return None, None

        confirmed = confirm_numista_type_details(details)
        if confirmed is None:
            return None, None
        if not confirmed:
            retry = prompt_yes_no("Try another N#?", "Choose No to return to editing the coin.")
            if retry:
                continue
            return None, None

        row = make_coin_type_cache_row_from_numista_api(session, year, mint_name, details)
        all_rows = upsert_coin_type_cache_rows([row])
        session["numista_type_index"] = build_type_index_from_cache(all_rows)

        # If this coin started from a temporary custom denomination, replace it
        # with the confirmed API-backed denomination from Coin_Types.csv.
        remove_custom_denominations_for_country_face(row.get("country", ""), row.get("face_value", ""))
        session["country"] = row.get("country", session.get("country", ""))
        session["currency"] = row.get("currency", session.get("currency", ""))
        session["face_value"] = row.get("face_value", session.get("face_value", ""))
        session["denomination"] = row.get("denomination", session.get("denomination", ""))

        return {
            "coin_type": row["coin_type"],
            "numista_number": row["numista_number"],
            "numista_title": row["numista_title"],
            "numista_category": row["numista_category"],
            "denomination": row["denomination"],
            "country": row["country"],
            "face_value": row["face_value"],
            "year": row["year"],
            "mint": row["mint"],
            "selected_mint": row["mint"],
            "match_note": "Numista API saved to Coin_Types.csv",
        }, row["coin_type"]

def load_numista_index():
    """Load owned coins and type choices from every CSV in ./Numista CSV.

    Numista export columns by position. Important: Numista exports can contain
    duplicate header names such as Weight, so this intentionally uses fixed
    column indexes instead of DictReader names.

      A  / 0  Country
      D  / 3  Currency
      E  / 4  Face value
      G  / 6  N# number
      H  / 7  Title
      I  / 8  Type/category
      J  / 9  Year range
      L  / 11 Composition
      M  / 12 Weight
      N  / 13 Diameter
      Q  / 16 Thickness
      R  / 17 Orientation
      T  / 19 Gregorian year
      U  / 20 Mintmark
      Y  / 24 Quantity

    Returns:
      index: set of owned (country, face_value, gregorian_year, mintmark)
      csv_files: loaded CSV paths
      countries: sorted country names
      denoms_by_country: {country: ["0.25 Dollar (1785-date)", ...]}
      type_index: exact-year lookup plus __ranges__ for API-added range rows
    """
    ensure_numista_dir()
    ensure_coin_types_csv()
    index = set()
    cache_rows_to_seed = []
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
                    numista_number = row[6].strip() if len(row) > 6 else ""
                    title = row[7].strip() if len(row) > 7 else ""
                    numista_category = row[8].strip() if len(row) > 8 else ""
                    export_year_range = row[9].strip() if len(row) > 9 else ""
                    composition = row[11].strip() if len(row) > 11 else ""
                    weight = row[12].strip() if len(row) > 12 else ""
                    diameter = row[13].strip() if len(row) > 13 else ""
                    thickness = row[16].strip() if len(row) > 16 else ""
                    orientation = row[17].strip() if len(row) > 17 else ""
                    gregorian_year = row[19].strip() if len(row) > 19 else ""
                    mintmark = normalize_mint(row[20]) if len(row) > 20 else ""

                    if not country or not face_value:
                        continue

                    countries.add(country)
                    denom_label = make_denom_label(face_value, currency)
                    denom_map.setdefault(country, set()).add(denom_label)

                    if gregorian_year:
                        cache_rows_to_seed.append(make_coin_type_cache_row(
                            "numista_csv", country, currency, face_value, denom_label,
                            gregorian_year, mintmark, title or "Unknown type",
                            numista_number, title, numista_category, "", path,
                            min_year=gregorian_year,
                            max_year=gregorian_year,
                            year_range=export_year_range or gregorian_year,
                            composition=composition,
                            weight=weight,
                            diameter=diameter,
                            thickness=thickness,
                            orientation=orientation,
                        ))

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
                        pass

                    index.add((country, face_value, gregorian_year, mintmark))
        except Exception:
            continue

    # Merge API/cache denominations from Coin_Types.csv so N#-added types
    # backfill the picker even when the user has no Numista export rows for
    # that country yet.
    for cache_country, labels in cache_denoms_by_country().items():
        if cache_country:
            countries.add(cache_country)
            denom_map.setdefault(cache_country, set()).update(labels)

    # Merge custom denominations saved in settings.json so they appear in the
    # same picker as Numista CSV denominations until an API-backed row replaces
    # them.
    for item in CUSTOM_DENOMINATIONS:
        custom_country = str(item.get("country", "")).strip()
        custom_label = str(item.get("denomination", "")).strip() or make_denom_label(item.get("face_value", ""), item.get("currency", ""))
        if custom_country and custom_label:
            countries.add(custom_country)
            denom_map.setdefault(custom_country, set()).add(custom_label)

    countries = sorted(countries)
    denoms_by_country = {
        country: sorted(labels, key=lambda label: (split_denom_label(label)[1].lower(), face_value_float_for_sort(split_denom_label(label)[0]), split_denom_label(label)[0]))
        for country, labels in denom_map.items()
    }

    coin_type_rows = upsert_coin_type_cache_rows(cache_rows_to_seed)
    type_index = build_type_index_from_cache(coin_type_rows)

    return index, csv_files, countries, denoms_by_country, type_index

def get_detected_type_options(session, year, mint_name):
    """Return Numista type choices for country/value/year.

    Match order:
      1. Exact year + current mint candidates.
      2. Same year from another mint.
      3. API/manual range rows where min_year <= entered year <= max_year.
      4. OTHER.
    """
    country = session.get("country", "").strip()
    face_value = normalize_decimal(session.get("face_value", ""))
    year_text = str(year).strip()
    entered_year = safe_int(year_text)
    type_index = session.get("numista_type_index", {}) or {}
    options = []
    seen = set()

    def add_option(option, match_note=""):
        # De-dupe by Numista number + type/title, intentionally ignoring mint.
        unique = (
            option.get("numista_number", ""),
            option.get("coin_type", ""),
            option.get("numista_title", ""),
        )
        if unique in seen:
            return
        seen.add(unique)
        copied = dict(option)
        copied["selected_mint"] = normalize_mint(mint_name)
        copied["match_note"] = match_note
        options.append(copied)

    if country and face_value and year_text:
        exact_mints = coin_mint_candidates(mint_name)

        # 1) Exact/current mint candidates first.
        for mint in exact_mints:
            for option in type_index.get((country, face_value, year_text, mint), []):
                add_option(option, "exact mint")

        # 2) Same country/value/year from any mint.
        for key, bucket in type_index.items():
            if key == "__ranges__" or not isinstance(key, tuple) or len(key) != 4:
                continue
            idx_country, idx_face, idx_year, idx_mint = key
            if idx_country == country and idx_face == face_value and idx_year == year_text:
                for option in bucket:
                    if idx_mint in exact_mints:
                        continue
                    add_option(option, f"same Numista type from mint {idx_mint or 'No Mint'}")

        # 3) API/manual range matches. This is what lets a single N#14203 API
        # entry detect all Liberty Head cent years from 1816 through 1835.
        if entered_year is not None:
            for option in type_index.get("__ranges__", []):
                if option.get("country", "") != country:
                    continue
                if normalize_decimal(option.get("face_value", "")) != face_value:
                    continue
                option_mint = normalize_mint(option.get("mint", ""))
                if option_mint and option_mint not in exact_mints:
                    # Blank mint ranges can match any mint. Specific mint ranges
                    # only match that mint.
                    continue
                min_year = safe_int(option.get("min_year", ""))
                max_year = safe_int(option.get("max_year", ""))
                if min_year is None or max_year is None:
                    continue
                if min_year <= entered_year <= max_year:
                    add_option(option, f"API range {year_range_label(min_year, max_year)}")

    options.sort(key=lambda option: (
        0 if option.get("match_note") == "exact mint" else 1 if str(option.get("match_note", "")).startswith("same Numista") else 2,
        option.get("coin_type", "").lower(),
        safe_int(option.get("min_year", ""), 999999),
        clean_numista_number(option.get("numista_number", "")) or "999999999",
    ))

    options.append({
        "coin_type": "OTHER",
        "numista_number": "",
        "numista_title": "OTHER",
        "numista_category": "Manual / not listed",
        "denomination": session.get("denomination", ""),
        "country": country,
        "face_value": face_value,
        "year": year_text,
        "min_year": year_text,
        "max_year": year_text,
        "year_range": year_text,
        "mint": normalize_mint(mint_name),
        "selected_mint": normalize_mint(mint_name),
        "match_note": "manual",
    })
    return options

def type_option_label(option):
    coin_type = option.get("coin_type", "") or "Unknown type"
    number = option.get("numista_number", "")
    clean_number = clean_numista_number(number)
    denom = option.get("denomination", "")
    category = option.get("numista_category", "")
    match_note = option.get("match_note", "")

    parts = [coin_type]
    details = []
    if clean_number:
        linked_number = terminal_link(f"N# {clean_number}", numista_url(number))
        details.append(linked_number)
    if denom:
        details.append(denom)
    if category and category not in (coin_type, "Manual / not listed"):
        details.append(category)
    if match_note and match_note not in ("exact mint", "manual"):
        details.append(match_note)
    if details:
        parts.append("(" + " | ".join(details) + ")")
    return " ".join(parts)

def selected_type_option(session, year, mint_index, coin_type_index):
    options = get_detected_type_options(session, year, MINTS[mint_index])
    if not options:
        return {"coin_type": "OTHER", "numista_number": "", "numista_title": "OTHER", "numista_category": "Manual / not listed"}
    coin_type_index = max(0, min(int(coin_type_index or 0), len(options) - 1))
    return options[coin_type_index]

def coin_exists_in_numista(numista_index, session, year, mint_name):
    country = session.get("country", "").strip()
    face_value = normalize_decimal(session.get("face_value", ""))
    if not country or not face_value or not year:
        return True
    candidates = coin_mint_candidates(mint_name)
    return any((country, face_value, str(year).strip(), mint) in numista_index for mint in candidates)

def choose_country_and_denom(numista_countries, denoms_by_country, current_country=None):
    """Choose or add a country/denomination for the active sorting session.

    The picker combines denominations from Numista CSV exports with custom
    denominations saved in settings.json. This lets a user stay in the same
    session when a foreign coin appears in a roll, even if that country or
    denomination does not exist in their Numista export yet.
    """
    numista_countries = list(numista_countries or [])
    denoms_by_country = denoms_by_country or {}
    custom_map = custom_denoms_by_country()
    cache_map = cache_denoms_by_country()

    country_set = set(numista_countries)
    country_set.update(cache_map.keys())
    country_set.update(custom_map.keys())
    country_options = sorted(country_set, key=lambda value: value.lower())

    if current_country in country_options:
        country_options.remove(current_country)
        country_options.insert(0, current_country)

    add_country_option = "Add country / denomination from Numista N#"
    manual_country_option = "Add custom country / denomination manually"
    country_options.append(add_country_option)
    country_options.append(manual_country_option)

    country = choose_from_list(
        "Select country for this coin:\n\n"
        "Numista CSV countries and learned API countries are shown together.\n"
        "If the country/denomination is missing, choose Add country / denomination from Numista N#.",
        country_options,
    )
    if not country:
        return None

    if country == add_country_option:
        return prompt_numista_country_denom_from_api()
    if country == manual_country_option:
        return prompt_custom_country_denom()

    denom_set = set(denoms_by_country.get(country, []))
    denom_set.update(cache_map.get(country, set()))
    denom_set.update(custom_map.get(country, set()))
    denom_options = sorted(
        denom_set,
        key=lambda label: (
            split_denom_label(label)[1].lower(),
            face_value_float_for_sort(split_denom_label(label)[0]),
            split_denom_label(label)[0],
        )
    )

    add_denom_option = f"Add denomination from Numista N# for {country}"
    manual_denom_option = f"Add custom denomination manually for {country}"

    if not denom_options:
        add_now = prompt_yes_no(
            f"No denominations found for {country}.",
            "Add one from a Numista N# now?\n\n"
            "This calls the Numista API, pulls the real country/value/currency, "
            "and saves the type to Coin_Types.csv before you enter year/mint."
        )
        if add_now:
            return prompt_numista_country_denom_from_api(country)
        return None

    denom_label = choose_from_list(
        f"Select denomination for {country}:\n\n"
        "If this denomination is missing, choose Add denomination from Numista N#.",
        denom_options + [add_denom_option, manual_denom_option],
    )
    if not denom_label:
        return None

    if denom_label == add_denom_option:
        return prompt_numista_country_denom_from_api(country)
    if denom_label == manual_denom_option:
        return prompt_custom_country_denom(country)

    custom_choice = find_custom_denom(country, denom_label)
    if custom_choice:
        return custom_choice

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

def session_meta_path(csv_path):
    return os.path.splitext(csv_path)[0] + ".session.json"

def load_session_meta(csv_path):
    path = session_meta_path(csv_path)
    if not os.path.exists(path):
        return {"session_name": "", "session_notes": ""}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "session_name": str(data.get("session_name", "")),
            "session_notes": str(data.get("session_notes", "")),
        }
    except Exception:
        return {"session_name": "", "session_notes": ""}

def save_session_meta(session):
    csv_path = session.get("path", "")
    if not csv_path:
        return
    data = {
        "session_name": session.get("session_name", ""),
        "session_notes": session.get("session_notes", ""),
        "updated": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        with open(session_meta_path(csv_path), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def edit_session_notes(session):
    current = session.get("session_notes", "")
    updated = text_input("Edit session notes. Examples: where coins came from, what you paid, cool finds:", current)
    if updated is None:
        return False
    session["session_notes"] = updated
    save_session_meta(session)
    clear()
    print(green("Session notes saved."))
    print()
    print("Press any key to continue.")
    read_key()
    return True

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


def confirm_session_type(session_type):
    if session_type not in ("Bulk sorting", "Coin roll hunt"):
        return True
    detail = (
        "This mode is for quickly adding year + mint mark entries."
        if session_type == "Bulk sorting"
        else "This mode is for coin roll hunting with optional roll tracking."
    )
    return bool(prompt_yes_no(f"Start {session_type}?", detail))

def choose_crh_roll_mode(coin_choice):
    mode = choose_from_list(
        "Coin Roll Hunt roll tracking mode:",
        ["Automatic roll tracking", "Manual next-roll selection", "No roll tracking"]
    )
    if not mode:
        return None, None
    if mode == "No roll tracking":
        return "none", ""

    qty = get_roll_quantity_for_choice(coin_choice)
    if not qty:
        add_now = prompt_yes_no(
            "No roll quantity saved for this denomination.",
            "Automatic tracking needs coins-per-roll. Add it to settings now?"
        )
        if add_now:
            key_name = roll_quantity_key(coin_choice["country"], coin_choice["face_value"], coin_choice["currency"])
            qty = prompt_positive_int(f"Coins per roll for {coin_choice['country']} | {coin_choice['denomination']}:")
            if qty is None:
                return None, None
            ROLL_QUANTITIES[key_name] = qty
            save_settings()
        elif mode == "Automatic roll tracking":
            return None, None

    if mode == "Automatic roll tracking":
        return "automatic", get_roll_quantity_for_choice(coin_choice)
    return "manual", get_roll_quantity_for_choice(coin_choice) or ""

def new_session(numista_countries, denoms_by_country):
    session_name = text_input("Enter new session name:")
    if not session_name:
        return None

    session_notes = text_input("Enter session notes, optional. Example: where the coins came from, what you paid, cool finds:")
    if session_notes is None:
        session_notes = ""

    session_type = choose_from_list("Select session type:", SESSION_TYPES)
    if not session_type:
        return None
    if not confirm_session_type(session_type):
        return None

    coin_choice = choose_country_and_denom(numista_countries, denoms_by_country)
    if not coin_choice:
        return None

    roll_mode = ""
    roll_quantity = ""
    current_roll = 1
    current_roll_count = 0
    if session_type == "Coin roll hunt":
        roll_mode, roll_quantity = choose_crh_roll_mode(coin_choice)
        if roll_mode is None:
            return None

    path = session_path(session_name)
    if os.path.exists(path):
        choice = choose_from_list(
            "A session with this name already exists. What do you want to do?",
            ["Resume existing session", "Overwrite and start fresh", "Cancel"]
        )
        if choice == "Resume existing session":
            log = load_session_csv(path)
            current_roll, current_roll_count = infer_roll_state(log, roll_quantity)
        elif choice == "Overwrite and start fresh":
            log = []
            write_session_csv(path, log)
        else:
            return None
    else:
        log = []
        write_session_csv(path, log)

    session_obj = {
        "session_name": session_name,
        "session_type": session_type,
        "country": coin_choice["country"],
        "denomination": coin_choice["denomination"],
        "currency": coin_choice["currency"],
        "face_value": coin_choice["face_value"],
        "path": path,
        "log": log,
        "session_notes": session_notes,
        "roll_mode": roll_mode,
        "roll_quantity": roll_quantity,
        "current_roll": current_roll,
        "current_roll_count": current_roll_count,
    }
    save_session_meta(session_obj)
    return session_obj

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


def infer_roll_state(log, roll_quantity=""):
    """Return next current roll and count within roll from saved CRH rows."""
    if not log:
        return 1, 0
    last = log[-1]
    try:
        roll = int(last.get("roll_number") or 1)
    except ValueError:
        roll = 1
    try:
        count = int(last.get("roll_coin_number") or 0)
    except ValueError:
        count = 0
    try:
        qty = int(roll_quantity or last.get("roll_quantity") or 0)
    except ValueError:
        qty = 0
    if qty and count >= qty:
        return roll + 1, 0
    return max(1, roll), max(0, count)

def resume_session(numista_countries, denoms_by_country):
    selected_file = choose_session_file_for_resume()
    if not selected_file:
        return None

    path = os.path.join(SESSIONS_DIR, selected_file)
    log = load_session_csv(path)
    meta = load_session_meta(path)

    if log:
        first = log[0]
        session_name = meta.get("session_name") or first.get("session_name", selected_file.replace(".csv", ""))
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
        session_name = meta.get("session_name") or selected_file.replace(".csv", "")
        session_type = "Unknown"
        coin_choice = choose_country_and_denom(numista_countries, denoms_by_country)
        if not coin_choice:
            return None
        country = coin_choice["country"]
        denomination = coin_choice["denomination"]
        currency = coin_choice["currency"]
        face_value = coin_choice["face_value"]

    roll_mode = first.get("roll_mode", "") if log else ""
    roll_quantity = first.get("roll_quantity", "") if log else ""
    current_roll, current_roll_count = infer_roll_state(log, roll_quantity)

    return {"session_name": session_name, "session_type": session_type, "country": country, "denomination": denomination, "currency": currency, "face_value": face_value, "path": path, "log": log, "session_notes": meta.get("session_notes", ""), "roll_mode": roll_mode, "roll_quantity": roll_quantity, "current_roll": current_roll, "current_roll_count": current_roll_count}

def session_menu():
    ensure_sessions_dir()
    ensure_numista_dir()
    numista_index, numista_files, numista_countries, denoms_by_country, numista_type_index = load_numista_index()
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
                session["numista_type_index"] = numista_type_index
                return session
        elif choice == "Resume session":
            session = resume_session(numista_countries, denoms_by_country)
            if session:
                session["numista_index"] = numista_index
                session["numista_csv_count"] = len(numista_files)
                session["numista_coin_count"] = len(numista_index)
                session["numista_countries"] = numista_countries
                session["denoms_by_country"] = denoms_by_country
                session["numista_type_index"] = numista_type_index
                return session
        elif choice == "Statistics":
            home_statistics_menu()
        elif choice == "Export Data":
            export_menu()
        elif choice == "Settings":
            settings_menu(numista_countries, denoms_by_country)
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

def coin_type_label(row):
    year = str(row.get("year", "")).strip() or "????"
    mint = str(row.get("mint", "")).strip() or "?"
    coin_type = str(row.get("coin_type", "")).strip() or "Unknown type"
    numista_number = str(row.get("numista_number", "")).strip()
    denom = str(row.get("denomination", "")).strip() or "Unknown denomination"
    country = str(row.get("country", "")).strip() or "Unknown country"
    number_text = f" | {numista_number}" if numista_number else ""
    return f"{year}-{mint} | {coin_type}{number_text} | {denom} | {country}"

def make_coin(session_name, session_type, country, denom, currency, face_value, year, mint_index, coin_type_option, notes, reject, reject_reason, keep_bulk, numista_found="", possible_missing_collection="", new_collection=False, roll_mode="", roll_number="", roll_coin_number="", roll_quantity=""):
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
        "coin_type": coin_type_option.get("coin_type", ""),
        "numista_number": coin_type_option.get("numista_number", ""),
        "numista_title": coin_type_option.get("numista_title", ""),
        "numista_category": coin_type_option.get("numista_category", ""),
        "notes": notes,
        "reject": str(bool(reject)),
        "reject_reason": reject_reason if reject else "",
        "keep_bulk": str(bool(keep_bulk)),
        "numista_found": str(numista_found),
        "possible_missing_collection": str(possible_missing_collection),
        "new_collection": str(boolish(new_collection) if isinstance(new_collection, str) else bool(new_collection)),
        "roll_mode": roll_mode,
        "roll_number": str(roll_number),
        "roll_coin_number": str(roll_coin_number),
        "roll_quantity": str(roll_quantity),
    }

def reset_coin():
    return "", 0, 0, "", False, "", False, "year"

def boolish(value):
    return str(value).lower() in ["true", "1", "yes"]

def current_year():
    return datetime.now().year

def get_year_range_for_session(session):
    """Return a practical valid range for the active coin type."""
    country = str(session.get("country", "")).lower()
    denom = str(session.get("denomination", "")).lower()
    max_year = current_year() + 1

    if "united states" in country and ("1 cent" in denom or "0.01" in denom):
        return 1793, max_year
    if "united states" in country:
        return 1792, max_year
    return 1600, max_year

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

def can_type_year_digit(session, current_text, digit):
    """Block impossible future years while typing.

    Allows partial years, but blocks the 4th digit if it would make the year
    greater than current year + 1.
    """
    if not digit.isdigit():
        return False

    if len(current_text) >= 4:
        return True  # starts a fresh year, same behavior as before

    candidate = current_text + digit

    if len(candidate) < 4:
        return True

    _, high = get_year_range_for_session(session)
    return int(candidate) <= high

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

def next_focus(focus, direction=1):
    i = FOCUS_ORDER.index(focus)
    return FOCUS_ORDER[(i + direction) % len(FOCUS_ORDER)]



def prompt_manual_roll_overflow(session, next_coin_number, roll_quantity):
    """Manual CRH overflow guard.

    Returns:
      "extra"     -> save this coin in the current roll even though it exceeds the roll quantity
      "next_roll" -> advance to the next roll and save this coin as coin #1 there
      None        -> cancel save and return to entry
    """
    selection = 0
    options = [
        ("extra", "Confirm extra coin in current roll"),
        ("next_roll", "Start next roll and add this coin there"),
        ("cancel", "Cancel and return to entry"),
    ]

    while True:
        clear()
        current_roll = int(session.get("current_roll", 1) or 1)
        print(c("=" * 100, "93"))
        print(bold(yellow("MANUAL CRH ROLL LIMIT REACHED".center(100))))
        print(c("=" * 100, "93"))
        print()
        print(bold("Current roll:"), green(str(current_roll)))
        print(bold("Saved coins in this roll:"), green(str(session.get("current_roll_count", 0))))
        print(bold("Expected coins per roll:"), cyan(str(roll_quantity)))
        print()
        print(yellow(f"Saving this coin would make roll {current_roll} contain {next_coin_number} coins."))
        print(dim("Choose whether this is an intentional extra coin, or whether this coin should begin the next roll."))
        print()

        for i, (_, label) in enumerate(options):
            prefix = "> " if i == selection else "  "
            line = prefix + label
            print(reverse(line) if i == selection else line)

        print()
        print(dim("TAB/DOWN/+ next | UP/- previous | ENTER confirm | BACKSPACE/ESC cancel"))
        key = read_key()
        if key in (KEY_BACKSPACE, KEY_ESC):
            return None
        if key in (KEY_TAB, KEY_DOWN, "+", "="):
            selection = (selection + 1) % len(options)
            continue
        if key in (KEY_SHIFT_TAB, KEY_UP, "-", "_"):
            selection = (selection - 1) % len(options)
            continue
        if key == KEY_ENTER:
            value = options[selection][0]
            return None if value == "cancel" else value

def save_current_coin(session, year, mint_index, coin_type_index, notes, reject, reject_reason, keep_bulk, editing_index, numista_index=None):
    if not (len(year) == 4 and year.isdigit()):
        return False, editing_index

    mint_name = MINTS[mint_index]
    coin_type_option = selected_type_option(session, year, mint_index, coin_type_index)
    if coin_type_option.get("coin_type") == "OTHER":
        manual_option, other_note = prompt_manual_coin_type(session, year, mint_name, notes)
        if not manual_option:
            return False, editing_index
        coin_type_option = manual_option
        if not str(notes).strip():
            notes = other_note

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

    roll_mode = session.get("roll_mode", "")
    roll_number = ""
    roll_coin_number = ""
    roll_quantity = session.get("roll_quantity", "") or ""
    manual_overflow_action = None

    if session.get("session_type") == "Coin roll hunt" and roll_mode in ("automatic", "manual") and editing_index is None:
        roll_number = int(session.get("current_roll", 1) or 1)
        roll_coin_number = int(session.get("current_roll_count", 0) or 0) + 1

        # In manual CRH mode, do not silently overfill a roll. If the user
        # enters coin #51 in a 50-coin roll, they can either confirm the extra
        # coin in the current roll or move that coin into the next roll as #1.
        if roll_mode == "manual":
            try:
                qty = int(roll_quantity or 0)
            except ValueError:
                qty = 0
            if qty and roll_coin_number > qty:
                manual_overflow_action = prompt_manual_roll_overflow(session, roll_coin_number, qty)
                if manual_overflow_action is None:
                    return False, editing_index
                if manual_overflow_action == "next_roll":
                    roll_number += 1
                    roll_coin_number = 1

    coin = make_coin(
        session["session_name"], session["session_type"], session.get("country", ""), session["denomination"], session.get("currency", ""), session.get("face_value", ""),
        year, mint_index, coin_type_option, notes, reject, reject_reason, keep_bulk, numista_found, possible_missing, new_collection,
        roll_mode, roll_number, roll_coin_number, roll_quantity
    )

    if editing_index is not None:
        session["log"][editing_index] = coin
        editing_index = None
    else:
        session["log"].append(coin)
        if session.get("session_type") == "Coin roll hunt" and session.get("roll_mode") in ("automatic", "manual"):
            session["current_roll"] = int(roll_number or session.get("current_roll", 1) or 1)
            session["current_roll_count"] = int(roll_coin_number or 0)
            if session.get("roll_mode") == "automatic":
                try:
                    qty = int(session.get("roll_quantity") or 0)
                except ValueError:
                    qty = 0
                if qty and session["current_roll_count"] >= qty:
                    session["current_roll"] = int(session.get("current_roll", 1) or 1) + 1
                    session["current_roll_count"] = 0

    write_session_csv(session["path"], session["log"])
    save_session_meta(session)
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

def draw(session, year, mint_index, coin_type_index, notes, reject, reject_reason, keep_bulk, selected_index, focus, editing_index):
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
    if session.get("session_notes"):
        print(f"{bold('Session Notes:')} {session.get('session_notes')}")
    print(f"{bold('Country:')} {session.get('country', 'Unknown')}    {bold('Denomination:')} {session['denomination']}")
    print(f"{bold('File:')} {session['path']}")
    if session.get("numista_csv_count", 0):
        type_count = sum(len(bucket) for bucket in (session.get("numista_type_index", {}) or {}).values())
        print(f"{bold('Numista CSVs:')} {session.get('numista_csv_count')} loaded from {NUMISTA_DIR} | {session.get('numista_coin_count', 0)} owned entries | {type_count} cached type rows")
    else:
        print(yellow(f"Numista CSVs: none loaded from {NUMISTA_DIR}"))
        print(dim(f"Coin type cache: {COIN_TYPES_PATH}"))

    total_sorted, today_sorted = session_counts(log)
    print(f"{bold('Sorted in this CSV:')} {green(str(total_sorted))} total    {bold('Today:')} {green(str(today_sorted))}")
    if session.get("session_type") == "Coin roll hunt":
        roll_mode = session.get("roll_mode") or "none"
        if roll_mode in ("automatic", "manual"):
            qty = session.get("roll_quantity") or "?"
            print(f"{bold('CRH Roll Tracking:')} {cyan(roll_mode)}    {bold('Current roll:')} {green(str(session.get('current_roll', 1)))}    {bold('Coins in roll:')} {green(str(session.get('current_roll_count', 0)))}/{qty}")
        else:
            print(f"{bold('CRH Roll Tracking:')} {dim('off')}")
    print()
    print(cyan("Flow:"), "Year → Mint → ENTER saves/adds coin  |  numpad . cycles Type  |  TAB moves selection")
    print(cyan("Controls:"), f"TAB = move   ENTER = select/save   + / - = mint   {key_display(HOTKEYS['type_next'])} = type   {key_display(HOTKEYS['reject'])} = REJECT   {key_display(HOTKEYS['keep_bulk'])} = KEEP/BULK")
    print(dim(f"Year is checked live. Max allowed year: {current_year() + 1}."))    
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
    type_options = get_detected_type_options(session, year, MINTS[mint_index])
    if coin_type_index >= len(type_options):
        coin_type_index = 0
    coin_type_value = bold(cyan(type_option_label(type_options[coin_type_index])))
    if len(type_options) > 1:
        coin_type_value += dim(f"  [{coin_type_index + 1}/{len(type_options)}]")
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
    box_line("Type", coin_type_value, "coin_type", "numpad . changes type; Numista links are clickable in supported terminals")
    box_line("Save Coin", green("manual save if you tab here"), "save", "")
    box_line("Notes", notes_value, "notes", "required if Type is OTHER")

    print(f"{bold('  Reject')}        {reject_value}      {dim('hotkey only; asks reason when turned on')}")
    print(f"{bold('  Keep/Bulk')}  {keep_value}      {dim('hotkey only: *')}")
    print()
    print(f"{(reverse(' Recent/Edit ') if focus == 'recent' else bold(' Recent/Edit '))} {dim('ENTER opens full previous-coin edit list')}")
    print(f"{(reverse(' Change Country/Denom ') if focus == 'change_denom' else bold(' Change Country/Denom '))} {dim('ENTER changes/adds active sorting selection')}")
    print(f"{(reverse(' Edit Session Notes ') if focus == 'session_notes' else bold(' Edit Session Notes '))} {dim('ENTER edits title-level notes for this session')}")
    if session.get("session_type") == "Coin roll hunt" and session.get("roll_mode") == "manual":
        print(f"{(reverse(' Next Roll ') if focus == 'next_roll' else bold(' Next Roll '))} {dim('ENTER starts the next roll manually')}")
    print(f"{(reverse(' Statistics ') if focus == 'statistics' else bold(' Statistics '))} {dim('ENTER opens session statistics page')}")
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
        print(f"{marker}{global_index + 1}. {coin.get('year', '')}-{coin.get('mint', '')} | {coin.get('coin_type', 'Unknown type')} | {coin.get('denomination', '')} | {coin.get('notes', '')}{flag_text}")

    print()
    print(c("-" * 110, "94"))
    print(bold("Current selection help:"))
    if focus == "year":
        print("Type the year. You can TAB to menus anytime, but the coin will not save unless the year is exactly 4 digits.")
    elif focus == "mint":
        print("Use + or - to choose the mint. ENTER saves the coin. Use numpad . anytime to change Type.")
    elif focus == "coin_type":
        print("Use numpad . to choose the detected Numista type. ENTER saves. Choose OTHER only when it is not listed; notes are required for OTHER.")
    elif focus == "save":
        print("Press ENTER to save this coin and start the next coin. This is the manual save step if you tabbed past Mint.")
    elif focus == "notes":
        print("Type notes if needed. ENTER saves this coin and starts the next coin.")
    elif focus == "recent":
        print("Press ENTER to open the full previous-coin edit list. TAB only moves selection.")
    elif focus == "change_denom":
        print("Press ENTER to choose a country/denomination, or add one from a Numista N# without placeholders.")
    elif focus == "session_notes":
        print("Press ENTER to edit session-level notes, such as cool finds, where coins came from, or what you paid.")
    elif focus == "next_roll":
        if session.get("session_type") == "Coin roll hunt" and session.get("roll_mode") == "manual":
            print("Press ENTER when you are ready to start the next roll.")
        else:
            print("Next Roll is only active for manual Coin Roll Hunt sessions.")
    elif focus == "statistics":
        print("Press ENTER to open a separate statistics page for this session CSV.")
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
    if choice.get("_numista_type_index"):
        session["numista_type_index"] = choice["_numista_type_index"]
        # Refresh picker data so the API-added denomination appears later without restart.
        try:
            numista_index, numista_files, numista_countries, denoms_by_country, numista_type_index = load_numista_index()
            session["numista_index"] = numista_index
            session["numista_csv_count"] = len(numista_files)
            session["numista_coin_count"] = len(numista_index)
            session["numista_countries"] = numista_countries
            session["denoms_by_country"] = denoms_by_country
            session["numista_type_index"] = numista_type_index
        except Exception:
            pass
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
            f"{coin.get('coin_type', 'Unknown type')} | {coin.get('denomination', '')} | {coin.get('notes', '')}{flag_text}"
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
            save_session_meta(session)
            return True
        if key in (KEY_BACKSPACE, KEY_ESC):
            return False


def advance_manual_roll(session):
    if session.get("session_type") != "Coin roll hunt" or session.get("roll_mode") != "manual":
        return False
    session["current_roll"] = int(session.get("current_roll", 1) or 1) + 1
    session["current_roll_count"] = 0
    clear()
    print(c("=" * 90, "92"))
    print(bold(green("NEXT ROLL STARTED".center(90))))
    print(c("=" * 90, "92"))
    print()
    print(f"Current roll: {green(str(session['current_roll']))}")
    print()
    print("Press any key to continue.")
    read_key()
    return True

def sorting_loop(session):
    numista_index = session.get("numista_index")
    if numista_index is None:
        numista_index, numista_files, numista_countries, denoms_by_country, numista_type_index = load_numista_index()
        session["numista_index"] = numista_index
        session["numista_csv_count"] = len(numista_files)
        session["numista_coin_count"] = len(numista_index)
        session["numista_countries"] = numista_countries
        session["denoms_by_country"] = denoms_by_country
        session["numista_type_index"] = numista_type_index
    year, mint_index, coin_type_index, notes, reject, reject_reason, keep_bulk, focus = reset_coin()
    selected_index = -1
    editing_index = None
    return_to_recent_after_edit = False

    def load_index_for_edit(index, return_to_recent=False):
        nonlocal year, mint_index, coin_type_index, notes, reject, reject_reason, keep_bulk, editing_index, focus, selected_index, return_to_recent_after_edit
        if index is None or not (0 <= index < len(session["log"])):
            return
        selected_index = index
        coin = session["log"][index]
        year = coin.get("year", "")
        notes = coin.get("notes", "")
        mint_value = coin.get("mint", "P")
        mint_index = MINTS.index(mint_value) if mint_value in MINTS else 0
        type_options = get_detected_type_options(session, year, mint_value)
        saved_type = coin.get("coin_type", "")
        saved_number = coin.get("numista_number", "")
        coin_type_index = 0
        for pos, option in enumerate(type_options):
            if option.get("coin_type") == saved_type and option.get("numista_number") == saved_number:
                coin_type_index = pos
                break
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
        nonlocal year, mint_index, coin_type_index, notes, reject, reject_reason, keep_bulk, focus, editing_index, selected_index, return_to_recent_after_edit
        was_editing_index = editing_index
        should_return_to_recent = return_to_recent_after_edit and was_editing_index is not None
        saved, editing_index = save_current_coin(session, year, mint_index, coin_type_index, notes, reject, reject_reason, keep_bulk, editing_index, numista_index)
        if saved:
            year, mint_index, coin_type_index, notes, reject, reject_reason, keep_bulk, focus = reset_coin()
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
        draw(session, year, mint_index, coin_type_index, notes, reject, reject_reason, keep_bulk, selected_index, focus, editing_index)
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

        # Numpad . cycles coin type from anywhere so ENTER can stay as Mint confirm/save.
        if hotkey_matches(key, "type_next"):
            options = get_detected_type_options(session, year, MINTS[mint_index])
            coin_type_index = (coin_type_index + 1) % len(options)
            focus = "coin_type"
            continue

        # + / - changes mint.
        if hotkey_matches(key, "mint_next"):
            mint_index = (mint_index + 1) % len(MINTS)
            coin_type_index = 0
            focus = "mint"
            continue
        if hotkey_matches(key, "mint_previous"):
            mint_index = (mint_index - 1) % len(MINTS)
            coin_type_index = 0
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
            elif focus == "coin_type":
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
                if change_current_country_denom(session):
                    coin_type_index = 0
                focus = "year"
            elif focus == "session_notes":
                edit_session_notes(session)
                focus = "year"
            elif focus == "next_roll":
                advance_manual_roll(session)
                focus = "year"
            elif focus == "statistics":
                statistics_menu(session)
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

        if focus == "year" and key.isdigit():
            if can_type_year_digit(session, year, key):
                if len(year) >= 4:
                    year = key
                else:
                    year += key
                coin_type_index = 0
            continue

        if focus == "notes" and isinstance(key, str) and len(key) == 1 and key.isprintable():
            notes += key
            continue

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
