import contextlib
import copy
import csv
from datetime import datetime, timedelta
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import predict
import settle
from analysis_v2 import candidates
from prediction_records import STRATEGIES, complete_snapshot, settled_summary

NOW = datetime(2026, 11, 5, 12, tzinfo=predict.TZ)


class DailyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.draws, self.preds = self.root/'draws.csv', self.root/'predictions.csv'
        self.history = [dict(date=(NOW.date()-timedelta(days=30-i)).isoformat(),
                             issue=str(i+1), number=f'{i*31%1000:03d}') for i in range(30)]
        self.write_draws(self.history)
        self.preds.write_text(','.join(predict.FIELDS)+'\n', encoding='utf-8')
        for module in (predict, settle):
            for attr, value in [('DRAWS', self.draws), ('PREDICTIONS', self.preds)]:
                handle = patch.object(module, attr, value)
                handle.start()
                self.addCleanup(handle.stop)
        handle = patch.dict(os.environ, {'DRY_RUN': '0'})
        handle.start()
        self.addCleanup(handle.stop)

    def write_draws(self, rows):
        with self.draws.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['date', 'issue', 'number'])
            writer.writeheader()
            writer.writerows(rows)

    def records(self):
        with self.preds.open(newline='') as f:
            return list(csv.DictReader(f))

    def run_predict(self):
        with contextlib.redirect_stdout(io.StringIO()):
            predict.main(NOW)

    def test_production_matches_backtest_and_legacy(self):
        self.write_draws(self.history+[dict(date='2026-11-05',issue='31',number='999'),
                                       dict(date='2026-11-06',issue='32',number='888')])
        self.run_predict()
        rows = self.records()
        self.assertEqual(len(rows), 40)
        for key, method in [(predict.PATTERN_STRATEGY, 'pattern'), (predict.STRATEGY, 'weighted')]:
            group = [r for r in rows if r['strategy'] == key]
            self.assertTrue(complete_snapshot(group))
            self.assertEqual([r['number'] for r in group], candidates(self.history, method, 20))
            self.assertTrue(all(r['target_date'] == '2026-11-05' for r in group))
            self.assertTrue(all(len(r['number']) == 3 for r in group))

    def test_repeat_is_byte_identical_and_old_group_is_preserved(self):
        self.run_predict()
        rows = self.records()
        old = [r for r in rows if r['strategy'] == predict.STRATEGY]
        with self.preds.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=predict.FIELDS)
            writer.writeheader()
            writer.writerows(old)
        prefix = self.preds.read_bytes()
        self.run_predict()
        self.assertTrue(self.preds.read_bytes().startswith(prefix))
        snapshot = self.preds.read_bytes()
        self.run_predict()
        self.assertEqual(snapshot, self.preds.read_bytes())
        self.assertEqual(len(self.records()), 40)

    def test_dry_run_cutoff_and_stale_history_never_write(self):
        before = self.preds.read_bytes()
        with patch.dict(os.environ, {'DRY_RUN': '1'}):
            self.run_predict()
        self.assertEqual(before, self.preds.read_bytes())
        for now in (NOW.replace(hour=19), NOW+timedelta(days=3)):
            with self.assertRaises(RuntimeError):
                predict.main(now)
            self.assertEqual(before, self.preds.read_bytes())
        self.write_draws(self.history[:-4])
        with self.assertRaises(RuntimeError):
            self.run_predict()
        self.assertEqual(before, self.preds.read_bytes())

    def test_invalid_partial_snapshot_stops_and_atomic_failure_preserves_file(self):
        before = self.preds.read_bytes()
        with patch.object(predict.os, 'replace', side_effect=OSError('simulated failure')):
            with self.assertRaises(OSError):
                self.run_predict()
        self.assertEqual(before, self.preds.read_bytes())
        self.run_predict()
        lines = self.preds.read_bytes().splitlines(keepends=True)
        self.preds.write_bytes(b''.join(lines[:-1]))
        before = self.preds.read_bytes()
        with self.assertRaises(RuntimeError):
            self.run_predict()
        self.assertEqual(before, self.preds.read_bytes())

    def test_settlement_and_metrics_are_separate_and_idempotent(self):
        self.run_predict()
        generated = self.records()
        actual = next(r['number'] for r in generated if r['strategy'] == predict.PATTERN_STRATEGY)
        self.write_draws(self.history+[dict(date='2026-11-05', issue='31', number=actual)])
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return NOW.replace(hour=23)
        with patch.object(settle, 'datetime', Clock), contextlib.redirect_stdout(io.StringIO()):
            settle.main()
            before = self.preds.read_bytes()
            settle.main()
        self.assertEqual(before, self.preds.read_bytes())
        for key in STRATEGIES:
            group = [r for r in self.records() if r['strategy'] == key]
            self.assertEqual(len(group), 20)
            self.assertTrue(all(r['status'] == ('hit' if r['number'] == actual else 'miss') for r in group))
            self.assertEqual(len(settled_summary(self.records(), key)), 1)
        new = settled_summary(self.records(), predict.PATTERN_STRATEGY)
        self.assertEqual(new[0]['命中'], 1)
        self.assertEqual(settled_summary(generated, predict.PATTERN_STRATEGY), [])
        bad = copy.deepcopy(self.records())
        bad[0]['created_at'] = '2026-11-05T20:00:00+08:00'
        self.assertEqual(settled_summary(bad, predict.PATTERN_STRATEGY), [])


if __name__ == '__main__':
    unittest.main()
