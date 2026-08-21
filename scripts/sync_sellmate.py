from misharp_hero.db import init_db
from misharp_hero.services.sellmate import SellmateClient, sync_inventory

if __name__ == "__main__":
    init_db()
    if SellmateClient().configured():
        print(sync_inventory())
    else:
        print("Sellmate: SKIP (not configured)")
