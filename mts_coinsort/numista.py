# Auto-split from MTS CoinSort V0.2.0.
# Keep behavior changes small in this refactor; modules are wired together at startup.
from .common import *
from . import app_state as state


def numista_api_configured():
    return bool(str(state.NUMISTA_API_KEY or '').strip())



def numista_fetch_type_details(numista_number):
    """Fetch one Numista catalogue type by N# using the saved API key.

    Returns (data, error). data is a dict when successful, error is a readable
    string when credentials/network/API response failed.
    """
    clean_number = clean_numista_number(numista_number)
    if not clean_number:
        return (None, 'No Numista number was entered.')
    if not numista_api_configured():
        return (None, 'No Numista API key is saved. Add it in Settings > Numista API settings first.')
    if not guard_numista_api_call(clean_number):
        return (None, 'Numista API lookup was blocked by your monthly usage guard.')
    url = f'https://api.numista.com/v3/types/{urllib.parse.quote(clean_number)}?lang=en'
    headers = {'Accept': 'application/json', 'Numista-API-Key': state.NUMISTA_API_KEY.strip()}
    if state.NUMISTA_CLIENT_ID.strip():
        headers['Numista-Client-Id'] = state.NUMISTA_CLIENT_ID.strip()
    request = urllib.request.Request(url, headers=headers, method='GET')
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode('utf-8', errors='replace')
        log_numista_api_call(clean_number, success=True)
        return (json.loads(raw), None)
    except urllib.error.HTTPError as exc:
        try:
            details = exc.read().decode('utf-8', errors='replace')
        except Exception:
            details = ''
        log_numista_api_call(clean_number, success=False)
        return (None, f'HTTP {exc.code} from Numista API. {details}'.strip())
    except urllib.error.URLError as exc:
        log_numista_api_call(clean_number, success=False)
        return (None, f'Network error while contacting Numista API: {exc.reason}')
    except Exception as exc:
        log_numista_api_call(clean_number, success=False)
        return (None, f'Could not read Numista API response: {exc}')



def numista_detail_value_text(details):
    value = details.get('value', {}) if isinstance(details.get('value', {}), dict) else {}
    return str(value.get('text', '') or '').strip()



def numista_detail_currency_text(details):
    currency = details.get('currency', {}) if isinstance(details.get('currency', {}), dict) else {}
    text = str(currency.get('full_name', '') or currency.get('name', '') or currency.get('display_name', '') or currency.get('title', '') or '').strip()
    return text



def currency_from_country_fallback(country):
    """Return a useful currency label when Numista omits currency text.

    Some API type responses provide a value like ``1 Cent`` but not a
    convenient currency string for building the local denomination picker.
    This fallback keeps the picker from creating bare labels such as ``0.01``.
    """
    key = re.sub('\\s+', ' ', str(country or '').strip().lower())
    defaults = {'canada': 'Canadian Dollar', 'united states': 'Dollar (1785-date)', 'mexico': 'Peso', 'united kingdom': 'Pound sterling', 'great britain': 'Pound sterling', 'australia': 'Australian Dollar', 'new zealand': 'New Zealand Dollar'}
    return defaults.get(key, '')



def normalize_currency_label(currency, country=''):
    """Clean/repair currency text for picker labels."""
    currency = str(currency or '').strip()
    country = str(country or '').strip()
    if not currency:
        return currency_from_country_fallback(country)
    if '(' in currency and ')' in currency:
        return currency
    low_currency = currency.lower()
    low_country = country.lower()
    if low_currency == 'dollar':
        if 'canada' in low_country:
            return 'Canadian Dollar'
        if 'australia' in low_country:
            return 'Australian Dollar'
        if 'new zealand' in low_country:
            return 'New Zealand Dollar'
        if 'united states' in low_country:
            return 'Dollar (1785-date)'
    return currency



