import unittest

from spa_farm.catalog import SeasonCatalog, normalize_name


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = SeasonCatalog.load()

    def test_load_season(self):
        self.assertGreaterEqual(len(self.catalog.strategies), 30)
        self.assertGreaterEqual(len(self.catalog.available_strategies), 20)
        self.assertEqual(len(self.catalog.goals), 7)
        self.assertEqual(self.catalog.etchings.total_wins, 60)
        self.assertGreater(len(self.catalog.chess), 100)

    def test_default_strategies_limit(self):
        names = self.catalog.default_strategies(20)
        self.assertEqual(len(names), 20)
        self.assertTrue(all(name for name in names))
        self.assertEqual(len(self.catalog.default_strategies(0)), len(self.catalog.available_strategies))

    def test_match_exact_and_quoted(self):
        self.assertEqual(self.catalog.match_strategy("阿米娅").name, "阿米娅")
        self.assertIsNotNone(self.catalog.match_strategy("“变形者集群”"))

    def test_match_ocr_noise(self):
        # OCR 常把引号/空格/部分笔画读丢
        self.assertEqual(self.catalog.match_strategy("阿 米 娅").name, "阿米娅")
        matched = self.catalog.match_strategy("琳琅诗怀雅")
        self.assertIsNotNone(matched)

    def test_unknown_returns_none(self):
        self.assertIsNone(self.catalog.match_strategy("完全不存在的策略名"))

    def test_normalize(self):
        self.assertEqual(normalize_name("“变形者集群”"), "变形者集群")
        self.assertEqual(normalize_name("Touch"), "touch")

    def test_goal_lookup(self):
        goal = self.catalog.goal("task-6")
        self.assertIsNotNone(goal)
        self.assertIn("投资人", goal.bonds)
        self.assertEqual(goal.layers, 50)

    def test_chess_lookup(self):
        self.assertTrue(self.catalog.is_known_oper("塔露拉"))
        self.assertFalse(self.catalog.is_known_oper("这不是干员名"))
        self.assertTrue(len(self.catalog.chess_priority()) > 50)


if __name__ == "__main__":
    unittest.main()
