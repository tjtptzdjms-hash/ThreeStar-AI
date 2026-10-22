"""Settle verified, pre-draw ThreeStar predictions against draws.csv."""
import csv
import os
import tempfile
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

DRAWS = Path('draws.csv')
PREDICTIONS = Path('predictions.csv')
TZ = ZoneInfo('Asia/Taipei')
CUTOFF = time(19, 0)
# Earlier manual runs were not verified as genuine pre-draw predictions.
EXCLUDED_DATES = {'2026-10-19', '2026-10-22'}
FIELDS = [
    'target_date', 'target_issue', 'created_at', 'strategy',
    'window', 'rank', 'number', 'status', 'actual_number', 'settled_at'
]


def read_csv(path):
    if not path.is_file():
        raise RuntimeError(f'找不到 {path}')
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def valid_number(value):
    return len(value) == 3 and value.isascii() and value.isdigit()


def main():
    pred_fields, predictions = read_csv(PREDICTIONS)
    if pred_fields != FIELDS:
        raise RuntimeError('predictions.csv 欄位不符，停止結算')
    draw_fields, draws = read_csv(DRAWS)
    if not {'date', 'issue', 'number'}.issubset(draw_fields or []):
        raise RuntimeError('draws.csv 欄位不符')

    now = datetime.now(TZ)
    official = {}
    for r in draws:
        day, issue, num = (r[k].strip() for k in ('date', 'issue', 'number'))
        if not (day and issue and valid_number(num)):
            continue
        if day in official and official[day] != (issue, num):
            raise RuntimeError(f'{day} 有互相衝突的開獎資料')
        official[day] = (issue, num)

    # Only settle groups with a complete, trustworthy 20-number snapshot.
    groups = {}
    for i, row in enumerate(predictions):
        if row['status'] != 'pending' or row['target_date'] in EXCLUDED_DATES:
            continue
        key = (row['target_date'], row['strategy'], row['window'])
        groups.setdefault(key, []).append(i)

    changed = 0
    for (day, strategy, window), indices in groups.items():
        if day not in official or day > now.date().isoformat():
            continue
        if day == now.date().isoformat() and now.time() < time(21, 30):
            continue
        rows = [predictions[i] for i in indices]
        ranks = [r['rank'] for r in rows]
        if (len(rows) != 20 or
            sorted(ranks, key=lambda x: int(x) if x.isdigit() else -1)
                != [str(i) for i in range(1, 21)]):
            print(f'跳過 {day}: 筆數或排名不完整')
            continue
        numbers = [r['number'] for r in rows]
        if len(set(numbers)) != 20 or not all(valid_number(n) for n in numbers):
            print(f'跳過 {day}: 號碼重複或無效')
            continue
        try:
            stamps = [datetime.fromisoformat(r['created_at']) for r in rows]
            if not all(t.tzinfo is not None and
                       t.astimezone(TZ).date().isoformat() == day and
                       t.astimezone(TZ).time().replace(tzinfo=None) < CUTOFF
                       for t in stamps):
                print(f'跳過 {day}: 預測建立時間無法確認為當日19點前')
                continue
        except ValueError:
            print(f'跳過 {day}: 日期格式錯誤')
            continue
        issue, actual = official[day]
        for i in indices:
            r = predictions[i]
            r['status'] = 'hit' if r['number'] == actual else 'miss'
            r['actual_number'] = actual
            r['target_issue'] = issue
            r['settled_at'] = now.isoformat(timespec='seconds')
            changed += 1
        print(f'{day} {issue}: {actual}, 命中 {int(actual in numbers)}/20')

    if not changed:
        print('無符合條件的待結算預測；檔案未修改')
        return
    if os.getenv('DRY_RUN') == '1':
        print(f'測試模式：原本可結算 {changed} 筆，不寫入檔案')
        return
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='',
                                         dir=PREDICTIONS.parent, prefix='.settle_',
                                         suffix='.csv', delete=False) as f:
            temp_name = f.name
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(predictions)
        os.replace(temp_name, PREDICTIONS)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
    print(f'完成結算 {changed} 筆')


if __name__ == '__main__':
    main()
