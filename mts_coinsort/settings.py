# Auto-split from MTS CoinSort V0.2.0.
# Keep behavior changes small in this refactor; modules are wired together at startup.
from .common import *
from . import app_state as state


def default_config_dir():
    """Return the OS-standard folder where settings.json should live.

    Keep settings outside the movable data folder so the app can always find
    the user's chosen data_dir on startup.
    """
    if os.name == 'nt':
        root = os.environ.get('APPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming')
        return os.path.join(root, state.APP_NAME)
    if sys.platform == 'darwin':
        return os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', state.APP_NAME)
    root = os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')
    return os.path.join(root, state.APP_SLUG)



def default_data_dir():
    """Return the OS-standard folder where sessions/exports/Numista CSV live."""
    if os.name == 'nt':
        root = os.environ.get('APPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming')
        return os.path.join(root, state.APP_NAME)
    if sys.platform == 'darwin':
        return os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', state.APP_NAME)
    root = os.environ.get('XDG_DATA_HOME') or os.path.join(os.path.expanduser('~'), '.local', 'share')
    return os.path.join(root, state.APP_SLUG)



def key_display(key):
    names = {state.KEY_ENTER: 'ENTER', state.KEY_BACKSPACE: 'BACKSPACE', state.KEY_DELETE: 'DELETE', state.KEY_ESC: 'ESC', state.KEY_TAB: 'TAB', state.KEY_SHIFT_TAB: 'SHIFT+TAB', state.KEY_UP: 'UP', state.KEY_DOWN: 'DOWN', state.KEY_LEFT: 'LEFT', state.KEY_RIGHT: 'RIGHT', ' ': 'SPACE'}
    return names.get(key, str(key).upper() if len(str(key)) == 1 else str(key))



def normalize_key_for_compare(key):
    if isinstance(key, str) and len(key) == 1:
        return key.lower()
    return key



def hotkey_matches(key, action):
    return normalize_key_for_compare(key) == normalize_key_for_compare(state.HOTKEYS.get(action, state.DEFAULT_HOTKEYS[action]))



def apply_data_dir(path):
    """Update all user-data folders after loading a custom data_dir."""
    state.DATA_DIR = clean_user_path(path)
    state.SESSIONS_DIR = os.path.join(state.DATA_DIR, 'coin_sort_sessions')
    state.NUMISTA_DIR = os.path.join(state.DATA_DIR, 'Numista CSV')
    state.EXPORTS_DIR = os.path.join(state.DATA_DIR, 'coin_sort_exports')
    state.COIN_TYPES_PATH = os.path.join(state.DATA_DIR, 'Coin_Types.csv')



def ensure_app_dirs():
    os.makedirs(state.CONFIG_DIR, exist_ok=True)
    os.makedirs(state.DATA_DIR, exist_ok=True)
    os.makedirs(state.SESSIONS_DIR, exist_ok=True)
    os.makedirs(state.NUMISTA_DIR, exist_ok=True)
    os.makedirs(state.EXPORTS_DIR, exist_ok=True)