def denomination_label_from_api(details, face_value, currency):
    """Build the picker label from API data without bare numeric placeholders."""
    country = numista_detail_country(details)
    currency = normalize_currency_label(currency, country)
    face_value = normalize_decimal(face_value) if face_value else ''
    value_text = numista_detail_value_text(details)
    if face_value and currency:
        return make_denom_label(face_value, currency)
    if value_text and currency:
        return f'{value_text} {currency}'.strip()
    if value_text:
        return value_text
    if face_value:
        fallback_currency = normalize_currency_label('', country)
        return make_denom_label(face_value, fallback_currency) if fallback_currency else face_value
    return currency



def numista_value_to_face_value(details):
    """Best-effort face-value parser from a Numista API type response.

    The API often returns a display value like ``1 Cent`` or ``25 Cents``.
    This turns common decimal-currency cent values into the normalized numeric
    face value used by the sorter, such as 0.01 or 0.25.
    """
    value = details.get('value', {}) if isinstance(details.get('value', {}), dict) else {}
    for key in ('numeric_value', 'decimal_value', 'face_value', 'value', 'number'):
        raw = value.get(key)
        if raw not in (None, ''):
            try:
                return normalize_decimal(raw)
            except Exception:
                pass
    text = str(value.get('text', '') or details.get('value', '') or '').strip()
    lowered = text.lower()
    frac_map = {'½': 0.5, '1/2': 0.5, '¼': 0.25, '1/4': 0.25}
    amount = None
    for token, number in frac_map.items():
        if token in lowered:
            amount = number
            break
    if amount is None:
        match = re.search('(\\d+(?:\\.\\d+)?)', lowered)
        if match:
            try:
                amount = float(match.group(1))
            except Exception:
                amount = None
    if amount is None:
        return ''
    if any((word in lowered for word in ('cent', 'cents', 'centime', 'centimes', 'penny', 'pence', 'sen'))):
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
    return {'country': country, 'currency': currency, 'face_value': normalize_decimal(face_value), 'denomination': denomination}



def make_coin_type_cache_row_from_numista_choice(choice, details, year='', mint_name=''):
    """Save a Numista API type as a denomination/type seed before coin entry.

    This is used when the user finds a foreign/unexpected coin and chooses
    ``Add from Numista N#`` before typing the year and mint. It avoids temporary
    placeholder countries or currencies by pulling the real country, value,
    currency, title, and year range directly from Numista.
    """
    session_stub = dict(choice or {})
    min_year = str(details.get('min_year', '') or '').strip()
    seed_year = str(year or min_year or '').strip()
    return make_coin_type_cache_row_from_numista_api(session_stub, seed_year, mint_name, details)



