# Auto-split from MTS CoinSort V0.2.0.
# Keep behavior changes small in this refactor; modules are wired together at startup.
from .common import *
from . import app_state as state


def enable_ansi_on_windows():
    """Enable ANSI escape handling in modern Windows terminals when possible.

    Returns True when ANSI control sequences should be safe to use.
    Linux/macOS terminals normally support ANSI already.
    """
    if os.name != 'nt':
        return True
    try:
        os.system('')
    except Exception:
        pass
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        if handle in (0, -1):
            return False
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 4
        new_mode = mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
        if not kernel32.SetConsoleMode(handle, new_mode):
            return False
        return True
    except Exception:
        return False



def configure_terminal_output():
    """Set global terminal capabilities after startup/settings load."""
    state.ANSI_SUPPORTED = enable_ansi_on_windows()
    if not state.ANSI_SUPPORTED:
        state.USE_COLOR = False



def c(text, code):
    if not state.USE_COLOR or not state.ANSI_SUPPORTED:
        return text
    return f'\x1b[{code}m{text}\x1b[0m'



def bold(text):
    return c(text, '1')



def cyan(text):
    return c(text, '96')



def green(text):
    return c(text, '92')



def yellow(text):
    return c(text, '93')



def red(text):
    return c(text, '91')



def dim(text):
    return c(text, '2')



def reverse(text):
    return c(text, '7')



def _flush_screen_buffer():
    """Write a full screen redraw in one terminal update.

    Linux/macOS use ANSI cursor/screen controls for smooth redraws. Windows
    uses ANSI when available, otherwise it falls back to `cls` so PyInstaller
    console builds do not print raw escape codes like ``←[2J``.
    """
    if state._SCREEN_BUFFER is None:
        return
    content = state._SCREEN_BUFFER.getvalue()
    state._SCREEN_BUFFER = None
    if sys.stdout is None:
        return
    if state.ANSI_SUPPORTED:
        sys.stdout.write('\x1b[?25l\x1b[H\x1b[2J')
        sys.stdout.write(content)
        sys.stdout.write('\x1b[?25h')
        sys.stdout.flush()
    else:
        os.system('cls' if os.name == 'nt' else 'clear')
        sys.stdout.write(content)
        sys.stdout.flush()



def print(*args, sep=' ', end='\n', file=None, flush=False):
    """Module-local print that buffers screen redraws after clear()."""
    if file is not None and file is not sys.stdout:
        return builtins.print(*args, sep=sep, end=end, file=file, flush=flush)
    if state._SCREEN_BUFFER is None:
        return builtins.print(*args, sep=sep, end=end, flush=flush)
    state._SCREEN_BUFFER.write(sep.join((str(arg) for arg in args)) + end)
    if flush:
        _flush_screen_buffer()



def clear():
    """Start a buffered redraw instead of blanking the terminal immediately."""
    state._SCREEN_BUFFER = io.StringIO()



def open_app_folders_menu():
    """Settings sub-page for opening data/config folders."""
    index = 0
    menu_items = ['Open data folder', 'Open settings folder', 'Open Numista CSV folder', 'Open sessions folder', 'Open exports folder', 'Back']
    paths = {'Open data folder': state.DATA_DIR, 'Open settings folder': state.CONFIG_DIR, 'Open Numista CSV folder': state.NUMISTA_DIR, 'Open sessions folder': state.SESSIONS_DIR, 'Open exports folder': state.EXPORTS_DIR}
    while True:
        clear()
        print(c('=' * 100, '94'))
        print(bold(cyan('APP FOLDERS'.center(100))))
        print(c('=' * 100, '94'))
        print()
        print(dim('Use these to copy in Numista CSV files, move session files, or find settings.json.'))
        print()
        print(f'Data folder    : {cyan(state.DATA_DIR)}')
        print(f'Settings folder: {cyan(state.CONFIG_DIR)}')
        print(f'Settings file  : {cyan(state.SETTINGS_PATH)}')
        print()
        for i, item in enumerate(menu_items):
            print(reverse(item) if i == index else item)
        print()
        print(dim('TAB/DOWN/+ next | UP/- previous | ENTER open/select | BACKSPACE/ESC back'))
        key = read_key()
        if key in (state.KEY_BACKSPACE, state.KEY_ESC):
            return
        if key in (state.KEY_TAB, state.KEY_DOWN, '+', '='):
            index = (index + 1) % len(menu_items)
            continue
        if key in (state.KEY_SHIFT_TAB, state.KEY_UP, '-', '_'):
            index = (index - 1) % len(menu_items)
            continue
        if key != state.KEY_ENTER:
            continue
        selected = menu_items[index]
        if selected == 'Back':
            return
        ok = open_folder(paths.get(selected, state.DATA_DIR))
        if not ok:
            clear()
            print(red('Could not open that folder automatically.'))
            print()
            print(paths.get(selected, state.DATA_DIR))
            print()
            print('Press any key to continue.')
            read_key()



def sound_settings_menu():
    """Settings sub-page for coin-saved sound behavior."""
    index = 0
    menu_items = ['Set sound mode', 'Set custom sound file path', 'Test coin saved sound', 'Clear custom sound file path', 'Back']
    while True:
        clear()
        print(c('=' * 100, '94'))
        print(bold(cyan('SOUND SETTINGS'.center(100))))
        print(c('=' * 100, '94'))
        print()
        print(dim('Default sound uses no files. Custom file is best as .wav on Windows.'))
        print()
        print(f'Coin saved sound : {cyan(sound_mode_label())}')
        print(f"Custom file path : {cyan(state.COIN_SAVE_SOUND_FILE or '(not set)')}")
        print()
        for i, item in enumerate(menu_items):
            print(reverse(item) if i == index else item)
        print()
        print(dim('TAB/DOWN/+ next | UP/- previous | ENTER select | BACKSPACE/ESC back'))
        key = read_key()
        if key in (state.KEY_BACKSPACE, state.KEY_ESC):
            save_settings()
            return
        if key in (state.KEY_TAB, state.KEY_DOWN, '+', '='):
            index = (index + 1) % len(menu_items)
            continue
        if key in (state.KEY_SHIFT_TAB, state.KEY_UP, '-', '_'):
            index = (index - 1) % len(menu_items)
            continue
        if key != state.KEY_ENTER:
            continue
        selected = menu_items[index]
        if selected == 'Set sound mode':
            current = sound_mode_label()
            choice = choose_from_list('Coin saved sound mode', ['Default built-in beep', 'Custom sound file', 'Off', 'Cancel'])
            if choice == 'Default built-in beep':
                state.COIN_SAVE_SOUND = True
                state.COIN_SAVE_SOUND_MODE = 'default'
                save_settings()
            elif choice == 'Custom sound file':
                state.COIN_SAVE_SOUND = True
                state.COIN_SAVE_SOUND_MODE = 'custom'
                if not state.COIN_SAVE_SOUND_FILE:
                    value = text_input('Enter full path to your custom sound file. WAV is recommended on Windows:')
                    if value is not None:
                        state.COIN_SAVE_SOUND_FILE = clean_user_path(value) if value.strip() else ''
                save_settings()
            elif choice == 'Off':
                state.COIN_SAVE_SOUND = False
                state.COIN_SAVE_SOUND_MODE = 'off'
                save_settings()
        elif selected == 'Set custom sound file path':
            value = text_input('Enter full path to your custom sound file. WAV is recommended on Windows.', state.COIN_SAVE_SOUND_FILE)
            if value is not None:
                state.COIN_SAVE_SOUND_FILE = clean_user_path(value) if value.strip() else ''
                if state.COIN_SAVE_SOUND_FILE:
                    state.COIN_SAVE_SOUND = True
                    state.COIN_SAVE_SOUND_MODE = 'custom'
                save_settings()
        elif selected == 'Test coin saved sound':
            play_coin_saved_sound(force=True)
        elif selected == 'Clear custom sound file path':
            state.COIN_SAVE_SOUND_FILE = ''
            if state.COIN_SAVE_SOUND_MODE == 'custom':
                state.COIN_SAVE_SOUND_MODE = 'default'
                state.COIN_SAVE_SOUND = True
            save_settings()
        elif selected == 'Back':
            save_settings()
            return



