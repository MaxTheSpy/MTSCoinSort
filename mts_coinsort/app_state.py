# Shared application state for the split MTS CoinSort modules.
from .common import *

MINTS = ["No Mint", "P", "D", "S", "W"]
SESSION_TYPES = ["Bulk sorting", "Coin roll hunt", "Other"]

APP_NAME = "MTS CoinSort"
APP_SLUG = "mts-coinsort"

def _default_config_dir():
    if os.name == "nt":
        root = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return os.path.join(root, APP_NAME)
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", APP_NAME)
    root = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(root, APP_SLUG)

def _default_data_dir():
    if os.name == "nt":
        root = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        return os.path.join(root, APP_NAME)
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", APP_NAME)
    root = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(root, APP_SLUG)

def _clean_user_path(path):
    return os.path.abspath(os.path.expandvars(os.path.expanduser(str(path).strip())))

CONFIG_DIR = _default_config_dir()
SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.json")
DATA_DIR = _default_data_dir()
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

BASE_FOCUS_ORDER = [
    "year",
    "mint",
    "coin_type",
    "save",
    "notes",
    "recent",
    "change_denom",
    "session_notes",
    "statistics",
    "quit",
]
CRH_MANUAL_EXTRA_FOCUS = ["next_roll"]

USE_COLOR = True
BIG_UI = True
COIN_SAVE_SOUND = True
COIN_SAVE_SOUND_MODE = "default"
COIN_SAVE_SOUND_FILE = ""
ROLL_QUANTITIES = {}
CUSTOM_DENOMINATIONS = []
NUMISTA_CLIENT_ID = ""
NUMISTA_API_KEY = ""

DEFAULT_NUMISTA_API_USAGE = {
    "month": "",
    "max_monthly_calls": 2000,
    "warn_percent": 85,
    "api_calls_this_month": 0,
    "successful_calls_this_month": 0,
    "failed_calls_this_month": 0,
    "cache_hits_this_month": 0,
    "api_calls_lifetime": 0,
    "cache_hits_lifetime": 0,
    "last_api_call": "",
    "last_cache_hit": "",
}
NUMISTA_API_USAGE = DEFAULT_NUMISTA_API_USAGE.copy()
ANSI_SUPPORTED = os.name != "nt"
_SCREEN_BUFFER = None
