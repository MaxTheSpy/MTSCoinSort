# Auto-split from MTS CoinSort V0.2.0.
# Keep behavior changes small in this refactor; modules are wired together at startup.
from .common import *
from . import app_state as state


def prompt_manual_coin_type(session, year, mint_name, existing_notes=''):
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
        print(red('Numista API key is not set.'))
        print()
        print('Go to Settings > Numista API settings and save your API key first.')
        print('Press any key to return to editing this coin.')
        read_key()
        return (None, None)
    should_search = prompt_yes_no('Coin type is OTHER. Open Numista search in your browser?', 'Find the correct catalogue page, then come back and enter the N# number. BACKSPACE/ESC returns to editing.')
    if should_search is None:
        return (None, None)
    if should_search:
        try:
            webbrowser.open(numista_search_url(session, year, mint_name))
        except Exception:
            pass
    while True:
        numista_number = text_input('Enter the Numista N# for this type. Example: 1109 or N#1109:\n\nIMPORTANT: Pressing ENTER here will call the Numista API using your saved API key.\nAfter the API returns a result, you will verify it before anything is saved.')
        if numista_number is None:
            return (None, None)
        clean_number = clean_numista_number(numista_number)
        if not clean_number:
            clear()
            print(red('A Numista number is required.'))
            print('Example: enter 1109 or N#1109')
            print('Press any key to continue.')
            read_key()
            continue
        cached_row = best_cached_numista_row(clean_number)
        if cached_row:
            local_choice_action = confirm_cached_numista_row(cached_row, clean_number, 'OTHER coin type selection')
            if local_choice_action is None:
                return (None, None)
            if local_choice_action == 'use':
                log_numista_cache_hit(clean_number)
                all_rows = read_coin_type_cache_rows()
                session['numista_type_index'] = build_type_index_from_cache(all_rows)
                option = cached_row_type_option(cached_row, current_year=year, current_mint=mint_name, match_note='local Coin_Types.csv cache')
                remove_custom_denominations_for_country_face(option.get('country', ''), option.get('face_value', ''))
                session['country'] = option.get('country', session.get('country', ''))
                session['currency'] = option.get('currency', session.get('currency', ''))
                session['face_value'] = option.get('face_value', session.get('face_value', ''))
                session['denomination'] = option.get('denomination', session.get('denomination', ''))
                return (option, option.get('coin_type', ''))
        details, error = numista_fetch_type_details(clean_number)
        if error:
            clear()
            print(red('Could not fetch that Numista type.'))
            print()
            print(error)
            print()
            retry = prompt_yes_no('Try another N#?', 'Choose No to return to editing the coin.')
            if retry:
                continue
            return (None, None)
        confirmed = confirm_numista_type_details(details)
        if confirmed is None:
            return (None, None)
        if not confirmed:
            retry = prompt_yes_no('Try another N#?', 'Choose No to return to editing the coin.')
            if retry:
                continue
            return (None, None)
        row = make_coin_type_cache_row_from_numista_api(session, year, mint_name, details)
        all_rows = upsert_coin_type_cache_rows([row])
        session['numista_type_index'] = build_type_index_from_cache(all_rows)
        remove_custom_denominations_for_country_face(row.get('country', ''), row.get('face_value', ''))
        session['country'] = row.get('country', session.get('country', ''))
        session['currency'] = row.get('currency', session.get('currency', ''))
        session['face_value'] = row.get('face_value', session.get('face_value', ''))
        session['denomination'] = row.get('denomination', session.get('denomination', ''))
        return ({'coin_type': row['coin_type'], 'numista_number': row['numista_number'], 'numista_title': row['numista_title'], 'numista_category': row['numista_category'], 'denomination': row['denomination'], 'country': row['country'], 'face_value': row['face_value'], 'year': row['year'], 'mint': row['mint'], 'selected_mint': row['mint'], 'match_note': 'Numista API saved to Coin_Types.csv'}, row['coin_type'])