def prompt_custom_country_denom(default_country=''):
    """Prompt for a new country/denomination when it is missing from Numista CSV."""
    country = str(default_country or '').strip()
    if not country:
        country = text_input('Enter country name for this coin, for example Canada, Mexico, United Kingdom:')
        if not country:
            return None
    face_value = text_input(f'Enter face value for {country}. Examples: 0.01, 0.05, 0.25, 1.00:')
    if not face_value:
        return None
    currency = text_input(f'Enter currency/denomination family for {country}. Examples: Dollar, Canadian Dollar, Peso, Euro:')
    if currency is None:
        return None
    default_label = make_denom_label(face_value, currency)
    denomination = text_input('Enter display label for the picker, or press ENTER to use this default:', default_label)
    if denomination is None:
        return None
    denomination = denomination or default_label
    choice = save_custom_denomination(country, face_value, currency, denomination)
    if choice:
        clear()
        print(green('Custom country/denomination saved.'))
        print()
        print(f"Now available: {choice['country']} | {choice['denomination']}")
        print()
        print(dim('If no type is listed for the coin, choose OTHER, enter the Numista N#, and the API will populate Coin_Types.csv.'))
        print('Press any key to continue.')
        read_key()
    return choice



def prompt_positive_int(title, default=''):
    while True:
        value = text_input(title, str(default) if default else '')
        if value is None:
            return None
        try:
            number = int(value)
        except ValueError:
            number = 0
        if number > 0:
            return number
        clear()
        print(red('Please enter a whole number greater than 0.'))
        print('Press any key to try again.')
        read_key()



def numista_api_settings_menu():
    """Settings sub-page for storing Numista API credentials and quota guard settings."""
    index = 0
    menu_items = ['Set / edit client ID', 'Set / edit API key', 'Set monthly API call max', 'Set warning percent', "Reset this month's local usage counters", 'Test API key', 'Clear saved API settings', 'Back']
    while True:
        usage = refresh_numista_api_usage_month(state.NUMISTA_API_USAGE)
        limit = usage.get('max_monthly_calls', 0)
        used = usage.get('api_calls_this_month', 0)
        remaining = max(0, limit - used)
        clear()
        print(c('=' * 100, '94'))
        print(bold(cyan('NUMISTA API SETTINGS'.center(100))))
        print(c('=' * 100, '94'))
        print()
        print(dim('Saved in settings.json. Treat the API key like a password and do not share the file.'))
        print()
        print(f"Client ID : {cyan(state.NUMISTA_CLIENT_ID or '(not set)')}")
        print(f'API key   : {cyan(mask_secret(state.NUMISTA_API_KEY))}')
        print()
        print(bold('Usage guard'))
        print(f"Month              : {cyan(usage.get('month', numista_usage_month_key()))}")
        print(f'Monthly max calls  : {cyan(limit)}')
        print(f'API calls used     : {(yellow(used) if used >= limit else cyan(used))}')
        print(f'Remaining calls    : {(red(remaining) if remaining == 0 else green(remaining))}')
        print(f"Warning threshold  : {cyan(str(usage.get('warn_percent', 85)) + '%')}")
        print(f"Successful / failed: {green(usage.get('successful_calls_this_month', 0))} / {red(usage.get('failed_calls_this_month', 0))}")
        print(f"Local cache hits   : {green(usage.get('cache_hits_this_month', 0))} this month, {green(usage.get('cache_hits_lifetime', 0))} lifetime")
        print(f"Lifetime API calls : {cyan(usage.get('api_calls_lifetime', 0))}")
        print(f"Last API call      : {usage.get('last_api_call') or 'Never'}")
        print()
        for i, item in enumerate(menu_items):
            print(reverse(item) if i == index else item)
        print()
        print(dim('TAB/DOWN/+ next | UP/- previous | ENTER select | BACKSPACE/ESC back'))
        key = read_key()
        if key in (state.KEY_ESC, state.KEY_BACKSPACE):
            save_settings()
            return
        if key in (state.KEY_TAB, state.KEY_DOWN, '+', '='):
            index = (index + 1) % len(menu_items)
            continue
        if key in (state.KEY_SHIFT_TAB, state.KEY_UP, '-', '_'):
            index = (index - 1) % len(menu_items)
            continue
        if key != state.KEY_ENTER:
            continue
        selected = menu_items[index]
        if selected == 'Set / edit client ID':
            value = text_input('Enter Numista client/user ID:', state.NUMISTA_CLIENT_ID)
            if value is not None:
                state.NUMISTA_CLIENT_ID = value.strip()
                save_settings()
        elif selected == 'Set / edit API key':
            value = text_input('Enter Numista API key:', state.NUMISTA_API_KEY)
            if value is not None:
                state.NUMISTA_API_KEY = value.strip()
                save_settings()
        elif selected == 'Set monthly API call max':
            set_numista_monthly_call_limit()
        elif selected == 'Set warning percent':
            set_numista_warning_percent()
        elif selected == "Reset this month's local usage counters":
            reset_numista_monthly_usage()
        elif selected == 'Test API key':
            result, error = numista_fetch_type_details('1')
            clear()
            if error:
                print(red('Numista API test failed.'))
                print()
                print(error)
            else:
                print(green('Numista API test worked.'))
                print()
                print(f"Example returned: N# {result.get('id', '1')} - {result.get('title', 'Unknown')}")
            print()
            print('Press any key to continue.')
            read_key()
        elif selected == 'Clear saved API settings':
            if prompt_yes_no('Clear saved Numista API settings?', 'This removes the client ID and API key from settings.json. Usage counters are kept.'):
                state.NUMISTA_CLIENT_ID = ''
                state.NUMISTA_API_KEY = ''
                save_settings()
        elif selected == 'Back':
            save_settings()
            return



