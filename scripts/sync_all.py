from misharp_hero.db import init_db
from misharp_hero.services.cafe24_admin import sync_products_incremental
from misharp_hero.services.cafe24_analytics import sync_analytics_days
from misharp_hero.services.cafe24_returns import sync_return_metrics
from misharp_hero.services.new_product_discovery import discover_new_products
from misharp_hero.services.sync import sync_launch_metrics


if __name__ == "__main__":
    init_db()
    print("Cafe24 products:", sync_products_incremental(72))
    print("New product discovery:", discover_new_products())
    print("Analytics:", sync_analytics_days(2))
    print("48H product metrics:", sync_launch_metrics())
    print("Return rate:", sync_return_metrics())
