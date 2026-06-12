# Auto-split from MTS CoinSort V0.2.0.
# Keep behavior changes small in this refactor; modules are wired together at startup.
from .common import *
from . import app_state as state


def cache_denoms_by_country():
    """Return denominations already learned in Coin_Types.csv.

    This lets API-added types backfill the country/denomination picker. For
    example, after adding a Canadian cent by N#, Canada 0.01 will come from
    Coin_Types.csv instead of staying as a temporary custom denomination.
    """
    mapping = {}
    try:
        for row in read_coin_type_cache_rows():
            country = str(row.get('country', '')).strip()
            face_value = normalize_decimal(row.get('face_value', ''))
            currency = normalize_currency_label(str(row.get('currency', '')).strip(), country)
            denom = str(row.get('denomination', '')).strip()
            if not denom or denom == face_value:
                denom = make_denom_label(face_value, currency) if currency else denom
            if country and face_value and denom:
                mapping.setdefault(country, set()).add(denom)
    except Exception:
        pass
    return mapping



def ensure_sessions_dir():
    ensure_app_dirs()



def ensure_numista_dir():
    ensure_app_dirs()



def ensure_exports_dir():
    ensure_app_dirs()



def ensure_coin_types_csv():
    """Create Coin_Types.csv if it does not exist yet."""
    ensure_app_dirs()
    if not os.path.exists(state.COIN_TYPES_PATH):
        with open(state.COIN_TYPES_PATH, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=state.COIN_TYPES_HEADERS, extrasaction='ignore')
            writer.writeheader()



def read_coin_type_cache_rows():
    ensure_coin_types_csv()
    rows = []
    try:
        with open(state.COIN_TYPES_PATH, 'r', newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                normalized = {key: row.get(key, '') for key in state.COIN_TYPES_HEADERS}
                min_year, max_year = normalized_year_bounds(normalized)
                normalized['min_year'] = min_year
                normalized['max_year'] = max_year
                if not normalized.get('year_range'):
                    normalized['year_range'] = year_range_label(min_year, max_year, normalized.get('year', ''))
                rows.append(normalized)
    except Exception:
        rows = []
    return rows



def write_coin_type_cache_rows(rows):
    ensure_app_dirs()
    with open(state.COIN_TYPES_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=state.COIN_TYPES_HEADERS, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            min_year, max_year = normalized_year_bounds(row)
            clean_row = {key: row.get(key, '') for key in state.COIN_TYPES_HEADERS}
            clean_row['min_year'] = min_year
            clean_row['max_year'] = max_year
            if not clean_row.get('year_range'):
                clean_row['year_range'] = year_range_label(min_year, max_year, clean_row.get('year', ''))
            repaired_currency = normalize_currency_label(clean_row.get('currency', ''), clean_row.get('country', ''))
            repaired_face = normalize_decimal(clean_row.get('face_value', ''))
            if repaired_currency and (not clean_row.get('currency') or str(clean_row.get('denomination', '')).strip() == repaired_face):
                clean_row['currency'] = repaired_currency
                clean_row['denomination'] = make_denom_label(repaired_face, repaired_currency)
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
        for field in state.COIN_TYPES_HEADERS:
            if not str(existing.get(field, '')).strip() and str(row.get(field, '')).strip():
                existing[field] = row.get(field, '')
                changed = True
        existing_face = normalize_decimal(existing.get('face_value', ''))
        new_currency = normalize_currency_label(row.get('currency', ''), row.get('country', '') or existing.get('country', ''))
        existing_denom = str(existing.get('denomination', '')).strip()
        if new_currency and existing_face and (not existing.get('currency') or existing_denom == existing_face):
            existing['currency'] = new_currency
            existing['denomination'] = make_denom_label(existing_face, new_currency)
            changed = True
    if changed or not os.path.exists(state.COIN_TYPES_PATH):
        write_coin_type_cache_rows(existing_rows)
    return existing_rows



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
    csv_files = [os.path.join(state.NUMISTA_DIR, name) for name in os.listdir(state.NUMISTA_DIR) if name.lower().endswith('.csv')]
    for path in csv_files:
        try:
            with open(path, 'r', newline='', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                next(reader, None)
                for row in reader:
                    if len(row) < 21:
                        continue
                    country = row[0].strip()
                    currency = row[3].strip() if len(row) > 3 else ''
                    face_value = normalize_decimal(row[4]) if len(row) > 4 else ''
                    numista_number = row[6].strip() if len(row) > 6 else ''
                    title = row[7].strip() if len(row) > 7 else ''
                    numista_category = row[8].strip() if len(row) > 8 else ''
                    export_year_range = row[9].strip() if len(row) > 9 else ''
                    composition = row[11].strip() if len(row) > 11 else ''
                    weight = row[12].strip() if len(row) > 12 else ''
                    diameter = row[13].strip() if len(row) > 13 else ''
                    thickness = row[16].strip() if len(row) > 16 else ''
                    orientation = row[17].strip() if len(row) > 17 else ''
                    gregorian_year = row[19].strip() if len(row) > 19 else ''
                    mintmark = normalize_mint(row[20]) if len(row) > 20 else ''
                    if not country or not face_value:
                        continue
                    countries.add(country)
                    denom_label = make_denom_label(face_value, currency)
                    denom_map.setdefault(country, set()).add(denom_label)
                    if gregorian_year:
                        cache_rows_to_seed.append(make_coin_type_cache_row('numista_csv', country, currency, face_value, denom_label, gregorian_year, mintmark, title or 'Unknown type', numista_number, title, numista_category, '', path, min_year=gregorian_year, max_year=gregorian_year, year_range=export_year_range or gregorian_year, composition=composition, weight=weight, diameter=diameter, thickness=thickness, orientation=orientation))
                    if not gregorian_year:
                        continue
                    quantity = '1'
                    if len(row) > 24:
                        quantity = row[24].strip() or '0'
                    try:
                        if float(quantity) <= 0:
                            continue
                    except ValueError:
                        pass
                    index.add((country, face_value, gregorian_year, mintmark))
        except Exception:
            continue
    for cache_country, labels in cache_denoms_by_country().items():
        if cache_country:
            countries.add(cache_country)
            denom_map.setdefault(cache_country, set()).update(labels)
    for item in state.CUSTOM_DENOMINATIONS:
        custom_country = str(item.get('country', '')).strip()
        custom_label = str(item.get('denomination', '')).strip() or make_denom_label(item.get('face_value', ''), item.get('currency', ''))
        if custom_country and custom_label:
            countries.add(custom_country)
            denom_map.setdefault(custom_country, set()).add(custom_label)
    countries = sorted(countries)
    denoms_by_country = {country: sorted(labels, key=lambda label: (split_denom_label(label)[1].lower(), face_value_float_for_sort(split_denom_label(label)[0]), split_denom_label(label)[0])) for country, labels in denom_map.items()}
    coin_type_rows = upsert_coin_type_cache_rows(cache_rows_to_seed)
    type_index = build_type_index_from_cache(coin_type_rows)
    return (index, csv_files, countries, denoms_by_country, type_index)



def coin_exists_in_numista(numista_index, session, year, mint_name):
    country = session.get('country', '').strip()
    face_value = normalize_decimal(session.get('face_value', ''))
    if not country or not face_value or (not year):
        return True
    candidates = coin_mint_candidates(mint_name)
    return any(((country, face_value, str(year).strip(), mint) in numista_index for mint in candidates))



def session_path(session_name):
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    return os.path.join(state.SESSIONS_DIR, f'{timestamp}_{safe_filename(session_name)}.csv')



def write_session_csv(path, log):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=state.CSV_HEADERS, extrasaction='ignore')
        writer.writeheader()
        for row in log:
            writer.writerow(row)



def load_session_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, 'r', newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))