def get_detected_type_options(session, year, mint_name):
    """Return Numista type choices for country/value/year.

    Match order:
      1. Exact year + current mint candidates.
      2. Same year from another mint.
      3. API/manual range rows where min_year <= entered year <= max_year.
      4. OTHER.
    """
    country = session.get('country', '').strip()
    face_value = normalize_decimal(session.get('face_value', ''))
    year_text = str(year).strip()
    entered_year = safe_int(year_text)
    type_index = session.get('numista_type_index', {}) or {}
    options = []
    seen = set()

    def add_option(option, match_note=''):
        unique = (option.get('numista_number', ''), option.get('coin_type', ''), option.get('numista_title', ''))
        if unique in seen:
            return
        seen.add(unique)
        copied = dict(option)
        copied['selected_mint'] = normalize_mint(mint_name)
        copied['match_note'] = match_note
        options.append(copied)
    if country and face_value and year_text:
        exact_mints = coin_mint_candidates(mint_name)
        for mint in exact_mints:
            for option in type_index.get((country, face_value, year_text, mint), []):
                add_option(option, 'exact mint')
        for key, bucket in type_index.items():
            if key == '__ranges__' or not isinstance(key, tuple) or len(key) != 4:
                continue
            idx_country, idx_face, idx_year, idx_mint = key
            if idx_country == country and idx_face == face_value and (idx_year == year_text):
                for option in bucket:
                    if idx_mint in exact_mints:
                        continue
                    add_option(option, f"same Numista type from mint {idx_mint or 'No Mint'}")
        if entered_year is not None:
            for option in type_index.get('__ranges__', []):
                if option.get('country', '') != country:
                    continue
                if normalize_decimal(option.get('face_value', '')) != face_value:
                    continue
                option_mint = normalize_mint(option.get('mint', ''))
                if option_mint and option_mint not in exact_mints:
                    continue
                min_year = safe_int(option.get('min_year', ''))
                max_year = safe_int(option.get('max_year', ''))
                if min_year is None or max_year is None:
                    continue
                if min_year <= entered_year <= max_year:
                    add_option(option, f'API range {year_range_label(min_year, max_year)}')
    options.sort(key=lambda option: (0 if option.get('match_note') == 'exact mint' else 1 if str(option.get('match_note', '')).startswith('same Numista') else 2, option.get('coin_type', '').lower(), safe_int(option.get('min_year', ''), 999999), clean_numista_number(option.get('numista_number', '')) or '999999999'))
    options.append({'coin_type': 'OTHER', 'numista_number': '', 'numista_title': 'OTHER', 'numista_category': 'Manual / not listed', 'denomination': session.get('denomination', ''), 'country': country, 'face_value': face_value, 'year': year_text, 'min_year': year_text, 'max_year': year_text, 'year_range': year_text, 'mint': normalize_mint(mint_name), 'selected_mint': normalize_mint(mint_name), 'match_note': 'manual'})
    return options



def type_option_label(option):
    coin_type = option.get('coin_type', '') or 'Unknown type'
    number = option.get('numista_number', '')
    clean_number = clean_numista_number(number)
    denom = option.get('denomination', '')
    category = option.get('numista_category', '')
    match_note = option.get('match_note', '')
    parts = [coin_type]
    details = []
    if clean_number:
        linked_number = terminal_link(f'N# {clean_number}', numista_url(number))
        details.append(linked_number)
    if denom:
        details.append(denom)
    if category and category not in (coin_type, 'Manual / not listed'):
        details.append(category)
    if match_note and match_note not in ('exact mint', 'manual'):
        details.append(match_note)
    if details:
        parts.append('(' + ' | '.join(details) + ')')
    return ' '.join(parts)



def visible_type_option_indexes(type_options, selected_index, window_size=7):
    """Return indexes to display for the inline coin-type picker.

    Display rules:
      - 1 detected type + OTHER: keep the compact single-line field.
      - Up to 5 detected types + OTHER: show the whole list.
      - More than 5 detected types + OTHER: show a rolling window around
        the selected type so the screen stays compact.
    """
    total = len(type_options or [])
    if total <= 2:
        return []
    selected_index = max(0, min(int(selected_index or 0), total - 1))
    if total <= 6:
        return list(range(total))
    window_size = max(3, min(int(window_size or 7), total))
    half = window_size // 2
    start = selected_index - half
    start = max(0, min(start, total - window_size))
    return list(range(start, start + window_size))



def type_option_plain_label(option):
    """Plain label for the live sorter screen.

    The sorting screen needs to stay compact and predictable. Long Numista
    titles are truncated by type_option_compact_label(), and only the small N#
    token is optionally made clickable so full labels do not wrap/underline the
    whole terminal line.
    """
    coin_type = str(option.get('coin_type', '') or 'Unknown type').strip()
    clean_number = clean_numista_number(option.get('numista_number', ''))
    if coin_type.upper() == 'OTHER':
        return 'OTHER'
    if clean_number:
        return f'{coin_type}  N# {clean_number}'
    return coin_type



def type_option_compact_label(option, reserved_columns=10, clickable_n_number=False):
    """Short, fixed-width-safe label for the visible inline picker.

    When clickable_n_number is True, only the N# token is hyperlinked. The coin
    type text itself stays plain and truncated, which keeps VS Code/Windows
    terminals from underlining or wrapping the whole sorter line.
    """
    coin_type = str(option.get('coin_type', '') or 'Unknown type').strip()
    clean_number = clean_numista_number(option.get('numista_number', ''))
    width = shutil.get_terminal_size((100, 30)).columns
    max_len = max(28, min(70, width - int(reserved_columns or 10)))
    if coin_type.upper() == 'OTHER':
        return 'OTHER'
    if clean_number:
        suffix_plain = f'  N# {clean_number}'
        coin_max = max(12, max_len - len(suffix_plain))
        coin_display = coin_type if len(coin_type) <= coin_max else coin_type[:coin_max - 3] + '...'
        suffix = '  ' + clickable_numista_number(clean_number) if clickable_n_number else suffix_plain
        return coin_display + suffix
    return coin_type if len(coin_type) <= max_len else coin_type[:max_len - 3] + '...'



