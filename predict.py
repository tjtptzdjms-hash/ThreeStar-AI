"""Create separate pre-draw snapshots for legacy and V2 research strategies."""
import csv
import io
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from analysis_v2 import candidates, ordered_draws
from prediction_records import STRATEGIES, complete_snapshot

DRAWS = Path('draws.csv')
PREDICTIONS = Path('predictions.csv')
TZ = ZoneInfo('Asia/Taipei')
WINDOW = 30
TOP_N = 20
HOT_WEIGHT = 0.4
MISS_WEIGHT = 0.6
STRATEGY = 'hot40_miss60_top20'
PATTERN_STRATEGY = 'v2_transition_laplace_w30_top20'
FIELDS = ['target_date', 'target_issue', 'created_at', 'strategy', 'window',
          'rank', 'number', 'status', 'actual_number', 'settled_at']


def next_draw_date(now):
    now = now.astimezone(TZ)
    if now.weekday() == 6:
        raise RuntimeError('星期日不產生預測')
    if now.hour >= 19:
        raise RuntimeError('已超過當日19:00預測截止時間')
    return now.date().isoformat()


def read_draws(target):
    with DRAWS.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    return ordered_draws([r for r in rows if r['date'] < target])[::-1]


def score_digits(rows, position):
    # Preserve the original production ranking, including lexical tie breaks.
    seq = [r['number'][position] for r in rows]
    counts = {d: seq.count(d) for d in '0123456789'}
    misses = {d: next((i for i, v in enumerate(seq) if v == d), len(seq))
              for d in '0123456789'}
    max_count = max(max(counts.values()), 1)
    max_miss = max(max(misses.values()), 1)
    return {d: HOT_WEIGHT * counts[d] / max_count + MISS_WEIGHT * misses[d] / max_miss
            for d in '0123456789'}


def legacy_picks(history):
    scores = [score_digits(history, p) for p in range(3)]
    ranked = [(f'{n:03d}', sum(scores[p][f'{n:03d}'[p]] for p in range(3))/3)
              for n in range(1000)]
    ranked.sort(key=lambda x: (-x[1], x[0]))
    return [number for number, _ in ranked[:TOP_N]]


def main(now=None):
    now = now or datetime.now(TZ)
    if now.tzinfo is None:
        raise ValueError('建立時間必須包含時區')
    now = now.astimezone(TZ)
    target = next_draw_date(now)
    original = PREDICTIONS.read_bytes()
    reader = csv.DictReader(io.StringIO(original.decode('utf-8-sig'), newline=''))
    if reader.fieldnames != FIELDS:
        raise RuntimeError('predictions.csv 欄位格式不符')
    existing = list(reader)
    needed = []
    for strategy in STRATEGIES:
        group = [r for r in existing if r['target_date'] == target
                 and r['strategy'] == strategy and r['window'] == str(WINDOW)]
        if group:
            if not complete_snapshot(group):
                raise RuntimeError(f'{strategy} 已有不完整或無效紀錄，保留檔案並停止')
            print(f'{strategy}：該日期已有完整預測，保留原紀錄')
        else:
            needed.append(strategy)
    if not needed:
        return
    history = read_draws(target)
    if len(history) < WINDOW:
        raise RuntimeError('歷史資料不足')
    if datetime.fromisoformat(history[0]['date']).date() < now.date()-timedelta(days=3):
        raise RuntimeError('歷史資料過舊，停止產生預測')
    history = history[:WINDOW]
    new_rows = []
    for strategy in needed:
        picks = (legacy_picks(history) if strategy == STRATEGY else
                 candidates(history[::-1], 'pattern', TOP_N))
        rows = [dict(target_date=target, target_issue='', created_at=now.isoformat(timespec='seconds'),
                     strategy=strategy, window=str(WINDOW), rank=str(rank), number=number,
                     status='pending', actual_number='', settled_at='')
                for rank, number in enumerate(picks, 1)]
        if not complete_snapshot(rows):
            raise RuntimeError('產生的預測不完整，停止寫入')
        new_rows.extend(rows)
        print(f'{strategy}：{len(rows)}組研究號碼，建立於 {rows[0]["created_at"]}')
        if os.getenv('DRY_RUN') == '1':
            print(' '.join(picks))
    if os.getenv('DRY_RUN') == '1':
        print('測試模式：不寫入正式資料')
        return
    output = io.StringIO(newline='')
    csv.DictWriter(output, fieldnames=FIELDS).writerows(new_rows)
    separator = b'' if original.endswith((b'\n', b'\r')) else b'\r\n'
    # Keep all existing bytes; replace atomically so a failure cannot append half
    # a strategy group. Refuse to overwrite a concurrent local file change.
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile('wb', dir=PREDICTIONS.parent, delete=False) as f:
            temp_name = f.name
            f.write(original + separator + output.getvalue().encode('utf-8'))
        if PREDICTIONS.read_bytes() != original:
            raise RuntimeError('預測檔已變更，停止寫入以保護既有紀錄')
        os.replace(temp_name, PREDICTIONS)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


if __name__ == '__main__':
    main()