def session_meta_path(csv_path):
    return os.path.splitext(csv_path)[0] + '.session.json'



def load_session_meta(csv_path):
    path = session_meta_path(csv_path)
    if not os.path.exists(path):
        return {'session_name': '', 'session_notes': ''}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {'session_name': str(data.get('session_name', '')), 'session_notes': str(data.get('session_notes', ''))}
    except Exception:
        return {'session_name': '', 'session_notes': ''}



def save_session_meta(session):
    csv_path = session.get('path', '')
    if not csv_path:
        return
    data = {'session_name': session.get('session_name', ''), 'session_notes': session.get('session_notes', ''), 'updated': datetime.now().isoformat(timespec='seconds')}
    try:
        with open(session_meta_path(csv_path), 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass



def list_sessions():
    ensure_sessions_dir()
    files = [f for f in os.listdir(state.SESSIONS_DIR) if f.lower().endswith('.csv')]
    files.sort(key=lambda f: os.path.getmtime(os.path.join(state.SESSIONS_DIR, f)), reverse=True)
    return files



def read_session_rows(filename):
    path = os.path.join(state.SESSIONS_DIR, filename)
    try:
        rows = load_session_csv(path)
        for row in rows:
            row.setdefault('source_file', filename)
        return rows
    except Exception:
        return []



def denom_bucket_for_row(row):
    face = normalize_decimal(row.get('face_value', ''))
    denom = str(row.get('denomination', '')).lower()
    if face == '0.01':
        return 'Pennies'
    if face == '0.05':
        return 'Nickels'
    if face == '0.10':
        return 'Dimes'
    if face == '0.25':
        return 'Quarters'
    if face == '0.50':
        return 'Half Dollars'
    if face == '1.00':
        return 'Dollar Coins'
    if 'penny' in denom or 'pennies' in denom or re.search('\\b1\\s+cent\\b', denom):
        return 'Pennies'
    if 'nickel' in denom or re.search('\\b5\\s+cent\\b', denom):
        return 'Nickels'
    if 'dime' in denom or re.search('\\b10\\s+cent\\b', denom):
        return 'Dimes'
    if 'quarter' in denom or re.search('\\b25\\s+cent\\b', denom):
        return 'Quarters'
    if 'half dollar' in denom or re.search('\\b50\\s+cent\\b', denom):
        return 'Half Dollars'
    if re.search('\\b1\\s+dollar\\b', denom):
        return 'Dollar Coins'
    return 'Other / Unknown'


