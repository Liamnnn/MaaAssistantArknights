import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from spa_farm import wizard
from spa_farm.config import AppConfig


class WizardTests(unittest.TestCase):
    def test_valid_maa_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertFalse(wizard._valid_maa_dir(root))
            (root / "resource" / "template" / "MiniGame" / "SPA").mkdir(parents=True)
            self.assertTrue(wizard._valid_maa_dir(root))

    def test_find_adb_prefers_maa_bundled(self):
        with tempfile.TemporaryDirectory() as tmp:
            maa = Path(tmp)
            adb = maa / "adb" / "adb.exe"
            adb.parent.mkdir(parents=True)
            adb.write_bytes(b"x")
            self.assertEqual(wizard.find_adb(maa), adb)

    def test_config_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = AppConfig(mode="badges")
            cfg.maa_dir = "D:/MAA"
            cfg.adb = "D:/MAA/adb/adb.exe"
            cfg.serial = "127.0.0.1:16384"
            cfg.targets.per_strategy_clears = 6
            path = Path(tmp) / "spa-farm.json"
            with mock.patch.object(wizard, "CONFIG_PATH", path):
                wizard.save_config(cfg)
                loaded = wizard.load_or_create_config()
            self.assertEqual(loaded.maa_dir, "D:/MAA")
            self.assertEqual(loaded.serial, "127.0.0.1:16384")
            self.assertEqual(loaded.targets.per_strategy_clears, 6)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["targets"]["strategy_limit"], 20)


if __name__ == "__main__":
    unittest.main()
