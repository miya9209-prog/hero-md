import argparse
from misharp_hero.db import init_db
from misharp_hero.services.cafe24_admin import sync_products
from misharp_hero.services.sync import sync_launch_metrics

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--products", action="store_true")
    p.add_argument("--launches", action="store_true")
    args = p.parse_args()
    init_db()

    if not args.products and not args.launches:
        args.launches = True

    if args.products:
        print("상품 동기화:", sync_products())
    if args.launches:
        print("48H 동기화:", sync_launch_metrics())
