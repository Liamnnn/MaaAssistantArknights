import unittest

from spa_farm.catalog import SeasonCatalog
from spa_farm.config import ShopPolicy
from spa_farm.scoring import build_focus, oper_score, rank_cards


class FakeCard:
    def __init__(self, name, tier=5):
        self.name = name
        self.tier = tier


class ScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = SeasonCatalog.load()
        cls.policy = ShopPolicy()

    def test_focus_from_goal(self):
        self.assertIn("精准", build_focus(self.catalog, "medal").bonds)
        self.assertFalse(build_focus(self.catalog, "medal").is_task)
        task = build_focus(self.catalog, "task-6")
        self.assertIn("投资人", task.bonds)
        self.assertTrue(task.is_task)
        self.assertIn("远见", build_focus(self.catalog, "layer-300").bonds)

    def test_task_focus_beats_general(self):
        focus = build_focus(self.catalog, "task-6")
        stacker = oper_score(self.catalog, self.policy, focus, "复奏", 2)
        general = oper_score(self.catalog, self.policy, focus, "塔露拉", 6)
        self.assertGreater(stacker, general)

    def test_duplicate_bonus(self):
        focus = build_focus(self.catalog, "medal")
        once = oper_score(self.catalog, self.policy, focus, "史尔特尔", 5, purchases=1)
        twice = oper_score(self.catalog, self.policy, focus, "史尔特尔", 5, purchases=2)
        none = oper_score(self.catalog, self.policy, focus, "史尔特尔", 5, purchases=0)
        self.assertGreater(once, none)
        self.assertGreater(twice, once)

    def test_rank_cards(self):
        focus = build_focus(self.catalog, "task-6")
        cards = [FakeCard("塔露拉", 6), FakeCard("复奏", 2), FakeCard("锡人", 2)]
        ranked = rank_cards(self.catalog, self.policy, focus, cards)
        self.assertEqual(ranked[0].name, "复奏")

    def test_unknown_goal_falls_back(self):
        focus = build_focus(self.catalog, "none")
        self.assertFalse(focus.bonds)


if __name__ == "__main__":
    unittest.main()