def prompt_numista_country_denom_from_api(default_country=''):
    """Prompt for an N#, call the API, confirm, save type, and return choice.

    This replaces the older temporary custom-denomination workflow for coins
    such as Canadian cents found in a US roll. The user enters the N# first,
    the API supplies the country/denomination, then the user continues entering
    year/mint normally in the same session.
    """
    if not numista_api_configured():
        clear()
        print(red('Numista API key is not set.'))
        print()
        print('Go to Settings > Numista API settings and save your API key first.')
        print('Press any key to return.')
        read_key()
        return None
    should_search = prompt_yes_no('Open Numista search in your browser?', 'Find the correct catalogue page, then come back and enter the N# number.\n\nChoose No if you already know the Numista number.')
    if should_search is None:
        return None
    if should_search:
        try:
            webbrowser.open(numista_country_denom_search_url(default_country))
        except Exception:
            pass
    while True:
        prompt = 'Enter the Numista N# for the coin type you want to add. Example: 457 or N#457:\n\nIMPORTANT: Pressing ENTER here will call the Numista API using your saved API key.\nThe API result will provide the country, denomination/value, title, and year range.\nYou will verify the result before anything is saved. ESC cancels.'
        if default_country:
            prompt += f'\n\nExpected country, if known: {default_country}'
        entered = text_input(prompt)
        if entered is None:
            return None
        clean_number = clean_numista_number(entered)
        if not clean_number:
            clear()
            print(red('A Numista number is required.'))
            print('Example: enter 457 or N#457')
            print('Press any key to continue.')
            read_key()
            continue
        cached_row = best_cached_numista_row(clean_number)
        if cached_row:
            local_choice_action = confirm_cached_numista_row(cached_row, clean_number, 'country/denomination selection')
            if local_choice_action is None:
                return None
            if local_choice_action == 'use':
                log_numista_cache_hit(clean_number)
                choice = cached_row_choice(cached_row)
                if not choice:
                    clear()
                    print(red('The local cached row did not contain enough country/denomination data.'))
                    print('The script will continue to the Numista API refresh path.')
                    print('Press any key to continue.')
                    read_key()
                else:
                    all_rows = read_coin_type_cache_rows()
                    remove_custom_denominations_for_country_face(choice.get('country', ''), choice.get('face_value', ''))
                    clear()
                    print(green('Using saved local Numista type.'))
                    print()
                    print(f"Now sorting: {cyan(choice['country'])} | {cyan(choice['denomination'])}")
                    print(f"Saved type: N# {cached_row.get('numista_number', '')} - {cached_row.get('numista_title', '')}")
                    print()
                    print(dim('Next, type the coin year and mint. The cached type should appear when the year matches its saved year/range.'))
                    print('Press any key to continue.')
                    read_key()
                    choice['_numista_type_index'] = build_type_index_from_cache(all_rows)
                    return choice
        details, error = numista_fetch_type_details(clean_number)
        if error:
            clear()
            print(red('Could not fetch that Numista type.'))
            print()
            print(error)
            print()
            retry = prompt_yes_no('Try another N#?', 'Choose No to return without changing country/denomination.')
            if retry:
                continue
            return None
        choice = numista_choice_from_details(details)
        if not choice:
            clear()
            print(red('The API result did not include enough value/country data to create a denomination.'))
            print()
            print('You can try another N#, or add the coin later using an existing country/denomination.')
            print()
            retry = prompt_yes_no('Try another N#?', 'Choose No to return without changing country/denomination.')
            if retry:
                continue
            return None
        confirmed = confirm_numista_type_details(details)
        if confirmed is None:
            return None
        if not confirmed:
            retry = prompt_yes_no('Try another N#?', 'Choose No to return without changing country/denomination.')
            if retry:
                continue
            return None
        row = make_coin_type_cache_row_from_numista_choice(choice, details)
        all_rows = upsert_coin_type_cache_rows([row])
        remove_custom_denominations_for_country_face(choice.get('country', ''), choice.get('face_value', ''))
        clear()
        print(green('Numista type saved and country/denomination selected.'))
        print()
        print(f"Now sorting: {cyan(choice['country'])} | {cyan(choice['denomination'])}")
        print(f"Saved type: N# {row.get('numista_number', '')} - {row.get('numista_title', '')}")
        print()
        print(dim('Next, type the coin year and mint. The type should now appear automatically when the year falls in the Numista range.'))
        print('Press any key to continue.')
        read_key()
        choice['_numista_type_index'] = build_type_index_from_cache(all_rows)
        return choice



def numista_detail_country(details):
    issuer = details.get('issuer', {}) if isinstance(details.get('issuer', {}), dict) else {}
    return str(issuer.get('name', '') or '').strip()



def numista_detail_category(details):
    return str(details.get('category', '') or details.get('type', '') or '').strip()



def numista_detail_years(details):
    min_year = details.get('min_year')
    max_year = details.get('max_year')
    if min_year and max_year:
        return f'{min_year}-{max_year}' if str(min_year) != str(max_year) else str(min_year)
    if min_year:
        return str(min_year)
    if max_year:
        return str(max_year)
    return 'Unknown'



