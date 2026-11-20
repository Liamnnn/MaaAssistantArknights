import unittest

import numpy as np

from spa_farm.battle import ShopReader
from spa_farm.config import ShopPolicy
from spa_farm.geometry import Rect
from spa_farm.ocr import TextLine
from spa_farm.screens import SHOP_CARDS
from spa_farm.vision import Screenshot


class FakeOcr:
    def __init__(self, lines):
        self.lines = lines
        self.calls = []

    def read(self, shot, rect=None):
        self.calls.append(rect)
        if rect is None:
            return self.lines
        return [line for line in self.lines if rect.contains(line.rect.center)]


def line(text, x, y, w=20, h=10):
    return TextLine(text, Rect(x, y, w, h), 0.99)


class ShopReaderTests(unittest.TestCase):
    def setUp(self):
        policy = ShopPolicy(priorities=["维什戴尔", "史尔特尔"], healers=["流明"])
        self.reader = ShopReader(FakeOcr([]), policy)
        self.shot = Screenshot(np.zeros((720, 1280, 3), dtype=np.uint8))

    def test_parse_two_cards(self):
        lines = [
            # 卡 1：x=200
            line("5", 190, 528),
            line("V", 132, 538),
            line("维多利亚", 180, 650),
            line("维什戴尔", 170, 680),
            # 卡 2：x=400
            line("3", 390, 528),
            line("III", 332, 538),
            line("谢拉格", 380, 650),
            line("史尔特尔", 370, 680),
        ]
        ocr = FakeOcr(lines)
        self.reader.ocr = ocr
        cards = self.reader.read_cards(self.shot, None)
        self.assertEqual([c.x for c in cards], [200, 400])
        self.assertEqual(cards[0].cost, 5)
        self.assertEqual(cards[0].tier, 5)
        self.assertEqual(cards[0].name, "维什戴尔")
        self.assertTrue(cards[0].is_oper)
        self.assertEqual(cards[1].name, "史尔特尔")

    def test_empty_slot(self):
        lines = [line("NO INFO", 190, 605)]
        self.reader.ocr = FakeOcr(lines)
        cards = self.reader.read_cards(self.shot, None)
        # 空位没有费用徽章，不会产生卡牌中心；这里只验证不会误识别为干员
        self.assertTrue(all(not c.is_oper for c in cards))

    def test_upgrade_button_filtered(self):
        lines = [
            line("7", 700, 528),  # 升级按钮附近的费用文字，不应算作卡牌
        ]
        self.reader.ocr = FakeOcr(lines)
        cards = self.reader.read_cards(self.shot, upgrade_x=650)
        self.assertEqual(cards, [])


if __name__ == "__main__":
    unittest.main()