def confirm_numista_type_details(details):
    """Show the fetched Numista type and require the user to confirm saving it."""
    selection = None

    def mark(text, active):
        return reverse(text) if active else dim(text)
    while True:
        clear()
        print(c('=' * 100, '94'))
        print(bold(cyan('VERIFY NUMISTA API RESULT'.center(100))))
        print(c('=' * 100, '94'))
        print()
        print(yellow('The N# you typed was looked up with the Numista API.'))
        print(bold('Verify this is the correct coin type before saving.'))
        print()
        print(f"N#          : {cyan(str(details.get('id', '')))}")
        print(f"Title       : {bold(details.get('title', 'Unknown'))}")
        print(f"Country     : {numista_detail_country(details) or 'Unknown'}")
        print(f'Years       : {numista_detail_years(details)}')
        print(f"Value       : {numista_detail_value_text(details) or 'Unknown'}")
        print(f"Currency    : {numista_detail_currency_text(details) or 'Unknown'}")
        print(f"Category    : {numista_detail_category(details) or 'Unknown'}")
        composition = details.get('composition', {})
        if isinstance(composition, dict) and composition.get('text'):
            print(f"Composition : {composition.get('text')}")
        if details.get('weight'):
            print(f"Weight      : {details.get('weight')} g")
        if details.get('size'):
            print(f"Diameter    : {details.get('size')} mm")
        print()
        print(dim('If saved, this type is added to Coin_Types.csv. If Numista gives a year range, every year in that range will match automatically.'))
        print()
        print('   +  ' + mark(green('  YES — save this type  '), selection is True))
        print('   -  ' + mark(red('  NO — do not save this type  '), selection is False))
        print()
        if selection is None:
            print(bold(yellow('No option selected yet.')))
        elif selection is True:
            print(green('Selected: YES — save this Numista type.'))
        else:
            print(red('Selected: NO — do not save this type.'))
        print()
        print(dim('Use + or - to choose. ENTER confirms. BACKSPACE/ESC cancels.'))
        key = read_key()
        if key in ('+', '=', state.KEY_DOWN, state.KEY_RIGHT):
            selection = True
        elif key in ('-', '_', state.KEY_UP, state.KEY_LEFT):
            selection = False
        elif key == state.KEY_ENTER and selection is not None:
            return selection
        elif key in (state.KEY_BACKSPACE, state.KEY_ESC):
            return None



def coin_roll_quantities_menu(numista_countries=None, denoms_by_country=None):
    """Settings sub-page for user-defined roll quantities by country/denomination."""
    numista_countries = numista_countries or []
    denoms_by_country = denoms_by_country or {}
    index = 0
    while True:
        entries = sorted(state.ROLL_QUANTITIES.items(), key=lambda item: item[0].lower())
        menu_items = [roll_quantity_label(key, qty) for key, qty in entries]
        menu_items += ['Add / edit from Numista denominations', 'Add / edit custom entry', 'Delete selected roll quantity', 'Back']
        index = max(0, min(index, len(menu_items) - 1))
        clear()
        print(c('=' * 100, '94'))
        print(bold(cyan('COIN ROLL QUANTITIES'.center(100))))
        print(c('=' * 100, '94'))
        print()
        print(dim('These are saved in settings.json and are not hard-coded.'))
        print(dim('Format: Country | denomination = coins per roll'))
        print()
        if not entries:
            print(yellow('No roll quantities saved yet.'))
            print()
        for i, item in enumerate(menu_items):
            print(reverse(item) if i == index else item)
        print()
        print(dim('TAB/DOWN/+ next | UP/- previous | ENTER select | BACKSPACE/ESC back'))
        key = read_key()
        if key in (state.KEY_BACKSPACE, state.KEY_ESC):
            save_settings()
            return
        if key in (state.KEY_TAB, state.KEY_DOWN, '+', '='):
            index = (index + 1) % len(menu_items)
            continue
        if key in (state.KEY_SHIFT_TAB, state.KEY_UP, '-', '_'):
            index = (index - 1) % len(menu_items)
            continue
        if key != state.KEY_ENTER:
            continue
        selected = menu_items[index]
        if index < len(entries):
            key_name, current_qty = entries[index]
            qty = prompt_positive_int(f'Edit coins per roll for:\n{roll_quantity_label(key_name, current_qty)}', current_qty)
            if qty is not None:
                state.ROLL_QUANTITIES[key_name] = qty
                save_settings()
            continue
        if selected == 'Add / edit from Numista denominations':
            if not numista_countries:
                clear()
                print(yellow('No Numista countries/denominations are loaded yet.'))
                print('Use custom entry, or add Numista CSV files and restart.')
                print('Press any key to continue.')
                read_key()
                continue
            choice = choose_country_and_denom(numista_countries, denoms_by_country)
            if not choice:
                continue
            key_name = roll_quantity_key(choice['country'], choice['face_value'], choice['currency'])
            qty = prompt_positive_int(f"Coins per roll for {choice['country']} | {choice['denomination']}:", state.ROLL_QUANTITIES.get(key_name, ''))
            if qty is not None:
                state.ROLL_QUANTITIES[key_name] = qty
                save_settings()
            continue
        if selected == 'Add / edit custom entry':
            country = text_input('Country name for this roll quantity:')
            if not country:
                continue
            face_value = text_input('Face value, for example 0.01, 0.25, 1.00:')
            if not face_value:
                continue
            currency = text_input('Currency/denomination label, for example Dollar (1785-date), Euro, Peso:')
            if currency is None:
                continue
            key_name = roll_quantity_key(country, face_value, currency)
            qty = prompt_positive_int(f'Coins per roll for {country} | {make_denom_label(face_value, currency)}:', state.ROLL_QUANTITIES.get(key_name, ''))
            if qty is not None:
                state.ROLL_QUANTITIES[key_name] = qty
                save_settings()
            continue
        if selected == 'Delete selected roll quantity':
            if not entries:
                continue
            labels = [roll_quantity_label(key, qty) for key, qty in entries]
            picked = choose_from_list('Delete which roll quantity?', labels + ['Cancel'])
            if picked and picked != 'Cancel':
                delete_index = labels.index(picked)
                key_name = entries[delete_index][0]
                if prompt_yes_no('Delete this roll quantity?', roll_quantity_label(key_name, state.ROLL_QUANTITIES[key_name])):
                    state.ROLL_QUANTITIES.pop(key_name, None)
                    save_settings()
            continue
        if selected == 'Back':
            save_settings()
            return