def selected_type_option(session, year, mint_index, coin_type_index):
    options = get_detected_type_options(session, year, state.MINTS[mint_index])
    if not options:
        return {'coin_type': 'OTHER', 'numista_number': '', 'numista_title': 'OTHER', 'numista_category': 'Manual / not listed'}
    coin_type_index = max(0, min(int(coin_type_index or 0), len(options) - 1))
    return options[coin_type_index]



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
    add_country_option = 'Add country / denomination from Numista N#'
    manual_country_option = 'Add custom country / denomination manually'
    country_options.append(add_country_option)
    country_options.append(manual_country_option)
    country = choose_from_list('Select country for this coin:\n\nNumista CSV countries and learned API countries are shown together.\nIf the country/denomination is missing, choose Add country / denomination from Numista N#.', country_options)
    if not country:
        return None
    if country == add_country_option:
        return prompt_numista_country_denom_from_api()
    if country == manual_country_option:
        return prompt_custom_country_denom()
    denom_set = set(denoms_by_country.get(country, []))
    denom_set.update(cache_map.get(country, set()))
    denom_set.update(custom_map.get(country, set()))
    denom_options = sorted(denom_set, key=lambda label: (split_denom_label(label)[1].lower(), face_value_float_for_sort(split_denom_label(label)[0]), split_denom_label(label)[0]))
    add_denom_option = f'Add denomination from Numista N# for {country}'
    manual_denom_option = f'Add custom denomination manually for {country}'
    if not denom_options:
        add_now = prompt_yes_no(f'No denominations found for {country}.', 'Add one from a Numista N# now?\n\nThis calls the Numista API, pulls the real country/value/currency, and saves the type to Coin_Types.csv before you enter year/mint.')
        if add_now:
            return prompt_numista_country_denom_from_api(country)
        return None
    denom_label = choose_from_list(f'Select denomination for {country}:\n\nIf this denomination is missing, choose Add denomination from Numista N#.', denom_options + [add_denom_option, manual_denom_option])
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
    return {'country': country, 'denomination': denom_label, 'currency': currency, 'face_value': face_value}



def prompt_missing_numista_coin(session, year, mint_name):
    """Force + / - selection, no default. Returns True to keep/save, False to cancel."""
    selection = None

    def selected(text, is_selected):
        return reverse(text) if is_selected else dim(text)
    while True:
        clear()
        coin_label = f"{year}-{mint_name}  |  {session.get('country', '')} | {session['denomination']}"
        print(c('═' * 100, '93'))
        print(bold(red('⚠  POSSIBLE NEW COLLECTION COIN  ⚠'.center(100))))
        print(c('═' * 100, '93'))
        print()
        print(bold(yellow('This coin was NOT found in your Numista CSV.')))
        print()
        print(c('┌' + '─' * 70 + '┐', '96'))
        print(c('│', '96') + bold('  COIN TO VERIFY'.ljust(70)) + c('│', '96'))
        print(c('├' + '─' * 70 + '┤', '96'))
        print(c('│', '96') + f"  Year / Mint : {bold(cyan(str(year) + '-' + mint_name))}".ljust(79)[:70] + c('│', '96'))
        print(c('│', '96') + f"  Country     : {bold(cyan(session.get('country', 'Unknown')))}".ljust(79)[:70] + c('│', '96'))
        print(c('│', '96') + f"  Denomination: {bold(cyan(session['denomination']))}".ljust(79)[:70] + c('│', '96'))
        print(c('│', '96') + f"  Session     : {session['session_name']}".ljust(70) + c('│', '96'))
        print(c('└' + '─' * 70 + '┘', '96'))
        print()
        print(red(bold('IMPORTANT:')), yellow('It may be missing from your collection.'))
        print(yellow('Put this coin in a SPECIAL VERIFY BIN — separate from Reject and Keep/Bulk.'))
        print(dim('You will still get this warning again if you find another matching coin, so you can pick the best one.'))
        print()
        print(bold('Save this coin as NEW COLLECTION in the session CSV?'))
        print()
        yes_text = '  YES — save as NEW COLLECTION  '
        no_text = '  NO — cancel and return to entry  '
        print('   +  ' + selected(green(yes_text), selection is True))
        print('   -  ' + selected(red(no_text), selection is False))
        print()
        if selection is None:
            print(bold(yellow('No option selected yet.')))
        elif selection is True:
            print(green('Selected: YES — this will be marked New Collection.'))
        else:
            print(red('Selected: NO — this will not be saved.'))
        print()
        print(dim('Use + or - to choose. Then press ENTER. BACKSPACE/ESC cancels.'))
        key = read_key()
        if key in ('+', '=', state.KEY_DOWN, state.KEY_RIGHT):
            selection = True
        elif key in ('-', '_', state.KEY_UP, state.KEY_LEFT):
            selection = False
        elif key == state.KEY_ENTER and selection is not None:
            return selection
        elif key in (state.KEY_BACKSPACE, state.KEY_ESC):
            return False



def confirm_session_type(session_type):
    if session_type not in ('Bulk sorting', 'Coin roll hunt'):
        return True
    detail = 'This mode is for quickly adding year + mint mark entries.' if session_type == 'Bulk sorting' else 'This mode is for coin roll hunting with optional roll tracking.'
    return bool(prompt_yes_no(f'Start {session_type}?', detail))