def load_settings():
    state.HOTKEYS = state.DEFAULT_HOTKEYS.copy()
    if not os.path.exists(state.SETTINGS_PATH):
        ensure_app_dirs()
        save_settings()
        return
    try:
        with open(state.SETTINGS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        custom_data_dir = data.get('data_dir', '')
        if isinstance(custom_data_dir, str) and custom_data_dir.strip():
            apply_data_dir(custom_data_dir)
        saved_hotkeys = data.get('hotkeys', {})
        for action in state.DEFAULT_HOTKEYS:
            if action in saved_hotkeys and isinstance(saved_hotkeys[action], str) and saved_hotkeys[action]:
                state.HOTKEYS[action] = saved_hotkeys[action]
        state.USE_COLOR = bool(data.get('use_color', state.USE_COLOR))
        state.BIG_UI = bool(data.get('big_ui', state.BIG_UI))
        sound_settings = data.get('sound', {}) if isinstance(data.get('sound', {}), dict) else {}
        saved_mode = str(sound_settings.get('coin_saved_mode', '') or data.get('coin_save_sound_mode', '') or '').strip().lower()
        saved_file = str(sound_settings.get('coin_saved_file', '') or data.get('coin_save_sound_file', '') or '').strip()
        old_enabled = bool(data.get('coin_save_sound', state.COIN_SAVE_SOUND))
        if saved_mode in ('default', 'custom', 'off'):
            state.COIN_SAVE_SOUND_MODE = saved_mode
            state.COIN_SAVE_SOUND = saved_mode != 'off'
        else:
            state.COIN_SAVE_SOUND = old_enabled
            state.COIN_SAVE_SOUND_MODE = 'default' if old_enabled else 'off'
        state.COIN_SAVE_SOUND_FILE = clean_user_path(saved_file) if saved_file else ''
        state.ROLL_QUANTITIES = normalize_roll_quantities(data.get('roll_quantities', {}))
        state.CUSTOM_DENOMINATIONS = normalize_custom_denominations(data.get('custom_denominations', []))
        numista_api = data.get('numista_api', {}) if isinstance(data.get('numista_api', {}), dict) else {}
        state.NUMISTA_CLIENT_ID = str(numista_api.get('client_id', '') or '')
        state.NUMISTA_API_KEY = str(numista_api.get('api_key', '') or '')
        state.NUMISTA_API_USAGE = normalize_numista_api_usage(numista_api.get('usage', {}))
        ensure_app_dirs()
    except Exception:
        state.HOTKEYS = state.DEFAULT_HOTKEYS.copy()
        state.COIN_SAVE_SOUND = True
        state.COIN_SAVE_SOUND_MODE = 'default'
        state.COIN_SAVE_SOUND_FILE = ''
        state.ROLL_QUANTITIES = {}
        state.CUSTOM_DENOMINATIONS = []
        state.NUMISTA_CLIENT_ID = ''
        state.NUMISTA_API_KEY = ''
        state.NUMISTA_API_USAGE = state.DEFAULT_NUMISTA_API_USAGE.copy()
        ensure_app_dirs()



def save_settings():
    ensure_app_dirs()
    data = {'data_dir': state.DATA_DIR, 'hotkeys': state.HOTKEYS, 'use_color': state.USE_COLOR, 'big_ui': state.BIG_UI, 'coin_save_sound': state.COIN_SAVE_SOUND, 'coin_save_sound_mode': state.COIN_SAVE_SOUND_MODE, 'coin_save_sound_file': state.COIN_SAVE_SOUND_FILE, 'sound': {'coin_saved_mode': state.COIN_SAVE_SOUND_MODE, 'coin_saved_file': state.COIN_SAVE_SOUND_FILE}, 'roll_quantities': state.ROLL_QUANTITIES, 'custom_denominations': state.CUSTOM_DENOMINATIONS, 'numista_api': {'client_id': state.NUMISTA_CLIENT_ID, 'api_key': state.NUMISTA_API_KEY, 'usage': refresh_numista_api_usage_month(state.NUMISTA_API_USAGE)}}
    with open(state.SETTINGS_PATH, 'w', encoding='utf-8') as f:
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
        country = str(item.get('country', '')).strip()
        face_value = normalize_decimal(item.get('face_value', ''))
        currency = str(item.get('currency', '')).strip()
        denomination = str(item.get('denomination', '')).strip() or make_denom_label(face_value, currency)
        if not country or not face_value:
            continue
        key = (country.lower(), face_value, currency.lower(), denomination.lower())
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({'country': country, 'currency': currency, 'face_value': face_value, 'denomination': denomination})
    cleaned.sort(key=lambda item: (item['country'].lower(), item['currency'].lower(), face_value_float_for_sort(item['face_value']), item['denomination'].lower()))
    return cleaned



def custom_denoms_by_country():
    mapping = {}
    for item in state.CUSTOM_DENOMINATIONS:
        country = str(item.get('country', '')).strip()
        label = str(item.get('denomination', '')).strip() or make_denom_label(item.get('face_value', ''), item.get('currency', ''))
        if country and label:
            mapping.setdefault(country, set()).add(label)
    return mapping



def find_custom_denom(country, denom_label):
    for item in state.CUSTOM_DENOMINATIONS:
        if str(item.get('country', '')).strip() == str(country).strip() and str(item.get('denomination', '')).strip() == str(denom_label).strip():
            return {'country': item.get('country', ''), 'denomination': item.get('denomination', ''), 'currency': item.get('currency', ''), 'face_value': normalize_decimal(item.get('face_value', ''))}
    return None



def save_custom_denomination(country, face_value, currency, denomination=''):
    """Save a custom country/denomination and return a session choice dict."""
    country = str(country or '').strip()
    face_value = normalize_decimal(face_value)
    currency = str(currency or '').strip()
    denomination = str(denomination or '').strip() or make_denom_label(face_value, currency)
    if not country or not face_value:
        return None
    new_item = {'country': country, 'currency': currency, 'face_value': face_value, 'denomination': denomination}
    normalized = normalize_custom_denominations(state.CUSTOM_DENOMINATIONS + [new_item])
    if normalized != state.CUSTOM_DENOMINATIONS:
        state.CUSTOM_DENOMINATIONS = normalized
        save_settings()
    return dict(new_item)



def remove_custom_denominations_for_country_face(country, face_value):
    """Remove temporary custom denominations after a Numista API type confirms them.

    A custom denomination is only a placeholder so the user can keep sorting a
    foreign or unexpected coin in the same session. Once the user enters an N#
    and the API saves a real Coin_Types.csv row for that country/face value, the
    placeholder should disappear from future pickers.
    """
    country_key = str(country or '').strip().lower()
    face_key = normalize_decimal(face_value)
    if not country_key or not face_key:
        return False
    kept = []
    removed = False
    for item in state.CUSTOM_DENOMINATIONS:
        item_country = str(item.get('country', '')).strip().lower()
        item_face = normalize_decimal(item.get('face_value', ''))
        if item_country == country_key and item_face == face_key:
            removed = True
            continue
        kept.append(item)
    if removed:
        state.CUSTOM_DENOMINATIONS = normalize_custom_denominations(kept)
        save_settings()
    return removed



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
        parts = str(raw_key).split('|')
        if len(parts) >= 3:
            key = roll_quantity_key(parts[0], parts[1], '|'.join(parts[2:]))
        else:
            key = str(raw_key).strip()
        if key:
            cleaned[key] = qty
    return cleaned



def roll_quantity_key(country, face_value, currency):
    return f'{str(country).strip()}|{normalize_decimal(face_value)}|{str(currency).strip()}'



def roll_quantity_label(key, qty):
    parts = str(key).split('|', 2)
    if len(parts) == 3:
        country, face_value, currency = parts
        denom = make_denom_label(face_value, currency)
        return f'{country} | {denom} = {qty} coins/roll'
    return f'{key} = {qty} coins/roll'



def get_roll_quantity_for_choice(choice):
    key = roll_quantity_key(choice.get('country', ''), choice.get('face_value', ''), choice.get('currency', ''))
    return state.ROLL_QUANTITIES.get(key)



def numista_usage_month_key():
    return datetime.now().strftime('%Y-%m')



def normalize_numista_api_usage(value):
    """Clean the Numista API usage block stored in settings.json."""
    usage = state.DEFAULT_NUMISTA_API_USAGE.copy()
    if isinstance(value, dict):
        for key in usage:
            if key in value:
                usage[key] = value[key]
    usage['max_monthly_calls'] = safe_positive_int(usage.get('max_monthly_calls'), 2000)
    usage['warn_percent'] = min(100, max(1, safe_positive_int(usage.get('warn_percent'), 85)))
    for key in ('api_calls_this_month', 'successful_calls_this_month', 'failed_calls_this_month', 'cache_hits_this_month', 'api_calls_lifetime', 'cache_hits_lifetime'):
        usage[key] = safe_positive_int(usage.get(key), 0)
    usage['month'] = str(usage.get('month', '') or '')
    usage['last_api_call'] = str(usage.get('last_api_call', '') or '')
    usage['last_cache_hit'] = str(usage.get('last_cache_hit', '') or '')
    return refresh_numista_api_usage_month(usage, save=False)



def refresh_numista_api_usage_month(usage=None, save=False):
    """Reset monthly counters when the calendar month changes."""
    usage = normalize_numista_api_usage_no_refresh(usage or state.NUMISTA_API_USAGE)
    month = numista_usage_month_key()
    if usage.get('month') != month:
        usage['month'] = month
        usage['api_calls_this_month'] = 0
        usage['successful_calls_this_month'] = 0
        usage['failed_calls_this_month'] = 0
        usage['cache_hits_this_month'] = 0
        usage['last_api_call'] = ''
        usage['last_cache_hit'] = ''
    state.NUMISTA_API_USAGE = usage
    if save:
        save_settings()
    return usage



def normalize_numista_api_usage_no_refresh(value):
    usage = state.DEFAULT_NUMISTA_API_USAGE.copy()
    if isinstance(value, dict):
        for key in usage:
            if key in value:
                usage[key] = value[key]
    usage['max_monthly_calls'] = safe_positive_int(usage.get('max_monthly_calls'), 2000)
    usage['warn_percent'] = min(100, max(1, safe_positive_int(usage.get('warn_percent'), 85)))
    for key in ('api_calls_this_month', 'successful_calls_this_month', 'failed_calls_this_month', 'cache_hits_this_month', 'api_calls_lifetime', 'cache_hits_lifetime'):
        usage[key] = safe_positive_int(usage.get(key), 0)
    usage['month'] = str(usage.get('month', '') or '')
    usage['last_api_call'] = str(usage.get('last_api_call', '') or '')
    usage['last_cache_hit'] = str(usage.get('last_cache_hit', '') or '')
    return usage



def set_numista_monthly_call_limit():
    usage = refresh_numista_api_usage_month(state.NUMISTA_API_USAGE)
    current = usage.get('max_monthly_calls', 2000)
    value = prompt_positive_int('Maximum Numista API calls you are willing to spend per calendar month:\n\nRecommended: 2000 or lower if that is your monthly Numista quota.\nThe app will block API lookups after this number is reached.', current)
    if value is not None:
        usage['max_monthly_calls'] = value
        state.NUMISTA_API_USAGE = usage
        save_settings()



def set_numista_warning_percent():
    usage = refresh_numista_api_usage_month(state.NUMISTA_API_USAGE)
    while True:
        value = text_input('Warn when monthly Numista API usage reaches what percent of your limit?\n\nExample: 85 means warn after 85% of your monthly max is used.', str(usage.get('warn_percent', 85)))
        if value is None:
            return
        try:
            percent = int(float(value))
        except ValueError:
            percent = 0
        if 1 <= percent <= 100:
            usage['warn_percent'] = percent
            state.NUMISTA_API_USAGE = usage
            save_settings()
            return
        clear()
        print(red('Please enter a number from 1 to 100.'))
        print('Press any key to try again.')
        read_key()



def reset_numista_monthly_usage():
    usage = refresh_numista_api_usage_month(state.NUMISTA_API_USAGE)
    if prompt_yes_no("Reset this month's Numista API usage counters?", "This only resets the local app counters in settings.json. It does not reset Numista's real quota."):
        usage['api_calls_this_month'] = 0
        usage['successful_calls_this_month'] = 0
        usage['failed_calls_this_month'] = 0
        usage['cache_hits_this_month'] = 0
        usage['last_api_call'] = ''
        usage['last_cache_hit'] = ''
        state.NUMISTA_API_USAGE = usage
        save_settings()



def log_numista_cache_hit(numista_number=''):
    usage = refresh_numista_api_usage_month(state.NUMISTA_API_USAGE)
    usage['cache_hits_this_month'] = usage.get('cache_hits_this_month', 0) + 1
    usage['cache_hits_lifetime'] = usage.get('cache_hits_lifetime', 0) + 1
    usage['last_cache_hit'] = datetime.now().isoformat(timespec='seconds')
    state.NUMISTA_API_USAGE = usage
    save_settings()



def log_numista_api_call(numista_number='', success=False):
    usage = refresh_numista_api_usage_month(state.NUMISTA_API_USAGE)
    usage['api_calls_this_month'] = usage.get('api_calls_this_month', 0) + 1
    usage['api_calls_lifetime'] = usage.get('api_calls_lifetime', 0) + 1
    if success:
        usage['successful_calls_this_month'] = usage.get('successful_calls_this_month', 0) + 1
    else:
        usage['failed_calls_this_month'] = usage.get('failed_calls_this_month', 0) + 1
    usage['last_api_call'] = datetime.now().isoformat(timespec='seconds')
    state.NUMISTA_API_USAGE = usage
    save_settings()



def guard_numista_api_call(numista_number=''):
    """Return True when one more Numista API call is allowed by user settings."""
    usage = refresh_numista_api_usage_month(state.NUMISTA_API_USAGE)
    limit = usage.get('max_monthly_calls', 0)
    used = usage.get('api_calls_this_month', 0)
    next_call = used + 1
    if limit <= 0:
        clear()
        print(red('Numista API calls are blocked.'))
        print()
        print('Your monthly max call setting is 0. Increase it in Settings > Numista API settings to allow API lookups.')
        print('Press any key to return.')
        read_key()
        return False
    if used >= limit:
        clear()
        print(red('Numista API monthly max reached.'))
        print()
        print(f"Local counter: {used} / {limit} calls used for {usage.get('month', numista_usage_month_key())}.")
        print('This API lookup was blocked to protect your chosen monthly limit.')
        print()
        print(dim('Use the local cache, raise the monthly max, or reset the local counter if you know it is wrong.'))
        print('Press any key to return.')
        read_key()
        return False
    warn_at = int(limit * usage.get('warn_percent', 85) / 100)
    if next_call >= warn_at:
        return bool(prompt_yes_no('Numista API usage warning.', f"This lookup will use call {next_call} of your {limit} monthly max for {usage.get('month', numista_usage_month_key())}.\n\nContinue with this API call?"))
    return True



def reset_hotkeys_to_default():
    state.HOTKEYS = state.DEFAULT_HOTKEYS.copy()
    save_settings()


