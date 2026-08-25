from datetime import datetime

from misharp_hero.services.cafe24_history import month_window, _shift_month


def test_month_window_leap_february():
    start, end = month_window(2024, 2)
    assert start == datetime(2024, 2, 1, 0, 0, 0)
    assert end == datetime(2024, 2, 29, 23, 59, 59)


def test_shift_month_cross_year():
    assert _shift_month(2026, 1, -1) == (2025, 12)
    assert _shift_month(2026, 12, 1) == (2027, 1)
