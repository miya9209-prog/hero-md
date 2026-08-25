from __future__ import annotations

import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from misharp_hero.db import init_db
from misharp_hero.services.cafe24_history import sync_completed_months, sync_history_month


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--months", type=int, default=36, help="완료월 기준 최근 N개월 수집")
    p.add_argument("--year", type=int)
    p.add_argument("--month", type=int)
    args = p.parse_args()
    init_db()

    if args.year and args.month:
        print("history_month:", sync_history_month(args.year, args.month))
        return
    print("history:", sync_completed_months(args.months))


if __name__ == "__main__":
    main()