def choose_crh_roll_mode(coin_choice):
    mode = choose_from_list('Coin Roll Hunt roll tracking mode:', ['Automatic roll tracking', 'Manual next-roll selection', 'No roll tracking'])
    if not mode:
        return (None, None)
    if mode == 'No roll tracking':
        return ('none', '')
    qty = get_roll_quantity_for_choice(coin_choice)
    if not qty:
        add_now = prompt_yes_no('No roll quantity saved for this denomination.', 'Automatic tracking needs coins-per-roll. Add it to settings now?')
        if add_now:
            key_name = roll_quantity_key(coin_choice['country'], coin_choice['face_value'], coin_choice['currency'])
            qty = prompt_positive_int(f"Coins per roll for {coin_choice['country']} | {coin_choice['denomination']}:")
            if qty is None:
                return (None, None)
            state.ROLL_QUANTITIES[key_name] = qty
            save_settings()
        elif mode == 'Automatic roll tracking':
            return (None, None)
    if mode == 'Automatic roll tracking':
        return ('automatic', get_roll_quantity_for_choice(coin_choice))
    return ('manual', get_roll_quantity_for_choice(coin_choice) or '')



def new_session(numista_countries, denoms_by_country):
    session_name = text_input('Enter new session name:')
    if not session_name:
        return None
    session_notes = text_input('Enter session notes, optional. Example: where the coins came from, what you paid, cool finds:')
    if session_notes is None:
        session_notes = ''
    session_type = choose_from_list('Select session type:', state.SESSION_TYPES)
    if not session_type:
        return None
    if not confirm_session_type(session_type):
        return None
    coin_choice = choose_country_and_denom(numista_countries, denoms_by_country)
    if not coin_choice:
        return None
    roll_mode = ''
    roll_quantity = ''
    current_roll = 1
    current_roll_count = 0
    if session_type == 'Coin roll hunt':
        roll_mode, roll_quantity = choose_crh_roll_mode(coin_choice)
        if roll_mode is None:
            return None
    path = session_path(session_name)
    if os.path.exists(path):
        choice = choose_from_list('A session with this name already exists. What do you want to do?', ['Resume existing session', 'Overwrite and start fresh', 'Cancel'])
        if choice == 'Resume existing session':
            log = load_session_csv(path)
            current_roll, current_roll_count = infer_roll_state(log, roll_quantity)
        elif choice == 'Overwrite and start fresh':
            log = []
            write_session_csv(path, log)
        else:
            return None
    else:
        log = []
        write_session_csv(path, log)
    session_obj = {'session_name': session_name, 'session_type': session_type, 'country': coin_choice['country'], 'denomination': coin_choice['denomination'], 'currency': coin_choice['currency'], 'face_value': coin_choice['face_value'], 'path': path, 'log': log, 'session_notes': session_notes, 'roll_mode': roll_mode, 'roll_quantity': roll_quantity, 'current_roll': current_roll, 'current_roll_count': current_roll_count}
    save_session_meta(session_obj)
    return session_obj



def confirm_delete_session(filename, path):
    selection = None
    while True:
        clear()
        print(c('=' * 90, '91'))
        print(bold(red('DELETE SESSION CSV?'.center(90))))
        print(c('=' * 90, '91'))
        print()
        print(bold('Selected file:'), cyan(filename))
        print(dim(path))
        print()
        print(red(bold('This moves the session CSV to a backup-style delete filename?')))
        print(yellow('Actually deleting is permanent from this folder, so only confirm if you are sure.'))
        print()
        print('   +  ' + (reverse(green('  YES — delete this session  ')) if selection is True else dim('  YES — delete this session  ')))
        print('   -  ' + (reverse(red('  NO — keep it  ')) if selection is False else dim('  NO — keep it  ')))
        print()
        print(dim('Use + or - to choose. ENTER confirms. BACKSPACE/ESC cancels.'))
        key = read_key()
        if key in ('+', '=', state.KEY_RIGHT, state.KEY_DOWN):
            selection = True
        elif key in ('-', '_', state.KEY_LEFT, state.KEY_UP):
            selection = False
        elif key == state.KEY_ENTER and selection is not None:
            return selection
        elif key in (state.KEY_BACKSPACE, state.KEY_ESC):
            return False



def choose_session_file_for_resume():
    """Session picker that can delete the highlighted session with BACKSPACE."""
    index = 0
    while True:
        files = list_sessions()
        if not files:
            clear()
            print(bold(yellow('No saved sessions found.')))
            print()
            print('Press any key to continue.')
            read_key()
            return None
        index = max(0, min(index, len(files) - 1))
        clear()
        print(c('=' * 100, '94'))
        print(bold(cyan('RESUME SAVED SESSION'.center(100))))
        print(c('=' * 100, '94'))
        print()
        print(bold('Controls:'), 'TAB/DOWN/+ next   UP/- previous   ENTER resume   BACKSPACE delete selected   ESC cancel')
        print(dim('Newest sessions appear first.'))
        print()
        for i, filename in enumerate(files):
            path = os.path.join(state.SESSIONS_DIR, filename)
            try:
                modified = datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M')
                rows = max(0, len(load_session_csv(path)))
                detail = f'{rows} coins | modified {modified}'
            except Exception:
                detail = 'unable to read details'
            line = f'{i + 1:>3}. {filename:<45} {detail}'
            print(reverse(line) if i == index else line)
        key = read_key()
        if key == state.KEY_ESC:
            return None
        if key in (state.KEY_TAB, state.KEY_DOWN, '+', '='):
            index = (index + 1) % len(files)
        elif key in (state.KEY_SHIFT_TAB, state.KEY_UP, '-', '_'):
            index = (index - 1) % len(files)
        elif key == state.KEY_ENTER:
            return files[index]
        elif key == state.KEY_BACKSPACE:
            filename = files[index]
            path = os.path.join(state.SESSIONS_DIR, filename)
            if confirm_delete_session(filename, path):
                try:
                    os.remove(path)
                    clear()
                    print(green(f'Deleted {filename}'))
                    print()
                    print('Press any key to continue.')
                    read_key()
                    index = max(0, index - 1)
                except Exception as exc:
                    clear()
                    print(red(f'Could not delete {filename}: {exc}'))
                    print()
                    print('Press any key to continue.')
                    read_key()



