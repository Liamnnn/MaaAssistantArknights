import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from spa_farm.battle import BoardState
from spa_farm.config import AppConfig, Targets
from spa_farm.perception import Observation
from spa_farm.runner import Runner
from spa_farm.screens import Scene
from spa_farm.vision import Screenshot


class FakePerception:
    def __init__(self, result=None):
        self.result = result

    def read_result(self, shot):
        return self.result

    def find(self, shot, alias, roi=None):
        return None


class FakeController:
    def __init__(self):
        self.actions = []

    def tap(self, point, settle=0.0):
        self.actions.append(("tap", point))

    def screenshot(self):
        return Screenshot(np.zeros((720, 1280, 3), dtype=np.uint8))

    def close(self):
        pass


def make_runner(tmp: str, mode="badges") -> Runner:
    cfg = AppConfig(mode=mode)
    cfg.targets = Targets(strategies=["A"], per_strategy_clears=1, total_wins=1)
    runner = Runner(cfg, Path(tmp) / "progress.json")
    runner.perception = FakePerception()
    runner.controller = FakeController()
    runner.battle = SimpleNamespace(board=BoardState())
    return runner


class RunnerTests(unittest.TestCase):
    def test_settlement_win_updates_progress_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = make_runner(tmp)
            runner.stats.strategy = "A"
            runner.stats.in_run = True
            runner.stats.run_started_at = time.time() - 60
            obs = Observation(Scene.SETTLEMENT, FakeController().screenshot(), result="win")
            runner._handle_settlement(obs)
            self.assertEqual(runner.progress.wins, 1)
            self.assertEqual(runner.progress.clears("A"), 1)
            self.assertIsNone(runner.stats.strategy)
            self.assertFalse(runner.stats.in_run)
            # 同一次结算重复判定只记一局
            runner._handle_settlement(obs)
            self.assertEqual(runner.progress.wins, 1)
            self.assertTrue((Path(tmp) / "progress.json").exists())

    def test_unknown_result_not_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = make_runner(tmp)
            runner.stats.strategy = "A"
            obs = Observation(Scene.SETTLEMENT, FakeController().screenshot(), result=None)
            runner._handle_settlement(obs)
            self.assertEqual(runner.progress.wins, 0)
            self.assertEqual(runner.progress.runs, 1)

    def test_points_mode_counts_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = make_runner(tmp, mode="points")
            runner.stats.run_started_at = time.time()
            obs = Observation(Scene.SETTLEMENT, FakeController().screenshot(), result="loss")
            runner._handle_settlement(obs)
            self.assertEqual(runner.progress.points, 80)
            self.assertEqual(runner.progress.wins, 0)

    def test_should_stop_when_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = make_runner(tmp)
            runner.progress.strategies = {"A": 1}
            runner.progress.wins = 1
            self.assertTrue(runner._should_stop())

    def test_status_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = make_runner(tmp)
            self.assertIn("A", runner.status_line())


if __name__ == "__main__":
    unittest.main()
