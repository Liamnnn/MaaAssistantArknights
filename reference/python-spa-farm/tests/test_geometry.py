import unittest

from spa_farm.geometry import BASE_HEIGHT, BASE_WIDTH, Point, Rect, scale_point, scale_rect


class GeometryTests(unittest.TestCase):
    def test_scale_720_to_1080(self):
        self.assertEqual(scale_point(Point(640, 360), (1920, 1080)), Point(960, 540))

    def test_scale_rect_roundtrip(self):
        rect = Rect(100, 50, 40, 20)
        self.assertEqual(scale_rect(rect, (BASE_WIDTH, BASE_HEIGHT)), rect)
        scaled = scale_rect(rect, (1920, 1080))
        self.assertEqual(scaled, Rect(150, 75, 60, 30))

    def test_center(self):
        self.assertEqual(Rect(10, 20, 30, 40).center, Point(25, 40))

    def test_clamp_inside(self):
        rect = Rect(-10, -10, 50, 50).clamp((BASE_WIDTH, BASE_HEIGHT))
        self.assertGreaterEqual(rect.x, 0)
        self.assertGreaterEqual(rect.y, 0)
        self.assertLessEqual(rect.right, BASE_WIDTH)

    def test_contains(self):
        rect = Rect(0, 0, 10, 10)
        self.assertTrue(rect.contains(Point(5, 5)))
        self.assertFalse(rect.contains(Point(10, 5)))


if __name__ == "__main__":
    unittest.main()
