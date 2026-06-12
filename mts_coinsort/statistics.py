# Auto-split from MTS CoinSort V0.2.0.
# Keep behavior changes small in this refactor; modules are wired together at startup.
from .common import *
from . import app_state as state


def export_menu():
    ensure_sessions_dir()
    ensure_exports_dir()
    files = list_sessions()
    if not files:
        clear()
        print(bold(yellow('No saved session CSVs found to export.')))
        print()
        print('Press any key to return.')
        read_key()
        return
    session_options = []
    option_to_file = {}
    for filename in files:
        path = os.path.join(state.SESSIONS_DIR, filename)
        try:
            rows = len(load_session_csv(path))
            modified = datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M')
            label = f'{filename}  ({rows} coins, modified {modified})'
        except Exception:
            label = f'{filename}  (unable to read details)'
        session_options.append(label)
        option_to_file[label] = filename
    picked_sessions = choose_multiple_from_list('EXPORT DATA - SELECT SESSIONS', session_options, allow_all=True)
    if not picked_sessions:
        return
    picked_files = [option_to_file[label] for label in picked_sessions]
    export_columns = state.CSV_HEADERS + ['source_file']
    picked_columns = choose_multiple_from_list('EXPORT DATA - SELECT COLUMNS', export_columns, allow_all=True)
    if not picked_columns:
        return
    rows = []
    for filename in picked_files:
        rows.extend(read_session_rows(filename))
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    out_path = os.path.join(state.EXPORTS_DIR, f'{timestamp}_coin_sort_export.csv')
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=picked_columns, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, '') for col in picked_columns})
    clear()
    print(c('=' * 100, '92'))
    print(bold(green('EXPORT COMPLETE'.center(100))))
    print(c('=' * 100, '92'))
    print()
    print(f'Exported rows : {green(str(len(rows)))}')
    print(f'Sessions      : {green(str(len(picked_files)))}')
    print(f'Columns       : {green(str(len(picked_columns)))}')
    print()
    print(bold('Saved to:'))
    print(cyan(out_path))
    print()
    print('Press any key to return.')
    read_key()



def session_group_key(row):
    return str(row.get('source_file') or row.get('session_name') or 'Current Session')



def calculate_time_analysis(rows, break_threshold_seconds=300):
    """Estimate active sorting time from saved coin timestamps.

    Time is calculated inside each session/file separately, then summed. This means
    a multi-day gap inside one session, or the gap between Mom/Dad sessions, is not
    counted as active sorting time when it exceeds the break threshold.
    """
    groups = {}
    for row in rows:
        ts = parse_coin_timestamp(row.get('timestamp', ''))
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
    coins_per_hour = total_coins / (active_seconds / 3600.0) if active_seconds > 0 else 0.0
    seconds_per_coin = active_seconds / total_coins if total_coins > 0 and active_seconds > 0 else 0.0
    return {'sessions_with_timestamps': len(groups), 'coins_with_timestamps': len(all_timestamps), 'break_threshold_seconds': break_threshold_seconds, 'calendar_span_seconds': calendar_span_seconds, 'raw_session_span_seconds': raw_session_span_seconds, 'active_seconds': active_seconds, 'ignored_break_seconds': ignored_break_seconds, 'longest_break_seconds': longest_break_seconds, 'counted_gap_count': counted_gap_count, 'ignored_gap_count': ignored_gap_count, 'coins_per_hour': coins_per_hour, 'seconds_per_coin': seconds_per_coin}