def read_assignable_key():
    while True:
        key = read_key()
        if key in (state.KEY_ESC, state.KEY_BACKSPACE):
            return None
        return key



def hotkeys_settings_menu():
    """Settings sub-page for assigning sorting hotkeys."""
    actions = list(state.DEFAULT_HOTKEYS.keys())
    menu_items = actions + ['Reset hotkeys to defaults', 'Back']
    index = 0
    while True:
        clear()
        print(c('=' * 100, '94'))
        print(bold(cyan('HOTKEY SETTINGS'.center(100))))
        print(c('=' * 100, '94'))
        print()
        print(dim('Select a hotkey, press ENTER, then press the new key. BACKSPACE/ESC cancels.'))
        print()
        print(bold('Current hotkeys'))
        print(c('-' * 100, '94'))
        for i, item in enumerate(menu_items):
            if item in actions:
                label = state.HOTKEY_LABELS[item]
                value = key_display(state.HOTKEYS[item])
                line = f'{label:<32} {cyan(value)}'
            else:
                line = item
            print(reverse(line) if i == index else line)
        print()
        print(dim('TAB/DOWN/+ next | UP/- previous | ENTER select | BACKSPACE/ESC back'))
        key = read_key()
        if key in (state.KEY_ESC, state.KEY_BACKSPACE):
            save_settings()
            return
        if key in (state.KEY_TAB, state.KEY_DOWN, '+', '='):
            index = (index + 1) % len(menu_items)
            continue
        if key in (state.KEY_SHIFT_TAB, state.KEY_UP, '-', '_'):
            index = (index - 1) % len(menu_items)
            continue
        if key != state.KEY_ENTER:
            continue
        selected = menu_items[index]
        if selected in actions:
            action = selected
            while True:
                clear()
                print(c('=' * 90, '94'))
                print(bold(cyan(f'ASSIGN HOTKEY: {state.HOTKEY_LABELS[action]}'.center(90))))
                print(c('=' * 90, '94'))
                print()
                print(f'Current key: {bold(yellow(key_display(state.HOTKEYS[action])))}')
                print()
                print(bold('Press the new key now.'))
                print(dim('BACKSPACE/ESC cancels. You can press numpad /, *, +, -, ENTER, etc.'))
                new_key = read_assignable_key()
                if new_key is None:
                    break
                conflict = None
                for other_action, other_key in state.HOTKEYS.items():
                    if other_action != action and normalize_key_for_compare(other_key) == normalize_key_for_compare(new_key):
                        conflict = other_action
                        break
                state.HOTKEYS[action] = new_key
                if conflict:
                    state.HOTKEYS[conflict] = state.DEFAULT_HOTKEYS[conflict]
                    clear()
                    print(yellow(f'{key_display(new_key)} was already used by {state.HOTKEY_LABELS[conflict]}.'))
                    print(yellow(f'{state.HOTKEY_LABELS[conflict]} was reset to {key_display(state.HOTKEYS[conflict])}.'))
                    print()
                    print('Press any key to continue.')
                    read_key()
                save_settings()
                break
        elif selected == 'Reset hotkeys to defaults':
            reset_hotkeys_to_default()
        elif selected == 'Back':
            save_settings()
            return



def settings_menu(numista_countries=None, denoms_by_country=None):
    menu_items = ['Hotkeys >', 'Sound settings >', 'Coin roll quantities >', 'Numista API settings >', 'Open data folder', 'Open sound file folder', 'Open app folders >', 'Toggle colors', 'Toggle big title', 'Back']
    index = 0

    def status_for_item(item):
        if item == 'Hotkeys >':
            return f'{len(state.DEFAULT_HOTKEYS)} assigned'
        if item == 'Sound settings >':
            return sound_mode_label()
        if item == 'Coin roll quantities >':
            return f'{len(state.ROLL_QUANTITIES)} saved'
        if item == 'Numista API settings >':
            return 'set' if numista_api_configured() else 'not set'
        if item == 'Open data folder':
            return state.DATA_DIR
        if item == 'Open sound file folder':
            return os.path.dirname(state.COIN_SAVE_SOUND_FILE) if state.COIN_SAVE_SOUND_FILE else 'no custom sound set'
        if item == 'Open app folders >':
            return 'data / settings / CSV / sessions / exports'
        if item == 'Toggle colors':
            return 'ON' if state.USE_COLOR else 'OFF'
        if item == 'Toggle big title':
            return 'ON' if state.BIG_UI else 'OFF'
        return ''
    while True:
        clear()
        print(c('=' * 100, '94'))
        print(bold(cyan('SETTINGS'.center(100))))
        print(c('=' * 100, '94'))
        print()
        print(dim(f'Settings file: {state.SETTINGS_PATH}'))
        print(dim(f'Data folder  : {state.DATA_DIR}'))
        print(dim('Items ending with > open a submenu. ENTER opens/toggles the selected item.'))
        print()
        print(bold('Configuration'))
        print(c('-' * 100, '94'))
        for i, item in enumerate(menu_items):
            if item == 'Back' and i != 0:
                print()
            status = status_for_item(item)
            if item.endswith('>'):
                line = f'{item:<30} {cyan(status)}'
            elif status:
                line = f'{item:<30} {status}'
            else:
                line = item
            print(reverse(line) if i == index else line)
        print()
        print(dim('TAB/DOWN/+ next | UP/- previous | ENTER select | BACKSPACE/ESC back'))
        key = read_key()
        if key in (state.KEY_ESC, state.KEY_BACKSPACE):
            save_settings()
            return
        if key in (state.KEY_TAB, state.KEY_DOWN, '+', '='):
            index = (index + 1) % len(menu_items)
            continue
        if key in (state.KEY_SHIFT_TAB, state.KEY_UP, '-', '_'):
            index = (index - 1) % len(menu_items)
            continue
        if key != state.KEY_ENTER:
            continue
        selected = menu_items[index]
        if selected == 'Hotkeys >':
            hotkeys_settings_menu()
        elif selected == 'Coin roll quantities >':
            coin_roll_quantities_menu(numista_countries, denoms_by_country)
        elif selected == 'Numista API settings >':
            numista_api_settings_menu()
        elif selected == 'Sound settings >':
            sound_settings_menu()
        elif selected == 'Open data folder':
            open_folder(state.DATA_DIR)
        elif selected == 'Open sound file folder':
            open_sound_folder()
        elif selected == 'Open app folders >':
            open_app_folders_menu()
        elif selected == 'Toggle colors':
            state.USE_COLOR = not state.USE_COLOR
            save_settings()
        elif selected == 'Toggle big title':
            state.BIG_UI = not state.BIG_UI
            save_settings()
        elif selected == 'Back':
            save_settings()
            return