def make_coin_type_cache_row_from_numista_api(session, year, mint_name, details):
    """Convert one Numista /types/{id} response into a range-aware cache row."""
    numista_number = clean_numista_number(details.get('id', ''))
    title = str(details.get('title', '') or 'Unknown type').strip()
    short_type = coin_type_from_numista_title(title)
    category = numista_detail_category(details)
    value_text = numista_detail_value_text(details)
    api_country = numista_detail_country(details)
    currency_text = normalize_currency_label(numista_detail_currency_text(details), api_country or session.get('country', ''))
    min_year = str(details.get('min_year', '') or '').strip()
    max_year = str(details.get('max_year', '') or '').strip()
    if not min_year:
        min_year = str(year or '').strip()
    if not max_year:
        max_year = min_year
    years = year_range_label(min_year, max_year, numista_detail_years(details))
    composition = ''
    comp_obj = details.get('composition', {})
    if isinstance(comp_obj, dict):
        composition = str(comp_obj.get('text', '') or '').strip()
    comments = []
    if api_country:
        comments.append(f'API country: {api_country}')
    if value_text:
        comments.append(f'API value: {value_text}')
    if currency_text:
        comments.append(f'API currency: {currency_text}')
    if years:
        comments.append(f'API years: {years}')
    row_country = api_country or session.get('country', '')
    row_currency = normalize_currency_label(currency_text or session.get('currency', ''), row_country)
    row_face_value = session.get('face_value', '')
    row_denomination = denomination_label_from_api(details, row_face_value, row_currency) if row_face_value else value_text or session.get('denomination', '')
    return make_coin_type_cache_row('numista_api', row_country, row_currency, row_face_value, row_denomination, str(year).strip(), mint_name, short_type, numista_number, title, category, '; '.join(comments), 'numista_api', min_year=min_year, max_year=max_year, year_range=years, composition=composition, weight=details.get('weight', '') or '', diameter=details.get('size', '') or '', thickness=details.get('thickness', '') or '', orientation=details.get('orientation', '') or '')



def clean_numista_number(value):
    """Return only the numeric part from values like 'N# 12345'."""
    match = re.search('(\\d+)', str(value or ''))
    return match.group(1) if match else ''



def numista_url(value):
    number = clean_numista_number(value)
    return f'https://en.numista.com/catalogue/pieces{number}.html' if number else ''



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
    if not state.ANSI_SUPPORTED:
        return f'{text} <{url}>'
    return f'\x1b]8;;{url}\x07{text}\x1b]8;;\x07\x1b[0m'



def coin_type_cache_key(row):
    min_year, max_year = normalized_year_bounds(row)
    source = str(row.get('source', '')).strip()
    year_key = str(row.get('year', '')).strip()
    if source in ('numista_api', 'manual_api') and min_year and max_year:
        year_key = ''
    return (str(row.get('country', '')).strip(), normalize_decimal(row.get('face_value', '')), year_key, str(min_year), str(max_year), normalize_mint(row.get('mint', '')), clean_numista_number(row.get('numista_number', '')), str(row.get('coin_type', '')).strip())



def coin_type_from_numista_title(title):
    """Return a short grouping name from a Numista title.

    Examples:
      1 Cent "Lincoln Cent" (Gold Omega Cent) -> Lincoln Cent
      1 Cent "Liberty Head" -> Liberty Head
      1 Dollar (American Innovation - Illinois) -> American Innovation - Illinois
    """
    title = str(title or '').strip()
    quoted = re.search('"([^"]+)"', title)
    if quoted:
        return quoted.group(1).strip()
    paren = re.search('\\(([^()]+)\\)', title)
    if paren:
        return paren.group(1).strip()
    if ' - ' in title:
        return title.split(' - ', 1)[1].strip()
    return title or 'Unknown type'



def make_coin_type_cache_row(source, country, currency, face_value, denomination, year, mint, coin_type, numista_number, numista_title='', numista_category='', comments='', source_csv='', min_year='', max_year='', year_range='', composition='', weight='', diameter='', thickness='', orientation=''):
    year_text = str(year).strip()
    min_year = str(min_year).strip() if min_year is not None else ''
    max_year = str(max_year).strip() if max_year is not None else ''
    if not min_year and year_text:
        min_year = year_text
    if not max_year and min_year:
        max_year = min_year
    if not year_range:
        year_range = year_range_label(min_year, max_year, year_text)
    return {'source': source, 'country': str(country).strip(), 'currency': str(currency).strip(), 'face_value': normalize_decimal(face_value), 'denomination': str(denomination).strip(), 'year': year_text, 'min_year': str(min_year).strip(), 'max_year': str(max_year).strip(), 'mint': normalize_mint(mint), 'coin_type': str(coin_type or 'Unknown type').strip(), 'numista_number': clean_numista_number(numista_number), 'numista_title': str(numista_title or coin_type or 'Unknown type').strip(), 'numista_category': str(numista_category).strip(), 'year_range': str(year_range or '').strip(), 'composition': str(composition or '').strip(), 'weight': str(weight or '').strip(), 'diameter': str(diameter or '').strip(), 'thickness': str(thickness or '').strip(), 'orientation': str(orientation or '').strip(), 'comments': str(comments).strip(), 'source_csv': os.path.basename(str(source_csv)) if source_csv else '', 'last_seen': datetime.now().isoformat(timespec='seconds')}