def infer_roll_state(log, roll_quantity=''):
    """Return next current roll and count within roll from saved CRH rows."""
    if not log:
        return (1, 0)
    last = log[-1]
    try:
        roll = int(last.get('roll_number') or 1)
    except ValueError:
        roll = 1
    try:
        count = int(last.get('roll_coin_number') or 0)
    except ValueError:
        count = 0
    try:
        qty = int(roll_quantity or last.get('roll_quantity') or 0)
    except ValueError:
        qty = 0
    if qty and count >= qty:
        return (roll + 1, 0)
    return (max(1, roll), max(0, count))



def resume_session(numista_countries, denoms_by_country):
    selected_file = choose_session_file_for_resume()
    if not selected_file:
        return None
    path = os.path.join(state.SESSIONS_DIR, selected_file)
    log = load_session_csv(path)
    meta = load_session_meta(path)
    if log:
        first = log[0]
        session_name = meta.get('session_name') or first.get('session_name', selected_file.replace('.csv', ''))
        session_type = first.get('session_type', 'Unknown')
        country = first.get('country', '')
        denomination = first.get('denomination', 'Unknown')
        currency = first.get('currency', '')
        face_value = first.get('face_value', '')
        if not country or not face_value:
            coin_choice = choose_country_and_denom(numista_countries, denoms_by_country, country or None)
            if not coin_choice:
                return None
            country = coin_choice['country']
            denomination = coin_choice['denomination']
            currency = coin_choice['currency']
            face_value = coin_choice['face_value']
    else:
        session_name = meta.get('session_name') or selected_file.replace('.csv', '')
        session_type = 'Unknown'
        coin_choice = choose_country_and_denom(numista_countries, denoms_by_country)
        if not coin_choice:
            return None
        country = coin_choice['country']
        denomination = coin_choice['denomination']
        currency = coin_choice['currency']
        face_value = coin_choice['face_value']
    roll_mode = first.get('roll_mode', '') if log else ''
    roll_quantity = first.get('roll_quantity', '') if log else ''
    current_roll, current_roll_count = infer_roll_state(log, roll_quantity)
    return {'session_name': session_name, 'session_type': session_type, 'country': country, 'denomination': denomination, 'currency': currency, 'face_value': face_value, 'path': path, 'log': log, 'session_notes': meta.get('session_notes', ''), 'roll_mode': roll_mode, 'roll_quantity': roll_quantity, 'current_roll': current_roll, 'current_roll_count': current_roll_count}



def refresh_numista_index_for_session(numista_index=None, numista_files=None):
    """Reload Numista CSV/cache before starting or resuming a session.

    This lets users copy a fresh Numista collection export into the Numista CSV
    folder and start/resume sorting without quitting and restarting the app.
    """
    old_file_count = len(numista_files or [])
    old_coin_count = len(numista_index or set())
    loaded = load_numista_index()
    new_index, new_files, new_countries, new_denoms, new_type_index = loaded
    if numista_files is not None and (len(new_files) != old_file_count or len(new_index) != old_coin_count):
        clear()
        print(green('Numista collection data refreshed.'))
        print()
        print(f'CSV files : {old_file_count} -> {len(new_files)}')
        print(f'Owned rows: {old_coin_count} -> {len(new_index)}')
        print()
        print('Press any key to continue.')
        read_key()
    return loaded



def prompt_reject_reason(current_reason=''):
    """Ask why a coin was rejected. Returns a reason string, or None if cancelled."""
    options = list(state.REJECT_REASONS)
    if current_reason and current_reason not in options:
        options.insert(0, f'Keep current reason: {current_reason}')
    choice = choose_from_list('Why was this coin rejected?', options)
    if not choice:
        return None
    if choice.startswith('Keep current reason:'):
        return current_reason
    if choice == 'Other / custom reason':
        custom = text_input('Type the custom reject reason:', current_reason if current_reason not in state.REJECT_REASONS else '')
        return custom.strip() if custom else None
    return choice



def coin_type_label(row):
    year = str(row.get('year', '')).strip() or '????'
    mint = str(row.get('mint', '')).strip() or '?'
    coin_type = str(row.get('coin_type', '')).strip() or 'Unknown type'
    numista_number = str(row.get('numista_number', '')).strip()
    denom = str(row.get('denomination', '')).strip() or 'Unknown denomination'
    country = str(row.get('country', '')).strip() or 'Unknown country'
    number_text = f' | {numista_number}' if numista_number else ''
    return f'{year}-{mint} | {coin_type}{number_text} | {denom} | {country}'