def read_key():
    _flush_screen_buffer()
    'Cross-platform single-key reader.\n\n    Windows uses msvcrt. Linux/macOS use the termios/tty raw-mode reader.\n    This avoids external keyboard dependencies and keeps the app usable in\n    normal console builds on both Windows and Linux.\n    '
    if os.name == 'nt' and msvcrt is not None:
        return read_key_windows()
    return read_key_unix()



def read_key_windows():
    """Read one key on Windows using msvcrt, mapping it to the app constants."""
    ch = msvcrt.getwch()
    if ch in ('\x00', 'à'):
        ch2 = msvcrt.getwch()
        mapping = {'H': state.KEY_UP, 'P': state.KEY_DOWN, 'M': state.KEY_RIGHT, 'K': state.KEY_LEFT, 'S': state.KEY_DELETE}
        return mapping.get(ch2, f'SPECIAL_WIN_{repr(ch2)}')
    if ch in ('\r', '\n'):
        return state.KEY_ENTER
    if ch == '\t':
        return state.KEY_TAB
    if ch in ('\x08', '\x7f'):
        return state.KEY_BACKSPACE
    if ch == '\x1b':
        return state.KEY_ESC
    return ch



def read_key_unix():
    """Linux/macOS raw key reader with Tab, arrows, numpad chars, Enter, Backspace."""
    if termios is None or tty is None:
        raise RuntimeError('This version needs a terminal with termios/tty support.')
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch in ('\r', '\n'):
            return state.KEY_ENTER
        if ch == '\t':
            return state.KEY_TAB
        if ch in ('\x7f', '\x08'):
            return state.KEY_BACKSPACE
        if ch == '\x1b':
            if not select.select([sys.stdin], [], [], 0.2)[0]:
                return state.KEY_ESC
            ch2 = sys.stdin.read(1)
            if ch2 == '[':
                if not select.select([sys.stdin], [], [], 0.2)[0]:
                    return state.KEY_ESC
                ch3 = sys.stdin.read(1)
                if ch3 == 'A':
                    return state.KEY_UP
                if ch3 == 'B':
                    return state.KEY_DOWN
                if ch3 == 'C':
                    return state.KEY_RIGHT
                if ch3 == 'D':
                    return state.KEY_LEFT
                if ch3 == 'Z':
                    return state.KEY_SHIFT_TAB
                if ch3 == '3' and select.select([sys.stdin], [], [], 0.2)[0]:
                    ch4 = sys.stdin.read(1)
                    if ch4 == '~':
                        return state.KEY_DELETE
                return f'SPECIAL_ESC_[{repr(ch3)}]'
            if ch2 == 'O':
                if not select.select([sys.stdin], [], [], 0.2)[0]:
                    return state.KEY_ESC
                ch3 = sys.stdin.read(1)
                if ch3 == 'A':
                    return state.KEY_UP
                if ch3 == 'B':
                    return state.KEY_DOWN
                if ch3 == 'C':
                    return state.KEY_RIGHT
                if ch3 == 'D':
                    return state.KEY_LEFT
                return f'SPECIAL_ESC_O{repr(ch3)}'
            return state.KEY_ESC
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)



def prompt_yes_no(title, detail=''):
    """Return True for Yes, False for No, or None when cancelled."""
    choice = choose_from_list(title + ('\n\n' + detail if detail else ''), ['Yes', 'No'])
    if choice is None:
        return None
    return choice == 'Yes'



def text_input(prompt, default=''):
    value = default
    while True:
        clear()
        print(prompt)
        print()
        print(value)
        print()
        print('Type text | ENTER/TAB confirm | BACKSPACE delete | ESC cancel')
        key = read_key()
        if key == state.KEY_ESC:
            return None
        if key in (state.KEY_ENTER, state.KEY_TAB):
            return value.strip()
        if key == state.KEY_BACKSPACE:
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
            print(('> ' if i == index else '  ') + item)
        print()
        print('TAB/DOWN next | UP previous | ENTER confirm | ESC cancel')
        key = read_key()
        if key == state.KEY_ESC:
            return None
        if key in (state.KEY_TAB, state.KEY_DOWN, '+', '='):
            index = (index + 1) % len(options)
        elif key in (state.KEY_SHIFT_TAB, state.KEY_UP, '-', '_'):
            index = (index - 1) % len(options)
        elif key == state.KEY_ENTER:
            return options[index]



def choose_multiple_from_list(title, options, allow_all=True):
    """Numpad-first multi-select menu. Returns selected option strings, or None."""
    if not options:
        clear()
        print(bold(yellow('Nothing available to select.')))
        print()
        print('Press any key to return.')
        read_key()
        return None
    index = 0
    selected = set(range(len(options))) if allow_all else set()
    focus_area = 'items'
    action_index = 0
    actions = ['Confirm', 'Select all', 'Select none', 'Cancel']
    while True:
        clear()
        print(c('=' * 110, '94'))
        print(bold(cyan(title.center(110))))
        print(c('=' * 110, '94'))
        print()
        print(bold('Controls:'), 'TAB moves selection   + / - changes highlighted option   ENTER selects/toggles   BACKSPACE cancels')
        print(dim('Use ENTER on an item to check/uncheck it. TAB down to Confirm when ready.'))
        print()
        for i, item in enumerate(options):
            check = '[x]' if i in selected else '[ ]'
            line = f'{check} {item}'
            is_active = focus_area == 'items' and i == index
            print(reverse(line) if is_active else line)
        print()
        print(c('-' * 110, '94'))
        print(dim(f'Selected: {len(selected)} of {len(options)}'))
        print()
        rendered_actions = []
        for i, action in enumerate(actions):
            text = f' {action} '
            rendered_actions.append(reverse(text) if focus_area == 'actions' and i == action_index else bold(text))
        print('   '.join(rendered_actions))
        print(dim('TAB switches between the item list and action row. + / - moves within the active area.'))
        key = read_key()
        if key in (state.KEY_BACKSPACE, state.KEY_ESC):
            return None
        if key in (state.KEY_TAB, state.KEY_DOWN):
            if focus_area == 'items':
                focus_area = 'actions'
                action_index = 0
            else:
                focus_area = 'items'
            continue
        if key in (state.KEY_SHIFT_TAB, state.KEY_UP):
            if focus_area == 'actions':
                focus_area = 'items'
            else:
                focus_area = 'actions'
                action_index = len(actions) - 1
            continue
        if key in ('+', '='):
            if focus_area == 'items':
                index = (index + 1) % len(options)
            else:
                action_index = (action_index + 1) % len(actions)
            continue
        if key in ('-', '_'):
            if focus_area == 'items':
                index = (index - 1) % len(options)
            else:
                action_index = (action_index - 1) % len(actions)
            continue
        if key == state.KEY_ENTER:
            if focus_area == 'items':
                if index in selected:
                    selected.remove(index)
                else:
                    selected.add(index)
                continue
            action = actions[action_index]
            if action == 'Confirm':
                if not selected:
                    clear()
                    print(red('Select at least one item first.'))
                    print('Press any key to continue.')
                    read_key()
                    focus_area = 'items'
                    continue
                return [options[i] for i in range(len(options)) if i in selected]
            if action == 'Select all':
                selected = set(range(len(options)))
            elif action == 'Select none':
                selected = set()
            elif action == 'Cancel':
                return None