def find_cached_numista_rows(numista_number):
    """Return Coin_Types.csv rows already saved for this Numista N#.

    This prevents unnecessary API calls when the user enters an N# that the
    sorter already learned from a Numista export or a previous API lookup.
    """
    clean_number = clean_numista_number(numista_number)
    if not clean_number:
        return []
    rows = []
    for row in read_coin_type_cache_rows():
        if clean_numista_number(row.get('numista_number', '')) == clean_number:
            rows.append(row)

    def row_sort_key(row):
        source = str(row.get('source', ''))
        source_rank = 0 if source == 'numista_api' else 1 if source == 'manual_api' else 2
        min_year, max_year = normalized_year_bounds(row)
        return (source_rank, str(row.get('country', '')).lower(), normalize_decimal(row.get('face_value', '')), safe_int(min_year, 999999), safe_int(max_year, 999999), normalize_mint(row.get('mint', '')))
    rows.sort(key=row_sort_key)
    return rows



def best_cached_numista_row(numista_number):
    rows = find_cached_numista_rows(numista_number)
    return rows[0] if rows else None



def cached_row_choice(row):
    """Create a country/denomination choice from a cached Coin_Types.csv row."""
    if not row:
        return None
    country = str(row.get('country', '')).strip()
    face_value = normalize_decimal(row.get('face_value', ''))
    currency = normalize_currency_label(str(row.get('currency', '')).strip(), country)
    denomination = str(row.get('denomination', '')).strip()
    if not denomination or denomination == face_value:
        denomination = make_denom_label(face_value, currency) if currency else denomination
    if not country or not face_value:
        return None
    return {'country': country, 'currency': currency, 'face_value': face_value, 'denomination': denomination}



def cached_row_type_option(row, current_year='', current_mint='', match_note='local Coin_Types.csv cache'):
    """Create the same option shape used by the normal type picker."""
    choice = cached_row_choice(row) or {}
    min_year, max_year = normalized_year_bounds(row)
    mint = normalize_mint(current_mint if current_mint is not None else row.get('mint', ''))
    return {'coin_type': row.get('coin_type', '') or row.get('numista_title', '') or 'Unknown type', 'numista_number': clean_numista_number(row.get('numista_number', '')), 'numista_title': row.get('numista_title', '') or row.get('coin_type', '') or 'Unknown type', 'numista_category': row.get('numista_category', ''), 'denomination': choice.get('denomination', row.get('denomination', '')), 'country': choice.get('country', row.get('country', '')), 'currency': choice.get('currency', row.get('currency', '')), 'face_value': choice.get('face_value', normalize_decimal(row.get('face_value', ''))), 'year': str(current_year or row.get('year', '')).strip(), 'min_year': min_year, 'max_year': max_year, 'year_range': row.get('year_range', '') or year_range_label(min_year, max_year, row.get('year', '')), 'mint': mint, 'selected_mint': mint, 'source': row.get('source', ''), 'composition': row.get('composition', ''), 'weight': row.get('weight', ''), 'diameter': row.get('diameter', ''), 'thickness': row.get('thickness', ''), 'orientation': row.get('orientation', ''), 'comments': row.get('comments', ''), 'match_note': match_note}