def make_coin(session_name, session_type, country, denom, currency, face_value, year, mint_index, coin_type_option, notes, reject, reject_reason, keep_bulk, numista_found='', possible_missing_collection='', new_collection=False, roll_mode='', roll_number='', roll_coin_number='', roll_quantity=''):
    return {'timestamp': datetime.now().isoformat(timespec='seconds'), 'session_name': session_name, 'session_type': session_type, 'country': country, 'denomination': denom, 'currency': currency, 'face_value': face_value, 'year': year, 'mint': state.MINTS[mint_index], 'coin_type': coin_type_option.get('coin_type', ''), 'numista_number': coin_type_option.get('numista_number', ''), 'numista_title': coin_type_option.get('numista_title', ''), 'numista_category': coin_type_option.get('numista_category', ''), 'notes': notes, 'reject': str(bool(reject)), 'reject_reason': reject_reason if reject else '', 'keep_bulk': str(bool(keep_bulk)), 'numista_found': str(numista_found), 'possible_missing_collection': str(possible_missing_collection), 'new_collection': str(boolish(new_collection) if isinstance(new_collection, str) else bool(new_collection)), 'roll_mode': roll_mode, 'roll_number': str(roll_number), 'roll_coin_number': str(roll_coin_number), 'roll_quantity': str(roll_quantity)}



def reset_coin():
    return ('', 0, 0, '', False, '', False, 'year')



def boolish(value):
    return str(value).lower() in ['true', '1', 'yes']



def get_year_range_for_session(session):
    """Return a practical valid range for the active coin type."""
    country = str(session.get('country', '')).lower()
    denom = str(session.get('denomination', '')).lower()
    max_year = current_year() + 1
    if 'united states' in country and ('1 cent' in denom or '0.01' in denom):
        return (1793, max_year)
    if 'united states' in country:
        return (1792, max_year)
    return (1600, max_year)



def year_warning(session, year):
    if not year:
        return 'Enter a 4-digit year before saving.'
    if not str(year).isdigit():
        return 'Year must contain numbers only.'
    if len(str(year)) < 4:
        return f'Need {4 - len(str(year))} more digit(s) before this coin can save.'
    if len(str(year)) > 4:
        return 'Year must be exactly 4 digits.'
    low, high = get_year_range_for_session(session)
    y = int(year)
    if y < low or y > high:
        suggestions = suggest_year_corrections(year, session.get('log', []), session)
        if suggestions:
            return f"Suspicious year. Did you mean {', '.join((str(x) for x in suggestions[:3]))}?"
        return f'Suspicious year. Expected roughly {low}-{high}.'
    return ''



def can_type_year_digit(session, current_text, digit):
    """Block impossible future years while typing.

    Allows partial years, but blocks the 4th digit if it would make the year
    greater than current year + 1.
    """
    if not digit.isdigit():
        return False
    if len(current_text) >= 4:
        return True
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
    for i in range(4):
        for d in '0123456789':
            if d == text[i]:
                continue
            candidate = int(text[:i] + d + text[i + 1:])
            if plausible_year_for_session(candidate, session):
                candidates.add(candidate)
    for i in range(4):
        for j in range(i + 1, 4):
            for d1 in '0123456789':
                for d2 in '0123456789':
                    chars = list(text)
                    if chars[i] == d1 and chars[j] == d2:
                        continue
                    chars[i] = d1
                    chars[j] = d2
                    if chars[0] == '0':
                        continue
                    candidate = int(''.join(chars))
                    if plausible_year_for_session(candidate, session):
                        candidates.add(candidate)
    if text.startswith('22'):
        candidate = int('20' + text[2:])
        if plausible_year_for_session(candidate, session):
            candidates.add(candidate)
    if text[0] == '1':
        for second in '789':
            candidate = int(text[0] + second + text[2:])
            if plausible_year_for_session(candidate, session):
                candidates.add(candidate)

    def digit_distance(y):
        return sum((a != b for a, b in zip(text, str(y).zfill(4))))

    def score(y):
        return (digit_distance(y), 0 if counts[y] else 1, -counts[y], abs(y - center), abs(y - int(text)))
    return sorted(candidates, key=score)[:5]



def focus_order_for_session(session):
    """Return the visible/selectable focus targets for the active session.

    Next Roll should only exist in Coin Roll Hunt sessions with roll tracking.
    In normal sort modes it is not displayed, so it should not be reachable
    by TAB/arrows. Automatic CRH still shows it as a manual override for
    short or partial rolls.
    """
    order = list(state.BASE_FOCUS_ORDER)
    if session.get('session_type') == 'Coin roll hunt' and session.get('roll_mode') in ('automatic', 'manual'):
        insert_at = order.index('statistics')
        order[insert_at:insert_at] = state.CRH_MANUAL_EXTRA_FOCUS
    return order



def normalize_focus_for_session(session, focus):
    """Move invisible/invalid focus targets back to year entry."""
    order = focus_order_for_session(session)
    if focus in order:
        return focus
    return 'year'



def next_focus(session, focus, direction=1):
    order = focus_order_for_session(session)
    focus = normalize_focus_for_session(session, focus)
    i = order.index(focus)
    return order[(i + direction) % len(order)]



