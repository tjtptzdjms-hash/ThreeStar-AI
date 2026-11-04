"""Read-only historical pattern research and chronological backtesting.

Input records use date, issue, number. Scores are rankings, not probabilities.
"""
from collections import Counter
from datetime import date
from itertools import product
from math import sqrt
import random
import re

DIGITS = '0123456789'
NUMBERS = tuple(''.join(x) for x in product(DIGITS, repeat=3))
STRATEGIES = ('hot', 'cold', 'weighted', 'pattern', 'random')


def ordered_draws(records):
    """Validate without silently dropping rows; return oldest first."""
    unique = {}
    for row in records:
        day, issue, number = (str(row[k]).strip() for k in ('date', 'issue', 'number'))
        date.fromisoformat(day)
        if not issue or not re.fullmatch(r'[0-9]{3}', number):
            raise ValueError('期別不可空白；號碼必須為三位數字（例如 007）')
        item = dict(date=day, issue=issue, number=number)
        if issue in unique and unique[issue] != item:
            raise ValueError(f'期別 {issue} 的資料互相衝突')
        unique[issue] = item
    return sorted(unique.values(), key=lambda r: (r['date'], int(r['issue']) if r['issue'].isdigit() else -1, r['issue']))


def features(number):
    digits = [int(d) for d in number]
    return {
        '奇偶': ''.join('奇' if d % 2 else '偶' for d in digits),
        '大小': ''.join('大' if d >= 5 else '小' for d in digits),
        '和值': sum(digits),
        '跨度': max(digits) - min(digits),
        '重號型態': {1: '三同號', 2: '一對', 3: '全不同'}[len(set(digits))],
    }


FEATURES = {n: features(n) for n in NUMBERS}


def history_patterns(records, window=100):
    if window < 1:
        raise ValueError('視窗必須大於零')
    rows = ordered_draws(records)[-window:]
    detail = []
    for i, row in enumerate(rows):
        prior = rows[i - 1]['number'] if i else None
        detail.append({**row, **FEATURES[row['number']], '同位置連莊數':
                       sum(a == b for a, b in zip(prior, row['number'])) if prior else None})
    summary = []
    for key in ('奇偶', '大小', '和值', '跨度', '重號型態'):
        counts = Counter(r[key] for r in detail)
        for value, count in sorted(counts.items(), key=lambda x: str(x[0])):
            summary.append({'牌路': key, '型態': str(value), '次數': count,
                            '比例': count / len(rows), '樣本數': len(rows)})
    return detail, summary


def candidates(history, strategy, top_n=20, seed=0):
    """history is strictly older than the target, in chronological order."""
    if strategy not in STRATEGIES or not 1 <= top_n <= 1000 or not history:
        raise ValueError('策略、組數或歷史資料無效')
    if strategy == 'random':
        return [f'{n:03d}' for n in random.Random(seed).sample(range(1000), top_n)]
    seqs = [[row['number'][p] for row in history] for p in range(3)]
    scores = []
    for seq in seqs:
        counts = Counter(seq)
        misses = {d: next((i for i, x in enumerate(reversed(seq)) if x == d), len(seq)) for d in DIGITS}
        max_count, max_miss = max(counts.values()), max(max(misses.values()), 1)
        if strategy == 'hot':
            scores.append({d: counts[d] / len(seq) for d in DIGITS})
        elif strategy == 'cold':
            scores.append({d: -counts[d] / len(seq) for d in DIGITS})
        elif strategy == 'weighted':
            scores.append({d: .4 * counts[d] / max_count + .6 * misses[d] / max_miss for d in DIGITS})
        else:
            # First-order digit transitions with Laplace smoothing, fitted only
            # to training history. Unseen contexts fall back to uniform scores.
            followers = Counter(b for a, b in zip(seq, seq[1:]) if a == seq[-1])
            scores.append({d: (followers[d] + 1) / (sum(followers.values()) + 10) for d in DIGITS})
    return sorted(NUMBERS, key=lambda n: (-sum(scores[p][n[p]] for p in range(3)), n))[:top_n]


def backtest(records, window=30, top_n=20, max_tests=200, holdout=50, seed=2026):
    """Walk forward, with a fixed latest holdout excluded from selection.

    Rows on the target date are excluded from training as well as later rows.
    Parameters must be fixed before inspecting the holdout results.
    """
    if window < 2 or max_tests < 1 or holdout < 1 or not 1 <= top_n <= 1000:
        raise ValueError('回測參數無效')
    rows = ordered_draws(records)
    tests = []
    for i, target in enumerate(rows):
        prior = [r for r in rows[:i] if r['date'] < target['date']]
        if len(prior) >= window:
            tests.append((target, prior[-window:]))
    tests = tests[-max_tests:]
    if len(tests) <= holdout:
        raise ValueError('資料不足：需有完整訓練視窗、探索期與保留驗證期')
    cut = len(tests) - holdout
    details = []
    for i, (target, history) in enumerate(tests):
        for strategy in STRATEGIES:
            # Stable across changes to max_tests; no shared/global RNG state.
            picks = candidates(history, strategy, top_n, f'{seed}:{target["issue"]}')
            details.append({'date': target['date'], 'issue': target['issue'],
                'actual': target['number'], 'strategy': strategy,
                'split': '探索' if i < cut else '保留驗證',
                'training_end': history[-1]['date'], 'training_size': len(history),
                'picks': ' '.join(picks), 'hit': int(target['number'] in picks)})
    summaries = []
    for split in ('探索', '保留驗證'):
        for strategy in STRATEGIES:
            group = [r for r in details if r['split'] == split and r['strategy'] == strategy]
            n, hits = len(group), sum(r['hit'] for r in group)
            rate, baseline = hits / n, top_n / 1000
            z = 1.959963984540054
            center = (rate + z*z/(2*n)) / (1 + z*z/n)
            radius = z * sqrt(rate*(1-rate)/n + z*z/(4*n*n)) / (1 + z*z/n)
            summaries.append({'區間': split, '策略': strategy, '每期組數': top_n,
                '回測期數': n, '命中期數': hits, '命中率': rate,
                '理論隨機基準': baseline, '差異（百分點）': (rate-baseline)*100,
                '95%區間下限': max(0, center-radius), '95%區間上限': min(1, center+radius)})
    # Select exclusively on exploration; report its holdout outcome separately.
    eligible = [r for r in summaries if r['區間'] == '探索' and r['策略'] != 'random']
    chosen = max(eligible, key=lambda r: (r['命中率'], -STRATEGIES.index(r['策略'])))['策略']
    return details, summaries, chosen
