# Auto-split from MTS CoinSort V0.2.0.
# Keep behavior changes small in this refactor; modules are wired together at startup.
from .common import *
from . import app_state as state


def clean_user_path(path):
    """Expand ~ and environment variables from settings.json path values."""
    return os.path.abspath(os.path.expandvars(os.path.expanduser(str(path).strip())))



def face_value_float_for_sort(value):
    try:
        return float(normalize_decimal(value))
    except Exception:
        return 999999.0



def mask_secret(value):
    value = str(value or '')
    if not value:
        return '(not set)'
    if len(value) <= 8:
        return '*' * len(value)
    return value[:4] + '*' * (len(value) - 8) + value[-4:]



def safe_positive_int(value, default=0):
    try:
        number = int(float(str(value).strip()))
    except Exception:
        return default
    return number if number >= 0 else default



def safe_filename(name):
    name = name.strip()
    name = re.sub('[^\\w\\s.-]', '', name)
    name = re.sub('\\s+', '_', name)
    return name or 'coin_sort_session'



def normalize_decimal(value):
    """Normalize values like 0.1, 0.10, 1, 1.00 for matching."""
    try:
        return f'{float(str(value).strip()):.2f}'
    except ValueError:
        return str(value).strip()



def normalize_mint(value):
    value = str(value).strip()
    if value.lower() in ('', 'no mint', 'none', 'nan'):
        return ''
    value = value.upper().replace(' ', '')
    if value in ('P', 'D', 'S', 'W'):
        return value
    if value.startswith('P'):
        return 'P'
    if value.startswith('D'):
        return 'D'
    if value.startswith('S'):
        return 'S'
    if value.startswith('W'):
        return 'W'
    return value



def coin_mint_candidates(mint_value):
    mint = normalize_mint(mint_value)
    if mint in ('', 'P', 'NO MINT'):
        return {'', 'P', 'NO MINT'}
    return {mint}



def make_denom_label(face_value, currency):
    face = normalize_decimal(face_value)
    currency = str(currency).strip()
    return f'{face} {currency}' if currency else face



def split_denom_label(label):
    parts = str(label).strip().split(' ', 1)
    face = normalize_decimal(parts[0]) if parts else ''
    currency = parts[1].strip() if len(parts) > 1 else ''
    return (face, currency)



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
    year = str(row.get('year', '')).strip()
    min_year = str(row.get('min_year', '')).strip()
    max_year = str(row.get('max_year', '')).strip()
    if not min_year and year:
        min_year = year
    if not max_year and min_year:
        max_year = min_year
    if not min_year and max_year:
        min_year = max_year
    return (min_year, max_year)



def year_range_label(min_year, max_year, fallback=''):
    min_year = str(min_year or '').strip()
    max_year = str(max_year or '').strip()
    if min_year and max_year:
        return min_year if min_year == max_year else f'{min_year}-{max_year}'
    return str(fallback or '').strip()



def edit_session_notes(session):
    current = session.get('session_notes', '')
    updated = text_input('Edit session notes. Examples: where coins came from, what you paid, cool finds:', current)
    if updated is None:
        return False
    session['session_notes'] = updated
    save_session_meta(session)
    clear()
    print(green('Session notes saved.'))
    print()
    print('Press any key to continue.')
    read_key()
    return True



def face_value_float(value):
    try:
        return float(normalize_decimal(value))
    except Exception:
        return 0.0



def money(value):
    return f'${value:,.2f}'



def parse_coin_timestamp(value):
    """Parse timestamps saved by the sorter. Returns None for blank/bad values."""
    text = str(value or '').strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%m/%d/%Y %H:%M:%S', '%m/%d/%Y %H:%M'):
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
        parts.append(f'{days}d')
    if hours or days:
        parts.append(f'{hours}h')
    if minutes or hours or days:
        parts.append(f'{minutes}m')
    if not parts:
        parts.append(f'{secs}s')
    return ' '.join(parts)



def current_year():
    return datetime.now().year