def prompt_manual_roll_overflow(session, next_coin_number, roll_quantity):
    """Manual CRH overflow guard.

    Returns:
      "extra"     -> save this coin in the current roll even though it exceeds the roll quantity
      "next_roll" -> advance to the next roll and save this coin as coin #1 there
      None        -> cancel save and return to entry
    """
    selection = 0
    options = [('extra', 'Confirm extra coin in current roll'), ('next_roll', 'Start next roll and add this coin there'), ('cancel', 'Cancel and return to entry')]
    while True:
        clear()
        current_roll = int(session.get('current_roll', 1) or 1)
        print(c('=' * 100, '93'))
        print(bold(yellow('MANUAL CRH ROLL LIMIT REACHED'.center(100))))
        print(c('=' * 100, '93'))
        print()
        print(bold('Current roll:'), green(str(current_roll)))
        print(bold('Saved coins in this roll:'), green(str(session.get('current_roll_count', 0))))
        print(bold('Expected coins per roll:'), cyan(str(roll_quantity)))
        print()
        print(yellow(f'Saving this coin would make roll {current_roll} contain {next_coin_number} coins.'))
        print(dim('Choose whether this is an intentional extra coin, or whether this coin should begin the next roll.'))
        print()
        for i, (_, label) in enumerate(options):
            prefix = '> ' if i == selection else '  '
            line = prefix + label
            print(reverse(line) if i == selection else line)
        print()
        print(dim('TAB/DOWN/+ next | UP/- previous | ENTER confirm | BACKSPACE/ESC cancel'))
        key = read_key()
        if key in (state.KEY_BACKSPACE, state.KEY_ESC):
            return None
        if key in (state.KEY_TAB, state.KEY_DOWN, '+', '='):
            selection = (selection + 1) % len(options)
            continue
        if key in (state.KEY_SHIFT_TAB, state.KEY_UP, '-', '_'):
            selection = (selection - 1) % len(options)
            continue
        if key == state.KEY_ENTER:
            value = options[selection][0]
            return None if value == 'cancel' else value



def save_current_coin(session, year, mint_index, coin_type_index, notes, reject, reject_reason, keep_bulk, editing_index, numista_index=None):
    if not (len(year) == 4 and year.isdigit()):
        return (False, editing_index)
    mint_name = state.MINTS[mint_index]
    coin_type_option = selected_type_option(session, year, mint_index, coin_type_index)
    if coin_type_option.get('coin_type') == 'OTHER':
        manual_option, other_note = prompt_manual_coin_type(session, year, mint_name, notes)
        if not manual_option:
            return (False, editing_index)
        coin_type_option = manual_option
        if not str(notes).strip():
            notes = other_note
    numista_found = ''
    possible_missing = ''
    new_collection = False
    if numista_index is not None:
        found = coin_exists_in_numista(numista_index, session, year, mint_name)
        numista_found = str(found)
        possible_missing = str(not found)
        if not found:
            keep_entry = prompt_missing_numista_coin(session, year, mint_name)
            if not keep_entry:
                return (False, editing_index)
            reject = False
            reject_reason = ''
            keep_bulk = False
            new_collection = True
    if reject and (not str(reject_reason).strip()):
        reject_reason = prompt_reject_reason()
        if not reject_reason:
            return (False, editing_index)
    roll_mode = session.get('roll_mode', '')
    roll_number = ''
    roll_coin_number = ''
    roll_quantity = session.get('roll_quantity', '') or ''
    manual_overflow_action = None
    if session.get('session_type') == 'Coin roll hunt' and roll_mode in ('automatic', 'manual') and (editing_index is None):
        roll_number = int(session.get('current_roll', 1) or 1)
        roll_coin_number = int(session.get('current_roll_count', 0) or 0) + 1
        if roll_mode == 'manual':
            try:
                qty = int(roll_quantity or 0)
            except ValueError:
                qty = 0
            if qty and roll_coin_number > qty:
                manual_overflow_action = prompt_manual_roll_overflow(session, roll_coin_number, qty)
                if manual_overflow_action is None:
                    return (False, editing_index)
                if manual_overflow_action == 'next_roll':
                    roll_number += 1
                    roll_coin_number = 1
    coin = make_coin(session['session_name'], session['session_type'], session.get('country', ''), session['denomination'], session.get('currency', ''), session.get('face_value', ''), year, mint_index, coin_type_option, notes, reject, reject_reason, keep_bulk, numista_found, possible_missing, new_collection, roll_mode, roll_number, roll_coin_number, roll_quantity)
    if editing_index is not None:
        session['log'][editing_index] = coin
        editing_index = None
    else:
        session['log'].append(coin)
        if session.get('session_type') == 'Coin roll hunt' and session.get('roll_mode') in ('automatic', 'manual'):
            session['current_roll'] = int(roll_number or session.get('current_roll', 1) or 1)
            session['current_roll_count'] = int(roll_coin_number or 0)
            if session.get('roll_mode') == 'automatic':
                try:
                    qty = int(session.get('roll_quantity') or 0)
                except ValueError:
                    qty = 0
                if qty and session['current_roll_count'] >= qty:
                    session['current_roll'] = int(session.get('current_roll', 1) or 1) + 1
                    session['current_roll_count'] = 0
    write_session_csv(session['path'], session['log'])
    save_session_meta(session)
    return (True, editing_index)