def session_menu():
    ensure_sessions_dir()
    ensure_numista_dir()
    numista_index, numista_files, numista_countries, denoms_by_country, numista_type_index = load_numista_index()
    while True:
        choice = choose_from_list('Coin Sorter Sessions', ['Start new session', 'Resume session', 'Statistics', 'Export Data', 'Settings', 'Quit'])
        if choice == 'Start new session':
            numista_index, numista_files, numista_countries, denoms_by_country, numista_type_index = refresh_numista_index_for_session(numista_index, numista_files)
            session = new_session(numista_countries, denoms_by_country)
            if session:
                session['numista_index'] = numista_index
                session['numista_csv_count'] = len(numista_files)
                session['numista_coin_count'] = len(numista_index)
                session['numista_countries'] = numista_countries
                session['denoms_by_country'] = denoms_by_country
                session['numista_type_index'] = numista_type_index
                return session
        elif choice == 'Resume session':
            numista_index, numista_files, numista_countries, denoms_by_country, numista_type_index = refresh_numista_index_for_session(numista_index, numista_files)
            session = resume_session(numista_countries, denoms_by_country)
            if session:
                session['numista_index'] = numista_index
                session['numista_csv_count'] = len(numista_files)
                session['numista_coin_count'] = len(numista_index)
                session['numista_countries'] = numista_countries
                session['denoms_by_country'] = denoms_by_country
                session['numista_type_index'] = numista_type_index
                return session
        elif choice == 'Statistics':
            home_statistics_menu()
        elif choice == 'Export Data':
            export_menu()
        elif choice == 'Settings':
            settings_menu(numista_countries, denoms_by_country)
            numista_index, numista_files, numista_countries, denoms_by_country, numista_type_index = refresh_numista_index_for_session(numista_index, numista_files)
        elif choice == 'Quit' or choice is None:
            return None