def confirm_cached_numista_row(row, numista_number, context='type'):
    """Ask whether to use the local cached N# row or refresh from the API.

    Returns:
      "use"     -> use the local Coin_Types.csv row
      "refresh" -> continue to Numista API lookup
      None      -> cancel/back
    """
    selection = 0
    actions = ['Use saved local type', 'Refresh from Numista API', 'Cancel']
    rows = find_cached_numista_rows(numista_number)
    match_count = len(rows)
    while True:
        clear()
        print(c('=' * 100, '94'))
        print(bold(cyan('NUMISTA N# FOUND LOCALLY'.center(100))))
        print(c('=' * 100, '94'))
        print()
        print(green(f'N# {clean_numista_number(numista_number)} is already saved in Coin_Types.csv.'))
        print(dim('Using the saved row avoids another Numista API call. You can refresh if you want to replace/enrich it.'))
        print()
        print(f'Saved matches: {match_count}')
        print(f"Source      : {row.get('source', '') or 'unknown'}")
        print(f"N#          : {cyan(clean_numista_number(row.get('numista_number', '')))}")
        print(f"Title       : {bold(row.get('numista_title', '') or row.get('coin_type', '') or 'Unknown')}")
        print(f"Coin type   : {row.get('coin_type', '') or 'Unknown'}")
        print(f"Country     : {row.get('country', '') or 'Unknown'}")
        print(f"Denomination: {row.get('denomination', '') or make_denom_label(row.get('face_value', ''), row.get('currency', '')) or 'Unknown'}")
        print(f"Years       : {row.get('year_range', '') or year_range_label(*normalized_year_bounds(row)) or 'Unknown'}")
        print(f"Mint        : {normalize_mint(row.get('mint', '')) or 'Any / No Mint'}")
        if row.get('composition'):
            print(f"Composition : {row.get('composition')}")
        if row.get('weight'):
            print(f"Weight      : {row.get('weight')} g")
        if row.get('diameter'):
            print(f"Diameter    : {row.get('diameter')} mm")
        print()
        print(dim(f'Context: {context}.'))
        print()
        for i, action in enumerate(actions):
            line = f'  {action}  '
            print(reverse(line) if i == selection else line)
        print()
        print(dim('TAB/DOWN/+ next | UP/- previous | ENTER confirm | BACKSPACE/ESC cancel'))
        key = read_key()
        if key in (state.KEY_BACKSPACE, state.KEY_ESC):
            return None
        if key in (state.KEY_TAB, state.KEY_DOWN, '+', '='):
            selection = (selection + 1) % len(actions)
            continue
        if key in (state.KEY_SHIFT_TAB, state.KEY_UP, '-', '_'):
            selection = (selection - 1) % len(actions)
            continue
        if key == state.KEY_ENTER:
            action = actions[selection]
            if action == 'Use saved local type':
                return 'use'
            if action == 'Refresh from Numista API':
                return 'refresh'
            return None



def option_from_cache_row(row, face_value, year, mint):
    min_year, max_year = normalized_year_bounds(row)
    return {'coin_type': row.get('coin_type', '') or row.get('numista_title', '') or 'Unknown type', 'numista_number': clean_numista_number(row.get('numista_number', '')), 'numista_title': row.get('numista_title', '') or row.get('coin_type', '') or 'Unknown type', 'numista_category': row.get('numista_category', ''), 'denomination': row.get('denomination', '') or make_denom_label(face_value, row.get('currency', '')), 'country': str(row.get('country', '')).strip(), 'face_value': face_value, 'year': str(year or row.get('year', '')).strip(), 'min_year': min_year, 'max_year': max_year, 'year_range': row.get('year_range', '') or year_range_label(min_year, max_year, row.get('year', '')), 'mint': mint, 'source': row.get('source', ''), 'composition': row.get('composition', ''), 'weight': row.get('weight', ''), 'diameter': row.get('diameter', ''), 'thickness': row.get('thickness', ''), 'orientation': row.get('orientation', ''), 'comments': row.get('comments', '')}



