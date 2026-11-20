import json
import tempfile
import unittest
from pathlib import Path

from spa_farm.tracker import Progress, format_duration


class TrackerTests(unittest.TestCase):
    def test_record_win_and_loss(self):
        p = Progress()
        p.record("A", "win", 100, 12)
        p.record("A", "loss", 80, 6)
        p.record("A", "aborted", 20)
        self.assertEqual(p.wins, 1)
        self.assertEqual(p.runs, 3)
        self.assertEqual(p.aborted, 1)
        self.assertEqual(p.clears("A"), 1)
        self.assertAlmostEqual(p.average_run_seconds(), 90.0)

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            p = Progress()
            p.record("A", "win", 120, 10)
            p.record_points(160)
            p.save(path)
            loaded = Progress.load(path)
            self.assertEqual(loaded.wins, 1)
            self.assertEqual(loaded.clears("A"), 1)
            self.assertEqual(loaded.points, 160)
            self.assertEqual(len(loaded.history), 1)

    def test_corrupt_file_is_backed_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("{not json", encoding="utf-8")
            p = Progress.load(path)
            self.assertEqual(p.wins, 0)
            self.assertTrue(path.with_suffix(".json.corrupt").exists())

    def test_eta(self):
        p = Progress()
        p.record("A", "win", 60, 10)
        self.assertAlmostEqual(p.eta_seconds(10), 600.0)

    def test_format_duration(self):
        self.assertEqual(format_duration(None), "未知")
        self.assertEqual(format_duration(59), "59s")
        self.assertEqual(format_duration(90), "1m30s")
        self.assertEqual(format_duration(3700), "1h01m")


if __name__ == "__main__":
    unittest.main()