def build_statistics_lines(title, rows, selected_files=None):
    """Build a cleaner, less repetitive statistics report."""
    selected_files = selected_files or []
    total = len(rows)
    today = datetime.now().date().isoformat()
    today_total = sum((1 for coin in rows if str(coin.get('timestamp', ''))[:10] == today))
    valid_years = [coin_year_int(coin) for coin in rows]
    valid_years = [year for year in valid_years if year is not None]
    reject_count = sum((1 for coin in rows if boolish(coin.get('reject', False))))
    keep_bulk_count = sum((1 for coin in rows if boolish(coin.get('keep_bulk', False))))
    new_collection_rows = [coin for coin in rows if boolish(coin.get('new_collection', False))]
    new_collection_count = len(new_collection_rows)
    collection_type_counts = Counter((coin_type_label(coin) for coin in new_collection_rows))
    unique_collection_type_count = len(collection_type_counts)
    reject_reason_counts = Counter((str(coin.get('reject_reason', '') or 'No reason saved').strip() for coin in rows if boolish(coin.get('reject', False))))
    year_counts = Counter(valid_years)
    decade_counts = Counter((decade_label(year) for year in valid_years))
    mint_counts = Counter((str(coin.get('mint', '') or 'Unknown') for coin in rows))
    session_type_counts = Counter((str(coin.get('session_type', '') or 'Unknown') for coin in rows))
    country_counts = Counter((str(coin.get('country', '') or 'Unknown') for coin in rows))
    denom_counts = Counter((str(coin.get('denomination', '') or 'Unknown') for coin in rows))
    bucket_order = ['Pennies', 'Nickels', 'Dimes', 'Quarters', 'Half Dollars', 'Dollar Coins', 'Other / Unknown']
    bucket_counts = Counter()
    bucket_values = Counter()
    total_value = 0.0
    for row in rows:
        bucket = denom_bucket_for_row(row)
        value = face_value_float(row.get('face_value', ''))
        bucket_counts[bucket] += 1
        bucket_values[bucket] += value
        total_value += value
    time_stats = calculate_time_analysis(rows)

    def pct(part, whole):
        return part / whole * 100.0 if whole else 0.0

    def every_label(event_count, unit_name):
        if not event_count:
            return f'No {unit_name.lower()} yet'
        coins_per = total / event_count if total else 0
        return f'1 every {coins_per:,.1f} coins'
    collection_find_rate = pct(new_collection_count, total)
    unique_type_rate = pct(unique_collection_type_count, total)
    lines = []
    lines.append('=' * 110)
    lines.append(title.center(110))
    lines.append('=' * 110)
    lines.append('')
    if selected_files:
        lines.append(f'Sessions included          : {len(selected_files)}')
        for filename in selected_files:
            lines.append(f'  - {filename}')
        lines.append('')
    lines.append('Session Summary')
    lines.append('---------------')
    lines.append(f'Total Coins Sorted         : {total:,}')
    lines.append(f'Sorted Today               : {today_total:,}')
    lines.append(f'Total Face Value           : {money(total_value)}')
    lines.append(f'Rejects                    : {reject_count:,}')
    lines.append(f'Kept for Bulk              : {keep_bulk_count:,}')
    lines.append(f'Collection Set-Asides      : {new_collection_count:,}')
    lines.append(f'Unique Collection Types    : {unique_collection_type_count:,}')
    lines.append('')
    lines.append('Collection Results')
    lines.append(f'  Collection set-asides    : {new_collection_count:,}  ({collection_find_rate:.2f}% of sorted coins)')
    lines.append(f"  Set-aside pace           : {every_label(new_collection_count, 'Collection Find')}")
    lines.append(f'  Unique collection types  : {unique_collection_type_count:,}  ({unique_type_rate:.2f}% of sorted coins)')
    lines.append(f"  Unique type pace         : {every_label(unique_collection_type_count, 'Unique Type')}")
    lines.append('')
    lines.append('Sorting Time')
    if time_stats['active_seconds'] > 0:
        lines.append(f"  Active sorting time      : {format_duration(time_stats['active_seconds'])}")
        lines.append(f"  Average time per coin    : {time_stats['seconds_per_coin']:.1f} seconds")
        lines.append(f"  Sorting pace             : {time_stats['coins_per_hour']:,.1f} coins/hour")
        lines.append(f"  Timestamped coins        : {time_stats['coins_with_timestamps']:,}")
        lines.append(f"  Timed sessions           : {time_stats['sessions_with_timestamps']:,}")
        lines.append(f"  Ignored long breaks      : {time_stats['ignored_gap_count']:,}")
    else:
        lines.append('  Active sorting time      : not enough timestamp gaps yet')
        lines.append('  Average time per coin    : not enough timestamp gaps yet')
        lines.append('  Sorting pace             : not enough timestamp gaps yet')
    lines.append('  Note                     : long gaps between sort days are ignored')
    lines.append('')
    lines.append('Denomination Totals')
    for bucket in bucket_order:
        lines.append(f'  {bucket:<18}: {bucket_counts[bucket]:>6} coins  {money(bucket_values[bucket])}')
    lines.append('  ' + '-' * 48)
    lines.append(f"  {'TOTAL':<18}: {total:>6} coins  {money(total_value)}")
    lines.append('')
    if reject_reason_counts:
        lines.append('Reject Reasons')
        for reason, count in reject_reason_counts.most_common():
            reject_pct = count / reject_count * 100 if reject_count else 0
            lines.append(f'  {reason:<28} {count:>5}  {reject_pct:>5.1f}%')
        lines.append('')
    if collection_type_counts:
        lines.append(f'Collection Set-Aside Types ({len(collection_type_counts)} Unique Types)')
        for label, count in collection_type_counts.most_common():
            lines.append(f'  {count:>4}x  {label}')
        lines.append('')
    if valid_years:
        oldest = min(valid_years)
        newest = max(valid_years)
        avg_year = round(sum(valid_years) / len(valid_years), 1)
        lines.append('Date Story')
        lines.append(f'  Oldest coin              : {oldest}')
        lines.append(f'  Newest coin              : {newest}')
        lines.append(f'  Average year             : {avg_year}')
        lines.append('')
        lines.append('Most Common Years')
        max_year_count = max(year_counts.values()) if year_counts else 0
        for year, count in year_counts.most_common(10):
            lines.append(f'  {year}: {count:>4}  {make_bar(count, max_year_count)}')
        lines.append('')
        lines.append('Most Common Decades')
        max_decade_count = max(decade_counts.values()) if decade_counts else 0
        for dec, count in decade_counts.most_common(10):
            lines.append(f'  {dec}: {count:>4}  {make_bar(count, max_decade_count)}')
        lines.append('')
    lines.append('Mint Mark Breakdown')
    max_mint_count = max(mint_counts.values()) if mint_counts else 0
    for mint, count in mint_counts.most_common():
        mint_pct = count / total * 100 if total else 0
        lines.append(f'  {mint:>8}: {count:>4}  {mint_pct:>5.1f}%  {make_bar(count, max_mint_count)}')
    lines.append('')
    if len(country_counts) > 1 or (country_counts and next(iter(country_counts)) not in ('Unknown', '')):
        lines.append('Country Breakdown')
        for country, count in country_counts.most_common(10):
            country_pct = count / total * 100 if total else 0
            lines.append(f'  {country:<28} {count:>5}  {country_pct:>5.1f}%')
        lines.append('')
    lines.append('Denomination Breakdown')
    for denom, count in denom_counts.most_common(12):
        denom_pct = count / total * 100 if total else 0
        lines.append(f'  {denom:<36} {count:>5}  {denom_pct:>5.1f}%')
    lines.append('')
    if len(session_type_counts) > 1 or (session_type_counts and next(iter(session_type_counts)) not in ('Unknown', '')):
        lines.append('Session Type Breakdown')
        for session_type, count in session_type_counts.most_common():
            type_pct = count / total * 100 if total else 0
            lines.append(f'  {session_type:<28} {count:>5}  {type_pct:>5.1f}%')
        lines.append('')
    return lines



