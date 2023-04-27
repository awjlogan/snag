import snag

import datetime
import unittest


class TestDateTimeFunctions(unittest.TestCase):
    def test_half_hour_floor(self):
        test_cases = (
            (datetime.datetime(2023, 4, 25, 11, 0, 0), datetime.datetime(2023, 4, 25, 11, 0, 0)),
            (datetime.datetime(2023, 4, 25, 11, 1, 0), datetime.datetime(2023, 4, 25, 11, 0, 0)),
            (datetime.datetime(2023, 4, 25, 11, 15, 0), datetime.datetime(2023, 4, 25, 11, 0, 0)),
            (datetime.datetime(2023, 4, 25, 11, 16, 0), datetime.datetime(2023, 4, 25, 11, 0, 0)),
            (datetime.datetime(2023, 4, 25, 11, 30, 0), datetime.datetime(2023, 4, 25, 11, 30, 0)),
            (datetime.datetime(2023, 4, 25, 11, 31, 0), datetime.datetime(2023, 4, 25, 11, 30, 0)),
            (datetime.datetime(2023, 4, 25, 11, 45, 0), datetime.datetime(2023, 4, 25, 11, 30, 0)),
            (datetime.datetime(2023, 4, 25, 11, 46, 0), datetime.datetime(2023, 4, 25, 11, 30, 0)),
        )
        for dt, expected in test_cases:
            with self.subTest(dt=dt):
                result = snag.half_hour_floor(dt)
                self.assertEqual(result, expected)

    def test_half_hour_ceil(self):
        test_cases = (
            (datetime.datetime(2023, 4, 25, 11, 0, 0), datetime.datetime(2023, 4, 25, 11, 30, 0)),
            (datetime.datetime(2023, 4, 25, 11, 1, 0), datetime.datetime(2023, 4, 25, 11, 30, 0)),
            (datetime.datetime(2023, 4, 25, 11, 15, 0), datetime.datetime(2023, 4, 25, 11, 30, 0)),
            (datetime.datetime(2023, 4, 25, 11, 16, 0), datetime.datetime(2023, 4, 25, 11, 30, 0)),
            (datetime.datetime(2023, 4, 25, 11, 30, 0), datetime.datetime(2023, 4, 25, 12, 0, 0)),
            (datetime.datetime(2023, 4, 25, 11, 31, 0), datetime.datetime(2023, 4, 25, 12, 0, 0)),
            (datetime.datetime(2023, 4, 25, 11, 45, 0), datetime.datetime(2023, 4, 25, 12, 0, 0)),
            (datetime.datetime(2023, 4, 25, 11, 46, 0), datetime.datetime(2023, 4, 25, 12, 0, 0)),
        )
        for dt, expected in test_cases:
            with self.subTest(dt=dt):
                result = snag.half_hour_ceil(dt)
                self.assertEqual(result, expected)


if __name__ == '__main__':
    unittest.main()
