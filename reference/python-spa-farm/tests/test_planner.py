import unittest

from spa_farm.planner import BadgePlan


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.plan = BadgePlan(["A", "B"], per_strategy_clears=3, total_wins=6)

    def test_picks_first_incomplete(self):
        self.assertEqual(self.plan.next_strategy({}, 0), "A")
        self.assertEqual(self.plan.next_strategy({"A": 3}, 3), "B")

    def test_extra_runs_after_badges_when_wins_short(self):
        plan = BadgePlan(["A", "B"], per_strategy_clears=1, total_wins=10)
        self.assertEqual(plan.next_strategy({"A": 1, "B": 1}, 2), "A")
        self.assertEqual(plan.remaining_runs({"A": 1, "B": 1}, 2), 8)

    def test_complete(self):
        self.assertTrue(self.plan.is_complete({"A": 3, "B": 3}, 6))
        self.assertFalse(self.plan.is_complete({"A": 3, "B": 3}, 5))
        self.assertIsNone(self.plan.next_strategy({"A": 3, "B": 3}, 6))

    def test_status_and_remaining(self):
        status = self.plan.status({"A": 1}, 1)
        self.assertEqual(status.strategy, "A")
        self.assertEqual(status.clears, 1)
        self.assertEqual(status.remaining_runs, 5)
        self.assertIn("A", status.summary())

    def test_validate(self):
        self.assertTrue(BadgePlan([], 6, 60).validate())
        self.assertFalse(BadgePlan(["A"], 6, 60).validate())
        self.assertFalse(BadgePlan(["A", "A"], 6, 60).validate())  # 构造函数会去重


if __name__ == "__main__":
    unittest.main()


class PlannerLimitTests(unittest.TestCase):
    def test_limit_only_requires_first_n(self):
        plan = BadgePlan(["A", "B", "C"], per_strategy_clears=3, total_wins=6, strategy_limit=2)
        self.assertEqual(plan.strategies, ["A", "B"])
        self.assertTrue(plan.is_complete({"A": 3, "B": 3}, 6))
        self.assertFalse(plan.is_complete({"A": 3}, 6))
        self.assertEqual(plan.remaining_runs({"A": 3}, 3), 3)

    def test_limit_zero_uses_all(self):
        plan = BadgePlan(["A", "B", "C"], 1, 3, strategy_limit=0)
        self.assertEqual(len(plan.strategies), 3)

    def test_duplicate_names_are_removed(self):
        plan = BadgePlan(["A", "A", "B"], 1, 2)
        self.assertEqual(plan.strategies, ["A", "B"])
