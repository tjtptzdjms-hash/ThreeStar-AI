"""Validation and labels for independent 20-number prediction snapshots."""
from datetime import datetime, date
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Taipei')
STRATEGIES = {
    'v2_transition_laplace_w30_top20': 'V2 同位置轉移牌路（研究）',
    'hot40_miss60_top20': '舊版 熱40／遺漏60（對照）',
}
EXCLUDED_DATES = {'2026-10-19', '2026-10-22'}


def complete_snapshot(rows):
    try:
        if len(rows) != 20 or len({r['number'] for r in rows}) != 20:
            return False
        if sorted(int(r['rank']) for r in rows) != list(range(1, 21)):
            return False
        keys = {(r['target_date'], r['strategy'], r['window'], r['created_at']) for r in rows}
        if len(keys) != 1:
            return False
        day, strategy, window, stamp = next(iter(keys))
        date.fromisoformat(day)
        if strategy not in STRATEGIES or window != '30':
            return False
        created = datetime.fromisoformat(stamp)
        if created.tzinfo is None:
            return False
        local = created.astimezone(TZ)
        if local.date().isoformat() != day or local.hour >= 19:
            return False
        return all(len(r['number']) == 3 and r['number'].isascii() and r['number'].isdigit() for r in rows)
    except (KeyError, ValueError, TypeError):
        return False


def settled_summary(records, strategy):
    groups = {}
    for row in records:
        if row.get('strategy') == strategy and row.get('target_date') not in EXCLUDED_DATES:
            key = (row.get('target_date'), row.get('window'))
            groups.setdefault(key, []).append(row)
    result = []
    for (day, _), rows in sorted(groups.items()):
        if not complete_snapshot(rows) or not all(r.get('status') in ('hit', 'miss') for r in rows):
            continue
        actuals = {r.get('actual_number', '') for r in rows}
        if len(actuals) != 1:
            continue
        actual = next(iter(actuals))
        if len(actual) != 3 or not actual.isascii() or not actual.isdigit():
            continue
        if not all(r['status'] == ('hit' if r['number'] == actual else 'miss') for r in rows):
            continue
        result.append({'日期': day, '命中': int(any(r['status'] == 'hit' for r in rows))})
    return result