def export_statistics_lines(lines, prefix='coin_sort_statistics'):
    ensure_exports_dir()
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    out_path = os.path.join(state.EXPORTS_DIR, f'{timestamp}_{safe_filename(prefix)}.txt')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines).replace('\x1b[', ''))
        f.write('\n')
    return out_path



def show_statistics_page(title, rows, selected_files=None, return_hint='ENTER selects the highlighted action.'):
    action_index = 0
    actions = ['Back', 'Export report']
    while True:
        lines = build_statistics_lines(title, rows, selected_files)
        clear()
        for line in lines:
            if line in ('Session Summary', 'Collection Results', 'Sorting Time', 'Denomination Totals', 'Reject Reasons', 'Date Story', 'Most Common Years', 'Most Common Decades', 'Mint Mark Breakdown', 'Country Breakdown', 'Denomination Breakdown', 'Session Type Breakdown') or line.startswith('Collection Set-Aside Types') or line.startswith('Unique Collection Types Found'):
                print(bold(yellow(line)))
            elif line.startswith('='):
                print(c(line, '94'))
            elif 'TOTAL' in line and 'coins' in line:
                print(bold(green(line)))
            else:
                print(line)
        print(c('-' * 110, '94'))
        rendered_actions = []
        for i, action in enumerate(actions):
            text = f' {action} '
            rendered_actions.append(reverse(text) if i == action_index else bold(text))
        print('   '.join(rendered_actions))
        print(dim(f'TAB/+/- changes the highlighted action. ENTER selects. BACKSPACE/ESC returns. {return_hint}'))
        key = read_key()
        if key in (state.KEY_BACKSPACE, state.KEY_ESC):
            return
        if key in (state.KEY_TAB, state.KEY_DOWN, '+', '='):
            action_index = (action_index + 1) % len(actions)
            continue
        if key in (state.KEY_SHIFT_TAB, state.KEY_UP, '-', '_'):
            action_index = (action_index - 1) % len(actions)
            continue
        if key == state.KEY_ENTER:
            action = actions[action_index]
            if action == 'Back':
                return
            if action == 'Export report':
                out_path = export_statistics_lines(lines, title.lower().replace(' ', '_'))
                clear()
                print(c('=' * 100, '92'))
                print(bold(green('STATISTICS EXPORT COMPLETE'.center(100))))
                print(c('=' * 100, '92'))
                print()
                print(bold('Saved to:'))
                print(cyan(out_path))
                print()
                print('Press any key to return to statistics.')
                read_key()
                continue