def session_counts(log):
    """Return (total_count, today_count) for the active session CSV log."""
    today = datetime.now().date().isoformat()
    total = len(log)
    today_count = 0
    for coin in log:
        timestamp = str(coin.get('timestamp', ''))
        if timestamp[:10] == today:
            today_count += 1
    return (total, today_count)



def change_current_country_denom(session):
    choice = choose_country_and_denom(session.get('numista_countries', []), session.get('denoms_by_country', {}), session.get('country'))
    if not choice:
        return False
    session['country'] = choice['country']
    session['denomination'] = choice['denomination']
    session['currency'] = choice['currency']
    session['face_value'] = choice['face_value']
    if choice.get('_numista_type_index'):
        session['numista_type_index'] = choice['_numista_type_index']
        try:
            numista_index, numista_files, numista_countries, denoms_by_country, numista_type_index = load_numista_index()
            session['numista_index'] = numista_index
            session['numista_csv_count'] = len(numista_files)
            session['numista_coin_count'] = len(numista_index)
            session['numista_countries'] = numista_countries
            session['denoms_by_country'] = denoms_by_country
            session['numista_type_index'] = numista_type_index
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
    log = session['log']
    if not log:
        clear()
        print(bold(yellow('No saved coins yet.')))
        print()
        print('Press BACKSPACE or ENTER to return.')
        while True:
            key = read_key()
            if key in (state.KEY_BACKSPACE, state.KEY_ENTER, state.KEY_ESC):
                return None
    if start_index is None:
        index = len(log) - 1
    else:
        index = max(0, min(int(start_index), len(log) - 1))
    top_index = index

    def format_previous_coin_line(i, coin):
        flags = []
        if boolish(coin.get('reject', False)):
            reason = coin.get('reject_reason', '')
            flags.append(red('REJECT' + (f': {reason}' if reason else '')))
        if boolish(coin.get('keep_bulk', False)):
            flags.append(green('KEEP/BULK'))
        if boolish(coin.get('new_collection', False)):
            flags.append(yellow('NEW COLLECTION'))
        flag_text = f" [{' | '.join(flags)}]" if flags else ''
        return f"{i + 1:>4}. {coin.get('year', '')}-{coin.get('mint', '')} | {coin.get('coin_type', 'Unknown type')} | {coin.get('denomination', '')} | {coin.get('notes', '')}{flag_text}"
    while True:
        terminal_rows = shutil.get_terminal_size((110, 30)).lines
        visible_count = max(5, terminal_rows - 11)
        visible_count = min(visible_count, len(log))
        if index < top_index:
            top_index = index
        elif index >= top_index + visible_count:
            top_index = index - visible_count + 1
        top_index = max(0, min(top_index, max(0, len(log) - visible_count)))
        bottom_index = min(len(log), top_index + visible_count)
        clear()
        print(c('=' * 110, '94'))
        print(bold(cyan('EDIT PREVIOUS COINS'.center(110))))
        print(c('=' * 110, '94'))
        print()
        print(bold('Controls:'), 'TAB/+ = newer/down   SHIFT+TAB/- = older/up   ENTER = edit selected   BACKSPACE = back')
        print(dim('The highlighted row stays on screen; the list scrolls as you move through older/newer coins.'))
        print(dim(f'Showing {top_index + 1}-{bottom_index} of {len(log)} saved coins.'))
        print()
        if top_index > 0:
            print(dim(f'  ... {top_index} older coin(s) above ...'))
        for i in range(top_index, bottom_index):
            line = format_previous_coin_line(i, log[i])
            print(reverse(line) if i == index else line)
        if bottom_index < len(log):
            print(dim(f'  ... {len(log) - bottom_index} newer coin(s) below ...'))
        key = read_key()
        if key == state.KEY_BACKSPACE or key == state.KEY_ESC:
            return None
        if key in ('+', '=', state.KEY_TAB, state.KEY_DOWN):
            index = min(len(log) - 1, index + 1)
        elif key in ('-', '_', state.KEY_SHIFT_TAB, state.KEY_UP):
            index = max(0, index - 1)
        elif key == state.KEY_ENTER:
            return index



def confirm_save_quit(session):
    while True:
        clear()
        print(c('=' * 90, '94'))
        print(bold(yellow('SAVE + QUIT?'.center(90))))
        print(c('=' * 90, '94'))
        print()
        print(bold('Your CSV will be saved here:'))
        print(cyan(session['path']))
        print()
        print(bold('Press ENTER to save and quit.'))
        print(bold('Press BACKSPACE to cancel and return.'))
        print()
        print(dim('ESC also cancels.'))
        key = read_key()
        if key == state.KEY_ENTER:
            write_session_csv(session['path'], session['log'])
            save_session_meta(session)
            return True
        if key in (state.KEY_BACKSPACE, state.KEY_ESC):
            return False



def advance_manual_roll(session):
    if session.get('session_type') != 'Coin roll hunt' or session.get('roll_mode') not in ('automatic', 'manual'):
        return False
    session['current_roll'] = int(session.get('current_roll', 1) or 1) + 1
    session['current_roll_count'] = 0
    clear()
    print(c('=' * 90, '92'))
    print(bold(green('NEXT ROLL STARTED'.center(90))))
    print(c('=' * 90, '92'))
    print()
    print(f"Current roll: {green(str(session['current_roll']))}")
    print()
    print('Press any key to continue.')
    read_key()
    return True