def build_type_index_from_cache(rows):
    """Build exact-year and range lookup indexes from Coin_Types.csv rows.

    The returned dict is backwards-compatible for exact lookups using
    (country, face_value, year, mint). It also includes a special "__ranges__"
    list used by get_detected_type_options() for API-added types that span many
    years, such as N#14203 covering 1816-1835.
    """
    type_index = {'__ranges__': []}
    range_seen = set()
    for row in rows:
        country = str(row.get('country', '')).strip()
        face_value = normalize_decimal(row.get('face_value', ''))
        year = str(row.get('year', '')).strip()
        mint = normalize_mint(row.get('mint', ''))
        min_year, max_year = normalized_year_bounds(row)
        source = str(row.get('source', '')).strip()
        if not country or not face_value:
            continue
        if year:
            option = option_from_cache_row(row, face_value, year, mint)
            key = (country, face_value, year, mint)
            bucket = type_index.setdefault(key, [])
            if not any((existing.get('coin_type') == option['coin_type'] and existing.get('numista_number') == option['numista_number'] for existing in bucket)):
                bucket.append(option)
        min_int = safe_int(min_year)
        max_int = safe_int(max_year)
        if source in ('numista_api', 'manual_api') and min_int is not None and (max_int is not None):
            range_key = (country, face_value, min_int, max_int, mint, clean_numista_number(row.get('numista_number', '')), row.get('coin_type', ''))
            if range_key not in range_seen:
                type_index['__ranges__'].append(option_from_cache_row(row, face_value, year, mint))
                range_seen.add(range_key)
    for key in list(type_index.keys()):
        if key == '__ranges__':
            continue
        type_index[key].sort(key=lambda option: (option.get('coin_type', '').lower(), clean_numista_number(option.get('numista_number', '')) or '999999999'))
    type_index['__ranges__'].sort(key=lambda option: (option.get('coin_type', '').lower(), safe_int(option.get('min_year', ''), 999999), clean_numista_number(option.get('numista_number', '')) or '999999999'))
    return type_index



def numista_search_denom_terms(session):
    """Return cleaner denomination search terms for Numista's catalog search.

    The active denomination label can be something like
    ``0.01 Dollar (1785-date)``. Numista's search often does better with
    human terms like ``1 cent`` and without the parenthesized currency era.
    Keep this conservative: use common US names when obvious, then fall back
    to a cleaned denomination label and numeric face/currency.
    """
    country = str(session.get('country', '')).strip().lower()
    face = normalize_decimal(session.get('face_value', ''))
    currency = str(session.get('currency', '')).strip()
    denom = re.sub('\\s*\\([^)]*\\)', '', str(session.get('denomination', '')).strip()).strip()
    if 'united states' in country:
        us_terms = {'0.01': '1 cent', '0.05': '5 cents', '0.10': '10 cents', '0.25': '25 cents', '0.50': '50 cents', '1.00': '1 dollar'}
        if face in us_terms:
            return us_terms[face]
    if denom:
        return denom
    if face and currency:
        return f'{face} {currency}'
    return face



def numista_search_url(session, year, mint_name):
    """Build a broad Numista search URL for finding a missing type.

    Mint marks are intentionally omitted. Searching ``2025 W`` or ``2005 D``
    can return no results even when the type exists, because Numista catalog
    search is type-oriented more than mint-row-oriented. The user can still
    refine the search manually after the browser opens.
    """
    parts = [session.get('country', ''), numista_search_denom_terms(session), str(year)]
    query = '+'.join((re.sub('\\s+', '+', str(p).strip()) for p in parts if p and str(p).strip()))
    return f'https://en.numista.com/catalogue/index.php?r={query}&ct=coin'



def numista_country_denom_search_url(default_country=''):
    """Build a Numista catalogue search page for adding a country/denomination by N#."""
    country = str(default_country or '').strip()
    if country:
        query = urllib.parse.quote_plus(country)
        return f'https://en.numista.com/catalogue/index.php?r={query}&ct=coin'
    return 'https://en.numista.com/catalogue/index.php?ct=coin'



def clickable_numista_number(clean_number):
    """Return a compact clickable N# when the terminal supports OSC-8 links."""
    clean_number = clean_numista_number(clean_number)
    if not clean_number:
        return ''
    label = f'N# {clean_number}'
    if state.ANSI_SUPPORTED:
        return terminal_link(label, numista_url(clean_number))
    return label


