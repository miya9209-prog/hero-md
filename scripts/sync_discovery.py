from __future__ import annotations

from misharp_hero.db import init_db
from misharp_hero.services.new_product_discovery import discover_new_products


def main():
    init_db()
    print("discovery:", discover_new_products())


if __name__ == "__main__":
    main()
