from misharp_hero.db import init_db
from misharp_hero.services.cafe24_admin import sync_products_incremental
from misharp_hero.services.cafe24_analytics import sync_analytics_days
from misharp_hero.services.sellmate import SellmateClient, sync_inventory
from misharp_hero.services.sera_remote import sync_sera_remote
from misharp_hero.services.sync import sync_launch_metrics

if __name__ == "__main__":
    init_db()
    print("Cafe24 products:", sync_products_incremental(48))
    print("Analytics:", sync_analytics_days(2))
    if SellmateClient().configured():
        print("Sellmate:", sync_inventory())
    else:
        print("Sellmate: SKIP (not configured)")
    print("SERA remote:", sync_sera_remote())
    print("48H HERO:", sync_launch_metrics())
