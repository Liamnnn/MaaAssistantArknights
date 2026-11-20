import unittest

from spa_farm.builds import BUILDS, resolve_build, select_build
from spa_farm.catalog import SeasonCatalog


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = SeasonCatalog.load()

    def test_select_by_goal_and_strategy(self):
        self.assertEqual(select_build(None, "task-6"), "amiya_economy")
        self.assertEqual(select_build(None, "layer-300"), "amiya_economy")
        self.assertEqual(select_build("阿米娅", "medal"), "spirit_swift")
        self.assertEqual(select_build("坚守", "medal"), "guard_swift")
        self.assertEqual(select_build("精准", "medal"), "precision_arcane")
        self.assertEqual(select_build("歌利亚", "medal"), "fast_level")
        self.assertEqual(select_build("歌利亚", "medal", low_profile=True), "guard_swift")

    def test_resolve_explicit(self):
        build = resolve_build(self.catalog, "amiya_economy", None, "medal")
        self.assertEqual(build.id, "amiya_economy")
        self.assertIn("投资人", build.bonds)
        self.assertGreaterEqual(build.upgrade_from_round, 3)

    def test_priority_filters_unknown(self):
        build = BUILDS["amiya_economy"]
        effective = build.effective_priority(self.catalog)
        self.assertNotIn("远山", effective)  # 本赛季干员池里没有
        self.assertIn("锡人", effective)

    def test_all_builds_have_name(self):
        for build in BUILDS.values():
            self.assertTrue(build.name)
            self.assertTrue(build.id)

    def test_upgrade_schedule(self):
        swift = BUILDS["spirit_swift"]
        self.assertFalse(swift.can_upgrade(1))
        self.assertFalse(swift.can_upgrade(2))
        self.assertTrue(swift.can_upgrade(3))
        self.assertFalse(swift.can_upgrade(4))
        self.assertTrue(swift.can_upgrade(5))


if __name__ == "__main__":
    unittest.main()


class BattleBuildIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = SeasonCatalog.load()

    def _player(self):
        from types import SimpleNamespace

        from spa_farm.battle import BattlePlayer
        from spa_farm.config import ShopPolicy, TileSet

        return BattlePlayer(
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
            ShopPolicy(),
            TileSet(),
            catalog=self.catalog,
            logger=lambda *_: None,
        )

    def test_set_strategy_switches_build(self):
        player = self._player()
        player.set_strategy("阿米娅")
        self.assertEqual(player.build.id, "spirit_swift")
        self.assertIn("精准", player.focus.bonds)

    def test_goal_forces_economy_build(self):
        from types import SimpleNamespace

        from spa_farm.battle import BattlePlayer
        from spa_farm.config import ShopPolicy, TileSet

        policy = ShopPolicy(goal="task-6")
        player = BattlePlayer(
            SimpleNamespace(),
            SimpleNamespace(),
            SimpleNamespace(),
            policy,
            TileSet(),
            catalog=self.catalog,
            logger=lambda *_: None,
        )
        self.assertEqual(player.build.id, "amiya_economy")
        self.assertIn("投资人", player.focus.bonds)