def draw(session, year, mint_index, coin_type_index, notes, reject, reject_reason, keep_bulk, selected_index, focus, editing_index):
    clear()
    log = session['log']
    if state.BIG_UI:
        print(c('=' * 110, '94'))
        print(bold(c(' ██████╗ ██████╗ ██╗███╗   ██╗     ███████╗ ██████╗ ██████╗ ████████╗ '.center(110), '96')))
        print(bold(c('██╔════╝██╔═══██╗██║████╗  ██║     ██╔════╝██╔═══██╗██╔══██╗╚══██╔══╝ '.center(110), '96')))
        print(bold(c('██║     ██║   ██║██║██╔██╗ ██║     ███████╗██║   ██║██████╔╝   ██║    '.center(110), '96')))
        print(bold(c('╚██████╗╚██████╔╝██║██║ ╚████║     ███████║╚██████╔╝██║  ██║   ██║    '.center(110), '96')))
        print(c('=' * 110, '94'))
    else:
        print(bold(cyan('COIN SORTER')))
    print(f"{bold('Session:')} {session['session_name']}    {bold('Type:')} {session['session_type']}")
    if session.get('session_notes'):
        print(f"{bold('Session Notes:')} {session.get('session_notes')}")
    print(f"{bold('Country:')} {session.get('country', 'Unknown')}    {bold('Denomination:')} {session['denomination']}")
    print(f"{bold('File:')} {session['path']}")
    if session.get('numista_csv_count', 0):
        type_count = sum((len(bucket) for bucket in (session.get('numista_type_index', {}) or {}).values()))
        print(f"{bold('Numista CSVs:')} {session.get('numista_csv_count')} loaded from {state.NUMISTA_DIR} | {session.get('numista_coin_count', 0)} owned entries | {type_count} cached type rows")
    else:
        print(yellow(f'Numista CSVs: none loaded from {state.NUMISTA_DIR}'))
        print(dim(f'Coin type cache: {state.COIN_TYPES_PATH}'))
    total_sorted, today_sorted = session_counts(log)
    print(f"{bold('Sorted in this CSV:')} {green(str(total_sorted))} total    {bold('Today:')} {green(str(today_sorted))}")
    if session.get('session_type') == 'Coin roll hunt':
        roll_mode = session.get('roll_mode') or 'none'
        if roll_mode in ('automatic', 'manual'):
            qty = session.get('roll_quantity') or '?'
            print(f"{bold('CRH Roll Tracking:')} {cyan(roll_mode)}    {bold('Current roll:')} {green(str(session.get('current_roll', 1)))}    {bold('Coins in roll:')} {green(str(session.get('current_roll_count', 0)))}/{qty}")
        else:
            print(f"{bold('CRH Roll Tracking:')} {dim('off')}")
    print()
    print(cyan('Flow:'), 'Type year digits anytime → + / - picks mint → ENTER saves  |  numpad . cycles visible Type list')
    print(cyan('Controls:'), f"TAB = move   ENTER = select/save   + / - = mint   {key_display(state.HOTKEYS['type_next'])} = type   {key_display(state.HOTKEYS['reject'])} = REJECT   {key_display(state.HOTKEYS['keep_bulk'])} = KEEP/BULK   Sound: {sound_mode_label()}")
    print(dim(f'Year is checked live. Max allowed year: {current_year() + 1}.'))
    print(dim('TAB only changes which field/action is selected. It does not change mint or toggle anything.'))
    print(c('-' * 110, '94'))
    status = f'EDITING COIN #{editing_index + 1}' if editing_index is not None else 'NEW COIN'
    print(bold(yellow(status)))
    print()

    def box_line(label_text, value_text, name, hint=''):
        left = reverse(f' {label_text} ') if focus == name else bold(f' {label_text} ')
        print(f'{left:<38} {value_text} {dim(hint)}')
        if state.BIG_UI:
            print()
    warning = year_warning(session, year)
    year_value = bold(cyan(year or '____'))
    if warning and year:
        year_value += '  ' + red('⚠')
    mint_value = bold(cyan(state.MINTS[mint_index]))
    type_options = get_detected_type_options(session, year, state.MINTS[mint_index])
    if coin_type_index >= len(type_options):
        coin_type_index = 0
    coin_type_value = bold(cyan(type_option_compact_label(type_options[coin_type_index], reserved_columns=48)))
    if len(type_options) > 1:
        coin_type_value += dim(f'  [{coin_type_index + 1}/{len(type_options)}]')
    notes_value = bold(cyan(notes)) if notes else dim('(blank)')
    reject_value = red('YES') if reject else dim('no')
    if reject and reject_reason:
        reject_value += dim(f' ({reject_reason})')
    keep_value = green('YES') if keep_bulk else dim('no')
    print(bold(cyan('  ┌──────────────────────────────────────────────────────────────┐')))
    print(bold(cyan('  │                    CURRENT COIN ENTRY                         │')))
    print(bold(cyan('  └──────────────────────────────────────────────────────────────┘')))
    print()
    box_line('Year', year_value, 'year', 'must be 4 digits to save')
    if warning:
        print('  ' + yellow(warning))
        print()
    box_line('Mint', mint_value, 'mint', '+ / - changes mint; ENTER saves')
    visible_type_indexes = visible_type_option_indexes(type_options, coin_type_index)
    if not visible_type_indexes:
        box_line('Type', coin_type_value, 'coin_type', 'numpad . changes type')
    else:
        type_label = reverse(' Type ') if focus == 'coin_type' else bold(' Type ')
        print(f"{type_label:<38} {dim('numpad . cycles down; visible list prevents overshooting')}")
        if state.BIG_UI:
            print()
        if len(type_options) > len(visible_type_indexes):
            first_visible = visible_type_indexes[0] + 1
            last_visible = visible_type_indexes[-1] + 1
            print('  ' + dim(f'Showing {first_visible}-{last_visible} of {len(type_options)} type choices.'))
        for option_index in visible_type_indexes:
            option = type_options[option_index]
            selected = option_index == coin_type_index
            prefix = '> ' if selected else '  '
            line = f'  {prefix}{type_option_compact_label(option, reserved_columns=8, clickable_n_number=True)}'
            print(reverse(line) if selected and focus == 'coin_type' else bold(cyan(line)) if selected else line)
        if state.BIG_UI:
            print()
    box_line('Save Coin', green('manual save if you tab here'), 'save', '')
    box_line('Notes', notes_value, 'notes', 'required if Type is OTHER')
    print(f"{bold('  Reject')}        {reject_value}      {dim('hotkey only; asks reason when turned on')}")
    print(f"{bold('  Keep/Bulk')}  {keep_value}      {dim('hotkey only: *')}")
    print()
    print(f"{(reverse(' Recent/Edit ') if focus == 'recent' else bold(' Recent/Edit '))} {dim('ENTER opens full previous-coin edit list')}")
    print(f"{(reverse(' Change Country/Denom ') if focus == 'change_denom' else bold(' Change Country/Denom '))} {dim('ENTER changes/adds active sorting selection')}")
    print(f"{(reverse(' Edit Session Notes ') if focus == 'session_notes' else bold(' Edit Session Notes '))} {dim('ENTER edits title-level notes for this session')}")
    if session.get('session_type') == 'Coin roll hunt' and session.get('roll_mode') in ('automatic', 'manual'):
        next_roll_hint = 'ENTER forces the next roll now' if session.get('roll_mode') == 'automatic' else 'ENTER starts the next roll manually'
        print(f"{(reverse(' Next Roll ') if focus == 'next_roll' else bold(' Next Roll '))} {dim(next_roll_hint)}")
    print(f"{(reverse(' Statistics ') if focus == 'statistics' else bold(' Statistics '))} {dim('ENTER opens session statistics page')}")
    print(f"{(reverse(' Save + Quit ') if focus == 'quit' else bold(' Save + Quit '))} {dim('ENTER opens confirmation')}")
    print()
    print(c('-' * 110, '94'))
    print(bold('Last sorted coins:'))
    recent = log[-5:]
    start_index = len(log) - len(recent)
    if not recent:
        print(dim('  No coins saved yet.'))
    for i, coin in enumerate(recent):
        global_index = start_index + i
        marker = reverse('> ') if global_index == selected_index else '  '
        flags = []
        if boolish(coin.get('reject', False)):
            reason = coin.get('reject_reason', '')
            flags.append(red('REJECT' + (f': {reason}' if reason else '')))
        if boolish(coin.get('keep_bulk', False)):
            flags.append(green('KEEP/BULK'))
        if boolish(coin.get('new_collection', False)):
            flags.append(yellow('NEW COLLECTION'))
        flag_text = f" [{' | '.join(flags)}]" if flags else ''
        print(f"{marker}{global_index + 1}. {coin.get('year', '')}-{coin.get('mint', '')} | {coin.get('coin_type', 'Unknown type')} | {coin.get('denomination', '')} | {coin.get('notes', '')}{flag_text}")
    print()
    print(c('-' * 110, '94'))
    print(bold('Current selection help:'))
    if focus == 'year':
        print('Type the year. Number keys jump back here from most fields. The coin will not save unless the year is exactly 4 digits.')
    elif focus == 'mint':
        print('Use + or - to choose the mint. ENTER saves the coin. Type year digits anytime to jump back to Year.')
    elif focus == 'coin_type':
        print('Use numpad . to move down the type list. ENTER saves. Choose OTHER only when it is not listed; notes are required for OTHER.')
    elif focus == 'save':
        print('Press ENTER to save this coin and start the next coin. This is the manual save step if you tabbed past Mint.')
    elif focus == 'notes':
        print('Type notes if needed. ENTER saves this coin and starts the next coin.')
    elif focus == 'recent':
        print('Press ENTER to open the full previous-coin edit list. TAB only moves selection.')
    elif focus == 'change_denom':
        print('Press ENTER to choose a country/denomination, or add one from a Numista N# without placeholders.')
    elif focus == 'session_notes':
        print('Press ENTER to edit session-level notes, such as cool finds, where coins came from, or what you paid.')
    elif focus == 'next_roll':
        if session.get('session_type') == 'Coin roll hunt' and session.get('roll_mode') == 'automatic':
            print('Press ENTER to force the next roll now. Use this for short, partial, or odd rolls.')
        elif session.get('session_type') == 'Coin roll hunt' and session.get('roll_mode') == 'manual':
            print('Press ENTER when you are ready to start the next roll.')
        else:
            print('Next Roll is only active for Coin Roll Hunt sessions with roll tracking.')
    elif focus == 'statistics':
        print('Press ENTER to open a separate statistics page for this session CSV.')
    elif focus == 'quit':
        print('ENTER opens Save + Quit confirmation.')



