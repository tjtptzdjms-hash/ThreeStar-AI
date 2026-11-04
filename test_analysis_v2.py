import copy
from datetime import date, timedelta
from pathlib import Path
import csv
import unittest
from unittest.mock import patch
import analysis_v2 as a


def fixture(n=80):
    return [dict(date=(date(2025, 1, 1)+timedelta(days=i)).isoformat(),
                 issue=str(i+1), number=f'{(i*37)%1000:03d}') for i in range(n)]


class ResearchTests(unittest.TestCase):
    def test_validation_and_leading_zero(self):
        rows = fixture(8)
        self.assertEqual(a.ordered_draws(rows[::-1])[0]['number'], '000')
        self.assertEqual(len(a.ordered_draws(rows+[rows[0]])), 8)
        with self.assertRaises(ValueError):
            a.ordered_draws(rows+[dict(rows[0], number='999')])
        for bad in ('12', '１２３', 'nan', '-01'):
            with self.assertRaises(ValueError):
                a.ordered_draws([dict(rows[0], number=bad)])

    def test_patterns(self):
        self.assertEqual(a.features('007'), {'奇偶': '偶偶奇', '大小': '小小大', '和值': 7, '跨度': 7, '重號型態': '一對'})
        rows = fixture(2)
        rows[0]['number'], rows[1]['number'] = '007', '017'
        detail, summary = a.history_patterns(rows)
        self.assertIsNone(detail[0]['同位置連莊數'])
        self.assertEqual(detail[1]['同位置連莊數'], 2)
        for key in ('奇偶', '大小', '和值', '跨度', '重號型態'):
            self.assertEqual(sum(r['次數'] for r in summary if r['牌路'] == key), 2)

    def test_unique_candidates_and_reproducibility(self):
        for strategy in a.STRATEGIES:
            picks = a.candidates(fixture(30), strategy, 20, 123)
            self.assertEqual(len(set(picks)), 20)
            self.assertEqual(picks, a.candidates(fixture(30), strategy, 20, 123))

    def test_training_excludes_target_and_same_date(self):
        rows = fixture(25)
        rows[11]['date'] = rows[10]['date']
        original = a.candidates
        seen = []
        def spy(history, strategy, top_n, seed):
            seen.append(copy.deepcopy(history))
            return original(history, strategy, top_n, seed)
        with patch.object(a, 'candidates', side_effect=spy):
            detail, _, _ = a.backtest(rows, 5, 20, 20, 5)
        self.assertEqual(len(seen), len(detail))
        for row, history in zip(detail, seen):
            self.assertEqual(len(history), 5)
            self.assertTrue(all(h['date'] < row['date'] for h in history))
            self.assertNotIn(row['issue'], [h['issue'] for h in history])

    def test_future_changes_cannot_change_past_predictions_or_selection(self):
        rows = fixture()
        before, summary, selected = a.backtest(rows, 10, 20, 40, 10)
        altered = copy.deepcopy(rows)
        for r in altered[-10:]:
            r['number'] = '999'
        after, _, selected_after = a.backtest(altered, 10, 20, 40, 10)
        self.assertEqual([r for r in before if r['split']=='探索'], [r for r in after if r['split']=='探索'])
        self.assertEqual(selected, selected_after)
        self.assertEqual(before[-50]['picks'], after[-50]['picks'])
        self.assertTrue(all(r['理論隨機基準'] == .02 for r in summary))
        self.assertTrue(all(0 <= r['95%區間下限'] <= r['95%區間上限'] <= 1 for r in summary))

    def test_exact_boundary_and_insufficient_history(self):
        detail, _, _ = a.backtest(fixture(12), 10, 8, 2, 1)
        self.assertEqual(len(detail), 10)
        with self.assertRaises(ValueError):
            a.backtest(fixture(11), 10, 8, 2, 1)

    def test_real_data_are_read_only(self):
        root = Path(__file__).resolve().parent
        paths = [root / 'draws.csv', root / 'predictions.csv']
        snapshots = [p.read_bytes() for p in paths]
        with paths[0].open(encoding='utf-8-sig') as f:
            rows = list(csv.DictReader(f))
        detail, summary, selected = a.backtest(rows)
        self.assertEqual(len(detail), 200*5)
        self.assertEqual(len(summary), 10)
        self.assertIn(selected, a.STRATEGIES[:-1])
        self.assertEqual(snapshots, [p.read_bytes() for p in paths])


if __name__ == '__main__':
    unittest.main()