def choose_session_files_for_statistics():
    ensure_sessions_dir()
    files = list_sessions()
    if not files:
        clear()
        print(bold(yellow('No saved session CSVs found for statistics.')))
        print()
        print('Press any key to return.')
        read_key()
        return None
    session_options = []
    option_to_file = {}
    for filename in files:
        path = os.path.join(state.SESSIONS_DIR, filename)
        try:
            rows = len(load_session_csv(path))
            modified = datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M')
            label = f'{filename}  ({rows} coins, modified {modified})'
        except Exception:
            label = f'{filename}  (unable to read details)'
        session_options.append(label)
        option_to_file[label] = filename
    picked_sessions = choose_multiple_from_list('STATISTICS - SELECT SESSIONS', session_options, allow_all=True)
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
    title = 'COMBINED SESSION STATISTICS' if len(picked_files) > 1 else 'SESSION STATISTICS'
    show_statistics_page(title, rows, picked_files, 'ENTER/BACKSPACE/ESC returns to home menu.')



def make_bar(count, max_count, width=30):
    if max_count <= 0:
        return ''
    filled = max(1, int(count / max_count * width))
    return '█' * filled



def coin_year_int(coin):
    year = str(coin.get('year', '')).strip()
    if year.isdigit() and len(year) == 4:
        return int(year)
    return None



def decade_label(year):
    return f'{year // 10 * 10}s'



def statistics_menu(session):
    """Statistics page for the active session CSV, using the same fields as home statistics."""
    selected_file = os.path.basename(session.get('path', 'current_session.csv'))
    rows = list(session.get('log', []))
    for row in rows:
        row.setdefault('source_file', selected_file)
    show_statistics_page('SESSION STATISTICS', rows, [selected_file], 'ENTER/BACKSPACE/ESC returns to coin entry.')


