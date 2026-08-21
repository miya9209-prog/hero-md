from __future__ import annotations
import argparse

from misharp_hero.db import init_db
from misharp_hero.services.cafe24_admin import sync_products_full, sync_products_incremental
from misharp_hero.services.cafe24_analytics import sync_analytics_days
from misharp_hero.services.sync import sync_launch_metrics
from misharp_hero.services.cafe24_returns import sync_return_metrics


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--products", action="store_true", help="Cafe24 상품 전체 동기화")
    p.add_argument("--products-incremental", action="store_true", help="최근 48H 수정상품")
    p.add_argument("--analytics", action="store_true", help="Analytics 최근 N일")
    p.add_argument("--analytics-days", type=int, default=2)
    p.add_argument("--launches", action="store_true", help="48H HERO 갱신")
    p.add_argument("--returns", action="store_true", help="48H 완료 HERO 반품률 갱신")
    args = p.parse_args()
    init_db()
    if args.products:
        print("products:", sync_products_full())
    if args.products_incremental:
        print("products_incremental:", sync_products_incremental(48))
    if args.analytics:
        print("analytics:", sync_analytics_days(args.analytics_days))
    if args.launches:
        print("hero:", sync_launch_metrics())
        # 30분 HERO 자동수집과 함께 48시간 완료 상품의 반품률도 갱신합니다.
        print("returns:", sync_return_metrics())
    elif args.returns:
        print("returns:", sync_return_metrics())


if __name__ == "__main__":
    main()