def sorting_loop(session):
    numista_index = session.get('numista_index')
    if numista_index is None:
        numista_index, numista_files, numista_countries, denoms_by_country, numista_type_index = load_numista_index()
        session['numista_index'] = numista_index
        session['numista_csv_count'] = len(numista_files)
        session['numista_coin_count'] = len(numista_index)
        session['numista_countries'] = numista_countries
        session['denoms_by_country'] = denoms_by_country
        session['numista_type_index'] = numista_type_index
    year, mint_index, coin_type_index, notes, reject, reject_reason, keep_bulk, focus = reset_coin()
    selected_index = -1
    editing_index = None
    return_to_recent_after_edit = False

    def load_index_for_edit(index, return_to_recent=False):
        nonlocal year, mint_index, coin_type_index, notes, reject, reject_reason, keep_bulk, editing_index, focus, selected_index, return_to_recent_after_edit
        if index is None or not 0 <= index < len(session['log']):
            return
        selected_index = index
        coin = session['log'][index]
        year = coin.get('year', '')
        notes = coin.get('notes', '')
        mint_value = coin.get('mint', 'No Mint')
        mint_index = state.MINTS.index(mint_value) if mint_value in state.MINTS else 0
        type_options = get_detected_type_options(session, year, mint_value)
        saved_type = coin.get('coin_type', '')
        saved_number = coin.get('numista_number', '')
        coin_type_index = 0
        for pos, option in enumerate(type_options):
            if option.get('coin_type') == saved_type and option.get('numista_number') == saved_number:
                coin_type_index = pos
                break
        reject = boolish(coin.get('reject', False))
        reject_reason = coin.get('reject_reason', '')
        keep_bulk = boolish(coin.get('keep_bulk', False))
        editing_index = index
        return_to_recent_after_edit = bool(return_to_recent)
        focus = 'year'

    def finish_save():
        nonlocal year, mint_index, coin_type_index, notes, reject, reject_reason, keep_bulk, focus, editing_index, selected_index, return_to_recent_after_edit
        was_editing_index = editing_index
        should_return_to_recent = return_to_recent_after_edit and was_editing_index is not None
        saved, editing_index = save_current_coin(session, year, mint_index, coin_type_index, notes, reject, reject_reason, keep_bulk, editing_index, numista_index)
        if saved:
            play_coin_saved_sound()
            year, mint_index, coin_type_index, notes, reject, reject_reason, keep_bulk, focus = reset_coin()
            if should_return_to_recent:
                selected_index = max(0, min(was_editing_index, len(session['log']) - 1)) if session['log'] else -1
                return_to_recent_after_edit = False
                chosen = previous_coins_menu(session, selected_index if selected_index != -1 else None)
                if chosen is not None:
                    load_index_for_edit(chosen, return_to_recent=True)
                else:
                    focus = 'year'
            else:
                selected_index = -1
                return_to_recent_after_edit = False

    def move_focus(direction):
        nonlocal focus
        focus = next_focus(session, focus, direction)
    while True:
        focus = normalize_focus_for_session(session, focus)
        draw(session, year, mint_index, coin_type_index, notes, reject, reject_reason, keep_bulk, selected_index, focus, editing_index)
        key = read_key()
        if hotkey_matches(key, 'save_quit'):
            if confirm_save_quit(session):
                break
            continue
        if hotkey_matches(key, 'reject'):
            if reject:
                reject = False
                reject_reason = ''
            else:
                reason = prompt_reject_reason(reject_reason)
                if reason:
                    reject = True
                    reject_reason = reason
                    keep_bulk = False
            continue
        if hotkey_matches(key, 'keep_bulk'):
            keep_bulk = not keep_bulk
            if keep_bulk:
                reject = False
                reject_reason = ''
            continue
        if hotkey_matches(key, 'type_next'):
            options = get_detected_type_options(session, year, state.MINTS[mint_index])
            coin_type_index = (coin_type_index + 1) % len(options)
            focus = 'coin_type'
            continue
        if hotkey_matches(key, 'mint_next'):
            mint_index = (mint_index + 1) % len(state.MINTS)
            coin_type_index = 0
            focus = 'mint'
            continue
        if hotkey_matches(key, 'mint_previous'):
            mint_index = (mint_index - 1) % len(state.MINTS)
            coin_type_index = 0
            focus = 'mint'
            continue
        if key == state.KEY_TAB:
            move_focus(1)
            continue
        if key == state.KEY_SHIFT_TAB:
            move_focus(-1)
            continue
        if key == state.KEY_UP:
            if focus == 'recent' and session['log']:
                selected_index = len(session['log']) - 1 if selected_index == -1 else max(0, selected_index - 1)
            else:
                move_focus(-1)
            continue
        if key == state.KEY_DOWN:
            if focus == 'recent' and session['log']:
                selected_index = len(session['log']) - 1 if selected_index == -1 else min(len(session['log']) - 1, selected_index + 1)
            else:
                move_focus(1)
            continue
        if key == state.KEY_LEFT:
            move_focus(-1)
            continue
        if key == state.KEY_RIGHT:
            if focus == 'recent':
                chosen = previous_coins_menu(session)
                if chosen is not None:
                    load_index_for_edit(chosen, return_to_recent=True)
                else:
                    focus = 'year'
            else:
                move_focus(1)
            continue
        if key == state.KEY_ENTER:
            if focus == 'year':
                focus = 'mint'
            elif focus == 'mint':
                finish_save()
            elif focus == 'coin_type':
                finish_save()
            elif focus == 'save':
                finish_save()
            elif focus == 'notes':
                finish_save()
            elif focus == 'recent':
                chosen = previous_coins_menu(session)
                if chosen is not None:
                    load_index_for_edit(chosen, return_to_recent=True)
                else:
                    focus = 'year'
            elif focus == 'change_denom':
                if change_current_country_denom(session):
                    coin_type_index = 0
                focus = 'year'
            elif focus == 'session_notes':
                edit_session_notes(session)
                focus = 'year'
            elif focus == 'next_roll':
                if session.get('session_type') == 'Coin roll hunt' and session.get('roll_mode') in ('automatic', 'manual'):
                    advance_manual_roll(session)
                focus = 'year'
            elif focus == 'statistics':
                statistics_menu(session)
                focus = 'year'
            elif focus == 'quit':
                if confirm_save_quit(session):
                    break
            continue
        if key == state.KEY_BACKSPACE:
            if focus == 'year':
                year = year[:-1]
            elif focus == 'notes':
                notes = notes[:-1]
            continue
        if isinstance(key, str) and len(key) == 1 and key.isdigit() and (focus != 'notes'):
            if can_type_year_digit(session, year, key):
                if len(year) >= 4:
                    year = key
                else:
                    year += key
                coin_type_index = 0
                focus = 'year'
            continue
        if focus == 'notes' and isinstance(key, str) and (len(key) == 1) and key.isprintable():
            notes += key
            continue



def main():
    load_settings()
    configure_terminal_output()
    while True:
        session = session_menu()
        if not session:
            clear()
            print('Goodbye.')
            return
        sorting_loop(session)


